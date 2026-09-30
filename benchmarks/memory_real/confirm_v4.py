"""Amendment 2: v4 against v3 on the fresh held-out set (selection-2.json). Run once.

    python benchmarks/memory_real/confirm_v4.py --cap 0.5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
from build_v4b import items_for  # noqa: E402
from replay_v4b import touch_replay  # noqa: E402
from score import OUT, decider_pass, metrics  # noqa: E402
from variants_v4b import Rule, run  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402

ITEMS = build.CACHE / "items-v4b-held2.jsonl"


def build_items() -> list[dict[str, Any]]:
    selection = json.loads((build.OUT / "selection-2.json").read_text(encoding="utf-8"))
    rows = []
    with ITEMS.open("w", encoding="utf-8", newline="\n") as handle:
        for g in selection["groups"]:
            for item in items_for(g["sessions"], g["group"], g["split"]):
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                if item["pool"]:
                    rows.append({**item, "pool": [ep.Episode.from_dict(d) for d in item["pool"]]})
    return rows


def union(a: dict[int, list[str]], b: dict[int, list[str]]) -> dict[int, list[str]]:
    return {n: list(dict.fromkeys([*a[n], *b[n]])) for n in a}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap", type=float, default=0.5)
    args = parser.parse_args(argv)
    items = build_items()
    with tempfile.TemporaryDirectory() as tmp:
        v4_touch, _ = touch_replay(items, Path(tmp))
    v3_touch, _ = run(items, Rule("v3", newest_k=2))
    v4 = union(v4_touch, asyncio.run(decider_pass(items, args.cap, 0.8, 0, True)))
    v3 = union(v3_touch, asyncio.run(decider_pass(items, args.cap, 0.7, 0, True)))
    rows = {"v4 shipped": metrics(items, v4), "v3 shipped": metrics(items, v3),
            "v4 touch": metrics(items, v4_touch), "v3 touch": metrics(items, v3_touch)}
    a, b = rows["v4 shipped"]["all/any"], rows["v3 shipped"]["all/any"]
    verdicts = {
        "1 precision above v3": a["precision"] > b["precision"],
        "2 recall within 0.01 of v3": a["recall"] >= b["recall"] - 0.01,
        "3 noise not above v3": a["noise"] <= b["noise"],
        "4 recall >= 0.80 and precision >= 0.50": a["recall"] >= 0.80 and a["precision"] >= 0.50,
        "5 noise <= 0.10": a["noise"] <= 0.10,
    }
    for name, m in rows.items():
        print(name.ljust(12), " | ".join(
            f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']}"
            for k in ("all/any", "all/lineage", "first/any")))
    print(json.dumps(verdicts, indent=1))
    out = {"requests": len(items), "rows": rows, "verdicts": verdicts}
    (OUT / "confirm-v4.json").write_text(json.dumps(out, indent=1), encoding="utf-8",
                                         newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
