"""The 211 substitution judgments against Claude Opus 5.5, replayed from their recording.

Free: it reads `docs/results/2026-09-30-opus55-substitution` and the evaluator's answers in
`docs/results/2026-09-27-memory-write-cut/fifty`. Nothing is called.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "docs" / "results" / "2026-09-30-opus55-substitution"
FIFTY = ROOT / "docs" / "results" / "2026-09-27-memory-write-cut" / "fifty"
sys.path.insert(0, str(ROOT / "benchmarks"))

from substitution import _at_half, norm  # noqa: E402

API_INPUT_PER_CASE = 145_492 / 212  # what the Opus 5 API run measured for the same prompts
JEV_PER_CASE = 28.4e-6
PRICE_IN, PRICE_OUT = 4e-6, 20e-6  # claude-opus-5-5, list
HAIKU_SIDE_CALL = 0.000976  # the CLI's own small call per session, measured on 2026-09-30


def _labels(path: Path) -> dict[str, str | None]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {row["id"]: row["label"] for row in map(json.loads, filter(str.strip, lines))}


@pytest.fixture(scope="module")
def scores():
    if not (NEW / "annotator-2.jsonl").exists() or not (FIFTY / "results.json").exists():
        pytest.skip("recordings not present")
    rows = json.loads((FIFTY / "results.json").read_text(encoding="utf-8"))
    opus5 = _labels(FIFTY / "annotator-2.jsonl")
    opus55 = _labels(NEW / "annotator-2.jsonl")
    base = [r for r in rows if opus5.get(r["id"])]
    right = lambda label, r: label == norm(r["expected"])  # noqa: E731
    return {
        "n": len(base),
        "shipped": sum(right(norm(r["predicted"]), r) for r in base),
        "cut": sum(right(_at_half(r), r) for r in base),
        "opus55": sum(right(opus55.get(r["id"]), r) for r in base),
        "opus5": sum(right(opus5[r["id"]], r) for r in base),
        "unanswered": sorted(i for i, label in opus55.items() if label is None),
    }


def test_the_same_211_cases(scores):
    assert scores["n"] == 211


def test_opus55_ties_the_shipped_policy_and_opus5_stays_ahead(scores):
    assert (scores["shipped"], scores["cut"], scores["opus55"], scores["opus5"]) == (
        200,
        202,
        199,
        204,
    )
    assert scores["unanswered"] == ["rd-46"]


def test_the_price_ratio_floor_is_about_a_hundred():
    lines = (NEW / "sessions-usage.jsonl").read_text(encoding="utf-8").splitlines()
    sessions = [json.loads(line) for line in lines if line.strip()]
    assert len(sessions) == 212
    assert round(sum(s["list_cost_usd"] for s in sessions), 2) == 2.63
    implied = [
        (
            s["list_cost_usd"]
            - HAIKU_SIDE_CALL
            - PRICE_IN * (s["input_tokens"] + 2 * s["cache_write_tokens"])
        )
        / PRICE_OUT
        for s in sessions
    ]
    median_out = statistics.median(implied)
    assert 15 <= median_out <= 40
    floor = (PRICE_IN * API_INPUT_PER_CASE + PRICE_OUT * 3) / JEV_PER_CASE
    typical = (PRICE_IN * API_INPUT_PER_CASE + PRICE_OUT * median_out) / JEV_PER_CASE
    assert round(floor) == 99
    assert 105 <= typical <= 120
