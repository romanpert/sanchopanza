"""Amendment 4 of `prereg-longmemeval.md`, EXPLORATORY: the cascade against BM25 at equal text.

python benchmarks/memory_gate/budget.py --out docs/results/2026-09-28-memory-gate/budget.json

Free: the cascade is replayed from `decisions-cascade.jsonl` (no live decider; a missing
decision aborts the run instead of being answered by anyone), on the 101 test questions the
live run covered. Every baseline is BM25 at a character budget: the cascade's own output on
that question (paired) or a fixed 1,500 characters.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cascade as cas  # noqa: E402
import longmemeval as lme  # noqa: E402
import run  # noqa: E402

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402
from sanchopanza.text import split_sentences  # noqa: E402

TEST_RUN = 101  # the prefix of the test slice the live cascade covered
FIXED = 1_500
BASELINES = ("bm25-passages", "bm25-sentences", "bm25-sessions")

Unit = tuple[int, str]  # (session index, text)


# --- units and filling ------------------------------------------------------------------


def units(q: Mapping[str, Any], level: str) -> list[Unit]:
    """Every session of the haystack as the cascade's paragraphs, or their sentences."""
    out: list[Unit] = []
    for i, turns in enumerate(q["haystack_sessions"]):
        for _, paragraph in cas.paragraphs_of(turns):
            pieces = [paragraph] if level == "paragraph" else split_sentences(paragraph)
            out = [*out, *((i, p) for p in pieces)]
    return out


def ranked(question: str, pool: Sequence[Unit]) -> list[Unit]:
    """BM25 order, positive scores only (a unit sharing no word with the question is noise)."""
    if not pool:
        return []
    scores = run.triage_run.bm25_scores(question, [text for _, text in pool])
    order = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: -scores[i])
    return [pool[i] for i in order]


def fill(order: Sequence[Unit], budget: int) -> list[Unit]:
    """Units in order until `budget` characters; the last one is cut to fit exactly."""
    out: list[Unit] = []
    used = 0
    for session, text in order:
        if used >= budget:
            break
        room = budget - used
        piece = text if len(text) <= room else text[:room]
        out = [*out, (session, piece)]
        used += len(piece)
    return out


def sessions_at(q: Mapping[str, Any], budget: int) -> list[Unit]:
    ms = lme.memories_of(q)
    order = [(i, ms[i].body) for i in lme.bm25_ranked(q, ms)]
    return fill(order, budget)


def baseline(q: Mapping[str, Any], name: str, budget: int) -> list[Unit]:
    if budget <= 0:
        return []
    if name == "bm25-sessions":
        return sessions_at(q, budget)
    level = "paragraph" if name == "bm25-passages" else "sentence"
    return fill(ranked(q["question"], units(q, level)), budget)


# --- evidence ---------------------------------------------------------------------------


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def evidence_turns(q: Mapping[str, Any]) -> list[str]:
    gold = lme.gold_of(q)
    return [
        _flat(str(t.get("content", "")))
        for i, turns in enumerate(q["haystack_sessions"])
        if i in gold
        for t in turns
        if t.get("has_answer")
    ]


def touches(evidence: Sequence[str], injected: Sequence[Unit]) -> bool | None:
    """None when the question marks no evidence turn; else whether the text touches one."""
    if not evidence:
        return None
    text = " \n ".join(_flat(t) for _, t in injected)
    return any(lme._overlaps(e, text) for e in evidence if e)


# --- rows and report --------------------------------------------------------------------


def entry(injected: Sequence[Unit], evidence: Sequence[str]) -> dict[str, Any]:
    return {
        "selected": sorted({s for s, _ in injected}),
        "chars": sum(len(t) for _, t in injected),
        "evidence": touches(evidence, injected),
    }


async def cascade_units(squire: Squire, q: Mapping[str, Any]) -> list[Unit]:
    ms = lme.memories_of(q)
    out: list[Unit] = []
    for i in lme.bm25_ranked(q, ms)[: cas.CANDIDATES]:
        kept, _, _ = await cas.cascade_kept(squire, q["question"], q["haystack_sessions"][i])
        out = [*out, *((i, s) for s in kept)]
    return out


async def rows_for(questions: Sequence[Mapping[str, Any]], squire: Squire) -> list[dict]:
    rows: list[dict[str, Any]] = []
    for q in questions:
        evidence = evidence_turns(q)
        own = await cascade_units(squire, q)
        paired = sum(len(t) for _, t in own)
        arms = {"cascade": entry(own, evidence)}
        for name in BASELINES:
            arms = {
                **arms,
                f"{name}@paired": entry(baseline(q, name, paired), evidence),
                f"{name}@{FIXED}": entry(baseline(q, name, FIXED), evidence),
            }
        rows = [*rows, {"id": q["question_id"], "gold": sorted(lme.gold_of(q)), "arms": arms}]
    return rows


def _recall(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    hit = sum(len(set(r["arms"][arm]["selected"]) & set(r["gold"])) for r in rows)
    total = sum(len(r["gold"]) for r in rows)
    return hit / total if total else None


def _any(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return (
        sum(bool(set(r["arms"][arm]["selected"]) & set(r["gold"])) for r in rows) / len(rows)
        if rows
        else None
    )


def _all(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return (
        sum(set(r["gold"]) <= set(r["arms"][arm]["selected"]) for r in rows) / len(rows)
        if rows
        else None
    )


def _evidence(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    marked = [r["arms"][arm]["evidence"] for r in rows if r["arms"][arm]["evidence"] is not None]
    return sum(marked) / len(marked) if marked else None


def _chars(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return sum(r["arms"][arm]["chars"] for r in rows) / len(rows) if rows else None


MEASURES = {
    "recall": _recall,
    "any_hit": _any,
    "all_hit": _all,
    "evidence": _evidence,
    "chars": _chars,
}


def report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    arms = list(rows[0]["arms"]) if rows else []
    out: dict[str, Any] = {
        "questions": len(rows),
        "with_evidence_turn": sum(r["arms"]["cascade"]["evidence"] is not None for r in rows),
    }
    for arm in arms:
        out[arm] = {
            k: lme.bootstrap(rows, lambda rs, f=f, a=arm: f(rs, a)) for k, f in MEASURES.items()
        }
    for arm in arms:
        if arm == "cascade":
            continue
        for k in ("recall", "evidence"):
            f = MEASURES[k]
            out[f"cascade_minus_{arm}_{k}"] = lme.bootstrap(
                rows, lambda rs, f=f, a=arm: _minus(f(rs, "cascade"), f(rs, a))
            )
    return out


def _minus(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    lme._data_ok()
    questions = lme.slices(lme.load())["test"][:TEST_RUN]
    recorded = RecordedDecider.from_file(cas.FIXTURE)
    replay = lme._Counted(run.triage_run.ReplayFirst(recorded, None))
    squire = Squire(replay, thresholds=replace(Thresholds(), max_decisions=10**7, max_usd=10.0))
    rows = asyncio.run(rows_for(questions, squire))
    if replay.missing or replay.failed:
        raise SystemExit(
            f"{replay.missing} decisions missing from the recording, {replay.failed} failed: "
            "not reported"
        )
    out = {"mode": "exploratory, replayed, free (amendment 4)", **report(rows)}
    text = json.dumps(out, indent=1)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
