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
import w17_round  # noqa: E402


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
CASES_SHA256 = "a589a5d25d025390af8071b80129670a2b129ee003a54f3721e445da246207b9"
FIXTURE = ROOT / "fixtures" / "c4-written" / "recording.jsonl"  # below fixtures/: its own set
MODEL = run.MODEL  # jev-1.13.0
GATE = run.GATE_UNDER_TEST  # 0.65, A5's
NAME = "c4-written"
CAP_USD = w17_round.BATCH_CAPS[NAME]  # 0.15, this lot's batch cap on the round's shared ledger
PARTIAL_SHARE = 0.02  # more cases than this unanswered once no launch is left: no verdict
# The question's wording admits `unrelated` for a consistent pair of events or for a role and
# its act: the second reading leaves those `agree` pairs out.
LABEL_SENSITIVE = {("dated", "agree"), ("role", "agree")}
BANDS = (0.065, 0.07, 0.08, 0.10, 0.125)  # A5's real band was 39 / 560 = 7.0 %


def lot() -> paid_once.Lot:
    return paid_once.Lot(
        name=NAME,
        prereg=PREREG,
        launcher=ROOT / "c4-written-run.cmd",  # fixed by the seal (`launcher_digest`), not here
        fixture=FIXTURE,
        model=MODEL,
        cap_usd=CAP_USD,
        instrument=(
            "src",
            "benchmarks/paid_once.py",
            "benchmarks/facts_gate",
            "benchmarks/thresholds.py",
            "benchmarks/w17_round.py",
        ),  # fmt: skip
        shared_ledger=w17_round.LEDGER,
        shared_cap_usd=w17_round.CAP_USD,
    )


def make_live() -> Any:  # pragma: no cover - builds the real client
    """`paid_once.jev_live` with the client's own retries off: no call is ever asked twice."""
    from sanchopanza.providers import jev

    jev.RETRYABLE = frozenset()
    return paid_once.jev_live(MODEL)


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


def result(rows: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    """The registered verdict, and the second reading without the label-sensitive pairs."""
    missing = sum(bool(r.get("unanswered")) for r in rows)
    if missing == len(rows):
        return {"verdict": "no verdict: not run", "unanswered": missing}
    if missing > PARTIAL_SHARE * len(rows):
        return {"verdict": f"partial: {missing} cases unanswered, no verdict",
                "unanswered": missing}  # fmt: skip
    answered = [r for r in rows if not r.get("unanswered")]
    primary = run.verdict(answered, GATE)
    kept = [r for r, c in zip(rows, cases, strict=True) if not r.get("unanswered")
            and (c["kind"], c["expected"]) not in LABEL_SENSITIVE]  # fmt: skip
    second = run.verdict(kept, GATE)
    only_labels = primary["verdict"].startswith("the gate does not") and second[
        "verdict"
    ].startswith("the gate beats")
    return {**primary, "unanswered": missing, "without_dated_and_role_agree": second,
            "label_disagreement_only": only_labels}  # fmt: skip


def power_rows(units: int) -> list[dict[str, Any]]:
    """A5's power formula (`run.p_beats`) at the bands in BANDS."""
    return [
        {"band": band, "added_expected": round(units * band, 1),
         "p_undecided": round(sum(run._binom(units, n, band) for n in range(run.MIN_ADDED)), 4),
         **{f"p_beats_at_{p:.2f}": round(run.p_beats(units, band, p), 3)
            for p in (0.80, 0.93, 0.95)}}
        for band in BANDS
    ]  # fmt: skip


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
        "result": result(rows, cases),
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
        print(json.dumps({"unrelated_controls": power_rows(unrelated)}, indent=1))
        return 0
    if args.action == "report":
        got = asyncio.run(report(cases))
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_text(json.dumps(got, indent=1) + "\n", "utf-8")
        print(json.dumps(got, indent=1))
        return 0
    asks = queries(cases)
    if args.action == "dry":
        print(json.dumps({"gate": GATE, "head": paid_once.head(), **paid_once.plan(asks, lot())},
                         indent=1))  # fmt: skip
        return 0
    got = paid_once.run_paid(lot(), asks, make_live=make_live)
    print(json.dumps(got, indent=1))
    return 0 if got["stopped"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
