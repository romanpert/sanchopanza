"""Memory between sessions on real people's sessions: SWE-chat, not our benchmark or our product.

    python benchmarks/memory_real/build.py select   # free: groups and windows, ids only, sealed
    python benchmarks/memory_real/build.py fetch    # free: transcripts from Hugging Face (token)
    python benchmarks/memory_real/build.py items    # free: requests, pools and labels by code

Dataset: `SALT-NLP/SWE-chat` (ODC-BY), real sessions between developers and coding agents in
public repositories. A group is one person on one repository; its window is up to WINDOW
consecutive Claude Code sessions. Each later session's every request is an item: the pool is the
records (`context.episodes`) of the window's earlier sessions, what `install --memory` would hold
when that session starts, and each record carries a label computed from the transcripts:

- `lineage`: the request's edits rewrite a line the record's edits wrote (the new work changes
  the earlier work itself);
- `file`: the request changes a file the record changed;
- none otherwise.

Groups are split into development and held out before anything is scored; the selection is
written to the repository (ids only) and sealed. Text stays in the cache (CACHE).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "benchmarks" / "candor_external"))

from labels import edits_of, lineage, written_lines  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402

DATASET = "SALT-NLP/SWE-chat"
SOURCE = Path.home() / ".cache" / "sanchopanza" / "candor-external" / "swe-chat"
CACHE = Path.home() / ".cache" / "sanchopanza" / "memory-real"
OUT = REPO / "docs" / "results" / "2026-10-01-memory-real"
SELECTION = OUT / "selection.json"
SEED = 20261001
GROUPS = 60
WINDOW = 6
AGENTS = ("Claude Code", "claude-code")
FETCH_CAP_BYTES = 2_000_000_000  # disk is short: stop downloading past this


def sessions_table() -> list[dict[str, Any]]:
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    cols = ["session_id", "repo_id", "user_id", "agent", "created_at"]
    t = pq.read_table(SOURCE / "sessions.parquet", columns=cols)
    stamp = pc.cast(pc.cast(t["created_at"], "timestamp[ns]"), "int64")
    t = t.set_column(t.schema.get_field_index("created_at"), "created_at", stamp)
    return t.to_pylist()


def select() -> None:
    from swechat import _transcript_names

    listed = CACHE / "names.json"
    if not listed.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        listed.write_text(json.dumps(sorted(_transcript_names())), encoding="utf-8")
    names = set(json.loads(listed.read_text(encoding="utf-8")))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in sessions_table():
        if (r["agent"] in AGENTS and r["created_at"] is not None and r["repo_id"]
                and r["user_id"] and f"{r['session_id']}.jsonl" in names):  # fmt: skip
            groups[(r["repo_id"], r["user_id"])].append(r)
    eligible = sorted(k for k, v in groups.items() if len(v) >= 3)
    rng = random.Random(SEED)
    rng.shuffle(eligible)
    chosen = []
    for n, key in enumerate(eligible[:GROUPS]):
        rows = sorted(groups[key], key=lambda r: r["created_at"])
        width = min(WINDOW, len(rows))
        start = rng.randrange(0, len(rows) - width + 1)
        chosen.append({"group": n, "split": "dev" if n < GROUPS // 2 else "held",
                       "repo_id": key[0],
                       "sessions": [r["session_id"] for r in rows[start:start + width]]})  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"source": DATASET, "seed": SEED, "groups": chosen,
               "eligible_groups": len(eligible)}  # fmt: skip
    SELECTION.write_text(json.dumps(payload, indent=1), encoding="utf-8", newline="\n")
    print(f"{len(chosen)} groups of {len(eligible)} eligible, "
          f"{sum(len(g['sessions']) for g in chosen)} sessions")  # fmt: skip


def fetch() -> None:
    import urllib.parse

    from swechat import _get

    folder = CACHE / "transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    total = sum(p.stat().st_size for p in folder.glob("*.jsonl"))
    for group in json.loads(SELECTION.read_text(encoding="utf-8"))["groups"]:
        for sid in group["sessions"]:
            target = folder / f"{sid}.jsonl"
            cached = SOURCE / "transcripts" / f"{sid}.jsonl"
            if target.exists():
                continue
            if total > FETCH_CAP_BYTES:
                raise SystemExit(f"stopped at {total / 1e9:.2f} GB (FETCH_CAP_BYTES)")
            data = cached.read_bytes() if cached.exists() else _get(
                f"https://huggingface.co/datasets/{DATASET}/resolve/main/transcripts/"
                f"{urllib.parse.quote(sid + '.jsonl')}")  # fmt: skip
            target.write_bytes(data)
            total += len(data)
    print(f"{total / 1e9:.2f} GB in {folder}")


def cwd_of(entries: list[Any]) -> str:
    return next((str(e["cwd"]) for e in entries if isinstance(e.get("cwd"), str)), "")


def session_parts(sid: str) -> dict[str, Any] | None:
    """A session's records, each request's messages, and what each request wrote and changed."""
    path = CACHE / "transcripts" / f"{sid}.jsonl"
    if not path.exists():
        return None
    entries = ep.entries_of(path)
    cwd = cwd_of(entries)
    records, _ = ep.episodes_of(entries, session=sid, cwd=cwd)
    split = ep.split_requests(entries)
    per_request = []
    for index, group in enumerate(split.groups, start=1):
        edits = edits_of(group, cwd)
        per_request.append({"index": index, "request": ep._request(group[0]),
                            "changed": sorted({e.path for e in edits}),
                            "removed": sorted({ln for e in edits for ln in e.removed}),
                            "written": sorted(written_lines(edits))})  # fmt: skip
    return {"sid": sid, "records": records, "requests": per_request}


def items() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    out = CACHE / "items.jsonl"
    counts: dict[str, int] = defaultdict(int)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for group in selection["groups"]:
            parts = [session_parts(s) for s in group["sessions"]]
            for position in range(1, len(parts)):
                target = parts[position]
                if target is None:
                    continue
                earlier = [p for p in parts[:position] if p is not None]
                pool = [r for p in earlier for r in p["records"]]
                wrote = {f"{p['sid']}-{q['index']:03d}": q
                         for p in earlier for q in p["requests"]}  # fmt: skip
                for request in target["requests"]:
                    labels = {}
                    for record in pool:
                        source = wrote.get(record.key, {"written": [], "changed": []})
                        labels[record.key] = (
                            "lineage" if lineage(request["removed"], source["written"])
                            else "file" if set(request["changed"]) & set(record.changed)
                            else "none"
                        )  # fmt: skip
                    counts[f"{group['split']} requests"] += 1
                    counts[f"{group['split']} with lineage"] += "lineage" in labels.values()
                    counts[f"{group['split']} with file"] += "file" in labels.values()
                    handle.write(json.dumps({
                        "group": group["group"], "split": group["split"],
                        "session": group["sessions"][position], "index": request["index"],
                        "first": request["index"] == 1, "request": request["request"],
                        "pool": [r.to_dict() for r in pool], "labels": labels,
                    }, ensure_ascii=False) + "\n")  # fmt: skip
    print(dict(counts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("select", "fetch", "items"))
    args = parser.parse_args(argv)
    {"select": select, "fetch": fetch, "items": items}[args.action]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
