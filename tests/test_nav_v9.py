"""v9's development runner: confirmation 5's misses (H1 H4 H5 H7) and two crawls for no
regression (H2 H8), Claude Code alone against v8.1 plus notes v3, and Sonnet with the notes and
no line. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("browse_nav_v9", ROOT / "benchmarks/browse/nav_v9.py")
v9 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_v9"] = v9
spec.loader.exec_module(v9)
v9.install()
nav = v9.nav

LINE = "never a URL pattern you guessed"
GUARD = "/* sanchopanza notes */"
CUT = "your function, inside sanchopanza's evaluate guard (not repeated)"


def test_the_round_is_six_seen_tasks_five_arms_two_runs_under_10_usd():
    assert [t[0] for t in v9.TASKS] == ["H1", "H4", "H5", "H7", "H2", "H8"]
    assert v9.ARMS == ("HAIKU", "HAIKU-V9", "SONNET", "SONNET-V9", "SONNET-NOTES")
    assert len(v9.planned()) == 60 and v9.RUNS == 2
    assert v9.CEILING_USD <= 10.00 and nav.SESSION_MAX_USD == 1.00
    assert {nav.MODELS[a] for a in v9.ARMS} == {"claude-haiku-4-5", "claude-sonnet-5"}
    assert nav.MODELS["SONNET-NOTES"] == "claude-sonnet-5"
    assert v9.SMOKE == (("H1", "HAIKU-V9"), ("H5", "HAIKU-V9"))
    assert v9.CLAUDE_VERSION == "2.1.287"


def test_each_arm_gets_v81s_hooks_and_its_own_env_in_its_own_settings_only(tmp_path):
    def read(arm, folder):
        folder.mkdir(exist_ok=True)
        return json.loads(v9.settings_for(arm, folder).read_text("utf-8"))

    for plain in ("HAIKU", "SONNET"):
        got = read(plain, tmp_path / plain)
        assert "hooks" not in got and "env" not in got
    v81 = json.loads(v9.v8.settings_for("HAIKU-V81", tmp_path).read_text("utf-8"))
    for arm in ("HAIKU-V9", "SONNET-V9", "SONNET-NOTES"):
        got = read(arm, tmp_path / arm)
        assert got["hooks"] == v81["hooks"] and got["permissions"] == v81["permissions"]
        assert got["env"]["SANCHOPANZA_CRAWL_NOTES"] == "3"
        assert {k: v for k, v in got["env"].items() if k not in (
            "SANCHOPANZA_CRAWL_NOTES", "SANCHOPANZA_CRAWL_LINE")} == {
            k: v for k, v in v81["env"].items() if k != "SANCHOPANZA_CRAWL_NOTES"}  # fmt: skip
    assert read("SONNET-NOTES", tmp_path / "n")["env"]["SANCHOPANZA_CRAWL_LINE"] == "0"
    assert "SANCHOPANZA_CRAWL_LINE" not in read("SONNET-V9", tmp_path / "s")["env"]


def _row(arm, ok=True, answer="ANSWER: 72", evaluates=2):
    return {"task": "H1", "run": 1, "arm": arm, "ok": ok, "workdir": "x", "success": True,
            "list_usd": 0.1, "answer": answer,
            "tools": {"mcp__playwright__browser_evaluate": evaluates}}  # fmt: skip


@pytest.mark.parametrize(
    ("arm", "text", "not_run"),
    [
        ("HAIKU-V9", f"{LINE} {GUARD} {CUT}", False),
        ("HAIKU-V9", f"{GUARD} {CUT}", True),  # no line on a gathering prompt
        ("SONNET-V9", f"{LINE} {CUT}", True),  # an evaluate the guard never wrapped
        ("SONNET-NOTES", f"{GUARD} {CUT}", False),
        ("SONNET-NOTES", f"{LINE} {GUARD} {CUT}", True),  # the notes arm must have no line
        ("SONNET-NOTES", f"{CUT}", True),
        ("HAIKU", "", False),
        ("SONNET", LINE, True),
    ],
)
def test_a_session_counts_only_with_exactly_its_arms_treatment(monkeypatch, arm, text, not_run):
    monkeypatch.setattr(nav, "one_session", lambda t, run, a: _row(a))
    monkeypatch.setattr(v9.conf3, "_transcript", lambda workdir: text)
    assert bool(v9.one_session(v9.TASKS[0], 1, arm).get("not_run")) is not_run


@pytest.mark.parametrize(
    ("ok", "answer", "stderr", "hit"),
    [
        (False, 'API Error: 429 {"type":"error","error":{"type":"rate_limit_error"}}', "", True),
        (False, "", 'API Error: 429 {"type":"rate_limit_error"}', True),
        (True, "You've hit your weekly limit · resets 9pm", "", True),
        (False, "Claude AI usage limit reached|1759", "", True),
        # the site's own 429s are the agent's business, not a reason to stop the round
        (False, "The site answered HTTP 429 Too Many Requests on page 3.", "", False),
        (False, "", "playwright: 429 Too Many Requests from api.potterdb.com", False),
        (True, "Paged slowly after a 429 rate limit from the site.\nANSWER: 203", "", False),
        (True, "Done.\nANSWER: 429", "", False),
        (False, "runner: TimeoutExpired", "", False),
    ],
)
def test_only_anthropics_429_or_usage_limit_stops_the_round(tmp_path, ok, answer, stderr, hit):
    (tmp_path / "stderr.txt").write_text(stderr, encoding="utf-8")
    row = {**_row("HAIKU", ok=ok, answer=answer), "workdir": str(tmp_path)}
    assert v9.api_limit_hit(row) is hit


def test_a_sites_429_does_not_stop_the_round(monkeypatch, tmp_path):
    def session(task, run, arm):
        return {**_row(arm, ok=False, answer="HTTP 429 Too Many Requests"),
                "workdir": str(tmp_path)}  # fmt: skip

    monkeypatch.setattr(nav, "one_session", session)
    monkeypatch.setattr(v9.conf3, "_transcript", lambda workdir: "")
    code, rows = v9.run(v9.planned()[:3], tmp_path / "s.jsonl", 9.0)
    assert code == 0 and len(rows) == 3 and not any(r.get("limit_hit") for r in rows)


def test_anthropics_429_stops_the_whole_round_and_says_stop_limit(monkeypatch, tmp_path):
    calls = []

    def session(task, run, arm):
        calls.append(arm)
        return {**_row(arm, ok=False, answer="API Error: 429 rate_limit_error"),
                "workdir": str(tmp_path)}  # fmt: skip

    monkeypatch.setattr(nav, "one_session", session)
    monkeypatch.setattr(v9.conf3, "_transcript", lambda workdir: "")
    path = tmp_path / "s.jsonl"
    code, rows = v9.run(v9.planned(), path, 9.0)
    assert code == 2 and len(calls) == 1 and rows[0]["not_run"]
    assert v9.v8.STOP_LIMIT in path.with_suffix(".log").read_text(encoding="utf-8")


def test_the_ceiling_counts_every_session_paid_for(monkeypatch, tmp_path):
    monkeypatch.setattr(nav, "one_session", lambda t, run, a: {**_row(a), "list_usd": 0.9})
    monkeypatch.setattr(v9.conf3, "_transcript", lambda workdir: "")
    code, rows = v9.run(v9.planned(), tmp_path / "s.jsonl", 3.0)
    assert code == 1 and sum(r["list_usd"] for r in rows) <= 3.0


def _result(text: str) -> str:
    block = {"type": "tool_result", "content": [{"type": "text", "text": text}]}
    return json.dumps({"message": {"content": [block]}})


def test_the_v3_notes_are_counted_by_kind_in_what_the_agent_saw():
    seen = [
        "### sanchopanza note\nsanchopanza: ... which says: Link header: next https://x?page=2.",
        "### sanchopanza note\nsanchopanza: ... which says: JSON meta.pagination.last: 55.",
        "### sanchopanza note\nsanchopanza: says: a JSON array of exactly 1000 items and no total",
        "### sanchopanza note\nsanchopanza: the one JSON response this call read held exactly",
        "### sanchopanza note\nsanchopanza: fetched JSON rows 18, distinct 6.",
    ]
    code = "said.push('Link header: ' + lk)"  # the wrapper's code is not a note
    text = "\n".join([*map(_result, seen), json.dumps({"x": code})])
    assert v9.v9_counts(text) == {"link_notes": 1, "keys_notes": 1, "round_notes": 1,
                                  "one_notes": 1}  # fmt: skip


def test_the_analysis_gives_each_arm_against_its_base_as_the_prereg_would():
    usd = {"HAIKU": 0.10, "HAIKU-V9": 0.08, "SONNET": 0.10, "SONNET-V9": 0.11,
           "SONNET-NOTES": 0.09}  # fmt: skip
    rows = [{"task": t, "run": run, "arm": arm, "success": arm != "HAIKU", "list_usd": usd[arm],
             "turns": 4} for t in v9.TASK_IDS for run in (1, 2) for arm in v9.ARMS]  # fmt: skip
    out = v9.analyse(rows)
    assert out["ratios"]["crawls HAIKU-V9/HAIKU"] == 0.8
    assert out["ratios"]["crawls SONNET-NOTES/SONNET-V9"] == 0.818
    like = out["prereg_like"]["HAIKU-V9 vs HAIKU"]
    assert like == {"ratio_total": 0.8, "tasks_cheaper": "6/6", "right": "12/12 vs 0/12"}
    assert out["prereg_like"]["SONNET-V9 vs SONNET"]["tasks_cheaper"] == "0/6"
    assert out["tasks"]["H1"]["SONNET-NOTES"]["right"] == "2/2"
