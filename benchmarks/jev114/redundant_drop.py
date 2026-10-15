"""redundant_page under Jev 1.14 with about 90 new `drop` cases in its derivation (lot
jev114-redundant-drop).

    python benchmarks/jev114/redundant_gen.py --check          # free: the cases are current
    python benchmarks/jev114/redundant_drop.py run --dry       # free: plan, bill
    python benchmarks/jev114/redundant_drop.py seal            # data.sha256, prereg.sha256
    python benchmarks/jev114/redundant_drop.py run --paid      # both versions, capped
    python benchmarks/jev114/redundant_drop.py rows            # free: fixtures -> rows
    python benchmarks/jev114/redundant_drop_analysis.py        # free: the verdict

Registered in docs/results/2026-10-16-redundant-drop/prereg.md.

THE CASES: the 125 of `benches/retrieval*.jsonl` (asked again, so every case of the lot comes
from one draw) and the 405 of `cases.jsonl`, rendered with labels by construction by
`redundant_gen.py`. Both go through `run_bench`, the path lot L1 asked them by, so a request is
byte for byte what the shipped squire sends.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for extra in ("src", "benchmarks"):
    sys.path.insert(0, str(ROOT / extra))
sys.path.insert(0, str(HERE))

import jev114_components as comp  # noqa: E402
import lot as lots  # noqa: E402
import redundant_gen  # noqa: E402

from sanchopanza.eval.bench import load_cases  # noqa: E402
from sanchopanza.points.triage import redundancy_questions  # noqa: E402
from sanchopanza.providers.capped import DEFAULT_PRICE_PER_MTOK, estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-16-redundant-drop"
CASES = OUT / "cases.jsonl"
DATA = OUT / "data.sha256"
RUN = Path(os.environ.get("SANCHOPANZA_JEV114_RUN", "C:/sp-runs/jev114")) / "redundant-drop"
OLD_FILES = ("retrieval", "retrieval-b", "retrieval-c")
EXPECTED = {"old": 125, "new": 405}
BATCH_CAP = 0.10

LOT = lots.Lot(
    name="jev114-redundant-drop",
    out=OUT,
    run=RUN,
    batch_cap=BATCH_CAP,
    fixture_stem="redundant-drop",
    sealed=(
        "docs/results/2026-10-16-redundant-drop/prereg.md",
        "docs/results/2026-10-16-redundant-drop/cases.jsonl",
        "benchmarks/jev114/redundant_gen.py",
        "benchmarks/jev114/redundant_scenarios.json",
        "benchmarks/jev114/redundant_drop.py",
        "benchmarks/jev114/redundant_drop_analysis.py",
        "benchmarks/jev114/lot.py",
        "benchmarks/jev114/l4_stats.py",
        "benchmarks/jev114/jev114_paired.py",
        "benchmarks/thresholds.py",
        "src/sanchopanza/points/triage.py",
        "src/sanchopanza/eval/bench.py",
        "src/sanchopanza/policy.py",
        "src/sanchopanza/providers/capped.py",
        "src/sanchopanza/providers/recorded.py",
    ),
)


def old_cases() -> list[dict[str, Any]]:
    out = []
    for name in OLD_FILES:
        for case in load_cases([ROOT / "benches" / f"{name}.jsonl"]):
            part = "cal" if name == "retrieval-c" else "ev"
            out.append({**case, "file": name, "half": part, "family": "bench"})
    return out


def new_cases() -> list[dict[str, Any]]:
    return [{**c, "file": "generated"} for c in load_cases([CASES])]


def cases() -> list[dict[str, Any]]:
    old, new = old_cases(), new_cases()
    if (len(old), len(new)) != (EXPECTED["old"], EXPECTED["new"]):
        raise SystemExit(f"{len(old)} old and {len(new)} new cases, registered {EXPECTED}")
    if new_cases() != [{**c, "file": "generated"} for c in redundant_gen.cases()]:
        raise SystemExit("cases.jsonl is not what redundant_gen.py writes: regenerate")
    return old + new


def cluster_of(case: Mapping[str, Any]) -> str:
    """Cases that share a `known` share a world: the resampling unit."""
    return hashlib.sha256(case["input"]["known"].encode("utf-8")).hexdigest()[:12]


def inputs_digest(all_cases: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for c in all_cases:
        body = [c["file"], c["id"], c["half"], c["input"], c["expected"]]
        h.update(json.dumps(body, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()


# --- asking: the bench path, as lot L1 -----------------------------------------------------


async def ask(case: Mapping[str, Any], decider: Any) -> tuple[Any, Any]:
    probe = comp.Probe(decider)
    return await comp.ask_bench(case, probe), probe


async def answered(case: Mapping[str, Any], arm: lots.Arm) -> bool:
    probe = comp.Probe(arm.recorded)
    await comp.ask_bench(case, probe)
    return bool(probe.calls) and all(c.get("answers") for c in probe.calls)


# --- the plan: free -------------------------------------------------------------------------


def l1_rate(old: list[dict[str, Any]]) -> dict[str, Any]:
    """USD per character of case input on lot L1's recordings of the 125 bench cases."""
    chars, usd, calls = 0, 0.0, 0
    for arm in lots.ARMS:
        model = lots.MODELS[arm] if arm == "14" else None
        replay = RecordedDecider.from_file(comp.fixture_for(arm), model=model)
        for case in old:
            probe = comp.Probe(replay)
            asyncio.run(comp.ask_bench(case, probe))
            for call in probe.calls:
                if call.get("answers"):
                    chars += len(json.dumps(case["input"], ensure_ascii=False))
                    usd += call.get("cost_usd") or 0.0
                    calls += 1
    return {"usd_per_char": usd / chars if chars else None, "calls": calls,
            "usd_per_call": usd / calls if calls else None, "source": "lot L1"}  # fmt: skip


