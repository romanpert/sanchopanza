"""The fourth confirmation: the crawl hook as v7 left it against Claude Code alone, Haiku and
Sonnet, on new crawls. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_nav_confirm4", ROOT / "benchmarks/browse/nav_confirm4.py"
)
conf4 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_confirm4"] = conf4
spec.loader.exec_module(conf4)
conf4.install()
nav = conf4.nav
OWN = {"nav_confirm4.py", "truth_confirm4.py"}


def _used_urls() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "benchmarks").rglob("*.py"):
        if path.name not in OWN:
            text = path.read_text(encoding="utf-8", errors="replace")
            found |= {u.rstrip(".,)'\"") for u in re.findall(r"https?://[^\s\"'<>)]+", text)}
    return found


def test_the_crawls_are_new_and_graded_on_their_answer_line():
    assert [t[0] for t in conf4.CRAWLS] == [f"G{i}" for i in range(1, 9)]
    assert [t[0] for t in conf4.INTERACTIVE] == ["I1", "I2"]
    used = _used_urls()
    for tid, url, question, required in conf4.CRAWLS:
        host = url.split("/")[2]
        assert url not in used and not any(u.startswith(url) for u in used), tid
        assert question.isascii() and required, tid
        if host not in {"books.toscrape.com"}:  # a sandbox used before, on categories never used
            assert not any(u.split("/")[2:3] == [host] for u in used if "//" in u), tid
        first = required[0][0] if isinstance(required[0], list) else required[0]
        assert nav.grade(f"Read it all.\nANSWER: {first}", required, tid)
        assert not nav.grade(f"I found {first}.", required, tid), "no ANSWER line"
        assert not nav.grade(f"ANSWER: 1{first}", required, tid)
    assert nav.grade("ANSWER: 78", conf4.CRAWLS[2][3], "G3")


def test_the_sp_arms_get_install_crawl_and_v7s_switches_and_the_plain_arms_nothing(tmp_path):
    from sanchopanza.harness.install import CRAWL_HOOKS

    plain = json.loads(conf4.settings_for("SONNET", tmp_path).read_text("utf-8"))
    assert "hooks" not in plain and "env" not in plain
    treated = json.loads(conf4.settings_for("HAIKU-SP", tmp_path).read_text("utf-8"))
    assert {e: v[0]["matcher"] for e, v in treated["hooks"].items()} == CRAWL_HOOKS
    assert treated["env"] == {"SANCHOPANZA_CRAWL_LINE_VERSION": "6", "SANCHOPANZA_CRAWL_NOTES": "1"}
    assert treated["permissions"] == plain["permissions"]


def test_install_points_at_this_phase_and_leaves_confirmation_3_sealed():
    assert conf4.procedure.PREREG.name == "prereg-crawl4.md"
    assert conf4.procedure.SESSIONS.name == "nav-confirm4-sessions.jsonl"
    assert conf4.conf3.TASKS == conf4.TASKS and conf4.ARMS == ("HAIKU", "HAIKU-SP", "SONNET",
                                                               "SONNET-SP")  # fmt: skip
    for tool in ("SendMessage", "ListAgents", "ScheduleWakeup", "CronCreate", "RemoteTrigger"):
        assert tool in nav.DISALLOWED.split()
    fresh = importlib.util.spec_from_file_location("x3", ROOT / "benchmarks/browse/nav_confirm3.py")
    sealed = importlib.util.module_from_spec(fresh)
    fresh.loader.exec_module(sealed)
    assert [t[0] for t in sealed.CRAWLS] == [f"E{i}" for i in range(1, 9)]


def _row(arm, evaluates=2):
    return {"task": "G1", "run": 1, "arm": arm, "ok": True, "workdir": "x", "success": True,
            "list_usd": 0.1, "tools": {"mcp__playwright__browser_evaluate": evaluates}}  # fmt: skip


@pytest.mark.parametrize(
    ("arm", "text", "not_run"),
    [
        ("HAIKU-SP", "never a URL pattern you guessed /* sanchopanza notes */", False),
        ("HAIKU-SP", "never a URL pattern you guessed", True),
        ("SONNET-SP", "", True),
        ("SONNET", "", False),
        ("HAIKU", "/* sanchopanza notes */", True),
    ],
)
def test_a_session_counts_only_if_it_got_exactly_its_arms_treatment(
    monkeypatch, arm, text, not_run
):
    monkeypatch.setattr(nav, "one_session", lambda task, run, a: _row(a))
    monkeypatch.setattr(conf4.conf3, "_transcript", lambda workdir: text)
    assert bool(conf4.one_session(conf4.TASKS[0], 1, arm).get("not_run")) is not_run


def _rows(costs, right=None):
    return [{"task": t[0], "run": run, "arm": arm, "list_usd": usd, "subtype": "success",
             "success": (right or {}).get(arm, True), "tools": {}}
            for t in conf4.TASKS for run in (1, 2, 3) for arm, usd in costs.items()]  # fmt: skip


def test_the_verdicts_are_confirmation_3s_over_these_tasks():
    cheap = {"HAIKU": 0.2, "HAIKU-SP": 0.1, "SONNET": 0.4, "SONNET-SP": 0.2}
    out = conf4.conf3.verdicts(_rows(cheap))
    assert out["complete"] and out["beats_on_both_models"]
    lost = _rows(cheap)
    lost[1] = {**lost[1], "success": False}  # one HAIKU-SP crawl answer fewer
    assert lost[1]["arm"] == "HAIKU-SP" and lost[1]["task"] == "G1"
    assert not conf4.conf3.verdicts(lost)["HAIKU"]["answers"]["holds"]


def test_live_refuses_to_spend_until_the_prereg_is_sealed_as_it_stands(tmp_path, monkeypatch):
    prereg = tmp_path / "prereg-crawl4.md"
    prereg.write_text("registered text", encoding="utf-8")
    monkeypatch.setattr(conf4.procedure, "PREREG", prereg)
    with pytest.raises(SystemExit):
        conf4.procedure.require_registration()
    prereg.with_suffix(".sha256").write_text(nav.base.digest(prereg) + "\n", encoding="utf-8")
    conf4.procedure.require_registration()


def test_the_prereg_seals_the_line_and_the_wrapper_this_code_runs():
    import hashlib

    from sanchopanza.harness import crawl_hook as crawl

    text = conf4.PREREG.read_text(encoding="utf-8")
    line = hashlib.sha256(crawl.STRATEGY_LINE_V6.encode()).hexdigest()
    wrapper = hashlib.sha256(crawl.wrap("() => 1", 120, notes=True).encode()).hexdigest()
    assert line in text and wrapper in text
