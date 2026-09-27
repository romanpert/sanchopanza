"""Tool selection as a LangChain / LangGraph / deepagents `AgentMiddleware`.

    from sanchopanza.harness.langchain import ToolSelectMiddleware

    middleware = [ToolSelectMiddleware(squire, always={"web_search"}, key_of=thread_id)]
    agent = create_agent(model, tools, middleware=middleware)

`key_of` maps a request to its conversation (the LangGraph `thread_id` on a server). Without
it nothing is kept between requests: safe, but each model call pays its own decision. See the
class docstring.

On every model call the tools on the request are grouped (`group_of`: the tool's
`metadata["server"]`, else the name's prefix before the first `_`, else the name), the squire
is asked which groups the current purpose needs, and the request continues with only those
groups' tools. The purpose is the last human message in the request.

Anything unexpected leaves the request untouched: no tools, a tool without a name, a single
group, no human message, a provider outage, an exception. The middleware can only narrow the
call, never break it, and the squire journals every selection with its probabilities.

Imports nothing from LangChain at module level. With `langchain` installed the class is a
real `AgentMiddleware`; without it, a plain object with the same methods, which is how the
tests drive it. Tested in shape (a request-like object), not against a live agent loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ..squire import Squire
from ..text import truncate
from ..window import ToolWindow

GroupOf = Callable[[Any], str]
NAMES_IN_ABOUT = 6


def _base() -> type:
    try:
        from langchain.agents.middleware.types import AgentMiddleware
    except ImportError:  # the adapter must import and be testable without LangChain
        return object
    return AgentMiddleware


def default_group_of(tool: Any) -> str:
    """The server an MCP tool came from, else the prefix of its name."""
    metadata = getattr(tool, "metadata", None) or {}
    server = metadata.get("server") if isinstance(metadata, Mapping) else None
    if server:
        return str(server)
    name = str(getattr(tool, "name", "") or "")
    return name.split("_", 1)[0] if "_" in name else name


def catalog_of(
    tools: Iterable[Any], group_of: GroupOf
) -> tuple[list[dict[str, Any]], dict[str, list[Any]]]:
    """Group tools into a catalog the squire can read, in a stable order."""
    groups: dict[str, list[Any]] = {}
    for tool in tools:
        groups.setdefault(group_of(tool), []).append(tool)
    catalog: list[dict[str, Any]] = []
    for name in sorted(groups):
        members = groups[name]
        names = ", ".join(sorted(str(getattr(t, "name", "")) for t in members)[:NAMES_IN_ABOUT])
        first = str(getattr(members[0], "description", "") or "")
        catalog.append(
            {
                "name": name,
                "about": truncate(f"{len(members)} tools ({names}). {first}", 160),
            }
        )
    return catalog, groups


def last_human_text(messages: Iterable[Any]) -> str:
    """The latest human message as plain text, or an empty string."""
    for message in reversed(list(messages)):
        kind = str(getattr(message, "type", "") or "")
        if kind != "human" and not message.__class__.__name__.endswith("HumanMessage"):
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(block.get("text", "")) for block in content if isinstance(block, Mapping)
            )
        return str(content)
    return ""


def human_texts(messages: Iterable[Any]) -> list[str]:
    """Every human message as plain text, in order."""
    out = []
    for message in messages:
        kind = str(getattr(message, "type", "") or "")
        if kind == "human" or message.__class__.__name__.endswith("HumanMessage"):
            out.append(last_human_text([message]))
    return out


SquireSource = Squire | Callable[[], Squire]


def _sibling(template: Squire) -> Squire:
    """A fresh squire - fresh meter - with the template's whole configuration."""
    return template.fork()


