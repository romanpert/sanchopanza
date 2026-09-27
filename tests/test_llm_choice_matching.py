"""An LLM's Choice answer is matched to the options by meaning of spelling, not byte for byte.

Found on 2026-09-25 (docs/results/2026-09-25-cascade/): Haiku 4.5 answered 16 of 298 register
classifications with the right label spelled differently - a literal `\\u00ed` escape instead
of "í", or "Farandula" for "Farándula" - and the provider dropped every one as no answer. A
label that matches exactly one option once escapes, accents and case are normalised is that
option; anything ambiguous or unknown is still no answer.
"""

from __future__ import annotations

from sanchopanza.contract import Choice
from sanchopanza.providers.llm import answers_from

OPTIONS = {"Político/Funcionario": None, "Artista/Farándula": None, "Otro": None}
QS = {"category": Choice("Which?", OPTIONS)}


def _choice(value: str) -> str | None:
    return answers_from({"category": value, "confidence": 0.8}, QS).get("category", None) and (
        answers_from({"category": value, "confidence": 0.8}, QS)["category"].choice
    )


def test_exact_labels_still_match():
    assert _choice("Otro") == "Otro"


def test_a_literal_unicode_escape_is_the_same_label():
    assert _choice("Pol\\u00edtico/Funcionario") == "Político/Funcionario"


def test_missing_accents_and_case_are_the_same_label():
    assert _choice("Artista/Farandula") == "Artista/Farándula"
    assert _choice("otro") == "Otro"


def test_an_unknown_label_is_still_no_answer():
    assert _choice("Deportista") is None
