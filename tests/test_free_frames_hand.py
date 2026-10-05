"""The FRAMES pilot's hand-grade analysis: regrading, the base cut at 70 %, the before/after
matrix and the paired test. Synthetic rows only: no model, no network, no money."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hand = _load("browse_free_frames_hand", "benchmarks/browse/free_frames_hand.py")


def _row(task: str, arm: str, ok: bool, usd: float, traj: list[float], **extra) -> dict:
    return {"task": task, "arm": arm, "ok_auto": ok, "ok_before": ok, "list_usd": usd,
            "trajectory": traj, "cap_usd": hand.frames.CAPS[arm], "tools": {"WebSearch": 1},
            **extra}  # fmt: skip


def test_graded_applies_only_listed_verdicts() -> None:
    listed = hand.graded(_row("FR187", "HAIKU-SRC", True, 0.3, [0.3]))
    assert listed["ok_hand"] is False and listed["ok_hand_before"] is True
    kept = hand.graded(_row("FRX", "HAIKU", True, 0.3, [0.3]))
    assert kept["ok_hand"] is True and kept["ok_hand_before"] is True


def test_cut_row_cuts_before_the_last_call_only() -> None:
    cap = hand.frames.CAPS["HAIKU"]  # 0.60: the cut is at 0.42
    over = {**_row("T1", "HAIKU", True, 0.55, [0.2, 0.43, 0.55]), "ok_hand": True}
    cut = hand.cut_row(over)
    assert cut["cut"] and cut["ok_hand"] is False and cut["list_usd"] == 0.43
    last = {**_row("T2", "HAIKU", True, 0.421, [0.2, 0.40, 0.421]), "ok_hand": True}
    assert hand.cut_row(last)["cut"] is False and hand.cut_row(last)["ok_hand"] is True
    under = {**_row("T3", "HAIKU", False, 0.1, [0.05, 0.1]), "ok_hand": False}
    assert hand.cut_row(under)["list_usd"] == 0.1
    assert abs(cap * hand.CUT_FRACTION - 0.42) < 1e-9


def test_matrix_counts_fired_sessions_only() -> None:
    rows = [
        {"hook_fired": True, "b": True, "a": True},
        {"hook_fired": True, "b": True, "a": False},
        {"hook_fired": True, "b": False, "a": False},
        {"hook_fired": False, "b": False, "a": True},
    ]
    got = hand.matrix(rows, "b", "a")
    assert got == {"right->right": 1, "right->wrong": 1, "wrong->right": 0, "wrong->wrong": 1}


def test_paired_names_the_discordant_tasks() -> None:
    base = [{"task": t, "ok_hand": ok} for t, ok in (("A", True), ("B", True), ("C", False))]
    src = [{"task": t, "ok_hand": ok} for t, ok in (("A", True), ("B", False), ("C", False))]
    got = hand.paired(base, src)
    assert (got["a_only"], got["b_only"], got["a_only_tasks"]) == (1, 0, ["B"])
    assert got["p_exact"] == 1.0


def test_spend_split_divides_by_every_session_of_the_arm() -> None:
    rows = [{"list_usd": 0.3, "usd_after_block": 0.1}, {"list_usd": 0.1, "usd_after_block": None}]
    got = hand.spend_split(rows)
    assert got == {"usd_after_block_total": 0.1, "mean_usd_before_block": 0.15,
                   "mean_usd_after_block": 0.05}  # fmt: skip


def test_report_carries_no_text_beyond_ids_and_reasons() -> None:
    rows = [
        _row("FR1", arm, True, 0.1, [0.05, 0.1], hook_fired=arm.endswith("-SRC"),
             usd_after_block=0.02 if arm.endswith("-SRC") else None, answer_after="secret")
        for arm in hand.frames.ARMS
    ]  # fmt: skip
    out = hand.report(rows, None)
    assert "secret" not in repr(out)
    assert out["by_arm"]["SONNET-CUT70"]["right_hand"] == 1
    assert out["paired_HAIKU-SRC_vs_HAIKU"]["p_exact"] == 1.0
