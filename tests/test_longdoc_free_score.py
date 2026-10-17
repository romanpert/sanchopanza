"""∞Bench En.QA's official scorer, vendored (benchmarks/longdoc_free/infbench_score.py): its
behaviour pinned, and its three functions identical to the upstream file when that is cached."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = (
    Path.home() / ".cache" / "sanchopanza" / "longdoc_free" / "upstream" / "compute_scores.py"
)
FUNCTIONS = ("normalize_answer", "f1_score", "qa_f1_score")


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


score = _load("lf_infbench_score", "benchmarks/longdoc_free/infbench_score.py")


def test_normalisation_lowers_and_drops_punctuation_articles_and_spaces():
    assert score.normalize_answer('  "The  Hebrides!" ') == "hebrides"
    assert score.normalize_answer("A Tale of an Apple") == "tale of apple"


def test_token_f1_is_the_maximum_over_the_references():
    assert score.qa_f1_score("Mrs. Deandra", ['"Mrs. Deandra"']) == 1.0
    assert score.qa_f1_score("Peyton", ["Annalisa", '"Peyton"']) == 1.0
    assert score.qa_f1_score("the summer home in the Hebrides", ["the Hebrides"]) == pytest.approx(
        2 * (1 / 4) * 1 / (1 / 4 + 1)
    )


def test_no_overlap_and_an_empty_reply_score_zero():
    assert score.qa_f1_score("Gannonmarie", ["Peyton"]) == 0
    assert score.qa_f1_score("", ["Peyton"]) == 0
    assert score.qa_f1_score("Peyton", []) == 0


def test_a_long_reply_loses_precision():
    short = score.qa_f1_score("Peyton", ["Peyton"])
    long = score.qa_f1_score("I think the answer is clearly Peyton here", ["Peyton"])
    assert short == 1.0 and long < 0.4


def _sources(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text("utf-8"))
    return {node.name: ast.unparse(node) for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS}  # fmt: skip


def test_the_three_functions_are_the_upstream_ones_unchanged():
    if not UPSTREAM.exists():
        pytest.skip("the upstream compute_scores.py is not cached on this machine")
    ours = _sources(ROOT / "benchmarks/longdoc_free/infbench_score.py")
    theirs = _sources(UPSTREAM)
    assert set(ours) == set(FUNCTIONS) == set(theirs)
    assert ours == theirs
