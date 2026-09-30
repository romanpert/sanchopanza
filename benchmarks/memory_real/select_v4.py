"""A fresh held-out set for v4: every eligible SWE-chat group not in selection.json. Free.

    python benchmarks/memory_real/select_v4.py      # writes OUT/selection-2.json (ids only)

Same eligibility and window as build.select (one person on one repository, at least three
Claude Code sessions with a transcript, up to WINDOW consecutive sessions from a seeded random
start); none of these groups was built, read or scored before.
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build  # noqa: E402

SEED = 20261002
SELECTION_2 = build.OUT / "selection-2.json"


def main() -> int:
    names = set(json.loads((build.CACHE / "names.json").read_text(encoding="utf-8")))
    used = {s for g in json.loads(build.SELECTION.read_text(encoding="utf-8"))["groups"]
            for s in g["sessions"]}  # fmt: skip
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in build.sessions_table():
        if (r["agent"] in build.AGENTS and r["created_at"] is not None and r["repo_id"]
                and r["user_id"] and f"{r['session_id']}.jsonl" in names):  # fmt: skip
            groups[(r["repo_id"], r["user_id"])].append(r)
    fresh = sorted(k for k, v in groups.items()
                   if len(v) >= 3 and not used & {r["session_id"] for r in v})  # fmt: skip
    rng = random.Random(SEED)
    chosen = []
    for n, key in enumerate(fresh):
        rows = sorted(groups[key], key=lambda r: r["created_at"])
        width = min(build.WINDOW, len(rows))
        start = rng.randrange(0, len(rows) - width + 1)
        chosen.append({"group": 100 + n, "split": "held2", "repo_id": key[0],
                       "sessions": [r["session_id"] for r in rows[start:start + width]],
                       })  # fmt: skip
    payload = {"source": build.DATASET, "seed": SEED, "groups": chosen}
    SELECTION_2.write_text(json.dumps(payload, indent=1), encoding="utf-8", newline="\n")
    print(f"{len(chosen)} fresh groups, {sum(len(g['sessions']) for g in chosen)} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
