"""v6 against v5 on the adoption chains' real sessions (read-only, local): what the touch gives
when each request starts a new session holding every earlier request's record.

Truth comes from the chain's patches: `diff-<i>.patch` is the working tree against the base
after request i, so request i changed a file when its block differs from `diff-<i-1>`'s, and
added the `+` lines it gained. A record is related to a later request as in build.py: `file`
(both changed it) or `lineage` (the later request took out a line the record added).

- v5: records as the transcript makes them (file tools), the touch on file tools only.
- v6: records plus what the tree says each request changed (simulated from the patches, kept
  only for files the request named in a tool input, as the hook does), the touch on Bash too.

    python benchmarks/memory_real/v6_chain.py [--runs DIR] [--chains A,B]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_v4 import _NUMBERED, _result_text  # noqa: E402
from replay_v5 import shown_in  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context.transcript import blocks_of  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

RUNS = Path.home() / ".cache" / "sanchopanza" / "adopt" / "runs"
OUT = HERE.parents[1] / "docs" / "results" / "2026-10-01-memory-real" / "chain-v6.json"
_FILE = re.compile(r"^diff --git a/(\S+) b/", re.M)


def patch_files(path: Path) -> dict[str, tuple[str, set[str]]]:
    """Per file: its block's text and its `+` lines (words-only prints)."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    starts = [(m.start(), m.group(1)) for m in _FILE.finditer(text)]
    for n, (at, name) in enumerate(starts):
        block = text[at:starts[n + 1][0] if n + 1 < len(starts) else len(text)]
        added = {ep.line_print(x[1:]) for x in block.splitlines()
                 if x.startswith("+") and not x.startswith("+++") and ep._counts(x[1:])}
        out[name] = (block, added)
    return out


def entries_of(stream: Path) -> list[dict[str, Any]]:
    """The stream's messages after a stand-in for the prompt: `claude -p` takes it as an
    argument and the stream never echoes it (its text does not matter to the touch)."""
    i = stream.stem.split("-")[1]
    out = [{"type": "user", "message": {"role": "user", "content": f"Request {i} of the chain"}}]
    for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("type") in ("user", "assistant"):
            out.append(e)
    return out


def touches(entries: list[dict[str, Any]], bash: bool) -> list[dict[str, Any]]:
    results: dict[str, str] = {}
    for e in entries:
        for b in blocks_of(e["message"]):
            if isinstance(b, dict) and b.get("type") == "tool_result" and not b.get("is_error"):
                results[str(b.get("tool_use_id"))] = _result_text(b.get("content"))
    out = []
    for e in entries:
        for b in blocks_of(e["message"]):
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            name, data = str(b.get("name")), b.get("input") or {}
            result = results.get(str(b.get("id")))
            if result is None:
                continue
            if name in ("Bash", "PowerShell") and bash:
                out.append({"tool_name": "Bash", "tool_input": {"command": data.get("command")},
                            "tool_response": {"stdout": result}})  # fmt: skip
            elif name in mh.TOUCH_TOOLS:
                response = ({"file": {"content": _NUMBERED.sub("", result)}}
                            if name == "Read" else {})  # fmt: skip
                out.append({"tool_name": name, "tool_input": data, "tool_response": response})
    return out


def chain(arm: Path) -> dict[str, Any] | None:
    streams = sorted(arm.glob("stream-*.jsonl"), key=lambda p: int(p.stem.split("-")[1]))
    if len(streams) < 2:
        return None
    cwd = ""
    for line in streams[0].read_text(encoding="utf-8").splitlines()[:5]:
        cwd = cwd or str(json.loads(line).get("cwd") or "")
    cwd = cwd.replace("\\", "/")
    prev: dict[str, tuple[str, set[str]]] = {}
    requests = []
    for stream in streams:
        i = int(stream.stem.split("-")[1])
        now = patch_files(arm / f"diff-{i}.patch")
        changed = sorted(f for f in set(now) | set(prev) if now.get(f, ("",))[0] != prev.get(
            f, ("",))[0])  # fmt: skip
        added = {f: now[f][1] - prev.get(f, ("", set()))[1] for f in changed if f in now}
        lost = {f: prev[f][1] - now.get(f, ("", set()))[1] for f in changed if f in prev}
        entries = entries_of(stream)
        found, _ = ep.episodes_of(entries, session=arm.name, cwd=cwd)
        record = replace(found[-1], index=i, session=f"{arm.parent.name[:20]}-{arm.name}") \
            if found else None  # fmt: skip
        inputs = [json.dumps(b.get("input") or {}) for e in entries for b in blocks_of(e["message"])
                  if isinstance(b, dict) and b.get("type") == "tool_use"]  # fmt: skip
        named = [f for f in changed if f.rsplit("/", 1)[-1] in "\n".join(inputs)]
        requests.append({"i": i, "entries": entries, "record": record, "changed": set(changed),
                         "added": added, "lost": lost, "named": named})  # fmt: skip
        prev = now
    return {"arm": arm, "cwd": cwd, "requests": requests}


