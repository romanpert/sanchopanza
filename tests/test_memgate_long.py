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


def test_the_cap_refuses_before_calling_and_drops_the_wave_it_stopped(monkeypatch):
    monkeypatch.setattr(ml, "Q_EST_USD", 0.0)  # the hard cap holds even if the estimate is wrong
    fake = _Fake()
    rows = _run([_q(i) for i in range(6)], fake, cap=1e-9)
    assert fake.calls == 0 and ml.halt_kind() == ml.CAP and "spend cap" in ml.HALTED[0]
    assert rows == []


def test_a_cap_stop_keeps_the_completed_waves_and_writes_them(monkeypatch):
    monkeypatch.setattr(ml, "Q_EST_USD", 0.0)
    fake = _Fake(cost=0.004)  # 3 calls a question, 0.024 a wave: the third wave hits 0.05
    rows = _run([_q(i) for i in range(10)], fake, cap=0.05)
    assert ml.halt_kind() == ml.CAP and len(rows) == 2 * ml.WAVE
    assert [r["rank"] for r in rows] == [36, 37, 38, 39]
    # The fake costs far more than its reservation (a few characters): the calls in flight can
    # overshoot by the difference, CappedDecider's documented limit. Jev's estimate errs high.
    assert ml.spent("test") <= 0.05 + ml.CONCURRENCY * 0.004
    assert ml.finish("a7", rows, "test", 0.05) == 0 and len(ml.read_rows("a7")) == 4


def test_a_ledger_refusal_with_room_left_is_a_pause_not_the_cap(monkeypatch):
    from sanchopanza.budget import SpendLedger

    monkeypatch.setattr(SpendLedger, "reserve", lambda self, usd, **kw: None)  # a lock fault
    fake = _Fake()
    rows = _run([_q(i) for i in range(4)], fake, cap=1.0)
    assert fake.calls == 0 and ml.halt_kind() == ml.CAP and rows == []
    assert ml.finish("a7", rows, "test", 1.0) == 2 and ml.read_rows("a7") is None


def test_a_ledger_fault_after_completed_waves_writes_nothing(monkeypatch):
    from sanchopanza.budget import SpendLedger

    real, calls = SpendLedger.reserve, {"n": 0}

    def flaky(self, usd, **kw):
        calls["n"] += 1
        return None if calls["n"] > 3 * ml.WAVE else real(self, usd, **kw)

    monkeypatch.setattr(SpendLedger, "reserve", flaky)
    rows = _run([_q(i) for i in range(6)], _Fake(), cap=1.0)
    assert len(rows) == ml.WAVE and ml.halt_kind() == ml.CAP
    assert ml.finish("a7", rows, "test", 1.0) == 2 and ml.read_rows("a7") is None


def test_no_rows_are_never_written():
    assert ml.finish("a7", [], "test", 1.0) == 2 and ml.read_rows("a7") is None


def test_the_soft_stop_starts_no_wave_the_cap_would_not_hold():
    fake = _Fake()
    rows = _run([_q(i) for i in range(4)], fake, cap=ml.Q_EST_USD * ml.WAVE * 0.99)
    assert rows == [] and fake.calls == 0 and not ml.HALTED


def test_the_soft_stop_also_reads_the_ledgers_room(monkeypatch):
    monkeypatch.setattr(ml, "LEDGER_CAP_USD", ml.Q_EST_USD * ml.WAVE * 0.99)
    fake = _Fake()
    rows = _run([_q(i) for i in range(4)], fake, cap=1.0)
    assert rows == [] and fake.calls == 0


def test_spend_stays_under_the_batch_cap_in_the_ledger():
    fake = _Fake(cost=0.004)
    cap = 0.05
    _run([_q(i) for i in range(20)], fake, cap=cap)
    assert ml.spent("test") <= cap + 1e-9
    assert ml.spent("test") == pytest.approx(0.004 * fake.calls)


