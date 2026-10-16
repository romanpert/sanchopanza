"""F2's public outputs (`benchmarks/memory_carry/handoff_publish.py`): rows keep numbers and flags
only, and H's cost takes the handoff turn's own cost when the resumed turn reports the session's
running total."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
pub = bench_module(ROOT / "benchmarks" / "memory_carry", "handoff_publish")

TOKENS = {"input": 2, "output": 627, "cache_read": 23413, "cache_write": 299}


def h_row() -> dict:
    return {"scene": "h_batch", "model": "sonnet", "arm": "H", "repeat": 1,
            "folder": "C:/somewhere/w16/r2/t00-b", "kept_all": True, "cost": 0.198253,
            "given": ["a", "b"], "native_after_1": [], "stderr": "private",
            "sessions": [{"tag": "session-1", "cost": 0.060688, "final": "the agent's words",
                          "init": {"session_id": "abc", "version": "2.1.287",
                                   "model": "claude-sonnet-5-5", "mcp": {"x": "connected"}},
                          "native": ["C:/somewhere/memory/x.md"]},
                         {"tag": "session-2", "cost": 0.0647244}],
            "handoff": {"cost": 0.0728406, "tokens": TOKENS, "chars": 900,
                        "text": "secret plan", "names": {"C": True, "D": True},
                        "init": {"session_id": "abc"}}}  # fmt: skip


def test_public_rows_keep_numbers_and_flags_only() -> None:
    row = pub.public_row(h_row())
    text = json.dumps(row)
    for private in ("C:/somewhere", "the agent's words", "secret plan", "abc", "private",
                    "connected"):  # fmt: skip
        assert private not in text
    assert row["folder"] == "t00-b" and row["given"] == 2 and row["native_after_1"] == 0
    assert row["sessions"][0]["init"]["version"] == "2.1.287"
    assert row["sessions"][0]["native"] == 1 and row["handoff"]["chars"] == 900


def test_h_cost_takes_the_handoff_turn_s_own_cost() -> None:
    # Measured on F2 (Sonnet 5.5, h_batch r1): session 1 0.060688, the resumed turn reported
    # 0.0728406, its own tokens price to 0.0121526 at Claude Code's rates.
    cost = pub.handoff_cost
    assert cost.priced(TOKENS, "sonnet") == pytest.approx(0.0728406 - 0.060688, abs=1e-9)
    got = cost.own_row(h_row())
    assert got["handoff"]["cost"] == pytest.approx(0.0121526, abs=1e-9)
    assert got["handoff"]["cost_reported_total"] == 0.0728406
    assert got["handoff"]["cost_source"] == cost.RUNNING
    assert got["cost"] == pytest.approx(0.198253 - 0.060688)
    assert cost.own_row(got) == got  # already at its own cost
    n0 = {**h_row(), "arm": "N0"}
    assert cost.own_row(n0) == n0
    assert pub.public_row(h_row())["handoff"]["cost"] == pytest.approx(0.0121526, abs=1e-9)


def w17_row(arm: str, kept: bool) -> dict:
    return {"scene": "h_batch", "model": "sonnet", "arm": arm, "repeat": 3, "line": "bare",
            "scope": "user", "call_cap": 0.5, "folder": "C:/somewhere/w18/r1/t00-c",
            "kept_all": kept, "task_pass": kept, "fact_pass": kept, "decision_pass": kept,
            "intact_pass": True, "tests_pass": True, "cost": 0.12, "jev_usd": 0.0002,
            "sendbacks_other_rule": 0, "given": ["UserPromptSubmit:abc-001"] if arm == "S"
            else [], "native_after_1": [], "hook_starts": 2 if arm == "S" else 0,
            "handoff": {},
            "sessions": [{"tag": "session-1", "cost": 0.06, "seconds": 30.0,
                          "init": {"session_id": "abc", "skill_names": ["sanchopanza-code"],
                                   "memory_auto": "C:/somewhere/memory/"}},
                         {"tag": "session-2", "cost": 0.06, "seconds": 31.0,
                          "touched": []}]}  # fmt: skip


def test_w17_rows_keep_the_stratum_and_the_send_backs() -> None:
    row = pub.public_row(w17_row("S", True))
    text = json.dumps(row)
    for private in ("C:/somewhere", "abc", "skill_names", "memory_auto"):
        assert private not in text
    assert row["line"] == "bare" and row["scope"] == "user" and row["call_cap"] == 0.5
    assert row["sendbacks_other_rule"] == 0 and row["given"] == 1 and "handoff" not in row


def test_w17_runs_are_analysed_by_their_own_sealed_analysis() -> None:
    rows = [w17_row("S", True), w17_row("N0", False)]
    got = pub.analysis(rows, "w17-sonnet", None)
    assert got == pub.handoff_pairs.analyse(rows, "sonnet", None, pub.planned("w17-sonnet"))
    assert got["strata"]["bare"]["kept_all"] == {"N0": 0, "S": 1}
    assert pub.analysis([pub.public_row(r) for r in rows], "w17-sonnet", None) == got


def test_w17_tables_must_match_the_night_in_every_field() -> None:
    table = {"verdict": "x", "cost_median_usd": {"S": 1.0}, "cost_ratio_median": 1.0}
    other = {**table, "cost_median_usd": {"S": 2.0}}
    assert pub.same_as_night(other, table, "f2-sonnet")  # F2: H's handoff turn re-costed
    assert not pub.same_as_night(other, table, "w17-sonnet")
    assert pub.same_as_night(table, table, "w17-sonnet")


def test_runs_default_to_f2_and_take_the_named_ones() -> None:
    assert pub.runs_of([]) == ("f2-pilot", "f2-sonnet", "f2-opus")
    assert pub.runs_of(["w17-sonnet"]) == ("w17-sonnet",)
    with pytest.raises(SystemExit):
        pub.runs_of(["w17-nope"])


def test_turn_own_reads_each_kind_of_report() -> None:
    cost = pub.handoff_cost
    own = cost.priced(TOKENS, "sonnet")
    assert cost.turn_own(0.06 + own, 0.06, TOKENS, "sonnet") == (pytest.approx(own),
                                                                  cost.RUNNING)  # fmt: skip
    assert cost.turn_own(own, 0.06, TOKENS, "sonnet") == (own, cost.OWN)
    assert cost.turn_own(0.5, 0.06, TOKENS, "sonnet") == (pytest.approx(own), cost.PRICED)
    assert cost.turn_own(0.5, 0.06, None, "sonnet") == (0.5, cost.OWN)
