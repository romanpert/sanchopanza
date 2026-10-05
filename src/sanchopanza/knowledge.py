"""Little and good text out of one long document, or out of many: the knowledge layer's core.

No network and no model of its own; a squire, when given, is the only judge. Two entry points:

- `read_page`: a page is cut as fetch v2 measured (`webpage_v2.passages`: 62 of 66 gold-bearing
  FRAMES pages at about 1,350 tokens, docs/results/2026-10-05-knowledge/). A document past
  `LONG_CHARS` characters, with a squire, goes through the cascade: a BM25 shortlist of
  `JUDGE_MAX` passages, the decision model's `select_passages` over it (a `triage_many`
  tournament, then `select_sentences` with a window of two inside the passages it keeps; on
  QASPER every answer sentence in 87.2 % of 219 new questions at 21 % of the text), under
  `READ_MAX_USD` a read (`long_judged`). Replayed from recordings on 195 QASPER papers it gave
  every answer sentence in 88.7 % at about 1,000 tokens, where fetch v2 gave 81.0 % at 1,800.
  Without a squire, or when it judged nothing, fetch v2's passages: a BM25 cascade (places, then
  passages, then sentences) was measured and lost to them at every budget (55.9 % against 71.7 %
  at 8,000 characters), so it is not shipped. Every excerpt keeps its place, for citing.
- `pick_docs`: many documents (a folder, a list of URLs) to the few that serve the purpose:
  one BM25 index over all their passages, a document scored by its two best; with a squire, the
  `triage_many` tournament over each candidate's best passages (confirmed on 200 HotpotQA
  questions with 100 pages: both supporting pages kept in 96.5 % at 3.1 % of the text). The
  chosen documents' passages share the budget.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from . import webpage, webpage_v2
from .text import BM25Index, split_sentences
from .webpage import Chunk, Page, Passages, render

LONG_CHARS = 20_000  # eligible characters past which a squire judges the document's passages
JUDGE_MAX = 60  # passages sent to the decision model at most (two tournament groups)
READ_MAX_USD = 0.03  # the decision model's spend on one read (recorded mean: under 0.002)
PICK_TOP = 5
PICK_JUDGE = 30  # candidate documents judged together (one in-context call)
PICK_NEXT = 5
PICK_MAX_USD = 0.02
MIN_SHARE = 1_500
PATH_SEP = webpage_v2.PATH_SEP
SEP = " [...] "


@dataclass(frozen=True)
class Excerpt:
    index: int  # the chunk's position in the page
    place: str
    text: str


@dataclass(frozen=True)
class Doc:
    source: str  # the URL or the path it was read from
    page: Page


# --- one document --------------------------------------------------------------------------------


def eligible(purpose: str, chunks: Sequence[Chunk]) -> list[int]:
    """fetch v2's eligible chunks (back matter out unless the purpose names it), or every chunk
    when that leaves none: a notes file whose one heading is "Notes" is not back matter."""
    return webpage_v2.eligible(purpose, chunks) or list(range(len(chunks)))


def _ranked_chunks(page: Page, purpose: str, allowed: Sequence[int]) -> list[int]:
    index = BM25Index([f"{c.heading}\n{c.text}" for c in page.chunks])
    wanted = set(allowed)
    return [i for i, _s in index.top(purpose, len(page.chunks)) if i in wanted]


def _join(sentences: Sequence[str], ids: Sequence[int]) -> str:
    out = ""
    for k, j in enumerate(ids):
        joint = "" if k == 0 else (" " if ids[k - 1] == j - 1 else SEP)
        out += joint + sentences[j]
    return out


def _fill(candidates: Sequence[tuple[int, str, str]], budget: int) -> list[Excerpt]:
    """Excerpts in the given (best first) order while they fit, then in page order."""
    picked: list[Excerpt] = []
    used = 0
    for index, place, text in candidates:
        if used + len(text) > budget:
            continue
        picked.append(Excerpt(index, place, text))
        used += len(text)
        if used >= budget * 0.9:
            break
    return sorted(picked, key=lambda e: e.index)


def _judge_list(page: Page, purpose: str) -> list[int]:
    """The decision model's shortlist: BM25's best passages, topped up in page order."""
    allowed = eligible(purpose, page.chunks)
    ranked = _ranked_chunks(page, purpose, allowed)[:JUDGE_MAX]
    rest = [i for i in allowed if i not in set(ranked)]
    return [*ranked, *rest[: JUDGE_MAX - len(ranked)]]


def _capped(squire: Any, max_usd: float) -> Any:
    return squire.fork(thresholds=replace(squire.thresholds, max_usd=max_usd))


async def long_judged(page: Page, purpose: str, budget: int, squire: Any) -> list[Excerpt] | None:
    """The cascade by the decision model over a BM25 shortlist; None when it judged nothing
    (no key, spending cap, an error), so the caller falls back to fetch v2's passages."""
    order = _judge_list(page, purpose)
    if not order:
        return None
    rank = {i: r for r, i in enumerate(order)}
    short = sorted(order)  # the tournament groups passages in page order
    pages = [(page.chunks[i].heading or page.title, page.chunks[i].text) for i in short]
    try:
        verdicts = await _capped(squire, READ_MAX_USD).select_passages(purpose=purpose, pages=pages)
    except Exception:  # noqa: BLE001 - fail open to BM25
        return None
    candidates = []
    for i, verdict in zip(short, verdicts, strict=False):
        if not verdict or all(p is None for _keep, p in verdict):
            continue
        sentences = split_sentences(page.chunks[i].text) or [page.chunks[i].text]
        ids = [j for j, (keep, _p) in enumerate(verdict) if keep and j < len(sentences)]
        if ids:
            candidates.append((rank[i], i, _join(sentences, ids)))
    if not candidates:
        return None
    return _fill([(i, page.chunks[i].heading, t) for _r, i, t in sorted(candidates)], budget)


