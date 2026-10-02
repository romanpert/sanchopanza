"""Browse, development: does Jev tell a request for an element by its place better than the rule?

python benchmarks/browse/position_jev.py OUT.json                          # free: the recording
python benchmarks/browse/position_jev.py OUT.json --live --env-file PATH   # new calls, <= 0.10 USD

One Truth question per goal of the three hand-labelled sets (`position_heldout*.jsonl`). All
three are development data now: the first two shaped the rule (d2a6fda, da4711d), and the third
(sealed in d69ce09) was read after the rule scored 0.30 / 0.20 on it. A design chosen here is
confirmed on goals sealed before it is measured. Calls are recorded in
`fixtures/browse-jev-position.jsonl`; a call already there is replayed, so only new questions
cost anything.
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

from sanchopanza.contract import Truth  # noqa: E402
from sanchopanza.harness.browse_hook import (  # noqa: E402
    POSITION_CRITERIA,
    POSITION_INSTRUCTIONS,
    POSITION_POINT,
    asks_for_position,
)
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

SETS = sorted(HERE.glob("position_heldout*.jsonl"))
FIXTURE = ROOT / "fixtures" / "browse-jev-position.jsonl"
CEILING_USD = 0.10
POINT = POSITION_POINT
QUESTION = Truth(instructions=POSITION_INSTRUCTIONS, criteria=POSITION_CRITERIA)  # the hook's


def spent() -> float:
    if not FIXTURE.exists():
        return 0.0
    rows = FIXTURE.read_text(encoding="utf-8").splitlines()
    return sum(float(json.loads(x).get("cost_usd") or 0.0) for x in rows if x.strip())


def score(said: list[bool], goals: list[dict[str, Any]]) -> dict[str, Any]:
    hits = sum(s and g["position"] for s, g in zip(said, goals, strict=True))
    return {
        "precision": round(hits / max(1, sum(said)), 3),
        "recall": round(hits / max(1, sum(g["position"] for g in goals)), 3),
        "wrong": [g["goal"] for s, g in zip(said, goals, strict=True) if s != g["position"]],
    }


async def ask_all(goals: list[dict[str, Any]], live: Any) -> list[float | None]:
    recorded = RecordedDecider.from_file(FIXTURE)
    out: list[float | None] = []
    for g in goals:
        state = {"request": g["goal"]}
        decision = await recorded.decide(POINT, state, {"position": QUESTION})
        if not decision.answers and live is not None:
            if spent() >= CEILING_USD:
                raise SystemExit(f"Jev ceiling reached: {spent():.4f} of {CEILING_USD} USD")
            decision = await live.decide(POINT, state, {"position": QUESTION})
        answer = decision.answer("position")
        out.append(None if answer.empty else answer.truth)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--cut", type=float, default=0.5)
    args = ap.parse_args()
    live = None
    if args.live:
        sys.path.insert(0, str(HERE))
        from run import key_from

        live = RecordingDecider(create("jev", api_key=key_from(args.env_file)), FIXTURE)
    report: dict[str, Any] = {"cut": args.cut}
    sets = {p: [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
            for p in SETS}  # fmt: skip

    async def every_set() -> list[list[float | None]]:
        # one event loop: the live client keeps its connection from one set to the next
        return [await ask_all(goals, live) for goals in sets.values()]

    for (path, goals), truths in zip(sets.items(), asyncio.run(every_set()), strict=True):
        rule = [asks_for_position("Task: " + g["goal"]) for g in goals]
        jev = [t is not None and t >= args.cut for t in truths]
        backed = [r if t is None else t >= args.cut for r, t in zip(rule, truths, strict=True)]
        report[path.stem] = {
            "goals": len(goals),
            "unanswered": sum(t is None for t in truths),
            "rule": score(rule, goals),
            "jev": score(jev, goals),
            "jev_else_rule": score(backed, goals),
            "truths": [None if t is None else round(t, 3) for t in truths],
        }
    report["jev_usd_spent"] = round(spent(), 5)
    pathlib.Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {
                k: v
                if not isinstance(v, dict)
                else {
                    a: (b if not isinstance(b, dict) else {"p": b["precision"], "r": b["recall"]})
                    for a, b in v.items()
                    if a != "truths"
                }
                for k, v in report.items()
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
