"""A third held-out set for v5: sessions nobody has built, read or scored. Free (ids only).

    python benchmarks/memory_real/select_v5.py         # writes OUT/selection-3.json
    python benchmarks/memory_real/select_v5.py fetch   # transcripts, capped at FETCH_CAP_BYTES

SWE-chat has no eligible group left outside selection.json and selection-2.json, but those
groups' windows took up to WINDOW of their sessions. Here, per used group, one run of at least
two consecutive sessions none of which was in a window (a seeded random run, and a window of up
to WINDOW consecutive sessions from a seeded random start in it), plus every group of exactly
two sessions (below the old threshold of three). Same people and repositories as seen data for
the first kind: declared; nothing was tuned per person or repository.
"""

from __future__ import annotations

import json
import random
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build  # noqa: E402
import select_v4  # noqa: E402

SEED = 20261003
SELECTION_3 = build.OUT / "selection-3.json"
FETCH_CAP_BYTES = 1_500_000_000  # the laptop's disk is at 99 %: this set's own cap


def runs_outside(rows: list[dict[str, Any]], used: set[str]) -> list[list[dict[str, Any]]]:
    """Maximal runs of consecutive sessions (by time) none of which was used, of length >= 2."""
    runs: list[list[dict[str, Any]]] = [[]]
    for r in rows:
        if r["session_id"] in used:
            runs.append([])
        else:
            runs[-1].append(r)
    return [run for run in runs if len(run) >= 2]


def select() -> int:
    names = set(json.loads((build.CACHE / "names.json").read_text(encoding="utf-8")))
    used: set[str] = set()
    for path in (build.SELECTION, select_v4.SELECTION_2):
        used |= {s for g in json.loads(path.read_text(encoding="utf-8"))["groups"]
                 for s in g["sessions"]}  # fmt: skip
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in build.sessions_table():
        if (r["agent"] in build.AGENTS and r["created_at"] is not None and r["repo_id"]
                and r["user_id"] and f"{r['session_id']}.jsonl" in names):  # fmt: skip
            groups[(r["repo_id"], r["user_id"])].append(r)
    rng = random.Random(SEED)
    chosen = []
    for n, key in enumerate(sorted(groups)):
        rows = sorted(groups[key], key=lambda r: r["created_at"])
        ids = {r["session_id"] for r in rows}
        if used & ids:
            runs = runs_outside(rows, used)
            if not runs:
                continue
            run = runs[rng.randrange(len(runs))]
            kind = "outside-window"
        elif len(rows) == 2:
            run, kind = rows, "two-sessions"
        else:
            continue
        width = min(build.WINDOW, len(run))
        start = rng.randrange(0, len(run) - width + 1)
        chosen.append({"group": 300 + n, "split": "held3", "kind": kind, "repo_id": key[0],
                       "sessions": [r["session_id"] for r in run[start:start + width]]})
    payload = {"source": build.DATASET, "seed": SEED, "groups": chosen}
    SELECTION_3.write_text(json.dumps(payload, indent=1), encoding="utf-8", newline="\n")
    kinds = defaultdict(int)
    for g in chosen:
        kinds[g["kind"]] += 1
    print(f"{len(chosen)} groups {dict(kinds)}, {sum(len(g['sessions']) for g in chosen)} sessions")
    return 0


def fetch() -> int:
    from swechat import _get  # benchmarks/candor_external, on build's path

    folder = build.CACHE / "transcripts"
    added = 0
    for group in json.loads(SELECTION_3.read_text(encoding="utf-8"))["groups"]:
        for sid in group["sessions"]:
            target = folder / f"{sid}.jsonl"
            if target.exists():
                continue
            if added > FETCH_CAP_BYTES:
                raise SystemExit(f"stopped at {added / 1e9:.2f} GB added (FETCH_CAP_BYTES)")
            cached = build.SOURCE / "transcripts" / f"{sid}.jsonl"
            data = cached.read_bytes() if cached.exists() else _get(
                f"https://huggingface.co/datasets/{build.DATASET}/resolve/main/transcripts/"
                f"{urllib.parse.quote(sid + '.jsonl')}")  # fmt: skip
            target.write_bytes(data)
            added += len(data)
    print(f"{added / 1e9:.2f} GB added to {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(fetch() if sys.argv[1:] == ["fetch"] else select())
