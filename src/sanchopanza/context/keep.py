"""The guard's cascade as a package: plumbing and a free rule propose, the decider cuts.

Three layers, cheapest first (docs/results/2026-09-29-context-guard/prereg-prompt-recall.md,
amendment 5):

1. **Plumbing** (`guard.pieces_of`): every line of every output that cannot be read again,
   by the tool that printed it; no content rule. If all of it fits the budget, it all goes and
   nothing is asked.
2. **The rule** (`guard.choose` over `guard.candidates`): errors, overlap with the requests,
   rare line shapes. Free, and what stands when the decider fails.
3. **The decider** (`points.keep`), asked only when the pool does not fit: one Score per block
   of output with the person's requests in full, then one Score per line of the best blocks,
   each line read in its block. Lines it scores at `MUST` or more go first, most important
   first; then the rule's lines; then lines it scores at `MAY` or more. The rule never takes
   room from a line the decider says the work needs, which is how the first cascade lost to
   the decider alone at 400 characters.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..points import keep as q
from . import guard
from .guard import Fact, Guard
from .transcript import calls

if TYPE_CHECKING:
    from ..squire import Squire

MUST = 2.0  # "a value the work might use" or above: goes before the rule
MAY = 1.5  # between background and a usable value: after the rule, if room is left
DEEP_BLOCKS = 4  # blocks whose lines are scored, best first, among those at MAY or more
CONCURRENT = 4  # block calls in flight at once: a burst of rate limits would fail the stage


async def _block_scores(
    squire: Squire, pieces: Sequence[Fact], groups: Sequence[list[int]], requests: str, notes: str
) -> list[float | None]:
    blocks = [(pieces[g[0]].source, "\n".join(pieces[i].line for i in g)) for g in groups]
    chunks = [range(i, min(i + q.BLOCKS_PER_CALL, len(blocks))) for i in
              range(0, len(blocks), q.BLOCKS_PER_CALL)]  # fmt: skip

    async def one(ids: range) -> list[float | None]:
        state, qs = q.block_questions(
            requests=requests, blocks=[blocks[i] for i in ids], notes=notes
        )
        decision = await squire.decide("keep_blocks", state, qs)
        squire.record(decision, blocks=len(ids))
        if decision.failed:
            raise RuntimeError(decision.error or "decider failed")
        return q.scores_of(decision, len(ids), q.block_id)

    gate = asyncio.Semaphore(CONCURRENT)

    async def gated(ids: range) -> list[float | None]:
        async with gate:
            return await one(ids)

    parts = await asyncio.gather(*(gated(ids) for ids in chunks))
    return [score for part in parts for score in part]


async def _line_scores(
    squire: Squire, pieces: Sequence[Fact], group: list[int], requests: str, notes: str
) -> list[float | None]:
    out: list[float | None] = []
    for start in range(0, len(group), q.LINES_PER_CALL):
        ids = group[start : start + q.LINES_PER_CALL]
        state, qs = q.line_questions(
            requests=requests,
            command=pieces[ids[0]].source,
            lines=[pieces[i].line for i in ids],
            notes=notes,
        )
        decision = await squire.decide("keep_lines", state, qs)
        squire.record(decision, lines=len(ids))
        if decision.failed:
            raise RuntimeError(decision.error or "decider failed")
        out.extend(q.scores_of(decision, len(ids), q.line_id))
    return out


async def line_scores(
    squire: Squire, pieces: Sequence[Fact], requests: str, notes: str = ""
) -> list[float | None]:
    """A score per piece (0 to `points.keep.TOP`); None for lines of blocks not scored.

    Raises when the decider fails; the caller decides what stands then.
    """
    groups = guard.blocks_of(pieces)
    blocks = await _block_scores(squire, pieces, groups, requests, notes)
    ranked = sorted(
        (i for i, s in enumerate(blocks) if s is not None and s >= MAY),
        key=lambda i: -(blocks[i] or 0.0),
    )[:DEEP_BLOCKS]
    answers = await asyncio.gather(
        *(_line_scores(squire, pieces, groups[i], requests, notes) for i in ranked)
    )
    out: list[float | None] = [None] * len(pieces)
    for i, scores in zip(ranked, answers, strict=True):
        for index, score in zip(groups[i], scores, strict=True):
            out[index] = score
    return out


def cascade(
    pieces: Sequence[Fact], rule_lines: frozenset[str], scores: Sequence[float | None] | None
) -> list[Fact]:
    """The order lines are fitted in: the decider's `MUST` lines (best first), then the rule's,
    then the decider's `MAY` lines. Without scores (the decider failed), the rule alone."""

    def by_rule(i: int) -> bool:
        return pieces[i].line[: guard.LINE_MAX] in rule_lines

    if scores is None or len(scores) != len(pieces):
        return _unique([p for i, p in enumerate(pieces) if by_rule(i)])

    def tier(i: int) -> int:
        s = scores[i] if scores[i] is not None else -1.0
        return 0 if s >= MUST else 1 if by_rule(i) else 2 if s >= MAY else 3

    order = sorted(
        range(len(pieces)),
        key=lambda i: (tier(i), -(scores[i] or 0.0), not by_rule(i), -pieces[i].call),
    )
    return _unique([pieces[i] for i in order if tier(i) < 3])


