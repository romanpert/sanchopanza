"""The six arms: what each keeps of a history's tool results, as one action per call id.

Free arms (code only):

- `keep_all`: nothing is pruned. The recall ceiling and the zero of the freed fraction.
- `last_3`: the API's context editing, `clear_tool_uses_20250919`, at its default `keep` of 3
  tool uses: every result but the three most recent is replaced by a placeholder. Nothing is
  archived.
- `mask_10`: observation masking with M = 10 as defined by Lindenbauer et al., "The
  Complexity Trap: Simple Observation Masking Is as Efficient as LLM Summarization for Agent
  Context Management" (arXiv:2508.21433): the observations of the last M turns stay, older
  ones become a placeholder, the actions (tool calls) and reasoning stay. A turn here is one
  assistant message that made tool calls (Claude Code runs parallel calls in one turn).
- `rules`: `sanchopanza.context.rules.triage_rules` alone, through `compact.plan(arm="rules")`;
  what the rules cannot decide is kept. Stubs are archived.

Decider arms (through a `Squire`):

- `fastjev`: the fast-jev-compaction replica, `compact.plan(arm="fastjev")`, its own cut 0.5.
- `sanchopanza`: rules, then the in-context decision (`Squire.prune_context`). It is planned
  once with `context_keep = 0.0`, which keeps every call that reached the final round, so the
  final cut can be applied offline at any value: the tournament's calls do not depend on the
  final cut, only its last comparison does. `at_cut` rebuilds the arm at a given cut.

Experimental, outside the registered six (`EXPERIMENTAL_ARMS`, only when named with `--arms`):

- `tournament`: no rules; every old result outside the structural invariants in one
  tournament of the `context` question (`compact.plan(arm="tournament")`). Planned with
  `context_keep = 0.0` like `sanchopanza`, so `at_cut` rebuilds it at any cut. Its question
  measured at AUC 0.57-0.61 on this dataset (docs/results/2026-09-28-context/): a negative
  prior, here so the lead can pre-register it as an amendment and measure it.

Every action is one of `keep`, `stub` (archived when the arm archives), `truncate` (the
fastjev note), `drop` (fastjev: call and result gone).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sanchopanza import Squire, Thresholds
from sanchopanza.context.transcript import Call
from sanchopanza.contract import Answer, Decision, Question, State, Truth

FREE_ARMS = ("keep_all", "last_3", "mask_10", "rules")
DECIDER_ARMS = ("fastjev", "sanchopanza")
ARMS = FREE_ARMS + DECIDER_ARMS
EXPERIMENTAL_ARMS = ("tournament",)
KNOWN_ARMS = ARMS + EXPERIMENTAL_ARMS
CUT_ARMS = frozenset({"sanchopanza", "tournament"})  # planned at cut 0, cut applied offline
ARCHIVING = frozenset({"rules", "sanchopanza", "tournament"})
API_KEEP = 3
MASK_TURNS = 10


@dataclass(frozen=True)
class ArmResult:
    arm: str
    actions: Mapping[str, str]
    # sanchopanza only: id -> (reached the final round and was asked, probability or None)
    asked: Mapping[str, tuple[bool, float | None]] | None = None
    decisions: int = 0
    failed: int = 0


def keep_all(calls: Sequence[Call]) -> dict[str, str]:
    return {c.id: "keep" for c in calls}


def last_n(calls: Sequence[Call], keep: int = API_KEEP) -> dict[str, str]:
    order = sorted(range(len(calls)), key=lambda i: (calls[i].result_msg, i))
    kept = {calls[i].id for i in order[-keep:]} if keep else set()
    return {c.id: "keep" if c.id in kept else "stub" for c in calls}


def mask(messages: Sequence[Mapping[str, Any]], calls: Sequence[Call], turns: int = MASK_TURNS):
    acting = [
        i
        for i, m in enumerate(messages)
        if m.get("role") == "assistant"
        and any(b.get("type") == "tool_use" for b in m.get("content", []))
    ]
    recent = set(acting[-turns:]) if turns else set()
    return {c.id: "keep" if c.use_msg in recent else "stub" for c in calls}


class CountingDecider:
    """Wraps any decider and counts what a run must not lose silently.

    `calls`: decisions asked; `errors`: calls that raised (the squire turns them into a
    default, so without this count a failed call looks like an answered "keep"); `empty`:
    calls that returned no answer at all; `loops`: distinct event loops the calls ran in. More
    than one loop is how the ReplayFirst loss happened (an `asyncio.Lock` or an HTTP client
    bound to the first `asyncio.run`, every call of the second one failing and being retried
    into a default): a run whose count is above one is incomplete, whatever it printed.
    """

    accepts_attachments = False

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "counted")
        self.calls = self.errors = self.empty = 0
        self._loops: list[Any] = []  # the loop objects: an id() can be reused once one closes
        self.first_error = ""

    @property
    def loops(self) -> int:
        return len(self._loops)

    @property
    def complete(self) -> bool:
        return self.errors == 0 and self.empty == 0 and self.loops <= 1

    def report(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "errors": self.errors,
            "empty": self.empty,
            "event_loops": self.loops,
            "complete": self.complete,
            "first_error": self.first_error[:200],
        }

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        import asyncio

        loop = asyncio.get_running_loop()
        if not any(seen is loop for seen in self._loops):
            self._loops.append(loop)
        self.calls += 1
        try:
            decision = await self._inner.decide(point, state, questions)
        except Exception as error:
            self.errors += 1
            self.first_error = self.first_error or f"{error.__class__.__name__}: {error}"
            raise
        if not decision.answers:
            self.empty += 1
        return decision


class FakeDecider:
    """Scripted, free and deterministic: each Truth gets p from a hash of (point, state, id).

    It exercises the decider arms end to end (states built, tournament run, plan applied)
    without a network call. Its answers mean nothing; numbers from it are plumbing checks.
    """

    name = "fake"
    accepts_attachments = False

    def __init__(self, script: Mapping[str, float] | None = None) -> None:
        self._script = dict(script or {})

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        seed = hashlib.sha256(f"{point}:{state!r}".encode()).hexdigest()
        answers = {}
        for qid, q in questions.items():
            if not isinstance(q, Truth):
                continue
            p = self._script.get(qid)
            if p is None:
                p = int(hashlib.sha256(f"{seed}:{qid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            answers[qid] = Answer(kind="truth", truth=p, confidence=abs(2 * p - 1))
        return Decision(point=point, answers=answers, provider=self.name, model="fake")


def squire_for(decider: Any, *, max_usd: float, max_decisions: int = 100_000) -> Squire:
    """One squire for a whole run, so its meter is the run's hard ceiling."""
    from sanchopanza.redact import redact_secrets

    thresholds = Thresholds().with_(context_keep=0.0, max_usd=max_usd, max_decisions=max_decisions)
    return Squire(decider, thresholds=thresholds, redact=redact_secrets)


