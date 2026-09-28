"""Compaction by pruning: keep every message, take out the tool results nothing needs.

    plan = await compact.plan(squire, messages)            # decide, write nothing
    pruned = compact.apply(messages, plan, archive_dir)    # the new message list
    summary = compact.report(messages, pruned, plan)       # what it freed, and why

Three arms, so they can be measured against each other on the same transcripts:

- `rules`: `rules.triage_rules` alone. Free and reproducible; what it cannot decide is kept.
- `sanchopanza`: the rules first, then one in-context decision over the calls they left
  (`points.context.prune_questions`, a tournament past `CALL_MAX`). A result below
  `Thresholds.context_keep` is stubbed; an unanswered one is kept.
- `fastjev`: the fast-jev-compaction replica (`points.context.fastjev_*`), no rules, its own
  truncate-or-drop table. For comparison.
- `mask`: observation masking, free: every tool result outside the last `mask_turns` acting
  turns is stubbed, everything archived. What the autopilot uses at compaction. Measured on
  40 public trajectories (docs/results/2026-09-28-context/): no question about future need
  separated needed from unneeded results (AUC 0.56-0.61), so no decider is asked here; what
  masking takes out goes to the archive, where recall (`harness.memory_gate`) finds it again.
- `tournament`: EXPERIMENTAL, negative prior. No rules: every old result in one tournament of
  the `context` question. That question measured at AUC 0.57-0.61 and a first round at 0.25
  that wipes almost everything; this arm exists to be measured, not to be used.

Structural invariants every arm keeps: the first message, the last `keep_recent` messages,
results already stubbed, and results shorter than a stub would be.

A stubbed result is not deleted. Its full text is written to the archive first, and the stub
names the file, so the model can `Read` it back verbatim: a re-run is not the same thing when
the file changed or the page moved. `apply` never separates a tool_use from its tool_result,
since a request carrying one without the other is refused by the API; the `fastjev` arm's
"drop" removes both together, as the original does.
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..points import context as questions
from ..points import hierarchy
from . import archive as archive_mod
from . import rules as rules_mod
from .transcript import Call, Message, blocks_of, calls, chars, task_of, text_of

if TYPE_CHECKING:
    from ..squire import Squire

Arm = Literal["sanchopanza", "fastjev", "rules", "mask", "tournament"]
StepAction = Literal["keep", "stub", "truncate", "drop"]
ARMS: tuple[str, ...] = ("sanchopanza", "fastjev", "rules", "mask", "tournament")
MASK_TURNS = 10  # arXiv:2508.21433's M

STUB = (
    "[sanchopanza pruned this {tool} result: {n} chars. Full text saved at {path}; "
    "Read it if you need it.]"
)


@dataclass(frozen=True, slots=True)
class Step:
    """What happens to one call's result, and why. `probability` is the decider's, if asked."""

    id: str
    tool: str
    action: StepAction
    reason: str
    chars: int
    probability: float | None = None
    call_probability: float | None = None  # the fastjev arm's second question


@dataclass(frozen=True, slots=True)
class Plan:
    arm: str
    steps: tuple[Step, ...]
    decisions: int = 0
    failed: int = 0
    errors: tuple[str, ...] = ()

    def by_id(self) -> dict[str, Step]:
        return {step.id: step for step in self.steps}

    @property
    def freed(self) -> int:
        """Result characters taken out (stubbed, truncated or dropped), before stub text."""
        return sum(s.chars for s in self.steps if s.action != "keep")


@dataclass(frozen=True, slots=True)
class _Asked:
    probabilities: Mapping[str, tuple[bool, float | None]]
    decisions: int
    failed: int
    errors: tuple[str, ...]


def _ruled(call: Call, verdict: rules_mod.Verdict, fallback: str) -> Step:
    action: StepAction = "stub" if verdict.action == "stub" else "keep"
    reason = fallback if verdict.action == "ask" else verdict.reason
    return Step(call.id, call.tool, action, reason, call.chars)


async def _ask_ours(
    squire: Squire,
    messages: Sequence[Message],
    found: Sequence[Call],
    ask: Sequence[str],
    hidden: Mapping[str, str],
) -> _Asked:
    task = task_of(messages)
    log: list[Any] = []

    async def judge(ids: Sequence[int]) -> list[float | None]:
        state, qs = questions.prune_questions(
            task, messages, found, candidates=[ask[i] for i in ids], hidden=hidden
        )
        decision = await squire.decide("context", state, qs)
        squire.record(decision, candidates=len(ids))
        log.append(decision)
        return [decision.answer(questions.call_id(k)).truth for k in range(len(ids))]

    result = await hierarchy.tournament(
        len(ask),
        judge,
        size=questions.CALL_MAX,
        first_cut=questions.FIRST_ROUND_CUT,
        final_cut=squire.thresholds.context_keep,
    )
    probabilities = {ask[i]: (v.keep, v.last) for i, v in enumerate(result.pages)}
    errors = tuple(str(d.error) for d in log if d.failed)
    return _Asked(probabilities, len(log), len(errors), errors)


async def _plan_ours(
    squire: Squire,
    messages: Sequence[Message],
    found: Sequence[Call],
    *,
    keep_recent: int,
    small: int,
    arm: str,
) -> Plan:
    verdicts = rules_mod.triage_rules(messages, found, keep_recent=keep_recent, small=small)
    if arm == "rules":
        steps = tuple(_ruled(c, verdicts[c.id], "rules_only") for c in found)
        return Plan(arm, steps)
    ask = [c.id for c in found if verdicts[c.id].action == "ask"]
    hidden = {c.id: verdicts[c.id].reason for c in found if verdicts[c.id].action == "stub"}
    asked = await _ask_ours(squire, messages, found, ask, hidden) if ask else _Asked({}, 0, 0, ())
    steps = []
    for call in found:
        if call.id not in asked.probabilities:
            steps.append(_ruled(call, verdicts[call.id], "undecided"))
            continue
        keep, p = asked.probabilities[call.id]
        action: StepAction = "keep" if keep else "stub"
        reason = "unanswered" if p is None else ("needed" if keep else "not_needed")
        steps.append(Step(call.id, call.tool, action, reason, call.chars, probability=p))
    return Plan(arm, tuple(steps), asked.decisions, asked.failed, asked.errors)


async def _plan_fastjev(squire: Squire, messages: Sequence[Message], found: Sequence[Call]) -> Plan:
    total = len(messages)
    candidates = [i for i, c in enumerate(found) if not questions.fastjev_pinned(c, total)]
    batches = [
        candidates[i : i + questions.CALL_MAX]
        for i in range(0, len(candidates), questions.CALL_MAX)
    ]

    async def one(batch: list[int]) -> Any:
        state, qs = questions.fastjev_questions(messages, found, batch)
        decision = await squire.decide("context_fastjev", state, qs)
        squire.record(decision, candidates=len(batch))
        return decision

    decisions = await asyncio.gather(*(one(b) for b in batches))
    by_index = {i: d for batch, d in zip(batches, decisions, strict=True) for i in batch}
    steps = []
    for index, call in enumerate(found):
        if index not in by_index:
            steps.append(Step(call.id, call.tool, "keep", "pinned", call.chars))
            continue
        v = questions.fastjev_decide(by_index[index], index)
        steps.append(
            Step(call.id, call.tool, v.action, v.reason, call.chars, v.keep_result, v.keep_call)
        )
    errors = tuple(str(d.error) for d in decisions if d.failed)
    return Plan("fastjev", tuple(steps), len(decisions), len(errors), errors)


def _structural(call: Call, total: int, keep_recent: int) -> str | None:
    """Why a call is never touched, whatever the arm decides, or None."""
    if call.use_msg == 0 or call.result_msg == 0:
        return "first_message"
    if call.use_msg >= total - keep_recent or call.result_msg >= total - keep_recent:
        return "recent"
    if call.result.startswith(rules_mod.STUB_PREFIX):
        return "already_pruned"
    if call.chars <= len(STUB) + 80:
        return "small"  # a stub would free nothing
    return None


def acting_turns(messages: Sequence[Message]) -> list[int]:
    """Indexes of assistant messages that made at least one tool call."""
    return [
        i
        for i, m in enumerate(messages)
        if m.get("role") == "assistant"
        and any(isinstance(b, Mapping) and b.get("type") == "tool_use" for b in blocks_of(m))
    ]


def _plan_mask(
    messages: Sequence[Message], found: Sequence[Call], *, keep_recent: int, turns: int
) -> Plan:
    recent = set(acting_turns(messages)[-turns:]) if turns > 0 else set()
    steps = []
    for call in found:
        pinned = _structural(call, len(messages), keep_recent)
        if pinned is not None:
            steps.append(Step(call.id, call.tool, "keep", pinned, call.chars))
        elif call.use_msg in recent:
            steps.append(Step(call.id, call.tool, "keep", "recent_turn", call.chars))
        else:
            steps.append(Step(call.id, call.tool, "stub", "masked", call.chars))
    return Plan("mask", tuple(steps))


async def _plan_tournament(
    squire: Squire, messages: Sequence[Message], found: Sequence[Call], *, keep_recent: int
) -> Plan:
    pinned = {c.id: _structural(c, len(messages), keep_recent) for c in found}
    ask = [c.id for c in found if pinned[c.id] is None]
    asked = await _ask_ours(squire, messages, found, ask, {}) if ask else _Asked({}, 0, 0, ())
    steps = []
    for call in found:
        if call.id not in asked.probabilities:
            steps.append(
                Step(call.id, call.tool, "keep", pinned[call.id] or "undecided", call.chars)
            )
            continue
        keep, p = asked.probabilities[call.id]
        reason = "unanswered" if p is None else ("needed" if keep else "not_needed")
        action: StepAction = "keep" if keep else "stub"
        steps.append(Step(call.id, call.tool, action, reason, call.chars, probability=p))
    return Plan("tournament", tuple(steps), asked.decisions, asked.failed, asked.errors)


async def plan(
    squire: Squire,
    messages: Sequence[Message],
    *,
    archive: Path | None = None,
    arm: str = "sanchopanza",
    keep_recent: int = 6,
    small: int = 400,
    mask_turns: int = MASK_TURNS,
) -> Plan:
    """Decide what happens to every tool result. Writes nothing.

    `archive` is accepted so both steps can be called with the same arguments; the plan
    itself writes nothing, `apply` does. Never raises on a decider failure: failed decisions
    keep their calls and are counted in `Plan.failed`, with the errors, for the report.
    """
    del archive
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; one of {ARMS}")
    found = calls(messages)
    if arm == "fastjev":
        return await _plan_fastjev(squire, messages, found)
    if arm == "mask":
        return _plan_mask(messages, found, keep_recent=keep_recent, turns=mask_turns)
    if arm == "tournament":
        return await _plan_tournament(squire, messages, found, keep_recent=keep_recent)
    return await _plan_ours(squire, messages, found, keep_recent=keep_recent, small=small, arm=arm)


def safe_name(call_id: str) -> str:
    """A file name from a tool_use id: letters, digits, `_`, `-` and `.` only."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", call_id).strip(".")[:120]
    return cleaned or "call"


