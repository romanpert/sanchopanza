"""The pre-registered fourth question for `memory_write`, measured on a batch written first.

    python benchmarks/memory_common.py --offline   # replay, free
    python benchmarks/memory_common.py             # records what is missing (~0.02 USD)

PRE-REGISTERED, before any `common` answer existed (2026-09-25):

- Question: `points.memory.common_question`. Asked in the same call as the other three.
- Primary policy, P1: store iff `durable >= remember` and `derivable <= t.derivable` and
  `common < 0.5`. `common` REPLACES `specific`, whose side-effect filtering of general
  knowledge is the job `common` takes over. 0.5 is a plain cut, not a derived one.
- Secondary, P2: the shipped three gates plus `common < 0.5` (does `common` add anything
  while `specific` still gates?).
- Success, judged on `benches/memory-e.jsonl` ONLY (written before measuring; the earlier
  100 cases exposed the defect and are in-sample for the design): P1 must agree with more
  labels than the shipped policy AND make no more errors in the costly direction (storing
  what should be skipped). Anything else is a failure and is reported as one.
- P3, pre-registered after P1 passed and BEFORE `benches/memory-f.jsonl` was measured: P1
  plus a floor `specific >= 0.15`, for the vacuous pointers P1 stores. Success on memory-f
  only: P3 agrees with more of family E (pointers) than P1, loses none of family F
  (instructions) that P1 keeps, and makes no more costly errors than P1.
- Also reported: the shipped policy on the four-question call, because adding a question to
  a joint call moves the other answers (2026-09-24 tools bench, section 5).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.points import memory  # noqa: E402
from sanchopanza.policy import Thresholds, probability  # noqa: E402

OLD = ("memory.jsonl", "memory-b.jsonl", "memory-c.jsonl")
NEW = ("memory-e.jsonl",)
NEW2 = ("memory-f.jsonl",)
NEW3 = ("memory-g.jsonl",)
SPECIFIC_FLOOR = 0.15  # P3, pre-registered
SPECIFIC_FLOOR_P4 = 0.08  # P4, pre-registered after P3 failed; last iteration
FIXTURE = ROOT / "fixtures" / "memory-common.jsonl"
OUT = ROOT / "docs" / "results" / "2026-09-25-window"
MAX_RUN_USD = 0.10


def load(names: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = []
    for name in names:
        for line in (ROOT / "benches" / name).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                row = json.loads(line)
                if row["point"] == "memory_write":
                    rows.append(row)
    return rows


def decider(offline: bool) -> Any:
    from sanchopanza.providers import create
    from sanchopanza.providers.chain import FallbackDecider
    from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

    entries = []
    for f in sorted((ROOT / "fixtures").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append({**json.loads(line), "default": False})
    recorded = RecordedDecider(entries)
    if offline:
        return recorded
    live = RecordingDecider(create("jev", api_key=os.environ.get("TYPESAFE_API_KEY")), FIXTURE)
    return FallbackDecider([recorded, live])


def p(decision: Any, key: str) -> float | None:
    answer = decision.answer(key)
    return None if answer.empty else probability(answer)


def verdicts(three: Any, four: Any, t: Thresholds) -> dict[str, str | None]:
    """Each policy's verdict, from the raw answers. None when an answer it needs is missing."""
    shipped = memory.decide_write(three, t)
    shipped4 = memory.decide_write(four, t)
    # Through the shipped function, so what is published is what the package does.
    has = all(p(four, k) is not None for k in ("durable", "specific", "derivable", "common"))

    def common(floor: float) -> bool | None:
        return memory.decide_write_common(four, t, specific_floor=floor).store if has else None

    p1, p3, p4 = common(0.0), common(SPECIFIC_FLOOR), common(SPECIFIC_FLOOR_P4)
    c = p(four, "common")
    p2 = None if c is None else (shipped4.store and c < 0.5)
    word = {True: "store", False: "skip", None: None}
    return {
        "shipped": "store" if shipped.store else "skip",
        "shipped_on_4q": "store" if shipped4.store else "skip",
        "P1": word[p1],
        "P2": word[p2],
        "P3": word[p3],
        "P4": word[p4],
    }


async def run(offline: bool) -> list[dict[str, Any]]:
    dec = decider(offline)
    t = Thresholds()
    rows = []
    spent = 0.0
    for batch, cases in (
        ("old", load(OLD)),
        ("new", load(NEW)),
        ("new2", load(NEW2)),
        ("new3", load(NEW3)),
    ):
        for case in cases:
            fact = case["input"]["fact"]
            s3, q3 = memory.write_questions(fact=fact)
            s4, q4 = memory.write_questions(fact=fact, ask_common=True)
            three = await dec.decide("memory_write", s3, q3)
            four = await dec.decide("memory_write", s4, q4)
            spent += 0.0 if offline else three.cost_usd + four.cost_usd
            if spent > MAX_RUN_USD:
                raise SystemExit(f"passed {MAX_RUN_USD} USD; stopped")
            rows.append(
                {
                    "id": case["id"],
                    "batch": batch,
                    "family": _family(case["id"]),
                    "expected": case["expected"],
                    "answers": {
                        k: p(four, k) for k in ("durable", "specific", "derivable", "common")
                    },
                    **verdicts(three, four, t),
                }
            )
    return rows


