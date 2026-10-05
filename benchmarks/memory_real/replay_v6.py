"""v6 against v5: the touch replayed through `memory_hook.touch` on items of build_v6.py, with
Bash calls skipped (v5, what a file-tool matcher sees) or sent to the hook (v6). Free.

    python benchmarks/memory_real/replay_v6.py --items CACHE/items-v6-dev.jsonl --tag dev
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from replay_v4 import event_for  # noqa: E402
from replay_v5 import shown_in  # noqa: E402
from score import CACHE, OUT, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402


def bash_event(item: dict[str, Any], transcript: Path, touch: dict[str, Any]) -> dict[str, Any]:
    return {"hook_event_name": "PostToolUse", "session_id": item["session"],
            "transcript_path": str(transcript), "cwd": item.get("cwd", ""), "tool_name": "Bash",
            "tool_input": {"command": touch["command"]},
            "tool_response": {"stdout": touch["output"], "stderr": ""}}  # fmt: skip


def touch_replay(items: list[dict[str, Any]], root: Path, bash: bool) -> tuple[Any, Any]:
    """(shown per item, characters per item, and per item which tool gave each record)."""
    os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
    os.environ.pop("SANCHOPANZA_MEMORY_SELECT", None)
    shown: dict[int, list[str]] = {}
    chars: dict[int, int] = {}
    by_tool: dict[int, dict[str, str]] = {}
    saved: set[str] = set()
    for n in sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])):
        item = items[n]
        transcript = root / "projects" / f"g{item['group']}-{item['session'][:8]}" / "t.jsonl"
        store = mh.store_for({"transcript_path": str(transcript)})
        if item["session"] not in saved:
            ep.save(store, item["pool"], keep_days=10_000)
            saved.add(item["session"])
        mh.note_live(store, item["session"], 0, frozenset(range(1, item["index"])),
                     item.get("cwd", ""))
        out: list[str] = []
        chars[n] = 0
        by_tool[n] = {}
        for touch in item["touches"]:
            if touch["tool"] == "Bash":
                if not bash:
                    continue
                event = bash_event(item, transcript, touch)
            else:
                event = event_for(item, transcript, touch["tool"], touch["path"], touch["seen"])
            payload = mh.touch(event)
            if payload:
                text = payload["hookSpecificOutput"]["additionalContext"]
                chars[n] += len(text)
                for key in shown_in(text, item["pool"]):
                    out.append(key)
                    by_tool[n][key] = touch["tool"]
        shown[n] = list(dict.fromkeys(out))
    return shown, chars, by_tool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v6-dev.jsonl"))
    parser.add_argument("--tag", default="dev")
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    rows = {}
    for name, bash in (("v5 touch", False), ("v6 touch", True)):
        with tempfile.TemporaryDirectory() as tmp:
            shown, chars, by_tool = touch_replay(items, Path(tmp), bash)
        m = metrics(items, shown)
        via_bash = [(n, k) for n, d in by_tool.items() for k, t in d.items() if t == "Bash"]
        good = sum(items[n]["labels"][k] != "none" for n, k in via_bash)
        rows[name] = {**m, "chars_per_request": round(sum(chars.values()) / len(items)),
                      "given_by_bash": len(via_bash), "related_given_by_bash": good}  # fmt: skip
        print(name.ljust(9), " | ".join(
            f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']}"
            for k in ("all/any", "all/lineage", "first/any")),
            f"chars {rows[name]['chars_per_request']} bash {len(via_bash)} ({good} related)")
    target = OUT / f"replay-v6-{args.tag}.json"
    target.write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
