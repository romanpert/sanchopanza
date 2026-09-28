"""Amendment 3 of `prereg-longmemeval.md`: the passage cascade over the BM25 candidates.

python benchmarks/memory_gate/cascade.py --dry         # BM25 arms + null cascade: free
python benchmarks/memory_gate/cascade.py --estimate    # expected calls and USD: free
python benchmarks/memory_gate/cascade.py --live --max-usd 0.30 --env-file PATH

For each of the BM25 top-5 sessions of a question, `Squire.select_passages` over the WHOLE
session split into paragraphs: a tournament at `document_paragraphs`, then sentences with a
window of `document_window` in the paragraphs that pass. A session is selected when any of
its passages is kept; what is injected is the kept sentences only. Only the cascade is asked
here: the gate and hybrid arms were measured in `longmemeval-live.json`, and replaying them
would charge their recorded cost against this run's cap.
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

import longmemeval as lme  # noqa: E402
import run  # noqa: E402

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.points import chunks, hierarchy  # noqa: E402
from sanchopanza.providers.jev import DEFAULT_PRICE_PER_MTOK  # noqa: E402
from sanchopanza.providers.null import NullDecider  # noqa: E402
from sanchopanza.text import split_sentences  # noqa: E402

SMOKE = 3  # dev questions, a pipeline check only
PARAGRAPH_LIMIT = chunks.PAGE_LIMIT  # a paragraph the tournament reads whole
CANDIDATES = lme.HYBRID_K
ARMS = ("nothing", "bm25@1", "bm25@3", "bm25@5", "cascade")
ABSTAIN = 10  # amendment 3: the first 10 of the shuffled abstention stratum
MIN_TEST = 60  # below this many test questions the run is not made
# Characters per billed token, MEASURED on the 740 recorded LongMemEval calls of the gate and
# hybrid run: in-context page calls median 3.96, minimum 3.34. Sentence calls are not
# measured on this data; the pessimistic figure for them is the memory_write median, 3.0.
TOURNAMENT_CPT = (3.96, 3.34)
SENTENCE_CPT = (3.96, 3.0)
FIXTURE = run.CACHE / "longmemeval" / "decisions-cascade.jsonl"


# --- paragraphs -------------------------------------------------------------------------


def _pack(pieces: Sequence[str], limit: int) -> list[str]:
    """Join consecutive pieces while they fit; split an oversized one by sentences."""
    units: list[str] = []
    for piece in pieces:
        if len(piece) <= limit:
            units = [*units, piece]
            continue
        for sentence in split_sentences(piece):
            units = [*units, *(sentence[i : i + limit] for i in range(0, len(sentence), limit))]
    out: list[str] = []
    for unit in units:
        if out and len(out[-1]) + 1 + len(unit) <= limit:
            out = [*out[:-1], out[-1] + "\n" + unit]
        else:
            out = [*out, unit]
    return out


def paragraphs_of(turns: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """(title, paragraph) for a whole session. Each turn is split on blank lines (an
    oversized piece by sentences), its first piece prefixed with the role, and consecutive
    pieces are packed ACROSS turns up to `PARAGRAPH_LIMIT` characters, so the tournament reads
    each paragraph whole and pays for as few questions as the text allows. Titled by the turns
    it spans."""
    units: list[tuple[int, str]] = []
    for n, turn in enumerate(turns):
        text = str(turn.get("content", ""))
        pieces = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        role = str(turn.get("role", ""))
        split = _pack(pieces, PARAGRAPH_LIMIT - len(role) - 2) if pieces else []
        units = [*units, *((n, f"{role}: {x}" if k == 0 else x) for k, x in enumerate(split))]
    out: list[tuple[list[int], str]] = []
    for n, unit in units:
        if out and len(out[-1][1]) + 1 + len(unit) <= PARAGRAPH_LIMIT:
            spans, text = out[-1]
            out = [*out[:-1], ([*spans, n], text + "\n" + unit)]
        else:
            out = [*out, ([n], unit)]
    return [(_title(spans), text) for spans, text in out]


def _title(spans: Sequence[int]) -> str:
    first, last = min(spans) + 1, max(spans) + 1
    return f"turn {first}" if first == last else f"turns {first}-{last}"


# --- the arm ----------------------------------------------------------------------------


async def cascade_session(
    squire: Squire, question: str, turns: Sequence[Mapping[str, Any]]
) -> tuple[bool, int, int, int]:
    """(selected, injected chars, paragraphs, paragraphs sent to the sentence stage) for one
    session. Nothing when the decider answered no sentence of it: a failure injects nothing."""
    kept, paragraphs, sent = await cascade_kept(squire, question, turns)
    return bool(kept), sum(len(s) + 1 for s in kept), paragraphs, sent


async def cascade_kept(
    squire: Squire, question: str, turns: Sequence[Mapping[str, Any]]
) -> tuple[list[str], int, int]:
    """(kept sentences, paragraphs, paragraphs sent on). No sentence when the decider
    answered none (amendment 4 reads the text itself, not only its length)."""
    pages = paragraphs_of(turns)
    if not pages:
        return [], 0, 0
    verdicts = await squire.select_passages(purpose=question, pages=pages)
    answered = False
    kept: list[str] = []
    for (_, paragraph), sentences in zip(pages, verdicts, strict=True):
        if sentences is None:
            continue
        answered = answered or any(p is not None for _, p in sentences)
        parts = split_sentences(paragraph)
        kept = [*kept, *(s for s, (keep, _) in zip(parts, sentences, strict=True) if keep)]
    sent = sum(v is not None for v in verdicts)
    return (kept if answered else []), len(pages), sent


async def arm_cascade(squire: Squire, q: Mapping[str, Any], ms: Sequence[Any]) -> dict:
    candidates = lme.bm25_ranked(q, ms)[:CANDIDATES]
    results = await asyncio.gather(
        *(cascade_session(squire, q["question"], q["haystack_sessions"][i]) for i in candidates)
    )
    return {
        "chosen": {i for i, r in zip(candidates, results, strict=True) if r[0]},
        "injected": sum(r[1] for r in results),
        "paragraphs": sum(r[2] for r in results),
        "paragraphs_sent": sum(r[3] for r in results),
    }


async def evaluate(questions: Sequence[Mapping[str, Any]], squire: Squire) -> list[dict]:
    rows: list[dict[str, Any]] = []
    for q in questions:
        ms = lme.memories_of(q)
        arm = await arm_cascade(squire, q, ms)
        gold = lme.gold_of(q)
        candidates = set(lme.bm25_ranked(q, ms)[:CANDIDATES])
        rows = [
            *rows,
            {
                "id": q["question_id"],
                "type": q["question_type"],
                "gold": sorted(gold),
                "sizes": [len(m.body) for m in ms],
                "chosen": {
                    "nothing": [],
                    **{f"bm25@{k}": sorted(lme.arm_bm25(q, ms, k)) for k in (1, 3, 5)},
                    "cascade": sorted(arm["chosen"]),
                },
                "injected": {"cascade": arm["injected"]},
                "gold_in_candidates": len(gold & candidates),
                "paragraphs": arm["paragraphs"],
                "paragraphs_sent": arm["paragraphs_sent"],
            },
        ]
    return rows


# --- report -----------------------------------------------------------------------------


def report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"questions": len(rows)}
    for arm in ARMS:
        out[arm] = {
            name: lme.bootstrap(rows, lambda rs, f=f, a=arm: f(rs, a))
            for name, f in lme.METRICS.items()
        }
    out["cascade_minus_bm25@3_recall"] = lme.bootstrap(
        rows, lambda rs: lme._diff(rs, "cascade", "bm25@3")
    )
    out["cascade_minus_bm25@5_recall"] = lme.bootstrap(
        rows, lambda rs: lme._diff(rs, "cascade", "bm25@5")
    )
    out["cascade_chars_over_bm25@3"] = lme.bootstrap(
        rows, lambda rs: lme._ratio(rs, "cascade", "bm25@3")
    )
    gold = sum(len(r["gold"]) for r in rows)
    out["ceiling_gold_in_candidates"] = {
        "in_candidates": sum(r["gold_in_candidates"] for r in rows),
        "gold": gold,
    }
    types = sorted({r["type"] for r in rows})
    out["by_type"] = {
        t: {
            "n": sum(r["type"] == t for r in rows),
            **{
                arm: {
                    name: lme._r(f([r for r in rows if r["type"] == t], arm))
                    for name, f in lme.METRICS.items()
                    if name != "precision"
                }
                for arm in ("bm25@3", "cascade")
            },
        }
        for t in types
    }
    return out


def abstention(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "questions": len(rows),
        **{
            a: {"quiet": lme._r(lme.quiet(rows, a)), "chars": lme._r(lme.chars(rows, a))}
            for a in ARMS
        },
    }


# --- estimate ---------------------------------------------------------------------------


def estimate_question(q: Mapping[str, Any]) -> dict[str, tuple[int, int]]:
    """Tournament calls exactly from the real paragraphs; sentence calls for every paragraph,
    to be scaled by the assumed share that passes 0.75."""
    question = q["question"]
    ms = lme.memories_of(q)
    tour_c = tour_p = (0, 0)
    sentences = (0, 0)
    for i in lme.bm25_ranked(q, ms)[:CANDIDATES]:
        pages = paragraphs_of(q["haystack_sessions"][i])
        if not pages:
            continue
        groups = hierarchy.groups(len(pages), chunks.PAGE_MAX)
        round_chars = sum(
            lme._call(chunks.context_questions(purpose=question, pages=[pages[j] for j in g]))
            for g in groups
        )
        if len(groups) == 1:
            c = p = (1, round_chars)
        else:
            final = lme._call(
                chunks.context_questions(purpose=question, pages=pages[: chunks.PAGE_MAX])
            )
            c = (len(groups) + 1, round_chars + final)
            p = (2 * len(groups) + 1, 2 * round_chars + final)
        tour_c = (tour_c[0] + c[0], tour_c[1] + c[1])
        tour_p = (tour_p[0] + p[0], tour_p[1] + p[1])
        for title, body in pages:
            size = lme._call(
                chunks.sentence_questions(
                    purpose=question, title=title, sentences=split_sentences(body)
                )
            )
            sentences = (sentences[0] + 1, sentences[1] + size)
    return {"tournament_central": tour_c, "tournament_pessimistic": tour_p, "sentences": sentences}


def _usd(tokens: float) -> float:
    return tokens * DEFAULT_PRICE_PER_MTOK / 1e6  # rounded only in totals


def question_cost(sizes: Mapping[str, tuple[int, int]], share: float, pessimistic: bool) -> float:
    """USD for one question given the share of paragraphs that reach the sentence stage."""
    k = 1 if pessimistic else 0
    tour = sizes["tournament_pessimistic" if pessimistic else "tournament_central"][1]
    return _usd(
        tour / TOURNAMENT_CPT[k] + min(1.0, share) * sizes["sentences"][1] / SENTENCE_CPT[k]
    )


def plan(
    test: Sequence[Mapping[str, Any]],
    abstain: Sequence[Mapping[str, Any]],
    share: float,
    budget: float,
) -> tuple[int, float]:
    """(N, pessimistic USD): the abstention questions first, then the largest prefix of the
    test slice, in its seeded order, whose pessimistic cost fits the budget. The pessimistic
    share is twice the observed one (at most 1)."""
    worst = min(1.0, 2 * share)
    spent = sum(question_cost(estimate_question(q), worst, True) for q in abstain)
    n = 0
    for q in test:
        cost = question_cost(estimate_question(q), worst, True)
        if spent + cost > budget:
            break
        spent, n = spent + cost, n + 1
    return n, round(spent, 4)


def estimate(questions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Free: the tournament exactly, and the whole cost for a range of sentence shares."""
    sizes = [estimate_question(q) for q in questions]
    out: dict[str, Any] = {
        "questions": len(questions),
        "paragraphs": sum(x["sentences"][0] for x in sizes),
        "tournament_calls": sum(x["tournament_central"][0] for x in sizes),
    }
    for share in (0.0, 0.05, 0.1, 0.2):
        out = {
            **out,
            f"usd_central_share_{share}": round(
                sum(question_cost(x, share, False) for x in sizes), 4
            ),
            f"usd_pessimistic_share_{share}": round(
                sum(question_cost(x, min(1.0, 2 * share), True) for x in sizes), 4
            ),
        }
    return out


