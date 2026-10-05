"""v6 diagnosis: which Bash calls give unrelated records on SWE-chat items (build_v6.py). Free,
local; prints commands, so run it only on the cache, never into the repo.

    python benchmarks/memory_real/v6_diag_bash.py dev held1
"""

import collections
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_v6 as rv  # noqa: E402
from replay_v5 import shown_in  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

C = Path.home() / ".cache/sanchopanza/memory-real"
kinds = collections.Counter()
for name in sys.argv[1:]:
    items = load(C / f"items-v6-{name}.jsonl")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
        os.environ.pop("SANCHOPANZA_MEMORY_SELECT", None)
        saved = set()
        for n in sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])):
            item = items[n]
            transcript = root / "projects" / f"g{item['group']}-{item['session'][:8]}" / "t.jsonl"
            store = mh.store_for({"transcript_path": str(transcript)})
            if item["session"] not in saved:
                ep.save(store, item["pool"], keep_days=10_000)
                saved.add(item["session"])
            mh.note_live(store, item["session"], 0, frozenset(range(1, item["index"])),
                         item.get("cwd", ""))
            for t in item["touches"]:
                if t["tool"] != "Bash":
                    event = rv.event_for(item, transcript, t["tool"], t["path"], t["seen"])
                    mh.touch(event)
                    continue
                out = mh.touch(rv.bash_event(item, transcript, t))
                text = out["hookSpecificOutput"]["additionalContext"] if out else ""
                for key in shown_in(text, item["pool"]):
                    label = item["labels"][key]
                    head = re.sub(r"^cd \S+ && ", "", t["command"]).split()[0:2]
                    writes = bool(mh.shell_written(t["command"]))
                    kinds[(label != "none", " ".join(head)[:30], writes)] += 1
                    if label == "none":
                        shown = t["command"][:140].replace("\n", " | ")
                        print(name, "UNRELATED", "write" if writes else "read", "|", shown)
for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
    print(v, k)
