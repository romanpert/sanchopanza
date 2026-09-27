"""A `ToolWindow` rendered into the Anthropic Messages API, without breaking the prompt cache.

    from sanchopanza.harness.messages_api import WindowedTools

    wt = WindowedTools(window, tools_by_group, model="claude-opus-5")
    tools = wt.tools()                         # send this, unchanged, on every request
    messages += wt.opening()                   # after the first user message
    ...
    change = await window.observe(result_text, trust="tool")
    messages += wt.after(change)               # a system message on Opus 5; nothing on Sonnet 5

Every shape here was checked with `messages.count_tokens` on 2026-09-25 (free), and the
probe is `benchmarks/agentdojo/window_data.py --probe`:

- **All catalog tools are declared with `defer_loading: true`, always.** They cost ~9 tokens
  each until surfaced, and `tools` stays byte-identical for the whole session - so the cache
  prefix does not depend on what this session selected, and two sessions with the same
  catalog share it.
- **Models that accept `tool_addition`** (Claude Opus 5, Opus 4.8, Fable 5 and 5.1, behind
  `mid-conversation-tool-changes-2026-07-01`) get a `system` message with one `tool_addition`
  per tool. Opus 5 is measured end to end; Opus 4.8 and Fable 5 and 5.1 only have the shape
  accepted by `count_tokens` (2026-09-27, `docs/results/2026-09-25-window/probe-models.json`).
  Mythos is left out: this key gets a 404, so nothing about it was probed. Proactive: the
  application decides, no round trip.
- **The others** (Claude Sonnet 5, Haiku 4.5: 400 on `tool_addition`) get a `load_tools` tool,
  the only non-deferred one. When the model calls it, the result is a `tool_result` holding
  only `tool_reference` blocks, which the API expands on any tool-search model. The window
  answers the call, so this is a tool search backed by a calibrated per-group judgment
  instead of BM25 - and its `need` argument is written by a model that may have read an
  injection, so it is only a clue to the selection question on the USER's purpose, and it
  is refused outright after a blocked tool result (`ToolWindow.request`).
- **On models without `tool_addition`, open with `wait_on_deferred=False`.** A widening
  there reaches the model only if it calls `load_tools`, and measured end to end it rarely
  does: the harness's "tools are now available" note was followed by a load in 2 of 16-18
  tasks. So a request that defers its instructions should get the whole catalog up front,
  as a one-shot selection would, instead of a window that waits for a read it cannot act on.
  `ToolWindow(..., wait_on_deferred=accepts_tool_addition(model))`.
- **Do not make the harness call `load_tools` for the model.** The API accepts a
  harness-written load answered with references, but after the model has read untrusted
  text Sonnet 5 takes the payment tools that then appear as the text escalating itself and
  refuses: 0 of 16 against 5 of 8 with everything loaded, and 1 of 8 with the load moved
  before the read (`docs/results/2026-09-25-push/`). On Opus 5 a `tool_addition` after the
  read held, 7 of 8 against 8 of 8.
- **Nothing is ever removed.** `tool_removal` reclaims no tokens (+26 measured); it would only
  spend them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ..window import Change, ToolWindow

TOOL_CHANGES_BETA = "mid-conversation-tool-changes-2026-07-01"
ADDITION_MODELS = frozenset(
    {
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-fable-5",
        "claude-fable-5-1",
    }
)
LOAD_TOOL = "load_tools"
LOAD_TOOL_DEFINITION: dict[str, Any] = {
    "name": LOAD_TOOL,
    "description": (
        "Load more tools. Only a few tools are loaded at the start; if you need a capability "
        "you do not have (another application, a kind of record, an action), call this with "
        "a short description of what you need to do next, and the matching tools become "
        "available in your next turn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "need": {"type": "string", "description": "What you need to do next, in one line."}
        },
        "required": ["need"],
    },
}


def accepts_tool_addition(model: str) -> bool:
    """True for models that take `tool_addition` in a mid-conversation system message.

    Exact ids only. A prefix match said yes to `claude-opus-5-5`, which nobody probed; a
    model that rejects the block answers every request with a 400.
    """
    return model in ADDITION_MODELS


class WindowedTools:
    """Renders one session's window. Holds no state of its own beyond what was surfaced."""

    def __init__(
        self,
        window: ToolWindow,
        tools_by_group: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        model: str,
    ) -> None:
        if not window.purpose:
            # Built before `open`, the frozen initial window is empty and on models without
            # `tool_addition` nothing is ever loaded - silently.
            raise ValueError("open the ToolWindow before building WindowedTools on it")
        self._window = window
        # A tool listed under two groups is declared once (the API rejects duplicate names),
        # under the first group that lists it.
        seen: set[str] = set()
        by_group: dict[str, list[dict[str, Any]]] = {}
        for g, ts in tools_by_group.items():
            by_group[g] = [dict(t) for t in ts if t.get("name") not in seen]
            seen.update(str(t.get("name")) for t in ts)
        self._by_group = by_group
        self._additions = accepts_tool_addition(model)
        # Frozen at construction, after `window.open`: on models without `tool_addition` the
        # opened groups are the non-deferred part of `tools`, which may never change again.
        self._initial = tuple(window.window)
        self._surfaced: tuple[str, ...] = () if self._additions else self._initial

    @property
    def uses_tool_addition(self) -> bool:
        return self._additions

    def betas(self) -> list[str]:
        return [TOOL_CHANGES_BETA] if self._additions else []

    def tools(self) -> list[dict[str, Any]]:
        """The `tools` array for every request of the session. Never changes.

        The loader is always the first entry and never deferred: the API rejects a request in
        which every tool is deferred (checked on Opus 5, even with a `tool_addition` in the
        same request), and it is the discovery fallback on every model. On models with
        `tool_addition` every catalog tool is deferred and `opening()` surfaces the window;
        on the others the opened groups are sent loaded, frozen from the first request.
        """
        loaded = set() if self._additions else set(self._initial)
        out: list[dict[str, Any]] = [LOAD_TOOL_DEFINITION]
        for group, tools in self._by_group.items():
            for t in tools:
                if t.get("name") == LOAD_TOOL:
                    continue
                out.append(dict(t) if group in loaded else {**t, "defer_loading": True})
        return out

    def _names(self, groups: Iterable[str]) -> list[str]:
        return [str(t["name"]) for g in groups for t in self._by_group.get(g, ())]

    def _surface(self, groups: Iterable[str]) -> list[str]:
        new = [g for g in groups if g not in self._surfaced]
        self._surfaced = (*self._surfaced, *new)
        return self._names(new)

    def opening(self) -> list[dict[str, Any]]:
        """Messages that surface the opened window. Send after the first user message."""
        return self._additions_message(self._surface(self._window.window))

    def after(self, change: Change) -> list[dict[str, Any]]:
        """Messages that surface what an event added. Empty when nothing was added, and
        always empty on models without `tool_addition`: there the model asks via
        `load_tools`, and the additions wait until it does."""
        if not self._additions or not change.added:
            return []
        return self._additions_message(self._surface(change.added))

    def _additions_message(self, names: list[str]) -> list[dict[str, Any]]:
        if not self._additions or not names:
            return []
        return [
            {
                "role": "system",
                "content": [
                    {"type": "tool_addition", "tool": {"type": "tool_reference", "name": n}}
                    for n in names
                ],
            }
        ]

    async def load(self, tool_use_id: str, need: str) -> dict[str, Any]:
        """Answer a `load_tools` call: a `tool_result` holding only `tool_reference` blocks.

        What the window opened but could not send (the proactive additions of a model
        without `tool_addition`) goes first, then whatever `ToolWindow.request` grants: the
        selection question on the user's purpose, `need` only a clue, refused while a blocked
        tool result taints the window. There is no "best group anyway" fallback: an earlier
        version had one, and four vague loads opened the whole catalog.

        The API rejects a result that mixes text with references, so a load with nothing to
        give is an empty-string result, not an explanation.
        """
        await self._window.request(need)
        if self._window.tainted or self._window.scanning:
            # Groups the window took in before the taint wait for the next user turn: handing
            # payment tools over right after untrusted text is what the push probe measured
            # as harmful, and what the docstring above promised not to do.
            return {"type": "tool_result", "tool_use_id": tool_use_id, "content": ""}
        pending = [g for g in self._window.window if g not in self._surfaced]
        names = self._surface(pending)
        content: Any = [{"type": "tool_reference", "tool_name": n} for n in names] or ""
        return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}


__all__ = [
    "ADDITION_MODELS",
    "LOAD_TOOL",
    "LOAD_TOOL_DEFINITION",
    "TOOL_CHANGES_BETA",
    "WindowedTools",
    "accepts_tool_addition",
]
