"""Offline, from the recorded answers only: which blocking rule keeps the breaks and drops the
false alarms? Each pair (related: the scene's own rule; unrelated: another scene's) has the Truth
`kept` probability and the Choice `relation` P(breaks); a rule is a function of both.

    python benchmarks/memory_carry/rule_check_combine.py RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rule_check_eval as rc  # noqa: E402

RULES = {
    "kept<0.5 and unrelated<0.5": lambda k, b, u: k < 0.5 and u < 0.5,
    "kept<0.5 and unrelated<0.3": lambda k, b, u: k < 0.5 and u < 0.3,
    "kept<0.5 and unrelated<0.2": lambda k, b, u: k < 0.5 and u < 0.2,
    "kept<0.35 and unrelated<0.5": lambda k, b, u: k < 0.35 and u < 0.5,
    "kept<0.5": lambda k, b, u: k < 0.5,
    "kept<0.35": lambda k, b, u: k < 0.35,
    "kept<0.25": lambda k, b, u: k < 0.25,
    "breaks>=0.5": lambda k, b, u: b >= 0.5,
    "kept<0.5 and breaks>=0.5": lambda k, b, u: k < 0.5 and b >= 0.5,
    "kept<0.5 and breaks>=0.3": lambda k, b, u: k < 0.5 and b >= 0.3,
    "kept<0.4 and breaks>=0.4": lambda k, b, u: k < 0.4 and b >= 0.4,
    "mean<0.5": lambda k, b, u: (k + (1 - b)) / 2 < 0.5,
}


def scored(runs: list[Path], unrelated: bool) -> list[tuple[bool, float, float]]:
    truth = rc.cases(runs, unrelated=unrelated)
    choice = rc.cases(runs, unrelated=unrelated, relation=True)
    if unrelated:
        truth, choice = truth[::3], choice[::3]
    asyncio.run(rc.answer(truth, live=False))
    asyncio.run(rc.answer(choice, live=False))
    return [(t["kept"], t["p"], 1 - c["p"], c["probs"].get("unrelated", 0.0))
            for t, c in zip(truth, choice, strict=True)
            if t.get("p") is not None and c.get("p") is not None]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    runs = [Path(r) for r in (argv or sys.argv[1:])]
    related, unrelated = scored(runs, False), scored(runs, True)
    broken = [r for r in related if not r[0]]
    kept = [r for r in related if r[0]]
    print(f"related: {len(broken)} broken, {len(kept)} kept; unrelated: {len(unrelated)}")
    print(f"{'rule':28s} {'caught':>7s} {'false (related)':>16s} {'false (unrelated)':>18s}")
    for name, rule in RULES.items():
        caught = sum(rule(k, b, u) for _, k, b, u in broken)
        false_related = sum(rule(k, b, u) for _, k, b, u in kept)
        false_unrelated = sum(rule(k, b, u) for _, k, b, u in unrelated)
        print(f"{name:28s} {caught:>3d}/{len(broken):<3d} {false_related:>8d}/{len(kept):<7d}"
              f" {false_unrelated:>9d}/{len(unrelated)}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
