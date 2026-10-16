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


def test_turn_own_reads_each_kind_of_report() -> None:
    cost = pub.handoff_cost
    own = cost.priced(TOKENS, "sonnet")
    assert cost.turn_own(0.06 + own, 0.06, TOKENS, "sonnet") == (pytest.approx(own),
                                                                  cost.RUNNING)  # fmt: skip
    assert cost.turn_own(own, 0.06, TOKENS, "sonnet") == (own, cost.OWN)
    assert cost.turn_own(0.5, 0.06, TOKENS, "sonnet") == (pytest.approx(own), cost.PRICED)
    assert cost.turn_own(0.5, 0.06, None, "sonnet") == (0.5, cost.OWN)
