"""`sanchopanza.knowledge`: little and good text from one long document or from many.

A page under `LONG_CHARS` is cut exactly as fetch v2 measured. Past it, a cascade: places
(pages or sections), then passages, then sentences, by BM25, or the decision model's
`select_passages` over a BM25 shortlist when a squire is given. `pick` chooses documents out of
many (BM25, or `triage_many` with a squire) and returns their best passages. No network."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sanchopanza import knowledge, text
from sanchopanza.policy import Thresholds
from sanchopanza.webpage import Chunk, Page

FILLER = (
    "The committee met in the afternoon and discussed the agenda. Members reviewed the minutes "
    "of the previous session. Several procedural points were raised and noted. "
)
ANSWER = "The reservoir holds 4,200 cubic hectometres of water at full capacity."


def _long_pdf(answer_page: int = 37, pages: int = 60) -> Page:
    chunks = []
    for n in range(1, pages + 1):
        body = FILLER * 3
        if n == answer_page:
            body = FILLER + ANSWER + " " + FILLER
        chunks.append(Chunk(f"p. {n}", body.strip()))
    return Page("Annual water report", tuple(chunks))


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --- one document --------------------------------------------------------------------------------


def test_a_short_page_is_cut_as_fetch_v2() -> None:
    page = Page("Lake", (Chunk("History", "The lake was surveyed in 1873."),))
    out = _run(knowledge.read_page(page, "survey year", 8_000))
    assert "Whole page" in out and "1873" in out


def test_a_long_document_gives_the_answer_sentence_with_its_page() -> None:
    page = _long_pdf()
    assert page.total > knowledge.LONG_CHARS
    out = _run(knowledge.read_page(page, "reservoir capacity cubic hectometres", 4_000))
    assert ANSWER in out
    assert "## p. 37" in out
    assert out.splitlines()[0].startswith("Long document")
    body = out.split("\n\n", 1)[1]
    assert len(body) <= 4_000 * 1.1


def test_without_any_match_the_lead_is_given() -> None:
    page = _long_pdf()
    out = _run(knowledge.read_page(page, "zebra quantum", 2_000))
    assert "committee met" in out


# --- the decision model --------------------------------------------------------------------------


@dataclass
class FakeSquire:
    keep_text: str = ANSWER
    unanswered: bool = False
    thresholds: Thresholds = field(default_factory=Thresholds)
    forks: list[Thresholds] = field(default_factory=list)
    seen_pages: list[int] = field(default_factory=list)

    def fork(self, *, thresholds: Thresholds | None = None) -> FakeSquire:
        self.forks.append(thresholds)
        return self

    async def select_passages(self, *, purpose: str, pages):
        self.seen_pages.append(len(pages))
        out = []
        for _title, body in pages:
            sentences = text.split_sentences(body)
            if self.unanswered:
                out.append([(True, None)] * len(sentences))
            elif self.keep_text in body:
                out.append([(self.keep_text in s, 0.9) for s in sentences])
            else:
                out.append(None)
        return out

    async def triage_many(self, *, purpose: str, pages):
        return [(self.keep_text in body, 0.9 if self.keep_text in body else 0.1)
                for _t, body in pages]  # fmt: skip


def test_with_a_squire_the_judged_sentences_are_given_under_a_spending_cap() -> None:
    squire = FakeSquire()
    out = _run(knowledge.read_page(_long_pdf(), "reservoir capacity", 4_000, squire=squire))
    assert ANSWER in out and "judged" in out.splitlines()[0]
    assert squire.forks and squire.forks[0].max_usd == knowledge.READ_MAX_USD
    assert squire.seen_pages[0] <= knowledge.JUDGE_MAX


def test_the_judged_sentences_drop_the_far_sentences_of_a_kept_passage() -> None:
    birds = " ".join(f"Unrelated sentence number {i} about birds." for i in range(12))
    chunks = [Chunk(f"p. {n}", FILLER * 3) for n in range(1, 60)]
    page = Page("Report", (*chunks, Chunk("p. 60", birds + " " + ANSWER + " " + birds)))
    excerpts = _run(knowledge.long_judged(page, "reservoir capacity", 2_000, FakeSquire()))
    kept = " ".join(e.text for e in excerpts)
    assert ANSWER in kept and "number 5 about" not in kept
    assert [e.place for e in excerpts] == ["p. 60"]


def test_without_a_squire_a_long_document_is_cut_as_fetch_v2() -> None:
    out = _run(knowledge.read_page(_long_pdf(), "reservoir capacity", 4_000))
    assert "passages by BM25" in out.splitlines()[0] and ANSWER in out


def test_a_decider_that_answers_nothing_falls_back_to_bm25() -> None:
    squire = FakeSquire(unanswered=True)
    out = _run(knowledge.read_page(_long_pdf(), "reservoir capacity", 4_000, squire=squire))
    assert ANSWER in out and "judged nothing" in out.splitlines()[0]


# --- many documents ------------------------------------------------------------------------------


def _docs() -> list[knowledge.Doc]:
    def doc(name: str, body: str) -> knowledge.Doc:
        return knowledge.Doc(name, Page(name, (Chunk("", body),)))

    return [
        doc("minutes.txt", FILLER * 2),
        doc("water.txt", FILLER + ANSWER),
        doc("budget.txt", "The budget for roads was raised by ten percent this year."),
    ]


def test_pick_chooses_the_documents_that_match_and_gives_their_passages() -> None:
    out = _run(knowledge.pick_docs(_docs(), "reservoir capacity", 4_000))
    assert out.splitlines()[0].startswith("Picked 1 of 3 documents")
    assert "# water.txt" in out and ANSWER in out
    assert "# budget.txt" not in out


def test_pick_with_a_squire_keeps_what_the_tournament_keeps() -> None:
    docs = _docs()
    squire = FakeSquire(keep_text="roads")
    out = _run(knowledge.pick_docs(docs, "what was raised this year", 4_000, squire=squire))
    assert "# budget.txt" in out and "judged" in out.splitlines()[0]


def test_pick_with_nothing_matching_says_so() -> None:
    out = _run(knowledge.pick_docs(_docs(), "zebra quantum", 4_000))
    assert out.startswith("No document")
