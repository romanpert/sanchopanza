"""After amendment 5 (not confirmed): which shell calls give the unrelated records on the
maintainer's local items (local_v6.py), through the product's touch, PowerShell as PowerShell.
Local only: prints commands, writes them to the cache, never to the repo.

    python benchmarks/memory_real/v61_diag_local.py
"""

import collections
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_v6 as lv  # noqa: E402
import replay_v6 as rv  # noqa: E402
from replay_v5 import shown_in  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

OUT = lv.build.CACHE / "diag-local-v61.jsonl"


def head(command: str) -> str:
    bare = re.sub(r"^\s*cd\s+(\"[^\"]*\"|'[^']*'|\S+)\s*(&&|;)\s*", "", command)
    return " ".join(bare.split()[:2])[:40]


def main() -> int:
    """With `--reads MODE` (variants_v62.reads), the shell reads of that v6.2 candidate, and
    labels that also count the request's shell writes (variants_v62.with_shell_label)."""
    if "--reads" in sys.argv:
        import variants_v62 as v62

        mode = sys.argv[sys.argv.index("--reads") + 1]
        with v62.reads(mode):
            return _main(v62.with_shell_label(load(lv.ITEMS)))
    return _main(load(lv.ITEMS))


def _main(items: list) -> int:
    kinds: collections.Counter = collections.Counter()
    before_edit: collections.Counter = collections.Counter()
    with tempfile.TemporaryDirectory() as tmp, OUT.open("w", encoding="utf-8") as out:
        root = Path(tmp)
        os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
        os.environ.pop("SANCHOPANZA_MEMORY_SELECT", None)
        saved: set[str] = set()
        for n in sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])):
            item = items[n]
            transcript = root / "projects" / f"g{item['group']}-{item['session'][:8]}" / "t.jsonl"
            store = mh.store_for({"transcript_path": str(transcript)})
            if item["session"] not in saved:
                ep.save(store, item["pool"], keep_days=10_000)
                saved.add(item["session"])
            mh.note_live(store, item["session"], 0, frozenset(range(1, item["index"])),
                         item.get("cwd", ""))  # fmt: skip
            written_before: set[str] = set()  # files this request wrote before the call
            for t in item["touches"]:
                if t["tool"] != "Bash":
                    mh.touch(rv.event_for(item, transcript, t["tool"], t["path"], t["seen"]))
                    if t["tool"] in ("Edit", "MultiEdit", "Write"):
                        written_before.add(t["path"].replace("\\", "/").casefold())
                    continue
                now = {p.replace("\\", "/").casefold() for p in mh.shell_written(t["command"])}
                first = not any(p.endswith(w) or w.endswith(p) for p in now for w in written_before)
                event = {**rv.bash_event(item, transcript, t), "tool_name": t.get("shell", "Bash")}
                res = mh.touch(event)
                written_before |= now
                text = res["hookSpecificOutput"]["additionalContext"] if res else ""
                for key in shown_in(text, item["pool"]):
                    related = item["labels"][key] != "none"
                    writes = bool(now)
                    kinds[(related, head(t["command"]), writes)] += 1
                    before_edit[(related, "at the request's first write" if first
                                 else "after an earlier write of the file")] += 1  # fmt: skip
                    out.write(json.dumps({"related": related, "writes": writes,
                                          "shell": t.get("shell", "Bash"),
                                          "request": item["request"][:200],
                                          "command": t["command"][:400]},
                                         ensure_ascii=False) + "\n")  # fmt: skip
    print("(related, when):", dict(before_edit))
    for k, v in kinds.most_common(40):
        print(v, k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
