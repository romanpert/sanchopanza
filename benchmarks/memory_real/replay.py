"""The shipped hook on development items, end to end through its own code: `memory_hook.touch`
on every file the agent opened or changed, with the state `UserPromptSubmit` leaves (the
session's earlier requests live), and the prompt-time recall at a session's first request from
the cached decider answers (score.decider_pass with the shipped cut). Free once answers exist.

    python benchmarks/memory_real/replay.py [--split dev] [--cap 0.2]
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
sys.path.insert(0, str(HERE.parents[1] / "src"))

from score import OUT, decider_pass, load_items, metrics  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402


def touch_replay(items: list[dict[str, Any]], root: Path) -> dict[int, list[str]]:
    os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
    os.environ["SANCHOPANZA_MEMORY_STORE_LOG"] = str(root / "log.jsonl")
    os.environ.pop("SANCHOPANZA_MEMORY_SELECT", None)
    shown: dict[int, list[str]] = {}
    order = sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"]))
    saved: set[tuple[int, str]] = set()
    for n in order:
        item = items[n]
        project = f"g{item['group']}-{item['session'][:8]}"
        transcript = root / "projects" / project / f"{item['session']}.jsonl"
        store = mh.store_for({"transcript_path": str(transcript)})
        if (item["group"], item["session"]) not in saved:
            ep.save(store, item["pool"], keep_days=10_000)  # the pool as the store holds it
            saved.add((item["group"], item["session"]))
        mh.note_live(store, item["session"], 0, frozenset(range(1, item["index"])))
        out: list[str] = []
        for tool, path in item["touched"]:
            payload = mh.touch({"hook_event_name": "PostToolUse", "session_id": item["session"],
                                "transcript_path": str(transcript), "cwd": "",
                                "tool_name": tool, "tool_input": {"file_path": path}})  # fmt: skip
            if payload:
                text = payload["hookSpecificOutput"]["additionalContext"]
                out.extend(e.key for e in item["pool"] if f"of session {e.session[:8]}" in text
                           and f"request {e.index} of" in text)  # fmt: skip
        shown[n] = list(dict.fromkeys(out))
    return shown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=("dev", "held"))
    parser.add_argument("--cap", type=float, default=0.2)
    args = parser.parse_args(argv)
    items = load_items(args.split)
    with tempfile.TemporaryDirectory() as tmp:
        touch = touch_replay(items, Path(tmp))
    prompt = asyncio.run(decider_pass(items, args.cap, mh.KEEP_AT, 0, True))
    both = {n: list(dict.fromkeys([*touch[n], *prompt[n]])) for n in touch}
    results = {"v3 touch (hook code)": metrics(items, touch),
               "v3 prompt, first request": metrics(items, prompt),
               "v3 shipped (touch + first-request prompt)": metrics(items, both)}
    for name, m in results.items():
        print(name.ljust(44), " | ".join(
            f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']} "
            f"S {m[k]['shown_per_request']}" for k in ("all/any", "all/lineage", "first/any")))
    (OUT / f"replay-{args.split}.json").write_text(json.dumps(results, indent=1),
                                                   encoding="utf-8", newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
