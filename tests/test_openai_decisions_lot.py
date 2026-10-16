"""D1's runner, free: the registered queries, the verdict rule, the pairing and the refusals
before any key is read. No network."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "openai_decisions"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import paid_once  # noqa: E402
import run  # noqa: E402

from sanchopanza import answers  # noqa: E402
from sanchopanza.contract import Decision, Truth  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402


def test_the_benches_ask_the_registered_queries() -> None:
    assert len(run.queries()) == run.QUERIES == 301


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (0.001, 0.05, "mejor"),
        (-0.049, 0.02, "no peor"),
        (-0.05, 0.02, "no concluyente"),
        (-0.09, -0.051, "peor"),
        (-0.09, -0.05, "no concluyente"),
    ],
)
def test_the_verdict_rule_is_the_sealed_one(lo, hi, expected) -> None:
    assert run.verdict(lo, hi) == expected


def test_paired_counts_and_a_deterministic_interval() -> None:
    a = [True] * 80 + [False] * 20
    b = [True] * 75 + [False] * 5 + [True] * 10 + [False] * 10
    one, two = run.paired(a, b), run.paired(a, b)
    assert one == two
    assert (one["only_a"], one["only_b"]) == (5, 10)
    assert one["difference"] == pytest.approx(-0.05)
    assert one["ci95"][0] < one["difference"] < one["ci95"][1]


def test_the_lot_counts_only_a_dated_snapshot_as_its_model() -> None:
    assert run.LOT.serves("gpt-6-luna") and run.LOT.serves("gpt-6-luna-2026-10-06")
    for other in ("gpt-6-luna2", "gpt-6-luna-mini", "gpt-6-luna-2026-10", "jev-1.13.0"):
        assert not run.LOT.serves(other)
    assert run.LOT.price_per_mtok == 0.10 and run.LOT.cap_usd == 0.10


def test_paid_refuses_without_the_seal_before_reading_the_key(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    lot = paid_once.Lot(
        name="d1-test",
        prereg=tmp_path / "prereg.md",
        launcher=tmp_path / "run.cmd",
        fixture=tmp_path / "fixture.jsonl",
        model="gpt-6-luna",
        cap_usd=0.10,
        instrument=(),
        home=tmp_path,
        price_per_mtok=0.10,
        snapshot=r"\d{4}-\d{2}-\d{2}",
        empty_streak=5,
    )
    (tmp_path / "prereg.md").write_text("x", encoding="utf-8")
    (tmp_path / "run.cmd").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        paid_once.run_paid(
            lot,
            run.queries()[:3],
            load_key=lambda: calls.append("key"),
            make_live=lambda: calls.append("live"),
            check=lambda model: calls.append("check"),
        )
    assert calls == []


def test_the_launcher_refuses_its_placeholders() -> None:
    text = (ROOT / "openai-decisions-run.cmd").read_text(encoding="utf-8")
    assert 'set "PY=<PYTHON>"' in text and 'set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"' in text
    assert "openai_decisions\\run.py paid" in text


# --- after the review: refusals recorded, the preflight's rule, unusable answers not right ---


def _decision(answers: dict, *, model: str = "gpt-6-luna", tokens: int = 100) -> Decision:
    return Decision("p", answers, "openai-decisions", model, input_tokens=tokens,
                    cost_usd=tokens * 0.10 / 1e6)  # fmt: skip


def _lot(tmp_path, streak: int = 5) -> paid_once.Lot:
    return paid_once.Lot(name="d1-test", prereg=tmp_path / "p.md", launcher=tmp_path / "r.cmd",
                         fixture=tmp_path / "fx.jsonl", model="gpt-6-luna", cap_usd=0.10,
                         instrument=(), home=tmp_path, price_per_mtok=0.10,
                         snapshot=r"\d{4}-\d{2}-\d{2}", empty_streak=streak)  # fmt: skip


class _Live:
    """Answers each query with nothing (a refusal) or with every question answered."""

    name = "openai-decisions"

    def __init__(self, refuse: set[int]) -> None:
        self.refuse, self.calls = refuse, 0

    async def decide(self, point, state, questions):
        i, self.calls = self.calls, self.calls + 1
        if i in self.refuse:
            return _decision({})
        return _decision({k: answers.truth(0.9) for k in questions})


def _truth_queries(n: int) -> list:
    return [("p", {"i": i}, {"q": Truth(f"question {i}")}) for i in range(n)]


def test_a_refusal_is_recorded_and_the_run_goes_on(tmp_path) -> None:
    lot, live = _lot(tmp_path), _Live({1, 3})
    out = asyncio.run(paid_once.ask_missing(_truth_queries(6), lot, live=live))
    assert (out["stopped"], out["asked"], out["unusable_answers"], live.calls) == (None, 6, 2, 6)
    assert asyncio.run(paid_once._missing(_truth_queries(6), lot)) == []  # asked, not re-asked


def test_five_unusable_answers_in_a_row_stop_the_run(tmp_path) -> None:
    out = asyncio.run(paid_once.ask_missing(_truth_queries(9), _lot(tmp_path),
                                            live=_Live(set(range(9)))))  # fmt: skip
    assert out["asked"] == 5 and "5 in a row" in out["stopped"]


def test_the_old_lots_still_stop_at_the_first_empty_answer(tmp_path) -> None:
    out = asyncio.run(paid_once.ask_missing(_truth_queries(4), _lot(tmp_path, streak=0),
                                            live=_Live({1})))  # fmt: skip
    assert out["asked"] == 2 and out["stopped"].startswith("failed or empty answer")


def _preflight_answers() -> dict:
    return {"ok": answers.truth(0.9), "kind": answers.choice({"operations": 0.9, "fiction": 0.1}),
            "urgency": answers.score([0.7, 0.2, 0.1])}  # fmt: skip


def test_the_preflight_needs_every_type_and_a_token_count() -> None:
    good = _decision(_preflight_answers())
    assert run.check_preflight(good, good.cost_usd, 0.02, 0.0, 0.10)["preflight"] == "ok"
    no_score = _decision({k: v for k, v in _preflight_answers().items() if k != "urgency"})
    with pytest.raises(SystemExit, match="urgency"):
        run.check_preflight(no_score, no_score.cost_usd, 0.02, 0.0, 0.10)
    with pytest.raises(SystemExit, match="token count"):
        run.check_preflight(_decision(_preflight_answers(), tokens=0), 1e-5, 0.02, 0.0, 0.10)
    with pytest.raises(SystemExit, match="served"):
        run.check_preflight(_decision(_preflight_answers(), model="gpt-6-luna-mini"), 1e-5, 0.02,
                            0.0, 0.10)  # fmt: skip


def test_the_preflight_projects_the_run_at_its_real_to_estimated_ratio() -> None:
    real = _decision(_preflight_answers(), tokens=1000)  # 0.0001 USD
    out = run.check_preflight(real, real.cost_usd / 3, 0.02, 0.0, 0.10)  # billed 3x the estimate
    assert out["ratio"] == pytest.approx(3.0) and out["projected_usd"] == pytest.approx(0.06)
    with pytest.raises(SystemExit, match="over the 0.1 cap"):
        run.check_preflight(real, real.cost_usd / 6, 0.02, 0.0, 0.10)


def test_a_row_without_a_usable_answer_is_flagged_for_both_arms() -> None:
    from sanchopanza.providers import create

    jev = run.flagged_rows(create("recorded", path=str(run.JEV_FIXTURE)))
    assert len(jev) == 244 and sum(f for _, f in jev) == 0  # Jev answered every question
    empty = run.flagged_rows(RecordedDecider(()))
    assert sum(f for _, f in empty) == 244 - 17  # all but the code denials ask a question


def test_a_partial_refusal_does_not_count_toward_the_streak(tmp_path) -> None:
    """A provider that refuses one question of two still answers: only a decision with no
    usable answer at all moves the streak, so a refused point does not stop the run."""

    class _Half:
        name, calls = "openai-decisions", 0

        async def decide(self, point, state, questions):
            self.calls += 1
            return _decision({"a": answers.truth(0.9)})  # "b" refused

    qs = [("p", {"i": i}, {"a": Truth("a"), "b": Truth("b")}) for i in range(8)]
    out = asyncio.run(paid_once.ask_missing(qs, _lot(tmp_path), live=_Half()))
    assert (out["stopped"], out["asked"], out["unusable_answers"]) == (None, 8, 8)


def test_the_registered_streak_is_longer_than_any_point_run() -> None:
    longest, current, last = 0, 0, None
    for point, _, _ in run.queries():
        current = current + 1 if point == last else 1
        last, longest = point, max(longest, current)
    assert longest < run.EMPTY_STREAK


def test_a_failed_preflight_leaves_no_launch_record(tmp_path) -> None:
    lot = _lot(tmp_path)
    calls: list[str] = []

    async def failing(model: str) -> None:
        calls.append("check")
        raise SystemExit("preflight: refused")

    monkey = {
        "require_sealed": paid_once.require_sealed,
        "require_instrument": paid_once.require_instrument,
        "require_inputs": paid_once.require_inputs,
    }
    paid_once.require_sealed = lambda lot: None
    paid_once.require_instrument = lambda lot: "0" * 40
    paid_once.require_inputs = lambda lot: None
    try:
        with pytest.raises(SystemExit, match="preflight"):
            paid_once.run_paid(lot, _truth_queries(2), load_key=lambda: calls.append("key"),
                               make_live=lambda: calls.append("live"), check=failing)  # fmt: skip
    finally:
        for name, fn in monkey.items():
            setattr(paid_once, name, fn)
    assert calls == ["key", "check"]
    assert paid_once.history(lot) == []


def test_the_published_result_replays_from_the_recording() -> None:
    """docs/results/2026-10-16-openai-decisions: 200 against 206 of 244, "no concluyente"."""
    if not run.LOT.fixture.exists():
        pytest.skip("D1's recording is not present")
    out = run.report()
    primary = out["primary"]
    assert (primary["a_right"], primary["b_right"], primary["only_a"], primary["only_b"]) == (
        200, 206, 7, 13)  # fmt: skip
    assert primary["verdict"] == "no concluyente" and out["queries_not_asked"] == 0
    assert out["rows_without_a_usable_answer"] == {"openai": 0, "jev": 0}
    assert [round(x, 4) for x in primary["ci95"]] == [-0.0615, 0.0123]
