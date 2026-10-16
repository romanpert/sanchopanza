"""C5's runner (benchmarks/passage_fit/free_confirm.py): the questions it builds, that the FREE
run costs no call the unbudgeted run did not make, the arms' cuts, the rule, and that a paid
run refuses before the key. No network, no QASPER file, no paid call."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import truth
from sanchopanza.contract import Decision
from sanchopanza.text import split_sentences

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "free_confirm", ROOT / "benchmarks/passage_fit/free_confirm.py"
)
fc = importlib.util.module_from_spec(spec)
sys.modules["free_confirm"] = fc
spec.loader.exec_module(fc)


def _paper() -> dict[str, Any]:
    paras = ["Intro sentence one. Intro two.", "We use a BiLSTM encoder. It has 2 layers.",
             "Results are good. Accuracy is 91 percent."]  # fmt: skip
    answer = {"unanswerable": False, "evidence": [paras[1]],
              "highlighted_evidence": ["We use a BiLSTM encoder."]}  # fmt: skip
    none = {"unanswerable": True, "evidence": []}
    return {
        "id": "p1",
        "full_text": {"section_name": ["Intro", "Method", "Results"],
                      "paragraphs": [[paras[0]], [paras[1]], [paras[2]]]},
        "qas": {"question": ["What encoder?", "What encoder?", "Is it open?"],
                "answers": [{"answer": [answer]}, {"answer": [answer]}, {"answer": [none]}]},
    }  # fmt: skip


def test_every_question_with_evidence_once_per_paper() -> None:
    rows = fc.every_question({"p1": _paper()})
    assert [r["question"] for r in rows] == ["What encoder?"]  # duplicate and unanswerable out
    assert rows[0]["paper"] == "p1" and rows[0]["gold"] == [False, True, False]


def _row(n: int = 4) -> dict[str, Any]:
    texts = [f"Sentence {k} about topic number {k} here. Another one for paragraph {k}."
             for k in range(n)]  # fmt: skip
    sentences = [[(0, len(split_sentences(t)[0])), (len(split_sentences(t)[0]) + 1, len(t))]
                 for t in texts]  # fmt: skip
    gold_s = [[False, False]] * (n - 1) + [[True, False]]
    return {"id": "p#1", "paper": "p", "question": "topic number",
            "pages": [("", t) for t in texts], "paras": texts, "sentences": sentences,
            "gold_s": gold_s}  # fmt: skip


def test_the_sentences_used_for_gold_are_select_passages_own() -> None:
    assert fc.aligned(_row())


class _Probs:
    """Every page kept at 0.9; the last paragraph's sentences surest."""

    name = "probs"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.calls += 1
        if point == "triage_pages":
            return Decision(point, {k: truth(0.9) for k in qs}, "probs", fc.MODEL)
        sure = "paragraph 3" in str(state)
        return Decision(point, {k: truth(0.99 if sure else 0.8) for k in qs}, "probs", fc.MODEL)


def test_free_reuses_every_call_and_cuts_by_probability_where_page_order_cuts_the_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fc, "BUDGET", 120)  # two of four paragraphs fit
    row = _row()
    live = _Probs()
    out = asyncio.run(fc.ask([row], fc.lot_asker(live)))
    assert live.calls == 5  # one tournament call, four sentence calls; FREE made none
    got = fc.arms(row, out[0])
    assert got["overflow"]
    assert got["PAGE"]["recall"] == 0.0 and got["FREE"]["recall"] == 1.0
    assert got["GOLD"]["recall"] == 1.0


def test_the_rule() -> None:
    assert fc.verdict({"recall_ci95_cluster_exact": (0.01, 0.2)}).startswith("FREE confirmed")
    assert fc.verdict({"recall_ci95_cluster_exact": (-0.01, 0.2)}).startswith("not confirmed")
    assert fc.verdict({"recall_ci95_cluster_exact": (-0.2, -0.01)}).startswith("FREE loses")
    assert fc.verdict({"recall_ci95_cluster_exact": None}).startswith("no verdict")


def test_a_paid_run_refuses_before_the_key_without_its_launcher() -> None:
    def trap(*_: Any, **__: Any) -> Any:
        raise AssertionError("the key was read")

    with pytest.raises(SystemExit, match="c5-free-run.cmd"):
        fc.paid(None, load_key=trap, check=trap, build_live=trap)


