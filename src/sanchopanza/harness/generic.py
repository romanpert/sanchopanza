"""The harness-agnostic layer: tool calls in, verdicts out.

A `Guardian` watches three families of tools:

- **delegation** (`Agent`, `Task`, ...): rewrites the requested tier to the one the squire
  chose (model per subtask) and, after the subtask returns, appends a review note.
- **search** (`WebSearch`, ...): denies a repeated query, or points to a cheaper engine.
- **shell** (`Bash`, ...): denies with a reason when the code list or the squire flags it.

Everything else passes untouched. Denying never breaks the agent: it receives the reason
and changes course.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from ..points.routing import TIERS, Tier
from .fetch import fetches_from_network

if TYPE_CHECKING:  # the squire loads asyncio; a hook that decides nothing never needs it
    from ..squire import Squire

Action = Literal["allow", "deny", "rewrite"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any]
    event: str = "PreToolUse"


@dataclass(frozen=True, slots=True)
class Verdict:
    action: Action
    reason: str = ""
    arguments: Mapping[str, Any] | None = None

    @property
    def allowed(self) -> bool:
        return self.action != "deny"


ALLOW = Verdict("allow")


@dataclass(frozen=True, slots=True)
class Note:
    """Something to say after a tool ran. `context` reaches the model, `user` the operator.

    They are separate because a detection control that only speaks to the model is trusting
    the model to act on a warning about text designed to steer it. The operator's copy is
    the part that does not depend on that.
    """

    context: str = ""
    user: str = ""

    def __bool__(self) -> bool:
        return bool(self.context or self.user)


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Names the harness uses. Defaults match Claude Code and the Claude Agent SDK."""

    delegate_tools: frozenset[str] = frozenset({"Agent", "Task"})
    delegate_task_keys: tuple[str, ...] = ("prompt", "description")
    delegate_tier_key: str = "subagent_type"
    # tier -> the subagent/model name the harness understands. Empty: the tier names.
    tiers: Mapping[Tier, str] = field(default_factory=dict)
    review_delegations: bool = True
    search_tools: frozenset[str] = frozenset({"WebSearch"})
    search_query_key: str = "query"
    # **Probe the capability; do not declare it.** This callable decides whether the squire
    # is allowed to route a query away from the model's own search, so it answers "does that
    # alternative exist and work, right now". A constant `True`, or a function that answers a
    # different question (is there quota left, is the feature flag on), sends work into a
    # hole: the routing succeeds, nothing fails, fail-open never fires, and the job comes
    # back empty and cheap. That has happened in production, and the arm that produced
    # nothing was 75 % cheaper. See docs/where-it-pays.md, section 5.
    cheap_search_available: Callable[[], bool] = lambda: False
    cheap_search_hint: str = (
        "Use the cheap search tool for this query; keep the model's search for what it cannot find."
    )
    shell_tools: frozenset[str] = frozenset({"Bash", "bash", "shell", "run_command", "execute"})
    shell_command_key: str = "command"
    guard_environment: Mapping[str, Any] | None = None
    result_limit: int = 4000
    # --- content that arrives from outside, scanned after the fact -----------------------
    # Off by default. It costs one decision per tool result and, unlike every other family
    # here, it cannot change the outcome: by PostToolUse the text is in the transcript and
    # the harness offers no way to replace a tool result. It detects and warns. See
    # `points.injection` for why that is still worth having and why it must not be sold as
    # a barrier.
    scan_content: bool = False
    # --- the agent's own "done", checked before it may stop ------------------------------
    # Off by default. On 655 AgentDojo trajectories the agent's word was right 52 % of the
    # time and the completion question 94 % (docs/results/2026-09-25-completion/). `done_cut`
    # is derived there to a 90 % precision target for a block: a false block costs a turn.
    check_done: bool = False
    done_cut: float = 0.5
    content_tools: frozenset[str] = frozenset({"WebFetch", "WebSearch"})
    # With `scan_content` on, the output of a shell command that fetches from the network
    # (`curl`, `wget`, `Invoke-WebRequest`, ... see `fetch.fetches_from_network`) is scanned
    # even when no shell tool is named in `content_tools`: an agent refused by WebFetch
    # reaches for `curl`. Other shell output is scanned only if the shell tool is named.
    scan_shell_fetches: bool = True
    # The purpose the content is judged against. A constant is fine; a callable returning
    # the live task is better, because the question asks what the text tries to change.
    content_purpose: Callable[[], str] = lambda: "the task this agent was given"
    # No longer cuts what is scanned (see `_scan`); kept so existing configs still load.
    content_limit: int = 4000

    def after_tools(self) -> frozenset[str]:
        """The tools a PostToolUse hook has to see. Which of their calls to scan is decided
        per call (`scans_after`): a matcher cannot tell `curl` from `ls`."""
        tools = self.delegate_tools
        if self.scan_content:
            tools = tools | self.content_tools
            if self.scan_shell_fetches:
                tools = tools | self.shell_tools
        return tools

    def scans_after(self, name: str, arguments: Mapping[str, Any]) -> bool:
        """Whether this tool call's result goes through the content scan (when it is on)."""
        if name in self.content_tools or name in self.delegate_tools:
            return True
        if not (self.scan_shell_fetches and name in self.shell_tools):
            return False
        return fetches_from_network(str(arguments.get(self.shell_command_key) or ""))

    def tier_name(self, tier: Tier) -> str:
        return self.tiers.get(tier, tier)

    def tier_of(self, name: str | None) -> Tier | None:
        if name in TIERS:
            return name  # type: ignore[return-value]
        for tier, mapped in self.tiers.items():
            if mapped == name:
                return tier
        return None


