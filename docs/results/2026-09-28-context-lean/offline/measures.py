"""The three offline measures (O1 index stubs, O2 large outputs at arrival, O3 API rival).

Pure functions over the context bench's units (`benchmarks/context/build.py`: history,
future, lexical NEEDED labels). No network, no key, no decider: the one paid arm (O2 `jev`)
lives in `run.py` and only receives the rows this module prepares. See README.md.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sanchopanza.context import arrival, compact
from sanchopanza.context.transcript import Call
from sanchopanza.context.transcript import calls as calls_of
from sanchopanza.context.transcript import chars as chars_of
from sanchopanza.text import bm25_scores

KEEP_RECENT = 6  # compact.plan's default, the autopilot's
LIMITS = (120, 240, 480)
MAIN_LIMIT = 240
LARGE = 6_000  # arrival.Settings().threshold
HEAD_LINES = TAIL_LINES = 20
TOKENS_PER_CHAR = 0.3  # O3 trigger proxy, stated as an assumption in README.md
TRIGGERS = (30_000, 50_000, 100_000)  # 100,000 is the documented default
API_KEEP = 3
SPLITS = ("dev", "test", "all")


# --- shared -----------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def share(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "share": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


def present(tokens: Sequence[str], text: str) -> bool:
    """At least one token found literally (substring), as the bench's `present` counts it."""
    return any(t and t in text for t in tokens)


def in_split(rows: Sequence[Mapping[str, Any]], split: str) -> list[Mapping[str, Any]]:
    return [r for r in rows if split == "all" or r["split"] == split]


def masked_ids(history: Sequence[Mapping[str, Any]], found: Sequence[Call], turns: int) -> set:
    """What the autopilot's compaction masks (`compact` arm `mask`), at M = `turns`."""
    plan = compact._plan_mask(history, found, keep_recent=KEEP_RECENT, turns=turns)
    return {s.id for s in plan.steps if s.action == "stub"}


# --- O1: index stubs --------------------------------------------------------------------------


def o1_rows(unit: Mapping[str, Any], index_of: Callable[..., str]) -> list[dict[str, Any]]:
    """One row per result masked at M = 10: its label and what each stub variant shows."""
    history, labels = unit["history"], unit["labels"]
    found = calls_of(history)
    stubbed = masked_ids(history, found, compact.MASK_TURNS)
    rows = []
    for call in found:
        if call.id not in stubbed:
            continue
        hits = labels[call.id]["hits"]
        plain = compact.stub_text(call.tool, call.chars, Path("ARCHIVE"))
        row: dict[str, Any] = {
            "unit": unit["unit"],
            "split": unit["split"],
            "chars": call.chars,
            "needed": labels[call.id]["needed"],
            "plain_hit": present(hits, plain),
        }
        for limit in LIMITS:
            index = index_of(call.result, limit=limit)
            row[f"index{limit}_chars"] = len(index)
            row[f"index{limit}_hit"] = present(hits, index)
            row[f"head{limit}_chars"] = min(limit, call.chars)
            row[f"head{limit}_hit"] = present(hits, call.result[:limit])
        rows.append(row)
    return rows


def o1_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in SPLITS:
        part = in_split(rows, split)
        needed = [r for r in part if r["needed"]]
        freed = sum(r["chars"] for r in part)
        block: dict[str, Any] = {
            "masked": len(part),
            "needed_masked": len(needed),
            "freed_chars": freed,
            "plain_stub": share(sum(r["plain_hit"] for r in needed), len(needed)),
        }
        for limit in LIMITS:
            for kind in ("index", "head"):
                added = sum(r[f"{kind}{limit}_chars"] for r in part)
                block[f"{kind}{limit}"] = {
                    **share(sum(r[f"{kind}{limit}_hit"] for r in needed), len(needed)),
                    "chars_added": added,
                    "chars_per_stub": round(added / len(part), 1) if part else None,
                    "added_pct_of_freed": round(100 * added / freed, 2) if freed else None,
                }
        out[split] = block
    return out


# --- O2: large outputs at arrival -------------------------------------------------------------


def needed_lines(text: str, hits: Sequence[str]) -> list[int]:
    return [i for i, line in enumerate(text.splitlines()) if present(hits, line)]


def lines_kept(text: str, wanted: Sequence[int], output: str) -> int:
    """Needed lines whose stripped text appears in `output`: one rule for every arm, so an arm
    that returns text (free_cut, jev) and one that returns line indexes are scored alike."""
    lines = text.splitlines()
    return sum(1 for i in wanted if lines[i].strip() and lines[i].strip() in output)


def head_tail_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= HEAD_LINES + TAIL_LINES:
        return text
    return "\n".join(lines[:HEAD_LINES] + lines[-TAIL_LINES:])


def bm25_lines(text: str, purpose: str, budget: int) -> str:
    """Lines ranked by BM25 against the purpose, best first while they fit, in original order."""
    lines = text.splitlines()
    if budget >= len(text):
        return text
    scores = bm25_scores(purpose, lines)
    chosen, used = set(), 0
    for i in sorted(range(len(lines)), key=lambda j: (-scores[j], j)):
        size = len(lines[i]) + 1
        if used + size <= budget:
            chosen.add(i)
            used += size
    return "\n".join(lines[i] for i in sorted(chosen))