def _family(case_id: str) -> str:
    n = int(case_id.split("-")[1])
    if 201 <= n <= 212:
        return "A instructions"
    if 213 <= n <= 224:
        return "B general knowledge"
    if 225 <= n <= 236:
        return "C findings"
    if 237 <= n <= 248:
        return "D transient"
    if 301 <= n <= 312:
        return "E pointers"
    if 313 <= n <= 324:
        return "F instructions"
    if 325 <= n <= 336:
        return "H verbatim of a held document"
    if 401 <= n <= 412:
        return "E2 pointers"
    if 413 <= n <= 424:
        return "F2 instructions"
    return "-"


def report(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| batch | policy | agree | stored what should be skipped (costly) | "
        "skipped what should be stored | no answer |",
        "|---|---|---|---|---|---|",
    ]
    for batch in ("new", "new2", "new3", "old"):
        sub = [r for r in rows if r["batch"] == batch]
        for pol in ("shipped", "shipped_on_4q", "P1", "P2", "P3", "P4"):
            ok = sum(r[pol] == r["expected"] for r in sub)
            costly = sum(r[pol] == "store" and r["expected"] == "skip" for r in sub)
            safe = sum(r[pol] == "skip" and r["expected"] == "store" for r in sub)
            none = sum(r[pol] is None for r in sub)
            lines.append(f"| {batch} ({len(sub)}) | {pol} | {ok} | {costly} | {safe} | {none} |")
    lines += [
        "",
        "New batches by family (agree / 12):",
        "",
        "| family | shipped | P1 | P2 | P3 | P4 |",
        "|---|---|---|---|---|---|",
    ]
    families = (
        "A instructions",
        "B general knowledge",
        "C findings",
        "D transient",
        "E pointers",
        "F instructions",
        "H verbatim of a held document",
        "E2 pointers",
        "F2 instructions",
    )
    for fam in families:
        sub = [r for r in rows if r["family"] == fam]
        cells = [
            str(sum(r[pol] == r["expected"] for r in sub))
            for pol in ("shipped", "P1", "P2", "P3", "P4")
        ]
        lines.append(f"| {fam} | " + " | ".join(cells) + " |")
    new = [r for r in rows if r["batch"] == "new"]

    def score(pol: str) -> tuple[int, int]:
        return (
            sum(r[pol] == r["expected"] for r in new),
            sum(r[pol] == "store" and r["expected"] == "skip" for r in new),
        )

    (s_ok, s_costly), (p_ok, p_costly) = score("shipped"), score("P1")
    verdict = "PASSES" if p_ok > s_ok and p_costly <= s_costly else "FAILS"
    lines += [
        "",
        f"Pre-registered criterion on the new batch: P1 {p_ok} vs shipped {s_ok} agreement, "
        f"costly errors {p_costly} vs {s_costly}: **{verdict}**.",
    ]
    f2 = [r for r in rows if r["batch"] == "new2"]

    def fam_ok(pol: str, fam: str) -> int:
        return sum(r[pol] == r["expected"] for r in f2 if r["family"] == fam)

    def kept(pol: str) -> set[str]:
        return {r["id"] for r in f2 if r["family"] == "F instructions" and r[pol] == "store"}

    def costly(pol: str) -> int:
        return sum(r[pol] == "store" and r["expected"] == "skip" for r in f2)

    ok3 = (
        fam_ok("P3", "E pointers") > fam_ok("P1", "E pointers")
        and kept("P1") <= kept("P3")
        and costly("P3") <= costly("P1")
    )
    lines.append(
        f"Pre-registered criterion for P3 on memory-f: pointers {fam_ok('P3', 'E pointers')} vs "
        f"{fam_ok('P1', 'E pointers')}, instructions kept {len(kept('P3'))} vs "
        f"{len(kept('P1'))}, costly {costly('P3')} vs {costly('P1')}: "
        f"**{'PASSES' if ok3 else 'FAILS'}**."
    )
    g = [r for r in rows if r["batch"] == "new3"]
    kept_g = {
        pol: {r["id"] for r in g if r["family"] == "F2 instructions" and r[pol] == "store"}
        for pol in ("P1", "P4")
    }
    ptr = {
        pol: sum(r[pol] == "store" for r in g if r["family"] == "E2 pointers")
        for pol in ("P1", "P4")
    }
    cst = {
        pol: sum(r[pol] == "store" and r["expected"] == "skip" for r in g) for pol in ("P1", "P4")
    }
    ok4 = kept_g["P1"] <= kept_g["P4"] and ptr["P4"] < ptr["P1"] and cst["P4"] <= cst["P1"]
    lines.append(
        f"Pre-registered criterion for P4 on memory-g: instructions kept {len(kept_g['P4'])} vs "
        f"{len(kept_g['P1'])}, pointers stored {ptr['P4']} vs {ptr['P1']}, costly {cst['P4']} "
        f"vs {cst['P1']}: **{'PASSES' if ok4 else 'FAILS'}**."
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    rows = asyncio.run(run(args.offline))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "memory-common.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    text = report(rows)
    (OUT / "memory-common.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