class ToolSelectMiddleware(_base()):  # type: ignore[misc]
    """Narrow `request.tools` to a per-conversation window that only grows.

    Until 2026-09-25 this re-selected on every model call. Within a turn that paid a decision
    per call for an unchanged answer; across turns it rewrote `request.tools` to whatever the
    newest message needed, dropping what the earlier ones had. That is the `churn` pattern
    `benchmarks/cache/` measured at 4.15x the cost of deciding once, shipped in the package's
    own adapter. Now each conversation keeps a `ToolWindow`: opened on its first model call,
    widened (never narrowed) on each new human turn, and asked nothing on calls in between.

    A widening still rewrites the `tools` array here, because LangChain passes a list and not
    the platform's `tool_addition` channel, so each one costs a cache rebuild; there are at
    most as many as there are groups, and there were one per turn before. With `grow=False`
    the window never widens after it opens, which keeps the prefix byte-identical for the
    whole conversation at the price of the misses the report counts.

    **Conversations are only told apart by `key_of(request)`.** Pass it - the LangGraph
    `thread_id` on a multi-tenant server - to get the window above. Without it, or when it
    returns `None` or an empty string for a request, nothing is kept between requests: each
    model call opens a fresh window on its last human message, with the earlier ones as
    clues. That default is safe and costs a decision per model call, plus whatever churn the
    reselection causes. Changed 2026-09-25: the old fallback key (first human message plus
    catalog) was shared by every conversation that opened with the same words ("hi"), so one
    user's widened window reached another user. A `key_of` that returns the same key for two
    users merges their windows in the same way; keying by anything the user controls is
    that bug again.

    **Each conversation has its own squire, and so its own budget.** Given a `Squire`, the
    middleware uses it as a template: every conversation (every request, without `key_of`)
    gets a fresh `Squire` with the same decider, thresholds, journal, brief and profile, and a
    meter of its own. Until 2026-09-25 one squire, one meter, served every conversation in the
    process, so a conversation that exhausted it made every later one fall open to the full
    catalog. The template itself is never charged: read decisions and cost from the journal.
    Pass a zero-argument callable instead to build each conversation's squire yourself; it
    is called once per conversation.

    Human-message text is treated as the user's and is not scanned. An application that puts
    documents or emails inside a human message, or a sub-agent whose "human" message is
    written by a parent model, should pass that text through `ToolWindow.observe(...,
    trust="tool")` itself.
    """

    MAX_CONVERSATIONS = 256

    def __init__(
        self,
        squire: SquireSource,
        *,
        always: Iterable[str] = (),
        group_of: GroupOf = default_group_of,
        clues_of: Callable[[Any], str] | None = None,
        grow: bool = True,
        key_of: Callable[[Any], str | None] | None = None,
    ) -> None:
        if _base() is not object:
            super().__init__()
        if isinstance(squire, Squire):
            self._new_squire: Callable[[], Squire] = lambda: _sibling(squire)
        elif callable(squire):
            self._new_squire = squire
        else:  # a squire-like object that is neither: shared, as before (one meter)
            self._new_squire = lambda: squire  # type: ignore[return-value]
        self._always = frozenset(always)
        self._group_of = group_of
        self._clues_of = clues_of
        self._grow = grow
        self._key_of = key_of
        self._windows: dict[tuple[str, tuple[str, ...]], tuple[ToolWindow, tuple[str, ...]]] = {}

    async def _open(
        self, request: Any, catalog: list[dict[str, Any]], humans: list[str]
    ) -> ToolWindow:
        window = ToolWindow(
            self._new_squire(), catalog, always=self._always, wait_on_deferred=False
        )
        clues = self._clues_of(request) if self._clues_of else ""
        if len(humans) > 1:  # opened mid-conversation: keep the earlier turns as clues
            clues = " | ".join([*humans[:-1], clues] if clues else humans[:-1])
        await window.open(humans[-1], clues=clues)
        return window

    async def _window_for(
        self, request: Any, catalog: list[dict[str, Any]], humans: list[str]
    ) -> ToolWindow:
        given = self._key_of(request) if self._key_of else None
        if not given:  # no conversation identity: nothing kept, nothing shared
            return await self._open(request, catalog, humans)
        key = (str(given), tuple(g["name"] for g in catalog))
        held = self._windows.get(key)
        if held is None:
            window = await self._open(request, catalog, humans)
            self._remember(key, window, tuple(humans))
            return window
        window, seen = held
        new = [h for h in humans if h not in seen]
        if self._grow:
            for text in new:
                await window.observe(text, trust="user")
        self._remember(key, window, (*seen, *new))
        return window

    def _remember(
        self, key: tuple[str, tuple[str, ...]], window: ToolWindow, seen: tuple[str, ...]
    ) -> None:
        rest = {k: v for k, v in self._windows.items() if k != key}
        if len(rest) >= self.MAX_CONVERSATIONS:
            rest = dict(list(rest.items())[1:])  # oldest out
        self._windows = {**rest, key: (window, seen)}

    async def narrow(self, request: Any) -> Any:
        """The request with fewer tools, or the same request when nothing should change."""
        try:
            tools = list(getattr(request, "tools", None) or [])
            if not tools or any(not getattr(t, "name", None) for t in tools):
                return request
            catalog, groups = catalog_of(tools, self._group_of)
            if len(catalog) < 2:
                return request
            humans = [h for h in human_texts(getattr(request, "messages", None) or []) if h.strip()]
            if not humans:
                return request
            window = await self._window_for(request, catalog, humans)
            if len(window.window) >= len(catalog):
                return request
            # By identity: tool objects (pydantic models, dataclasses) need not be hashable.
            keep = {id(t) for name in window.window for t in groups.get(name, ())}
            override = getattr(request, "override", None)
            if override is None:
                return request
            return override(tools=[t for t in tools if id(t) in keep])
        except Exception:  # never break the model call
            return request

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        return await handler(await self.narrow(request))

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        """Sync path: narrows only when no event loop is running; otherwise passes through."""
        try:
            narrowed = asyncio.run(self.narrow(request))
        except RuntimeError:  # a loop is already running: the async path is the one in use
            narrowed = request
        return handler(narrowed)


__all__ = [
    "ToolSelectMiddleware",
    "catalog_of",
    "default_group_of",
    "human_texts",
    "last_human_text",
]
