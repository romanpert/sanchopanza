"""The third confirmation: Claude Code with sanchopanza's crawl installed against Claude Code
alone, Haiku and Sonnet, on new tasks. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_nav_confirm3", ROOT / "benchmarks/browse/nav_confirm3.py"
)
conf3 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_confirm3"] = conf3
spec.loader.exec_module(conf3)
nav = conf3.nav

SPENT = {
    *[f"C{i}" for i in range(1, 9)], *[f"D{i}" for i in range(1, 9)],
    *[f"S{i}" for i in range(1, 6)], *[f"H{i}" for i in range(1, 6)],
    *[f"A{i}" for i in range(1, 7)], "B1", "B2",
}  # fmt: skip


def test_its_tasks_are_new_and_each_crawl_is_graded_on_its_answer_line():
    ids = [t[0] for t in conf3.TASKS]
    assert len(ids) == len(set(ids)) == 10 and len(conf3.CRAWLS) == 8
    assert not SPENT & set(ids)
    spent_urls = {t[1] for t in nav.STRATEGY_TASKS + nav.HARD_TASKS + nav.TASKS}
    for tid, url, question, required in conf3.TASKS:
        assert url.startswith("https://") and question.isascii() and required, tid
    for tid, url, _, _ in conf3.CRAWLS:  # a crawl on a page a line was tuned on is not new
        assert url not in spent_urls, tid
    for tid, _, _, required in conf3.CRAWLS:
        assert nav.grade(f"Read every page.\nANSWER: {required[0]}", required, tid)
        assert not nav.grade(f"I found {required[0]} of them.", required, tid), "no ANSWER line"
        assert not nav.grade(f"{required[0]} pages.\nANSWER: 1{required[0]}", required, tid)


def test_the_treated_arms_get_exactly_what_install_crawl_writes(tmp_path):
    from sanchopanza.harness.install import CRAWL_HOOKS

    plain = json.loads(conf3.settings_for("HAIKU", tmp_path).read_text("utf-8"))
    assert "hooks" not in plain
    treated = json.loads(conf3.settings_for("SONNET-SP", tmp_path).read_text("utf-8"))
    assert treated["permissions"] == plain["permissions"]
    assert {e: v[0]["matcher"] for e, v in treated["hooks"].items()} == CRAWL_HOOKS
    commands = {h["command"] for v in treated["hooks"].values() for e in v for h in e["hooks"]}
    assert commands == {conf3.crawl_command()} and commands.pop().endswith(" crawl-hook")


def test_install_points_the_runner_at_this_phase_and_leaves_the_sealed_ones():
    conf3.install()
    assert nav.MODELS["HAIKU-SP"] == "claude-haiku-4-5"
    assert nav.MODELS["SONNET-SP"] == "claude-sonnet-5"
    assert conf3.procedure.PREREG.name == "prereg-crawl3.md"
    assert conf3.procedure.SESSIONS.name == "nav-confirm3-sessions.jsonl"
    first = importlib.util.spec_from_file_location(
        "x_first", ROOT / "benchmarks/browse/nav_confirm.py"
    )
    sealed = importlib.util.module_from_spec(first)
    first.loader.exec_module(sealed)
    assert sealed.PREREG.name == "prereg-strategy.md" and sealed.ARMS == ("HAIKU", "HAIKU-HINT2")


def _rows(costs: dict[str, float], right: dict[str, bool] | None = None) -> list[dict]:
    rows = []
    for tid in [t[0] for t in conf3.TASKS]:
        for run in (1, 2, 3):
            for arm, usd in costs.items():
                rows.append({"task": tid, "run": run, "arm": arm, "list_usd": usd,
                             "success": (right or {}).get(arm, True), "subtype": "success",
                             "tools": {}})  # fmt: skip
    return rows


def test_sanchopanza_beats_the_harness_only_on_price_and_answers_at_once():
    cheap = {"HAIKU": 0.2, "HAIKU-SP": 0.1, "SONNET": 0.4, "SONNET-SP": 0.2}
    verdict = conf3.verdicts(_rows(cheap))
    assert verdict["complete"] and verdict["beats_on_both_models"]
    lost = conf3.verdicts(_rows(cheap, {"SONNET-SP": False}))
    assert lost["HAIKU"]["beats_the_harness"] and not lost["SONNET"]["beats_the_harness"]
    assert not lost["SONNET"]["answers"]["holds"] and lost["SONNET"]["price"]["holds"]
    dear = conf3.verdicts(_rows({**cheap, "HAIKU-SP": 0.18}))
    assert not dear["HAIKU"]["price"]["holds"] and not dear["beats_on_both_models"]


def test_one_answer_lost_on_the_crawls_is_enough_to_fail_the_answers_bar():
    rows = _rows({"HAIKU": 0.2, "HAIKU-SP": 0.1, "SONNET": 0.4, "SONNET-SP": 0.2})
    miss = next(r for r in rows if r["arm"] == "HAIKU-SP" and r["task"] == "E6")
    rows = [{**r, "success": False} if r is miss else r for r in rows]
    assert not conf3.verdicts(rows)["HAIKU"]["answers"]["holds"]


def test_a_hang_is_charged_the_session_cap():
    rows = _rows({"HAIKU": 0.2, "HAIKU-SP": 0.1, "SONNET": 0.4, "SONNET-SP": 0.2})
    hang = next(r for r in rows if r["arm"] == "HAIKU-SP" and r["task"] == "E1")
    rows = [{**r, "subtype": "runner: TimeoutExpired", "list_usd": 0.0} if r is hang else r
            for r in rows]  # fmt: skip
    described = conf3.described(rows)
    assert described["arms"]["HAIKU-SP"]["hangs_killed_by_the_runner"] == 1
    assert described["arms"]["HAIKU-SP"]["list_usd"] > 1.0
