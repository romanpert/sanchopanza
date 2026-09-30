"""Single-issue tasks from SWE-bench Verified, seeded, disjoint from every instance the find runs
used (the retrieval run, its development sample and find e2e). Free.

Two strata: `general` (the "<15 min fix" and "15 min - 1 hour" issues, half each: does it make
the ordinary case worse?) and `hard` (the "1-4 hours" and ">4 hours" issues: long reading in a
large repository). Graded by the official SWE-bench harness (`run_swe.py` beside it).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "find"))

SEED = 20260930
PLAN = {  # stratum -> (difficulties, development, held out)
    "general-easy": (("<15 min fix",), 2, 10),
    "general-medium": (("15 min - 1 hour",), 2, 10),
    "hard": (("1-4 hours", ">4 hours"), 2, 6),
}


def used_by_find() -> set[str]:
    import ceiling
    import e2e
    import swebench

    used = {r["instance_id"] for r in swebench.instances()}
    used |= {r["instance_id"] for r in ceiling.dev_instances(set(used))}
    used |= {r["instance_id"] for r in e2e.sample()}
    return used


def select() -> list[dict[str, Any]]:
    import pyarrow.parquet as pq
    import swebench

    used = used_by_find()
    rows = sorted((r for r in pq.read_table(swebench.DATA / "verified.parquet").to_pylist()
                   if r["instance_id"] not in used), key=lambda r: r["instance_id"])  # fmt: skip
    rng = random.Random(SEED)
    out = []
    for stratum, (levels, dev, held) in PLAN.items():
        pool = [r for r in rows if r["difficulty"] in levels]
        picked = rng.sample(pool, dev + held)
        for i, row in enumerate(picked):
            out.append({"instance_id": row["instance_id"], "repo": row["repo"],
                        "difficulty": row["difficulty"], "stratum": stratum,
                        "split": "dev" if i < dev else "held"})  # fmt: skip
    return out


def main() -> int:
    chosen = select()
    (HERE / "singles-selected.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8",
                                                newline="\n")  # fmt: skip
    for row in chosen:
        print(row["split"], row["stratum"], row["instance_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
