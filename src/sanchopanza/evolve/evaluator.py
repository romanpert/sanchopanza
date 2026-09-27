"""Score a `Knobs` snapshot on a split by replaying recorded decisions through the real policy.

The replay is `eval.bench.run_bench` - the same `Squire` methods production calls - with the
snapshot's thresholds and a decider chain built for the snapshot:

    QuestionOverrides(recording or live)  ->  MissCounter  ->  run_bench

Four refusals, each of them a way an outer loop would otherwise score an edit it never tested:

- **`RecordingInvalidated`**: the snapshot rewords a question. The request changes, the
  recording no longer answers, and the only honest score is a live re-ask. Refused unless a
  live decider was passed explicitly (wrap it in `RecordingDecider` so the re-ask becomes a
  recording).
- **`UnexercisedEdit`**: the edit is to something the bench runner never builds (a catalog
  `about`, a window flag) or overrides (`allow_upgrade`, the per-job caps). Scoring it would
  report "no change" for an edit that was never run, and a loop would keep it for free.
- **`RecordingMiss`**: a decision came back with no answers. The policy then falls back to
  its default, and on a gate whose default is the right label that *scores as a hit*. A
  missing recording must not look like a result.
- **`FreshSplitSpent`**: the fresh split was already read once.

Holdout reads are allowed and counted, and each one is journaled with the snapshot read.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from ..answers import truth
from ..contract import Answer, Decider, Decision, Question, State
from ..eval.bench import Row, run_bench
from ..journal import Journal, NullJournal
from .knobs import Edit, Knobs, diff
from .regularizers import NoiseFloor, drift_magnitude, noise_floor
from .split import Case, Part, Split

# Threshold names `run_bench` forces to its own values: an edit to them is never exercised.
RUNNER_FIXED: frozenset[str] = frozenset({"allow_upgrade", "max_decisions", "max_usd"})
# The label a point emits when it ACTS - the direction whose error the operator sees. Same
# orientation as `benchmarks/thresholds.py` ACTION, plus page triage.
ACTING: dict[str, object] = {
    "memory_write": "store",
    "redundant_page": "drop",
    "extract_gate": "skip",
    "recall": "skip",
    "goal_met": True,
    "repeats_check": True,
    "triage": "drop",
}


class RecordingInvalidated(RuntimeError):
    """The snapshot changes a request the recording answered. Needs a live decider."""


class UnexercisedEdit(RuntimeError):
    """The snapshot changes something this evaluator never runs."""


class RecordingMiss(RuntimeError):
    """A replayed decision had no recorded answer, so the policy default would be scored."""


class FreshSplitSpent(RuntimeError):
    """The fresh split is read once."""


@dataclass(frozen=True, slots=True)
class Score:
    """Agreement of one snapshot on one split part. `hits / n`: an abstention earns nothing."""

    part: Part
    knobs: str  # fingerprint of the snapshot scored
    n: int
    hits: int
    decided: int
    calls: int
    misses: int
    cost_usd: float  # what the calls cost when recorded; the replay itself costs nothing
    per_point: Mapping[str, tuple[int, int]]  # point -> (hits, n)
    # Wrong AND acting (stored, dropped, skipped): the costly direction every policy here is
    # asymmetric against. Agreement is symmetric and cannot see a trade of cheap errors for
    # costly ones; a loop should hold this at or below the incumbent's (docs/evolve.md).
    costly_errors: int
    outcomes: tuple[tuple[str, str], ...]  # (case id, predicted), to detect inert edits
    live: bool = False

    @property
    def accuracy(self) -> float:
        return self.hits / self.n if self.n else 0.0

    @property
    def cost_per_case(self) -> float:
        return self.cost_usd / self.n if self.n else 0.0


class QuestionOverrides:
    """Rewrites the `instructions` of overridden questions before the inner decider sees them.

    Keys are `point:question`. The decider is the one chokepoint every point goes through, so
    this needs no hook in `points/*.py`; the recording key moves with the wording, which is
    exactly why a reworded question cannot be replayed.
    """

    def __init__(self, inner: Decider, overrides: Mapping[str, str]) -> None:
        self._inner = inner
        self._overrides = dict(overrides)
        self.name = inner.name
        self.accepts_attachments = getattr(inner, "accepts_attachments", False)

    def _rewrite(self, point: str, questions: Mapping[str, Question]) -> dict[str, Question]:
        return {
            key: (
                replace(q, instructions=self._overrides[f"{point}:{key}"])
                if f"{point}:{key}" in self._overrides
                else q
            )
            for key, q in questions.items()
        }

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        return await self._inner.decide(point, state, self._rewrite(point, questions))


class _MissCounter:
    """Counts decisions asked and decisions that came back with no answer at all."""

    def __init__(self, inner: Decider) -> None:
        self._inner = inner
        self.name = inner.name
        self.accepts_attachments = getattr(inner, "accepts_attachments", False)
        self.calls = 0
        self.misses = 0

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        decision = await self._inner.decide(point, state, questions)
        self.calls += 1
        if questions and not decision.answers:
            self.misses += 1
        return decision


class _Drift:
    """Shifts every Truth probability by `shift`, clamped, as a re-ask on another day might.

    Choice and Score answers pass unchanged: their drift has not been measured here.
    """

    def __init__(self, inner: Decider, shift: float) -> None:
        self._inner = inner
        self._shift = shift
        self.name = inner.name
        self.accepts_attachments = getattr(inner, "accepts_attachments", False)

    def _move(self, answer: Answer) -> Answer:
        if answer.kind != "truth" or answer.truth is None:
            return answer
        return truth(answer.truth + self._shift)

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        decision = await self._inner.decide(point, state, questions)
        moved = {key: self._move(a) for key, a in decision.answers.items()}
        return replace(decision, answers=moved)


class Evaluator:
    """Scores snapshots on a fixed split. Stateful on purpose: it counts what was read."""

    def __init__(
        self,
        split: Split,
        *,
        recording: Decider,
        base: Knobs,
        live: Decider | None = None,
        journal: Journal | None = None,
        allow_missing: bool = False,
        concurrency: int = 4,
    ) -> None:
        self._split = split
        self._recording = recording
        self._base = base
        self._live = live
        self._journal: Journal = journal or NullJournal()
        self._allow_missing = allow_missing
        self._concurrency = concurrency
        self._holdout_reads = 0
        self._fresh_read = False

    @property
    def split(self) -> Split:
        return self._split

    @property
    def base(self) -> Knobs:
        """The snapshot the recording was made with."""
        return self._base

    @property
    def holdout_reads(self) -> int:
        return self._holdout_reads

    # --- checks ------------------------------------------------------------------------------

    def check(self, knobs: Knobs) -> tuple[Edit, ...]:
        """The edits from the recorded base, or the reason they cannot be scored here."""
        edits = diff(self._base, knobs)
        unexercised = [
            e
            for e in edits
            if e.kind in ("about", "flag") or (e.kind == "threshold" and e.key in RUNNER_FIXED)
        ]
        if unexercised:
            names = ", ".join(f"{e.kind}:{e.key}" for e in unexercised)
            raise UnexercisedEdit(
                f"{names}: the bench runner never exercises this, so any score would be the "
                "score of an edit that was not run"
            )
        reworded = [e for e in edits if e.invalidates_recordings]
        if reworded and self._live is None:
            names = ", ".join(f"{e.kind}:{e.key}" for e in reworded)
            raise RecordingInvalidated(
                f"{names} changes the request, so the recording cannot answer it. Pass a live "
                "decider explicitly (it costs money and drifts up to 0.09 a day)"
            )
        return edits

    def _account(self, knobs: Knobs, part: Part) -> None:
        if part == "fresh":
            if self._fresh_read:
                raise FreshSplitSpent("the fresh split was already read; it is read once")
            self._fresh_read = True
        elif part == "holdout":
            self._holdout_reads += 1
            self._journal.record(
                "holdout_read", {"read": self._holdout_reads, "knobs": knobs.fingerprint()}
            )

    # --- running -----------------------------------------------------------------------------

    def _decider(self, knobs: Knobs, edits: Sequence[Edit]) -> tuple[Decider, bool]:
        live = any(e.invalidates_recordings for e in edits)
        inner = self._live if live and self._live is not None else self._recording
        return QuestionOverrides(inner, knobs.question), live

    async def _rows(
        self, knobs: Knobs, cases: Sequence[Case], decider: Decider
    ) -> tuple[list[Row], _MissCounter]:
        counter = _MissCounter(decider)
        results = await run_bench(
            cases, counter, thresholds=knobs.to_thresholds(), concurrency=self._concurrency
        )
        return [r for r in results if isinstance(r, Row)], counter

    async def _measure(self, knobs: Knobs, part: Part, edits: Sequence[Edit]) -> Score:
        decider, live = self._decider(knobs, edits)
        rows, counter = await self._rows(knobs, self._split.part(part), decider)
        if counter.misses and not self._allow_missing:
            raise RecordingMiss(
                f"{counter.misses} of {counter.calls} decisions had no recorded answer; "
                "the policy default would have been scored as the result"
            )
        return _score(part, knobs, rows, counter, live)

    async def ascore(self, knobs: Knobs, part: Part) -> Score:
        edits = self.check(knobs)
        self._split.part(part)  # validates the name before anything is counted
        self._account(knobs, part)
        return await self._measure(knobs, part, edits)

    def score(self, knobs: Knobs, part: Part) -> Score:
        """Synchronous `ascore`. Do not call from inside a running event loop."""
        return asyncio.run(self.ascore(knobs, part))

    async def ascore_fresh(self, *snapshots: Knobs) -> tuple[Score, ...]:
        """The one read of the fresh split, for every snapshot declared in this call.

        Final against base is a comparison, not a selection, so both go in one read. What is
        refused is coming back with a third snapshot after seeing the first two.
        """
        if not snapshots:
            raise ValueError("declare at least one snapshot for the fresh read")
        checked = [(k, self.check(k)) for k in snapshots]
        self._account(snapshots[0], "fresh")
        return tuple([await self._measure(k, "fresh", edits) for k, edits in checked])

    def score_fresh(self, *snapshots: Knobs) -> tuple[Score, ...]:
        return asyncio.run(self.ascore_fresh(*snapshots))

    async def aflips_under_drift(self, knobs: Knobs, part: Part, magnitude: float) -> int:
        """Cases whose correctness changes when every Truth answer moves by +/- `magnitude`.

        The share of a split that one day of provider drift can flip, measured through the
        real policy rather than guessed from a distance to one cut.
        """
        if magnitude < 0:
            raise ValueError("a drift magnitude is non-negative")
        edits = self.check(knobs)
        cases = self._split.part(part)
        self._account(knobs, part)
        decider, _ = self._decider(knobs, edits)
        base, _ = await self._rows(knobs, cases, decider)
        if magnitude == 0 or not base:
            return 0
        up, _ = await self._rows(knobs, cases, _Drift(decider, magnitude))
        down, _ = await self._rows(knobs, cases, _Drift(decider, -magnitude))
        right = {r.id: r.correct for r in base}
        moved = {r.id for r in (*up, *down) if r.correct != right.get(r.id)}
        return len(moved)

    def flips_under_drift(self, knobs: Knobs, part: Part, magnitude: float) -> int:
        return asyncio.run(self.aflips_under_drift(knobs, part, magnitude))

    def noise_floor(
        self, knobs: Knobs, part: Part = "evolve", *, drift: Sequence[float] = ()
    ) -> NoiseFloor:
        """`regularizers.noise_floor` at this split's size, with the drift share measured."""
        score = self.score(knobs, part)
        magnitude = drift_magnitude(drift)
        flips = self.flips_under_drift(knobs, part, magnitude) if magnitude else 0
        return noise_floor(score.n, score.accuracy, drift_flips=flips, magnitude=magnitude)


def _score(
    part: Part, knobs: Knobs, rows: Sequence[Row], counter: _MissCounter, live: bool
) -> Score:
    per_point: dict[str, tuple[int, int]] = {}
    for r in rows:
        hits, n = per_point.get(r.point, (0, 0))
        per_point[r.point] = (hits + (1 if r.correct else 0), n + 1)
    outcomes = tuple(sorted((r.id, repr(r.predicted)) for r in rows))
    return Score(
        part=part,
        knobs=knobs.fingerprint(),
        n=len(rows),
        hits=sum(1 for r in rows if r.correct),
        decided=sum(1 for r in rows if r.decided),
        calls=counter.calls,
        misses=counter.misses,
        cost_usd=sum(r.cost_usd for r in rows),
        per_point=dict(sorted(per_point.items())),
        costly_errors=sum(
            1
            for r in rows
            if r.correct is False and r.point in ACTING and r.predicted == ACTING[r.point]
        ),
        outcomes=outcomes,
        live=live,
    )
