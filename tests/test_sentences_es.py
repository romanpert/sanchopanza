"""`text.split_sentences` on Spanish: accented capitals, opening marks, the usual abbreviations.

The splitter cut only before an ASCII capital, a digit, `(` or `[`, so a Spanish sentence that
opened with `É`, `Á`, `Ñ`, `¿` or `¡` stayed glued to the one before, and the sentence stage
judged two sentences as one. English splits as before: the last tests pin the cases where the
new rules could have touched it (`Sr.` after a name, `."`), and the QASPER replay in
`test_select_passages_bench.py` demands the same sentences on 219 papers.
"""

from __future__ import annotations

import pytest

from sanchopanza.text import split_sentences


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "La ONU aprobó la resolución. Él votó en contra.",
            ["La ONU aprobó la resolución.", "Él votó en contra."],
        ),
        (
            "No hubo acuerdo. Ésa fue la conclusión. Ángel no estaba.",
            ["No hubo acuerdo.", "Ésa fue la conclusión.", "Ángel no estaba."],
        ),
        (
            "Llegaron tarde. Ñandúes y emúes corrían. Último aviso.",
            ["Llegaron tarde.", "Ñandúes y emúes corrían.", "Último aviso."],
        ),
        (
            "¿Vienes mañana? ¡Claro que sí! Íbamos a llamarte.",
            ["¿Vienes mañana?", "¡Claro que sí!", "Íbamos a llamarte."],
        ),
        (
            "Lo dijo ayer. ¿Quién lo duda? Nadie.",
            ["Lo dijo ayer.", "¿Quién lo duda?", "Nadie."],
        ),
        (
            "Se cerró el plazo. «No habrá prórroga», dijo el ministro.",
            ["Se cerró el plazo.", "«No habrá prórroga», dijo el ministro."],
        ),
        (
            "El informe es claro. Úsese con cuidado.",
            ["El informe es claro.", "Úsese con cuidado."],
        ),
    ],
)
def test_a_spanish_sentence_opening_with_an_accent_or_a_mark_is_cut(text, expected):
    assert split_sentences(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # a title before a name is not the end of a sentence
        (
            "Ayer habló el Sr. Pérez con la Sra. Gómez. Después se fueron.",
            ["Ayer habló el Sr. Pérez con la Sra. Gómez.", "Después se fueron."],
        ),
        (
            "Firmó la Srta. Ruiz ante la Dra. Álvarez y Dña. Elena. Fin.",
            ["Firmó la Srta. Ruiz ante la Dra. Álvarez y Dña. Elena.", "Fin."],
        ),
        ("Sr. Martínez, pase usted. Gracias.", ["Sr. Martínez, pase usted.", "Gracias."]),
        # "p. ej." before a capital is not an end either
        (
            "Hay ciudades grandes, p. ej. Madrid o Barcelona. Otras no.",
            ["Hay ciudades grandes, p. ej. Madrid o Barcelona.", "Otras no."],
        ),
        # nor a page or number reference
        (
            "Véase la pág. 12 y el núm. 3 del boletín. Nada más.",
            ["Véase la pág. 12 y el núm. 3 del boletín.", "Nada más."],
        ),
        # "EE. UU." is one acronym
        (
            "La economía de EE. UU. creció. El euro bajó.",
            ["La economía de EE. UU. creció.", "El euro bajó."],
        ),
        (
            "Ud. sabrá lo que hace. Uds. también.",
            ["Ud. sabrá lo que hace.", "Uds. también."],
        ),
    ],
)
def test_spanish_abbreviations_do_not_end_a_sentence(text, expected):
    assert split_sentences(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # decimals with a comma, and thousands with a dot, never cut: no space after the mark
        (
            "La inflación fue del 3,5 % en 2023. El paro bajó al 11,8 %.",
            ["La inflación fue del 3,5 % en 2023.", "El paro bajó al 11,8 %."],
        ),
        ("Costó 1.250 euros. Lo pagó él.", ["Costó 1.250 euros.", "Lo pagó él."]),
        # "etc." before a lower-case word goes on; before a capital it ends, as in English
        (
            "Trajeron pan, vino, etc. y se quedaron. Ésa fue la noche.",
            ["Trajeron pan, vino, etc. y se quedaron.", "Ésa fue la noche."],
        ),
        (
            "Trajeron pan, vino, etc. Luego se fueron.",
            ["Trajeron pan, vino, etc.", "Luego se fueron."],
        ),
        # acronyms written without dots are words; a sentence ending in one is cut as usual
        (
            "Lo publicó la OCDE. El BCE no opinó. La UE tampoco.",
            ["Lo publicó la OCDE.", "El BCE no opinó.", "La UE tampoco."],
        ),
        # a lower-case opening is not a cut, in either language
        ("Dijo que sí. y luego que no.", ["Dijo que sí. y luego que no."]),
    ],
)
def test_spanish_numbers_etc_and_acronyms(text, expected):
    assert split_sentences(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("One. Two!  Three? 4 more. (a) b.", ["One.", "Two!", "Three?", "4 more.", "(a) b."]),
        # "Sr." after a name is the English suffix, and it still ends a sentence there
        (
            "The airport is named after Ben Douglas, Sr. The name stuck.",
            ["The airport is named after Ben Douglas, Sr.", "The name stuck."],
        ),
        (
            "He met Eugene Black Sr. Then he left.",
            ["He met Eugene Black Sr.", "Then he left."],
        ),
        # quotes are not an opening mark: English text has `. "` often and cut it before
        ('He said no. "Fine," she said.', ['He said no. "Fine," she said.']),
        ("Mr. Smith arrived. Dr. Jones left.", ["Mr.", "Smith arrived.", "Dr.", "Jones left."]),
        ("It costs 3.5 dollars. Cheap.", ["It costs 3.5 dollars.", "Cheap."]),
    ],
)
def test_english_splits_as_before(text, expected):
    assert split_sentences(text) == expected
