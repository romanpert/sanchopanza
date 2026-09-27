"""Score `memory_collision` as the two binary questions it actually is.

    python benchmarks/collision.py
    python benchmarks/collision.py --bench benches/memory.jsonl --fixture fixtures/new-points.jsonl

Free: it replays a recording and does arithmetic. Nothing is called and nothing is spent.

## Why this exists

`memory_collision` reports four labels - `duplicate`, `replace`, `flag`, `keep_both` - and
that shape has hidden it from every metric in this repository since it was added.

Read `decide_collision`: the model answers **two** independent Truth questions,
`contradicts` and `adds_nothing`. The four actions are those two probabilities plus
`newer`, which is **never asked of the model** - the harness supplies it from timestamps it
already holds, precisely because this model class reads dates as text. So a "4-label point"
is two binary judgments and one comparison done in code.

The consequence is mechanical and it is in `eval/bench.py`: for this point `probability`
stays `None`, because there is no single probability to report, and a row with no
probability is excluded from the binary table. The point therefore has **no AUC, no Brier
and no ECE anywhere in the paper or the results**, while every other point has all three.
`docs/results/2026-09-24-fifty/README.md` says the point "needs its own treatment". This is
that treatment, and it needed no new labels at all.

## The two binary truths are recovered, not annotated

The 4-way label plus `newer`, which is part of the case input, determines both binary
answers exactly. `truths()` below is the inverse of `decide_collision`. That matters for
three reasons: the published bench files are not edited, so the runs of 2026-09-24 stay
reproducible byte for byte; the recording replays unchanged; and the new metric applies
retroactively to every collision case ever labelled.

The one thing the inverse cannot recover is `contradicts` on a `duplicate` case: the
`adds_nothing` branch short-circuits before `contradicts` is consulted, so the label
constrains nothing there. Those cases are excluded from the `contradicts` column rather
than guessed, which is why its n is smaller than the case count.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.eval.bench import _bench_thresholds  # noqa: E402
from sanchopanza.eval.stats import auc, brier, ece, wilson  # noqa: E402
from sanchopanza.journal import MemoryJournal  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

POINT = "memory_collision"

# Targets and the acted-case floor each one needs at perfect observed precision, from the
# 95 % Wilson lower bound. Same arithmetic as `benchmarks/thresholds.py`; stated here so a
# reader of this file alone can see what the sample would have to be.
FLOOR = {0.80: 16, 0.90: 35, 0.95: 73}


def truths(expected: str, newer: bool | None) -> dict[str, bool | None]:
    """The two binary answers implied by the 4-way label. The inverse of `decide_collision`."""
    if expected == "duplicate":
        # `pn >= t.act` fires first and returns, so the label says nothing about contradicts.
        return {"adds_nothing": True, "contradicts": None}
    if expected in ("replace", "flag"):
        return {"adds_nothing": False, "contradicts": True}
    if expected == "keep_both":
        # Reached either because contradicts was low, or because it was high and the stored
        # fact is the newer one. `newer` separates the two without asking the model.
        return {"adds_nothing": False, "contradicts": newer is False}
    raise ValueError(f"unknown collision label: {expected!r}")


def load(bench: Path, point: str) -> list[dict[str, Any]]:
    cases = []
    for line in bench.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        case = json.loads(line)
        if case.get("point") == point:
            cases.append(case)
    return cases


async def replay(cases: list[dict[str, Any]], fixture: Path) -> list[dict[str, Any]]:
    """Every case through a fresh squire against the recording, as the bench does it."""
    decider = RecordedDecider.from_file(fixture)
    t = _bench_thresholds(Thresholds()).with_(max_decisions=10_000, max_usd=100.0)
    rows = []
    for case in cases:
        squire = Squire(decider, thresholds=t, journal=MemoryJournal())
        inp = case["input"]
        r = await squire.reconcile(new=inp["new"], stored=inp["stored"], newer=inp.get("newer"))
        rows.append(
            {
                "id": case["id"],
                "expected": case["expected"],
                "newer": inp.get("newer"),
                "action": r.action,
                "contradicts": r.contradicts,
                "adds_nothing": r.adds_nothing,
                "truths": truths(case["expected"], inp.get("newer")),
            }
        )
    return rows


def _pairs(rows: list[dict[str, Any]], name: str) -> list[tuple[float, bool]]:
    """(score, truth) for the cases this question is defined on."""
    scores, labels = _question(rows, name)
    return list(zip(scores, labels, strict=True))


def _question(rows: list[dict[str, Any]], name: str) -> tuple[list[float], list[bool]]:
    scores, labels = [], []
    for row in rows:
        truth = row["truths"][name]
        if truth is None:
            continue
        scores.append(float(row[name]))
        labels.append(bool(truth))
    return scores, labels


def report(rows: list[dict[str, Any]], t: Thresholds) -> str:
    out: list[str] = []
    out.append(f"# `{POINT}` as two binary questions\n")
    out.append(f"{len(rows)} cases, replayed from the recording. Cost: 0.\n")

    out.append("## Per case\n")
    out.append("| id | label | action | correct | `contradicts` | `adds_nothing` |")
    out.append("|---|---|---|---|---|---|")
    for row in rows:
        ok = "yes" if row["action"] == row["expected"] else "**no**"
        out.append(
            f"| {row['id']} | {row['expected']} | {row['action']} | {ok} "
            f"| {row['contradicts']:.2f} | {row['adds_nothing']:.2f} |"
        )
    wrong = [r["id"] for r in rows if r["action"] != r["expected"]]
    out.append(f"\nAgreement: {len(rows) - len(wrong)}/{len(rows)}. Errors: {wrong or 'none'}\n")

    out.append("## The two questions, scored for the first time\n")
    out.append("| question | n | positives | AUC | Brier | ECE | separation |")
    out.append("|---|---|---|---|---|---|---|")
    # (max negative, min positive, max positive) per question. The third is what says
    # whether a cut is reachable at all, and leaving it out is how the first version of this
    # file printed a conclusion instead of deriving one: it read `min(pos)` and described it
    # as the top of the range. On the 16 original cases min and max both sat under `t.act`,
    # so the sentence happened to be true; on a batch of ordinary restatements it was false
    # and the tool asserted the branch was dead while the table beside it showed 16/18 firing.
    # A narrative that does not recompute is a narrative that lies on the second dataset.
    band: dict[str, tuple[float, float, float]] = {}
    for name in ("contradicts", "adds_nothing"):
        scores, labels = _question(rows, name)
        pos = [s for s, y in zip(scores, labels, strict=True) if y]
        neg = [s for s, y in zip(scores, labels, strict=True) if not y]
        lo = max(neg) if neg else 0.0
        band[name] = (lo, min(pos) if pos else 1.0, max(pos) if pos else 0.0)
        out.append(
            f"| `{name}` | {len(scores)} | {len(pos)} | {auc(scores, labels):.2f} "
            f"| {brier(scores, labels):.3f} | {ece(scores, labels):.3f} "
            f"| {lo:.2f} -> {band[name][1]:.2f} (gap {band[name][1] - lo:.2f}) |"
        )

    out.append("\n## One threshold, two distributions\n")
    out.append(f"`decide_collision` gates both questions on the same `t.act = {t.act}`.\n")
    for name, acting in (("contradicts", "a contradiction"), ("adds_nothing", "`duplicate`")):
        lo, first, top = band[name]
        if t.act > top:
            verdict = (
                f"sits **above the entire positive range** (top positive {top:.2f}), so "
                f"{acting} cannot fire at all: not a branch that fails, one that does not exist"
            )
        elif t.act > first:
            caught = sum(1 for s, y in _pairs(rows, name) if y and s >= t.act)
            total = sum(1 for _s, y in _pairs(rows, name) if y)
            verdict = (
                f"reaches {caught}/{total} of the positives (range {first:.2f} to {top:.2f}), "
                f"so {acting} fires but loses the weakest cases"
            )
        else:
            verdict = f"falls in the gap between {lo:.2f} and {first:.2f} and separates every case"
        out.append(f"- `{name}`: the cut {verdict}.")
    out.append("")
    out.append(
        "The same `adds_nothing` predicate at page granularity is `redundant_page`, which "
        f"carries its own derived threshold `t.adds_nothing = {t.adds_nothing}`. Whether a "
        "threshold derived at one granularity transfers to another is an open question in "
        "this repository; the sweep below is the evidence available, and it is thin.\n"
    )

    scores, labels = _question(rows, "adds_nothing")
    pos_n = sum(labels)
    out.append("| cut | duplicates caught | false positives | precision | 95 % lower bound |")
    out.append("|---|---|---|---|---|")
    for cut in (t.act, t.adds_nothing, 0.5, 0.40):
        tp = sum(1 for s, y in zip(scores, labels, strict=True) if s >= cut and y)
        fp = sum(1 for s, y in zip(scores, labels, strict=True) if s >= cut and not y)
        acted = tp + fp
        if acted:
            p, lo, _hi = wilson(tp, acted)
            prec, bound = f"{p:.0%}", f"{lo:.0%}"
        else:
            prec, bound = "-", "-"
        out.append(f"| {cut:.2f} | {tp}/{pos_n} | {fp} | {prec} | {bound} |")

    out.append("\n## What this sample can and cannot support\n")
    acted_now = sum(1 for s, y in zip(scores, labels, strict=True) if s >= t.adds_nothing)
    out.append(
        f"At the most permissive cut examined the `duplicate` branch acts on **{acted_now}** "
        "case(s). A precision target needs the 95 % Wilson lower bound to clear it, which at "
        "perfect observed precision requires:\n"
    )
    for target, floor in FLOOR.items():
        out.append(f"- {target:.0%}: **{floor}** acted cases (about {floor * 2} labelled)")
    out.append(
        f"\nSo no threshold moves on this evidence, and the bench that would settle it is not "
        f"'fifty more cases of the same shape': it is a bench built **toward the branch that "
        f"acts**, with at least {FLOOR[0.80]} genuine duplicates plus the near-misses that "
        "would produce false positives - corroboration from a second source, a narrower "
        "restatement, the same value carrying one new qualifier.\n"
    )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", default=str(ROOT / "benches/memory.jsonl"))
    parser.add_argument("--fixture", default=str(ROOT / "fixtures/new-points.jsonl"))
    parser.add_argument("--out", default="", help="write the report here as well as to stdout")
    args = parser.parse_args()

    cases = load(Path(args.bench), POINT)
    if not cases:
        print(f"no {POINT} cases in {args.bench}", file=sys.stderr)
        return 1
    rows = asyncio.run(replay(cases, Path(args.fixture)))
    text = report(rows, Thresholds())
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
