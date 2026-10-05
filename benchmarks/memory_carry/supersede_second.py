"""A second labeller's run of the F1 supersession variants (2026-10-05) on fresh cases
(`supersede_second_cases.py`), sealed in a commit before any call.

    python supersede_second.py plan            # free: counts the calls
    python supersede_second.py run --paid      # Jev only, hard cap CAP calls
    python supersede_second.py report          # free: the table and the pick

The variants' questions are imported from `supersede_bench.py` as they are (a: v8.2's Choice;
b: Truth on the request; d: the same Truth on each stored rule said since; b+d: the higher of
the two, any failure fails open; c: contradicts / refines / unrelated). The first labeller's
cases module is replaced by an empty stub before that import, so none of its cases is loaded.

Decision rule, fixed in the sealing commit before any call:
- Per variant, on all 48 cases, the cut is the lowest multiple of 0.05 that is >= 0.5 and at
  least 0.10 above every negative's score.
- A case is suppressed when its score is >= the cut. A failed answer, or (for d) no stored rule
  since, scores as not suppressed; in the AUC it counts as 0.0. Failures are reported.
- The variant picked is the one with the most true suppressions at its cut. Ties go to fewer
  calls per case (on these cases: a, b, c 1; d the stored rules since; b+d 1 + those), then to
  the simpler, in this order: b, d, c, a, b+d.
- If the picked variant suppresses fewer than 4 of the 16 positives, the recommendation is to
  ship none (no suppression, v8.1's behaviour).

Budget: Jev only; every decision is counted before it is asked and the run stops at CAP. The
ledger and answers live in OUT, outside the first labeller's results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# never load the first labeller's cases: the bench imports these four names at module level
_stub = types.ModuleType("supersede_cases")
_stub.CARRY_NOTES, _stub.REAL_PAIRS, _stub.REAL_SENDBACKS, _stub.WRITTEN = {}, [], [], []
sys.modules["supersede_cases"] = _stub

import supersede_bench as sb  # noqa: E402
from supersede_second_cases import CASES  # noqa: E402

CAP = 250
OUT = HERE.parent.parent / "docs" / "results" / "2026-10-05-memory-supersede-second"
LEDGER = OUT / "ledger.json"
ASKED = ("a", "b", "c", "d")
SCORED = ("a", "b", "d", "b+d", "c")
SIMPLER = ("b", "d", "c", "a", "b+d")
MIN_TP = 4
FLOOR = 0.5
MARGIN = 0.10
DANGER_AT = 0.75  # the shipped cut, for the "task would break it" count


def calls_for(case: Mapping[str, Any], variant: str) -> int:
    if variant == "b+d":
        return sb.calls_for(case, "b") + sb.calls_for(case, "d")
    return sb.calls_for(case, variant)


def _path(variant: str) -> Path:
    return OUT / f"answers-{variant}.jsonl"


def _rows(variant: str) -> dict[str, dict[str, Any]]:
    path = _path(variant)
    if not path.exists():
        return {}
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["id"]: r for r in rows}


def todo() -> list[tuple[str, dict[str, Any], int]]:
    out = []
    for v in ASKED:
        done = _rows(v)
        out += [(v, c, calls_for(c, v)) for c in CASES if c["id"] not in done]
    return out


def _ledger() -> dict[str, Any]:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"calls": 0, "usd": 0.0, "runs": []}


def plan(_: argparse.Namespace) -> int:
    work = todo()
    need = sum(n for _, _, n in work)
    used = int(_ledger()["calls"])
    print(f"planned {need} calls for {len(work)} case-variants; ledger {used} used, "
          f"{CAP - used} left of {CAP}")  # fmt: skip
    return 0


async def _run(work: list[tuple[str, dict[str, Any], int]], left: int) -> sb.Counted:
    from sanchopanza.harness.claude_code import squire_from_env

    sq = sb.Counted(squire_from_env(redact=True), left)
    gate = asyncio.Semaphore(6)
    OUT.mkdir(parents=True, exist_ok=True)

    async def one(variant: str, case: dict[str, Any]) -> None:
        async with gate:
            try:
                row = await sb.ask_case(sq, variant, case)
            except Exception as exc:  # noqa: BLE001 - recorded, scored as not suppressed
                row = {"id": case["id"], "variant": variant, "score": None,
                       "failed": f"{type(exc).__name__}: {exc}"[:200]}  # fmt: skip
        with _path(variant).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    await asyncio.gather(*(one(v, c) for v, c, n in work if n > 0))
    return sq


def run(args: argparse.Namespace) -> int:
    work = todo()
    need = sum(n for _, _, n in work)
    ledger = _ledger()
    left = CAP - int(ledger["calls"])
    print(f"planned {need} calls; {left} left of {CAP}")
    if not args.paid:
        return 0
    if need > left:
        print("refusing: the planned calls pass what is left of the cap")
        return 1
    if os.environ.get("SANCHOPANZA_PROVIDER") != "jev" or not os.environ.get("TYPESAFE_API_KEY"):
        print("refusing: needs SANCHOPANZA_PROVIDER=jev and TYPESAFE_API_KEY")
        return 1
    started = time.time()
    sq = asyncio.run(_run(work, need))
    LEDGER.write_text(json.dumps({
        "calls": int(ledger["calls"]) + sq.calls, "usd": round(ledger["usd"] + sq.usd, 6),
        "runs": [*ledger["runs"], {"at": started, "calls": sq.calls,
                                   "usd": round(sq.usd, 6)}]}, indent=1),
        encoding="utf-8")  # fmt: skip
    print(f"made {sq.calls} calls, {sq.usd:.6f} USD")
    return 0


# --- scoring ------------------------------------------------------------------------------------


def score(ans: Mapping[str, Mapping[str, dict]], variant: str, case: Mapping[str, Any],
          ) -> tuple[float | None, bool]:  # fmt: skip
    """(score, failed). None with failed False: nothing to ask (d with no stored rule since)."""
    cid = case["id"]
    if variant == "b+d":
        b, d = ans["b"].get(cid), ans["d"].get(cid)
        if b is None or b.get("failed") or (d is not None and d.get("failed")):
            return None, True
        vals = [x for x in (b.get("score"), (d or {}).get("score")) if x is not None]
        return (max(vals) if vals else None), False
    if variant == "d" and calls_for(case, "d") == 0:
        return None, False
    row = ans[variant].get(cid)
    if row is None or row.get("failed") or row.get("score") is None:
        return None, True
    return float(row["score"]), False


def cut_for(neg: Sequence[float]) -> float:
    need = max(FLOOR, (max(neg) if neg else 0.0) + MARGIN)
    return round(0.05 * math.ceil(round(need / 0.05, 9)), 2)


def auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def metrics(ans: Mapping[str, Mapping[str, dict]], variant: str) -> dict[str, Any]:
    pos, neg, danger, fails = [], [], [], 0
    for c in CASES:
        s, failed = score(ans, variant, c)
        fails += failed
        v = 0.0 if s is None else s
        (pos if c["label"] == 1 else neg).append(v)
        if c["kind"] == "neg-break":
            danger.append(v)
    cut = cut_for(neg)
    calls = sum(calls_for(c, variant) for c in CASES) / len(CASES)
    return {"variant": variant, "cut": cut, "tp": sum(p >= cut for p in pos), "pos": len(pos),
            "fp": sum(n >= cut for n in neg), "neg": len(neg), "auc": round(auc(pos, neg), 3),
            "max_neg": round(max(neg), 3), "min_pos": round(min(pos), 3), "failed": fails,
            "danger_at_075": sum(x >= DANGER_AT for x in danger),
            "tp_at_075": sum(p >= DANGER_AT for p in pos),
            "fp_at_075": sum(n >= DANGER_AT for n in neg),
            "calls_per_case": round(calls, 3)}  # fmt: skip


def pick(table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    best = sorted(table, key=lambda m: (-m["tp"], m["calls_per_case"],
                                        SIMPLER.index(m["variant"])))[0]  # fmt: skip
    if best["tp"] < MIN_TP:
        return {"pick": None, "why": f"best catches {best['tp']} < {MIN_TP}: ship none"}
    return {"pick": best["variant"], "cut": best["cut"], "tp": best["tp"]}


def report(_: argparse.Namespace) -> int:
    ans = {v: _rows(v) for v in ASKED}
    table = [metrics(ans, v) for v in SCORED]
    choice = pick(table)
    per_case = []
    for c in CASES:
        per_case.append({"id": c["id"], "label": c["label"], "kind": c["kind"],
                         **{v: score(ans, v, c)[0] for v in SCORED}})  # fmt: skip
    out = {"table": table, "choice": choice, "ledger": _ledger(), "cases": per_case}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for m in table:
        print(json.dumps(m))
    print(json.dumps(choice))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan").set_defaults(fn=plan)
    r = sub.add_parser("run")
    r.add_argument("--paid", action="store_true")
    r.set_defaults(fn=run)
    sub.add_parser("report").set_defaults(fn=report)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
