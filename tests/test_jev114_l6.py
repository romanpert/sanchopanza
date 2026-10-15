"""Lot L6 (benchmarks/jev114/l6.py and l6_analysis.py), with no network: the cut, the Choice
reading, the substitution arithmetic, the threshold-free QASPER reading and the memory gate."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from sanchopanza.contract import Answer, Decision

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("jev114_l6", ROOT / "benchmarks/jev114/l6.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["jev114_l6"] = module
    spec.loader.exec_module(module)
    return module


l6 = _load()
import l6_analysis as an  # noqa: E402  (on the path once l6 is loaded)


def test_middle_cut_keeps_head_and_tail():
    text = "a" * 50 + "b" * 50
    assert l6.middle_cut(text, 200) == text
    cut = l6.middle_cut(text, 20)
    assert cut.startswith("a" * 10) and cut.endswith("b" * 10) and "[...]" in cut


def test_the_registered_windows_and_caps():
    assert l6.CUT_CHARS == {"S": 100_000, "L": 900_000}
    assert l6.BATCH_CAP_USD == 1.50 and l6.LEDGER_CAP_USD == 4.50
    assert l6.CONCURRENCY <= 4
    assert l6.CELLS == ("j13r-S", "j14-S", "j13r-L", "j14-L")
    assert l6.B3_TAU == 0.9


def test_top_of_reads_the_chosen_letter_and_its_probability():
    probs = {"A": 0.1, "B": 0.7, "C": 0.1, "D": 0.1}
    answer = Answer(kind="choice", confidence=0.6, choice="B", probabilities=probs)
    letter, p, dist = l6.top_of(Decision("x", {"answer": answer}, "jev", "m"))
    assert (letter, p) == ("B", 0.7) and dist == probs
    assert l6.top_of(Decision("x", {}, "jev", "m")) == (None, None, {})


def test_model_order_alternates():
    assert l6.model_order(0) == ("j13r", "j14")
    assert l6.model_order(1) == ("j14", "j13r")


def _b3_row(i, gold, jev, p, sonnet_ok, usd=0.1):
    cell = {"letter": jev, "p": p, "probs": {}, "usd": 0.001, "tokens": 10}
    return {
        "id": f"t{i}",
        "gold": gold,
        "j14-L": cell,
        "sonnet": {"letter": gold if sonnet_ok else "Z", "ok": sonnet_ok, "usd": usd},
    }


def test_substitution_uses_jev_only_where_it_is_sure():
    rows = [
        _b3_row(0, "A", "A", 0.95, False),  # covered, Jev right, Sonnet wrong
        _b3_row(1, "B", "C", 0.95, True),  # covered, Jev wrong, Sonnet right
        _b3_row(2, "C", "D", 0.40, True),  # not covered: Sonnet's answer stands
        _b3_row(3, "D", None, None, False),  # Jev failed: not covered
    ]
    sub = an.substitution(rows, "j14-L", 0.9)
    assert sub["covered"] == 2 and sub["coverage"] == 0.5
    assert sub["precision"] == 0.5 and sub["sonnet_on_covered"] == 0.5
    assert sub["hybrid_vs_sonnet"]["new"] == 0.5 and sub["hybrid_vs_sonnet"]["old"] == 0.5
    assert sub["sonnet_usd_saved"] == pytest.approx(0.2)
    assert sub["jev_usd"] == pytest.approx(0.004)  # every recorded cost of the cell counts
    assert an.substitution_verdict(sub, 0.9, 0.2, 0.9) == "no sustituye"


def test_budget_mask_takes_the_most_probable_paragraphs_within_the_share():
    row = {
        "sizes": [10, 10, 10, 10],
        "gold": [False, True, False, False],
        "x": {"keep": [True] * 4, "p": [0.2, 0.9, None, 0.5]},
    }
    assert an.budget_mask(row, "x", 0.5) == [False, True, False, True]
    assert an.budget_mask(row, "x", 0.25) == [False, True, False, False]
    assert an.budget_mask(row, "x", 0.1) == [False] * 4


def test_a6_arm_scores_at_the_cut_and_at_the_budget():
    row = {
        "id": "p",
        "sizes": [10, 30, 60],
        "gold": [True, False, False],
        "j14-L": {"keep": [True, True, False], "p": [0.9, 0.5, 0.1]},
    }
    out = an.a6_arm([row], "j14-L", 0.25)
    assert out["all_evidence"] == 1.0 and out["kept_share"] == 0.4
    assert out["budget_all_evidence"] == 1.0 and out["budget_kept_share"] == 0.1
    assert out["P28"] is False


def test_a7_gate_is_empty_when_recall_says_no_and_none_when_it_failed():
    row = {
        "gold": [1],
        "bm25@3": [0, 1, 2],
        "j14-look": False,
        "j14-L": [1],
        "j13r-look": True,
        "j13r-L": None,
    }
    assert an.a7_chosen(row, "j14-L") == set()
    assert an.a7_chosen(row, "j13r-L") is None
    assert an.a7_chosen(row, "bm25@3") == {0, 1, 2}


def test_a7_recall_pools_gold_sessions():
    rows = [
        {"gold": [0, 1], "sizes": [5, 5, 5], "bm25@3": [0], "j14-look": True, "j14-L": [0, 1]},
        {"gold": [2], "sizes": [5, 5, 5], "bm25@3": [2], "j14-look": True, "j14-L": []},
    ]
    assert an.a7_cell(rows, "j14-L")["recall"] == pytest.approx(2 / 3, abs=1e-4)
    assert an.a7_cell(rows, "bm25@3")["recall"] == pytest.approx(2 / 3, abs=1e-4)


def test_paired_stat_reports_no_difference_on_equal_arms():
    out = an.paired_stat(lambda i: len(i), lambda i: len(i), 5)
    assert out["diff"] == 0 and out["p"] == 1.0


def test_arm_refusal_is_counted_not_raised():
    class Refuses:
        name = "jev"

        async def decide(self, point, state, questions):
            raise RuntimeError("HTTP 400 max_tokens_exceeded")

    gate = asyncio.Semaphore(1)
    arm = l6.l4.Arm("j14-L", Path("does-not-exist.jsonl"), "jev-1.14.0", Refuses(), gate)
    got = asyncio.run(arm.decide("p", {"x": 1}, {}))
    assert got.failed and arm.failures == 1


class _Fake:
    """A live decider: fails on the states named in `fail`, else a fixed Choice or Truths."""

    name = "jev"

    def __init__(self, model, fail=()):
        self.model, self.fail, self.seen = model, set(fail), []

    async def decide(self, point, state, questions):
        self.seen.append(state)
        await asyncio.sleep(0)
        key = state.get("document", state.get("purpose", ""))
        if any(f in key for f in self.fail):
            raise RuntimeError("HTTP 400")
        answers = {}
        for k, q in questions.items():
            if q.kind == "choice":
                answers[k] = Answer(
                    kind="choice", confidence=0.9, choice="A", probabilities={"A": 0.9, "B": 0.1}
                )
            else:
                answers[k] = Answer(kind="truth", confidence=0.8, truth=0.9)
        return Decision(point, answers, "jev", self.model, cost_usd=0.001)


def test_a_failure_marks_only_its_own_item_under_gather(tmp_path):
    gate = asyncio.Semaphore(4)
    fake = _Fake("jev-1.14.0", fail={"bad question"})
    arm = l6.l4.Arm("j14-L", tmp_path / "a.jsonl", "jev-1.14.0", fake, gate)
    arms = {c: arm for c in l6.CELLS}
    rows = [
        {
            "id": str(i),
            "question": "bad question" if i == 0 else f"q{i}",
            "gold": [True, False],
            "pages": [("t", "one"), ("t", "two")],
        }
        for i in range(6)
    ]

    async def go():
        return await asyncio.gather(*(l6.a6_one(i, r, arms, None) for i, r in enumerate(rows)))

    out = asyncio.run(go())
    assert out[0]["j14-L"] is None
    assert all(o["j14-L"] is not None for o in out[1:])


def test_b3_shrinks_the_window_for_both_models(tmp_path):
    class Task:
        task_id, gold, length, difficulty = "t", "A", "short", "easy"
        question, choices = "q?", ("a", "b", "c", "d")

    doc = tmp_path / "d.txt"
    doc.write_text("x" * 400 + "MIDDLE" + "y" * 400, encoding="utf-8")
    Task.doc_path = str(doc)
    saved = dict(l6.CUT_CHARS)
    l6.CUT_CHARS.update({"S": 100, "L": 2_000})
    try:
        gate = asyncio.Semaphore(4)
        fakes = {m: _Fake(l6.MODELS[m], fail={"MIDDLE"}) for m in l6.MODELS}
        arms = {
            c: l6.l4.Arm(
                c, tmp_path / f"{c}.jsonl", l6.MODELS[c.split("-")[0]], fakes[c.split("-")[0]], gate
            )
            for c in l6.CELLS
        }
        row = asyncio.run(l6.b3_one(0, Task, arms))
    finally:
        l6.CUT_CHARS.clear()
        l6.CUT_CHARS.update(saved)
    # L shows the whole 806 characters at 1.0 and 0.8 (both refused), the 1,280 cut too: failed
    assert row["j14-L"]["letter"] is None and row["j14-L"]["tries"] == 3
    assert row["j13r-S"]["letter"] == "A" and row["j13r-S"]["tries"] == 1
    assert row["j14-S"]["usd"] == pytest.approx(0.001)


def test_top_of_without_a_probability_for_the_pick_is_unanswered():
    answer = Answer(kind="choice", confidence=0.6, choice="B", probabilities={"A": 0.5})
    assert l6.top_of(Decision("x", {"answer": answer}, "jev", "m"))[0] is None


def test_a7_failure_gap_counts_failed_cells():
    good = {"gold": [0], "sizes": [5], "bm25@3": [0], "excerpt_seen": 1, "excerpt_total": 1}
    rows = [
        good | {f"{m}-look": True for m in ("j13r", "j14")} | {c: [0] for c in l6.CELLS}
        for _ in range(3)
    ]
    rows.append(rows[0] | {"j14-L": None})
    out = an.analyse_a7(rows, min_questions=20)
    assert out["complete"] == 3 and out["failures"]["j14-L"] == 1
    assert out["recall_failure_as_empty"]["j14-L"] == 0.75
    assert out["family"]["recall_model_L"]["verdict"] == "no concluyente (n bajo)"
    assert out["against_bm25@3"]["j14-L"]["beats"] is False
