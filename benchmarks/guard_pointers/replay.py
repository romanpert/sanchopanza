"""The compaction guard's two blocks replayed on recorded long sessions: what each would cost to
carry, and how often the agent fetched again what the whole-results block would have held.

Free and offline: recorded Claude Code transcripts of clean Claude Code (no guard), the current
`context.parts` and `context.pointers` code, no model, no API. Result:
docs/results/2026-10-16-guard-pointers-replay/.

At each compaction of a session (each `compact_boundary` in its transcript):

- **The whole-results block** (`GUARD_CHOOSER=struct`, `install --guard-full`): the transcript up
  to the boundary through `context.parts.split(..., parts=6)` with its defaults (44,000
  characters of results, 6 parts of at most 9,500), as the hook would attach it.
- **The pointer block** (the default since 2026-10-16): `context.pointers.build` on the same
  transcript, its archive folder a fixed 70-character absolute path, the length of a project's
  `.sanchopanza/archive/<session id>` (the block names it once, so its length counts once).
- **Carry cost** of a block: its tokens written once to the cache and read by every later request
  of the segment it opens (until the next compaction): tokens x (write + read x (requests - 1)).
- **Re-fetches** (the benefit the whole-results block could have had at best): calls in that
  segment that fetch again an item the block held whole (the label line before each `<<<output`
  fence): a Read of a file whose read or edit the block held, with no edit of that file earlier
  in the segment, or the same shell, Grep, Glob or other label. First re-fetch per item per
  segment only. Its cost: the request that issued it (its whole context read again, its output)
  and its result carried to the next compaction.
- **First reads**: of the files read after the compaction (first read per file, before any edit
  of it), how many were read or edited in the segment before, and how many the block held; and
  the same for shell commands.

Rates: Sonnet 5.5, USD per million tokens, output 10, cache read 0.2, 1-hour cache write 4,
fitted exactly from Claude Code's own session costs in the F2 cell (docs/results/2026-10-16-
memory-f2). Tokens per character: 0.30, from the two guarded compactions of the L-smoke run
(6,274 tokens of cache write over 20,850 characters of guard block).

    python benchmarks/guard_pointers/replay.py --runs <L-compact run root>

`--runs` (or SANCHOPANZA_GUARD_REPLAY_RUNS) is the root of the long-compaction run (the folder
that holds `cfg/<chain>-sonnet-Ne|Nl/claude-config/projects/...`), which stays local. The output
(`--out`, default the published folder) names sessions by their arm folder only.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics as st
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sanchopanza.context import guard, parts, pointers
from sanchopanza.context.structural import FILE_TOOLS, label_of, path_key
from sanchopanza.context.transcript import Call, history_from_claude_code

REPO = Path(__file__).resolve().parents[2]
PUBLISHED = REPO / "docs" / "results" / "2026-10-16-guard-pointers-replay"
TOK_PER_CHAR = 0.30
PRICE_OUT, PRICE_READ, PRICE_WRITE = 10e-6, 0.2e-6, 4e-6
STRUCT_PARTS = 6
ARMS = ("Ne", "Nl")
READS = frozenset({"Read", "Bash", "Grep", "Glob", "PowerShell", "LS", "NotebookRead"})
SHELL = frozenset({"Bash", "PowerShell"})
ARCHIVE = Path(os.path.abspath(os.sep)) / "work" / "repo" / ".sanchopanza" / "archive" / ("0" * 36)


# ---- reading a session --------------------------------------------------------------------------


def discover(runs: Path) -> list[Path]:
    """One transcript per Sonnet Ne/Nl arm folder (the largest, the main session)."""
    found = []
    for arm in sorted((runs / "cfg").glob("*-long60-*-sonnet-*")):
        if arm.name.rsplit("-", 1)[-1] not in ARMS:
            continue
        files = sorted(arm.glob("claude-config/projects/*/*.jsonl"), key=lambda p: p.stat().st_size)
        if files:
            found.append(files[-1])
    return found


def arm_of(path: Path) -> str:
    """The arm folder's name (`<chain>-sonnet-Ne`), the session's only name in the output."""
    for parent in path.parents:
        if parent.parent.name == "cfg":
            return parent.name
    return path.stem


def _entries(lines: Sequence[str]) -> list[dict[str, Any]]:
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _is_boundary(entry: Mapping[str, Any]) -> bool:
    return entry.get("type") == "system" and entry.get("subtype") == "compact_boundary"


def cut_lines(lines: Sequence[str]) -> list[int]:
    """Line numbers of the compaction boundaries."""
    out = []
    for i, line in enumerate(lines):
        if '"compact_boundary"' in line:
            try:
                if _is_boundary(json.loads(line)):
                    out.append(i)
            except ValueError:
                continue
    return out


def _results(entries: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in entries:
        content = (e.get("message") or {}).get("content")
        if e.get("type") != "user" or not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                if isinstance(c, list):
                    c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                out[str(b.get("tool_use_id"))] = str(c or "")
    return out


def segments(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per segment (0: before the first compaction): its calls in order with the request that
    made each, and its requests (deduplicated by message id) with context and output tokens."""
    results = _results(entries)
    segs: list[dict[str, Any]] = [{"calls": [], "reqs": []}]
    seen: set[str] = set()
    for e in entries:
        if _is_boundary(e):
            segs.append({"calls": [], "reqs": []})
            continue
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        mid = msg.get("id")
        usage = msg.get("usage") or {}
        if mid and mid not in seen:
            seen.add(mid)
            keys = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            context = sum(usage.get(k, 0) or 0 for k in keys)
            segs[-1]["reqs"].append(
                {"id": mid, "ctx": context, "out": usage.get("output_tokens", 0) or 0}
            )
        for b in msg.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                cid = str(b.get("id"))
                call = Call(id=cid, tool=str(b.get("name")), input=dict(b.get("input") or {}),
                            result=results.get(cid, ""))  # fmt: skip
                segs[-1]["calls"].append((mid, call))
    return segs


