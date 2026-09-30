"""Items for v4.1 (review of v4, 2026-10-01). Free.

    python benchmarks/memory_real/build_v4b.py [--selection F] [--out F]

For each pool record, the lines its request wrote **per file**, in the order written: failed
calls skipped, a line the same request later took out removed again, and a Write over a file
the request had read counting only the lines not in that read. For each touch, the lines in
view (prefiltered to those that could match any pool record under either normalization) and
whether the view was partial (a Read with offset or limit, or with no content). Labels as
build.py. Written to CACHE/items-v4b.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
from build_v4 import _NUMBERED, _result_text  # noqa: E402
from labels import TOUCHING, _lines, _relative  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context.transcript import blocks_of, calls, merge_consecutive  # noqa: E402

_WORDS = re.compile(r"\w+")


def tokens(line: str) -> str:
    """A line as its words only: quotes, commas, spacing and brackets a formatter changes, out."""
    return " ".join(_WORDS.findall(line))


def _ordered(text: Any) -> list[str]:
    if not isinstance(text, str):
        return []
    out = []
    for raw in text.split("\n"):
        line = " ".join(raw.split())
        if line in _lines(raw) and line not in out:
            out.append(line)
    return out


def written_per_file(messages: Sequence[Mapping[str, Any]], cwd: str) -> dict[str, list[str]]:
    history = calls(merge_consecutive(messages))
    per: dict[str, list[str]] = defaultdict(list)
    last_read: dict[str, set[str]] = {}
    for call in history:
        data = call.input if isinstance(call.input, Mapping) else {}
        path = data.get("file_path")
        if not isinstance(path, str) or call.is_error:
            continue
        rel = _relative(path, cwd)
        if call.tool == "Read":
            last_read[rel] = set(_ordered(_NUMBERED.sub("", call.result)))
            continue
        if call.tool == "Edit":
            pairs = [(data.get("old_string"), data.get("new_string"))]
        elif call.tool == "MultiEdit":
            pairs = [(e.get("old_string"), e.get("new_string"))
                     for e in data.get("edits") or [] if isinstance(e, Mapping)]  # fmt: skip
        elif call.tool == "Write":
            pairs = [("\n".join(last_read.get(rel, ())), data.get("content"))]
        else:
            continue
        for old, new in pairs:
            before, after = set(_ordered(old)), _ordered(new)
            gone = before - set(after)
            per[rel] = [ln for ln in per[rel] if ln not in gone]
            per[rel].extend(ln for ln in after if ln not in before and ln not in per[rel])
    return dict(per)


def views(messages: Sequence[Mapping[str, Any]], cwd: str) -> list[dict[str, Any]]:
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
            partial = False
            if name == "Read":
                text = _NUMBERED.sub("", results.get(str(block.get("id")), ""))
                seen = _ordered(text)
                partial = bool(data.get("offset") or data.get("limit")) or not seen
            elif name == "Edit":
                seen = _ordered(data.get("old_string"))
            elif name == "MultiEdit":
                seen = [ln for e in data.get("edits") or [] if isinstance(e, Mapping)
                        for ln in _ordered(e.get("old_string"))]  # fmt: skip
            else:
                seen = []
            out.append({"tool": name, "path": _relative(path, cwd), "seen": seen,
                        "partial": partial})  # fmt: skip
    return out


def session(sid: str) -> dict[str, Any] | None:
    parts = build.session_parts(sid)
    if parts is None:
        return None
    entries = ep.entries_of(build.CACHE / "transcripts" / f"{sid}.jsonl")
    cwd = build.cwd_of(entries)
    split = ep.split_requests(entries)
    return {**parts,
            "per_file": {i: written_per_file(g, cwd) for i, g in enumerate(split.groups, 1)},
            "views": {i: views(g, cwd) for i, g in enumerate(split.groups, 1)}}  # fmt: skip


def items_for(sids: list[str], group: int, split: str) -> list[dict[str, Any]]:
    parts = [session(s) for s in sids]
    out = []
    for position in range(1, len(parts)):
        target = parts[position]
        earlier = [p for p in parts[:position] if p is not None]
        pool = [r for p in earlier for r in p["records"]]
        if target is None or not pool:
            continue
        wrote = {f"{p['sid']}-{q['index']:03d}": q for p in earlier for q in p["requests"]}
        per_file = {f"{p['sid']}-{i:03d}": f for p in earlier for i, f in p["per_file"].items()}
        every = {ln for f in per_file.values() for lines in f.values() for ln in lines}
        every_tokens = {tokens(ln) for ln in every}
        for request in target["requests"]:
            labels = {}
            for record in pool:
                source = wrote.get(record.key, {"written": []})
                labels[record.key] = (
                    "lineage" if build.lineage(request["removed"], source["written"])
                    else "file" if set(request["changed"])
                    & set(record.changed_raw or record.changed)
                    else "none")  # fmt: skip
            touches = [{**v, "seen": [ln for ln in v["seen"]
                                      if ln in every or tokens(ln) in every_tokens]}
                       for v in target["views"].get(request["index"], [])]  # fmt: skip
            out.append({"group": group, "split": split, "session": target["sid"],
                        "index": request["index"], "first": request["index"] == 1,
                        "request": request["request"], "touches": touches,
                        "pool": [r.to_dict() for r in pool],
                        "per_file": {r.key: per_file.get(r.key, {}) for r in pool},
                        "labels": labels})  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", default=str(build.SELECTION))
    parser.add_argument("--out", default=str(build.CACHE / "items-v4b.jsonl"))
    parser.add_argument("--split", default="dev", help="groups of this split only")
    args = parser.parse_args(argv)
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    n = 0
    with Path(args.out).open("w", encoding="utf-8", newline="\n") as handle:
        for g in selection["groups"]:
            if g["split"] != args.split:
                continue
            for item in items_for(g["sessions"], g["group"], g["split"]):
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} {args.split} requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