@pytest.mark.parametrize(
    "error",
    [DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)"),
     DeciderUnavailable("jev did not answer: HTTP 429"),
     DeciderUnavailable("jev did not answer: HTTP 401"),
     DeciderUnavailable("jev did not answer: HTTP 403"),
     DeciderUnavailable("jev did not answer: HTTP 503"),
     DeciderUnavailable("jev unreachable: ConnectError")],
)  # fmt: skip
def test_an_outage_pauses_dead_and_writes_nothing(error):
    fake = _Fake(raises=error)
    rows = _run([_q(i) for i in range(6)], fake)
    assert ml.halt_kind() == ml.PAUSE and fake.calls <= ml.WAVE  # only the calls in flight
    assert rows == [] and ml.finish("a7", rows, "test", 1.0) == 2 and ml.read_rows("a7") is None


@pytest.mark.parametrize(
    ("text", "stop"),
    [("jev did not answer: HTTP 529", True), ("jev unreachable: ReadTimeout", False),
     ("jev unreachable: ConnectTimeout", False), ("jev refused (HTTP 400): too long", False),
     ("spend cap: not called", False)],
)  # fmt: skip
def test_what_counts_as_an_outage(text, stop):
    assert ml.stops(DeciderUnavailable(text)) is stop


def test_a_timeout_on_one_window_is_a_failed_cell_not_a_stop():
    ok, slow = _Fake(), _Fake(raises=DeciderUnavailable("jev unreachable: ReadTimeout"))

    def inner(cell):
        return slow if cell.endswith("L") else ok

    rows = asyncio.run(ml.run([_q(i) for i in range(4)], live=True, name="a7", batch="test",
                              cap_usd=1.0, with_rec=False, make_inner=inner))  # fmt: skip
    assert not ml.HALTED and len(rows) == 4
    assert all(r["j13r-L"] is None and r["j13r-S"] is not None for r in rows)
    assert all(r["errors"] == {"j13r-L": "ReadTimeout"} for r in rows)
    assert an.errors_by_class(rows) == {"j13r-L": {"ReadTimeout": 4}}
    assert an.analyse(rows)["errors_by_class"] == {"j13r-L": {"ReadTimeout": 4}}


@pytest.mark.parametrize(
    ("error", "label"),
    [(DeciderUnavailable("jev unreachable: ReadTimeout"), "ReadTimeout"),
     (DeciderUnavailable("jev unreachable: ConnectTimeout"), "ConnectTimeout"),
     (DeciderUnavailable(f"jev refused (HTTP 400): {SECRET} too long"), "HTTP400"),
     (DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)"), "HTTP402"),
     (RuntimeError(f"something {SECRET}"), "RuntimeError")],
)  # fmt: skip
def test_error_class_is_a_name_without_text(error, label):
    assert ml.error_class(error) == label


def test_a_replay_keeps_the_live_runs_error_classes():
    live = [{"id": "a", "j13r-L": None, "errors": {"j13r-L": "ReadTimeout"}, "rank": 36},
            {"id": "b", "j13r-L": [0], "rank": 37}]  # fmt: skip
    replayed = [{k: v for k, v in r.items() if k != "errors"} for r in live]
    assert ml.with_live_errors(replayed, live) == live
    assert [list(r) for r in ml.with_live_errors(replayed, live)] == [list(r) for r in live]


def test_three_failed_calls_in_a_row_pause_the_run():
    fake = _Fake(raises=DeciderUnavailable("jev unreachable: ReadTimeout"))
    rows = _run([_q(i) for i in range(6)], fake)
    assert ml.halt_kind() == ml.PAUSE and "in a row" in ml.HALTED[0]
    assert rows == [] and fake.calls <= ml.MAX_CONSECUTIVE_FAILURES + ml.WAVE


def test_a_wrong_model_pauses_and_is_not_recorded():
    class Other(_Fake):
        async def decide(self, point, state, questions):
            got = await super().decide(point, state, questions)
            return Decision(point, got.answers, "jev", "jev-1.14.0", cost_usd=0.001)

    rows = _run([_q(0)], Other())
    assert ml.halt_kind() == ml.PAUSE and "served jev-1.14.0" in ml.HALTED[0] and rows == []
    recorded = [p for p in ml.OUT.glob("*-answers-*.jsonl") if p.read_text(encoding="utf-8")]
    assert recorded == []