def _from_plan(arm: str, plan: Any) -> ArmResult:
    actions = {s.id: s.action for s in plan.steps}
    asked = None
    if arm in CUT_ARMS:
        asked = {
            s.id: (s.action == "keep", s.probability)
            for s in plan.steps
            if s.reason in ("needed", "not_needed", "unanswered")
        }
    return ArmResult(arm, actions, asked, plan.decisions, plan.failed)


async def run_arm(
    arm: str,
    messages: Sequence[Mapping[str, Any]],
    calls: Sequence[Call],
    squire: Squire | None = None,
) -> ArmResult:
    if arm == "keep_all":
        return ArmResult(arm, keep_all(calls))
    if arm == "last_3":
        return ArmResult(arm, last_n(calls))
    if arm == "mask_10":
        return ArmResult(arm, mask(messages, calls))
    if arm not in ("rules", *DECIDER_ARMS, *EXPERIMENTAL_ARMS):
        raise ValueError(f"unknown arm {arm!r}; one of {KNOWN_ARMS}")
    if squire is None:
        squire = squire_for(None, max_usd=0.0)
    plan = await squire.prune_context(list(messages), arm=arm)
    return _from_plan(arm, plan)


def at_cut(result: ArmResult, cut: float) -> dict[str, str]:
    """A cut arm (`sanchopanza`, `tournament`) at `cut`: a finalist is kept at p >= cut or
    when unanswered."""
    if result.asked is None:
        return dict(result.actions)
    out = dict(result.actions)
    for cid, (finalist, p) in result.asked.items():
        out[cid] = "keep" if finalist and (p is None or p >= cut) else "stub"
    return out
