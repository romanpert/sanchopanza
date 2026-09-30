"""How much of SWE-chat nobody has looked at: groups of two sessions, and sessions of the used
groups outside their windows. Counts only, ids only. Free.

    python benchmarks/memory_real/v5_unseen.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build  # noqa: E402
import select_v4  # noqa: E402


def main() -> int:
    names = set(json.loads((build.CACHE / "names.json").read_text(encoding="utf-8")))
    used: set[str] = set()
    for path in (build.SELECTION, select_v4.SELECTION_2):
        used |= {s for g in json.loads(path.read_text(encoding="utf-8"))["groups"]
                 for s in g["sessions"]}  # fmt: skip
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in build.sessions_table():
        if (r["agent"] in build.AGENTS and r["created_at"] is not None and r["repo_id"]
                and r["user_id"] and f"{r['session_id']}.jsonl" in names):  # fmt: skip
            groups[(r["repo_id"], r["user_id"])].append(r)
    two = [k for k, v in groups.items() if len(v) == 2]
    outside = {k: [r for r in v if r["session_id"] not in used]
               for k, v in groups.items() if used & {r["session_id"] for r in v}}  # fmt: skip
    runs = sum(1 for v in outside.values() if len(v) >= 2)
    print(f"groups with a transcript: {len(groups)}; used sessions: {len(used)}")
    print(f"groups of exactly two sessions: {len(two)}")
    print(f"used groups with >= 2 sessions outside their window: {runs}, "
          f"{sum(len(v) for v in outside.values() if len(v) >= 2)} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
