"""C4: does A5's `unrelated_at=0.65` hold on fa-17's kinds of pair? (roadmap C4)

Pre-registered in `docs/results/2026-10-16-c4-written/prereg.md` (a draft until sealed).

    python benchmarks/facts_gate/written_run.py dry      # free: the calls of the batch, priced
    python benchmarks/facts_gate/written_run.py power    # free: the probability of each verdict
    python benchmarks/facts_gate/written_run.py seal     # sha256 of prereg.md and launcher, once
    python benchmarks/facts_gate/written_run.py paid     # Jev, through c4-written-run.cmd only
    python benchmarks/facts_gate/written_run.py report   # free once recorded: the verdict

The batch is `written.jsonl` (`written.py`, labels by construction). Only the shipped question
is asked, once per case (`run.query`); the gate is applied in code to the answers. The gate is
not derived here: it is A5's, 0.65, and the rule is A5's (`run.verdict`: at least 16 added
verdicts, no missed conflict, Wilson 95 % lower bound of their precision >= 0.80). `paid`
refuses before reading the key unless the seal, the instrument commit, the cases' hash, the cap
and the launch rule all hold (`paid_once.run_paid`).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import paid_once  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("facts_gate_run", HERE / "run.py")  # A5's runner: its question, gates and rule
written = _load("facts_written", HERE / "written.py")

RESULTS = ROOT / "docs" / "results" / "2026-10-16-c4-written"
PREREG = RESULTS / "prereg.md"
CASES = written.OUT
CASES_SHA256 = "44351330b80dd172cd7aa75a4c33252e0eeb638cedf216cbdd7e1fcf81e601d8"
FIXTURE = ROOT / "fixtures" / "c4-written" / "recording.jsonl"  # below fixtures/: its own set
MODEL = run.MODEL  # jev-1.13.0
GATE = run.GATE_UNDER_TEST  # 0.65, A5's
CAP_USD = 0.15


def lot() -> paid_once.Lot:
    return paid_once.Lot(
        name="c4-written",
        prereg=PREREG,
        launcher=ROOT / "c4-written-run.cmd",
        fixture=FIXTURE,
        model=MODEL,
        cap_usd=CAP_USD,  # hard, in the ledger at ~/.cache/sanchopanza/c4-written/ (fixed path)
        instrument=(
            "src",
            "benchmarks/paid_once.py",
            "benchmarks/facts_gate",
            "benchmarks/thresholds.py",
            "c4-written-run.cmd",
        ),  # fmt: skip
    )


def load() -> list[dict[str, Any]]:
    paid_once.require_file(CASES, CASES_SHA256)
    return [json.loads(x) for x in CASES.read_text(encoding="utf-8").splitlines() if x]


def queries(cases: list[dict[str, Any]]) -> list[tuple[str, Any, Any]]:
    return [run.query(c) for c in cases]


def wrong_by_kind(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Per related kind and label: how many pairs the gate turns into `unrelated` (all wrong),
    and how many the shipped policy decides wrong (descriptive)."""
    out: dict[str, Any] = {}
    for row, case in zip(rows, cases, strict=True):
        if case["expected"] == "unrelated":
            continue
        cell = out.setdefault(f"{case['kind']}:{case['expected']}",
                              {"n": 0, "gate_added_unrelated": 0, "shipped_wrong": 0,
                               "shipped_undecided": 0})  # fmt: skip
        cell["n"] += 1
        gated = row.get(f"g{GATE:.2f}")
        cell["gate_added_unrelated"] += row["shipped"] is None and gated == "unrelated"
        cell["shipped_wrong"] += row["shipped"] not in (None, case["expected"])
        cell["shipped_undecided"] += row["shipped"] is None
    for cell in out.values():
        cell["gate_added_wilson95_high"] = round(1 - run.wilson_lower(
            cell["n"] - cell["gate_added_unrelated"], cell["n"]), 4)  # fmt: skip
    return dict(sorted(out.items()))


async def report(cases: list[dict[str, Any]], the_lot: paid_once.Lot | None = None) -> dict:
    the_lot = the_lot or lot()
    recorded = paid_once.recorded(the_lot)
    missing = sum([not (await recorded.decide(*run.query(c))).answers for c in cases])
    if paid_once.unanswered_blocks(the_lot, missing):
        raise SystemExit(f"{missing} cases unanswered and a launch is still allowed: relaunch")
    rows = await run.answered(cases, recorded, "written", allow_missing=True)
    return {
        "head": paid_once.head(),
        "gate_under_test": GATE,
        "unanswered": sum(r.get("unanswered", False) for r in rows),
        "shipped": run.shipped(rows),
        "gates": [run.added(rows, g) for g in run.GATES],
        "added_by_type": run.by_type(rows, GATE),
        "related_kinds": wrong_by_kind(rows, cases),
        "result": run.verdict(rows, GATE),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("dry", "power", "seal", "paid", "report"))
    args = ap.parse_args()
    if args.action == "seal":
        print(paid_once.seal(lot()))
        return 0
    cases = load()
    if args.action == "power":
        unrelated = sum(c["expected"] == "unrelated" for c in cases)
        print(json.dumps({"unrelated_controls": run.power_table(unrelated)}, indent=1))
        return 0
    if args.action == "report":
        result = asyncio.run(report(cases))
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
        print(json.dumps(result, indent=1))
        return 0
    asks = queries(cases)
    if args.action == "dry":
        print(json.dumps({"gate": GATE, "head": paid_once.head(), **paid_once.plan(asks, lot())},
                         indent=1))  # fmt: skip
        return 0
    result = paid_once.run_paid(lot(), asks)
    print(json.dumps(result, indent=1))
    return 0 if result["stopped"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
