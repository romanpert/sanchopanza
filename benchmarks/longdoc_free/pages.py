"""A novel as `select_passages` pages, and the text it keeps as the file arm H reads.

Pages: the novel's paragraphs (split at blank lines), consecutive ones joined while the page
stays within PAGE_CHARS, the length the page tournament shows of a page (`chunks.PAGE_LIMIT`),
so the tournament judges each page whole; a paragraph longer than that is split at sentence
ends (`text.split_sentences`), and a sentence longer than that at PAGE_CHARS. Titles are the
page's position, from 1. Nothing is dropped: the pages' text, joined, is the novel's paragraphs.

Kept text: `select_passages` returns, per page, None (not sent on) or one `(keep, p)` per
sentence of `text.split_sentences(page)`. The kept sentences are joined in the novel's order,
a page's with spaces, pages apart with a blank line, and GAP between pages that are not next to
each other. Pure: no model.

Prefilter (opt-in; no sealed run used it): `bm25_shortlist` keeps the K pages BM25 scores best
for the question, so only those enter Jev's page tournament; `spread` puts the tournament's
entries back among the whole novel's pages (None for every page left out).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sanchopanza.points.chunks import PAGE_LIMIT
from sanchopanza.text import BM25Index, split_sentences

PAGE_CHARS = PAGE_LIMIT  # 900
GAP = "[...]"
EMPTY = "(No passage of the novel was kept for this question.)"

Page = tuple[str, str]
Entry = Sequence[tuple[bool, float | None]] | None


def paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pieces(paragraph: str, limit: int) -> list[str]:
    """A paragraph in pieces of at most `limit` characters, cut at sentence ends."""
    if len(paragraph) <= limit:
        return [paragraph]
    out: list[str] = []
    current = ""
    for sentence in split_sentences(paragraph) or [paragraph]:
        for start in range(0, len(sentence), limit):
            part = sentence[start : start + limit]
            joined = f"{current} {part}" if current else part
            if len(joined) <= limit:
                current = joined
            else:
                out.append(current)
                current = part
    if current:
        out.append(current)
    return out


def pages_of(text: str, limit: int = PAGE_CHARS) -> list[Page]:
    pieces = [piece for p in paragraphs(text) for piece in _pieces(p, limit)]
    pages: list[str] = []
    current = ""
    for piece in pieces:
        joined = f"{current}\n\n{piece}" if current else piece
        if len(joined) <= limit:
            current = joined
        else:
            pages.append(current)
            current = piece
    if current:
        pages.append(current)
    return [(str(i + 1), page) for i, page in enumerate(pages)]


def bm25_shortlist(pages: Sequence[Page], question: str, k: int) -> list[int]:
    """The free prefilter (opt-in, off in every sealed run): the indices of the `k` pages BM25
    (`text.BM25Index`, the package's one) scores best for `question`, ties by position, returned
    in the novel's order. Every page when `k` covers them."""
    if k < 1:
        raise ValueError("k must be >= 1")
    if k >= len(pages):
        return list(range(len(pages)))
    scores = BM25Index([page for _, page in pages]).scores(question)
    best = sorted(range(len(pages)), key=lambda i: (-scores[i], i))[:k]
    return sorted(best)


def spread(entries: Sequence[Entry], shortlist: Sequence[int], n: int) -> list[Entry]:
    """A shortlist's entries back at their pages' places among `n`, None everywhere else."""
    if len(entries) != len(shortlist):
        raise ValueError(f"{len(entries)} entries for a shortlist of {len(shortlist)}")
    out: list[Entry] = [None] * n
    for index, entry in zip(shortlist, entries, strict=True):
        out[index] = entry
    return out


def kept_text(pages: Sequence[Page], entries: Sequence[Entry]) -> str:
    """The kept sentences in the novel's order; EMPTY when nothing is kept."""
    if len(pages) != len(entries):
        raise ValueError(f"{len(entries)} entries for {len(pages)} pages")
    blocks: list[tuple[int, str]] = []
    for index, ((_, page), entry) in enumerate(zip(pages, entries, strict=True)):
        if not entry:
            continue
        sentences = split_sentences(page)
        if len(sentences) != len(entry):
            raise ValueError(f"page {index + 1}: {len(entry)} marks for {len(sentences)} sentences")
        kept = [s for s, (keep, _) in zip(sentences, entry, strict=True) if keep]
        if kept:
            blocks.append((index, " ".join(kept)))
    if not blocks:
        return EMPTY
    out = [blocks[0][1]]
    for (before, _), (index, block) in zip(blocks, blocks[1:], strict=False):
        out.append(block if index == before + 1 else f"{GAP}\n\n{block}")
    return "\n\n".join(out)
