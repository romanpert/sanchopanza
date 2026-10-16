"""C4's batch (benchmarks/facts_gate/written.py): fa-17's kinds of pair, labels by construction.

Two dated events with a necessary order, a role and an act, a figure and its subset: a pair is
`agree` when its values respect the constraint, `conflict` when they break it, and the
`unrelated` controls pair two facts no values could make contradict. These tests check every
label against the values the case was built from, and the runner's lot. No paid call.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import json
import re
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


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
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


def _numbers_in(text: str, lang: str) -> list[int]:
    """Every number in a fact, read back with the language's thousands separator."""
    sep = "." if lang == "es" else ","
    found = re.findall(rf"\d{{1,3}}(?:\{sep}\d{{3}})+|\d+", text)
    return [int(x.replace(sep, "")) for x in found]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_the_values_read_back_from_the_text_are_the_stored_ones(case: dict) -> None:
    text = case["input"]["fact_a"] + " " + case["input"]["fact_b"]
    lang, v = case["lang"], case["values"]
    numbers = _numbers_in(text, lang)
    if case["kind"] == "dated":
        for day in (v["first"], v["second"]):
            y, m, d = (int(x) for x in day.split("-"))
            assert written.date_text(dt.date(y, m, d), lang) in text
    elif case["kind"] == "role":
        assert v["appointed"] in numbers and v["act"] in numbers
    elif case["kind"] == "subset":
        assert v["whole"] in numbers and v["part"] in numbers
    # one way of writing numbers: from 1,000 up, always the separator
    assert not re.search(r"(?<![\d.,])\d{4,}(?![\d.,])", re.sub(r"\b(1[89]|20)\d\d\b", "", text))


def test_the_second_name_counts_the_docstring_states() -> None:
    named = [c for c in CASES if c["identity_in"]]
    assert len(named) == 83 and all(c["kind"] == "dated" for c in named)
    assert Counter(c["expected"] for c in named) == {"agree": 36, "conflict": 47}
    assert Counter(c["identity_in"] for c in named) == {"a": 55, "b": 28}
    assert "83 of the 300" in written.__doc__ and "in `fact_b` in 28" in written.__doc__


def _rows(n: int, *, unanswered: int = 0) -> list[dict]:
    return [{"expected": "unrelated", "shipped": None, "type": "t", "unanswered": k < unanswered,
             **{f"g{g:.2f}": "unrelated" for g in runner.run.GATES}} for k in range(n)]  # fmt: skip


def test_a_run_not_made_or_partial_gets_no_verdict() -> None:
    cases = [{"kind": "unrelated", "expected": "unrelated"}] * 100
    assert runner.result(_rows(100, unanswered=100), cases)["verdict"] == "no verdict: not run"
    assert runner.result(_rows(100, unanswered=3), cases)["verdict"].startswith("partial")
    got = runner.result(_rows(100, unanswered=2), cases)  # 2 % or fewer: scored without them
    assert got["verdict"] == "the gate beats the shipped policy" and got["unanswered"] == 2


def test_a_failure_driven_only_by_consistent_dated_or_role_pairs_is_a_label_disagreement() -> None:
    rows = _rows(40)
    cases = [{"kind": "unrelated", "expected": "unrelated"}] * 40
    wrong = {**rows[0], "expected": "agree"}
    rows += [wrong] * 10
    cases += [{"kind": "dated", "expected": "agree"}] * 10
    got = runner.result(rows, cases)
    assert got["verdict"].startswith("the gate does not")
    assert got["without_dated_and_role_agree"]["verdict"] == "the gate beats the shipped policy"
    assert got["label_disagreement_only"]


def test_power_is_read_at_a5s_real_band() -> None:
    bands = [r["band"] for r in runner.power_rows(600)]
    assert 0.065 in bands and 0.07 in bands


def test_the_lot_spends_on_the_rounds_shared_ledger_and_its_launcher_is_sealed_not_instrument(
    tmp_path: Path,
) -> None:
    lot = runner.lot()
    assert lot.ledger == runner.w17_round.LEDGER and lot.shared_cap_usd == 6.0
    assert lot.cap_usd == 0.15
    assert not any(p.endswith(".cmd") for p in lot.instrument)
    assert "benchmarks/w17_round.py" in lot.instrument
    filled = tmp_path / "c4-written-run.cmd"
    text = lot.launcher.read_text(encoding="utf-8")
    filled.write_text(text.replace("<PYTHON>", r"C:\py\python.exe", 1)
                      .replace("<KEYS_ENV_PATH>", r"C:\k\.env", 1), encoding="utf-8")  # fmt: skip
    assert runner.paid_once.launcher_digest(filled) == runner.paid_once.launcher_digest(
        lot.launcher
    )
