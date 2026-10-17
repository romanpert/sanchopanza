"""Lot longdoc-free's pages and kept text (benchmarks/longdoc_free/pages.py). Pure."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pages = _load("lf_pages", "benchmarks/longdoc_free/pages.py")
from sanchopanza.text import split_sentences  # noqa: E402


def _novel(n: int = 40) -> str:
    return "\n\n".join(f"Paragraph {i} says that Emma met Mr. Knightley at noon." for i in range(n))


def test_pages_stay_within_the_tournament_view_and_lose_nothing():
    text = _novel() + "\n\n" + "A very long paragraph sentence goes on. " * 60
    got = pages.pages_of(text)
    assert all(len(page) <= pages.PAGE_CHARS for _, page in got)
    assert [title for title, _ in got] == [str(i + 1) for i in range(len(got))]
    flat = lambda s: "".join(s.split())  # noqa: E731
    assert flat("".join(p for _, p in got)) == flat("".join(pages.paragraphs(text)))


def test_a_sentence_longer_than_a_page_is_cut_at_the_page_length():
    got = pages.pages_of("x" * 2000)
    assert [len(p) for _, p in got] == [900, 900, 200]


def test_kept_text_joins_kept_sentences_in_order_with_a_gap_between_distant_pages():
    novel = pages.pages_of(_novel(200))
    assert len(novel) > 3
    entries = [None] * len(novel)
    for index in (0, 1, 3):
        n = len(split_sentences(novel[index][1]))
        entries[index] = [(i == 0, 0.9) for i in range(n)]
    got = pages.kept_text(novel, entries)
    blocks = got.split("\n\n")
    assert blocks[0].startswith("Paragraph 0") and blocks[1].startswith(
        split_sentences(novel[1][1])[0]
    )
    assert blocks[2] == pages.GAP  # page 3 is not next to page 2
    assert len(blocks) == 4


def test_nothing_kept_is_said_plainly():
    novel = pages.pages_of(_novel())
    assert pages.kept_text(novel, [None] * len(novel)) == pages.EMPTY
    n = len(split_sentences(novel[0][1]))
    assert pages.kept_text(novel, [[(False, 0.1)] * n] + [None] * (len(novel) - 1)) == pages.EMPTY


def test_a_mismatch_between_pages_and_marks_is_refused():
    novel = pages.pages_of(_novel())
    with pytest.raises(ValueError):
        pages.kept_text(novel, [None])
    with pytest.raises(ValueError):
        pages.kept_text(novel, [[(True, 0.9)] * 99] + [None] * (len(novel) - 1))


def test_a_real_novel_when_cached():
    folder = Path.home() / ".cache" / "sanchopanza" / "longdoc_free" / "novels"
    files = sorted(folder.glob("*.txt")) if folder.exists() else []
    if not files:
        pytest.skip("no ∞Bench novel cached")
    text = files[0].read_text("utf-8")
    got = pages.pages_of(text)
    assert all(len(p) <= pages.PAGE_CHARS for _, p in got)
    assert len(got) > len(text) // pages.PAGE_CHARS * 0.9