# ---- the two blocks ------------------------------------------------------------------------------


def blocks_at(lines: Sequence[str], cut: int, folder: Path) -> dict[str, Any]:
    """Both blocks for the transcript before line `cut`."""
    path = folder / "upto.jsonl"
    path.write_text("\n".join(lines[:cut]) + "\n", encoding="utf-8")
    messages, boundary = history_from_claude_code(path)
    try:
        struct_texts = list(parts.split(messages, since=boundary, parts=STRUCT_PARTS).texts)
    except ValueError:  # a part over the cap: the hook would give the rule's block instead
        struct_texts = [guard.block(guard.build(messages))]
    built, entries = pointers.build(messages, since=boundary, archive=ARCHIVE)
    return {
        "struct_texts": struct_texts,
        "pointer_text": guard.block(built),
        "pointer_listed": len(built.pointers),
        "archived": len(entries),
        "archived_chars": sum(len(e.text) for e in entries),
    }


def carry_usd(chars: int, requests: int) -> float:
    tokens = chars * TOK_PER_CHAR
    return tokens * PRICE_WRITE + tokens * max(requests - 1, 0) * PRICE_READ


# ---- what the whole-results block held, and what was fetched again -------------------------------


def key_of_label(label: str) -> tuple[str, str]:
    """A file key for a read or an edit of one file, else the label itself."""
    for tool in sorted(FILE_TOOLS, key=len, reverse=True):
        if label.startswith(tool + " "):
            rest = label[len(tool) + 1 :]
            for cut in (" lines ", " from line "):
                rest = rest.split(cut)[0]
            key = path_key(rest)
            if key:
                return ("file", key)
    return ("label", label)


def key_of_call(call: Call) -> tuple[str, str]:
    return key_of_label(label_of(call))


def held_of(texts: Sequence[str]) -> set[tuple[str, str]]:
    """The items a block holds whole: the label line before each output fence."""
    held = set()
    for text in texts:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line == "<<<output" and i > 0:
                held.add(key_of_label(lines[i - 1]))
    return held


def refetches(seg: Mapping[str, Any], held: set[tuple[str, str]]) -> list[dict[str, Any]]:
    edited: set[str] = set()
    done: set[tuple[str, str]] = set()
    order = {r["id"]: i for i, r in enumerate(seg["reqs"])}
    out = []
    for mid, call in seg["calls"]:
        key = key_of_call(call)
        if call.tool in FILE_TOOLS and call.tool != "Read":
            if key[0] == "file":
                edited.add(key[1])
            continue
        if call.tool not in READS and key[0] != "label":
            continue
        if key not in held or key in done or (key[0] == "file" and key[1] in edited):
            continue
        done.add(key)
        i = order.get(mid, 0)
        req = seg["reqs"][i] if seg["reqs"] else {"ctx": 0, "out": 0}
        remaining = max(len(seg["reqs"]) - i - 1, 0)
        tokens = len(call.result) * TOK_PER_CHAR
        usd = (req["ctx"] * PRICE_READ + req["out"] * PRICE_OUT + tokens * PRICE_WRITE
               + tokens * remaining * PRICE_READ)  # fmt: skip
        out.append({"tool": call.tool, "result_tokens": round(tokens), "usd": usd})
    return out


def first_reads(
    before: Mapping[str, Any], seg: Mapping[str, Any], held: set[tuple[str, str]]
) -> dict[str, int]:
    earlier = {key_of_call(c) for _, c in before["calls"]}
    seen: set[tuple[str, str]] = set()
    edited: set[tuple[str, str]] = set()
    out = dict.fromkeys(("reads", "reads_seen_before", "reads_held", "shell", "shell_seen_before",
                         "shell_held"), 0)  # fmt: skip
    for _, call in seg["calls"]:
        key = key_of_call(call)
        if call.tool in FILE_TOOLS and call.tool != "Read":
            edited.add(key)
            continue
        if key in seen or key in edited:
            continue
        seen.add(key)
        kind = "reads" if call.tool == "Read" else "shell" if call.tool in SHELL else ""
        if kind:
            out[kind] += 1
            out[f"{kind}_seen_before"] += key in earlier
            out[f"{kind}_held"] += key in held
    return out


