"""The completion-check numbers, replayed from `fixtures/completion-jev.jsonl`. No network.

The trajectories are this repository's own AgentDojo runs (in `docs/results/`), so this
replays without any external data. `docs/results/2026-09-25-completion/README.md` quotes it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "completion_run", ROOT / "benchmarks" / "completion" / "run.py"
)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

CASES = run.load()
if not CASES:
    pytest.skip("AgentDojo run files not present", allow_module_level=True)
ROWS = asyncio.run(run.table(CASES))
REPORT = run.analyze(ROWS)


def test_every_trajectory_was_answered_from_the_recording():
    assert REPORT["n"] == 655
    assert REPORT["missing"]["jev"] == 0


def test_jev_against_trusting_the_agent():
    assert REPORT["all"]["trust"] == 0.5221
    assert REPORT["all"]["jev"] == 0.9374
    assert REPORT["held_out"]["jev"] == 0.9453
    assert REPORT["jev_auc"] == 0.9807
    assert REPORT["P13"] is True


def test_the_derived_block_cut_holds_out():
    held = [r for r in ROWS if r["half"] == "held_out" and r["jev_p"] is not None]
    blocked = [r for r in held if r["jev_p"] < 0.5]
    right = sum(r["label"] == "not_done" for r in blocked)
    assert (len(blocked), right) == (147, 138)


def test_the_cascade_matches_sonnet_at_a_fifth_of_its_cost():
    if REPORT["missing"]["sonnet"]:
        pytest.skip("Sonnet answers not recorded")
    assert REPORT["held_out"]["sonnet"] == 0.9605
    block = REPORT["cascade_sonnet"]
    assert block["tau"] == 0.7
    assert block["held_out"]["cascade_acc"] == 0.9605
    assert block["held_out"]["escalated"] == 63
    assert block["held_out"]["cost_ratio"] == 0.2148
    assert REPORT["P14"] is True