def as_text(result: Any, original: str) -> tuple[str, bool]:
    """(what the agent gets, cut?) from free_cut / arrival.cut: a Cut, a string or None."""
    if result is None:
        return original, False
    if isinstance(result, str):
        return result, result != original
    text = getattr(result, "text", None)
    return (original, False) if text is None else (str(text), True)


def large_calls(unit: Mapping[str, Any]) -> list[Call]:
    found = calls_of(unit["history"])
    return sorted((c for c in found if c.chars >= LARGE), key=lambda c: c.result_msg)


def purpose_for(unit: Mapping[str, Any], call: Call) -> str:
    return arrival.purpose_of(unit["history"][: call.result_msg], call.tool, call.input)


def o2_base(unit: Mapping[str, Any], call: Call) -> dict[str, Any]:
    hits = unit["labels"][call.id]["hits"]
    wanted = needed_lines(call.result, hits)
    return {
        "unit": unit["unit"],
        "split": unit["split"],
        "tool": call.tool,
        "chars": call.chars,
        "lines": len(call.result.splitlines()),
        "label_needed": unit["labels"][call.id]["needed"],
        "needed_lines": len(wanted),
        "wanted": wanted,
    }


def score_arm(row: dict[str, Any], call: Call, arm: str, output: str, cut: bool) -> None:
    row[f"{arm}_chars"] = len(output)
    row[f"{arm}_kept_lines"] = lines_kept(call.result, row["wanted"], output)
    row[f"{arm}_cut"] = cut


def o2_free_rows(
    unit: Mapping[str, Any], free_cut: Callable[..., Any], settings: Any
) -> list[dict[str, Any]]:
    rows = []
    for call in large_calls(unit):
        row = o2_base(unit, call)
        purpose = purpose_for(unit, call)
        ht = head_tail_lines(call.result)
        score_arm(row, call, "head_tail", ht, ht != call.result)
        fc, cut = as_text(free_cut(call.result, purpose, settings), call.result)
        score_arm(row, call, "free_cut", fc, cut)
        for name, budget in (("bm25_at_free_cut", len(fc)), ("bm25_at_head_tail", len(ht))):
            out = bm25_lines(call.result, purpose, budget)
            score_arm(row, call, name, out, out != call.result)
        rows.append(row)
    return rows


def o2_summary(rows: Sequence[Mapping[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in SPLITS:
        part = in_split(rows, split)
        with_lines = [r for r in part if r["needed_lines"]]
        total = sum(r["chars"] for r in part)
        block: dict[str, Any] = {
            "results": len(part),
            "label_needed": sum(r["label_needed"] for r in part),
            "with_needed_lines": len(with_lines),
            "needed_lines": sum(r["needed_lines"] for r in with_lines),
        }
        for arm in arms:
            if not part or f"{arm}_chars" not in part[0]:
                continue
            lines = sum(r["needed_lines"] for r in with_lines)
            block[arm] = {
                "all_needed_lines_kept": share(
                    sum(r[f"{arm}_kept_lines"] == r["needed_lines"] for r in with_lines),
                    len(with_lines),
                ),
                "needed_lines_kept": round(
                    sum(r[f"{arm}_kept_lines"] for r in with_lines) / lines, 4
                )
                if lines
                else None,
                "chars_kept_pct": round(100 * sum(r[f"{arm}_chars"] for r in part) / total, 2)
                if total
                else None,
                "results_cut": sum(r[f"{arm}_cut"] for r in part),
            }
        out[split] = block
    return out


# --- O3: the API's clear_tool_uses_20250919 --------------------------------------------------


def api_actions(
    history: Sequence[Mapping[str, Any]],
    found: Sequence[Call],
    trigger: int,
    keep: int = API_KEEP,
    clear_at_least: int | None = None,
) -> dict[str, str]:
    """The request at the cut as the API would edit it. Stateless per request: the client
    sends the whole history each time, so only this request's size matters."""
    if chars_of(history) * TOKENS_PER_CHAR < trigger:
        return {c.id: "keep" for c in found}
    order = sorted(range(len(found)), key=lambda i: (found[i].use_msg, i))
    kept = {found[i].id for i in order[-keep:]} if keep else set()
    actions = {c.id: "keep" if c.id in kept else "stub" for c in found}
    if clear_at_least is not None:
        cleared = sum(c.chars for c in found if actions[c.id] == "stub") * TOKENS_PER_CHAR
        if cleared < clear_at_least:
            return {c.id: "keep" for c in found}
    return actions


def o3_arm_actions(unit: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    history = unit["history"]
    found = calls_of(history)
    out = {}
    for turns in (10, 3):
        stubbed = masked_ids(history, found, turns)
        out[f"mask_{turns}"] = {c.id: "stub" if c.id in stubbed else "keep" for c in found}
    for trigger in TRIGGERS:
        out[f"api_T{trigger // 1000}k"] = api_actions(history, found, trigger)
    out["api_always"] = api_actions(history, found, 0)
    return out


def o3_triggered(units: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    est = [chars_of(u["history"]) * TOKENS_PER_CHAR for u in units]
    return {f"T{t // 1000}k": sum(e >= t for e in est) for t in TRIGGERS}