# ---- a session, the summary ----------------------------------------------------------------------


def replay_session(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    segs = segments(_entries(lines))
    name = arm_of(path)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, cut in enumerate(cut_lines(lines), start=1):
            if k >= len(segs):
                break
            got = blocks_at(lines, cut, Path(tmp))
            seg = segs[k]
            nreqs = len(seg["reqs"])
            struct_chars = sum(len(t) for t in got["struct_texts"])
            pointer_chars = len(got["pointer_text"])
            held = held_of(got["struct_texts"])
            again = refetches(seg, held)
            rows.append({
                "session": name, "arm": name.rsplit("-", 1)[-1], "compaction": k,
                "segment_requests": nreqs,
                "struct_chars": struct_chars, "struct_parts": len(got["struct_texts"]),
                "struct_held": len(held), "struct_usd": carry_usd(struct_chars, nreqs),
                "pointer_chars": pointer_chars, "pointer_listed": got["pointer_listed"],
                "archived": got["archived"], "archived_chars": got["archived_chars"],
                "pointer_usd": carry_usd(pointer_chars, nreqs),
                "refetches": len(again), "refetch_usd": sum(r["usd"] for r in again),
                "refetch_tools": sorted(r["tool"] for r in again),
                **first_reads(segs[k - 1], seg, held),
            })  # fmt: skip
    return rows


def _med(xs: Sequence[float]) -> float:
    return st.median(xs) if xs else 0.0


def summarise(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sessions: dict[str, dict[str, Any]] = defaultdict(lambda: {"struct": 0.0, "pointer": 0.0})
    for r in rows:
        s = sessions[r["session"]]
        s["arm"] = r["arm"]
        s["struct"] += r["struct_usd"]
        s["pointer"] += r["pointer_usd"]
    per_arm = {}
    for arm in ARMS:
        xs = [s for s in sessions.values() if s["arm"] == arm]
        if xs:
            per_arm[arm] = {
                "sessions": len(xs),
                "compactions": sum(1 for r in rows if r["arm"] == arm),
                "struct_usd_per_session_mean": st.mean(s["struct"] for s in xs),
                "struct_usd_per_session_median": _med([s["struct"] for s in xs]),
                "pointer_usd_per_session_mean": st.mean(s["pointer"] for s in xs),
                "pointer_usd_per_session_median": _med([s["pointer"] for s in xs]),
            }
    struct_total = sum(s["struct"] for s in sessions.values())
    pointer_total = sum(s["pointer"] for s in sessions.values())
    n = len(rows)
    keys = ("reads", "reads_seen_before", "reads_held", "shell", "shell_seen_before", "shell_held")
    totals = {k: sum(r[k] for r in rows) for k in keys}
    return {
        "sessions": len(sessions),
        "compactions": n,
        "struct_chars_median": _med([r["struct_chars"] for r in rows]),
        "pointer_chars_median": _med([r["pointer_chars"] for r in rows]),
        "pointer_chars_max": max((r["pointer_chars"] for r in rows), default=0),
        "archived_chars_median": _med([r["archived_chars"] for r in rows]),
        "per_arm": per_arm,
        "saving_usd_per_session_mean": (struct_total - pointer_total) / max(len(sessions), 1),
        "saving_share_of_struct_carry": 1 - pointer_total / struct_total if struct_total else 0.0,
        "compactions_with_a_refetch": sum(1 for r in rows if r["refetches"]),
        "refetches": sum(r["refetches"] for r in rows),
        "refetch_usd_per_compaction_mean": sum(r["refetch_usd"] for r in rows) / max(n, 1),
        "struct_usd_per_compaction_mean": sum(r["struct_usd"] for r in rows) / max(n, 1),
        "first_reads": totals,
        "rates_usd_per_mtok": {"output": 10, "cache_read": 0.2, "cache_write_1h": 4},
        "tokens_per_char": TOK_PER_CHAR,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--runs",
        type=Path,
        default=os.environ.get("SANCHOPANZA_GUARD_REPLAY_RUNS"),
        help="the long-compaction run root (SANCHOPANZA_GUARD_REPLAY_RUNS)",
    )
    parser.add_argument("--out", type=Path, default=PUBLISHED, help="where to write the JSON")
    args = parser.parse_args(argv)
    if args.runs is None:
        parser.error("--runs (or SANCHOPANZA_GUARD_REPLAY_RUNS) is required")
    paths = discover(Path(args.runs))
    if not paths:
        parser.error(f"no Sonnet Ne/Nl long60 transcripts under {args.runs}/cfg")
    rows = [row for path in paths for row in replay_session(path)]
    summary = summarise(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compactions.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