def test_the_lot_is_bound_to_its_input_budget_and_cap() -> None:
    lot = fc.lot()
    assert lot.cap_usd == fc.CAP_USD <= 2.0 and fc.BUDGET == 3_400
    assert lot.inputs == ((fc.QASPER, fc.QASPER_SHA256),) and len(fc.QASPER_SHA256) == 64
    assert "benchmarks/passage_fit" in lot.instrument


def test_the_rule_reads_the_unrounded_bound() -> None:
    assert fc.verdict({"recall_ci95_cluster_exact": (0.00004, 0.2)}).startswith("FREE confirmed")
    assert fc.bounds([0.1 * k for k in range(41)]) == (0.1 * 1, 0.1 * 39)


def test_any_call_unanswered_gives_no_verdict_and_a_sensitivity_without_its_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fc, "BUDGET", 120)
    rows = [_row(), {**_row(), "id": "q#2", "paper": "q"}]
    live = _Probs()
    out = asyncio.run(fc.ask(rows, fc.lot_asker(live)))
    got = fc.report(rows, out, unanswered=2, affected=frozenset({"q#2"}))
    assert got["verdict"] == "no verdict: incomplete, 2 calls unanswered"
    assert got["sensitivity_without_affected"]["questions_left_out"] == 1
    assert got["sensitivity_without_affected"]["questions"] == 1
    assert fc.report(rows, out)["verdict"] != got["verdict"]


class _Moved(_Probs):
    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.calls += 1
        return Decision(point, {k: truth(0.9) for k in qs}, "moved", "jev-1.14.0")


def test_a_model_switch_is_a_written_stop_that_forbids_a_relaunch() -> None:
    async def check(_: str) -> None:
        return None

    got = asyncio.run(fc.session([_row()], fc.lot(), check, lambda _: (None, _Moved()),
                                 lambda: None))  # fmt: skip
    assert got["stop_kind"] == "model" and got["stopped"].startswith("model moved")
    assert not fc.paid_once.may_launch([{"stop_kind": got["stop_kind"]}])


def test_the_lot_spends_on_the_round_ledger_and_its_launcher_is_sealed_not_instrument(
    tmp_path: Path,
) -> None:
    lot = fc.lot()
    assert lot.ledger == fc.w17_round.LEDGER and lot.shared_cap_usd == 6.0 and lot.cap_usd == 2.0
    assert not any(p.endswith(".cmd") for p in lot.instrument)
    filled = tmp_path / "c5-free-run.cmd"
    text = lot.launcher.read_text(encoding="utf-8")
    filled.write_text(text.replace("<PYTHON>", "C:/py/python.exe", 1)
                      .replace("<KEYS_ENV_PATH>", "C:/k/.env", 1), encoding="utf-8")  # fmt: skip
    assert fc.paid_once.launcher_digest(filled) == fc.paid_once.launcher_digest(lot.launcher)
    assert fc.lot_asker(None).memo_failures  # a failed call is never asked again in the run


def test_an_unanswered_call_met_by_page_and_free_counts_once() -> None:
    asker = fc.lot_asker(None)  # a replay with nothing recorded
    asyncio.run(fc.ask([_row()], asker))
    assert asker.failures == 2  # the tournament call, met by both runs
    assert fc.unanswered(asker) == 1


class _Costly(_Probs):
    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        got = await super().decide(point, state, qs)
        return Decision(point, got.answers, "costly", fc.MODEL, cost_usd=0.15)


def test_a_decision_answered_again_from_the_memo_never_exhausts_the_squire() -> None:
    """The sealed run's defect: the squire's own meter charged a decision again each time the
    memo or the recording answered it, under a cap equal to the batch's, and cut 1,437 of
    FREE's decisions to defaults. Here PAGE's calls cost 1.50 and FREE's repeat them."""
    rows = [
        {**_row(), "id": f"q#{k}", "paper": "q", "question": f"topic number {k}"} for k in range(2)
    ]
    live = _Costly()
    out = asyncio.run(fc.ask(rows, fc.lot_asker(live)))
    assert live.calls == 10  # 5 a question, none asked twice
    for got in out:
        assert all(p is not None for entry in got["free"] if entry for _, p in entry)
