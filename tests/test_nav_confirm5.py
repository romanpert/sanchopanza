"""The fifth confirmation: the crawl hook as v8.1 left it against Claude Code alone, Haiku and
Sonnet, on new crawls and four interactive tasks. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_nav_confirm5", ROOT / "benchmarks/browse/nav_confirm5.py"
)
conf5 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_confirm5"] = conf5
spec.loader.exec_module(conf5)
conf5.install()
nav = conf5.nav
OWN = {"nav_confirm5.py", "truth_confirm5.py", "check_tasks5.py"}
REUSED_HOSTS = {"books.toscrape.com"}  # a sandbox used before, on a category never used


def _used_urls() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "benchmarks").rglob("*.py"):
        if path.name not in OWN:
            text = path.read_text(encoding="utf-8", errors="replace")
            found |= {u.rstrip(".,)'\"") for u in re.findall(r"https?://[^\s\"'<>)]+", text)}
    return found


def test_the_new_tasks_are_on_urls_and_hosts_no_earlier_phase_named():
    used = _used_urls()
    hosts = {u.split("/")[2] for u in used if u.count("/") >= 2}
    new = [*conf5.CRAWLS, *conf5.INTERACTIVE[2:]]
    assert [t[0] for t in new] == [*(f"H{i}" for i in range(1, 9)), "I3", "I4"]
    for tid, url, question, _required in new:
        host = url.split("/")[2]
        assert url not in used and not any(u.startswith(url) for u in used), tid
        assert host in REUSED_HOSTS or host not in hosts, tid
        assert question.isascii() and '"' not in question, tid


def test_crawls_are_graded_on_their_answer_line_and_interactive_tasks_on_substrings():
    for tid, _url, _question, required in conf5.CRAWLS:
        assert nav.grade(f"Read it all.\nANSWER: {required[0]}", required, tid), tid
        assert not nav.grade(f"I found {required[0]}.", required, tid), "no ANSWER line"
        assert not nav.grade(f"ANSWER: 1{required[0]}", required, tid), tid
    i3, i4 = conf5.INTERACTIVE[2:]
    assert nav.grade("Balance: 6,196. Message: Transaction successful", i3[3], "I3")
    assert not nav.grade("Balance: 6596. Deposit Successful", i3[3], "I3")
    assert nav.grade("comments first program; checkboxes cb1; radioval rd3; dropdown dd5", i4[3],
                     "I4")  # fmt: skip
    assert not nav.grade("Checkbox 1, radio 3, Drop Down Item 5", i4[3], "I4")


# demoblaze's 15 product names (api.demoblaze.com, 2026-10-05). The first seal asked H7 for a count
# of 6, which a wrong ANSWER line naming "Nexus 6" would have passed.
BLAZE_NAMES = (
    "Samsung galaxy s6, Nokia lumia 1520, Nexus 6, Samsung galaxy s7, Iphone 6 32gb, Sony xperia "
    "z5, HTC One M9, Sony vaio i5, Sony vaio i7, Apple monitor 24, MacBook air, Dell i7 8gb, 2017 "
    "Dell 15.6 Inch, ASUS Full HD, MacBook Pro"
)


def test_no_product_name_on_an_answer_line_can_pass_h7():
    h7 = next(t for t in conf5.CRAWLS if t[0] == "H7")
    assert h7[3] == ["4"] and "less than $500" in h7[2]
    for wrong in ("2", "3", "5", "7"):
        assert not nav.grade(f"ANSWER: {wrong} ({BLAZE_NAMES}; $400, $360)", h7[3], "H7"), wrong


def test_the_plan_is_160_sessions_three_runs_a_crawl_and_four_an_interactive_task():
    plan = conf5.planned()
    assert len(plan) == 4 * (8 * 3 + 4 * 4) == 160
    assert {conf5.runs_of(t[0]) for t in conf5.CRAWLS} == {3}
    assert {conf5.runs_of(t[0]) for t in conf5.INTERACTIVE} == {4}
    assert [t[0] for t in conf5.INTERACTIVE] == ["I1", "I2", "I3", "I4"]


def test_the_line_answers_every_crawl_prompt_and_no_interactive_one():
    from sanchopanza.harness.crawl_hook import gathers

    for task in conf5.TASKS:
        assert gathers(conf5.prompt_of(task)) is (task[0] in conf5.CRAWL_IDS), task[0]


def test_the_sp_arms_get_v81_in_their_own_settings_and_the_plain_arms_nothing(tmp_path):
    assert conf5.SP_ENV == {
        "SANCHOPANZA_CRAWL_LINE_VERSION": "6", "SANCHOPANZA_CRAWL_NOTES": "2",
        "SANCHOPANZA_CRAWL_ECHO": "short", "SANCHOPANZA_CRAWL_LINE_AT": "prompt",
        "SANCHOPANZA_CRAWL_NOTES_AT": "front", "SANCHOPANZA_CRAWL_SHOT": "snapshot-first",
    }  # fmt: skip
    plain = json.loads(conf5.settings_for("HAIKU", tmp_path).read_text("utf-8"))
    assert "hooks" not in plain and "env" not in plain
    treated = json.loads(conf5.settings_for("SONNET-SP", tmp_path).read_text("utf-8"))
    assert treated["env"] == conf5.SP_ENV and treated["permissions"] == plain["permissions"]
    assert {e: v[0]["matcher"] for e, v in treated["hooks"].items()} == {
        "SessionStart": "", "PreToolUse": r"mcp__.*__browser_(evaluate|take_screenshot)",
        "PostToolUse": r"mcp__.*__browser_evaluate", "UserPromptSubmit": "",
    }  # fmt: skip
    assert nav.settings_for is conf5.settings_for
    assert nav.MODELS["HAIKU-SP"] == "claude-haiku-4-5"
    assert nav.MODELS["SONNET-SP"] == "claude-sonnet-5"


def test_install_points_at_this_phase_and_leaves_the_sealed_phases_alone():
    assert conf5.procedure.PREREG.name == "prereg-crawl5.md"
    assert conf5.procedure.SESSIONS.name == "nav-confirm5-sessions.jsonl"
    assert conf5.conf3.TASKS == conf5.TASKS and conf5.ARMS == ("HAIKU", "HAIKU-SP", "SONNET",
                                                               "SONNET-SP")  # fmt: skip
    for tool in ("SendMessage", "ListAgents", "ScheduleWakeup", "CronCreate", "RemoteTrigger"):
        assert tool in nav.DISALLOWED.split()
    fresh = importlib.util.spec_from_file_location("x4", ROOT / "benchmarks/browse/nav_confirm4.py")
    sealed = importlib.util.module_from_spec(fresh)
    fresh.loader.exec_module(sealed)
    assert [t[0] for t in sealed.CRAWLS] == [f"G{i}" for i in range(1, 9)]


def _result(text: str) -> str:
    block = {"type": "tool_result", "content": [{"type": "text", "text": text}]}
    return json.dumps({"message": {"content": [block]}})


DOWN = "### Page\n- Page URL: https://x.test/\n- Page Title: Application Error\n- HTTP status: 503"
UP = "### Page\n- Page URL: https://x.test/\n- Page Title: X"


def test_page_loads_are_read_from_the_tool_results_only():
    text = "\n".join([_result(DOWN), _result(UP), json.dumps({"toolUseResult": DOWN}), "junk"])
    assert conf5.page_loads(text) == (2, 1)
    assert conf5.page_loads(_result("### Page\n- Page URL: a\n- HTTP status: 404")) == (1, 0)


def _session(monkeypatch, tmp_path, text, success=False, arm="HAIKU"):
    sessions = tmp_path / "sessions.jsonl"
    monkeypatch.setattr(conf5, "SESSIONS", sessions)
    monkeypatch.setattr(conf5.conf3, "_transcript", lambda workdir: text)
    row = {"task": "I3", "run": 1, "arm": arm, "ok": True, "workdir": "x", "success": success,
           "list_usd": 0.05, "answer": "the site is down", "tools": {}}  # fmt: skip
    monkeypatch.setattr(nav, "one_session", lambda task, run, a: {**row, "arm": a})
    return sessions


def test_a_session_whose_every_load_was_5xx_runs_again_once_and_then_counts_as_wrong(
    monkeypatch, tmp_path
):
    task = conf5.INTERACTIVE[2]
    sessions = _session(monkeypatch, tmp_path, "\n".join([_result(DOWN), _result(DOWN)]))
    first = conf5.one_session(task, 1, "HAIKU")
    assert first["site_down"] and first["not_run"] and first["subtype"] == conf5.SITE_DOWN
    sessions.write_text(json.dumps(first) + "\n", encoding="utf-8")
    again = conf5.one_session(task, 1, "HAIKU")
    assert again["site_down_again"] and not again.get("not_run") and not again["success"]
    assert nav.phase.counted([first, again]) == [again]


@pytest.mark.parametrize(
    ("loads", "success", "down"),
    [
        ((DOWN, UP), False, False),
        ((DOWN,), True, False),
        ((), False, False),
        ((DOWN,), False, True),
    ],
)
def test_site_down_needs_a_wrong_answer_and_nothing_but_5xx(
    monkeypatch, tmp_path, loads, success, down
):
    _session(monkeypatch, tmp_path, "\n".join(_result(x) for x in loads), success=success)
    row = conf5.one_session(conf5.INTERACTIVE[2], 1, "SONNET")
    assert bool(row.get("site_down")) is down


@pytest.mark.parametrize(
    ("task_index", "arm", "text", "not_run"),
    [
        (0, "HAIKU-SP", "never a URL pattern you guessed", False),
        (0, "HAIKU-SP", "", True),  # a crawl with no line
        (8, "SONNET-SP", "never a URL pattern you guessed", True),  # the line on I1
        (8, "SONNET-SP", "", False),
        (8, "HAIKU", "", False),
        (0, "HAIKU", "never a URL pattern you guessed", True),  # a plain session saw it
    ],
)
def test_a_session_counts_only_if_it_got_exactly_its_arms_treatment(
    monkeypatch, tmp_path, task_index, arm, text, not_run
):
    _session(monkeypatch, tmp_path, text, success=True, arm=arm)
    row = conf5.one_session(conf5.TASKS[task_index], 1, arm)
    assert bool(row.get("not_run")) is not_run


def test_the_repeats_come_after_every_planned_session(monkeypatch, tmp_path):
    sessions = tmp_path / "s.jsonl"
    monkeypatch.setattr(conf5, "SESSIONS", sessions)
    order: list[tuple] = []
    downs: set[tuple] = set()

    def fake(task, run, arm):
        key = (task[0], run, arm)
        order.append(key)
        row = {"task": task[0], "run": run, "arm": arm, "success": True, "list_usd": 0.0}
        if key == ("H1", 1, "HAIKU") and key not in downs:
            downs.add(key)
            return {**row, "success": False, "site_down": True, "not_run": True}
        return row

    monkeypatch.setattr(conf5, "one_session", fake)
    code, rows = conf5.run_live()
    assert code == 0 and len(order) == 161
    assert order[0] == ("H1", 1, "HAIKU") and order[-1] == ("H1", 1, "HAIKU")
    assert len(nav.phase.counted(rows)) == 160


def _rows(costs, right=None):
    return [{"task": t[0], "run": run, "arm": arm, "list_usd": usd, "subtype": "success",
             "success": (right or {}).get(arm, True), "tools": {}}
            for t in conf5.TASKS for run in range(1, conf5.runs_of(t[0]) + 1)
            for arm, usd in costs.items()]  # fmt: skip


def test_the_verdicts_are_confirmation_4s_code_over_these_tasks():
    cheap = {"HAIKU": 0.2, "HAIKU-SP": 0.1, "SONNET": 0.4, "SONNET-SP": 0.2}
    out = conf5.verdicts(_rows(cheap))
    assert out["complete"] and out["beats_on_both_models"]
    assert out["HAIKU"]["no_harm"]["HAIKU-SP"] == "16/16"
    assert out["HAIKU"]["answers"]["HAIKU-SP"] == "24/24"
    assert out["SONNET"]["price"]["tasks_cheaper"] == "8/8"
    rows = _rows(cheap)
    lost = [{**r, "success": False} if (r["arm"], r["task"], r["run"]) == ("HAIKU-SP", "H1", 1)
            else r for r in rows]  # fmt: skip
    assert not conf5.verdicts(lost)["HAIKU"]["answers"]["holds"]
    one_less = [{**r, "success": False} if (r["arm"], r["task"], r["run"]) == ("SONNET-SP", "I3", 1)
                else r for r in rows]  # fmt: skip
    assert conf5.verdicts(one_less)["SONNET"]["no_harm"]["holds"]  # the margin of one
    dear = {**cheap, "HAIKU-SP": 0.16}  # 0.8 of the plain arm: over 0.75
    assert not conf5.verdicts(_rows(dear))["HAIKU"]["price"]["holds"]
    assert not conf5.verdicts(rows[:-1])["complete"]


def test_live_refuses_to_spend_until_the_prereg_is_sealed_as_it_stands(tmp_path, monkeypatch):
    prereg = tmp_path / "prereg-crawl5.md"
    prereg.write_text("registered text", encoding="utf-8")
    monkeypatch.setattr(conf5.procedure, "PREREG", prereg)
    with pytest.raises(SystemExit):
        conf5.procedure.require_registration()
    prereg.with_suffix(".sha256").write_text(nav.base.digest(prereg) + "\n", encoding="utf-8")
    conf5.procedure.require_registration()


def test_a_sanchopanza_hook_in_the_user_settings_fails_the_preflight(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "hooks": {"Stop": [{"hooks": [{"command": "node x.js"}]}]},
                "permissions": {"allow": ["sanchopanza"]},
            }
        ),
        encoding="utf-8",
    )
    assert conf5.user_hook_problems(path) == []
    path.write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [
        {"command": "python -m sanchopanza crawl-hook"}]}]}}), encoding="utf-8")  # fmt: skip
    assert conf5.user_hook_problems(path)
    assert conf5.user_hook_problems(tmp_path / "missing.json") == []


def test_the_prereg_seals_what_this_code_runs():
    import hashlib

    from sanchopanza.harness import crawl_hook as crawl

    text = conf5.PREREG.read_text(encoding="utf-8")
    line = hashlib.sha256(crawl.STRATEGY_LINE_V6.encode()).hexdigest()
    wrapper = hashlib.sha256(crawl.wrap("() => 1", 120, notes=2).encode()).hexdigest()
    texts = hashlib.sha256(
        "\n".join((crawl.ECHO_LINE, crawl.NOTES_HEAD, crawl.SHOT_REASON)).encode()
    ).hexdigest()
    assert line in text and wrapper in text and texts in text
    for tid, _url, _question, required in conf5.CRAWLS:
        assert re.search(rf"\| {tid} \|.*\| {required[0]} \|", text), tid
    for name, value in conf5.SP_ENV.items():
        assert f"{name}={value}" in text, name
    assert f"{conf5.CEILING_USD:.0f} USD" in text
