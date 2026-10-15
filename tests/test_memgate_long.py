"""Lot memgate-long (benchmarks/memgate_long/), with no network and no paid call: the question
selection, the caps and the stops, the verdict rules on synthetic numbers, replay determinism
and rows without text."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from sanchopanza.contract import Answer, DeciderOutOfFunds, DeciderUnavailable, Decision

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "benchmarks/memgate_long/memgate_long.py"
    spec = importlib.util.spec_from_file_location("memgate_long", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["memgate_long"] = module
    spec.loader.exec_module(module)
    return module


ml = _load()
import memgate_long_analysis as an  # noqa: E402  (on the path once the runner is loaded)

SECRET = "zebra-quartz"  # a word that only the sessions and the question hold


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ml, "OUT", tmp_path / "out")
    monkeypatch.setattr(ml, "LEDGER_PATH", tmp_path / "ledger.json")
    ml.HALTED.clear()
    yield
    ml.HALTED.clear()


def _q(i: int, sessions: int = 4, gold: int = 1) -> dict:
    turns = [
        [{"role": "user", "content": f"session {s} {SECRET} topic{s} " * 4,
          "has_answer": s == gold}]
        for s in range(sessions)
    ]  # fmt: skip
    return {
        "question_id": f"q{i}", "question_type": "single-session-user",
        "question": f"what did I say about topic{gold} {SECRET}?",
        "answer_session_ids": [f"answer_{gold}"],
        "haystack_session_ids": [f"answer_{s}" if s == gold else f"h{s}" for s in range(sessions)],
        "haystack_dates": [f"2023/01/0{s + 1}" for s in range(sessions)],
        "haystack_sessions": turns,
    }  # fmt: skip


class _Fake:
    """A live decider that answers every Truth 0.9 (keep, look) as jev-1.13.0, or raises."""

    name = "jev"

    def __init__(self, raises: Exception | None = None, cost: float = 0.001) -> None:
        self.raises, self.cost, self.calls = raises, cost, 0

    async def decide(self, point, state, questions):
        self.calls += 1
        await asyncio.sleep(0)
        if self.raises is not None:
            raise self.raises
        answers = {k: Answer(kind="truth", confidence=0.8, truth=0.9) for k in questions}
        return Decision(point, answers, "jev", ml.MODEL, input_tokens=10, cost_usd=self.cost)


def _run(qs, fake, *, cap=1.0, live=True):
    return asyncio.run(ml.run(qs, live=live, name="a7", batch="test", cap_usd=cap,
                              with_rec=False, make_inner=lambda cell: fake))  # fmt: skip


# ---- selection --------------------------------------------------------------------------------


def _test_slice(n: int = 120) -> list[dict]:
    return [{"question_id": f"t{i:03d}"} for i in range(n)]


def test_select_takes_the_84_after_l6s_36_in_the_seeded_order():
    test = _test_slice()
    order = ml.l6.launch_order(len(test))
    used = [test[i]["question_id"] for i in order[:36]]
    rest = ml.select(test, {"d1", "d2"}, used)
    ids = [q["question_id"] for q in rest]
    assert len(ids) == 84 == len(set(ids))
    assert ids == [test[i]["question_id"] for i in order[36:]]
    assert not set(ids) & set(used)


def test_select_refuses_when_l6s_questions_are_not_the_head_of_the_order():
    test = _test_slice()
    order = ml.l6.launch_order(len(test))
    used = [test[i]["question_id"] for i in order[1:37]]
    with pytest.raises(SystemExit):
        ml.select(test, set(), used)


def test_select_refuses_a_count_other_than_84_or_an_overlap_with_dev():
    test = _test_slice(119)
    order = ml.l6.launch_order(len(test))
    used = [test[i]["question_id"] for i in order[:36]]
    with pytest.raises(SystemExit, match="not 84"):
        ml.select(test, set(), used)
    test = _test_slice()
    order = ml.l6.launch_order(len(test))
    used = [test[i]["question_id"] for i in order[:36]]
    with pytest.raises(SystemExit, match="dev"):
        ml.select(test, {test[order[50]]["question_id"]}, used)


def test_the_registered_constants():
    assert ml.MODEL == "jev-1.13.0" and ml.CELLS == ("j13r-S", "j13r-L")
    assert ml.BATCH_CAP_USD == 1.50 and ml.LEDGER_CAP_USD == 1.50
    assert ml.SMOKE_CAP_USD == 0.05 and ml.SMOKE_BATCH != ml.BATCH
    assert ml.CONCURRENCY <= 4 and ml.N_QUESTIONS == 84 and ml.L6_USED == 36
    assert ml.l6.LONG_LIMITS.page_chars == 400_000 and ml.l6.LONG_LIMITS.pages_per_call == 1_000
    assert ml.L6_A7_USD == 0.4425


# ---- caps and stops ---------------------------------------------------------------------------


def test_the_cap_refuses_before_calling_and_stops_the_run(monkeypatch):
    monkeypatch.setattr(ml, "Q_EST_USD", 0.0)  # the hard cap holds even if the estimate is wrong
    fake = _Fake()
    rows = _run([_q(i) for i in range(6)], fake, cap=1e-9)
    assert fake.calls == 0 and ml.HALTED and "spend cap" in ml.HALTED[0]
    assert len(rows) == ml.WAVE  # the first wave ends, no other starts


def test_the_soft_stop_starts_no_wave_the_cap_would_not_hold():
    fake = _Fake()
    rows = _run([_q(i) for i in range(4)], fake, cap=ml.Q_EST_USD * ml.WAVE * 0.99)
    assert rows == [] and fake.calls == 0 and not ml.HALTED


def test_spend_stays_under_the_batch_cap_in_the_ledger():
    fake = _Fake(cost=0.004)
    cap = 0.05
    _run([_q(i) for i in range(20)], fake, cap=cap)
    assert ml.spent("test") <= cap + 1e-9
    assert ml.spent("test") == pytest.approx(0.004 * fake.calls)


@pytest.mark.parametrize(
    "error",
    [DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)"),
     DeciderUnavailable("jev did not answer: HTTP 429")],
)  # fmt: skip
def test_a_402_or_a_429_stops_dead(error):
    fake = _Fake(raises=error)
    rows = _run([_q(i) for i in range(6)], fake)
    assert ml.HALTED and fake.calls <= ml.WAVE  # only the calls already in flight
    assert len(rows) == ml.WAVE


def test_another_refusal_is_a_failed_cell_not_a_stop():
    fake = _Fake(raises=DeciderUnavailable("jev unreachable: ReadTimeout"))
    rows = _run([_q(i) for i in range(4)], fake)
    assert not ml.HALTED and len(rows) == 4
    assert all(r["j13r-S"] is None and r["j13r-L"] is None for r in rows)


def test_no_retry_on_429_leaves_529_retryable(monkeypatch):
    from sanchopanza.providers import jev

    monkeypatch.setattr(jev, "RETRYABLE", frozenset({429, 529}))
    ml.no_retry_on_429()
    assert frozenset({529}) == jev.RETRYABLE


def test_the_live_path_refuses_without_the_seal():
    with pytest.raises(SystemExit, match="seal"):
        ml.require_prereg()


def test_seal_then_require_passes_and_a_changed_prereg_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(ml, "SEALED", ("tests/test_memgate_long.py",))
    monkeypatch.setattr(ml, "SEALED_DATA", ())
    monkeypatch.setattr(ml, "REPO", tmp_path)
    monkeypatch.setattr(ml, "OUT", tmp_path / "docs")
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_memgate_long.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "docs/prereg.md").write_text("rules\n", encoding="utf-8")
    first = ml.seal()
    ml.require_prereg()
    assert ml.seal() == first  # the same seal again is accepted
    (tmp_path / "docs/prereg.md").write_text("other rules\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ml.require_prereg()
    with pytest.raises(SystemExit, match="another seal"):
        ml.seal()


# ---- replay and rows --------------------------------------------------------------------------


def test_replay_gives_the_same_rows_for_free():
    qs = [_q(i, gold=i % 3) for i in range(5)]
    fake = _Fake()
    live = _run(qs, fake)
    paid = fake.calls
    again = _run(qs, _Fake(), live=False)
    assert again == live and paid > 0
    assert all(r["j13r-L"] is not None and r["j13r-S"] is not None for r in live)
    assert [r["rank"] for r in live] == [36, 37, 38, 39, 40]


def test_rows_and_recordings_hold_no_text():
    qs = [_q(i) for i in range(3)]
    rows = _run(qs, _Fake())
    ml.write_rows("a7", rows)
    for path in [*ml.OUT.glob("*.jsonl")]:
        assert SECRET not in path.read_text(encoding="utf-8"), path.name
    assert set(rows[0]) == {"id", "type", "gold", "sizes", "bm25@3", "excerpt_seen",
                            "excerpt_total", "j13r-look", "j13r-S", "j13r-L", "rank"}  # fmt: skip


# ---- verdict rules ----------------------------------------------------------------------------


def _row(i: int, gold: list[int], s: list[int] | None, lng: list[int] | None,
         bm25: list[int], look: bool = True) -> dict:  # fmt: skip
    return {"id": f"q{i}", "gold": gold, "sizes": [10] * 5, "bm25@3": bm25,
            "excerpt_seen": 1, "excerpt_total": 1, "j13r-look": look,
            "j13r-S": s, "j13r-L": lng}  # fmt: skip


def test_confirmado_when_l_beats_s_clearly():
    rows = [_row(i, [0], [] if i % 2 else [0], [0], [0]) for i in range(40)]
    out = an.analyse(rows)
    assert out["confirmation"]["diff"] == 0.5 and out["confirmation"]["ci95"][0] > 0
    assert out["confirmation"]["verdict"] == "confirmado"
    assert out["family"][an.PRIMARY]["p_holm"] == out["family"][an.PRIMARY]["p"]  # family of one


def test_no_confirmado_when_l_and_s_tie():
    rows = [_row(i, [0], [0] if i % 2 else [], [0] if i % 2 else [], [0]) for i in range(40)]
    assert an.analyse(rows)["confirmation"]["verdict"] == "no confirmado"


def test_failures_and_small_n_withhold_the_verdict():
    good = [_row(i, [0], [], [0], [0]) for i in range(40)]
    failing = [_row(100 + i, [0], [], None, [0]) for i in range(2)]  # L failed on 2 of 42
    out = an.analyse([*good, *failing])
    assert out["failures"]["j13r-L"] == 2 and out["complete"] == 40
    assert out["confirmation"]["verdict"] == "no confirmado (fallos)"
    assert an.analyse(good[:19])["confirmation"]["verdict"] == "no concluyente (n bajo)"


def test_bm25_verdicts_bate_alcanza_and_no_alcanza():
    beats = an.bm25_verdict({"diff": 0.05, "ci95": (0.01, 0.09)}, 84)
    within = an.bm25_verdict({"diff": -0.03, "ci95": (-0.1, 0.04)}, 84)
    short = an.bm25_verdict({"diff": -0.0308, "ci95": (-0.159, 0.086)}, 84)  # L6's -3.08
    assert (beats, within, short) == ("bate", "alcanza", "no alcanza")
    assert an.bm25_verdict({"diff": 0.2, "ci95": (0.1, 0.3)}, 19) == "no concluyente (n bajo)"


def test_the_pooled_reading_is_descriptive_and_counts_both_sets():
    new = [_row(i, [0], [], [0], [0]) for i in range(30)]
    old = [_row(100 + i, [0], [0], [0], [1]) | {"j14-L": [0]} for i in range(10)]
    out = an.analyse(new, l6_rows=old)
    pooled = out["pooled_120_descriptive"]
    assert pooled["complete"] == 40 and "descriptive" in pooled["note"]
    assert not {"verdict", "confirmation", "bm25_verdicts", "family"} & set(pooled)


def test_power_shrinks_the_se_with_n():
    rows = [_row(i, [0], [] if i % 4 == 0 else [0], [0] if i % 6 else [], [0] if i % 5 else [1])
            for i in range(36)]  # fmt: skip
    p36, p84 = an.power(rows, 36), an.power(rows, 84)
    assert p84["se_window"] < p36["se_window"]
    assert p84["se_window"] == pytest.approx(p36["se_window"] * (36 / 84) ** 0.5, abs=1e-3)
    assert 0 <= p84["power_at_half"] <= p84["power_at_l6_effect"] <= 1
