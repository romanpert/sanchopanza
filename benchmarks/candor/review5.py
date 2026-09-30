"""Round 5's review tier (prereg-5.md): the rules' report plus the frontier's answers (Jev).

    CANDOR_ROUND=5 python benchmarks/candor/review5.py            # replay only
    CANDOR_ROUND=5 python benchmarks/candor/review5.py --live     # Jev, capped (rounds.CAPS)

Every item of the round (natural sessions and counterfactuals) goes through `candor.check` on
the report with its status block and the hook's snapshot, then through `candor.frontier` with
one Jev call per item that has a doubt. The lock is the rules' critical findings only; the
review tier is any `high` or `critical`, the frontier's included. Answers are recorded in
`review-answers-5.jsonl` (hashed keys, no text) and replay free.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import monitors  # noqa: E402
import rounds  # noqa: E402

from sanchopanza.candor import should_lock  # noqa: E402
from sanchopanza.candor.frontier import frontier  # noqa: E402
from sanchopanza.candor.rules import check  # noqa: E402

ANSWERS = rounds.path("review-answers.jsonl")
SCORED = rounds.path("review.jsonl")


class _Squire:
    """`monitors.Asker` behind what `candor.frontier` calls; an unrecorded answer adds nothing."""

    def __init__(self, asker: monitors.Asker) -> None:
        self.asker = asker

    async def decide(self, point: str, state: Any, questions: dict[str, Any]) -> Any:
        decision = await self.asker.ask(point, state, questions)
        if decision is None:
            raise LookupError("no recorded answer")
        return decision

    def record(self, *_args: Any, **_kwargs: Any) -> None:
        return None


async def _one(item: dict[str, Any], squire: _Squire) -> dict[str, Any]:
    turn = monitors.turn_of(item, block=True, snapshot=True)
    base = check(turn)
    try:
        report = await frontier(squire, turn, base)
    except LookupError:
        report = base  # not asked (replay without an answer): the rules alone
    found = [f.to_dict() for f in report.findings]
    added = sorted({f["rule"] for f in found if f.get("origin") == "model"})
    return {k: item[k] for k in ("id", "set", "kind", "positive", "model", "task")} | {
        "lock": should_lock([f.to_dict() for f in base.findings]),
        "review": should_lock(found, on="high"),
        "rules": sorted({f["rule"] for f in found}),
        "frontier_added": added,
    }


async def run(live: bool, cap: float) -> list[dict[str, Any]]:
    decider = None
    if live:
        from sanchopanza.providers import create

        decider = create("jev", api_key=os.environ["TYPESAFE_API_KEY"])
    asker = monitors.Asker("jev", decider, monitors.Store(ANSWERS), cap, live)
    squire = _Squire(asker)
    rows = await asyncio.gather(*(_one(i, squire) for i in monitors.items()))
    sys.stderr.write(f"Jev spent {asker.spent:.4f} USD (cap {cap})\n")
    return list(rows)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="review5.py")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cap", type=float, default=0.10)
    args = parser.parse_args(argv)
    rows = asyncio.run(run(args.live, rounds.cap("jev_review", args.cap)))
    SCORED.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    sys.stdout.write(f"{len(rows)} items, {sum(r['review'] for r in rows)} in review\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
