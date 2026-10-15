"""The Jev 1.14 label comparison (benchmarks/label/jev114.py): sampling, interleaving, statistics.
No network: fake deciders only."""

from __future__ import annotations

import asyncio
import importlib.util
import random
import sys
from pathlib import Path
from typing import Any

from sanchopanza.contract import Answer, Decision
from sanchopanza.eval.stats import auc
from sanchopanza.label import Rubric

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bench = _load("label_jev114", ROOT / "benchmarks" / "label" / "jev114.py")
data = _load("label_data114", ROOT / "benchmarks" / "label" / "data114.py")
RUBRIC = Rubric(field="topic", options={"a": "A", "b": "B"}, add_other=False)


class Scripted:
    """Answers `a` or `b` by a fixed rule; logs the order of calls and the most in flight."""

    def __init__(self, name: str, winner: str, log: list[tuple[str, str]], flight: dict) -> None:
        self.name, self._winner, self._log, self._flight = name, winner, log, flight

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self._flight["now"] += 1
        self._flight["max"] = max(self._flight["max"], self._flight["now"])
        self._log.append((self.name, state["text"]))
        await asyncio.sleep(0.001)
        self._flight["now"] -= 1
        other = "b" if self._winner == "a" else "a"
        answer = Answer(kind="choice", confidence=0.8, choice=self._winner,
                        probabilities={self._winner: 0.9, other: 0.1})  # fmt: skip
        return Decision(point=point, answers={"category": answer}, provider=self.name, model="m")


def test_positions_keep_the_original_300_and_add_700_distinct() -> None:
    picked = data.positions(7600)
    assert len(picked) == 1000 == len(set(picked))
    assert set(data.evenly(7600, 300)) <= set(picked)
    assert all(0 <= i < 7600 for i in picked)


def test_both_arms_answer_every_item_in_alternating_order_at_most_four_in_flight() -> None:
    log: list[tuple[str, str]] = []
    flight = {"now": 0, "max": 0}
    squires = {
        "13r": bench.squire_of(Scripted("13r", "a", log, flight)),
        "14": bench.squire_of(Scripted("14", "b", log, flight)),
    }
    rows = [{"key": f"k{i}", "text": f"t{i}", "gold": "a"} for i in range(20)]
    out = asyncio.run(bench.run_set(rows, RUBRIC, squires))
    assert [r["label_13r"] for r in out] == ["a"] * 20
    assert [r["label_14"] for r in out] == ["b"] * 20
    firsts = {}
    for arm, text in log:
        firsts.setdefault(text, arm)
    assert firsts["t0"] == "13r" and firsts["t1"] == "14" and firsts["t2"] == "13r"
    assert flight["max"] <= bench.CONCURRENCY


def test_fast_auc_matches_the_quadratic_one() -> None:
    rng = random.Random(3)
    scores = [round(rng.random(), 1) for _ in range(200)]
    truths = [rng.random() < 0.7 for _ in range(200)]
    assert abs(bench.fast_auc(scores, truths) - auc(scores, truths)) < 1e-9


def test_holm_and_the_verdicts() -> None:
    assert bench.holm({"x": 0.01, "y": 0.04, "z": 0.5}) == {"x": 0.03, "y": 0.08, "z": 0.5}
    up = {"accuracy_diff": 0.03, "accuracy_diff_ci95": [0.01, 0.05]}
    assert bench.verdict(up, 0.01) == "mejora"
    assert bench.verdict(up, 0.2) == "no peor"
    down = {"accuracy_diff": -0.03, "accuracy_diff_ci95": [-0.05, -0.01]}
    assert bench.verdict(down, 0.01) == "peor"
    wide = {"accuracy_diff": -0.01, "accuracy_diff_ci95": [-0.03, 0.01]}
    assert bench.verdict(wide, 0.5) == "no concluyente"


def test_sib_bootstrap_resamples_whole_sentences() -> None:
    rows = [
        {"key": f"sib-{lang}-{s}", "sentence": s, "lang": lang, "gold": "a",
         "label_13r": "a", "label_14": "a" if s % 2 else "b"}
        for s in range(10) for lang in ("eng_Latn", "spa_Latn")
    ]  # fmt: skip
    assert len(bench.clusters_of(rows)) == 10
    # Every language moves together, so the gap between them never changes.
    assert bench.multilingual(rows)["ci95"] == [0.0, 0.0]


def test_the_plan_refuses_what_does_not_fit(tmp_path: Path, monkeypatch: Any) -> None:
    ledger = bench.SpendLedger(tmp_path / "ledger.json", cap_usd=4.5)
    monkeypatch.setattr(bench, "estimate_ratio", lambda: 2.0)
    assert bench.plan({"14": 1}, 0.05, ledger)["fits"] is True
    assert bench.plan({"14": 1}, 0.09, ledger)["fits"] is False
