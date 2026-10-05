"""Why a record the shell touch gave in a committing request is not of a file the request
committed (`commit_label.py`): per such give, the files it was given for (the record's files
the request writes, by the parser) and where each one is: committed later in the session,
ignored by git, outside any repository, or inside one and never committed. Local, free, counts
and anonymised kinds only.

    python benchmarks/memory_real/commit_label_diag.py [--items CACHE/items-v61-local.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import commit_label as cl  # noqa: E402
import replay_v6 as rv  # noqa: E402
from score import CACHE  # noqa: E402
from variants_v4b import load  # noqa: E402
from variants_v62 import _norm  # noqa: E402

from sanchopanza.context import shell  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402


def written(item: dict[str, Any]) -> dict[str, str]:
    """Files the request writes through the shell, as labels spell them -> absolute path."""
    cwd = str(item.get("cwd") or "")
    out = {}
    for t in item["touches"]:
        if "command" not in t:
            continue
        base = cl.folder(shell.view(t["command"], "", cwd)[2] or cwd)
        for p in mh.shell_written(t["command"]):
            q = cl.folder(p)  # `~`, `$HOME`, `/c/` as the file system names them (review, M4)
            full = q if (q.startswith("/") or q[1:2] == ":") else f"{base.rstrip('/')}/{q}"
            out[_norm(p, cwd, base)] = full
    return out


def where(full: str, later: set[str], spelt: str) -> str:
    if spelt in later:
        return "committed later in the session"
    folder = str(Path(full).parent)
    while folder and not Path(folder).is_dir() and Path(folder).parent != Path(folder):
        folder = str(Path(folder).parent)
    root = cl.root_of(folder)
    if root is None:
        return "outside any repository"
    if cl._git(root, "check-ignore", "-q", full) is not None:
        return "ignored by git"
    if cl._git(root, "ls-files", "--error-unmatch", full) is not None:
        return "tracked, not committed in the session"
    return "untracked, not committed in the session"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v61-local.jsonl"))
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    files = [cl.committed(it)[0] for it in items]
    with tempfile.TemporaryDirectory() as tmp:
        _, _, by_tool = rv.touch_replay(items, Path(tmp), True)
    kinds: Counter[str] = Counter()
    gives = 0
    for n, given in by_tool.items():
        if not files[n]:
            continue
        item = items[n]
        later = {f for m, it in enumerate(items) if it["session"] == item["session"]
                 and it["index"] > item["index"] for f in files[m]}  # fmt: skip
        mine = written(item)
        for key, tool in given.items():
            if tool != "Bash":
                continue
            gives += 1
            record = next(r for r in item["pool"] if r.key == key)
            cwd = str(item.get("cwd") or "")
            changed = {_norm(str(c), cwd) for c in (record.changed_raw or record.changed)}
            hit = changed & set(mine)
            if hit & files[n]:
                kinds["committed in the request"] += 1
                continue
            spelt = sorted(hit)[0] if hit else ""
            kinds[where(mine[spelt], later, spelt) if spelt else "no written file matched"] += 1
    print(json.dumps({"shell_gives_in_committing_requests": gives, "kinds": kinds}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
