"""A5 (`benchmarks/facts_gate/`) and the shared paid helper (`benchmarks/paid_once.py`).

Nothing here calls a paid API: the live decider is a fake, and the ledger a temporary file.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import pathlib
import re
import sys

import pytest

from sanchopanza.contract import Answer, Decision

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cases = _load("facts_gate_cases", ROOT / "benchmarks" / "facts_gate" / "cases.py")
run = _load("facts_gate_run", ROOT / "benchmarks" / "facts_gate" / "run.py")
paid_once = sys.modules["paid_once"]
NUMBER = re.compile(r"\d[\d.,]*\d|\d")

# --- the constructed batch ----------------------------------------------------------------


def test_the_committed_batch_is_the_seeded_one_and_its_hash_holds():
    text = cases.text_of(cases.build())
    committed = (ROOT / "benchmarks" / "facts_gate" / "cases.jsonl").read_bytes()
    assert committed.replace(b"\r\n", b"\n").decode("utf-8") == text
    sealed = (ROOT / "benchmarks" / "facts_gate" / "cases.sha256").read_text().strip()
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == sealed == run.CASES_SHA256


def test_the_batch_mix_is_the_registered_one():
    built = cases.build()
    assert len(built) == 1500
    labels = [c["expected"] for c in built]
    assert (labels.count("unrelated"), labels.count("agree"), labels.count("conflict")) == (
        600,
        450,
        450,
    )
    shapes = [c["shape"] for c in built]
    assert (shapes.count("same"), shapes.count("twin")) == (560, 40)
    assert len({c["id"] for c in built}) == 1500
    pairs = {frozenset((c["input"]["fact_a"], c["input"]["fact_b"])) for c in built}
    assert len(pairs) == 1500  # no pair twice, in either order
    assert {c["lang"] for c in built} == {"es", "en"}


def test_each_shape_is_its_label_by_construction():
    for c in cases.build():
        a, b = c["input"]["fact_a"], c["input"]["fact_b"]
        assert a != b
        if c["shape"] in ("restated", "detail"):
            assert c["expected"] == "agree"
        elif c["shape"] == "values":
            assert c["expected"] == "conflict"
        else:
            assert c["expected"] == "unrelated"
        assert " de el " not in a + b


def test_both_wordings_of_an_attribute_name_the_same_event():
    """A conflict between the two wordings is one only if they name the same event: a
    founding and an incorporation, or edition N and N editions held, would not be."""
    for (kind, attribute), (es, en) in cases.EVENT_STEMS.items():
        templates = cases.KINDS[kind][2][attribute][3]
        assert all(es in t.lower() for t in templates[:2]), (kind, attribute)
        assert all(en in t.lower() for t in templates[2:]), (kind, attribute)
    every = {(kind, a) for kind, (_, _, attributes) in cases.KINDS.items() for a in attributes}
    assert len(every) == 24 and set(cases.EVENT_STEMS) == every


def test_an_agreement_states_one_value_and_a_conflict_two():
    for c in cases.build():
        a, b = c["input"]["fact_a"], c["input"]["fact_b"]
        na, nb = set(NUMBER.findall(a)), set(NUMBER.findall(b))
        if c["expected"] == "agree":
            assert na == nb, c["id"]
        elif c["shape"] == "values":
            assert na != nb, c["id"]


def test_a_conflict_value_is_plainly_different():
    rng = __import__("random").Random(3)
    v = cases.draw(rng, "museum", "visitors")
    w = cases.other_value(rng, "museum", "visitors", v)
    assert abs(w - v) >= 0.15 * v


# --- the gate rule ------------------------------------------------------------------------


def _rows(spec):
    """spec: (expected, shipped verdict, verdict at every gate >= threshold)."""
    out = []
    for i, (expected, shipped, opens_at) in enumerate(spec):
        row = {"id": str(i), "expected": expected, "shipped": shipped}
        for g in run.GATES:
            row[f"g{g:.2f}"] = shipped or ("unrelated" if g <= opens_at else None)
        out.append(row)
    return out


def test_added_counts_only_what_the_shipped_policy_left_undecided():
    rows = _rows([("unrelated", None, 0.66), ("agree", None, 0.62), ("unrelated", "agree", 0.9)])
    got = run.added(rows, 0.60)
    assert (got["added"], got["right"], got["wrong"]) == (2, 1, 1)
    assert got["net"] == 1 - 4


def test_the_derived_gate_is_the_best_net_and_ties_go_stricter():
    rows = _rows([("unrelated", None, 0.66), ("unrelated", None, 0.66), ("agree", None, 0.55)])
    assert run.derive(rows) == 0.65
    assert run.derive(_rows([("agree", None, 0.70)])) is None


def test_the_verdict_needs_enough_cases_and_the_target():
    few = _rows([("unrelated", None, 0.70)] * 10)
    assert run.verdict(few, 0.65)["verdict"].startswith("undecided")
    good = _rows([("unrelated", None, 0.70)] * 30)
    assert run.verdict(good, 0.65)["verdict"] == "the gate beats the shipped policy"
    bad = _rows([("unrelated", None, 0.70)] * 20 + [("conflict", None, 0.70)])
    assert run.verdict(bad, 0.65)["verdict"] == "the gate does not beat the shipped policy"
    assert "stands" in run.verdict(good, None)["verdict"]


def test_the_added_verdicts_are_broken_down_by_type():
    rows = _rows([("unrelated", None, 0.70), ("agree", None, 0.70), ("unrelated", None, 0.70)])
    kinds = ("museum:works+year", "museum:works+year", "bridge:length+year")
    for row, kind in zip(rows, kinds, strict=True):
        row["type"] = kind
    assert run.by_type(rows, 0.65) == {
        "museum:works+year": {"added": 2, "wrong": 1},
        "bridge:length+year": {"added": 1, "wrong": 0},
    }
    attrs = {c["attributes"] for c in cases.build() if c["shape"] == "same"}
    assert all(a.count("+") == 1 and len(set(a.split("+"))) == 2 for a in attrs)


def test_the_target_is_compared_unrounded():
    # 60 of 67: Wilson lower bound 0.7997, which rounds to 0.800 at three decimals
    rows = _rows([("unrelated", None, 0.70)] * 60 + [("agree", None, 0.70)] * 7)
    assert round(run.wilson_lower(60, 67), 3) == 0.8 > run.wilson_lower(60, 67)
    assert run.verdict(rows, 0.65)["verdict"] == "the gate does not beat the shipped policy"


def test_the_registered_power_is_what_the_batch_gives():
    (low, mid, high) = run.power_table(560)  # the same-entity pairs only: the conservative count
    assert (low["band"], mid["band"], high["band"]) == (0.08, 0.10, 0.125)
    assert high["added_expected"] == 70.0 and high["p_undecided"] == 0.0
    assert high["p_beats_at_0.93"] >= 0.85 and high["p_beats_at_0.80"] <= 0.02
    assert low["p_beats_at_0.93"] < mid["p_beats_at_0.93"] < high["p_beats_at_0.93"]
    assert run.power_table(200)[2]["p_beats_at_0.93"] < 0.35  # the first draft: a coin flip


class OneCase:
    name = "one"

    async def decide(self, point, state, questions):
        return Decision(point, {}, "one", "-")


def test_an_unanswered_case_is_undecided_under_every_policy_when_allowed():
    case = {"id": "x", "expected": "unrelated", "input": {"fact_a": "A.", "fact_b": "B."}}
    with pytest.raises(SystemExit):
        asyncio.run(run.answered([case], OneCase(), "t"))
    (row,) = asyncio.run(run.answered([case], OneCase(), "t", allow_missing=True))
    assert row["unanswered"] and row["shipped"] is None
    assert all(row[f"g{g:.2f}"] is None for g in run.GATES)


# --- paid_once ----------------------------------------------------------------------------


def _lot(tmp_path, **kw):
    tmp_path.mkdir(parents=True, exist_ok=True)
    prereg = tmp_path / "prereg.md"
    if not prereg.exists():
        prereg.write_text("rule\n", encoding="utf-8")
    launcher = tmp_path / "x-run.cmd"
    if not launcher.exists():
        launcher.write_text('@echo off\nset "PY=<PYTHON>"\nset "SANCHOPANZA_KEYS_ENV=<K>"\n')
    base = dict(
        name="t", prereg=prereg, launcher=launcher, fixture=tmp_path / "f" / "rec.jsonl",
        model="jev-1.13.0", cap_usd=0.01, instrument=("src",), home=tmp_path / "home",
    )  # fmt: skip
    return paid_once.Lot(**{**base, **kw})


class Live:
    name = "live"

    def __init__(self, fail_at=None, model="jev-1.13.0"):
        self.calls = 0
        self.fail_at = fail_at
        self.model = model

    async def decide(self, point, state, questions):
        self.calls += 1
        if self.fail_at is not None and self.calls >= self.fail_at:
            return Decision(point, {}, "live", "-", error="HTTP 500")
        answers = {k: Answer("choice", 0.9, choice="agree") for k in questions}
        return Decision(point, answers, "live", self.model, cost_usd=2e-5)


def _queries(n):
    return [run.query({"input": {"fact_a": f"A {i}.", "fact_b": f"B {i}."}}) for i in range(n)]


def test_plan_prices_what_is_missing_and_ask_missing_asks_it_once(tmp_path):
    lot = _lot(tmp_path)
    asks = _queries(3)
    plan = paid_once.plan(asks, lot)
    assert (plan["to_ask"], plan["usd_at_median_request"]) == (3, round(3 * 71e-6, 6))
    assert plan["ledger"] == str(tmp_path / "home" / "t" / "ledger.jsonl")
    live = Live()
    got = asyncio.run(paid_once.ask_missing(asks, lot, live=live))
    assert got["stopped"] is None and live.calls == 3
    assert paid_once.plan(asks, lot)["to_ask"] == 0  # a relaunch asks nothing
    asyncio.run(paid_once.ask_missing(asks, lot, live=live))
    assert live.calls == 3


def test_ask_missing_stops_at_a_failure_the_cap_and_another_model(tmp_path):
    live = Live(fail_at=2)
    got = asyncio.run(paid_once.ask_missing(_queries(5), _lot(tmp_path / "a"), live=live))
    assert got["stop_kind"] == "failure" and live.calls == 2
    capped = Live()
    got = asyncio.run(
        paid_once.ask_missing(_queries(5), _lot(tmp_path / "b", cap_usd=1e-9), live=capped)
    )
    assert got["stop_kind"] == "cap" and capped.calls == 0
    moved = Live(model="jev-1.14.0")
    got = asyncio.run(paid_once.ask_missing(_queries(5), _lot(tmp_path / "c"), live=moved))
    assert got["stop_kind"] == "model" and moved.calls == 1


class LoopBound:
    """A client that, like httpx's, belongs to the loop it was made in."""

    name = "bound"
    made: list = []

    def __init__(self):
        self.loop = asyncio.get_running_loop()  # raises outside a running loop
        self.closed = False
        LoopBound.made.append(self)

    async def decide(self, point, state, questions):
        if asyncio.get_running_loop() is not self.loop or self.closed:
            raise RuntimeError("Event loop is closed")
        answers = {k: Answer("choice", 0.9, choice="agree") for k in questions}
        return Decision(point, answers, "bound", "jev-1.13.0", cost_usd=2e-5)

    async def aclose(self):
        self.closed = True