def duplicates_of_old(new: list[dict[str, Any]], old: list[dict[str, Any]]) -> int:
    seen = {c["input"]["text"] for c in old} | {c["input"]["known"] for c in old}
    return sum(c["input"]["text"] in seen or c["input"]["known"] in seen for c in new)


def plan(all_cases: list[dict[str, Any]]) -> dict[str, Any]:
    old = [c for c in all_cases if c["file"] != "generated"]
    new = [c for c in all_cases if c["file"] == "generated"]
    rate = l1_rate(old)
    chars = sum(len(json.dumps(c["input"], ensure_ascii=False)) for c in all_cases)
    expected = 2 * chars * rate["usd_per_char"] if rate["usd_per_char"] else None
    pessimistic = 2 * sum(
        estimate_usd(*redundancy_questions(**c["input"]), price_per_mtok=DEFAULT_PRICE_PER_MTOK)
        for c in all_cases
    )
    by = Counter((c["half"], c["file"] if c["file"] != "generated" else "new", c["expected"])
                 for c in all_cases)  # fmt: skip
    problems = [(c["id"], p) for c in new for p in redundant_gen.problems(c)]
    return {
        "cases": len(all_cases),
        "by_half_source_label": {" ".join(k): n for k, n in sorted(by.items())},
        "new_drop_in_calibration": sum(c["half"] == "cal" and c["expected"] == "drop" for c in new),
        "families": dict(sorted(Counter(c["family"] for c in new).items())),
        "clusters": len({cluster_of(c) for c in all_cases}),
        "label_problems": problems,
        "new_duplicating_old": duplicates_of_old(new, old),
        "calls": 2 * len(all_cases),
        "jev_usd_expected": round(expected, 4) if expected is not None else None,
        "jev_usd_pessimistic": round(pessimistic, 4),
        "rate": rate,
        "claude_usd": 0.0,
        "batch_cap": LOT.batch_cap,
        "ledger": lots.ledger_room(LOT),
    }


def cmd_run(args: argparse.Namespace) -> int:
    if args.dry == args.paid:
        raise SystemExit("run: pass exactly one of --dry or --paid")
    all_cases = cases()
    if args.dry:
        report = plan(all_cases)
        print(json.dumps(report, indent=1, ensure_ascii=False))
        refused = lots.may_launch(LOT)
        print(f"dry: nothing asked. A paid launch now would be "
              f"{'refused: ' + refused if refused else 'allowed after the seal'}")  # fmt: skip
        return 4 if report["label_problems"] or report["new_duplicating_old"] else 0
    lots.require_seal(LOT)
    sealed = json.loads(DATA.read_text(encoding="utf-8"))
    if inputs_digest(all_cases) != sealed["cases"]:
        raise SystemExit("inputs differ from the sealed ones: nothing spent")
    return lots.paid_launch(LOT, lambda: asyncio.run(lots.run_cases(LOT, all_cases, ask, answered)))


def cmd_seal(_: argparse.Namespace) -> int:
    data = {"cases": inputs_digest(cases())}
    DATA.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    (OUT / "prereg.sha256").write_text(lots.digest(LOT) + "\n", encoding="utf-8")
    print(json.dumps(data), "prereg.sha256", lots.digest(LOT))
    return 0


ROWS = OUT / "drop-scored.jsonl"


async def rows_of(all_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arms = lots.arms_of(LOT, False, asyncio.Semaphore(LOT.gate))
    rows = []
    for case in all_cases:
        ps: dict[str, float | None] = {}
        for arm in lots.ARMS:
            result, probe = await ask(case, arms[arm])
            row = comp.row_dict(result, case, arm, probe)
            ok = probe.calls and all(c.get("answers") for c in probe.calls)
            ps[arm] = row.get("probability") if ok else None
        keep = {k: case[k] for k in ("id", "file", "half", "family", "expected")}
        rows.append(keep | {"scenario": case.get("scenario"), "cluster": cluster_of(case),
                            "p_13r": ps["13r"], "p_14": ps["14"]})  # fmt: skip
    return rows


def cmd_rows(_: argparse.Namespace) -> int:
    rows = asyncio.run(rows_of(cases()))
    ROWS.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"{len(rows)} rows -> {ROWS.relative_to(ROOT).as_posix()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("run", cmd_run), ("seal", cmd_seal), ("rows", cmd_rows)):
        p = sub.add_parser(name)
        if name == "run":
            p.add_argument("--dry", action="store_true")
            p.add_argument("--paid", action="store_true")
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
