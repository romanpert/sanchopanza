"""C4's batch (benchmarks/facts_gate/written.py): fa-17's kinds of pair, labels by construction.

Two dated events with a necessary order, a role and an act, a figure and its subset: a pair is
`agree` when its values respect the constraint, `conflict` when they break it, and the
`unrelated` controls pair two facts no values could make contradict. These tests check every
label against the values the case was built from, and the runner's lot. No paid call.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


written = _load("facts_written", ROOT / "benchmarks/facts_gate/written.py")
runner = _load("facts_written_run", ROOT / "benchmarks/facts_gate/written_run.py")
CASES = written.build()


def test_the_batch_has_the_registered_mix_and_alternates_languages() -> None:
    assert len(CASES) == 1500
    assert Counter(c["expected"] for c in CASES) == {
        "unrelated": 600,
        "agree": 450,
        "conflict": 450,
    }
    related = Counter((c["kind"], c["expected"]) for c in CASES if c["expected"] != "unrelated")
    assert set(related.values()) == {150}  # 150 agree and 150 conflict per kind
    assert [c["lang"] for c in CASES[:4]] == ["es", "en", "es", "en"]
    assert len({c["id"] for c in CASES}) == 1500
    assert len({frozenset(c["input"].values()) for c in CASES}) == 1500


def test_the_build_is_deterministic_and_matches_the_committed_file() -> None:
    assert written.text_of(written.build()) == written.text_of(CASES)
    on_disk = written.OUT.read_bytes().decode("utf-8")
    assert on_disk == written.text_of(CASES)
    assert written.digest(on_disk) == written.OUT.with_suffix(".sha256").read_text().strip()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_every_label_follows_from_its_values(case: dict) -> None:
    v = case["values"]
    if case["kind"] == "dated":
        ordered = v["second"] > v["first"]
    elif case["kind"] == "role":
        ordered = v["act"] >= v["appointed"]
    elif case["kind"] == "subset":
        ordered = v["part"] < v["whole"]
    else:
        assert case["expected"] == "unrelated" and case["kind"] == "unrelated"
        return
    assert case["expected"] == ("agree" if ordered else "conflict")


@pytest.mark.parametrize("case", CASES[:300], ids=lambda c: c["id"])
def test_both_facts_name_the_same_entity_and_show_their_values(case: dict) -> None:
    a, b = case["input"]["fact_a"], case["input"]["fact_b"]
    assert case["entity"].lower() in a.lower() and case["entity"].lower() in b.lower()
    shown = " ".join(case["shown"])
    assert all(s in a + " " + b for s in case["shown"]), shown


def test_the_runner_asks_the_shipped_question_once_per_case_under_a_small_cap() -> None:
    lot = runner.lot()
    assert lot.cap_usd <= 0.15 and lot.model == "jev-1.13.0"
    assert runner.GATE == 0.65
    asks = runner.queries(CASES)
    assert len(asks) == 1500 and {p for p, _, _ in asks} == {"facts"}
    assert asks[0][1]["fact_a"] == CASES[0]["input"]["fact_a"]


def test_the_rule_is_a5s_at_the_fixed_gate() -> None:
    def row(expected: str, gated: str | None) -> dict:
        return {"expected": expected, "shipped": None, "type": "t", "g0.65": gated,
                **{f"g{g:.2f}": gated for g in runner.run.GATES}}  # fmt: skip

    right = [row("unrelated", "unrelated")] * 20
    assert runner.run.verdict(right, 0.65)["verdict"] == "the gate beats the shipped policy"
    missed = right + [row("conflict", "unrelated")]
    assert runner.run.verdict(missed, 0.65)["verdict"].startswith("the gate does not")
    assert runner.run.verdict(right[:10], 0.65)["verdict"].startswith("undecided")


def test_the_report_refuses_while_cases_are_unanswered(tmp_path: Path) -> None:
    from dataclasses import replace

    empty = replace(runner.lot(), home=tmp_path, fixture=tmp_path / "none.jsonl")
    with pytest.raises(SystemExit, match="unanswered"):
        asyncio.run(runner.report(CASES, empty))


def test_cases_file_is_json_lines_with_lf() -> None:
    raw = written.OUT.read_bytes()
    assert b"\r\n" not in raw
    assert all(json.loads(x)["point"] == "facts" for x in raw.decode("utf-8").splitlines())
