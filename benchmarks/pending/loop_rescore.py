"""Re-score the recorded loop bench at the threshold the policy actually enforces (F11).

    .venv/Scripts/python.exe benchmarks/pending/loop_rescore.py

Free and offline: every answer comes from a recording, nothing is called.

Why. `eval/bench.py` scores `goal_met` and `repeats_check` with `probability >= 0.5`, and
`benchmarks/thresholds.py` lists 0.50 as the shipped value, but `points/loop.decide` only
speaks at `probability >= Thresholds.saturated` (0.70). The published "agreement under the
policy" for this point is therefore the 0.5 figure. This script replays the SAME recordings
through the real `Squire.check_loop` and reads what the shipped policy actually says (the
note in `LoopAdvice.message`), then scores it next to the 0.5 cut.

Recordings used, one per case (the "-v2" fixtures carry the loop entries unchanged; the
script checks that and fails loudly if it ever stops being true):

- `fixtures/new-points-v2.jsonl` + `benches/loop.jsonl`   first batch, 14 + 12 cases
- `fixtures/new-points-50-v2.jsonl` + `benches/loop-b.jsonl` second batch, 36 + 38 cases

"Acting" means the policy emits its advisory note for that question. For both questions the
costly direction is acting on a false case (telling an agent it is done when it is not, or
that a needed check is a repeat); silence is the default behaviour of the harness.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.eval.bench import load_cases  # noqa: E402
from sanchopanza.eval.stats import wilson  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import RecordedDecider  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

BATCHES = (
    ("first (loop.jsonl)", "loop.jsonl", "new-points-v2.jsonl", "new-points.jsonl"),
    ("second (loop-b.jsonl)", "loop-b.jsonl", "new-points-50-v2.jsonl", "new-points-50.jsonl"),
)
NOTE = {
    "goal_met": "appears to be established already",
    "repeats_check": "looks like one already run",
}
OUT = ROOT / "docs" / "results" / "2026-09-25-pending" / "loop-rescore.json"


def _loop_entries(path: Path) -> dict[str, dict]:
    rows = (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip())
    return {r["key"]: r["answers"] for r in rows if r.get("point") == "loop"}


def _check_same_recording(a: Path, b: Path) -> None:
    ea, eb = _loop_entries(a), _loop_entries(b)
    if ea != eb:
        raise SystemExit(f"{a.name} and {b.name} disagree on loop answers: re-derive this report")


async def _replay(cases: list[dict], fixture: Path) -> list[dict]:
    decider = RecordedDecider.from_file(fixture)
    t = Thresholds()
    rows = []
    for case in cases:
        squire = Squire(decider, thresholds=t.with_(max_decisions=10_000, max_usd=100.0))
        inp = case["input"]
        advice = await squire.check_loop(
            goal=inp["goal"],
            done=inp["done"],
            pending=inp.get("pending", ""),
            checks=inp.get("checks", ()),
        )
        point = case["point"]
        p = advice.goal_met if point == "goal_met" else advice.repeats_check
        speaks = NOTE[point] in advice.message
        if speaks != (p >= t.saturated):
            raise SystemExit(f"{case['id']}: note and probability disagree; policy changed?")
        rows.append(
            {
                "id": case["id"],
                "point": point,
                "expected": bool(case["expected"]),
                "probability": p,
                "at_0.5": p >= 0.5,
                "shipped": speaks,
            }
        )
    return rows


def _score(rows: list[dict], key: str) -> dict:
    tp = sum(1 for r in rows if r[key] and r["expected"])
    fp = sum(1 for r in rows if r[key] and not r["expected"])
    fn = sum(1 for r in rows if not r[key] and r["expected"])
    tn = sum(1 for r in rows if not r[key] and not r["expected"])
    n = len(rows)
    silent_band = sum(1 for r in rows if not r[key] and r["probability"] > 0.30)

    def w(k: int, m: int) -> list[float]:
        return [round(x, 3) for x in wilson(k, m)]

    return {
        "n": n,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": [tp + tn, n, *w(tp + tn, n)],
        "precision": [tp, tp + fp, *w(tp, tp + fp)],
        "recall": [tp, tp + fn, *w(tp, tp + fn)],
        "silent_in_band_0.30_to_cut": silent_band,
    }


def _fmt(s: list) -> str:
    k, m, _, lo, hi = s
    return f"{k}/{m} [{lo:.0%}, {hi:.0%}]" if m else "-"


async def main() -> None:
    t = Thresholds()
    all_rows: list[dict] = []
    for label, bench, fixture, twin in BATCHES:
        _check_same_recording(ROOT / "fixtures" / fixture, ROOT / "fixtures" / twin)
        cases = [
            c
            for c in load_cases([ROOT / "benches" / bench])
            if c["point"] in ("goal_met", "repeats_check")
        ]
        for r in await _replay(cases, ROOT / "fixtures" / fixture):
            all_rows.append({**r, "batch": label})

    report: dict = {"saturated": t.saturated, "cells": {}, "rows": all_rows}
    print(f"shipped threshold (Thresholds().saturated) = {t.saturated}\n")
    print("| point | batch | cut | accuracy | precision | recall | FP | FN |")
    print("|---|---|---|---|---|---|---|---|")
    for point in ("goal_met", "repeats_check"):
        for label in [b[0] for b in BATCHES] + ["both (n=50)"]:
            rows = [
                r
                for r in all_rows
                if r["point"] == point and (label.startswith("both") or r["batch"] == label)
            ]
            for key, cut in (("at_0.5", "0.50"), ("shipped", f"{t.saturated:.2f}")):
                s = _score(rows, key)
                report["cells"][f"{point}|{label}|{cut}"] = s
                print(
                    f"| {point} | {label} | {cut} | {_fmt(s['accuracy'])} | "
                    f"{_fmt(s['precision'])} | {_fmt(s['recall'])} | {s['fp']} | {s['fn']} |"
                )
    print("\nCases where the two cuts disagree, or either is wrong:")
    for r in all_rows:
        if r["at_0.5"] != r["shipped"] or r["shipped"] != r["expected"]:
            print(
                f"  {r['id']:7} expected={r['expected']!s:5} p={r['probability']:.2f} "
                f"0.5->{r['at_0.5']!s:5} shipped->{r['shipped']!s:5}"
            )
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwritten {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
