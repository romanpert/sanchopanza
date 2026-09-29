"""v4 of the rules on rounds 1-3, in sample: every v4 change was shaped on round-3 data, so these
numbers are not a result, only the check that v4 does what it was built for and what it costs.

    python benchmarks/candor/explore_v4.py       # free, from the recordings (raw runs are local)

For each round it scores the stored v1/v2/v3 lock (`scored*.jsonl`, `rules_block.critical`)
against v4 on the same items, without and with the snapshot the hook took in every session.
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
OUT = HERE.parents[1] / "docs" / "results" / "2026-09-29-candor"


def one_round(name: str) -> dict[str, Any]:
    os.environ["CANDOR_ROUND"] = name
    import rounds

    importlib.reload(rounds)
    import monitors

    importlib.reload(monitors)
    stored = {
        json.loads(x)["id"]: json.loads(x)
        for x in rounds.path("scored.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    }
    every = monitors.items()
    every += monitors.adversarial(every)
    groups: dict[str, dict[str, list[int]]] = {}
    changed_items = []
    for item in every:
        if item["id"] not in stored:
            continue
        s = stored[item["id"]]
        v4 = monitors.rules_arm(item, block=True)["critical"]
        v4s = monitors.rules_arm(item, block=True, snapshot=True)["critical"]
        was = bool(s["rules_block"]["critical"])
        group = f"{s['set']}:{'pos' if s['positive'] else 'neg'}"
        cell = groups.setdefault(group, {"n": [0], "stored": [0], "v4": [0], "v4_snapshot": [0]})
        cell["n"][0] += 1
        cell["stored"][0] += was
        cell["v4"][0] += v4
        cell["v4_snapshot"][0] += v4s
        if v4 != was or v4s != was:
            changed_items.append({"id": item["id"], "positive": s["positive"], "stored": was,
                                  "v4": v4, "v4_snapshot": v4s})  # fmt: skip
    table = {g: {k: v[0] for k, v in c.items()} for g, c in sorted(groups.items())}
    return {"table": table, "changed": changed_items}


def main() -> int:
    out = {r: one_round(r) for r in ("1", "2", "3")}
    (OUT / "explore-v4.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for r, v in out.items():
        print(f"== round {r}")
        for g, c in v["table"].items():
            print(f"  {g:22s} {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
