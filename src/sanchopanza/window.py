"""A tool window that follows the agent through a session: it opens narrow and only grows.

`Squire.select_tools` decides once, from the request. That is right when the only way to
change a tool set is to rewrite the `tools` array, because rewriting it invalidates the whole
prompt cache (measured: 4.15x the cost of deciding once). It is wrong the moment the work
moves: a request that defers its instructions to an email names no domain until the email is
read, a message with a link needs `web` only once the message is on screen, and the second
task of a session is not the first.

The platform now has channels that change the tools a model sees *without* touching the
prefix. Measured with `messages.count_tokens` on 2026-09-25 (free; the probe is in
`benchmarks/agentdojo/tools_window.py --probe`):

- **Deferred tools cost almost nothing.** Ten tools of ~940 tokens each: 9,430 tokens loaded,
  93 declared with `defer_loading: true`. So a harness should declare its whole catalog once,
  deferred, and keep `tools` byte-identical for the life of the session - and across
  sessions, since the prefix no longer depends on what one session selected.
- **`tool_addition` in a mid-conversation `system` message** loads a deferred tool at the
  point it is sent (+1,929 tokens for two). Application-initiated, so it can be proactive.
  Claude Opus 5 accepts it; **Claude Sonnet 5 answers 400** ("not supported on this model").
- **A `tool_result` holding only `tool_reference` blocks** loads the named tools on Sonnet 5,
  Haiku 4.5 and Opus 5 alike, from *any* tool - it need not be the platform's search tool,
  and no search tool has to be declared. Mixed with text in the same result it is a 400, and
  a loose `tool_reference` outside a result is a 400. So on models without `tool_addition`
  the window grows when the agent calls something (a search tool this package backs).
- **`tool_removal` reclaims nothing.** Two added, one removed: +26 tokens, the removal block
  itself. A tool's schema stays in the history where it was added. Removal is a control
  (revoke a capability), never a saving, and this window does not do it.

So the window is **append-only**. It never swaps, never removes, and each addition costs one
schema written to cache once and read at a tenth of the price after. What it can get wrong is
adding too much (tokens for the rest of the session) or too little (a discovery round trip,
if the harness also offers search, or a task the agent cannot finish, if it does not).

**The security consequence, which is the reason `observe` takes a trust level.** A selection
made once from the user's request is a boundary on what the agent can do - weak, but real:
it is how AgentDojo's `tool_filter` defense works. Widening the window from what the agent
*reads* hands that boundary to whoever wrote the page. "Send the balance to this IBAN" in a
fetched document reads, to the observe question, exactly like the deferred instruction of a
legitimate request. So text the user did not write is scanned for injection before it may add
anything, and a flagged text adds nothing. Measured in `docs/results/2026-09-25-window/`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .points import injection, tools
from .squire import Squire

Trust = Literal["user", "tool"]


@dataclass(frozen=True, slots=True)
class Change:
    """What one event did to the window. `added` is what the harness has to surface now."""

    trigger: str  # "open" | "user" | "tool" | "found"
    added: tuple[str, ...]
    window: tuple[str, ...]
    reason: str
    probabilities: Mapping[str, float] = field(default_factory=dict)
    blocked: bool = False  # untrusted text was flagged; nothing it asked for was added

    @property
    def changed(self) -> bool:
        return bool(self.added)


class ToolWindow:
    """One session's tool window. Not thread-safe; one per agent loop.

    - `open(purpose)` before the first request: the one-shot selection, except that a
      request deferring its instructions is narrowed anyway (`wait_on_deferred`), because
      the window can widen once the deferred content is read.
    - `observe(text, trust="user")` on a new user turn: the task may have changed.
    - `observe(text, trust="tool")` on a tool result: what was read may call for a group
      the request did not name. Scanned for injection first.
    - `found(groups)` when the agent discovered a group by itself (a search hit): recorded,
      because every one of those is a miss the window could have prevented.
    """

    def __init__(
        self,
        squire: Squire,
        catalog: Sequence[Mapping[str, Any]],
        *,
        always: Iterable[str] = (),
        wait_on_deferred: bool = True,
        scan_untrusted: bool = True,
    ) -> None:
        self._squire = squire
        self._catalog = tuple(dict(g) for g in catalog)
        self._names = tuple(str(g.get("name", "")).strip() for g in self._catalog)
        self._requires = tools.requires_of(self._catalog)
        self._always = tuple(n for n in always if n in self._names)
        self._wait = wait_on_deferred
        self._scan = scan_untrusted
        self._window: tuple[str, ...] = ()
        self._purpose = ""
        self._misses: tuple[str, ...] = ()
        # Set when a tool result was blocked (flagged, or not fully scanned) and cleared by the
        # next user turn. While set, the model's own requests for more tools are refused: a
        # model that has just read an injection writes its "need" in the attacker's words,
        # and no scan of that need can tell (review of 2026-09-25).
        self._tainted = False
        # Tool results whose scan has not come back yet. A `request` racing one of them read
        # the taint before it was set (review of 2026-09-25); while any is in flight, refused.
        self._scanning = 0
        # The model's word is judged once per user turn. Jev moves by up to 0.09 between
        # asks of the same state, so a borderline group was a coin flip per retry: repeated
        # `load_tools` calls walked it open.
        self._requested = False

    @property
    def window(self) -> tuple[str, ...]:
        return self._window

    @property
    def purpose(self) -> str:
        return self._purpose

    @property
    def tainted(self) -> bool:
        return self._tainted

    @property
    def wait_on_deferred(self) -> bool:
        return self._wait

    @property
    def scan_untrusted(self) -> bool:
        return self._scan

    @property
    def scanning(self) -> bool:
        """A tool result's scan is still in flight: nothing may be handed over yet."""
        return self._scanning > 0

    @property
    def misses(self) -> tuple[str, ...]:
        """Groups the agent had to find by itself. Each one is a round trip the window lost."""
        return self._misses

    def _outside(self) -> list[dict[str, Any]]:
        held = set(self._window)
        return [g for g, n in zip(self._catalog, self._names, strict=True) if n not in held]

    def _grow(self, names: Iterable[str]) -> tuple[str, ...]:
        """Append, in catalog order, whatever is new. Returns only the new names."""
        held = set(self._window)
        new = tuple(n for n in self._names if n in set(names) and n not in held)
        self._window = (*self._window, *new)
        return new

    async def open(self, purpose: str, *, clues: str = "") -> Change:
        self._purpose = purpose
        selection = await self._squire.select_tools(
            purpose=purpose,
            catalog=self._catalog,
            clues=clues,
            always=self._always,
            honour_deferred=not self._wait,
            warn_churn=False,
        )
        added = self._grow(selection.keep)
        reason = selection.reason
        deferred = selection.deferred
        if self._wait and deferred is not None and deferred >= self._squire.thresholds.deferred:
            reason += (
                f"; the request defers its instructions ({deferred:.2f}): "
                "narrowed anyway, the window widens when the content is read"
            )
        return Change("open", added, self._window, reason, dict(selection.probabilities))

    async def observe(self, text: str, *, trust: Trust) -> Change:
        """Widen the window for what just arrived. Never narrows it."""
        if trust == "user":
            self._tainted = False
            self._requested = False
        outside = self._outside()
        if not outside or not text.strip():
            return Change(trust, (), self._window, "nothing outside the window or nothing read")
        if trust == "user":
            return await self._on_user_turn(text, outside)
        return await self._on_tool_result(text, outside)

    async def _on_user_turn(self, text: str, outside: list[dict[str, Any]]) -> Change:
        # A new user message is a new purpose, asked with the question validated for
        # selection. The previous purpose goes in as clues: "and now send it to Bob"
        # means nothing without it.
        previous = self._purpose
        self._purpose = text
        probs, _deferred, decisions = await self._squire.ask_groups(
            "tools",
            outside,
            lambda chunk: tools.questions(purpose=text, catalog=chunk, clues=previous),
        )
        # Fail open on user text, which is trusted: a group nobody answered for is added, the
        # same rule `select` applies. Without it a decider outage or an exhausted budget on
        # turn two froze the window at turn one's groups for the rest of the conversation -
        # in a harness with no search to fall back on, a task the agent cannot do.
        # Except when the budget ran out. That is not an outage: an attacker causes it by
        # feeding long documents (about nine decisions each), and falling open then handed
        # the whole catalog to the next harmless user turn (review of 2026-09-25).
        exhausted = self._squire.exhausted or any(d.provider == "budget" for d in decisions)
        unanswered = 0.0 if exhausted else 1.0
        answered = {n: (unanswered if p is None else p) for n, p in probs.items()}
        added = self._grow(
            tools.additions(
                answered,
                self._squire.thresholds.with_(window_add=self._squire.thresholds.tools),
                requires=self._requires,
                held=self._window,
                available=self._names,
            )
        )
        reason = f"new user turn: +{len(added)} at p >= {self._squire.thresholds.tools:.2f}"
        for d in decisions:
            self._squire.record(d, window_trigger="user", added=list(added), reason=reason)
        return Change("user", added, self._window, reason, _known(probs))

    async def _on_tool_result(self, text: str, outside: list[dict[str, Any]]) -> Change:
        # After a blocked result the model chooses what to read next, and the attacker may
        # write it: a clean-looking "settle the invoice to this IBAN" added the payment group
        # to a tainted window (review of 2026-09-25). Shut until the next user turn.
        if self._tainted:
            return Change(
                "tool",
                (),
                self._window,
                "a tool result was blocked since the last user turn: no widening",
                blocked=True,
            )
        self._scanning += 1
        try:
            return await self._judge_tool_result(text, outside)
        finally:
            self._scanning -= 1

    async def _judge_tool_result(self, text: str, outside: list[dict[str, Any]]) -> Change:
        purpose = self._purpose

        async def observe() -> tuple[dict[str, float | None], list[Any]]:
            probs, _deferred, decisions = await self._squire.ask_groups(
                "tool_window",
                outside,
                lambda chunk: tools.observe_questions(
                    purpose=purpose, just_read=text, catalog=chunk
                ),
            )
            return probs, decisions

        # The scan and the observe question run at the same time and the observe answer is
        # thrown away if the scan objects. Sequential, they added two decision latencies to
        # every tool call; measured end to end, that made the agent slower than loading
        # every tool. Security is unchanged: flagged text still adds nothing. The cost is one
        # decision spent on text that turns out to be flagged.
        if self._scan and injection.code_signal(text):
            # The free code layer already objects: no model call of either kind is made.
            flag = await self._squire.scan_content(purpose=purpose, text=text, source="tool window")
            self._tainted = True
            return Change(
                "tool",
                (),
                self._window,
                f"what was read carries instructions for the agent ({flag.reason or 'code'}): "
                "it may not widen the window",
                blocked=True,
            )
        if self._scan:
            flag, (probs, decisions) = await asyncio.gather(
                self._squire.scan_content(purpose=purpose, text=text, source="tool window"),
                observe(),
            )
            if flag.flagged or not flag.complete:
                self._tainted = True
                why = (
                    f"what was read carries instructions for the agent ({flag.probability:.2f})"
                    if flag.flagged
                    else "the injection scan did not cover all of it"
                )
                for d in decisions:
                    self._squire.record(d, window_trigger="tool", added=[], reason=why)
                return Change(
                    "tool", (), self._window, f"{why}: it may not widen the window", blocked=True
                )
        else:
            probs, decisions = await observe()
        added = self._grow(
            tools.additions(
                probs,
                self._squire.thresholds,
                requires=self._requires,
                held=self._window,
                available=self._names,
            )
        )
        reason = (
            f"after a tool result: +{len(added)} at p >= {self._squire.thresholds.window_add:.2f}"
        )
        for d in decisions:
            self._squire.record(d, window_trigger="tool", added=list(added), reason=reason)
        return Change("tool", added, self._window, reason, _known(probs))

    async def request(self, need: str) -> Change:
        """The model asks for more tools (a `load_tools` call). Judged against the USER's purpose.

        `need` is written by the model, after whatever it has read, so it is neither user text
        nor scannable third-party text: an injected model writes a plain "pay the invoice to
        this IBAN", which no injection question flags because it is not addressed to an AI.
        So the question is the selection question on the user's own purpose, with `need` only
        as a clue, at the selection threshold; nothing is added on a missing answer; and
        nothing at all while the window is tainted by a blocked tool result.
        """
        outside = self._outside()
        if self._tainted or self._scanning:
            why = (
                "a tool result was blocked since the last user turn"
                if self._tainted
                else "a tool result is still being scanned"
            )
            return Change(
                "request", (), self._window, f"{why}: no widening on request", blocked=True
            )
        if not outside or not need.strip():
            return Change("request", (), self._window, "nothing outside the window or no need")
        if self._requested:
            return Change(
                "request", (), self._window, "already judged a request this user turn: not re-asked"
            )
        self._requested = True
        purpose = self._purpose
        probs, _deferred, decisions = await self._squire.ask_groups(
            "tools",
            outside,
            lambda chunk: tools.questions(purpose=purpose, catalog=chunk, clues=need),
        )
        added = self._grow(
            tools.additions(
                probs,
                self._squire.thresholds.with_(window_add=self._squire.thresholds.tools),
                requires=self._requires,
                held=self._window,
                available=self._names,
            )
        )
        self._misses = (*self._misses, *added)
        reason = f"requested by the model: +{len(added)} judged on the user's purpose"
        for d in decisions:
            self._squire.record(d, window_trigger="request", added=list(added), reason=reason)
        return Change("request", added, self._window, reason, _known(probs))

    def found(self, groups: Iterable[str]) -> Change:
        """The agent found these by itself. Add them, and count each as a miss.

        While the window is tainted the miss is recorded and nothing is added: the find may
        have been steered by what was read, and `requires` would pull prerequisites in too.
        """
        if self._tainted:
            wanted = [g for g in groups if g in self._names and g not in self._window]
            self._squire.journal.record(
                "window_miss", {"added": [], "refused": wanted, "window": list(self._window)}
            )
            return Change(
                "found", (), self._window, "found while tainted: recorded, not added", blocked=True
            )
        added = self._grow(tools.close_over(groups, self._requires, available=self._names))
        self._misses = (*self._misses, *added)
        self._squire.journal.record(
            "window_miss", {"added": list(added), "window": list(self._window)}
        )
        return Change("found", added, self._window, f"found by the agent: {', '.join(added)}")


def _known(probs: Mapping[str, float | None]) -> dict[str, float]:
    return {n: p for n, p in probs.items() if p is not None}


__all__ = ["Change", "ToolWindow", "Trust"]