# --- main -------------------------------------------------------------------------------


def slices() -> dict[str, list[Mapping[str, Any]]]:
    parts = lme.slices(lme.load())
    return {
        "smoke": parts["dev"][:SMOKE],
        "test": parts["test"],
        "abstention": parts["abstention"][:ABSTAIN],
    }


def sentence_share(squire_journal_rows: Sequence[Mapping[str, Any]]) -> float:
    """Share of paragraphs that reached the sentence stage in the smoke rows."""
    sent = sum(r["paragraphs_sent"] for r in squire_journal_rows)
    total = sum(r["paragraphs"] for r in squire_journal_rows)
    return sent / total if total else 1.0


async def run_staged(
    parts: Mapping[str, Sequence[Mapping[str, Any]]], squire: Squire, *, live: bool, budget: float
) -> dict[str, Any]:
    """Smoke, plan, then the planned slice, all in ONE event loop (see
    `longmemeval.evaluate_slices`)."""
    smoke = await evaluate(parts["smoke"], squire)
    share = sentence_share(smoke) if live else 0.0
    spent = squire.meter.cost_usd
    n, planned = plan(parts["test"], parts["abstention"], share, budget - spent)
    out: dict[str, Any] = {
        "smoke": smoke,
        "share": share,
        "spent_smoke": spent,
        "n": n,
        "planned": planned,
    }
    if live and n < MIN_TEST:
        return {**out, "test": [], "abstention": []}
    test = await evaluate(parts["test"][:n] if live else parts["test"], squire)
    return {**out, "test": test, "abstention": await evaluate(parts["abstention"], squire)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--max-usd", type=float, default=0.30)
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    lme._data_ok()
    parts = slices()
    if args.estimate:
        every = [q for v in parts.values() for q in v]
        print(
            json.dumps(
                {"slices": {k: len(v) for k, v in parts.items()}, **estimate(every)}, indent=1
            )
        )
        return 0
    replay = None
    if args.live:
        lme.require_prereg()
        squire, replay = _live_squire(args)
    else:
        squire = Squire(NullDecider(), thresholds=replace(Thresholds(), max_decisions=10**7))
    staged = asyncio.run(run_staged(parts, squire, live=args.live, budget=args.max_usd))
    smoke, share, spent_smoke, n, planned = (
        staged["smoke"],
        staged["share"],
        staged["spent_smoke"],
        staged["n"],
        staged["planned"],
    )
    out: dict[str, Any] = {
        "mode": "live" if args.live else "dry (null decider: the cascade injects nothing)",
        "smoke": {
            "questions": len(smoke),
            "sentence_share": round(share, 4),
            "spent_usd": round(spent_smoke, 4),
        },
        "plan": {
            "test_questions": n,
            "abstention_questions": len(parts["abstention"]),
            "pessimistic_usd": planned,
        },
    }
    if args.live and n < MIN_TEST:
        out = {**out, "stopped": f"only {n} test questions fit the budget: not run"}
    else:
        out = {
            **out,
            "test": report(staged["test"]),
            "abstention": abstention(staged["abstention"]),
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
    replay = lme._Counted(run.triage_run.ReplayFirst(recorded, live))
    thresholds = replace(Thresholds(), max_decisions=10**6, max_usd=args.max_usd)
    return Squire(replay, thresholds=thresholds), replay


if __name__ == "__main__":
    sys.exit(main())
