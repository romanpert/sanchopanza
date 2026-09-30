"""Variants of the memory selectors on development items, from cached decider answers. Free."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score import decider_pass, load_items, metrics, touch_pass  # noqa: E402

EDITS = ("Edit", "MultiEdit", "Write", "NotebookEdit")


def show(name, items, shown):
    m = metrics(items, shown)
    row = {k: m[k] for k in ("all/any", "all/lineage", "first/any")}
    print(name.ljust(34), " | ".join(
        f"{k}: R {v['recall']} P {v['precision']} N {v['noise']} S {v['shown_per_request']}"
        for k, v in row.items()))
    return m


def union(a, b):
    return {n: list(dict.fromkeys([*a[n], *b[n]])) for n in a}


def main():
    items = load_items("dev")
    out = {}
    touch = {}
    for per_file in (1, 2, 3):
        for tools, tname in ((None, "read+edit"), (EDITS, "edit")):
            kw = {"per_file": per_file} | ({"tools": tools} if tools else {})
            shown, _ = touch_pass(items, **kw)
            touch[(per_file, tname)] = shown
            out[f"touch {tname} x{per_file}"] = show(f"touch {tname} x{per_file}", items, shown)
    for keep_at, min_chars, first in ((0.2, 0, False), (0.5, 40, False), (0.7, 40, False),
                                      (0.5, 40, True), (0.7, 0, True)):
        shown = asyncio.run(decider_pass(items, 0.0001, keep_at, min_chars, first))
        name = f"decider >={keep_at} len>={min_chars}{' first' if first else ''}"
        out[name] = show(name, items, shown)
        both = union(touch[(2, "read+edit")], shown)
        out["touch x2 + " + name] = show("touch x2 + " + name, items, both)
    Path(__file__).resolve().parents[2].joinpath(
        "docs/results/2026-10-01-memory-real/variants-dev.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
