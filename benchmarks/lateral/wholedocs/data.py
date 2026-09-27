"""Every probability the two QASPER stages produced, per question, with the gold marks.

Shared by the whole-papers rescoring (`rescore.py`) and its confirmation (`confirm.py`).
The tournament is replayed through `hierarchy.tournament` with the same judge as
`Squire.triage_many`, so every call hits the same recording key, and the Verdict's `first`
and `final` probabilities are kept instead of only the keep bit. Sentences are asked with
the same state as `Squire.select_sentences`; their probabilities are kept too.

A sentence probability exists only inside a paragraph the tournament kept. Every rule
scored here therefore works inside the shipped paragraph stage (M), whose recall is its
ceiling.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]

_spec = importlib.util.spec_from_file_location(
    "longdocs_sentences", ROOT / "benchmarks" / "longdocs" / "sentences.py"
)
ls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ls)
ld = ls.ld

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.points import chunks, hierarchy  # noqa: E402


def load_papers(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {p["id"]: p for p in (json.loads(x) for x in lines if x)}


def loose(cap_usd: float) -> Thresholds:
    return replace(Thresholds(), max_decisions=10_000_000, max_usd=cap_usd)


class Probed:
    """The two squires of a probe; `exhausted` is true if either hit its cap."""

    def __init__(self, many: Squire, squire: Squire) -> None:
        self.many, self.squire = many, squire

    @property
    def exhausted(self) -> bool:
        return self.many.exhausted or self.squire.exhausted


async def probe(
    rows: list[dict[str, Any]],
    tournament: Any,
    sentences: Any,
    *,
    cap_usd: float = 5.0,
    cap_tournament_usd: float = 5.0,
) -> Probed:
    """Fill `keep`, `para_first`, `para_final`, `t_calls` and `p_s` on every row."""
    many = Squire(tournament, thresholds=loose(cap_tournament_usd))
    squire = Squire(sentences, thresholds=loose(cap_usd))
    t = Thresholds()
    gate = asyncio.Semaphore(6)

    async def one(row: dict[str, Any]) -> None:
        pages = row["pages"]

        async def judge(ids: Any) -> list[float | None]:
            state, qs = chunks.context_questions(
                purpose=row["question"], pages=[pages[i] for i in ids]
            )
            async with gate:
                decision = await many.decide("triage_pages", state, qs)
            return [decision.answer(chunks.page_id(k)).truth for k in range(len(ids))]

        result = await hierarchy.tournament(
            len(pages),
            judge,
            size=chunks.PAGE_MAX,
            first_cut=t.pages_first_round,
            final_cut=t.pages_in_context,
        )
        row["keep"] = [v.keep for v in result.pages]
        row["para_first"] = [v.first for v in result.pages]
        row["para_final"] = [v.final for v in result.pages]
        row["t_calls"] = result.calls
        probs: list[list[float | None]] = []
        for (section, _), para, ranges, keep in zip(
            pages, row["paras"], row["sentences"], row["keep"], strict=True
        ):
            if not keep:
                probs.append([None] * len(ranges))
                continue
            async with gate:
                got = await squire.select_sentences(
                    purpose=row["question"],
                    title=section,
                    sentences=[para[a:b] for a, b in ranges],
                )
            probs.append([p for _, p in got])
        row["p_s"] = probs

    await asyncio.gather(*(one(r) for r in rows))
    return Probed(many, squire)
