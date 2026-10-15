"""The two parts of lot L1 that are not `benches/*.jsonl`: supersession and A9.

- **Supersession** (`memory_rules`, shipped since 2026-10-05): variant a of
  `benchmarks/memory_carry/supersede_bench.py`, the question `memory_rules` ships, on both
  labellers' benches (the first one's real cases come from the local store, as in its own run;
  without that store only its written, carry and stale cases are asked). Shipped rule: the
  likeliest newer option reaches `SUPERSEDED_AT` and beats `stands`; a failed or partial answer
  sends back (not suppressed), as in production.
- **A9**: the AgentDojo cases longer than one 2,000-character window, scanned two ways, both
  models: `windows` is `Squire.scan_content` without its keyword layer (windows of 2,000 with
  200 of overlap, at most `max_windows`, stop once one passes the cut, highest probability
  wins); `whole` is one call over the whole text. No long-context header: the longest text is
  about 7k tokens, under the default 32k per question.
"""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CARRY = ROOT / "benchmarks" / "memory_carry"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(CARRY))

from sanchopanza.contract import Decider  # noqa: E402
from sanchopanza.eval.bench import _bench_thresholds, load_cases  # noqa: E402
from sanchopanza.harness.memory_rules import SUPERSEDED_AT  # noqa: E402
from sanchopanza.journal import MemoryJournal  # noqa: E402
from sanchopanza.points import injection  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

FIRST = ROOT / "docs" / "results" / "2026-10-05-memory-supersede"
SECOND = ROOT / "docs" / "results" / "2026-10-05-memory-supersede-second"


def _squire(decider: Decider) -> Squire:
    t = _bench_thresholds(Thresholds()).with_(max_decisions=10_000, max_usd=100.0)
    return Squire(decider, thresholds=t, journal=MemoryJournal())


def _supersede_bench() -> types.ModuleType:
    import supersede_bench

    return supersede_bench


def supersede_cases() -> list[dict[str, Any]]:
    """Both labellers' labelled cases (ambiguous ones out), tagged by bench."""
    sb = _supersede_bench()
    try:
        first = sb.load_cases()
    except SystemExit:  # the private store is not on this machine: public cases only
        rows = [json.loads(x) for x in sb.BENCH.read_text(encoding="utf-8").splitlines()
                if x.strip()]  # fmt: skip
        first = [r for r in rows if not r.get("private")]
    from supersede_second_cases import CASES

    out = [{**c, "file": "supersede-1", "component": "supersede", "point": "supersede"}
           for c in first if c.get("label") in (0, 1)]  # fmt: skip
    out += [{**c, "file": "supersede-2", "component": "supersede", "point": "supersede",
             "split": "all"} for c in CASES]  # fmt: skip
    return out


def supersede_row(case: Mapping[str, Any], score: float | None,
                  stands: float | None) -> dict[str, Any]:  # fmt: skip
    suppressed = score is not None and stands is not None and score >= SUPERSEDED_AT \
        and score > stands  # fmt: skip
    label = int(case["label"])
    return {"id": case["id"], "point": "supersede", "expected": label, "score": score,
            "stands": stands, "predicted": suppressed, "decided": True,
            "correct": suppressed == (label == 1), "probability": score,
            "split": case.get("split"), "kind": case.get("kind") or case.get("family"),
            "provider": "jev"}  # fmt: skip


async def ask_supersede(case: Mapping[str, Any], decider: Decider) -> dict[str, Any]:
    sb = _supersede_bench()
    got = await sb.ask_case(_squire(decider), "a", case)
    return supersede_row(case, got.get("score"), got.get("stands"))


def supersede_historical() -> list[dict[str, Any]]:
    """The recorded 1.13 answers of both runs, scored by today's shipped rule."""
    rows = []
    for folder, name in ((FIRST, "supersede-1"), (SECOND, "supersede-2")):
        cases = {c["id"]: c for c in supersede_cases() if c["file"] == name}
        for line in (folder / "answers-a.jsonl").read_text(encoding="utf-8").splitlines():
            got = json.loads(line) if line.strip() else None
            if got and got["id"] in cases:
                row = supersede_row(cases[got["id"]], got.get("score"), got.get("stands"))
                rows.append({**row, "arm": "113rec", "file": name, "component": "supersede",
                             "calls": [{"answers": {"superseded": {}}}]})  # fmt: skip
    return rows


def a9_cases() -> list[dict[str, Any]]:
    cases = load_cases([ROOT / "benches" / "agentdojo-injection.jsonl"])
    return [{**c, "file": "agentdojo-injection", "component": "a9"}
            for c in cases if len(c["input"]["text"]) > injection.TEXT_LIMIT]  # fmt: skip


def _a9_row(case: Mapping[str, Any], best: float | None, asked: int, total: int,
            t: Thresholds) -> dict[str, Any]:  # fmt: skip
    flagged = best is not None and best > t.injection
    code = injection.code_signal(case["input"]["text"]) is not None
    return {"id": case["id"], "point": "injection", "expected": case["expected"],
            "probability": best, "predicted": flagged, "decided": best is not None,
            "correct": best is not None and flagged == case["expected"], "windows": asked,
            "windows_total": total, "keyword": code, "provider": "jev",
            "chars": len(case["input"]["text"])}  # fmt: skip


async def ask_a9_windows(case: Mapping[str, Any], decider: Decider) -> dict[str, Any]:
    squire = _squire(decider)
    t = squire.thresholds
    text, purpose = case["input"]["text"], case["input"].get("purpose", "")
    every = injection.windows(text, injection.TEXT_LIMIT)
    best: float | None = None
    asked = 0
    for chunk in every[: t.max_windows]:
        state, qs = injection.questions(purpose=purpose, text=chunk, limit=injection.TEXT_LIMIT)
        decision = await squire.decide("injection", state, qs)
        asked += 1
        p = decision.answer("injection").truth
        if decision.failed or p is None:
            continue
        best = p if best is None else max(best, p)
        if p > t.injection:
            break
    return _a9_row(case, best, asked, len(every), t)


async def ask_a9_whole(case: Mapping[str, Any], decider: Decider) -> dict[str, Any]:
    squire = _squire(decider)
    text, purpose = case["input"]["text"], case["input"].get("purpose", "")
    state, qs = injection.questions(purpose=purpose, text=text, limit=len(text) + 1)
    decision = await squire.decide("injection", state, qs)
    p = None if decision.failed else decision.answer("injection").truth
    return _a9_row(case, p, 1, 1, squire.thresholds)
