"""The shipped touch (v4.1) on items of build_v4b.py, through `memory_hook.touch`, plus recall at
a session's first request from cached decider answers. Free once answers exist.

    python benchmarks/memory_real/replay_v4b.py [--items F] [--tag dev] [--cap 0.2]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from replay_v4 import event_for  # noqa: E402
from score import CACHE, OUT, decider_pass, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402


def touch_replay(items: list[dict[str, Any]], root: Path) -> tuple[dict[int, list[str]], int]:
    os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
    os.environ["SANCHOPANZA_MEMORY_STORE_LOG"] = str(root / "log.jsonl")
    os.environ.pop("SANCHOPANZA_MEMORY_SELECT", None)
    shown: dict[int, list[str]] = {}
    chars = 0
    saved: set[str] = set()
    for n in sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])):
        item = items[n]
        transcript = root / "projects" / f"g{item['group']}-{item['session'][:8]}" / "t.jsonl"
        store = mh.store_for({"transcript_path": str(transcript)})
        if item["session"] not in saved:
            ep.save(store, item["pool"], keep_days=10_000)
            saved.add(item["session"])
        mh.note_live(store, item["session"], 0, frozenset(range(1, item["index"])))
        out: list[str] = []
        for touch in item["touches"]:
            event = event_for(item, transcript, touch["tool"], touch["path"], touch["seen"])
            payload = mh.touch(event)
            if payload:
                text = payload["hookSpecificOutput"]["additionalContext"]
                chars += len(text)
                out.extend(e.key for e in item["pool"] if f"of session {e.session[:8]}" in text
                           and f"request {e.index} of" in text)  # fmt: skip
        shown[n] = list(dict.fromkeys(out))
    return shown, chars


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v4b.jsonl"))
    parser.add_argument("--tag", default="dev")
    parser.add_argument("--cap", type=float, default=0.2)
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    with tempfile.TemporaryDirectory() as tmp:
        touch, chars = touch_replay(items, Path(tmp))
    prompt = asyncio.run(decider_pass(items, args.cap, mh.KEEP_AT, 0, True))
    both = {n: list(dict.fromkeys([*touch[n], *prompt[n]])) for n in touch}
    results = {"v4.1 touch (hook code)": {**metrics(items, touch),
                                          "chars_per_request": round(chars / len(items))},
               "v4.1 shipped (touch + first-request prompt)": metrics(items, both)}
    for name, m in results.items():
        print(name.ljust(44), " | ".join(
            f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']}"
            for k in ("all/any", "all/lineage", "first/any")))
    print("touch characters per request", round(chars / len(items)))
    target = OUT / f"replay-v4b-{args.tag}.json"
    target.write_text(json.dumps(results, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
