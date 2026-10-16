"""Memory's C8 code on SWE-chat's first prompts, free (docs/results/2026-10-16-memory-c8-replay).

The items are lot memgate-hook's (docs/results/2026-10-16-memgate-hook): the first request of
every later session of the three public SWE-chat sets of docs/results/2026-10-01-memory-real,
each with its whole first prompt, the records of the group's earlier sessions (its pool) and
labels by code from the transcripts (`lineage`/`file`/none). Built by
`benchmarks/memgate_hook/memgate_hook.py --build` into the local cache; read here, never
redistributed. Counted:
- the prompts the continuation cue fires on (`memory_recall.continuation`), which kind of cue
  (an opening go-on verb, or a question about where the last session left off), and the label
  of the record `memory_recall.continued` would give. An item carries no time of its own, so
  the 7-day bound is not applied: the count is an upper bound;
- the prompts longer than `episodes.REQUEST_CHARS`, and among them those with a plan-shaped
  sentence (`memory_rules.is_plan`) past the head a head cut kept, and whether the head-and-tail
  record (`episodes.head_tail`) keeps one of them.
The output holds counts only: no prompt text.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_recall as mrc  # noqa: E402
from sanchopanza.harness import memory_rules as mr  # noqa: E402
from sanchopanza.points.rules import sentences  # noqa: E402

ITEMS = Path.home() / ".cache" / "sanchopanza" / "memory-real" / "items-memgate-hook.jsonl"


def cue_kind(prompt: str) -> str:
    return "opening" if mrc._CONTINUE.search(prompt.strip()) else "left_off"


def count_item(item: dict[str, Any], counts: Counter[str]) -> Counter[str]:
    prompt = str(item.get("prompt") or "").strip()
    found: Counter[str] = Counter({"items": 1})
    if len(prompt) > ep.REQUEST_CHARS:
        found["long"] += 1
        head = prompt[: ep.REQUEST_CHARS]
        plans = [s for s in sentences(prompt) if mr.is_plan(s) and s not in head]
        if plans:
            found["long_plan_past_head"] += 1
            kept = ep.head_tail(prompt, ep.REQUEST_CHARS)
            found["long_plan_past_head_kept"] += any(s in kept for s in plans)
    if mrc.continuation(prompt):
        pool = [ep.Episode.from_dict(r) for r in item.get("pool") or []]
        now = max((e.at for e in pool), default=0.0) + 1.0  # no time of its own: no age bound
        given = mrc.continued(prompt, pool, now)
        labels = item.get("labels") or {}
        found["cue"] += 1
        found[f"cue_{cue_kind(prompt)}"] += 1
        found[f"cue_given_{labels.get(given.key, 'none') if given else 'nothing'}"] += 1
        related = any(v != "none" for v in labels.values())
        found["cue_related_in_pool" if related else "cue_nothing_related_in_pool"] += 1
    return counts + found


KEYS = ("items", "long", "long_plan_past_head", "long_plan_past_head_kept", "cue", "cue_opening",
        "cue_left_off", "cue_given_lineage", "cue_given_file", "cue_given_none",
        "cue_given_nothing", "cue_related_in_pool", "cue_nothing_related_in_pool")  # fmt: skip


def run(items: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    with items.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                counts = count_item(json.loads(line), counts)
    return {"items_file": items.name, **{k: counts[k] for k in KEYS},
            **{k: v for k, v in sorted(counts.items()) if k not in KEYS}}  # fmt: skip
