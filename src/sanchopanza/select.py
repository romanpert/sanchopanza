"""Select a few among many: the one shape behind every "which of these matter?" in the package.

Two stages, the same wherever the candidates come from (code fragments of a repository,
archived tool output, memory files, pages, passages):

1. **Shortlist by code.** BM25 (`text.BM25Index`) over each candidate's title and text keeps
   the `shortlist_k` best. Free, no key, milliseconds. A candidate with no word of the query in
   it never reaches the model.
2. **Judge in context** (optional). With a `Squire`, the shortlist goes to `triage_many`: one
   in-context question per group of 30, a tournament past that, each candidate judged beside
   the others (docs/results/2026-09-27-hierarchy/: both supporting pages kept in 96.5 % of 200
   questions with 100 pages each, at 3.1 % of the text). Without one, the BM25 order stands.

The model never writes anything: it only keeps or drops what code proposed, so a failed or
missing decider degrades to the free ranking and never to an empty answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .text import BM25Index


@dataclass(frozen=True, slots=True)
class Candidate:
    """One thing to choose among. `key` is stable (a path with lines, a file, an entry id);
    `title` is what a reader sees first; `text` is what is scored and judged."""

    key: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class Pick:
    candidate: Candidate
    bm25: float
    p: float | None  # the judge's probability; None when nothing judged it


def index_of(candidates: Sequence[Candidate]) -> BM25Index:
    """The BM25 index `select` uses, built once when the same candidates serve many queries."""
    return BM25Index([f"{c.title}\n{c.text}" for c in candidates])


async def select(
    query: str,
    candidates: Sequence[Candidate],
    *,
    squire: Any = None,
    purpose: str = "",
    shortlist_k: int = 60,
    keep: int = 10,
    index: BM25Index | None = None,
) -> list[Pick]:
    """The best `keep` candidates for `query`: BM25 shortlist, then the judge if there is one.

    `purpose` is what the judge is told the selection is for (default: the query). Kept items
    come first, by the judge's probability then BM25; if the judge keeps nothing, nothing is
    returned, since an empty answer from a working judge is an answer. If it fails, the free
    ranking is returned.
    """
    if not candidates or not query.strip():
        return []
    index = index or index_of(candidates)
    short = index.top(query, shortlist_k)
    if not short:
        return []
    if squire is None:
        return [Pick(candidates[i], score, None) for i, score in short[:keep]]
    pages = [(candidates[i].title, candidates[i].text) for i, _ in short]
    try:
        verdicts = await squire.triage_many(purpose=purpose or query, pages=pages)
    except Exception:  # noqa: BLE001 - a judge failure degrades to the free ranking
        return [Pick(candidates[i], score, None) for i, score in short[:keep]]
    kept = [
        Pick(candidates[i], score, p)
        for (i, score), (keep_it, p) in zip(short, verdicts, strict=False)
        if keep_it
    ]
    kept.sort(key=lambda pick: (-(pick.p if pick.p is not None else 0.5), -pick.bm25))
    return kept[:keep]
