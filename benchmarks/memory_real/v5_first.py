"""v5, item 1: what recall at a session's first request adds to the v4.1 touch, and at what
noise, for several conditions. Free: the touch replayed through the hook's code and the
decider's answers read from the cache only (a missing answer stops the run; nothing is called).

    python benchmarks/memory_real/v5_first.py --items CACHE/items-v4b.jsonl --tag dev
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from replay_v4b import touch_replay  # noqa: E402
from score import CACHE, OUT, _answers, _key, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

Cond = Callable[[dict[str, Any], ep.Episode, float | None], bool]
def named(item: dict[str, Any], e: ep.Episode) -> bool:
    """The product's gate (`memory_hook.gate_passes`), on the item's request."""
    return mh.gate_passes(item["request"], e)


def prompt_pass(items: list[dict[str, Any]], keep: Cond) -> dict[int, list[str]]:
    cached = _answers()
    shown: dict[int, list[str]] = {}
    for n, item in enumerate(items):
        found = mh.candidates(item["request"], item["pool"], mh.K) if item["first"] else []
        if not found:
            shown[n] = []
            continue
        key = _key(item["request"], [e.key for e in found])
        if key not in cached:
            raise SystemExit(f"no cached answer for item {n}: this script never calls the decider")
        p = cached[key]
        kept = sorted((e for e in found if keep(item, e, p.get(e.key))),
                      key=lambda e: -(p.get(e.key) or 0))  # fmt: skip
        shown[n] = mh.render(kept)[1]
    return shown


def at(cut: float) -> Cond:
    return lambda item, e, p: p is not None and p >= cut


def longer(cut: float, chars: int) -> Cond:
    return lambda item, e, p: len(item["request"]) >= chars and p is not None and p >= cut


VARIANTS: dict[str, Cond | None] = {
    "touch only": None,
    "+ decider 0.8 (v4.1 shipped)": at(0.8),
    "+ decider 0.9": at(0.9),
    "+ decider 0.95": at(0.95),
    "+ decider 0.8, prompt >= 80 chars": longer(0.8, 80),
    "+ decider 0.8, prompt >= 200 chars": longer(0.8, 200),
    "+ names a changed file (no model)": lambda item, e, p: named(item, e),
    "+ decider 0.8 and names a changed file": lambda item, e, p: named(item, e) and at(0.8)(
        item, e, p),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v4b.jsonl"))
    parser.add_argument("--tag", default="dev")
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    with tempfile.TemporaryDirectory() as tmp:
        touch, _ = touch_replay(items, Path(tmp))
    rows = {}
    for name, cond in VARIANTS.items():
        extra = prompt_pass(items, cond) if cond else {n: [] for n in touch}
        both = {n: list(dict.fromkeys([*touch[n], *extra[n]])) for n in touch}
        rows[name] = metrics(items, both)
        rows[name]["prompt_records"] = sum(len(v) for v in extra.values())
    for name, m in rows.items():
        print(name.ljust(40), f"+{m['prompt_records']:>3}", " | ".join(
            f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']}"
            for k in ("all/any", "all/lineage", "first/any")))
    target = OUT / f"v5-first-{args.tag}.json"
    target.write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
