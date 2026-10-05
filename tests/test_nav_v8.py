"""v8's development runner: confirmation 4's arms on G3 G6 I2 G4 G8 G1, with v8's switches in
two new arms. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("browse_nav_v8", ROOT / "benchmarks/browse/nav_v8.py")
v8 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_v8"] = v8
spec.loader.exec_module(v8)
v8.install()
nav = v8.nav


def test_the_round_is_six_tasks_five_arms_two_runs_under_12_usd():
    assert [t[0] for t in v8.TASKS] == ["G3", "G6", "I2", "G4", "G8", "G1"]
    assert v8.ARMS == ("HAIKU", "HAIKU-V7", "HAIKU-V8", "SONNET", "SONNET-V8")
    assert v8.RUNS == 2 and v8.CEILING_USD <= 12.00 and nav.SESSION_MAX_USD == 1.00
    assert len(nav.phase.planned(v8.TASKS, [1, 2], v8.ARMS)) == 60
    assert {nav.MODELS[a] for a in v8.ARMS} == {"claude-haiku-4-5", "claude-sonnet-5"}
    assert nav.MODELS["SONNET-V8"] == "claude-sonnet-5"
    for tool in ("SendMessage", "ListAgents", "ScheduleWakeup", "CronCreate", "RemoteTrigger"):
        assert tool in nav.DISALLOWED.split()


def test_each_arm_gets_its_hooks_and_env_in_its_own_settings_only(tmp_path):
    from sanchopanza.harness.crawl_hook import V8_HOOKS
    from sanchopanza.harness.install import CRAWL_HOOKS

    def read(arm):
        return json.loads(v8.settings_for(arm, tmp_path).read_text("utf-8"))

    for plain in ("HAIKU", "SONNET"):
        assert "hooks" not in read(plain) and "env" not in read(plain)
    v7 = read("HAIKU-V7")
    assert {e: v[0]["matcher"] for e, v in v7["hooks"].items()} == CRAWL_HOOKS
    assert v7["env"] == {"SANCHOPANZA_CRAWL_LINE_VERSION": "6", "SANCHOPANZA_CRAWL_NOTES": "1"}
    for arm in ("HAIKU-V8", "SONNET-V8"):
        got = read(arm)
        assert {e: v[0]["matcher"] for e, v in got["hooks"].items()} == {**CRAWL_HOOKS, **V8_HOOKS}
        commands = {h["command"] for v in got["hooks"].values() for h in v[0]["hooks"]}
        assert commands == {v8.conf3.crawl_command()}
        assert got["env"] == {
            "SANCHOPANZA_CRAWL_LINE_VERSION": "6",
            "SANCHOPANZA_CRAWL_NOTES": "2",
            "SANCHOPANZA_CRAWL_ECHO": "short",
            "SANCHOPANZA_CRAWL_LINE_AT": "prompt",
        }
        assert got["permissions"] == read("HAIKU")["permissions"]


def _row(arm, evaluates=2, ok=True, answer="ANSWER: 6"):
    return {"task": "G6", "run": 1, "arm": arm, "ok": ok, "workdir": "x", "success": True,
            "list_usd": 0.1, "answer": answer,
            "tools": {"mcp__playwright__browser_evaluate": evaluates}}  # fmt: skip


LINE = "never a URL pattern you guessed"
GUARD = "/* sanchopanza notes */"
CUT = "your function, inside sanchopanza's evaluate guard (not repeated)"
ECHO = "await page.evaluate('/* sanchopanza evaluate guard */ async"


@pytest.mark.parametrize(
    ("arm", "task", "text", "not_run"),
    [
        ("HAIKU-V8", "G6", f"{LINE} {GUARD} {CUT}", False),
        ("HAIKU-V8", "G6", f"{GUARD} {CUT}", True),  # no line on a gathering prompt
        ("HAIKU-V8", "I2", f"{GUARD} {CUT}", False),
        ("HAIKU-V8", "I2", f"{LINE} {GUARD} {CUT}", True),  # the line on an acting prompt
        ("HAIKU-V8", "G6", f"{LINE} {GUARD} {ECHO}", True),  # the echo left uncut
        ("SONNET-V8", "G6", f"{LINE} {CUT}", True),  # an evaluate the guard never wrapped
        ("HAIKU-V7", "I2", f"{LINE} {GUARD}", False),
        ("HAIKU-V7", "G6", GUARD, True),
        ("HAIKU", "G6", "", False),
        ("SONNET", "G6", CUT, True),
    ],
)
def test_a_session_counts_only_with_exactly_its_arms_treatment(
    monkeypatch, arm, task, text, not_run
):
    monkeypatch.setattr(nav, "one_session", lambda t, run, a: _row(a))
    monkeypatch.setattr(v8.conf3, "_transcript", lambda workdir: text)
    the_task = next(t for t in v8.TASKS if t[0] == task)
    assert bool(v8.one_session(the_task, 1, arm).get("not_run")) is not_run


def _use(tool_input):
    block = {"type": "tool_use", "name": "mcp__playwright__browser_evaluate", "input": tool_input}
    return json.dumps({"message": {"role": "assistant", "content": [block]}})


def test_an_evaluate_with_no_function_is_not_one_the_guard_should_have_wrapped(monkeypatch):
    """I2 run 1, HAIKU-V8: the only evaluate sent `{"code": ...}`, the guard left it alone as it
    should, and the session was marked not_run for a missing wrapper."""
    malformed = "\n".join(["not json", _use({"code": "window.scrollBy(0, 300)"})])
    monkeypatch.setattr(nav, "one_session", lambda t, run, a: _row(a, evaluates=1))
    monkeypatch.setattr(v8.conf3, "_transcript", lambda workdir: malformed)
    assert not v8.one_session(v8.TASKS[2], 1, "HAIKU-V8").get("not_run")
    unwrapped = "\n".join([LINE, _use({"function": "() => 1"})])
    monkeypatch.setattr(v8.conf3, "_transcript", lambda workdir: unwrapped)
    assert v8.one_session(v8.TASKS[1], 1, "HAIKU-V8")["not_run"]
    assert v8.guardable_evaluates(malformed, 1) == 0
    assert v8.guardable_evaluates("plain text", 3) == 3


def test_the_v8_notes_are_counted_as_results_not_as_the_wrappers_code(monkeypatch):
    code = "' clicks did not change the page text' 'fetched JSON rows ' + sp.rows"
    text = f"{LINE} {GUARD} {CUT} {code} 5 clicks did not change the page text: x " + (
        "fetched JSON rows 332, distinct 298." * 2
    )
    monkeypatch.setattr(nav, "one_session", lambda t, run, a: _row(a))
    monkeypatch.setattr(v8.conf3, "_transcript", lambda workdir: text)
    row = v8.one_session(v8.TASKS[1], 1, "HAIKU-V8")
    assert (row["click_notes"], row["rows_notes"], row["echo_cut"]) == (1, 2, 1)


@pytest.mark.parametrize(
    ("ok", "answer", "stderr", "hit"),
    [
        (False, "API Error: 429 rate_limit_error", "", True),
        (False, "", "Error: 429 Too Many Requests", True),
        (True, "You've hit your weekly limit", "", True),
        (True, "Done.\nANSWER: 429", "", False),  # a count of 429 is an answer
        (False, "runner: TimeoutExpired", "", False),
    ],
)
def test_a_429_or_a_usage_limit_is_caught(tmp_path, ok, answer, stderr, hit):
    (tmp_path / "stderr.txt").write_text(stderr, encoding="utf-8")
    row = {**_row("HAIKU", ok=ok, answer=answer), "workdir": str(tmp_path)}
    assert v8.limit_hit(row) is hit


def test_a_limit_stops_the_whole_round_and_says_stop_limit(monkeypatch, tmp_path):
    calls = []

    def session(task, run, arm):
        calls.append(arm)
        return _row(arm, ok=False, answer="API Error: 429")

    monkeypatch.setattr(nav, "one_session", session)
    monkeypatch.setattr(v8.conf3, "_transcript", lambda workdir: "")
    path = tmp_path / "s.jsonl"
    plan = nav.phase.planned(v8.TASKS, [1, 2], v8.ARMS)
    code, rows = v8._run(plan, path, 12.0)
    assert code == 2 and len(calls) == 1 and rows[0]["not_run"]
    assert v8.STOP_LIMIT in path.with_suffix(".log").read_text(encoding="utf-8")


def test_the_ceiling_counts_every_session_paid_for(monkeypatch, tmp_path):
    monkeypatch.setattr(nav, "one_session", lambda t, run, a: {**_row(a), "list_usd": 0.9})
    monkeypatch.setattr(v8.conf3, "_transcript", lambda workdir: "")
    plan = nav.phase.planned(v8.TASKS, [1, 2], ("HAIKU",))
    code, rows = v8._run(plan, tmp_path / "s.jsonl", 3.0)
    assert code == 1 and sum(r["list_usd"] for r in rows) <= 3.0


def test_the_analysis_gives_the_two_ratios_v8_is_for():
    rows = [{"task": t, "run": run, "arm": arm, "success": True, "list_usd": usd, "turns": 4}
            for t in v8.TASK_IDS for run in (1, 2)
            for arm, usd in (("HAIKU", 0.10), ("HAIKU-V8", 0.12), ("SONNET", 0.08),
                             ("SONNET-V8", 0.06))]  # fmt: skip
    out = v8.analyse(rows)
    assert out["ratios"]["I2 HAIKU-V8/HAIKU"] == 1.2
    assert out["ratios"]["G4+G8 SONNET-V8/SONNET"] == 0.75
    assert out["tasks"]["G6"]["HAIKU"] == {"right": "2/2", "mean_usd": 0.1, "turns": [4, 4]}
    assert out["arms"]["SONNET-V8"]["sessions"] == 12