def render_excerpts(page: Page, excerpts: Sequence[Excerpt]) -> str:
    """In page order, each place named once, `[...]` over every gap (`webpage.render`)."""
    texts = {e.index: e.text for e in excerpts}
    shown = Page(page.title, tuple(Chunk(c.heading, texts.get(i, c.text))
                                   for i, c in enumerate(page.chunks)))  # fmt: skip
    return render(shown, [e.index for e in excerpts])


def _places(excerpts: Sequence[Excerpt]) -> list[str]:
    out: list[str] = []
    for e in excerpts:
        if e.place and e.place not in out:
            out.append(e.place)
    return out


def _eligible_total(page: Page, purpose: str) -> int:
    return sum(len(page.chunks[i].text) for i in eligible(purpose, page.chunks))


def _opening(page: Page, budget: int) -> Passages:
    """The document's first chunks within the budget, when no passage matches the purpose."""
    picked, used = [], 0
    for i, chunk in enumerate(page.chunks):
        if used + len(chunk.text) > budget:
            break
        picked, used = [*picked, i], used + len(chunk.text)
    picked = picked or [0]
    return Passages(page.title, render(page, picked), used, page.total, len(picked),
                    len(page.chunks))  # fmt: skip


def _short(page: Page, purpose: str, budget: int) -> tuple[Passages, str]:
    """fetch v2's passages (version 1's when v2 would leave nothing, see `eligible`), and the
    header; the document's opening when nothing matches."""
    if webpage_v2.eligible(purpose, page.chunks):
        out = webpage_v2.passages(page, purpose, budget)
    else:
        out = webpage.passages(page, purpose, budget)
    if out.picked or not page.chunks:
        return out, out.header()
    lead = _opening(page, budget)
    return lead, "No passage matches the purpose's words: the document's opening instead."


async def read_page(
    page: Page, purpose: str, budget: int, *, squire: Any = None, long_chars: int = LONG_CHARS
) -> str:
    """The header line and the text for one document: fetch v2's passages, or, for a long one
    with a squire, the passages and sentences the decision model keeps."""
    total = _eligible_total(page, purpose)
    long = total > long_chars
    excerpts = await long_judged(page, purpose, budget, squire) if long and squire else None
    if excerpts:
        shown = sum(len(e.text) for e in excerpts)
        places = _places(excerpts)
        named = ", ".join(places[:8]) + (", ..." if len(places) > 8 else "")
        header = (
            f"Long document ({total:,} characters), passages judged by the decision model: "
            f"{shown:,} characters from {len(places)} places{f' ({named})' if named else ''}. "
            "Ask again with another purpose for other passages."
        )
        return f"{header}\n\n{render_excerpts(page, excerpts)}"
    out, header = _short(page, purpose, budget)
    if long:
        why = " (the decision model judged nothing)" if squire else ""
        header = f"Long document ({total:,} characters), passages by BM25{why}. {header}"
    return f"{header}\n\n{out.text}"


