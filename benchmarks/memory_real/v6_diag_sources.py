"""v6.1 diagnosis: for every record the shell touch gives on SWE-chat items (build_v6.py), its
label, the command's first words, and where the matching lines came from (the output, the
command's own text, a quoted string, a heredoc body). Free, local; writes one JSON line per
given record to the cache (it holds commands), never into the repo.

    python benchmarks/memory_real/v6_diag_sources.py dev held1
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_v6 as rv  # noqa: E402
from replay_v5 import shown_in  # noqa: E402
from variants_v4b import load  # noqa: E402
from variants_v61 import with_cwd  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context import shell  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

C = Path.home() / ".cache/sanchopanza/memory-real"


def sources(command: str, output: str) -> dict[str, set[str]]:
    _, bodies = shell._parts(command)
    own = command[: shell.SCAN]
    return {
        "output": ep.line_prints(shell._LINE_PREFIX.sub("", output[: shell.SCAN])),
        "own": ep.line_prints("\n".join(shell._TRIPLE.split(own))),
        "quoted": ep.line_prints("\n".join(q[1:-1] for q in shell._QUOTED.findall(own))),
        "heredoc": ep.line_prints("\n".join(bodies)),
    }


def main() -> int:
    out = (C / "diag-sources.jsonl").open("w", encoding="utf-8")
    for name in sys.argv[1:]:
        items = with_cwd(load(C / f"items-v6-{name}.jsonl"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["SANCHOPANZA_MEMORY_STORE"] = str(root / "store")
            os.environ.pop("SANCHOPANZA_MEMORY_SELECT", None)
            saved: set[str] = set()
            order = sorted(
                range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"])
            )
            for n in order:
                item = items[n]
                transcript = (
                    root / "projects" / f"g{item['group']}-{item['session'][:8]}" / "t.jsonl"
                )
                store = mh.store_for({"transcript_path": str(transcript)})
                if item["session"] not in saved:
                    ep.save(store, item["pool"], keep_days=10_000)
                    saved.add(item["session"])
                mh.note_live(
                    store,
                    item["session"],
                    0,
                    frozenset(range(1, item["index"])),
                    item.get("cwd", ""),
                )
                pool = {e.key: e for e in item["pool"]}
                for t in item["touches"]:
                    if t["tool"] != "Bash":
                        mh.touch(rv.event_for(item, transcript, t["tool"], t["path"], t["seen"]))
                        continue
                    res = mh.touch(rv.bash_event(item, transcript, t))
                    text = res["hookSpecificOutput"]["additionalContext"] if res else ""
                    for key in shown_in(text, item["pool"]):
                        e = pool[key]
                        wrote = {p for _, prints in e.wrote or () for p in prints}
                        src = {
                            k: len(v & wrote) for k, v in sources(t["command"], t["output"]).items()
                        }
                        bare = re.sub(r"^\s*cd \S+ *(&&|;) *", "", t["command"])
                        row = {
                            "set": name,
                            "label": item["labels"][key],
                            "head": bare.split()[:3],
                            "item": n,
                            "path": [
                                k for k in mh.bash_view(t["command"], t["output"], item["cwd"])[0]
                            ][:3],
                            "writes": mh.shell_written(t["command"]),
                            "sources": src,
                            "command": t["command"][:300],
                            "output_chars": len(t["output"]),
                        }
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
