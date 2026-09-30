"""The whole rule policy, today's code, against what each round recorded. Free.

    python benchmarks/candor/policy_replay.py

For rounds 4 and 5, every item (natural and counterfactual) is checked again with the rules, the
status block and the snapshot (`monitors.rules_arm(..., snapshot=True)`), and set beside the
lock the round recorded (`scored-N.jsonl`, `rules_block_snap`). Prints every item whose lock
changed, and the lock counts on misreports and honest reports, before and now.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def replay(round_name: str) -> dict[str, Any]:
    os.environ["CANDOR_ROUND"] = round_name
    import monitors
    import rounds

    importlib.reload(rounds)
    importlib.reload(monitors)
    scored_path = rounds.path("scored.jsonl")
    recorded = {}
    for line in scored_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            snap = row.get("rules_block_snap")
            if snap is not None:
                recorded[row["id"]] = snap
    counts = {"before": {"tp": 0, "fp": 0}, "now": {"tp": 0, "fp": 0}}
    changed = []
    items = monitors.items()
    for item in items:
        if item["id"] not in recorded:
            continue
        now = monitors.rules_arm(item, block=True, snapshot=True)
        before = recorded[item["id"]]
        key = "tp" if item["positive"] else "fp"
        counts["before"][key] += bool(before["critical"])
        counts["now"][key] += bool(now["critical"])
        if bool(before["critical"]) != bool(now["critical"]):
            changed.append({"id": item["id"], "positive": item["positive"],
                            "before": before["rules"], "now": now["rules"]})  # fmt: skip
    return {"round": round_name, "items": len(recorded),
            "positives": sum(1 for i in items if i["id"] in recorded and i["positive"]),
            "counts": counts, "lock_changed": changed}  # fmt: skip


def main() -> int:
    for name in ("4", "5"):
        print(json.dumps(replay(name), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
