"""Batch jev114-l2: Jev 1.14 against 1.13 on check_done and the permission cascade. No network.

The statistics are pinned on small hand-made cases. The September replay must reproduce the
published figures through this runner, which is what makes its 1.13 and 1.14 arms comparable
with them; it needs R-Judge and ATBench-Codex locally (not redistributed), or skips.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import os
import pathlib

import pytest

from .helpers import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "results" / "2026-10-15-jev114-l2"
_spec = importlib.util.spec_from_file_location(
    "jev114_l2", ROOT / "benchmarks" / "cascade" / "jev114.py"
)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

# The runner's own defaults, so that this test reads what a live run reads.
RJUDGE = bench.default_path("SANCHOPANZA_RJUDGE", "R-Judge")
CODEX = dataset("CODEX") or bench.default_path(
    "SANCHOPANZA_ATBENCH_CODEX", "atbench-codex-test.json"
)


def test_loading_the_runner_leaves_the_harness_variable_alone():
    assert os.environ.get("SANCHOPANZA_EVAL_HARNESS") != "sanchopanza_jev114_replay_harness"


def test_the_stand_in_harness_cannot_call_claude():
    with pytest.raises(RuntimeError, match="replay only"):
        asyncio.run(bench._NoClaude().run("prompt", schema={}))


def test_auc_counts_ties_as_a_half():
    assert bench.auc([0.1, 0.4, 0.35, 0.8], [False, False, True, True]) == 0.75
    assert bench.auc([0.5, 0.5], [False, True]) == 0.5
    assert bench.auc([0.2, 0.3], [True, True]) is None


def test_exact_mcnemar():
    a = [True] * 10 + [False] * 2
    b = [False] * 10 + [True] * 2
    result = bench.mcnemar_exact(a, b)
    assert (result["only_a"], result["only_b"]) == (10, 2)
    assert result["p"] == pytest.approx(0.0386, abs=1e-4)
    assert bench.mcnemar_exact([True, False], [True, False])["p"] == 1.0


def test_holm_is_step_down_and_monotone():
    adjusted = bench.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})


def test_reading():
    assert bench.reading(0.03, 0.01, 0.01) == "better"
    assert bench.reading(-0.03, -0.05, 0.01) == "worse"
    assert bench.reading(-0.005, -0.015, 0.5) == "not worse"
    assert bench.reading(-0.005, -0.025, 0.5) == "inconclusive"


def test_paired_bootstrap_of_identical_arms_is_zero():
    hits = [True, False, True, True]
    assert bench.bootstrap_diff(hits, hits, lambda xs: sum(xs) / len(xs)) == (0.0, 0.0, 0.0)
    assert bench.bootstrap_diff([], [], lambda xs: None) is None


def test_a_line_served_under_another_name_does_not_count_for_a_live_arm():
    assert bench.served_elsewhere("14", "jev-1.14.1")
    assert bench.served_elsewhere("13r", "jev-latest")
    assert not bench.served_elsewhere("14", "jev-1.14.0")
    assert not bench.served_elsewhere("rec", "jev-latest")


def test_the_registration_is_the_sealed_one():
    sealed = OUT / "prereg.sha256"
    if not sealed.exists():
        pytest.skip("not sealed yet")
    assert sealed.read_text(encoding="utf-8").strip() == bench.digest()


@pytest.mark.skipif(
    not (pathlib.Path(RJUDGE).exists() and CODEX and pathlib.Path(CODEX).exists()),
    reason="R-Judge or ATBench-Codex not present locally",
)
def test_the_september_replay_gives_the_published_figures():
    sets = bench.load_sets(argparse.Namespace(rjudge=RJUDGE, codex=CODEX))
    if not sets["completion"]:
        pytest.skip("AgentDojo run files not present")
    assert asyncio.run(bench.unknown_inputs(sets)) == 0
    claude = bench.claude_answers(sets)
    got = {
        name: bench.per_arm(name, asyncio.run(bench.jev_rows(cases, "rec")), claude[name])
        for name, cases in sets.items()
    }
    completion = got["completion"]
    assert (completion["alone"]["acc"], completion["alone"]["auc"]) == (0.9374, 0.9807)
    assert completion["P13"] and completion["P14_sonnet"]["held_out"]["cost_ratio"] == 0.2148
    opus = got["rjudge"]["opus_registered"]
    assert (opus["tau"], opus["held_out"]["cost_ratio"], opus["passes"]) == (0.8, 0.5681, False)
    sonnet = got["rjudge"]["P1_sonnet"]
    assert (sonnet["tau"], sonnet["held_out"]["cost_ratio"]) == (0.8, 0.5766)
    held = got["codex"]["confirm_held_out"]
    assert (held["answered"], held["primary"]["cascade_acc"], held["primary"]["cost_ratio"]) == (
        239,
        0.8033,
        0.3882,
    )
    assert got["codex"]["confirm_all_500"]["primary"]["cost_ratio"] == 0.3854


def test_sealed_originals_still_hold():
    for stem in bench.ORIGINAL_SEALS:
        base = ROOT / "docs" / "results" / stem
        raw = pathlib.Path(f"{base}.md").read_bytes().replace(b"\r\n", b"\n")
        held = pathlib.Path(f"{base}.sha256").read_text(encoding="utf-8").strip()
        assert hashlib.sha256(raw).hexdigest() == held


def _report():
    path = OUT / "analysis.json"
    if not path.exists():
        pytest.skip("no analysis yet")
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def test_the_published_verdicts():
    conclusions = _report()["conclusions"]
    assert conclusions["check_done"] == "recalibrate the cut on 1.14 first"
    assert conclusions["permission_cascade"] == "stay on 1.13"
    assert conclusions["codex_confirmation_with_14"] == "confirmed"
    assert conclusions["rjudge_under_bar_with_14"] is True
    assert conclusions["rjudge_bar_13r_vs_14_split_noise"] is True
    bar = conclusions["rjudge_opus_bar_50"]
    assert [bar[a]["cost_ratio"] for a in ("rec", "13r", "14")] == [0.5681, 0.6565, 0.439]


def test_the_published_comparisons():
    sets = _report()["sets"]
    got = {
        name: (
            c["acc"],
            c["acc_ci95"],
            c["mcnemar"]["only_a"],
            c["mcnemar"]["only_b"],
            c["reading"],
        )
        for name, c in ((n, s["14_vs_13r"]) for n, s in sets.items())
    }
    assert got == {
        "completion": ([0.9191, 0.9405], [-0.0336, -0.0107], 1, 15, "worse"),
        "rjudge": ([0.8967, 0.8739], [0.007, 0.0403], 18, 5, "better"),
        "codex": ([0.772, 0.788], [-0.036, 0.004], 9, 17, "inconclusive"),
    }
    assert sets["completion"]["14_vs_13r"]["auc_ci95"] == [-0.0196, -0.0059]


@pytest.mark.skipif(
    not (pathlib.Path(RJUDGE).exists() and CODEX and pathlib.Path(CODEX).exists()),
    reason="R-Judge or ATBench-Codex not present locally",
)
def test_both_live_arms_replay_from_their_fixtures():
    sets = bench.load_sets(argparse.Namespace(rjudge=RJUDGE, codex=CODEX))
    if not sets["completion"]:
        pytest.skip("AgentDojo run files not present")
    for arm, model in bench.MODELS.items():
        for cases in sets.values():
            rows = asyncio.run(bench.jev_rows(cases, arm))
            assert all(r["jev"] is not None for r in rows)
            assert {r["jev_model"] for r in rows} == {model}
    rows = asyncio.run(bench.jev_rows(sets["completion"], "14"))
    assert bench.alone(rows, "completion")["acc"] == 0.9191