def test_the_live_part_runs_in_one_loop_with_a_client_made_in_it(tmp_path):
    seen = []

    async def check(model):
        seen.append(asyncio.get_running_loop())

    LoopBound.made.clear()
    got = asyncio.run(
        paid_once.session(
            _queries(4), _lot(tmp_path), make_live=LoopBound, check=check,
            on_start=lambda: seen.append("start"),
        )
    )  # fmt: skip
    assert got["stopped"] is None and got["asked"] == 4
    (client,) = LoopBound.made
    assert seen == [client.loop, "start"] and client.closed
    # the defect this guards against: a client made in one loop, used in a second one
    with pytest.raises(RuntimeError):
        LoopBound()  # no running loop: it cannot be made outside one
    stale = client
    other = asyncio.run(paid_once.ask_missing(_queries(1), _lot(tmp_path / "z"), live=stale))
    assert other["stop_kind"] == "failure" and "Event loop is closed" in other["stopped"]


def test_the_launch_rule_allows_one_relaunch_never_after_a_stop(tmp_path):
    lot = _lot(tmp_path)
    assert paid_once.may_launch(paid_once.history(lot))
    paid_once._note(lot, {"event": "start", "head": "h"})
    assert paid_once.history(lot)[0]["stop_kind"] == "unfinished"  # killed: one more allowed
    assert paid_once.may_launch(paid_once.history(lot))
    paid_once._note(lot, {"event": "end", "stop_kind": "failure"})
    assert paid_once.may_launch(paid_once.history(lot))
    paid_once._note(lot, {"event": "start"})
    paid_once._note(lot, {"event": "end", "stop_kind": None})
    assert not paid_once.may_launch(paid_once.history(lot))  # two launches: none left
    for kind in ("funds", "limit", "cap"):
        assert not paid_once.may_launch([{"stop_kind": kind}])
    assert paid_once.stop_kind("JevError: HTTP 402 payment required") == "funds"
    assert paid_once.stop_kind("JevError: HTTP 429") == "limit"


