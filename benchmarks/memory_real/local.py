"""The touch on the maintainer's own Claude Code sessions, locally: no text leaves the machine
(the touch calls no model) and the repository gets counts only.

    python benchmarks/memory_real/local.py

Groups are project folders under ~/.claude/projects with at least three sessions, benchmark
and temporary folders excluded; each takes up to WINDOW consecutive sessions from a seeded
random start. Items and labels are built exactly as for SWE-chat (build.session_parts), and the
shipped hook's touch is replayed through its own code (replay.touch_replay).
"""

from __future__ import annotations

import json
import random
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
from replay import touch_replay  # noqa: E402
from score import OUT, metrics  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402

PROJECTS = Path.home() / ".claude" / "projects"
EXCLUDE = ("-cache-", "AppData-Local-Temp", "sanchopanza-adopt", "-tmp")
SEED = 20261001
GROUPS = 60
WINDOW = 6


def first_stamp(path: Path) -> float:
    for entry in ep.entries_of(path)[:50]:
        if entry.get("timestamp"):
            return ep._stamp(entry)
    return path.stat().st_mtime


def choose() -> list[tuple[str, list[Path]]]:
    rng = random.Random(SEED)
    groups = []
    for folder in sorted(PROJECTS.iterdir()):
        if not folder.is_dir() or any(x in folder.name for x in EXCLUDE):
            continue
        sessions = sorted(folder.glob("*.jsonl"), key=first_stamp)
        if len(sessions) >= 3:
            groups.append((folder.name, sessions))
    rng.shuffle(groups)
    out = []
    for name, sessions in groups[:GROUPS]:
        width = min(WINDOW, len(sessions))
        start = rng.randrange(0, len(sessions) - width + 1)
        out.append((name, sessions[start:start + width]))
    return out


def main() -> int:
    cache = Path(tempfile.mkdtemp())
    items: list[dict[str, Any]] = []
    try:
        folder = build.CACHE
        build.CACHE = cache  # session_parts reads CACHE/transcripts/<sid>.jsonl
        (cache / "transcripts").mkdir()
        chosen = choose()
        for g, (_, sessions) in enumerate(chosen):
            for path in sessions:
                shutil.copyfile(path, cache / "transcripts" / path.name)
            parts = [build.session_parts(p.stem) for p in sessions]
            for position in range(1, len(parts)):
                target = parts[position]
                earlier = [p for p in parts[:position] if p]
                pool = [r for p in earlier for r in p["records"]]
                if target is None or not pool:
                    continue
                wrote = {f"{p['sid']}-{q['index']:03d}": q for p in earlier for q in p["requests"]}
                for request in target["requests"]:
                    labels = {}
                    for record in pool:
                        source = wrote.get(record.key, {"written": []})
                        labels[record.key] = (
                            "lineage" if build.lineage(request["removed"], source["written"])
                            else "file" if set(request["changed"]) & set(
                                record.changed_raw or record.changed)
                            else "none")  # fmt: skip
                    items.append({"group": g, "session": target["sid"],
                                  "index": request["index"], "first": request["index"] == 1,
                                  "request": request["request"], "touched": request["touched"],
                                  "pool": pool, "labels": labels})  # fmt: skip
        build.CACHE = folder
        with tempfile.TemporaryDirectory() as tmp:
            shown = touch_replay(items, Path(tmp))
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    result = {"groups": len(chosen), "requests": len(items),
              "with_related_any": sum(bool({"lineage", "file"} & set(i["labels"].values()))
                                      for i in items),
              "v3 touch (hook code)": metrics(items, shown)}  # fmt: skip
    m = result["v3 touch (hook code)"]
    print(json.dumps({k: result[k] for k in ("groups", "requests", "with_related_any")}))
    for k in ("all/any", "all/lineage", "first/any"):
        print(k, m[k])
    (OUT / "local-touch.json").write_text(json.dumps(result, indent=1), encoding="utf-8",
                                         newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