def passages_text(page: Page, purpose: str, budget: int) -> str:
    """The text alone, by BM25: fetch v2's passages."""
    return _short(page, purpose, budget)[0].text


# --- many documents ------------------------------------------------------------------------------


def _doc_scores(docs: Sequence[Doc], purpose: str) -> dict[int, tuple[float, list[int]]]:
    """Per document with a match: the sum of its two best passage scores and its passages in
    order of score, all from one BM25 index over every document's eligible passages."""
    entries = [(d, i) for d, doc in enumerate(docs)
               for i in eligible(purpose, doc.page.chunks)]  # fmt: skip
    if not entries:
        return {}
    texts = [
        f"{docs[d].page.title}\n{docs[d].page.chunks[i].heading}\n{docs[d].page.chunks[i].text}"
        for d, i in entries
    ]
    scored: dict[int, list[tuple[float, int]]] = {}
    for (d, i), score in zip(entries, BM25Index(texts).scores(purpose), strict=True):
        if score > 0:
            scored.setdefault(d, []).append((score, i))
    out = {}
    for d, rows in scored.items():
        rows = sorted(rows, reverse=True)
        out[d] = (sum(s for s, _i in rows[:2]), [i for _s, i in rows])
    return out


async def _judged_choice(
    docs: Sequence[Doc],
    ranked: Sequence[int],
    best: dict[int, list[int]],
    purpose: str,
    squire: Any,
) -> list[int] | None:
    candidates = list(ranked[:PICK_JUDGE])
    pages = [
        (docs[d].page.title or docs[d].source,
         "\n".join(docs[d].page.chunks[i].text for i in best[d][:2]))
        for d in candidates
    ]  # fmt: skip
    try:
        verdicts = await _capped(squire, PICK_MAX_USD).triage_many(purpose=purpose, pages=pages)
    except Exception:  # noqa: BLE001 - fail open to BM25
        return None
    if not verdicts or all(p is None for _keep, p in verdicts):
        return None
    pairs = enumerate(zip(candidates, verdicts, strict=False))
    kept = [(0.5 if p is None else p, -pos, d) for pos, (d, (keep, p)) in pairs if keep]
    return [d for *_rest, d in sorted(kept, reverse=True)][:PICK_TOP]


async def pick_docs(
    docs: Sequence[Doc], purpose: str, budget: int, *, squire: Any = None, skipped: int = 0
) -> str:
    """The documents that serve `purpose`, best first, and their passages within `budget`."""
    scores = _doc_scores(docs, purpose)
    ranked = sorted(scores, key=lambda d: (-scores[d][0], d))
    if not ranked:
        return (f"No document of {len(docs)} matches the purpose's words. Try other words, or "
                "read one document with its own purpose.")  # fmt: skip
    best = {d: scores[d][1] for d in ranked}
    judged = await _judged_choice(docs, ranked, best, purpose, squire) if squire else None
    if judged:
        chosen, mode = judged, "judged by the decision model"
    elif judged == []:  # it judged and kept none: BM25's two best, said as such
        chosen, mode = ranked[:2], "the decision model kept none; BM25's best"
    else:
        chosen, mode = ranked[:PICK_TOP], "ranked by BM25"
    share = max(MIN_SHARE, budget // len(chosen))
    parts = []
    for d in chosen:
        doc = docs[d]
        parts.append(f"# {doc.page.title or doc.source}\n{doc.source}\n"
                     f"{passages_text(doc.page, purpose, share)}")  # fmt: skip
    rest = [docs[d].source for d in ranked if d not in chosen][:PICK_NEXT]
    unread = f" {skipped} could not be read." if skipped else ""
    following = f" Next best: {', '.join(rest)}." if rest else ""
    header = f"Picked {len(chosen)} of {len(docs)} documents for the purpose ({mode})."
    header += unread + following
    return header + "\n\n" + "\n\n".join(parts)
