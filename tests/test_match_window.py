"""The opt-in page excerpt of roadmap C6: the head, unless the best match lies past it.

`triage_pages` and the paragraph tournament of `select_passages` show the decider each page's
first 900 characters. On B6's Spanish articles the answer sentence started past them in 24 of
614 questions and was then kept in about a third; `excerpt="window"` shows a window of whole
sentences around the paragraph's best word match to the question instead, and changes nothing
when that match already lies in the head.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sanchopanza import Squire
from sanchopanza.contract import Answer, Decision
from sanchopanza.points import chunks
from sanchopanza.text import match_window, truncate

FILLER = "Esta frase de relleno habla de otra cosa distinta. "  # 51 characters


def _paragraph(answer: str, before: int, after: int = 3) -> str:
    return (FILLER * before + answer + " " + FILLER * after).strip()


def test_a_text_that_fits_is_returned_unchanged() -> None:
    text = "Una frase corta. Otra más."
    assert match_window(text, "frase corta", 900) == text


def test_a_best_match_inside_the_head_keeps_the_head_exactly() -> None:
    text = _paragraph("El castillo fue construido en 1205 por el rey.", before=2, after=30)
    assert match_window(text, "¿Cuándo fue construido el castillo?", 900) == truncate(text, 900)


def test_a_best_match_past_the_head_brings_its_sentence_in_whole_sentences() -> None:
    answer = "El castillo fue construido en 1205 por el rey."
    text = _paragraph(answer, before=30, after=10)
    got = match_window(text, "¿Cuándo fue construido el castillo?", 900)
    assert answer in got
    assert got.startswith("[...] ") and got.endswith(" [...]")
    body = got.removeprefix("[...] ").removesuffix(" [...]")
    assert len(body) <= 900
    assert body.startswith("Esta frase") and body.endswith(".")  # sentences are not cut


def test_the_window_reaches_the_end_without_a_trailing_marker() -> None:
    answer = "El castillo fue construido en 1205 por el rey."
    text = _paragraph(answer, before=30, after=0)
    got = match_window(text, "¿Cuándo fue construido el castillo?", 900)
    assert got.endswith(answer) and got.startswith("[...] ")


def test_matching_folds_accents_and_case_on_both_sides() -> None:
    answer = "Durante el PERIODO triásico vivieron estos animales."
    text = _paragraph(answer, before=30)
    assert answer in match_window(text, "¿En qué período vivieron?", 900)


def test_a_purpose_with_no_useful_word_keeps_the_head() -> None:
    text = _paragraph("Nada aquí.", before=30)
    assert match_window(text, "de la", 900) == truncate(text, 900)


def test_ties_go_to_the_earliest_sentence() -> None:
    hit = "El castillo tiene torres."
    text = (hit + " " + FILLER * 30 + hit + " " + FILLER * 5).strip()
    assert match_window(text, "castillo", 900) == truncate(text, 900)


def test_a_best_sentence_longer_than_the_limit_is_cut_from_its_start() -> None:
    long_one = "El castillo " + "muy " * 400 + "alto."
    text = (FILLER * 30 + long_one).strip()
    got = match_window(text, "castillo", 900)
    assert got.startswith("[...] El castillo muy")
    assert len(got.removeprefix("[...] ").removesuffix(" [...]")) == 900


def test_whitespace_is_collapsed_only_in_a_window() -> None:
    answer = "El castillo fue construido en 1205."
    text = ("Relleno  sin\tinterés alguno aquí. " * 30) + "\n" + answer
    got = match_window(text, "castillo construido", 900)
    assert answer in got and "\t" not in got


# --- the question builder and the Squire ------------------------------------------------------


def test_context_questions_keeps_the_head_by_default_and_windows_on_request() -> None:
    answer = "El castillo fue construido en 1205 por el rey."
    pages = [("", _paragraph(answer, before=30)), ("", "Corta.")]
    purpose = "¿Cuándo fue construido el castillo?"
    head, _ = chunks.context_questions(purpose=purpose, pages=pages)
    same, _ = chunks.context_questions(purpose=purpose, pages=pages, excerpt="head")
    window, qs = chunks.context_questions(purpose=purpose, pages=pages, excerpt="window")
    assert head == same and answer not in head["pages"]
    assert answer in window["pages"] and list(qs) == ["P01", "P02"]


def test_context_questions_refuses_an_unknown_excerpt() -> None:
    with pytest.raises(ValueError, match="excerpt"):
        chunks.context_questions(purpose="p", pages=[("", "x")], excerpt="middle")


class _Seen:
    name = "seen"

    def __init__(self) -> None:
        self.states: list[tuple[str, Any]] = []

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.states.append((point, state))
        return Decision(point, {k: Answer("truth", 0.9, truth=0.9) for k in qs}, "seen", "stub")


def test_select_passages_and_triage_pages_pass_the_excerpt_to_the_paragraph_calls() -> None:
    answer = "El castillo fue construido en 1205 por el rey."
    pages = [("", _paragraph(answer, before=30)), ("", "Otra cosa.")]
    purpose = "¿Cuándo fue construido el castillo?"
    for excerpt, inside in (("head", False), ("window", True)):
        seen = _Seen()
        squire = Squire(seen)
        asyncio.run(squire.select_passages(purpose=purpose, pages=pages, excerpt=excerpt))
        asyncio.run(squire.triage_pages(purpose=purpose, pages=pages, excerpt=excerpt))
        asyncio.run(squire.triage_many(purpose=purpose, pages=pages, excerpt=excerpt))
        paged = [s["pages"] for p, s in seen.states if p == "triage_pages"]
        assert len(paged) == 3 and all((answer in s) is inside for s in paged)
        sentences = [s["sentences"] for p, s in seen.states if p == "select_sentences"]
        assert sentences and answer in sentences[0]  # the sentence stage reads the whole page


def test_the_default_paragraph_call_is_the_measured_one() -> None:
    pages = [("", _paragraph("El castillo fue construido en 1205.", before=30))]
    plain, chosen = _Seen(), _Seen()
    asyncio.run(Squire(plain).select_passages(purpose="castillo", pages=pages))
    asyncio.run(Squire(chosen).select_passages(purpose="castillo", pages=pages, excerpt="head"))
    assert plain.states == chosen.states