def with_tree(record: ep.Episode, request: dict[str, Any]) -> ep.Episode:
    extra = request["named"]
    wrote = {r: list(p) for r, p in record.wrote or ()}
    for f in extra:
        wrote[f] = list(dict.fromkeys([*wrote.get(f, []), *sorted(request["added"].get(f, ()))]))
    return replace(record, changed=tuple(dict.fromkeys([*record.changed, *extra])),
                   changed_raw=tuple(dict.fromkeys([*record.changed_raw, *extra])),
                   wrote=tuple((r, tuple(p)) for r, p in wrote.items()))  # fmt: skip


def label(later: dict[str, Any], earlier: dict[str, Any]) -> str:
    if any(earlier["added"].get(f, set()) & later["lost"].get(f, set()) for f in later["lost"]):
        return "lineage"
    return "file" if later["changed"] & earlier["changed"] else "none"


def score(found: list[dict[str, Any]], v6: bool) -> dict[str, Any]:
    n: dict[str, int] = defaultdict(int)
    for c in found:
        for k, target in enumerate(c["requests"]):
            pool_reqs = [r for r in c["requests"][:k] if r["record"] is not None]
            if not pool_reqs:
                continue
            pool = [with_tree(r["record"], r) if v6 else r["record"] for r in pool_reqs]
            labels = {p.key: label(target, r) for p, r in zip(pool, pool_reqs, strict=True)}
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["SANCHOPANZA_MEMORY_STORE"] = str(Path(tmp) / "store")
                transcript = Path(tmp) / "projects" / "p" / "t.jsonl"
                store = mh.store_for({"transcript_path": str(transcript)})
                ep.save(store, pool, keep_days=100_000)
                mh.note_live(store, "new", 0, frozenset(), c["cwd"])
                given: list[str] = []
                chars = 0
                for t in touches(target["entries"], bash=v6):
                    out = mh.touch({"hook_event_name": "PostToolUse", "session_id": "new",
                                    "transcript_path": str(transcript), "cwd": c["cwd"], **t})
                    text = out["hookSpecificOutput"]["additionalContext"] if out else ""
                    chars += len(text)
                    given.extend(shown_in(text, pool))
            related = {key for key, v in labels.items() if v != "none"}
            n["requests"] += 1
            n["chars"] += chars
            n["given"] += len(given)
            n["good"] += sum(labels[g] != "none" for g in given)
            n["good_lineage"] += sum(labels[g] == "lineage" for g in given)
            if related:
                n["with_related"] += 1
                n["hits"] += bool(related & set(given))
            else:
                n["unrelated"] += 1
                n["noisy"] += bool(given)
            n["records_changing_nothing"] += sum(not p.changed for p in pool)
            n["pool_records"] += len(pool)

    def ratio(a: str, b: str) -> float | None:
        return round(n[a] / n[b], 3) if n[b] else None

    return {"requests": n["requests"], "with_related": n["with_related"],
            "recall": ratio("hits", "with_related"), "precision": ratio("good", "given"),
            "lineage_precision": ratio("good_lineage", "given"),
            "noise": ratio("noisy", "unrelated"), "given": n["given"],
            "chars_per_request": ratio("chars", "requests"),
            "pool_records_changing_nothing": ratio("records_changing_nothing", "pool_records")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", default=str(RUNS))
    parser.add_argument("--model", default="sonnet")
    args = parser.parse_args(argv)
    for name in ("SANCHOPANZA_MEMORY_SELECT", "SANCHOPANZA_PROVIDER", "TYPESAFE_API_KEY"):
        os.environ.pop(name, None)
    arms = []
    for arm in sorted(Path(args.runs).glob("*/*")):
        first = arm / "stream-1.jsonl"
        if first.exists() and args.model in first.read_text(encoding="utf-8")[:4000]:
            found = chain(arm)
            if found:
                arms.append(found)
    print(f"{len(arms)} arms: " + ", ".join(f"{a['arm'].parent.name}/{a['arm'].name}"
                                             f" ({len(a['requests'])})" for a in arms))
    mh.SHELL_EDIT_RULE = False
    rows = {"v5": score(arms, False), "v6 read rule on Bash": score(arms, True)}
    mh.SHELL_EDIT_RULE = True
    rows["v6 edit rule on writing Bash"] = score(arms, True)
    for name, m in rows.items():
        print(name, json.dumps(m))
    OUT.write_text(json.dumps({args.model: rows}, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