def test_a_report_waits_for_the_relaunch_then_counts_what_is_missing(tmp_path):
    lot = _lot(tmp_path)
    assert not paid_once.unanswered_blocks(lot, 0)
    assert paid_once.unanswered_blocks(lot, 3)  # nothing launched yet
    paid_once._note(lot, {"event": "start"})
    paid_once._note(lot, {"event": "end", "stop_kind": "funds"})
    assert not paid_once.unanswered_blocks(lot, 3)  # no relaunch after a 402: scored as missing


def _named(lot):
    """The prereg names the current HEAD as its instrument commit."""
    lot.prereg.write_text(f"rule\nInstrument commit: `{paid_once.head()}`\n", encoding="utf-8")
    return lot


def test_the_seal_covers_prereg_and_launcher_but_not_its_local_values(tmp_path):
    lot = _lot(tmp_path)
    with pytest.raises(SystemExit, match="names no instrument commit"):
        paid_once.seal(lot)
    _named(lot)
    first = paid_once.seal(lot)
    assert paid_once.seal(lot) == first
    paid_once.require_sealed(lot)
    filled = lot.launcher.read_text().replace("<PYTHON>", "D:/py.exe").replace("<K>", "D:/k")
    lot.launcher.write_text(filled)
    paid_once.require_sealed(lot)  # filling the two local values keeps the seal
    lot.launcher.write_text(filled + "echo more\n")
    with pytest.raises(SystemExit):
        paid_once.require_sealed(lot)
    with pytest.raises(SystemExit):
        paid_once.seal(lot)  # never overwritten
    lot.launcher.write_text(filled)
    lot.prereg.write_text("rule, edited after the seal\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        paid_once.require_sealed(lot)


class Trap:
    """Stands for the key loader and the live client: any call is recorded."""

    def __init__(self):
        self.calls = []

    def load_key(self):
        self.calls.append("load_key")

    def make_live(self):
        self.calls.append("make_live")
        return LoopBound()

    async def check(self, model):
        self.calls.append("check")


def _paid(lot, trap, n=3):
    return paid_once.run_paid(
        lot, _queries(n), load_key=trap.load_key, make_live=trap.make_live, check=trap.check
    )


def test_no_key_and_no_client_before_every_check_passes(tmp_path, capsys):
    stable = ("LICENSE",)  # an instrument path no test run changes
    trap = Trap()
    lot = _lot(tmp_path / "a", instrument=stable)
    with pytest.raises(SystemExit, match="not sealed"):
        _paid(lot, trap)  # never sealed
    paid_once.seal(_named(lot))
    lot.prereg.write_text(lot.prereg.read_text() + "edited\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not sealed"):
        _paid(lot, trap)  # sealed, then changed
    other = tmp_path / "input.bin"
    other.write_bytes(b"x")
    lot = _lot(tmp_path / "b", instrument=stable, inputs=((other, "0" * 64),))
    paid_once.seal(_named(lot))
    with pytest.raises(SystemExit, match="registered input"):
        _paid(lot, trap)  # sealed, but another input hash
    lot = _lot(tmp_path / "c", instrument=stable)
    paid_once.seal(_named(lot))
    lot.fixture.parent.mkdir(parents=True)
    line = {"key": "k", "point": "facts", "model": "jev-1.14.0", "answers": {}}
    lot.fixture.write_text(json.dumps(line) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="first launch"):
        _paid(lot, trap)  # a recording already there before any launch
    lot = _lot(tmp_path / "d", instrument=stable, cap_usd=0.0002)
    paid_once.seal(_named(lot))
    with pytest.raises(SystemExit, match="does not fit"):
        _paid(lot, trap, n=5)  # 5 x 71 micro-USD over the cap
    assert trap.calls == []


def test_a_sealed_lot_asks_once_in_one_loop_and_the_relaunch_rule_holds(tmp_path, capsys):
    trap = Trap()
    lot = _lot(tmp_path, instrument=("LICENSE",))
    paid_once.seal(_named(lot))
    LoopBound.made.clear()
    got = _paid(lot, trap)
    assert got["stopped"] is None and got["asked"] == 3
    assert trap.calls == ["load_key", "check", "make_live"]
    assert paid_once.plan(_queries(3), lot)["to_ask"] == 0
    assert _paid(lot, trap)["note"] == "nothing missing"  # nothing asked, nothing launched
    assert len(paid_once.history(lot)) == 1


def test_another_models_answer_never_counts_as_recorded(tmp_path):
    lot = _lot(tmp_path)
    asyncio.run(paid_once.ask_missing(_queries(2), lot, live=Live(model="jev-1.14.0")))
    assert lot.fixture.exists()  # written by the recorder before the model was checked
    assert paid_once.plan(_queries(2), lot)["to_ask"] == 2


def test_a_relaunch_counts_what_the_ledger_already_holds(tmp_path):
    lot = _lot(tmp_path, cap_usd=0.00016)
    asyncio.run(paid_once.ask_missing(_queries(1), lot, live=Live()))
    plan = paid_once.plan(_queries(3), lot)  # 2 left: 142 micro-USD, under the cap alone
    assert plan["usd_spent_on_ledger"] > 0 and plan["usd_at_median_request"] < lot.cap_usd
    with pytest.raises(SystemExit, match="spent \\+ estimate"):
        paid_once.require_room(plan, lot.cap_usd)


def test_load_key_reads_only_the_named_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("SANCHOPANZA_KEYS_ENV", raising=False)
    with pytest.raises(SystemExit):
        paid_once.load_key()
    env = tmp_path / "keys.env"
    env.write_text('OTHER=1\nTYPESAFE_API_KEY="fake-for-test"\n', encoding="utf-8")
    monkeypatch.setenv("SANCHOPANZA_KEYS_ENV", str(env))
    paid_once.load_key()
    assert paid_once.os.environ["TYPESAFE_API_KEY"] == "fake-for-test"


def test_the_instrument_and_the_inputs_are_checked_before_any_key(tmp_path):
    lot = _lot(tmp_path)
    with pytest.raises(SystemExit, match="no instrument commit"):
        paid_once.require_instrument(lot)
    lot.prereg.write_text("Instrument commit: `" + "0" * 40 + "`\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="does not descend"):
        paid_once.require_instrument(lot)
    data = tmp_path / "input.bin"
    data.write_bytes(b"x\r\n")
    paid_once.require_inputs(_lot(tmp_path, inputs=((data, paid_once.raw_digest(data)),)))
    with pytest.raises(SystemExit):
        paid_once.require_inputs(_lot(tmp_path, inputs=((data, "0" * 64),)))
    paid_once.require_file(run.CASES, run.CASES_SHA256)
    with pytest.raises(SystemExit):
        paid_once.require_file(data, run.CASES_SHA256)


def test_a_run_needs_room_under_the_cap():
    with pytest.raises(SystemExit):
        paid_once.require_room(
            {"usd_at_median_request": 0.2, "usd_estimate_capped_decider": 0.01}, 0.1
        )


def test_both_launchers_are_tracked_without_local_values():
    for name in ("a5-unrelated-run.cmd", "b4-order-run.cmd"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert 'set "PY=<PYTHON>"' in text and 'set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"' in text
        assert "C:\\Users" not in text and "C:/" not in text


# --- the recorded derivation --------------------------------------------------------------


def test_the_recorded_free_derivation_is_the_published_one():
    path = ROOT / "docs" / "results" / "2026-10-16-a5-unrelated" / "free.json"
    if not path.exists():
        pytest.skip("free.json not written")
    got = asyncio.run(run.free())
    assert json.loads(json.dumps(got)) == json.loads(path.read_text("utf-8"))
    assert got["derived_gate"] == run.GATE_UNDER_TEST == 0.65
