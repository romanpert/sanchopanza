"""The counts in `docs/results/2026-09-25-wide/README.md`, recomputed from its rows.

Two concurrent runs share `runs-5.jsonl` (see the README): rows with `wrong_calls` are run B,
rows without it (plus `runs-5-first-four.jsonl`) are run A. Errored rows are excluded.
"""

from __future__ import annotations

import json
import pathlib
from collections import defaultdict

import pytest

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "docs" / "results" / "2026-09-25-wide"

if not (RESULTS / "runs-5.jsonl").exists():  # pragma: no cover
    pytest.skip("wide catalog results not present", allow_module_level=True)


def _rows(name: str) -> list[dict]:
    path = RESULTS / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


ALL = [r for r in _rows("runs-5.jsonl") + _rows("runs-5-first-four.jsonl") if "error" not in r]
RUN_A = [r for r in ALL if "wrong_calls" not in r]
RUN_B = [r for r in ALL if "wrong_calls" in r]


def _paired(rows: list[dict]) -> dict[str, list[dict]]:
    by: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by[(r["suite"], r["task"])][r["arm"]] = r
    keys = sorted(k for k, arms in by.items() if len(arms) == 3)
    return {arm: [by[k][arm] for k in keys] for arm in ("full", "search", "sancho")}


def _usd(rows: list[dict]) -> float:
    return round(sum(r["usd_model"] + r["usd_jev"] for r in rows), 3)


def test_run_a_search_matches_the_window_at_a_third_of_its_cost():
    p = _paired(RUN_A)
    assert [sum(r["success"] for r in p[a]) for a in ("full", "search", "sancho")] == [7, 8, 8]
    assert len(p["full"]) == 9
    assert (_usd(p["full"]), _usd(p["search"]), _usd(p["sancho"])) == (4.581, 0.575, 1.624)


def test_run_b_has_no_call_to_a_distractor_in_any_arm():
    p = _paired(RUN_B)
    assert len(p["full"]) == 5
    assert [sum(r["success"] for r in p[a]) for a in ("full", "search", "sancho")] == [4, 4, 4]
    assert all(r["wrong_calls"] == 0 for a in p for r in p[a])


def test_the_window_opened_the_near_duplicate_workspace_server_most_often():
    sancho = [r for r in ALL if r["arm"] == "sancho"]
    assert len(sancho) == 17
    assert sum("mcp_google_workspace" in r["window"] for r in sancho) == 11


def test_only_travel_and_workspace_were_reached_but_one_banking_row():
    assert {r["suite"] for r in ALL if r["suite"] != "banking"} == {"travel", "workspace"}
    banking = [r for r in ALL if r["suite"] == "banking"]
    assert [(r["arm"], "wrong_calls" in r) for r in banking] == [("search", True)]


def test_claude_code_hook_changes_nothing_measurable():
    mcp = _rows("claude-code-mcp.jsonl")
    base = [r for r in mcp if r["arm"] == "base"]
    hook = [r for r in mcp if r["arm"] == "hook"]
    assert sum(r["right_server"] for r in base) == sum(r["right_server"] for r in hook) == 7
    builtin = _rows("claude-code-builtin.jsonl")
    assert all(r["target_called"] for r in builtin)
