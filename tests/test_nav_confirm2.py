"""The second confirmation (line v5): new tasks, the first confirmation's verdicts and files
left untouched. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_nav_confirm2", ROOT / "benchmarks/browse/nav_confirm2.py"
)
conf2 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_confirm2"] = conf2
spec.loader.exec_module(conf2)
run = conf2.confirmation


def test_its_tasks_are_new_to_every_line_and_to_the_first_confirmation():
    ids = [t[0] for t in run.TASKS]
    assert len(ids) == len(set(ids)) == 10 and len(run.CRAWLS) == 8
    seen = {t[0] for t in run.nav.STRATEGY_TASKS + run.nav.HARD_TASKS}
    first = {t[0] for t in conf2.first.CRAWLS}
    assert not (seen | first) & {t[0] for t in run.CRAWLS}
    for tid, url, question, required in run.TASKS:
        assert url.startswith("https://") and question.isascii() and required, tid
    for tid, _, _, required in run.CRAWLS:
        assert run.nav.grade(f"ANSWER: {required[0]}", required, tid)


def test_it_measures_line_v5_against_the_unaided_model():
    assert run.ARMS == ("HAIKU", "HAIKU-HINT5")
    assert run.PREREG.name == "prereg-strategy2.md"
    assert run.SESSIONS.name == "nav-confirm2-sessions.jsonl"


def test_the_first_confirmation_is_left_as_it_was_sealed():
    assert conf2.first.ARMS == ("HAIKU", "HAIKU-HINT2")
    assert conf2.first.PREREG.name == "prereg-strategy.md"
    assert conf2.first.SESSIONS.name == "nav-confirm-sessions.jsonl"
    assert conf2.first is not run


def test_its_verdicts_are_the_first_confirmations_function_over_its_own_arms():
    rows = []
    for tid in [t[0] for t in run.TASKS]:
        for r in (1, 2, 3):
            for arm, usd in (("HAIKU", 0.2), ("HAIKU-HINT5", 0.05)):
                rows.append({"task": tid, "run": r, "arm": arm, "success": True,
                             "list_usd": usd, "subtype": "success",
                             "tools": {}})  # fmt: skip
    verdict = run.verdicts(rows)
    assert verdict["complete"] and verdict["H1_cost"]["holds"]
    assert verdict["H2_accuracy"]["holds"] and verdict["H3_no_harm"]["holds"]
