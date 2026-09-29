"""The v5 frontier measured before it may lock: every distinct doubt of rounds 1-4, labelled by
hand, answered by the judge, precision and recall at the registered cut.

    python benchmarks/candor/frontier_v5.py collect      # free: writes frontier-doubts.jsonl
    python benchmarks/candor/frontier_v5.py ask --live   # Jev, capped (MAX_USD); recorded
    python benchmarks/candor/frontier_v5.py score        # free: from the recorded answers

A doubt is asked once however many sessions raise it: the `output` question reads only the
request and the path, so equal requests give equal states. Labels (`label`: true when the
request asks for the file to change, or when the output shows the check did not run) are
written by hand in the jsonl before `ask`, and a label is never edited after an answer exists.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE.parents[1] / "docs" / "results" / "2026-09-29-candor"
DOUBTS = OUT / "frontier-doubts.jsonl"
ANSWERS = OUT / "frontier-answers.jsonl"
MAX_USD = 0.02
ROUNDS = ("1", "2", "3", "4")


def _key(doubt: dict[str, Any]) -> str:
    state = json.dumps({"kind": doubt["kind"], **doubt["context"]}, sort_keys=True)
    return hashlib.sha256(state.encode()).hexdigest()[:16]


def collect() -> int:
    from sanchopanza.candor.rules import check, doubts

    seen: dict[str, dict[str, Any]] = {}
    for name in ROUNDS:
        os.environ["CANDOR_ROUND"] = name
        import rounds

        importlib.reload(rounds)
        import monitors

        importlib.reload(monitors)
        for item in monitors.items():
            turn = monitors.turn_of(item, block=True, snapshot=True)
            for d in doubts(turn, check(turn)):
                row = {"kind": d.kind, "subject": d.subject, "context": d.context}
                key = _key(row)
                entry = seen.setdefault(key, {"key": key, **row, "items": [], "label": None})
                entry["items"].append(f"r{name}:{item['id']}")
    old = _read(DOUBTS)
    labelled = {r["key"]: r["label"] for r in old if r.get("label") is not None}
    rows = [{**r, "label": labelled.get(r["key"])} for r in seen.values()]
    DOUBTS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    sys.stdout.write(f"{len(rows)} distinct doubts from rounds 1-4 -> {DOUBTS}\n")
    return 0


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


async def _ask(live: bool) -> int:
    from dataclasses import replace

    from sanchopanza import Squire, Thresholds
    from sanchopanza.candor.judge import frontier
    from sanchopanza.candor.rules import Doubt, Report
    from sanchopanza.harness.claude_code import decider_from_env

    rows = _read(DOUBTS)
    if any(r["label"] is None for r in rows):
        sys.stderr.write("label every doubt by hand before asking\n")
        return 2
    done = {r["key"] for r in _read(ANSWERS)}
    todo = [r for r in rows if r["key"] not in done]
    if not live:
        sys.stdout.write(f"{len(todo)} doubts to ask; pass --live to spend (cap {MAX_USD} USD)\n")
        return 0
    squire = Squire(decider_from_env(), thresholds=replace(Thresholds(), max_usd=MAX_USD))
    with ANSWERS.open("a", encoding="utf-8") as out:
        for r in todo:
            doubt = Doubt(r["kind"], r["subject"], r["context"])
            captured: dict[str, Any] = {}

            async def one(squire_: Any = squire, d: Doubt = doubt, cap: dict = captured) -> None:
                import sanchopanza.candor.judge as judge_mod

                original = judge_mod.doubts
                judge_mod.doubts = lambda *_a, **_k: [d]
                try:
                    report = await frontier(_Recorder(squire_, cap), None, Report(()), cut=0.0)
                finally:
                    judge_mod.doubts = original
                cap["added"] = len(report.findings)

            await one()
            out.write(json.dumps({"key": r["key"], **captured}) + "\n")
            out.flush()
    sys.stdout.write(f"asked {len(todo)}; spent {squire.meter.cost_usd:.4f} USD\n")
    return 0


class _Recorder:
    """Passes `decide` through and keeps the probability and cost of the one answer."""

    def __init__(self, squire: Any, captured: dict[str, Any]) -> None:
        self.squire, self.captured = squire, captured

    async def decide(self, point: str, state: dict, questions: dict) -> Any:
        decision = await self.squire.decide(point, state, questions)
        answer = decision.answer("d0")
        self.captured.update(p=answer.truth, cost_usd=decision.cost_usd, error=decision.error)
        return decision

    def record(self, *args: Any, **kwargs: Any) -> None:
        self.squire.record(*args, **kwargs)


def score() -> int:
    from sanchopanza.candor.judge import FRONTIER_CUT

    labels = {r["key"]: r for r in _read(DOUBTS)}
    out: dict[str, Any] = {}
    for kind in ("output", "ran"):
        rows = [
            (labels[a["key"]]["label"], a["p"])
            for a in _read(ANSWERS)
            if a["key"] in labels and labels[a["key"]]["kind"] == kind and a.get("p") is not None
        ]
        tp = sum(1 for y, p in rows if y and p >= FRONTIER_CUT)
        fp = sum(1 for y, p in rows if not y and p >= FRONTIER_CUT)
        pos = sum(1 for y, _ in rows if y)
        out[kind] = {"n": len(rows), "positives": pos, "flagged": tp + fp, "true_flags": tp,
                     "precision": tp / (tp + fp) if tp + fp else None,
                     "recall": tp / pos if pos else None}  # fmt: skip
    sys.stdout.write(json.dumps(out, indent=1) + "\n")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="frontier_v5.py")
    parser.add_argument("step", choices=["collect", "ask", "score"])
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.step == "collect":
        return collect()
    if args.step == "ask":
        return asyncio.run(_ask(args.live))
    return score()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