def _unique(facts: Sequence[Fact]) -> list[Fact]:
    """A line printed twice by one command takes room once."""
    seen: set[tuple[str, str]] = set()
    out: list[Fact] = []
    for fact in facts:
        if (fact.source, fact.line) not in seen:
            seen.add((fact.source, fact.line))
            out.append(fact)
    return out


async def choose(
    squire: Squire,
    history: Sequence[Any],
    requests: Sequence[str],
    *,
    budget: int = guard.FACTS_CHARS,
    notes: str = "",
    web: bool = False,
) -> tuple[tuple[Fact, ...], str, int]:
    """(the lines kept, how they were chosen, how many lines were in the pool)."""
    pieces = guard.pieces_of(history, web=web)
    if len(guard._fit(pieces, budget)) == len(pieces):
        return fit(history, requests, pieces, None, budget, web=web)
    scores = await score(squire, pieces, requests, notes)
    return fit(history, requests, pieces, scores, budget, web=web)


FAILED = "failed"  # what `score` returns when the decider failed


async def score(
    squire: Squire, pieces: Sequence[Fact], requests: Sequence[str], notes: str = ""
) -> list[float | None] | str:
    """The decider's scores for `pieces`, or `FAILED`. The only step that costs.

    `FAILED` too when no provider answered (the null decider returns empty answers without an
    error): the rule then stands and says so, instead of a hybrid being called the cascade.
    """
    if squire.provider == "null":
        return FAILED
    try:
        scores = await line_scores(squire, pieces, "\n\n".join(requests), notes)
    except RuntimeError:  # a decision that failed; a bug of ours is left to raise
        return FAILED
    return scores if any(s is not None for s in scores) else FAILED


def fit(
    history: Sequence[Any],
    requests: Sequence[str],
    pieces: Sequence[Fact],
    scores: list[float | None] | str | None,
    budget: int,
    *,
    web: bool = False,
) -> tuple[tuple[Fact, ...], str, int]:
    """The lines within `budget`, free: everything when it fits (`scores` None), the rule when
    the decider failed, else the cascade."""
    everything = guard._fit(pieces, budget)
    if len(everything) == len(pieces):
        return everything, "keep (all fit)", len(pieces)
    rule = guard.choose(guard.candidates(history, guard.focus_of(requests), web=web), budget)
    if scores is None or isinstance(scores, str):
        return rule, "keep (decider failed: rule only)", len(pieces)
    rule_lines = frozenset(f.line for f in rule)
    return guard._fit(cascade(pieces, rule_lines, scores), budget), "keep", len(pieces)


def pending_tasks(history: Sequence[Any]) -> str:
    """The agent's own task list at its latest `TodoWrite`, open items only; "" without one.

    What `notes` can hold at a compaction: Claude Code 2.1.282 runs `SessionStart` hooks
    before `PostCompact` and writes the new summary to the transcript after both, so no hook
    that adds context sees the summary it follows (docs/results/2026-09-29-context-guard/).
    """
    for call in reversed(list(history)):
        todos = call.input.get("todos") if call.tool == "TodoWrite" else None
        if isinstance(todos, list):
            open_items = [
                f"- [{t.get('status', '')}] {t.get('content', '')}"
                for t in todos
                if isinstance(t, Mapping) and t.get("status") != "completed"
            ]
            return "Open tasks:\n" + "\n".join(open_items) if open_items else ""
    return ""


async def build(
    squire: Squire,
    messages: Sequence[Mapping[str, Any]],
    *,
    facts_chars: int = guard.FACTS_CHARS,
    requests_chars: int = guard.REQUESTS_CHARS,
    notes: str = "",
    web: bool = False,
) -> Guard:
    """The guard with its facts chosen by the cascade. `notes` (the native summary, a task
    list) goes to the decider next to the requests when given."""
    history = calls(messages)
    requests = guard.requests_of(messages, requests_chars)
    facts, chooser, pool = await choose(
        squire, history, requests, budget=facts_chars, notes=notes, web=web
    )
    return Guard(
        facts=facts,
        requests=requests,
        trail=guard.trail_of(history),
        candidates=pool,
        chooser=chooser,
        clipped=guard.clipped_of(history, web=web),
    )
