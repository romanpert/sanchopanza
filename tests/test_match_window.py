"""The opt-in page excerpt of roadmap C6: the head, unless the best match lies past it.

`triage_pages` and the paragraph tournament of `select_passages` show the decider each page's
first 900 characters. On B6's Spanish articles the answer sentence started past them in 24 of
614 questions and was then kept in about a third; `page_view="window"` shows a window of whole
sentences around the paragraph's best word match to the question instead, and changes nothing
when that match already lies in the head.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import pytest

from sanchopanza import Squire
from sanchopanza.contract import Answer, Decision
from sanchopanza.points import chunks
from sanchopanza.providers.recorded import key_of
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
    assert len(got.removeprefix("[...] ").removesuffix(" [...]")) == 900 - len("[...] ")


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
    same, _ = chunks.context_questions(purpose=purpose, pages=pages, page_view="head")
    window, qs = chunks.context_questions(purpose=purpose, pages=pages, page_view="window")
    assert head == same and answer not in head["pages"]
    assert answer in window["pages"] and list(qs) == ["P01", "P02"]


def test_context_questions_refuses_an_unknown_page_view() -> None:
    with pytest.raises(ValueError, match="page_view"):
        chunks.context_questions(purpose="p", pages=[("", "x")], page_view="middle")


class _Seen:
    name = "seen"

    def __init__(self) -> None:
        self.states: list[tuple[str, Any]] = []

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.states.append((point, state))
        return Decision(point, {k: Answer("truth", 0.9, truth=0.9) for k in qs}, "seen", "stub")


def test_select_passages_and_triage_pages_pass_the_page_view_to_the_paragraph_calls() -> None:
    answer = "El castillo fue construido en 1205 por el rey."
    pages = [("", _paragraph(answer, before=30)), ("", "Otra cosa.")]
    purpose = "¿Cuándo fue construido el castillo?"
    for view, inside in (("head", False), ("window", True)):
        seen = _Seen()
        squire = Squire(seen)
        asyncio.run(squire.select_passages(purpose=purpose, pages=pages, page_view=view))
        asyncio.run(squire.triage_pages(purpose=purpose, pages=pages, page_view=view))
        asyncio.run(squire.triage_many(purpose=purpose, pages=pages, page_view=view))
        paged = [s["pages"] for p, s in seen.states if p == "triage_pages"]
        assert len(paged) == 3 and all((answer in s) is inside for s in paged)
        sentences = [s["sentences"] for p, s in seen.states if p == "select_sentences"]
        assert sentences and answer in sentences[0]  # the sentence stage reads the whole page


def test_the_default_paragraph_call_is_byte_for_byte_the_measured_one() -> None:
    """Pinned from the code before the option existed (622d1db): the recording key every
    published replay looks up, and the state's sha256."""
    long_page = (FILLER * 30 + "El castillo fue construido en 1205 por el rey.\n\n        "
                 + FILLER * 5).strip()  # fmt: skip
    pages = [("Historia", long_page), ("", "Corta."), ("Notas", "x " * 700)]
    state, qs = chunks.context_questions(purpose="¿Cuándo fue construido el castillo?", pages=pages)
    assert key_of("triage_pages", state, qs) == "e5416bc5afcd672c"
    flat = json.dumps(state, ensure_ascii=False, sort_keys=True).encode()
    assert hashlib.sha256(flat).hexdigest() == (
        "27a74d50aeec9335361a452b7038f2386023b475242de1a5fe535b02866694f3"
    )


def test_an_unknown_page_view_is_refused_before_any_call() -> None:
    seen = _Seen()
    for call in (Squire(seen).select_passages, Squire(seen).triage_pages, Squire(seen).triage_many):
        with pytest.raises(ValueError, match="page_view"):
            asyncio.run(call(purpose="p", pages=[("", "x")], page_view="middle"))
    assert seen.states == []


# --- the edges --------------------------------------------------------------------------------


def test_indentation_and_blank_lines_are_measured_as_the_head_shows_them() -> None:
    answer = "El castillo fue construido en 1205 por el rey."
    unit = "Relleno sin interés alguno.\n\n        "  # 36 raw characters, 28 collapsed
    text = unit * 30 + answer  # the answer ends near character 886 collapsed, 1,126 raw
    assert answer not in truncate(text, 900)
    assert answer in match_window(text, "¿Cuándo fue construido el castillo?", 900)


def test_a_sentence_after_a_footnote_and_a_zero_width_space_is_found() -> None:
    answer = "La muralla fue construida en 1205 por el rey."
    text = (FILLER * 30).strip() + " Fue citada en 1900.[12]\u200b " + answer + " " + FILLER
    assert answer in match_window(text, "¿Cuándo fue construida la muralla?", 900)


def test_sentences_opened_by_inverted_marks_are_sentences() -> None:
    answer = "¿Sabía que el castillo tiene doce torres?"
    text = (FILLER * 30).strip() + " " + answer + " ¡Y un foso! " + (FILLER * 3).strip()
    got = match_window(text, "¿Cuántas torres tiene el castillo?", 900)
    assert answer in got


def test_a_text_with_no_latin_word_keeps_the_head() -> None:
    text = "Это предложение о другом. " * 60 + "Замок построен в году."
    assert match_window(text, "Когда построен замок?", 900) == truncate(text, 900)


def _ending_at(end: int) -> str:
    answer = "El castillo fue construido en 1205."
    lead = "Relleno " + "x" * (end - len(answer) - len("Relleno ") - 2) + "."
    text = lead + " " + answer + " " + (FILLER * 5).strip()
    assert text.index(answer) + len(answer) == end
    return text


def test_a_match_ending_exactly_at_the_limit_keeps_the_head_and_one_past_it_moves() -> None:
    purpose = "¿Cuándo fue construido el castillo?"
    at = _ending_at(900)
    assert match_window(at, purpose, 900) == truncate(at, 900)
    past = _ending_at(901)
    assert match_window(past, purpose, 900) != truncate(past, 900)
    assert "El castillo fue construido en 1205." in match_window(past, purpose, 900)


def test_a_window_is_no_longer_than_the_head_it_replaces_and_has_no_double_space() -> None:
    answer = "El castillo fue construido en 1205 por el rey."
    for before, after in ((30, 10), (30, 0), (12, 40)):
        text = _paragraph(answer, before=before, after=after)
        got = match_window(text, "¿Cuándo fue construido el castillo?", 900)
        assert len(got) <= 900 + len(" [...]") and "  " not in got


def test_a_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="limit"):
        match_window("text", "purpose", 0)
