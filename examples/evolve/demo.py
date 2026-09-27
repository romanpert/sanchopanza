"""A trivial RRSI-style outer loop over the fifty-case bench, entirely offline, for 0 USD.

    python examples/evolve/demo.py [--ledger path/to/ledger.jsonl]

The proposer is deliberately dumb: each round sweeps one threshold over a grid, one atomic
edit per candidate. Everything else is the real interface:

    Split.by_hash -> Evaluator (replaying fixtures/new-points-50-v2.jsonl through the real
    policy code) -> leak_check -> Ledger.already_refuted -> admit (noise floor, cost rule,
    edit budget) -> Ledger.record -> holdout confirmation -> one fresh read at the end.

The noise floor uses the six re-ask deltas measured on 2026-09-25 (0.30 -> 0.39 and 0.38;
0.34 -> 0.36 twice; 0.29 -> 0.31 twice; `docs/results/2026-09-25-window/` section 7).

What to expect, and why it is the correct output: the shipped thresholds were derived or
measured on these same cases, the evolution split is about 100 cases, and the floor is about
8 points. A sweep of one threshold at a time should find nothing admissible. If it prints
"no candidate admitted", the loop is doing its job: it refused to turn noise into a change.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sanchopanza import Thresholds
from sanchopanza.eval.bench import load_cases
from sanchopanza.evolve import (
    Evaluator,
    Knobs,
    Ledger,
    Score,
    Split,
    admit,
    diff,
    edit_budget,
    leak_check,
)
from sanchopanza.journal import MemoryJournal
from sanchopanza.providers import RecordedDecider

ROOT = Path(__file__).resolve().parents[2]
BENCHES = ["loop-b.jsonl", "memory-b.jsonl", "graph-build-b.jsonl", "retrieval-b.jsonl"]
FIXTURE = ROOT / "fixtures" / "new-points-50-v2.jsonl"
DRIFT = (0.09, 0.08, 0.02, 0.02, 0.02, 0.02)
GRID = {
    "adds_nothing": (0.45, 0.50, 0.55, 0.65, 0.70, 0.80),
    "remember": (0.55, 0.60, 0.65, 0.75, 0.80),
    "derivable": (0.60, 0.65, 0.70, 0.80, 0.85),
    "act": (0.60, 0.65, 0.70, 0.80, 0.85),
    "saturated": (0.50, 0.60, 0.80, 0.90),  # the bench scores loop at 0.5: expect "inert"
}
BETA0, BETA1 = 0.0, 0.0  # thresholds do not change the calls, so no extra cost is allowed


def line(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def per_point(score: Score) -> str:
    return ", ".join(f"{p} {h}/{n}" for p, (h, n) in score.per_point.items())


def run_round(
    ev: Evaluator,
    ledger: Ledger,
    incumbent: Knobs,
    incumbent_score: Score,
    delta: float,
    knob: str,
    budget: int,
    round_: int,
) -> tuple[Knobs, Score] | None:
    """Try every grid value of one knob. Returns the best admitted candidate, if any."""
    best: tuple[Knobs, Score, float] | None = None
    for value in GRID[knob]:
        candidate = incumbent.with_threshold(knob, value)
        edits = diff(incumbent, candidate)
        if not edits:
            continue
        label = f"  {knob} {incumbent.threshold(knob):.2f} -> {value:.2f}"
        if not all(leak_check(e, ev.split.evolve).ok for e in edits):
            line(f"{label}: leak, rejected before scoring")
            continue
        if ledger.already_refuted(edits, incumbent=incumbent.fingerprint()):
            line(f"{label}: refuted earlier, not retried")
            continue
        score = ev.score(candidate, "evolve")
        if score.outcomes == incumbent_score.outcomes:
            verdict, reasons = "refuted", ("inert: no prediction changed on this split",)
            gain = 0.0
        else:
            adm = admit(
                score.accuracy,
                incumbent_score.accuracy,
                delta=delta,
                cost_delta=score.cost_per_case - incumbent_score.cost_per_case,
                beta0=BETA0,
                beta1=BETA1,
                edits=edits,
                budget=budget,
            )
            reasons, gain = adm.reasons, adm.gain
            if score.costly_errors > incumbent_score.costly_errors:
                reasons = (
                    *reasons,
                    f"costly-direction errors {incumbent_score.costly_errors} -> "
                    f"{score.costly_errors}",
                )
            verdict = "admitted" if not reasons else "refuted"
        ledger.record(
            edits,
            incumbent=incumbent.fingerprint(),
            part="evolve",
            candidate=score.accuracy,
            incumbent_score=incumbent_score.accuracy,
            delta=delta,
            verdict=verdict,
            reasons=reasons,
            round=round_,
        )
        why = "; ".join(reasons) if reasons else "above the floor"
        tally = f"{score.hits}/{score.n} ({gain:+.3f}, costly {score.costly_errors})"
        line(f"{label}: {tally} {verdict.upper()} - {why}")
        if verdict == "admitted" and (best is None or gain > best[2]):
            best = (candidate, score, gain)
    return None if best is None else (best[0], best[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=None, help="JSONL ledger path (default: in memory)")
    args = parser.parse_args()
    if not FIXTURE.exists():
        line(f"fixture not found: {FIXTURE}")
        return 1

    cases = load_cases(ROOT / "benches" / name for name in BENCHES)
    split = Split.by_hash(cases, holdout=0.25, fresh=0.25)
    journal = MemoryJournal()
    base = Knobs.from_thresholds(Thresholds())
    ev = Evaluator(split, recording=RecordedDecider.from_file(FIXTURE), base=base, journal=journal)
    ledger = Ledger(args.ledger)

    line(f"cases: {len(cases)}; split evolve/holdout/fresh = {split.sizes}")
    incumbent, incumbent_score = base, ev.score(base, "evolve")
    floor = ev.noise_floor(base, "evolve", drift=DRIFT)
    line(
        f"incumbent (shipped) on evolve: {incumbent_score.hits}/{incumbent_score.n}, "
        f"costly-direction errors {incumbent_score.costly_errors}"
    )
    line(f"  {per_point(incumbent_score)}")
    line(
        f"noise floor: delta {floor.delta:.3f} = Wilson half-width {floor.sampling:.3f} + "
        f"drift {floor.drift:.3f} ({floor.drift_flips} cases flip at +/-{floor.magnitude:.2f})"
    )

    rounds = list(GRID)
    admitted_any = False
    for r, knob in enumerate(rounds):
        budget = edit_budget(r, len(rounds), 3, 1)
        line(f"\nround {r} - sweep {knob} - edit budget {budget}")
        found = run_round(ev, ledger, incumbent, incumbent_score, floor.delta, knob, budget, r)
        if found is None:
            line("  no candidate admitted")
            continue
        candidate, score = found
        held = ev.score(candidate, "holdout")
        held_incumbent = ev.score(incumbent, "holdout")
        if held.accuracy < held_incumbent.accuracy:
            line(f"  holdout refuses it: {held.hits}/{held.n} vs {held_incumbent.hits}/{held.n}")
            continue
        line(f"  holdout confirms: {held.hits}/{held.n} vs {held_incumbent.hits}/{held.n}")
        incumbent, incumbent_score, admitted_any = candidate, score, True
        floor = ev.noise_floor(incumbent, "evolve", drift=DRIFT)

    line("")
    refuted = sum(1 for e in ledger.entries if e.verdict == "refuted")
    line(f"ledger: {len(ledger.entries)} trials, {refuted} refuted")
    line(f"holdout reads: {ev.holdout_reads}")
    if admitted_any:
        final, shipped = ev.score_fresh(incumbent, base)
        line(f"fresh (read once): final {final.hits}/{final.n} vs shipped {shipped.hits}/{final.n}")
        for edit in diff(base, incumbent):
            line(f"  kept: {edit.kind} {edit.key} {edit.before} -> {edit.after}")
    else:
        line("no candidate cleared the noise floor: the shipped thresholds stand.")
        line("the fresh split was not read; it stays unspent for the next real change.")
    line("cost: 0 USD (every decision replayed from the recording)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