def stub_text(tool: str, n: int, path: Path) -> str:
    return STUB.format(tool=tool, n=n, path=path)


def _about(arguments: Mapping[str, Any] | None) -> str:
    """A short title for an archived result: the input field that names what it was."""
    arguments = arguments or {}
    for key in ("file_path", "command", "pattern", "url", "query", "description", "prompt"):
        if arguments.get(key):
            return str(arguments[key])[:160]
    return ""


def _archive(
    archive: Path | None, step: Step, text: str, arguments: Mapping[str, Any] | None = None
) -> Path:
    if archive is None:
        raise ValueError("a stub needs an archive directory: nothing is deleted unsaved")
    meta = {"tool": step.tool, "about": _about(arguments), "id": step.id, "by": "compaction"}
    return archive_mod.write_entry(archive, step.id, text, meta)


def _result_block(
    block: Mapping[str, Any],
    step: Step,
    archive: Path | None,
    arguments: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    text = text_of(block.get("content"))
    if step.action == "stub":
        path = _archive(archive, step, text, arguments)
        return {**block, "content": stub_text(step.tool, len(text), path)}
    if step.action == "truncate":
        return {**block, "content": questions.fastjev_truncated(text, bool(block.get("is_error")))}
    return dict(block)


def _rewrite(
    message: Message,
    steps: Mapping[str, Step],
    archive: Path | None,
    inputs: Mapping[str, Any] | None = None,
) -> Message | None:
    blocks = blocks_of(message)
    out = []
    changed = False
    for block in blocks:
        if not isinstance(block, Mapping):
            out.append(block)
            continue
        kind = block.get("type")
        key = str(block.get("id") if kind == "tool_use" else block.get("tool_use_id"))
        step = steps.get(key) if kind in ("tool_use", "tool_result") else None
        if step is None or step.action == "keep":
            out.append(block)
        elif step.action == "drop":
            changed = True
        elif kind == "tool_result":
            out.append(_result_block(block, step, archive, (inputs or {}).get(key)))
            changed = True
        else:
            out.append(block)
    if not changed:
        return message
    return {**message, "content": out} if out else None


def apply(messages: Sequence[Message], plan: Plan, archive: Path | None) -> list[Message]:
    """The pruned messages: same order, every tool_use still with its tool_result.

    A stub's full text is written to `archive/<tool_use_id>.txt` before the stub replaces
    it; `is_error` and every other key of the block are kept. A message left with no
    content by a `drop` goes. Untouched messages come back as the same objects.
    """
    steps = {s.id: s for s in plan.steps if s.action != "keep"}
    if not steps:
        return list(messages)
    inputs = {c.id: c.input for c in calls(messages) if c.id in steps}
    rewritten = (_rewrite(m, steps, archive, inputs) for m in messages)
    return [m for m in rewritten if m is not None]


def report(before: Sequence[Message], after: Sequence[Message], plan: Plan) -> dict[str, Any]:
    """Counts per action and reason, characters before and after, and the reduction."""
    chars_before, chars_after = chars(before), chars(after)
    reasons = Counter(f"{s.action}:{s.reason}" for s in plan.steps)
    return {
        "arm": plan.arm,
        "calls": len(plan.steps),
        "actions": dict(Counter(s.action for s in plan.steps)),
        "reasons": dict(sorted(reasons.items())),
        "messages_before": len(before),
        "messages_after": len(after),
        "chars_before": chars_before,
        "chars_after": chars_after,
        "reduction": 0.0 if chars_before == 0 else (chars_before - chars_after) / chars_before,
        "decisions": plan.decisions,
        "failed_decisions": plan.failed,
        "errors": list(plan.errors[:3]),
    }
