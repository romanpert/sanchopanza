"""v5, item 1: when the decider gives a related record at a session's first request, would the
touch have given one too, and after how many file calls? The metric credits a record in view at
any point of the request; a record given at the prompt arrives before the agent looks. Free.

    python benchmarks/memory_real/v5_first_timing.py --items CACHE/items-v4b.jsonl
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from replay_v4 import event_for  # noqa: E402
from score import CACHE  # noqa: E402
from v5_first import VARIANTS, prompt_pass  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

RELATED = {"lineage", "file"}


def first_related_touch(items: list[dict[str, Any]], root: Path) -> dict[int, int | None]:
    """Per request, the position of the first file call whose touch gave a related record."""
    import os

    os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
    os.environ.pop("SANCHOPANZA_MEMORY_SELECT", None)
    out: dict[int, int | None] = {}
    saved: set[str] = set()
    for n in sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])):
        item = items[n]
        transcript = root / "projects" / f"g{item['group']}-{item['session'][:8]}" / "t.jsonl"
        store = mh.store_for({"transcript_path": str(transcript)})
        if item["session"] not in saved:
            ep.save(store, item["pool"], keep_days=10_000)
            saved.add(item["session"])
        mh.note_live(store, item["session"], 0, frozenset(range(1, item["index"])))
        out[n] = None
        for position, touch in enumerate(item["touches"]):
            payload = mh.touch(event_for(item, transcript, touch["tool"], touch["path"],
                                         touch["seen"]))  # fmt: skip
            text = payload["hookSpecificOutput"]["additionalContext"] if payload else ""
            if out[n] is None and any(
                item["labels"][e.key] in RELATED and f"of session {e.session[:8]}" in text
                and f"request {e.index} of" in text for e in item["pool"]
            ):  # fmt: skip
                out[n] = position
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v4b.jsonl"))
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    with tempfile.TemporaryDirectory() as tmp:
        when = first_related_touch(items, Path(tmp))
    prompt = prompt_pass(items, VARIANTS["+ decider 0.8 (v4.1 shipped)"])
    for n, keys in prompt.items():
        good = [k for k in keys if items[n]["labels"][k] in RELATED]
        if not keys:
            continue
        calls = len(items[n]["touches"])
        print(f"item {n}: prompt gave {len(keys)} ({len(good)} related); touch's first related "
              f"at file call {when[n]} of {calls}; request {len(items[n]['request'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
