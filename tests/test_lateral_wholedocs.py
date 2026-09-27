"""Whole papers by a paragraph gate and sentence windows, replayed. No network.

Pins `docs/results/2026-09-28-lateral-wholedocs/README.md`: the derivation on the 261 recorded
questions of 2026-09-27, the confirmation on 219 questions nothing was derived on, and the
answering run from the CLI cache. The rule itself is tested without any data. The replays need
the local QASPER test export in SANCHO_QASPER (and HotpotQA in SANCHO_HOTPOT for the
descriptive transfer), or skip.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results" / "2026-09-28-lateral-wholedocs"
BENCH = ROOT / "benchmarks" / "lateral"
QASPER = os.environ.get("SANCHO_QASPER", "")
HOTPOT = os.environ.get("SANCHO_HOTPOT", "")
needs_qasper = pytest.mark.skipif(
    not QASPER or not pathlib.Path(QASPER).exists(), reason="SANCHO_QASPER not set"
)


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rules = _load("wholedocs_rules_test", BENCH / "wholedocs" / "rules.py")
ledger = _load("lateral_ledger_test", BENCH / "ledger.py")


@pytest.mark.parametrize("name", ["prereg", "prereg-answers"])
def test_the_pre_registrations_are_the_hashed_ones(name):
    raw = (RESULTS / f"{name}.md").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == (RESULTS / f"{name}.sha256").read_text().strip()


def test_a_window_keeps_the_neighbours_of_a_kept_sentence_inside_its_paragraph():
    assert rules.widen([False, False, True, False, False, False], 2) == [
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert rules.widen([True, False, False], 0) == [True, False, False]
    with pytest.raises(ValueError):
        rules.widen([True], -1)


def test_the_gate_drops_a_paragraph_and_an_unanswered_probability_passes():
    rule = rules.Rule(gate=0.75, cut=0.28, window=1)
    assert rules.paragraph_mask(True, 0.74, [0.9, 0.9], rule) == [False, False]
    assert rules.paragraph_mask(False, 0.99, [0.9], rule) == [False]
    assert rules.paragraph_mask(True, None, [0.1, 0.3, 0.1, 0.1], rule) == [
        True,
        True,
        True,
        False,
    ]
    assert rules.paragraph_mask(True, 0.8, [None, 0.1, 0.1], rule) == [True, True, False]
    assert rules.needs_sentence_call(True, 0.75, rule)
    assert not rules.needs_sentence_call(True, 0.749, rule)


def test_the_shipped_rule_is_the_identity_of_the_two_stages():
    assert rules.Rule(gate=0.40, cut=0.28, window=0) == rules.SHIPPED


def test_every_lateral_run_stayed_under_its_money_bars():
    assert ledger.jev_spent() <= ledger.JEV_TOTAL_USD
    assert ledger.cli_spent() <= ledger.CLI_TOTAL_USD


def _run(script: str, *extra: str) -> tuple[dict, str]:
    out = subprocess.run(
        [sys.executable, str(BENCH / "wholedocs" / script), "--qasper", QASPER, *extra],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=1800,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout), out.stderr


@needs_qasper
def test_the_derivation_replays_and_picks_the_registered_rule():
    extra = ("--hotpot", HOTPOT) if HOTPOT and pathlib.Path(HOTPOT).exists() else ()
    report, _ = _run("rescore.py", *extra)
    assert report["questions"] == 261
    assert report["chosen"] == {"gate": 0.75, "cut": 0.28, "window": 2}
    assert (report["chosen_score"]["all_gold"], report["chosen_score"]["kept_share"]) == (
        0.8697,
        0.2251,
    )
    assert (report["shipped_score"]["all_gold"], report["shipped_score"]["kept_share"]) == (
        0.8314,
        0.3148,
    )
    assert report["sentence_calls"] == {"shipped": 5308, "chosen": 2273}
    assert report["halves"]["both_bars_held_out"] == 26
    if "hotpot_confirm_descriptive" in report:
        hp = report["hotpot_confirm_descriptive"]
        assert (hp["shipped"]["sentence_joint"], hp["chosen"]["sentence_joint"]) == (0.9033, 0.8333)


@needs_qasper
def test_the_confirmation_replays_as_published():
    report, err = _run("confirm.py")
    assert "live 0, missing 0" in err
    assert report["questions"] == 219
    assert report["by_set"] == {"fresh": 89, "second": 130}
    pooled = report["pooled"]
    assert (pooled["GW_frozen"]["all_gold"], pooled["GW_frozen"]["kept_share"]) == (0.8721, 0.21)
    assert (pooled["MS_shipped"]["all_gold"], pooled["MS_shipped"]["kept_share"]) == (
        0.8402,
        0.3024,
    )
    assert pooled["BM25_sentences_at_GW_text"]["all_gold"] == 0.4338
    assert report["calls"] == {
        "tournament": 839,  # 853 recorded, 855 live; the 14 repeats are reused since the memo fix
        "sentences_asked_all_kept_paragraphs": 4277,
        "sentences_needed_by_rule": 1766,
    }
    assert (report["Q1"], report["Q2"], report["Q3"]) == (True, True, True)
    assert report["verdict"] == "confirmed"


@needs_qasper
def test_the_answering_run_replays_from_the_cli_cache():
    report, _ = _run("answers.py")
    assert report["sizing"] == {"pilot_usd": 0.2556, "per_question_usd": 0.02556, "n": 146}
    assert (report["questions"], report["answered_by_both"]) == (146, 146)
    assert (report["arms"]["FULL"]["f1"], report["arms"]["GW"]["f1"]) == (0.4445, 0.4817)
    assert report["GW_minus_FULL_f1"] == {"mean": 0.0373, "ci95": [-0.0045, 0.0782]}
    assert report["tokens_share_GW_of_FULL"] == 0.3454
    assert (report["A1"], report["A2"], report["verdict"]) == (True, True, "confirmed")