def test_no_retry_on_429_leaves_529_retryable(monkeypatch):
    from sanchopanza.providers import jev

    monkeypatch.setattr(jev, "RETRYABLE", frozenset({429, 529}))
    ml.no_retry_on_429()
    assert frozenset({529}) == jev.RETRYABLE


def test_jev_inner_sets_the_header_and_timeout_by_window(monkeypatch):
    from sanchopanza.providers.jev import LONG_CONTEXT_HEADER

    monkeypatch.setenv("TYPESAFE_API_KEY", "placeholder-for-a-test")
    long, short = ml.jev_inner("j13r-L"), ml.jev_inner("j13r-S")
    assert long.model == short.model == "jev-1.13.0"
    assert long._headers() == {LONG_CONTEXT_HEADER: "true"} and long._timeout_s == 180.0
    assert short._headers() == {} and short._timeout_s == 30.0


def test_the_live_path_refuses_without_the_seal():
    with pytest.raises(SystemExit, match="seal"):
        ml.require_prereg()


@pytest.mark.parametrize("entry", ["smoke", "run"])
def test_the_live_paths_check_the_seal_before_the_key_or_the_preflight(monkeypatch, entry):
    touched = []
    monkeypatch.setattr(ml.l4, "load_key", lambda: touched.append("key"))
    monkeypatch.setattr(ml, "preflight_or_stop", lambda: touched.append("preflight"))
    with pytest.raises(SystemExit, match="seal"):
        ml.smoke(True) if entry == "smoke" else ml.run_live()
    assert touched == []


def _sealable(tmp_path, monkeypatch):
    monkeypatch.setattr(ml, "SEALED", ("tests/test_memgate_long.py",))
    monkeypatch.setattr(ml, "SEALED_DATA", ())
    monkeypatch.setattr(ml, "REPO", tmp_path)
    monkeypatch.setattr(ml, "OUT", tmp_path / "docs")
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_memgate_long.py").write_text("x\n", encoding="utf-8")
    (tmp_path / "docs/prereg.md").write_text("rules\n", encoding="utf-8")


def test_seal_then_require_passes_and_a_changed_prereg_fails(tmp_path, monkeypatch):
    _sealable(tmp_path, monkeypatch)
    first = ml.seal()
    ml.require_prereg()
    assert ml.seal() == first  # the same seal again is accepted
    (tmp_path / "docs/prereg.md").write_text("other rules\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ml.require_prereg()
    with pytest.raises(SystemExit, match="another seal"):
        ml.seal()
    assert ml.seal(again=True) != first  # before any answer or spend, a re-seal is allowed


def test_no_reseal_once_answers_or_spend_exist(tmp_path, monkeypatch):
    _sealable(tmp_path, monkeypatch)
    ml.seal()
    (tmp_path / "docs/prereg.md").write_text("other rules\n", encoding="utf-8")
    (tmp_path / "docs/smoke-answers-j13r-L.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="no re-seal"):
        ml.seal(again=True)
    (tmp_path / "docs/smoke-answers-j13r-L.jsonl").unlink()
    from sanchopanza.budget import SpendLedger

    ledger = SpendLedger(ml.LEDGER_PATH, cap_usd=1.0)
    ledger.settle(ledger.reserve(0.001, batch=ml.SMOKE_BATCH), 0.001)
    with pytest.raises(SystemExit, match="no re-seal"):
        ml.seal(again=True)


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


def test_failed_cells_hold_their_class_and_no_text():
    ok = _Fake()
    refused = _Fake(raises=DeciderUnavailable(f"jev refused (HTTP 400): {SECRET} is too long"))

    def inner(cell):
        return refused if cell.endswith("L") else ok

    rows = asyncio.run(ml.run([_q(i) for i in range(2)], live=True, name="a7", batch="test",
                              cap_usd=1.0, with_rec=False, make_inner=inner))  # fmt: skip
    ml.write_rows("a7", rows)
    assert all(r["errors"] == {"j13r-L": "HTTP400"} for r in rows)
    for path in [*ml.OUT.glob("*.jsonl")]:
        assert SECRET not in path.read_text(encoding="utf-8"), path.name


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
