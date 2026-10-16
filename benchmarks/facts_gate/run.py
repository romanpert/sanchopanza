"""A5: does an `unrelated` gate other than the shipped one beat it?

Pre-registered in `docs/results/2026-10-16-a5-unrelated/prereg.md`.

    python benchmarks/facts_gate/run.py free     # free: derive the gate, see it on graph-e
    python benchmarks/facts_gate/run.py dry      # free: the calls of the constructed batch, priced
    python benchmarks/facts_gate/run.py seal     # sha256 of prereg.md and the launcher, once
    python benchmarks/facts_gate/run.py paid     # Jev, through a5-unrelated-run.cmd only
    python benchmarks/facts_gate/run.py report   # free once recorded: the verdict

`paid` refuses before reading the key unless the seal, the instrument commit, the cases' hash,
the derived gate, the cap and the launch rule all hold (`paid_once.run_paid`).

The gate is `entities.decide_facts(..., unrelated_at=g)`: below the shipped confidence gate
(`relax`, 0.60), `unrelated` is still accepted when it is the top option at probability >= g.
Shipped is `None`. Only the shipped question is asked; every gate is applied in code to the
same answers, so one call per case decides every gate.

- `free` derives the gate on every recorded `facts` answer of `benches/graph.jsonl` and
  `graph-c.jsonl` (50 cases, two recordings of jev-1.13.0: the original fixtures and the
  2026-10-15 re-run), by the rule below, and shows it on `graph-e.jsonl` (the fifth batch,
  30 cases, both recordings). Free, descriptive: graph-e is where 0.5 already failed to help.
- `paid` asks the shipped question once per case of the constructed batch
  (`benchmarks/facts_gate/cases.jsonl`, labels by construction), recorded in
  `fixtures/facts-gate/recording.jsonl`, and `report` applies the sealed rule to it.

Derivation rule: among `GATES`, the gate whose added `unrelated` verdicts (cases the shipped
policy leaves undecided) maximise right - 4 x wrong, which is positive exactly when they are
right at least 80 % of the time; ties to the stricter gate; no gate if the best is <= 0.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import paid_once  # noqa: E402
from thresholds import wilson_lower  # noqa: E402

from sanchopanza import Thresholds  # noqa: E402
from sanchopanza.eval.bench import load_cases  # noqa: E402
from sanchopanza.points import entities  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-10-16-a5-unrelated"
PREREG = RESULTS / "prereg.md"
CASES = HERE / "cases.jsonl"
# One level below `fixtures/`, like the fifth batch: the analyses that read every
# `fixtures/*.jsonl` (option order, policy shape, the edge-facts canary) keep their sets.
FIXTURE = ROOT / "fixtures" / "facts-gate" / "recording.jsonl"
F = ROOT / "fixtures"
RECORDINGS = {
    "original": (
        F / "public-benches.jsonl",
        F / "fourth-batch.jsonl",
        F / "edge-fix.jsonl",
        F / "fifth-batch" / "recording.jsonl",
    ),
    "rerun-2026-10-15": (F / "jev114" / "l1-components-113r.jsonl",),
}
DERIVE_ON = ("graph", "graph-c")
SHOW_ON = ("graph-e",)
GATES = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
WRONG_WEIGHT = 4  # right - 4 x wrong > 0  <=>  precision > 0.80, the package's target
TARGET = 0.80
MIN_ADDED = 16  # 16 of 16 is the fewest added verdicts whose Wilson lower bound clears 0.80
MODEL = "jev-1.13.0"
COSTLY = {"agree", "conflict"}
GATE_UNDER_TEST = 0.65  # derived by `derive` on the recordings, written in prereg.md
CASES_SHA256 = "a219ba794172621e2877f8492df34bdd8b7391421215bed7cb8dc52e24039b53"
LOT = paid_once.Lot(
    name="a5-unrelated",
    prereg=PREREG,
    launcher=ROOT / "a5-unrelated-run.cmd",
    fixture=FIXTURE,
    model=MODEL,
    cap_usd=0.10,  # hard, in the ledger at ~/.cache/sanchopanza/a5-unrelated/ (fixed path)
    instrument=(
        "src",
        "benchmarks/paid_once.py",
        "benchmarks/facts_gate",
        "benchmarks/jev114/l4.py",
        "benchmarks/thresholds.py",
        "benches/graph.jsonl",
        "benches/graph-c.jsonl",
        "benches/graph-e.jsonl",
        *(str(p.relative_to(ROOT)).replace("\\", "/") for ps in RECORDINGS.values() for p in ps),
    ),
)


def entries(paths: tuple[pathlib.Path, ...]) -> list[dict[str, Any]]:
    out = []
    for path in paths:
        out += [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return out


def bench(names: tuple[str, ...]) -> list[dict[str, Any]]:
    paths = [ROOT / "benches" / f"{n}.jsonl" for n in names]
    return [c for c in load_cases(paths) if c["point"] == "facts"]


def query(case: dict[str, Any]) -> tuple[str, Any, Any]:
    i = case["input"]
    return ("facts", *entities.fact_questions(fact_a=i["fact_a"], fact_b=i["fact_b"]))


async def answered(
    cases: list[dict[str, Any]], decider: Any, tag: str, *, allow_missing: bool = False
) -> list[dict[str, Any]]:
    """One row per case: the label and the verdict of the shipped policy and of every gate.
    A case with no answer is refused, or with `allow_missing` (the sealed rule, after the
    launches are spent) undecided under every policy and flagged `unanswered`."""
    t = Thresholds()
    rows = []
    for c in cases:
        d = await decider.decide(*query(c))
        row = {"id": c["id"], "set": tag, "expected": c["expected"]}
        if d.failed or not d.answers:
            if not allow_missing:
                raise SystemExit(f"{tag}: {c['id']} has no recording")
            rows.append({**row, "unanswered": True, "shipped": None,
                         **{f"g{g:.2f}": None for g in GATES}})  # fmt: skip
            continue
        row["shipped"] = entities.decide_facts(d, t)[0]
        for g in GATES:
            row[f"g{g:.2f}"] = entities.decide_facts(d, t, unrelated_at=g)[0]
        rows.append(row)
    return rows


def added(rows: list[dict[str, Any]], gate: float) -> dict[str, Any]:
    """The verdicts `gate` adds to the shipped policy, and what they are worth."""
    new = [r for r in rows if r["shipped"] is None and r[f"g{gate:.2f}"] is not None]
    right = sum(r["expected"] == "unrelated" for r in new)
    return {
        "gate": gate,
        "added": len(new),
        "right": right,
        "wrong": len(new) - right,
        "missed_conflicts": sum(r["expected"] == "conflict" for r in new),
        "net": right - WRONG_WEIGHT * (len(new) - right),
        "wilson95_low": wilson_lower(right, len(new)) if new else None,  # unrounded: compared
    }


def shipped(rows: list[dict[str, Any]]) -> dict[str, int]:
    decided = [r for r in rows if r["shipped"] is not None]
    return {
        "n": len(rows),
        "decided": len(decided),
        "right": sum(r["shipped"] == r["expected"] for r in decided),
        "costly": sum({r["shipped"], r["expected"]} == COSTLY for r in decided),
        "unrelated_read_as_agree": sum(
            r["expected"] == "unrelated" and r["shipped"] == "agree" for r in decided
        ),
    }


def derive(rows: list[dict[str, Any]]) -> float | None:
    scored = [added(rows, g) for g in GATES]
    best = max(scored, key=lambda s: (s["net"], s["gate"]))
    return best["gate"] if best["net"] > 0 else None


async def free() -> dict[str, Any]:
    derive_rows, show_rows = [], []
    for tag, paths in RECORDINGS.items():
        decider = RecordedDecider(entries(paths))
        derive_rows += await answered(bench(DERIVE_ON), decider, tag)
        show_rows += await answered(bench(SHOW_ON), decider, tag)
    gate = derive(derive_rows)
    return {
        "derived_gate": gate,
        "derivation": {
            "cases": "graph + graph-c, 50 cases x 2 recordings",
            "shipped": shipped(derive_rows),
            "gates": [added(derive_rows, g) for g in GATES],
        },
        "shown_on_fifth_batch": {
            "cases": "graph-e, 30 cases x 2 recordings",
            "shipped": shipped(show_rows),
            "gates": [added(show_rows, g) for g in GATES],
        },
    }


def verdict(rows: list[dict[str, Any]], gate: float | None) -> dict[str, Any]:
    """The sealed rule (prereg.md), on the constructed batch."""
    if gate is None:
        return {"gate": None, "verdict": "no gate derived: the shipped policy stands"}
    got = added(rows, gate)
    if got["added"] < MIN_ADDED:
        outcome = "undecided: too few cases in the band to reach the target"
    elif got["missed_conflicts"] == 0 and wilson_lower(got["right"], got["added"]) >= TARGET:
        outcome = "the gate beats the shipped policy"
    else:
        outcome = "the gate does not beat the shipped policy"
    return {**got, "verdict": outcome}


async def report(gate: float | None) -> dict[str, Any]:
    cases = load_cases([CASES])
    recorded = RecordedDecider.from_file(FIXTURE)
    missing = sum([not (await recorded.decide(*query(c))).answers for c in cases])
    if paid_once.unanswered_blocks(LOT, missing):
        raise SystemExit(f"{missing} cases unanswered and a launch is still allowed: relaunch")
    rows = await answered(cases, recorded, "constructed", allow_missing=True)
    by_shape = {
        s: shipped([r for r, c in zip(rows, cases, strict=True) if c["shape"] == s])
        for s in sorted({c["shape"] for c in cases})
    }
    return {
        "head": paid_once.head(),
        "gate_under_test": gate,
        "unanswered": sum(r.get("unanswered", False) for r in rows),
        "shipped": shipped(rows),
        "shipped_by_shape": by_shape,
        "gates": [added(rows, g) for g in GATES],
        "result": verdict(rows, gate),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("free", "dry", "seal", "paid", "report"))
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.action == "seal":
        print(paid_once.seal(LOT))
        return 0
    derived = asyncio.run(free())
    if args.action == "free":
        (RESULTS / "free.json").write_text(json.dumps(derived, indent=1) + "\n", "utf-8")
        print(json.dumps(derived, indent=1))
        return 0
    if derived["derived_gate"] != GATE_UNDER_TEST:
        raise SystemExit("the recordings no longer derive the registered gate: nothing done")
    paid_once.require_file(CASES, CASES_SHA256)
    if args.action == "report":
        result = asyncio.run(report(GATE_UNDER_TEST))
        (RESULTS / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
        print(json.dumps(result, indent=1))
        return 0
    asks = [query(c) for c in load_cases([CASES])]
    if args.action == "dry":
        plan = paid_once.plan(asks, LOT)
        print(json.dumps({"gate_under_test": GATE_UNDER_TEST, "head": paid_once.head(), **plan},
                         indent=1))  # fmt: skip
        return 0
    sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))
    import l4  # noqa: PLC0415  (jev114/l4.py: the key loader every lot uses)

    from sanchopanza.providers.jev import JevDecider

    result = paid_once.run_paid(
        LOT, asks, load_key=l4.load_key, make_live=lambda: JevDecider(model=MODEL)
    )
    print(json.dumps(result, indent=1))
    return 0 if result["stopped"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
