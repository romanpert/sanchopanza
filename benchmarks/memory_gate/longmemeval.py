"""The memory gate on LongMemEval S, gold labels
(`docs/results/2026-09-28-memory-gate/prereg-longmemeval.md`).

python benchmarks/memory_gate/longmemeval.py --dry        # baselines + null gate: free
python benchmarks/memory_gate/longmemeval.py --estimate   # expected calls, tokens, USD: free
python benchmarks/memory_gate/longmemeval.py --live --max-usd 0.60 --env-file PATH  # not run

The dataset is not redistributed: download `longmemeval_s_cleaned.json` from the Hugging Face
dataset `xiaowu0162/longmemeval-cleaned` into `~/.cache/sanchopanza/memory_gate/longmemeval/`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import pathlib
import random
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run  # noqa: E402

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.harness import memory_gate as mg  # noqa: E402
from sanchopanza.points import chunks, hierarchy, memory  # noqa: E402
from sanchopanza.providers.jev import DEFAULT_PRICE_PER_MTOK  # noqa: E402
from sanchopanza.providers.null import NullDecider  # noqa: E402
from sanchopanza.text import excerpt  # noqa: E402

RESULTS = run.RESULTS
PREREG = RESULTS / "prereg-longmemeval.md"
PREREG_HASH = RESULTS / "prereg-longmemeval.sha256"
DATA = run.CACHE / "longmemeval" / "longmemeval_s_cleaned.json"
DATA_SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
FIXTURE = run.CACHE / "longmemeval" / "decisions.jsonl"
SEED = 20260928
DEV, TEST, ABSTAIN = 10, 120, 20  # amendment 1 of prereg-longmemeval.md
ALL_CAP = 25_000
BM25_K = (1, 3, 5)
BOOT = 2_000
HYBRID_K = 5  # amendment 2: BM25 candidates judged in one in-context call
ARMS = (
    "nothing",
    "all@25k",
    *(f"bm25@{k}" for k in BM25_K),
    "triage",
    "gate",
    "hybrid",
    "hybrid+recall",
)


def prereg_hash() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    if not PREREG_HASH.exists() or PREREG_HASH.read_text().strip() != prereg_hash():
        raise SystemExit("prereg-longmemeval.md changed or was never hashed: nothing spent")


# --- data -------------------------------------------------------------------------------


def _listed(value: Any) -> list[Any]:
    """The cleaned release stores some lists as their Python repr."""
    if isinstance(value, str):
        import ast

        return list(ast.literal_eval(value))
    return list(value)


def load(path: pathlib.Path = DATA) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            **q,
            "answer_session_ids": _listed(q["answer_session_ids"]),
            "haystack_session_ids": _listed(q["haystack_session_ids"]),
            "haystack_dates": _listed(q["haystack_dates"]),
            "haystack_sessions": _listed(q["haystack_sessions"]),
        }
        for q in raw
    ]


def slices(questions: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    answerable = sorted(
        (q for q in questions if not q["question_id"].endswith("_abs")),
        key=lambda q: q["question_id"],
    )
    random.Random(SEED).shuffle(answerable)
    abstain = sorted(
        (q for q in questions if q["question_id"].endswith("_abs")), key=lambda q: q["question_id"]
    )
    random.Random(SEED).shuffle(abstain)
    return {
        "dev": answerable[:DEV],
        "test": answerable[DEV : DEV + TEST],
        "abstention": abstain[:ABSTAIN],
    }


def session_text(turns: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(f"{t.get('role', '')}: {t.get('content', '')}" for t in turns)


def memories_of(q: Mapping[str, Any]) -> list[mg.Memory]:
    """Sessions as memories. The title is index and date only: gold ids start with `answer_`."""
    return [
        mg.Memory(f"s{i + 1:02d}", str(date), "", session_text(turns))
        for i, (date, turns) in enumerate(
            zip(q["haystack_dates"], q["haystack_sessions"], strict=True)
        )
    ]


def gold_of(q: Mapping[str, Any]) -> set[int]:
    wanted = set(q["answer_session_ids"])
    return {i for i, sid in enumerate(q["haystack_session_ids"]) if sid in wanted}


def excerpt_ceiling(q: Mapping[str, Any], among: set[int] | None = None) -> tuple[int, int]:
    """(gold sessions whose evidence turn is visible in the excerpt, gold sessions with one).

    With `among`, only gold sessions in that set count as seen (the hybrid's candidates); the
    denominator stays every gold session with an evidence turn, so it bounds recall."""
    seen = total = 0
    for i in gold_of(q):
        turns = q["haystack_sessions"][i]
        evidence = [str(t.get("content", "")) for t in turns if t.get("has_answer")]
        if not evidence:
            continue
        total += 1
        shown = excerpt(session_text(turns), q["question"], chunks.PAGE_LIMIT)
        visible = any(_overlaps(e, shown) for e in evidence)
        seen += visible and (among is None or i in among)
    return seen, total


def _overlaps(evidence: str, shown: str, width: int = 40) -> bool:
    if len(evidence) <= width:
        return evidence in shown
    return any(evidence[s : s + width] in shown for s in range(0, len(evidence) - width + 1, 20))


# --- arms -------------------------------------------------------------------------------


def arm_all(q: Mapping[str, Any], ms: Sequence[mg.Memory]) -> set[int]:
    """Newest first by haystack date; a session is taken whole if it still fits."""
    order = sorted(range(len(ms)), key=lambda i: q["haystack_dates"][i], reverse=True)
    chosen, used = set(), 0
    for i in order:
        size = len(ms[i].body)
        if used + size <= ALL_CAP:
            chosen, used = {*chosen, i}, used + size
    return chosen


def bm25_ranked(q: Mapping[str, Any], ms: Sequence[mg.Memory]) -> list[int]:
    """Session indexes with a positive BM25 score, best first."""
    scores = run.triage_run.bm25_scores(q["question"], [m.body for m in ms])
    return [i for _, i in sorted(((s, i) for i, s in enumerate(scores) if s > 0), reverse=True)]


def arm_bm25(q: Mapping[str, Any], ms: Sequence[mg.Memory], k: int) -> set[int]:
    return set(bm25_ranked(q, ms)[:k])


async def arm_hybrid(squire: Squire, q: Mapping[str, Any], ms: Sequence[mg.Memory]) -> set[int]:
    """BM25 top-`HYBRID_K`, then `triage_pages` over them at `pages_in_context`. Nothing when
    the decider answered none of them (a failure injects nothing)."""
    candidates = bm25_ranked(q, ms)[:HYBRID_K]
    if not candidates:
        return set()
    pages = mg.pages_of([ms[i] for i in candidates], purpose=q["question"])
    verdicts = await squire.triage_pages(purpose=q["question"], pages=pages)
    if not any(p is not None for _, p in verdicts):
        return set()
    return {i for i, (keep, _) in zip(candidates, verdicts, strict=True) if keep}


async def arm_gate(squire: Squire, q: Mapping[str, Any], ms: Sequence[mg.Memory]) -> dict:
    recall = await squire.needs_recall(q["question"])
    verdicts = await mg.triage_memories(squire, q["question"], ms)
    answered = any(p is not None for _, p in verdicts)
    triage = {i for i, (keep, _) in enumerate(verdicts) if keep} if answered else set()
    return {"triage": triage, "gate": triage if recall.look else set(), "look": recall.look}


async def evaluate(questions: Sequence[Mapping[str, Any]], squire: Squire) -> list[dict]:
    rows: list[dict[str, Any]] = []
    for q in questions:
        ms = memories_of(q)
        gated = await arm_gate(squire, q, ms)
        hybrid = await arm_hybrid(squire, q, ms)
        chosen = {
            "nothing": set(),
            "all@25k": arm_all(q, ms),
            **{f"bm25@{k}": arm_bm25(q, ms, k) for k in BM25_K},
            "triage": gated["triage"],
            "gate": gated["gate"],
            "hybrid": hybrid,
            "hybrid+recall": hybrid if gated["look"] else set(),
        }
        seen, total = excerpt_ceiling(q)
        seen_hybrid, _ = excerpt_ceiling(q, among=set(bm25_ranked(q, ms)[:HYBRID_K]))
        rows = [
            *rows,
            {
                "id": q["question_id"],
                "type": q["question_type"],
                "gold": sorted(gold_of(q)),
                "sizes": [len(m.body) for m in ms],
                "chosen": {arm: sorted(s) for arm, s in chosen.items()},
                "look": gated["look"],
                "excerpt_seen": seen,
                "excerpt_total": total,
                "excerpt_seen_hybrid": seen_hybrid,
            },
        ]
    return rows


async def evaluate_slices(
    parts: Mapping[str, Sequence[Mapping[str, Any]]], squire: Squire
) -> dict[str, list[dict]]:
    """Every slice in ONE event loop: `ReplayFirst` holds an `asyncio.Lock`, and a second
    `asyncio.run` makes every contended acquire raise (the cascade run lost calls that way)."""
    return {k: await evaluate(v, squire) for k, v in parts.items()}


# --- metrics ----------------------------------------------------------------------------

Metric = Callable[[Sequence[Mapping[str, Any]], str], float | None]


def _parts(row: Mapping[str, Any], arm: str) -> tuple[set[int], set[int], int]:
    """(chosen, gold, chars). An arm that injects passages, not whole sessions, records its
    own character count in `row["injected"]` (amendment 3, the cascade)."""
    chosen, gold = set(row["chosen"][arm]), set(row["gold"])
    injected = (row.get("injected") or {}).get(arm)
    size = injected if injected is not None else sum(row["sizes"][i] for i in chosen)
    return chosen, gold, size


def recall(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    hit = sum(len(_parts(r, arm)[0] & set(r["gold"])) for r in rows)
    total = sum(len(r["gold"]) for r in rows)
    return hit / total if total else None


def any_hit(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return (
        sum(bool(set(r["chosen"][arm]) & set(r["gold"])) for r in rows) / len(rows)
        if rows
        else None
    )


def all_hit(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return sum(set(r["gold"]) <= set(r["chosen"][arm]) for r in rows) / len(rows) if rows else None


def chars(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return sum(_parts(r, arm)[2] for r in rows) / len(rows) if rows else None


def precision(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    chosen = sum(len(r["chosen"][arm]) for r in rows)
    hit = sum(len(set(r["chosen"][arm]) & set(r["gold"])) for r in rows)
    return hit / chosen if chosen else None


def quiet(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    return sum(not r["chosen"][arm] for r in rows) / len(rows) if rows else None


METRICS: dict[str, Metric] = {
    "recall": recall,
    "any_hit": any_hit,
    "all_hit": all_hit,
    "chars": chars,
    "precision": precision,
}


def bootstrap(rows: Sequence[Mapping[str, Any]], stat: Callable[[Sequence], float | None]):
    """(point, low, high): 95 % percentile interval over questions, seeded."""
    point = stat(rows)
    if point is None or not rows:
        return point, None, None
    rng = random.Random(SEED)
    draws = sorted(
        v
        for v in (stat([rows[rng.randrange(len(rows))] for _ in rows]) for _ in range(BOOT))
        if v is not None
    )
    lo, hi = draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]
    return _r(point), _r(lo), _r(hi)


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 4 if v <= 1 else 1)


def report(rows: Sequence[Mapping[str, Any]], arms: Sequence[str] = ARMS) -> dict[str, Any]:
    out: dict[str, Any] = {"questions": len(rows)}
    for arm in arms:
        out[arm] = {
            name: bootstrap(rows, lambda rs, f=f, a=arm: f(rs, a)) for name, f in METRICS.items()
        }
    out["gate_minus_bm25@3_recall"] = bootstrap(rows, lambda rs: _diff(rs, "gate", "bm25@3"))
    types = sorted({r["type"] for r in rows})
    out["by_type"] = {
        t: {
            arm: {
                name: _r(f([r for r in rows if r["type"] == t], arm))
                for name, f in METRICS.items()
                if name != "precision"
            }
            for arm in arms
        }
        | {"n": sum(r["type"] == t for r in rows)}
        for t in types
    }
    seen = sum(r["excerpt_seen"] for r in rows)
    total = sum(r["excerpt_total"] for r in rows)
    out["excerpt_ceiling"] = {
        "seen": seen,
        "seen_among_hybrid_candidates": sum(r["excerpt_seen_hybrid"] for r in rows),
        "with_evidence_turn": total,
    }
    out["hybrid_minus_bm25@3_recall"] = bootstrap(rows, lambda rs: _diff(rs, "hybrid", "bm25@3"))
    out["hybrid_minus_bm25@5_recall"] = bootstrap(rows, lambda rs: _diff(rs, "hybrid", "bm25@5"))
    out["hybrid_chars_over_bm25@3"] = bootstrap(rows, lambda rs: _ratio(rs, "hybrid", "bm25@3"))
    out["recall_skips"] = sum(not r["look"] for r in rows)
    return out


def _ratio(rows: Sequence[Mapping[str, Any]], a: str, b: str) -> float | None:
    ca, cb = chars(rows, a), chars(rows, b)
    return None if ca is None or not cb else ca / cb


def _diff(rows: Sequence[Mapping[str, Any]], a: str, b: str) -> float | None:
    ra, rb = recall(rows, a), recall(rows, b)
    return None if ra is None or rb is None else ra - rb


def abstention_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "questions": len(rows),
        **{arm: {"quiet": _r(quiet(rows, arm)), "chars": _r(chars(rows, arm))} for arm in ARMS},
    }


# --- estimate ---------------------------------------------------------------------------


def _call(state_qs: tuple[Mapping[str, Any], Mapping[str, Any]]) -> int:
    return run._body_chars(*state_qs)


def estimate_question(q: Mapping[str, Any]) -> dict[str, tuple[int, int]]:
    """(calls, JSON chars) per component, from the real states of one question.

    `triage_pessimistic` assumes a second full tournament round before the final (round one
    keeps more than `chunks.PAGE_MAX` sessions); `triage_central`, one round and the final."""
    question = q["question"]
    ms = memories_of(q)
    pages = mg.pages_of(ms, purpose=question)
    out = {"recall": (1, _call(memory.recall_questions(turn=question)))}
    if len(pages) <= chunks.PAGE_MAX:
        one = (1, _call(chunks.context_questions(purpose=question, pages=pages)))
        out = {**out, "triage_central": one, "triage_pessimistic": one}
    else:
        groups = hierarchy.groups(len(pages), chunks.PAGE_MAX)
        round_chars = sum(
            _call(chunks.context_questions(purpose=question, pages=[pages[i] for i in g]))
            for g in groups
        )
        final = _call(chunks.context_questions(purpose=question, pages=pages[: chunks.PAGE_MAX]))
        out = {
            **out,
            "triage_central": (len(groups) + 1, round_chars + final),
            "triage_pessimistic": (2 * len(groups) + 1, 2 * round_chars + final),
        }
    candidates = bm25_ranked(q, ms)[:HYBRID_K]
    hybrid_pages = mg.pages_of([ms[i] for i in candidates], purpose=question)
    hybrid = (
        (1, _call(chunks.context_questions(purpose=question, pages=hybrid_pages)))
        if candidates
        else (0, 0)
    )
    return {**out, "hybrid": hybrid}


def _usd(chars: int, per_token: float) -> tuple[int, float]:
    tokens = math.ceil(chars / per_token)
    return tokens, round(tokens * DEFAULT_PRICE_PER_MTOK / 1e6, 4)


def estimate(questions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every live call of the pre-registered run: recall, the gate's tournament, the hybrid."""
    totals: dict[str, tuple[int, int]] = {}
    for q in questions:
        for part, (calls, chars) in estimate_question(q).items():
            c, n = totals.get(part, (0, 0))
            totals = {**totals, part: (c + calls, n + chars)}
    central, per_c = ("recall", "triage_central", "hybrid"), run.CHARS_PER_TOKEN[0]
    worst, per_p = ("recall", "triage_pessimistic", "hybrid"), run.CHARS_PER_TOKEN[1]
    out: dict[str, Any] = {"questions": len(questions)}
    for part, (calls, chars) in totals.items():
        out = {**out, f"{part}_calls": calls, f"{part}_usd_central": _usd(chars, per_c)[1]}
    for label, parts, per in (("central", central, per_c), ("pessimistic", worst, per_p)):
        calls = sum(totals[p][0] for p in parts)
        tokens, usd = _usd(sum(totals[p][1] for p in parts), per)
        out = {**out, f"calls_{label}": calls, f"tokens_{label}": tokens, f"usd_{label}": usd}
    return out


# --- main -------------------------------------------------------------------------------


def _data_ok() -> None:
    if not DATA.exists():
        raise SystemExit(f"download longmemeval_s_cleaned.json into {DATA.parent} first")
    digest = hashlib.sha256(DATA.read_bytes()).hexdigest()
    if digest != DATA_SHA256:
        raise SystemExit(f"{DATA.name} is not the registered file ({digest[:12]}...)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--max-usd", type=float, default=0.60)
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    _data_ok()
    parts = slices(load())
    everything = [*parts["dev"], *parts["test"], *parts["abstention"]]
    cost = estimate(everything)
    if args.estimate:
        print(json.dumps({"slices": {k: len(v) for k, v in parts.items()}, **cost}, indent=1))
        return 0
    if args.live:
        require_prereg()
        if cost["usd_pessimistic"] > args.max_usd:
            raise SystemExit(f"estimate above --max-usd {args.max_usd}: nothing spent")
        squire, replay = _live_squire(args)
    else:
        squire, replay = (
            Squire(NullDecider(), thresholds=replace(Thresholds(), max_decisions=10**7)),
            None,
        )
    rows = asyncio.run(evaluate_slices(parts, squire))
    out = {
        "mode": "live" if args.live else "dry (null decider: triage and gate inject nothing)",
        "estimate": cost,
        "dev": report(rows["dev"]),
        "test": report(rows["test"]),
        "abstention": abstention_report(rows["abstention"]),
    }
    if replay is not None:
        out = {
            **out,
            "complete": not squire.exhausted and not replay.missing and not replay.failed,
            "failed_calls": replay.failed,
            "live_calls": replay.asked,
            "spent_usd": round(squire.meter.cost_usd, 4),
        }
    text = json.dumps(out, indent=1)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def _live_squire(args: Any) -> tuple[Squire, Any]:
    from sanchopanza.providers import create
    from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else RecordedDecider([])
    live = RecordingDecider(create("jev", api_key=run._key(args.env_file)), FIXTURE)
    replay = _Counted(run.triage_run.ReplayFirst(recorded, live))
    thresholds = replace(Thresholds(), max_decisions=10**6, max_usd=args.max_usd)
    return Squire(replay, thresholds=thresholds), replay


class _Counted(run.Guarded):
    """`Guarded` that also exposes the replay's own counters."""

    @property
    def missing(self) -> int:
        return self._inner.missing

    @property
    def asked(self) -> int:
        return self._inner.asked


if __name__ == "__main__":
    sys.exit(main())
