"""Items for memory v4: what the agent saw when it touched a file. Free.

    python benchmarks/memory_real/build_v4.py [--source swechat|local]

Like build.py (whose items and labels are unchanged), and each touch also carries, for every
pool record that changed the touched file, how many of the lines that record wrote appear in
what the agent saw: the content a Read returned, or the `old_string` of an Edit. That is the
signal v4 ranks by. Written to CACHE/items-v4.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
from labels import TOUCHING, _lines, _relative  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context.transcript import blocks_of  # noqa: E402

_NUMBERED = re.compile(r"^\s*\d+[→\t]", re.M)


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text") or "") for b in content if isinstance(b, Mapping))
    return ""


def viewed_of(messages: Iterable[Mapping[str, Any]], cwd: str) -> list[tuple[str, str, set[str]]]:
    """(tool, path, lines seen) for every file call, in order: a Read's returned lines (the
    line numbers taken off), an Edit's `old_string` lines; nothing for a Write."""
    messages = list(messages)
    results: dict[str, str] = {}
    for message in messages:
        for block in blocks_of(message):
            if isinstance(block, Mapping) and block.get("type") == "tool_result":
                results[str(block.get("tool_use_id"))] = _result_text(block.get("content"))
    out = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for block in blocks_of(message):
            if not (isinstance(block, Mapping) and block.get("type") == "tool_use"
                    and block.get("name") in TOUCHING):  # fmt: skip
                continue
            data = block.get("input") or {}
            path = data.get("file_path") or data.get("notebook_path")
            if not isinstance(path, str):
                continue
            name = str(block["name"])
            if name == "Read":
                seen = _lines(_NUMBERED.sub("", results.get(str(block.get("id")), "")))
            elif name == "Edit":
                seen = _lines(data.get("old_string"))
            elif name == "MultiEdit":
                seen = {ln for e in data.get("edits") or [] if isinstance(e, Mapping)
                        for ln in _lines(e.get("old_string"))}  # fmt: skip
            else:
                seen = set()
            out.append((name, _relative(path, cwd), seen))
    return out


def parts_v4(path: Path, sid: str) -> dict[str, Any] | None:
    parts = build.session_parts(sid)
    if parts is None:
        return None
    entries = ep.entries_of(path)
    cwd = build.cwd_of(entries)
    split = ep.split_requests(entries)
    viewed = {i: viewed_of(g, cwd) for i, g in enumerate(split.groups, start=1)}
    return {**parts, "viewed": viewed}


def items_for(sessions: list[tuple[str, Path]], group: int, split: str) -> list[dict[str, Any]]:
    parts = [parts_v4(path, sid) for sid, path in sessions]
    out = []
    for position in range(1, len(parts)):
        target = parts[position]
        earlier = [p for p in parts[:position] if p is not None]
        pool = [r for p in earlier for r in p["records"]]
        if target is None or not pool:
            continue
        wrote = {f"{p['sid']}-{q['index']:03d}": q for p in earlier for q in p["requests"]}
        written = {k: set(v["written"]) for k, v in wrote.items()}
        by_path: dict[str, list[ep.Episode]] = defaultdict(list)
        for r in pool:
            for c in r.changed_raw or r.changed:
                by_path[c].append(r)
        for request in target["requests"]:
            labels = {}
            for record in pool:
                labels[record.key] = (
                    "lineage" if build.lineage(request["removed"], written.get(record.key, ()))
                    else "file" if set(request["changed"])
                    & set(record.changed_raw or record.changed)
                    else "none")  # fmt: skip
            everything = set().union(*written.values()) if written else set()
            touches = [[tool, rel, {r.key: len(seen & written.get(r.key, set()))
                                    for r in by_path.get(rel, [])},
                        sorted(seen & everything)]  # what the replay shows the hook
                       for tool, rel, seen in target["viewed"].get(request["index"], [])]
            out.append({"group": group, "split": split, "session": target["sid"],
                        "index": request["index"], "first": request["index"] == 1,
                        "request": request["request"], "touched": request["touched"],
                        "touches": touches, "pool": [r.to_dict() for r in pool],
                        "labels": labels})  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", default=str(build.SELECTION))
    parser.add_argument("--out", default=str(build.CACHE / "items-v4.jsonl"))
    args = parser.parse_args(argv)
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    counts: dict[str, int] = defaultdict(int)
    with Path(args.out).open("w", encoding="utf-8", newline="\n") as handle:
        for g in selection["groups"]:
            sessions = [(s, build.CACHE / "transcripts" / f"{s}.jsonl") for s in g["sessions"]]
            for item in items_for(sessions, g["group"], g["split"]):
                counts[f"{g['split']} requests"] += 1
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
