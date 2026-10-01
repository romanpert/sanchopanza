"""v5, item 5: memory across a compaction, on real sessions that compacted. Free, local.

Every SWE-chat session in the cache with at least one `compact_boundary` is replayed event by
event through the hook's own code: each request's UserPromptSubmit (which records the earlier
requests and notes what is live), each compaction's SessionStart (written before the boundary is
in the transcript, as Claude Code does), and each Read/Edit/MultiEdit/Write/NotebookEdit's
PostToolUse with its real input and result. Only this session's own records are in the store,
so what is measured is what the hook gives back of the requests a compaction took out.

A request after the session's first compaction is an item. A record is related to it as in
build.py (`lineage`: it rewrites a line the record wrote; `file`: it changes a file the record
changed). Recall: items with a related record compacted out by the item's end that had one in
view since the last compaction; precision: records given during an item that are related to it;
noise: items with no related compacted record that were given anything. Also: of the related
records given, how many name a changed file that the compaction summary already names.

Sessions split before anything is scored: dev when sha1(id) starts with 0-7, else held.

    python benchmarks/memory_real/v5_compact.py --split dev
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
from build_v4 import _NUMBERED, _result_text  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context.transcript import _is_boundary, blocks_of, message_text  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

OUT = build.OUT / "compact-v5.json"
# The variant measured against the shipped hook: after a compaction, the edit fallback (the
# newest record when an edit shows none of a record's lines) only for a file that got nothing
# since that compaction. CURRENT is (session, epoch), set by `replay`.
EDIT_ONCE = False
CURRENT: list[Any] = [None]
_GIVEN_PATHS: set[Any] = set()
_CHOOSE = mh.choose_touched


def _choose_once(matching: Any, tool: str, seen: Any, k: int = mh.TOUCH_K,
                 wanted: Any = None, writers: Any = ()) -> list[Any]:  # fmt: skip
    chosen = _CHOOSE(matching, tool, seen, k, wanted, writers)
    session, epoch = CURRENT[0]
    where = (session, epoch, frozenset(wanted or ()))
    if EDIT_ONCE and epoch and chosen and tool != "Read":
        fallback = not _CHOOSE(matching, "Read", seen, k, wanted, writers)
        if fallback and where in _GIVEN_PATHS:
            return []
    if chosen:
        _GIVEN_PATHS.add(where)
    return chosen


mh.choose_touched = _choose_once
_TITLE = re.compile(r"request (\d+) of session (\S{1,8}) \(")


def split_of(sid: str) -> str:
    return "dev" if hashlib.sha1(sid.encode()).hexdigest()[0] in "01234567" else "held"


def compacted_sessions(split: str) -> list[Path]:
    out = []
    for path in sorted((build.CACHE / "transcripts").glob("*.jsonl")):
        if split_of(path.stem) != split:
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            if any('"compact_boundary"' in line for line in handle):
                out.append(path)
    return out


def _request_starts(entries: Sequence[Mapping[str, Any]]) -> list[int]:
    """Positions where a new request starts (a prompt written again after a boundary is not)."""
    starts, opened = [], set()
    for position, entry in enumerate(entries):
        if not ep._conversational(entry) or not ep.is_request(entry["message"]):
            continue
        identity = ep._identity(entry, position, True)
        if identity not in opened:
            opened.add(identity)
            starts.append(position)
    return starts


def _touch_events(entries: Sequence[Mapping[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    """(position of the result, the PostToolUse's tool name, input and response)."""
    uses: dict[str, tuple[str, Mapping[str, Any]]] = {}
    out = []
    for position, entry in enumerate(entries):
        if entry.get("isSidechain") or not isinstance(entry.get("message"), Mapping):
            continue
        for block in blocks_of(entry["message"]):
            if not isinstance(block, Mapping):
                continue
            if block.get("type") == "tool_use" and block.get("name") in mh.TOUCH_TOOLS:
                uses[str(block.get("id"))] = (str(block["name"]), block.get("input") or {})
            elif block.get("type") == "tool_result" and str(block.get("tool_use_id")) in uses:
                if block.get("is_error"):
                    continue
                tool, data = uses.pop(str(block.get("tool_use_id")))
                response: Any = {}
                if tool == "Read":
                    text = _NUMBERED.sub("", _result_text(block.get("content")))
                    response = {"type": "text", "file": {"content": text}}
                out.append((position, {"tool_name": tool, "tool_input": data,
                                       "tool_response": response,
                                       "cwd": str(entry.get("cwd") or "")}))  # fmt: skip
    return out


def _write(path: Path, entries: Sequence[Mapping[str, Any]]) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def replay(path: Path, root: Path) -> dict[str, Any] | None:
    """The hook through one session: per request, the keys given and the epoch they were given
    in; the request's start and end epoch; what was live at its end; each epoch's summary."""
    sid = path.stem
    entries = ep.entries_of(path)
    starts = _request_starts(entries)
    if len(starts) < 2:
        return None
    project = root / "projects" / sid[:12]
    project.mkdir(parents=True, exist_ok=True)
    transcript = project / f"{sid}.jsonl"
    base = {"session_id": sid, "transcript_path": str(transcript)}
    events: list[tuple[int, int, str, dict[str, Any]]] = []
    events += [(p, 0, "boundary", {}) for p, e in enumerate(entries) if _is_boundary(e)]
    events += [(p, 1, "prompt", {}) for p in starts]
    events += [(p, 2, "touch", data) for p, data in _touch_events(entries)]
    events.sort(key=lambda x: (x[0], x[1]))
    given: dict[int, list[tuple[str, int]]] = {i: [] for i in range(1, len(starts) + 1)}
    chars: dict[int, int] = dict.fromkeys(given, 0)
    epoch_at_start: dict[int, int] = {}
    summaries: dict[int, str] = {}
    epoch = 0
    request = 0
    for position, _, kind, data in events:
        CURRENT[0] = (sid, epoch + (kind == "boundary"))
        if kind == "boundary":
            _write(transcript, entries[:position])
            mh.handle({**base, "hook_event_name": "SessionStart", "source": "compact",
                       "cwd": build.cwd_of(list(entries))})  # fmt: skip
            epoch += 1
            summary = next((e for e in entries[position:position + 5]
                            if e.get("isCompactSummary")), None)  # fmt: skip
            summaries[epoch] = message_text(summary["message"]) if summary else ""
        elif kind == "prompt":
            request += 1
            epoch_at_start[request] = epoch
            _write(transcript, entries[:position])
            text = message_text(entries[position]["message"])
            mh.handle({**base, "hook_event_name": "UserPromptSubmit", "prompt": text,
                       "cwd": str(entries[position].get("cwd") or "")})  # fmt: skip
        elif request:
            out = mh.handle({**base, "hook_event_name": "PostToolUse", **data})
            text = out["hookSpecificOutput"]["additionalContext"] if out else ""
            chars[request] += len(text)
            for index, short in _TITLE.findall(text):
                if sid.startswith(short):
                    given[request].append((f"{sid}-{int(index):03d}", epoch))
    live_end = _live_at_ends(entries, starts)
    live_start = {i: set(ep.split_requests(entries[:p]).live) for i, p in enumerate(starts, 1)}
    return {"sid": sid, "given": given, "chars": chars, "epoch_at_start": epoch_at_start,
            "live_start": live_start, "touched": _touched(entries, starts),
            "epoch_at_end": _epoch_at_ends(entries, starts), "live_end": live_end,
            "summaries": summaries}  # fmt: skip


def _touched(entries: Sequence[Mapping[str, Any]], starts: list[int]) -> dict[int, set[str]]:
    """Per request, the base names of the files its file tools touched."""
    ends = [*starts[1:], len(entries)]
    out: dict[int, set[str]] = {}
    for i, (a, b) in enumerate(zip(starts, ends, strict=True), 1):
        names = set()
        for _position, data in _touch_events(entries[a:b]):
            raw = data["tool_input"].get("file_path") or data["tool_input"].get("notebook_path")
            if isinstance(raw, str):
                names.add(raw.replace("\\", "/").rsplit("/", 1)[-1])
        out[i] = names
    return out


def _epoch_at_ends(entries: Sequence[Mapping[str, Any]], starts: list[int]) -> dict[int, int]:
    ends = [*starts[1:], len(entries)]
    bounds = [p for p, e in enumerate(entries) if _is_boundary(e)]
    return {i: sum(b < end for b in bounds) for i, end in enumerate(ends, 1)}


def _live_at_ends(entries: Sequence[Mapping[str, Any]], starts: list[int]) -> dict[int, set[int]]:
    ends = [*starts[1:], len(entries)]
    return {i: set(ep.split_requests(entries[:end]).live) for i, end in enumerate(ends, 1)}


def _label(reqs: dict[int, Any], i: int, j: int) -> str:
    source, target = reqs.get(j), reqs[i]
    if source is None:
        return "none"
    if build.lineage(target["removed"], source["written"]):
        return "lineage"
    return "file" if set(target["changed"]) & set(source["changed"]) else "none"


def score(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Recall is counted twice: over records compacted out by the request's end (a record still
    in context when its file was opened, and compacted later, is not the hook's to give), and
    over records compacted out before the request started. Misses of the second, by cause."""
    n: dict[str, int] = defaultdict(int)
    causes: dict[str, int] = defaultdict(int)
    for s in sessions:
        parts = build.session_parts(s["sid"])
        if parts is None:
            continue
        reqs = {r["index"]: r for r in parts["requests"]}
        records = {r.key: r for r in parts["records"]}
        view: dict[int, set[str]] = defaultdict(set)  # epoch -> keys given in it so far
        for i in sorted(s["given"]):
            for key, epoch in s["given"][i]:
                view[epoch].add(key)
            if s["epoch_at_end"][i] == 0 or i not in reqs:
                continue
            n["items"] += 1
            now = view[s["epoch_at_end"][i]]
            key = f"{s['sid']}-{{:03d}}".format
            related = {key(j) for j in range(1, i)
                       if j not in s["live_end"][i] and _label(reqs, i, j) != "none"}
            early = {key(j) for j in range(1, i)
                     if j not in s["live_start"][i] and _label(reqs, i, j) != "none"}
            mine = [k for k, _ in s["given"][i]]
            n["chars"] += s["chars"][i]
            lineage = {key(j) for j in range(1, i)
                       if j not in s["live_end"][i] and _label(reqs, i, j) == "lineage"}
            n["good_lineage"] += sum(_label(reqs, i, int(k[-3:])) == "lineage" for k in mine)
            if lineage:
                n["with_lineage"] += 1
                n["hits_lineage"] += bool(lineage & now)
            n["given"] += len(mine)
            n["good"] += sum(_label(reqs, i, int(k[-3:])) != "none" for k in mine)
            if related:
                n["with_related"] += 1
                n["hits"] += bool(related & now)
            else:
                n["unrelated"] += 1
                n["noisy"] += bool(mine)
            if early:
                n["with_early"] += 1
                if early & now:
                    n["hits_early"] += 1
                else:
                    files = {f.rsplit("/", 1)[-1] for k in early if k in records
                             for f in records[k].changed}  # fmt: skip
                    earlier = any(early & v for e, v in view.items()
                                  if e != s["epoch_at_end"][i])  # fmt: skip
                    causes[("file touched" if files & s["touched"][i] else "no file touched")
                           + (", given in another epoch" if earlier else "")] += 1
            summary = s["summaries"].get(s["epoch_at_end"][i], "").casefold()
            for k in set(mine) & related:
                n["related_given"] += 1
                files = records[k].changed if k in records else ()
                n["in_summary"] += any(f.rsplit("/", 1)[-1].casefold() in summary for f in files)

    def ratio(a: str, b: str) -> float | None:
        return round(n[a] / n[b], 3) if n[b] else None

    return {"sessions": len(sessions), "post_compaction_requests": n["items"],
            "with_related": n["with_related"], "recall": ratio("hits", "with_related"),
            "precision": ratio("good", "given"), "noise": ratio("noisy", "unrelated"),
            "given_per_request": ratio("given", "items"),
            "chars_per_request": ratio("chars", "items"),
            "lineage": {"with_related": n["with_lineage"],
                        "recall": ratio("hits_lineage", "with_lineage"),
                        "precision": ratio("good_lineage", "given")},
            "with_related_compacted_before_start": n["with_early"],
            "recall_compacted_before_start": ratio("hits_early", "with_early"),
            "misses_before_start_by_cause": dict(causes),
            "related_given_already_named_in_summary": f"{n['in_summary']}/{n['related_given']}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=("dev", "held"))
    parser.add_argument("--edit-once", action="store_true", help="the variant")
    args = parser.parse_args(argv)
    global EDIT_ONCE
    EDIT_ONCE = args.edit_once
    for name in ("SANCHOPANZA_MEMORY_SELECT", "SANCHOPANZA_PROVIDER", "TYPESAFE_API_KEY"):
        os.environ.pop(name, None)  # as most people run it: no decider, the touch only
    # SWE-chat sessions are months old: the store's 30-day retention would prune every record
    # as it is written (a replay artifact; people's records are fresh when they compact)
    ep.save.__kwdefaults__["keep_days"] = 100_000
    paths = compacted_sessions(args.split)
    print(f"{len(paths)} compacted sessions in {args.split}", flush=True)
    sessions = []
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SANCHOPANZA_MEMORY_STORE"] = str(Path(tmp) / "store")
        for n, path in enumerate(paths):
            found = replay(path, Path(tmp))
            if found:
                sessions.append(found)
            if n % 10 == 9:
                print(f"  {n + 1} replayed", flush=True)
    result = score(sessions)
    print(json.dumps(result, indent=1))
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    name = f"{args.split} edit-once" if args.edit_once else args.split
    OUT.write_text(json.dumps({**old, name: result}, indent=1), encoding="utf-8",
                   newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
