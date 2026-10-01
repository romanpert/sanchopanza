"""Items for v6 (the touch on Bash): build_v4b's items with every Bash call kept, in order,
among the file tools' touches, with its command and its output (cache only, never the repo).
Free.

    python benchmarks/memory_real/build_v6.py --split dev --out CACHE/items-v6-dev.jsonl
    python benchmarks/memory_real/build_v6.py --selection OUT/selection-3.json --split held3 ...
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
import build_v4b  # noqa: E402
from build_v4 import _NUMBERED, _result_text  # noqa: E402
from labels import TOUCHING, _relative  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context import shell  # noqa: E402
from sanchopanza.context.transcript import blocks_of  # noqa: E402

COMMAND_CHARS = 8_000


def views(messages: Sequence[Mapping[str, Any]], cwd: str) -> list[dict[str, Any]]:
    """build_v4b.views with each Bash call in its place: its command and output."""
    results: dict[str, Any] = {}
    for message in messages:
        for block in blocks_of(message):
            if isinstance(block, Mapping) and block.get("type") == "tool_result":
                results[str(block.get("tool_use_id"))] = block
    out = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for block in blocks_of(message):
            if not (isinstance(block, Mapping) and block.get("type") == "tool_use"):
                continue
            name, data = str(block.get("name")), block.get("input") or {}
            result = results.get(str(block.get("id"))) or {}
            text = _result_text(result.get("content")) if result else ""
            if name in ("Bash", "PowerShell"):  # the hook reads both alike; replayed as Bash
                command = data.get("command")
                if isinstance(command, str) and not result.get("is_error"):
                    out.append({"tool": "Bash", "shell": name, "seen": [],
                                "command": command[:COMMAND_CHARS],
                                "output": text[:shell.SCAN]})  # fmt: skip
                continue
            if name not in TOUCHING:
                continue
            path = data.get("file_path") or data.get("notebook_path")
            if not isinstance(path, str):
                continue
            if name == "Read":
                seen = build_v4b._ordered(_NUMBERED.sub("", text))
            elif name == "Edit":
                seen = build_v4b._ordered(data.get("old_string"))
            elif name == "MultiEdit":
                seen = [ln for e in data.get("edits") or [] if isinstance(e, Mapping)
                        for ln in build_v4b._ordered(e.get("old_string"))]  # fmt: skip
            else:
                seen = []
            out.append({"tool": name, "path": _relative(path, cwd), "seen": seen,
                        "partial": False})  # fmt: skip
    return out


_CWD: dict[str, str] = {}


def cwd_of(session: str) -> str:
    """Where the session started: the hook keeps it in its state; Bash commands may hold
    absolute paths under it."""
    if session not in _CWD:
        entries = ep.entries_of(build.CACHE / "transcripts" / f"{session}.jsonl")
        _CWD[session] = build.cwd_of(entries)
    return _CWD[session]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", default=str(build.SELECTION))
    parser.add_argument("--split", default="dev")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    build_v4b.views = views  # items_for reads views through session(): Bash kept, unfiltered
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    n = 0
    with Path(args.out).open("w", encoding="utf-8", newline="\n") as handle:
        for g in selection["groups"]:
            if g["split"] != args.split:
                continue
            for item in build_v4b.items_for(g["sessions"], g["group"], g["split"]):
                # the folder the session started in, as the hook keeps it (missing until
                # 2026-10-01: an absolute path in a shell command never matched)
                item = {**item, "cwd": cwd_of(item["session"])}
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} {args.split} requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
