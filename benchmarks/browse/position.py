"""Browse: `asks_for_position` on hand-labelled goals the rule was not written on.

python benchmarks/browse/position.py OUT.json   # with the sanchopanza to test on sys.path

`position_heldout.jsonl` (30 goals, sealed in 2e2cf73 before the rule changed): does the answer
depend on the order the page lists things? Prints and writes precision and recall of the rule
and the goals it gets wrong. Free: no model.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
HELD_OUT = HERE / "position_heldout.jsonl"


def main(out: str) -> int:
    from sanchopanza.harness.browse_hook import asks_for_position

    goals = [json.loads(x) for x in HELD_OUT.read_text(encoding="utf-8").splitlines() if x]
    said = [asks_for_position("Task: " + g["goal"]) for g in goals]
    hits = sum(s and g["position"] for s, g in zip(said, goals, strict=True))
    report = {
        "goals": len(goals),
        "precision": round(hits / max(1, sum(said)), 3),
        "recall": round(hits / max(1, sum(g["position"] for g in goals)), 3),
        "false_positives": [g["goal"] for s, g in zip(said, goals, strict=True)
                            if s and not g["position"]],
        "missed": [g["goal"] for s, g in zip(said, goals, strict=True) if g["position"] and not s],
    }  # fmt: skip
    pathlib.Path(out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]) if len(sys.argv) == 2 else __doc__)
