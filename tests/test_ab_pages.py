"""`benchmarks/ab/fixed.py --lever pages`: the pieces that must hold before anything is paid.

The run itself needs Jev and a model; nothing here calls either. What is pinned: passages
cover the document and respect the page limit, the tournament's verdicts map back to the
right passages, a recorded bare arm is refused unless its sequences are today's, and the
whole pipeline runs end to end with the fake decider and the fake answerer.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AB = ROOT / "benchmarks" / "ab"


@pytest.fixture(scope="module")
def pages():
    for path in (str(AB), str(ROOT / "benchmarks")):
        if path not in sys.path:
            sys.path.insert(0, path)
    import pages as module

    return module


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    text: str


def test_passages_cover_the_text_within_the_limit(pages):
    text = "Short head.\n\n" + ("A sentence about costs. " * 80) + "\n\nTail paragraph here."
    parts = pages.passages(text, limit=300, minimum=50)
    assert all(len(p) <= 300 for p in parts)
    joined = " ".join(parts)
    assert "Short head." in joined and "Tail paragraph here." in joined
    assert joined.count("A sentence about costs.") == 80


def test_short_paragraphs_fold_forward(pages):
    parts = pages.passages("## Title\n\nA body long enough to stand alone.", limit=900, minimum=20)
    assert parts == ["## Title\n\nA body long enough to stand alone."]


class Verdicts:
    """A squire stand-in: keeps the passages whose text contains `keep`."""

    def __init__(self, keep: str) -> None:
        self.keep = keep
        self.seen: list[tuple[str, str]] = []

    async def triage_many(self, *, purpose, pages):
        self.seen = list(pages)
        return [(self.keep in text, 0.9 if self.keep in text else 0.1) for _t, text in pages]


def test_trim_keeps_passages_in_order_and_withholds_empty_documents(pages):
    first = "The figure is 28.7 here. " + "It is stated plainly. " * 10
    a = Doc("a", "A", first + "\n\n" + "Filler text. " * 30)
    b = Doc("b", "B", "Nothing of use. " * 20)
    squire = Verdicts("28.7")
    bodies, withheld, dropped = asyncio.run(pages.trim_by_pages(squire, "q", [a, b]))
    assert bodies == {"a": first.strip()}
    assert withheld == ["b"]
    assert "a#1" in dropped and all(x.startswith(("a#", "b#")) for x in dropped)
    assert [t for t, _ in squire.seen][:1] == ["A"]


def test_the_fake_decider_is_deterministic_and_answers_everything(pages):
    from sanchopanza.contract import Truth

    qs = {"p0": Truth("x"), "p1": Truth("y")}
    one = asyncio.run(pages.EveryQuestion().decide("triage_pages", {"s": 1}, qs))
    two = asyncio.run(pages.EveryQuestion().decide("triage_pages", {"s": 1}, qs))
    assert one.answers == two.answers and set(one.answers) == {"p0", "p1"}


def test_a_recorded_bare_arm_is_refused_unless_it_is_todays(pages):
    seq = {"t1": [Doc("d1", "", ""), Doc("d2", "", "")]}
    row = {"task": "t1", "arm": "bare", "repeat": 0, "model": "m", "fetched": ["d1", "d2"]}
    assert pages.check_reusable([row], seq, "m") == []
    assert pages.check_reusable([{**row, "fetched": ["d2", "d1"]}], seq, "m")
    assert pages.check_reusable([row], seq, "other-model")
    assert pages.check_reusable([{**row, "error": "boom"}], seq, "m")
    assert pages.check_reusable([], seq, "m")


def test_an_unknown_ref_fails_loudly(pages):
    with pytest.raises(FileNotFoundError):
        pages.git_reader("no-such-ref-xyz", ROOT)("docs/paper.md")


def test_the_whole_pipeline_runs_free_with_fakes():
    env = {"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    argv = [sys.executable, "-m", "benchmarks.ab.fixed", "--lever", "pages", "--fake"]
    argv += ["--repeats", "1", "--tasks", "viviendas,cost"]
    done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr[-2000:]
    assert "--fake:" in done.stdout and "lever `pages`" in done.stdout
    assert "passages removed" in done.stdout
