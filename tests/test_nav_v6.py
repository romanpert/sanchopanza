"""Line v6's development runner: the crawl hook with v5 against v6, Haiku alone for reference,
on eight new crawls. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("browse_nav_v6", ROOT / "benchmarks/browse/nav_v6.py")
v6 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_v6"] = v6
spec.loader.exec_module(v6)
nav = v6.nav
v6.install()


def _used_urls() -> set[str]:
    """Every URL any other benchmark file names: a v6 task must be on none of them."""
    found: set[str] = set()
    for path in (ROOT / "benchmarks").rglob("*.py"):
        if path.name in {"nav_v6.py", "truth_v6.py", "repeat_fingerprint.py"}:  # this phase's own
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found |= {u.rstrip(".,)'\"") for u in re.findall(r"https?://[^\s\"'<>)]+", text)}
    return found


def test_the_tasks_are_new_free_phrased_and_graded_on_their_answer_line():
    ids = [t[0] for t in v6.TASKS]
    assert ids == [f"F{i}" for i in range(1, 9)]
    used = _used_urls()
    for tid, url, question, required in v6.TASKS:
        assert url not in used and not any(u.startswith(url) for u in used), tid
        assert question.isascii() and "page" not in question.lower().replace("this page's", ""), tid
        assert nav.grade(f"Read it all.\nANSWER: {required[0]}", required, tid)
        assert not nav.grade(f"I found {required[0]} of them.", required, tid), "no ANSWER line"
        assert not nav.grade(f"{required[0]} pages.\nANSWER: 1{required[0]}", required, tid)


def test_a_trap_answer_is_never_the_truth():
    truth = {t[0]: t[3][0] for t in v6.TASKS}
    for tid, traps in v6.TRAPS.items():
        assert truth[tid] not in traps, tid


def test_the_treated_arms_get_what_install_crawl_writes_and_their_version(tmp_path):
    from sanchopanza.harness.install import CRAWL_HOOKS

    plain = json.loads(v6.settings_for("HAIKU", tmp_path).read_text("utf-8"))
    assert "hooks" not in plain and "env" not in plain
    for arm, version in (("HAIKU-V5", "5"), ("HAIKU-V6", "6")):
        treated = json.loads(v6.settings_for(arm, tmp_path).read_text("utf-8"))
        assert treated["permissions"] == plain["permissions"]
        assert {e: v[0]["matcher"] for e, v in treated["hooks"].items()} == CRAWL_HOOKS
        assert treated["env"] == {"SANCHOPANZA_CRAWL_LINE_VERSION": version}


def test_each_mark_is_in_its_own_line_only():
    from sanchopanza.harness.crawl_hook import LINES

    for version, mark in v6.MARKS.items():
        assert mark in LINES[version]
        assert all(mark not in line for v, line in LINES.items() if v != version)


def test_the_bench_sessions_cannot_reach_other_sessions_or_schedule():
    for tool in ("SendMessage", "ListAgents", "ScheduleWakeup", "CronCreate", "RemoteTrigger"):
        assert tool in nav.DISALLOWED.split()
    assert nav.SESSION_MAX_USD == 1.00 and v6.CEILING_USD <= 12.00


def test_the_two_lines_run_before_the_reference():
    plan = v6.plan(v6.TASKS, [1, 2, 3])
    arms = [p[3] for p in plan]
    assert len(plan) == 72 and arms.index("HAIKU") == 48
    assert set(arms[:48]) == {"HAIKU-V5", "HAIKU-V6"}


def _row(arm: str, ok: bool = True, **extra) -> dict:
    return {"task": "F4", "run": 1, "arm": arm, "ok": ok, "workdir": "x", "success": True,
            "list_usd": 0.1, **extra}  # fmt: skip


@pytest.mark.parametrize(
    ("arm", "text", "not_run"),
    [
        ("HAIKU-V6", v6.MARKS["6"], False),
        ("HAIKU-V6", v6.MARKS["5"], True),
        ("HAIKU-V6", v6.MARKS["5"] + v6.MARKS["6"], True),
        ("HAIKU-V5", v6.MARKS["5"], False),
        ("HAIKU-V5", "", True),
        ("HAIKU", "", False),
    ],
)
def test_a_treated_session_counts_only_if_its_own_line_reached_it(monkeypatch, arm, text, not_run):
    monkeypatch.setattr(nav, "one_session", lambda task, run, a: _row(a))
    monkeypatch.setattr(v6.confirm3, "_transcript", lambda workdir: text)
    row = v6.one_session(v6.TASKS[3], 1, arm)
    assert bool(row.get("not_run")) is not_run


def test_analyse_counts_right_cost_and_traps_per_arm_and_task():
    rows = [
        _row("HAIKU-V6", answer="ANSWER: 5"),
        _row("HAIKU-V5", success=False, answer="ANSWER: 4", list_usd=0.2),
        _row("HAIKU", subtype="runner: TimeoutExpired", list_usd=0.0, success=False),
    ]
    out = v6.analyse(rows)
    assert out["arms"]["HAIKU-V6"]["right"] == "1/1"
    assert out["arms"]["HAIKU-V5"]["traps_fallen"] == 1
    assert out["arms"]["HAIKU"]["mean_usd"] == 1.0, "a killed session is charged the cap"
    assert out["tasks"]["F4"]["HAIKU-V5"]["answers"] == ["4"]
