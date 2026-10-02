"""The strategy confirmation: its tasks, its registration gate and its pre-specified verdicts.
No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_nav_confirm", ROOT / "benchmarks/browse/nav_confirm.py"
)
conf = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_confirm"] = conf
spec.loader.exec_module(conf)


def test_the_tasks_are_new_ascii_and_graded_from_their_answer_line():
    ids = [t[0] for t in conf.TASKS]
    assert len(ids) == len(set(ids)) == 10
    developed = {t[0] for t in conf.nav.STRATEGY_TASKS + conf.nav.HARD_TASKS}
    assert not developed & set(ids), "no task the line was developed on"
    for tid, url, question, required in conf.TASKS:
        assert url.startswith("https://") and question.isascii() and required, tid
    crawl = [t for t in conf.TASKS if t[0].startswith("C")]
    assert len(crawl) == 8
    for tid, _, _, required in crawl:
        assert conf.nav.grade(f"Walked them all.\nANSWER: {required[0]}", required, tid)
        assert not conf.nav.grade(f"ANSWER: {required[0]}0", required, tid)


def test_the_arms_differ_by_the_line_alone():
    assert conf.ARMS == ("HAIKU", "HAIKU-HINT2")
    assert {conf.nav.MODELS[a] for a in conf.ARMS} == {"claude-haiku-4-5"}


def _row(task, run, arm, ok=True, usd=0.1, subtype="success", turns=10, navs=1):
    return {"task": task, "run": run, "arm": arm, "success": ok, "list_usd": usd,
            "subtype": subtype, "ok": subtype == "success", "turns": turns,
            "tools": {"mcp__playwright__browser_navigate": navs}}  # fmt: skip


def _rows(hint_usd: float, base_usd: float, hint_ok=True, base_ok=True) -> list[dict]:
    rows = []
    for tid in [t[0] for t in conf.TASKS]:
        for run in (1, 2, 3):
            rows.append(_row(tid, run, "HAIKU", base_ok, base_usd))
            rows.append(_row(tid, run, "HAIKU-HINT2", hint_ok, hint_usd))
    return rows


def test_a_cheaper_and_as_good_line_holds_every_hypothesis():
    verdict = conf.verdicts(_rows(hint_usd=0.05, base_usd=0.2))
    assert verdict["H1_cost"]["holds"] and verdict["H2_accuracy"]["holds"]
    assert verdict["H3_no_harm"]["holds"]


def test_the_same_cost_fails_the_cost_hypothesis():
    assert not conf.verdicts(_rows(0.2, 0.2))["H1_cost"]["holds"]


def test_a_cheaper_line_that_answers_wrong_fails_accuracy():
    verdict = conf.verdicts(_rows(0.05, 0.2, hint_ok=False))
    assert verdict["H1_cost"]["holds"] and not verdict["H2_accuracy"]["holds"]


def test_a_session_killed_by_the_runner_costs_the_session_cap_not_zero():
    """H1 of the development round hung for 30 minutes and recorded 0 USD: that is not free."""
    killed = _row("C1", 1, "HAIKU-HINT2", ok=False, usd=0.0, subtype="runner: TimeoutExpired")
    assert conf.charged(killed) == conf.nav.SESSION_MAX_USD
    assert conf.charged(_row("C1", 1, "HAIKU", usd=0.07)) == 0.07


def test_a_missing_session_leaves_the_phase_incomplete_rather_than_judged():
    rows = [r for r in _rows(0.05, 0.2) if not (r["task"] == "C3" and r["arm"] == "HAIKU")]
    assert conf.verdicts(rows)["complete"] is False


def test_nothing_is_spent_unless_the_registration_matches(tmp_path, monkeypatch):
    prereg = tmp_path / "prereg.md"
    prereg.write_text("plan", encoding="utf-8")
    monkeypatch.setattr(conf, "PREREG", prereg)
    with pytest.raises(SystemExit, match="not registered"):
        conf.require_registration()
    prereg.with_suffix(".sha256").write_text(conf.nav.base.digest(prereg) + "\n")
    conf.require_registration()
    prereg.write_text("plan, edited after sealing", encoding="utf-8")
    with pytest.raises(SystemExit, match="not registered"):
        conf.require_registration()
