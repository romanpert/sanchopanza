"""v4 touch rules against v3 on development items of build_v4.py. Free.

    python benchmarks/memory_real/variants_v4.py [--split dev]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from score import CACHE, OUT, metrics  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402


def load(split: str) -> list[dict[str, Any]]:
    out = []
    for line in (CACHE / "items-v4.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["split"] == split and item["pool"]:
            out.append({**item, "pool": [ep.Episode.from_dict(d) for d in item["pool"]]})
    return out


def run(items: list[dict[str, Any]], rule: str, k: int = 2, least: int = 1,
        fallback: int = 0, edit_fallback: int = 0) -> tuple[dict[int, list[str]], int]:  # fmt: skip
    """rule `newest`: v3; `overlap`: records with >= `least` of their lines in view, most
    first, else the `fallback` newest. Once per session. Returns shown and characters given."""
    at = {e.key: e.at for i in items for e in i["pool"]}
    size = {e.key: len(e.text()) for i in items for e in i["pool"]}
    given: dict[str, set[str]] = {}
    shown: dict[int, list[str]] = {}
    chars = 0
    for n in sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])):
        item = items[n]
        seen = given.setdefault(item["session"], set())
        out: list[str] = []
        for tool, _, overlaps, *_ in item["touches"]:
            fresh = {key: c for key, c in overlaps.items() if key not in seen}
            if rule == "newest":
                pick = sorted(fresh, key=lambda key: -at[key])[:k]
            else:
                hits = [key for key, c in fresh.items() if c >= least]
                pick = sorted(hits, key=lambda key: (-fresh[key], -at[key]))[:k]
                if not pick and fallback:
                    pick = sorted(fresh, key=lambda key: -at[key])[:fallback]
                if not pick and edit_fallback and tool != "Read":
                    pick = sorted(fresh, key=lambda key: -at[key])[:edit_fallback]
            for key in pick:
                seen.add(key)
                out.append(key)
                chars += size[key]
        shown[n] = out
    return shown, chars


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=("dev", "held"))
    args = parser.parse_args(argv)
    items = load(args.split)
    rows = {}
    rules = [("v3 newest x2", "newest", {}),
             *[(f"v4 overlap>={m} x2", "overlap", {"least": m}) for m in (1, 2, 3)],
             *[(f"v4 overlap>={m} x2, else newest x1", "overlap", {"least": m, "fallback": 1})
               for m in (1, 2)],
             ("v4 overlap>=1 x1", "overlap", {"least": 1, "k": 1}),
             ("v4 overlap>=1 x2, edit else newest x1", "overlap", {"least": 1, "edit_fallback": 1}),
             ("v4 overlap>=2 x2, edit else newest x1", "overlap", {"least": 2, "edit_fallback": 1}),
             ("v4 overlap>=1 x1, edit else newest x1", "overlap",
              {"least": 1, "k": 1, "edit_fallback": 1})]  # fmt: skip
    for name, rule, kw in rules:
        shown, chars = run(items, rule, **kw)
        m = metrics(items, shown)
        rows[name] = {**m, "chars_per_request": round(chars / len(items))}
        print(name.ljust(36), " | ".join(
            f"{s}: R {m[s]['recall']} P {m[s]['precision']} N {m[s]['noise']}"
            for s in ("all/any", "all/lineage", "first/any")),
            f"| chars/req {round(chars / len(items))}")
    (OUT / f"variants-v4-{args.split}.json").write_text(json.dumps(rows, indent=1),
                                                       encoding="utf-8", newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
