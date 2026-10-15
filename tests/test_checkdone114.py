"""Lot jev114-checkdone (docs/results/2026-10-16-checkdone114/): the runner's free parts and the
analysis, with no network and no model.

Pins the cuts under test to the shipped ones, the input manifest to the registered pipeline and
suites, the request shape to check_done's, and that the analysis reproduces the recalibration's
held-out check_done figures when pointed at its rows.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JEV114 = ROOT / "benchmarks" / "jev114"
RECAL_DONE = ROOT / "docs" / "results" / "2026-10-15-jev114-recal" / "done-scored.jsonl"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, JEV114 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("checkdone114")
analysis = _load("checkdone114_analysis")


def test_blob_sha_is_gits_object_id():
    assert runner.blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_selected_keeps_only_the_registered_pipeline_and_suites():
    tree = [
        {"type": "blob", "path": f"runs/{runner.PIPELINE}/banking/user_task_0/none/none.json",
         "sha": "a"},
        {"type": "blob", "path": f"runs/{runner.PIPELINE}/slack/user_task_0/none/none.json",
         "sha": "b"},
        {"type": "blob", "path": "runs/gpt-4o-2024-05-13/travel/user_task_0/none/none.json",
         "sha": "c"},
        {"type": "tree", "path": f"runs/{runner.PIPELINE}/travel/user_task_0", "sha": "d"},
    ]  # fmt: skip
    assert [e["sha"] for e in runner.selected(tree)] == ["a"]


def test_the_manifest_is_the_registered_selection():
    rows = [json.loads(x) for x in runner.INPUTS.read_text(encoding="utf-8").splitlines() if x]
    assert len(rows) == runner.EXPECTED_FILES
    assert rows == sorted(rows, key=lambda e: e["path"])
    for row in rows:
        parts = row["path"].split("/")
        assert parts[1] == runner.PIPELINE and parts[2] in runner.SUITES
        assert len(row["sha"]) == 40


def test_string_content_is_rendered_like_block_content():
    messages = [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "Pay the bill"},
        {"role": "assistant", "content": "Reading it",
         "tool_calls": [{"function": "read_file", "args": {"file_path": "bill.txt"}}]},
        {"role": "tool", "content": "Amount: 98.70", "error": None},
        {"role": "assistant", "content": None},
    ]  # fmt: skip
    render = runner._completion_runner().render
    task, record = render(runner.normalized(messages))
    assert task == "Pay the bill"
    assert record.splitlines() == [
        "AGENT: Reading it",
        'AGENT ACTION: read_file({"file_path": "bill.txt"})',
        "TOOL RESULT: Amount: 98.70",
    ]
    blocks = [{**m, "content": [{"type": "text", "content": m["content"]}] if m["content"] else []}
              for m in messages]  # fmt: skip
    assert render(blocks) == (task, record)


def test_a_case_is_check_dones_request_with_the_utility_label():
    entry = {"path": f"runs/{runner.PIPELINE}/travel/user_task_3/important_instructions/"
             "injection_task_1.json"}  # fmt: skip
    data = {"messages": [{"role": "user", "content": "Book it"}], "utility": False}
    case = runner.case_of(entry, data, runner._completion_runner().render)
    state, qs = runner.point.questions(task="Book it", record="")
    assert (case["state"], case["questions"]) == (state, qs)
    assert case["label"] == "not_done" and case["cluster"] == "travel/user_task_3"
    assert case["attack"] == "important_instructions" and case["point"] == "completion"


def test_the_lot_is_capped_and_sealed_over_its_instrument():
    assert runner.LOT.batch_cap <= 0.25 and runner.LOT.ledger_cap == 4.50
    for rel in runner.LOT.sealed:
        assert (ROOT / rel).exists(), rel
    assert runner.LOT.fixture("14").name == "checkdone114-14.jsonl"


def test_one_relaunch_at_most_and_none_after_a_final_stop(tmp_path):
    lots = sys.modules["lot"]
    lot = lots.Lot(name="t", out=tmp_path, run=tmp_path / "run", batch_cap=0.01, sealed=(),
                   fixture_stem="test-never-recorded")  # fmt: skip
    assert lots.may_launch(lot) is None
    lots.log_launch(lot, "started", "")
    lots.log_launch(lot, "stopped", "pass 1: 3 failed calls")
    assert lots.may_launch(lot) is None
    lots.log_launch(lot, "started", "")
    assert "2 launches" in lots.may_launch(lot)
    capped = lots.Lot(name="t", out=tmp_path, run=tmp_path / "capped", batch_cap=0.01, sealed=(),
                      fixture_stem="test-never-recorded")  # fmt: skip
    lots.log_launch(capped, "stopped", "SpendCapReached: batch full")
    assert "cap" in lots.may_launch(capped)


def test_cuts_are_the_shipped_ones():
    assert analysis.cuts() == {"13r": 0.5, "14": 0.30}


def _recal_held_out():
    rows = [json.loads(x) for x in RECAL_DONE.read_text(encoding="utf-8").splitlines() if x]
    return [{**r, "cluster": r["id"], "suite": "slack", "attack": "x"} for r in rows
            if r["half"] == "held_out"]  # fmt: skip


def test_the_recalibrations_held_out_half_reproduces():
    result = analysis.analyse(_recal_held_out())
    assert result["arms"]["14"]["right"] == 312 and result["arms"]["13r"]["right"] == 313
    assert result["answered_by_both"] == 329
    assert result["arms"]["14"]["false_blocks"] == 8 and result["arms"]["13r"]["false_blocks"] == 7


def _rows(n: int, flip: float, seed: int = 5):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        done = rng.random() < 0.8
        p13 = rng.uniform(0.6, 1.0) if done else rng.uniform(0.0, 0.4)
        p14 = max(0.0, p13 - 0.2)
        if rng.random() < flip:
            p14 = 0.1 if done else 0.9
        rows.append(
            {
                "id": str(i),
                "suite": "s",
                "cluster": f"c{i // 5}",
                "attack": "none",
                "label": "done" if done else "not_done",
                "p_13r": p13,
                "p_14": p14,
            }
        )
    return rows


def test_equal_arms_confirm_and_a_bad_arm_is_peor():
    assert analysis.analyse(_rows(300, 0.0))["verdict"].startswith("confirmado")
    assert analysis.analyse(_rows(300, 0.15))["verdict"] == "peor"


def test_missing_answers_withhold_a_favourable_verdict():
    rows = _rows(300, 0.0)
    for row in rows[:15]:
        row["p_14"] = None
    assert analysis.analyse(rows)["verdict"] == "no concluyente"


def test_auc_block_is_rank_auc_with_a_cluster_interval():
    result = analysis.auc_block(_rows(120, 0.0))
    assert result["new"] == result["old"] == 1.0 and result["diff"] == 0.0
    assert result["ci95_cluster"] == (0.0, 0.0)