class Guardian:
    def __init__(self, squire: Squire, config: HarnessConfig | None = None) -> None:
        self.squire = squire
        self.config = config or HarnessConfig()

    async def before_tool(self, call: ToolCall) -> Verdict:
        c = self.config
        if call.name in c.delegate_tools:
            return await self._before_delegate(call)
        if call.name in c.search_tools:
            return await self._before_search(call)
        if call.name in c.shell_tools:
            return await self._before_shell(call)
        return ALLOW

    async def after_tool(self, call: ToolCall, response: Any) -> Note | None:
        """What to say once a tool has returned, to the model and to the operator.

        Two things can happen here and they are independent: a delegated subtask gets its
        report reviewed, and content that arrived from outside gets scanned for instructions
        aimed at the model. A tool can be in both families; both notes are then joined.
        """
        c = self.config
        text = text_of(response)
        if not text.strip():
            return None
        parts: list[Note] = []
        if call.name in c.delegate_tools and c.review_delegations:
            task = self._task_text(call.arguments)
            if task.strip():
                outcome = await self.squire.review_report(task, text[: c.result_limit])
                if outcome and outcome.message:
                    parts.append(Note(context=outcome.message))
        if c.scan_content and c.scans_after(call.name, call.arguments):
            parts.append(await self._scan(call, text))
        joined = Note(
            context="\n\n".join(p.context for p in parts if p.context),
            user="\n".join(p.user for p in parts if p.user),
        )
        return joined if (joined.context or joined.user) else None

    async def _scan(self, call: ToolCall, text: str) -> Note:
        c = self.config
        source = _source_of(call) or call.name
        # The whole text: `scan_content` slides its own windows and `max_windows` bounds the
        # cost. Cut here first, a payload after character 4,000 was never read by either
        # layer and the journal still said the scan was complete (review of 2026-09-25).
        flag = await self.squire.scan_content(purpose=c.content_purpose(), text=text, source=source)
        # An incomplete scan stays silent here, as an outage does (the journal records
        # `complete`): a note on every page while the provider is down is noise, not news.
        if not flag.flagged:
            return Note()
        return Note(context=flag.note, user=flag.warning)

    # --- families --------------------------------------------------------------------

    async def _before_delegate(self, call: ToolCall) -> Verdict:
        c = self.config
        task = self._task_text(call.arguments)
        if not task.strip():
            return ALLOW
        requested = call.arguments.get(c.delegate_tier_key)
        default = c.tier_of(requested if isinstance(requested, str) else None) or "default"
        result = await self.squire.route_task(task, requested=requested, default=default)
        chosen = c.tier_name(result.tier)
        if chosen == requested or (requested is None and result.tier == default):
            return ALLOW
        return Verdict(
            "rewrite", result.reason, {**dict(call.arguments), c.delegate_tier_key: chosen}
        )

    async def _before_search(self, call: ToolCall) -> Verdict:
        c = self.config
        query = str(call.arguments.get(c.search_query_key) or "")
        if not query.strip():
            return ALLOW
        route = await self.squire.route_search(query, cheap_available=c.cheap_search_available())
        if route.route == "cut":
            return Verdict(
                "deny",
                "This query repeats one already made in this job. Do not rephrase it: use the "
                "results you have or change the angle.",
            )
        if route.route == "cheap":
            return Verdict("deny", f"{c.cheap_search_hint} (category '{route.category}').")
        return ALLOW

    async def _before_shell(self, call: ToolCall) -> Verdict:
        c = self.config
        command = str(call.arguments.get(c.shell_command_key) or "")
        if not command.strip():
            return ALLOW
        result = await self.squire.guard_command(command, environment=c.guard_environment)
        if not result.denied:
            return ALLOW
        return Verdict(
            "deny",
            f"Command denied ({result.reason}). This job does not delete outside its output, "
            "does not send files or secrets to the network, does not change permissions and "
            "does not execute downloaded content. Achieve the same with the job's own tools.",
        )

    def _task_text(self, arguments: Mapping[str, Any]) -> str:
        for key in self.config.delegate_task_keys:
            value = arguments.get(key)
            if value:
                return str(value)
        return ""


def _source_of(call: ToolCall) -> str:
    """A short name for where content came from: a URL, a path, a query."""
    for key in ("url", "file_path", "path", "query", "command", "prompt", "description"):
        value = call.arguments.get(key)
        if value:
            return str(value)[:200]
    return ""


def text_of(response: Any) -> str:
    """The text of a tool result, whatever shape it arrives in."""
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        # Claude Code's built-in tools: Read nests the file, WebFetch and WebSearch return
        # `result` / `results`. Read as empty, the content scan never ran on them.
        file = response.get("file")
        if isinstance(file, Mapping) and isinstance(file.get("content"), str):
            return file["content"]
        if isinstance(response.get("result"), str):
            return response["result"]
        # Claude Code's Bash: {"stdout", "stderr", "interrupted", "isImage", ...}. Read as
        # empty until 2026-09-28, so naming `Bash` as a content tool scanned nothing.
        streams = [response.get(k) for k in ("stdout", "stderr")]
        if any(isinstance(v, str) for v in streams):
            return "\n".join(v for v in streams if isinstance(v, str) and v)
        if isinstance(response.get("output"), str):
            return response["output"]
        results = response.get("results")
        if isinstance(results, list) and results:
            return "\n".join(
                part if isinstance(part, str) else json.dumps(part, ensure_ascii=False)
                for part in results
            )
        content = response.get("content")
        if isinstance(content, list):
            return "\n".join(
                str(part.get("text", "")) for part in content if isinstance(part, Mapping)
            )
        return str(content or response.get("text") or "")
    if isinstance(response, list):
        return "\n".join(text_of(part) for part in response)
    return str(response)
