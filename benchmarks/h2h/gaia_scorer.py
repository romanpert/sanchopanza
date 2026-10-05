"""GAIA's official grade, reproduced, plus the cases that go to a person.

`question_scorer` is the leaderboard's own rule (space gaia-benchmark/leaderboard, `scorer.py`,
read 2026-10-05), rewritten without its prints and warnings and otherwise unchanged, quirks
included:

- a gold that `float()` accepts is a number: the answer loses `$`, `%` and `,` and must equal it
  as a float; an answer that still does not parse is +inf, so "5 km" against "5" fails;
- otherwise a gold with `,` or `;` is a list: both sides split on either, same length, each
  element compared as a number when the gold's element is one, else lower-cased with all
  whitespace removed and punctuation KEPT;
- otherwise a string: lower-cased, all whitespace and ASCII punctuation removed;
- a missing answer is the string "None".

The official rule is the headline number. `needs_review` flags the misses a person should read
(the gold inside the answer, the same number with a unit, the same list in another order, a
missing FINAL ANSWER line): a hand verdict is recorded beside the official one and never
replaces it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import string
import sys
from types import ModuleType

_LIST_SPLIT = re.compile(r"[,;]")
# The answer is `gaia_session.marker_line`'s: the last marker's own line or, when that is empty,
# the next line that is not candor's status block. One rule for every h2h extractor.
_WRAPPERS = "*`\"' "


def normalize_number_str(number_str: str) -> float:
    for char in ("$", "%", ","):
        number_str = number_str.replace(char, "")
    try:
        return float(number_str)
    except ValueError:
        return float("inf")


def split_string(s: str) -> list[str]:
    return _LIST_SPLIT.split(s)


def normalize_str(input_str: str, remove_punct: bool = True) -> str:
    no_spaces = re.sub(r"\s", "", input_str).lower()
    if remove_punct:
        return no_spaces.translate(str.maketrans("", "", string.punctuation))
    return no_spaces


def is_float(element: object) -> bool:
    try:
        float(element)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def question_scorer(model_answer: str | None, ground_truth: str) -> bool:
    if model_answer is None:
        model_answer = "None"
    if is_float(ground_truth):
        return normalize_number_str(model_answer) == float(ground_truth)
    if any(char in ground_truth for char in (",", ";")):
        gt_elems = split_string(ground_truth)
        ma_elems = split_string(model_answer)
        if len(gt_elems) != len(ma_elems):
            return False
        comparisons = []
        for ma_elem, gt_elem in zip(ma_elems, gt_elems, strict=True):
            if is_float(gt_elem):
                comparisons.append(normalize_number_str(ma_elem) == float(gt_elem))
            else:
                comparisons.append(
                    normalize_str(ma_elem, remove_punct=False)
                    == normalize_str(gt_elem, remove_punct=False)
                )
        return all(comparisons)
    return normalize_str(model_answer) == normalize_str(ground_truth)


def _reading() -> ModuleType:
    """`gaia_session`, beside this file, whichever name the runner loaded it under."""
    name = "h2h_gaia_session"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, pathlib.Path(__file__).with_name("gaia_session.py"))  # fmt: skip
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def final_answer(reply: str) -> str | None:
    """The answer `gaia_session.marker_line` reads after the last "FINAL ANSWER:", with markdown
    emphasis, backticks and quotes around it stripped; None when the reply has no such marker."""
    found = _reading().marker_line(reply)
    if found is None:
        return None
    text = found.strip()
    if text.startswith("[") and text.endswith("]"):  # the template's own brackets, echoed
        text = text[1:-1]
    return text.strip(_WRAPPERS).strip()


# --- the review path ----------------------------------------------------------------------------

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _numbers(text: str) -> list[float]:
    return [float(x) for x in _NUM.findall(text.replace(",", ""))]


def needs_review(model_answer: str | None, ground_truth: str) -> str | None:
    """Why an officially wrong answer might be right, or None. Never changes the grade."""
    if question_scorer(model_answer, ground_truth):
        return None
    if model_answer is None:
        return "no FINAL ANSWER line"
    if is_float(ground_truth) and float(ground_truth) in _numbers(model_answer):
        return "the gold's number with other text"
    got, want = normalize_str(model_answer), normalize_str(ground_truth)
    if want and want in got:
        return "the gold inside the answer"
    if any(c in ground_truth for c in ",;"):
        a = sorted(normalize_str(x) for x in split_string(model_answer))
        b = sorted(normalize_str(x) for x in split_string(ground_truth))
        if a == b:
            return "the same list in another order"
    return None
