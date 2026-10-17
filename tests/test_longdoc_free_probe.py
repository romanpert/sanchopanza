"""The BM25 prefilter's paid probe (benchmarks/longdoc_free/jev_phase.py, phase "probe"): its own
lot, its fixed ids and K, one launch, the cap enforced by the ledger, the rehearsal of the paid
path with a costed stub in place of Jev, the replay and the decision rule. No network, no key."""

from __future__ import annotations

import asyncio
import dataclasses
import gzip
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


jp = _load("lf_jev_phase", "benchmarks/longdoc_free/jev_phase.py")
dry = _load("lf_bm25_dry", "benchmarks/longdoc_free/bm25_dry.py")
br = jp.br
from sanchopanza.contract import Decision  # noqa: E402
from sanchopanza.providers.capped import estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402


def _benchmarks_off_the_path() -> None:
    """As test_longdoc_free_jev: benchmarks/ off sys.path between tests (agentdojo's skip)."""
    for entry in (str(ROOT / "benchmarks"), str(ROOT / "benchmarks" / "b6_es")):
        while entry in sys.path:
            sys.path.remove(entry)


_benchmarks_off_the_path()


@pytest.fixture(autouse=True)
def _benchmarks_on_the_path_while_testing(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks"))
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks" / "b6_es"))


def _rows() -> list[dict]:
    words = ["meadow", "river", "letter", "carriage", "garden", "ball", "rain", "church"]
    paragraphs = [
        f"Part {i}. Emma saw the {words[i % 8]} near Hartfield and spoke of the {words[i % 5]} "
        f"for a while. " * 6
        for i in range(300)
    ]
    paragraphs[57] = "Harriet sang an old ballad at the harvest supper in Donwell Abbey."
    novel = jp.pages.pages_of("\n\n".join(paragraphs))
    return [{"id": i, "novel": "n0", "question": q, "answers": ["Donwell Abbey"], "pages": novel}
            for i, q in ((0, "Where did Harriet sing the ballad?"),
                         (7, "What did Emma see near Hartfield?"))]  # fmt: skip


# ---- the lot -----------------------------------------------------------------------------------


def test_the_probes_ledger_cap_and_its_worst_overshoot_stay_within_the_owners_ten_cents():
    cap = jp.CAP_USD["probe"]
    assert cap == 0.06 and jp.PROBE_IN_FLIGHT == br.CONCURRENCY == 4
    worst = cap + jp.PROBE_IN_FLIGHT * jp.PROBE_MAX_BILL_USD + jp.PROBE_PREFLIGHT_USD
    assert worst <= jp.PROBE_HARD_CAP_USD == 0.10
    assert worst == pytest.approx(0.0626, abs=5e-5)


def test_the_cap_sits_above_the_plan_and_above_any_spend_that_already_decides_no():
    probe_read = _probe_read()
    assert pytest.approx(3 * probe_read.RULE_MEAN_USD) == probe_read.RULE_TOTAL_USD
    # a cap stop leaves settled bills over the rule's total: the cap less one call's
    # reservation and the reservations still open (4 in flight, each under 0.001)
    assert jp.CAP_USD["probe"] - 5 * 0.001 > probe_read.RULE_TOTAL_USD
    assert jp.CAP_USD["probe"] >= 0.0385 + 0.02  # the plan fits with margin


def test_the_probes_constants_are_the_dev_and_the_dry_measurement_s():
    import gzip
    import json as _json

    with gzip.open(ROOT / "fixtures/longdoc-free/jev-dev.jsonl.gz", "rt", encoding="utf-8") as fh:
        bills = [float(_json.loads(x)["cost_usd"]) for x in fh if x.strip()]
    assert max(bills) <= jp.PROBE_MAX_BILL_USD  # a call overshoots its reservation by < its bill
    measured = _json.loads((jp.PROBE_DIR / "bm25-dry.json").read_text("utf-8"))
    assert measured["ratio_real_over_stub"]["pooled"] == jp.PROBE_STUB_RATIO
    at_k = next(k for k in measured["by_k"] if k["k"] == jp.PROBE_K)["jev_usd_oracle_by_id"]
    assert pytest.approx(sum(at_k[str(i)] for i in jp.PROBE_IDS)) == jp.PROBE_ORACLE_USD


def test_the_probes_room_check_takes_the_larger_of_the_corrected_stub_and_the_oracle(
    monkeypatch,
):
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: _stub_asker())
    got = jp.dry("probe", _rows())
    corrected = got["pessimistic_usd"] * jp.PROBE_STUB_RATIO
    assert got["planned_usd"] == round(max(corrected, jp.PROBE_ORACLE_USD), 4)
    assert got["fits_under_cap"] == (got["planned_usd"] <= jp.CAP_USD["probe"])
    assert "planned_usd" not in jp.dry("dev", _rows())  # the sealed phases' plan, unchanged


def test_the_probe_is_its_own_lot_capped_under_ten_cents():
    probe, dev = jp.lot("probe"), jp.lot("dev")
    assert probe.name == "longdoc-free-bm25-probe" and probe.cap_usd == 0.06
    assert probe.prereg.name == "prereg-probe.md"
    assert probe.prereg.parent.name == "2026-10-17-lfree-bm25-dry"
    assert probe.fixture.name == "jev-probe.jsonl"
    assert len({probe.fixture, dev.fixture, jp.lot("confirm").fixture}) == 3
    assert probe.run_dir != dev.run_dir and probe.ledger != dev.ledger
    assert probe.launcher == dev.launcher  # one launcher, one mode a phase
    assert probe.model == "jev-1.13.0"


def test_the_probes_ids_and_k_are_fixed_in_code_and_only_the_probe_has_a_prefilter():
    assert jp.PROBE_IDS == (0, 7, 375) and jp.PROBE_K == 200
    assert jp.prefilter_for("probe") == 200
    assert jp.prefilter_for("dev") is None and jp.prefilter_for("confirm") is None
    assert set(jp.PROBE_IDS) <= set(jp.pool.phase_ids(jp.pool.read_frozen(), "dev"))
    assert jp.phase_ids("probe") == set(jp.PROBE_IDS)


@pytest.mark.parametrize("argv", [
    ["paid", "--phase", "dev", "--prefilter-k", "5"],
    ["paid", "--phase", "probe", "--prefilter-k", "200"],
    ["rows", "--phase", "probe", "--prefilter-k", "200"],
    ["dry", "--phase", "probe", "--prefilter-k", "100"],
])  # fmt: skip
def test_the_cli_takes_no_prefilter_for_a_paid_path_nor_another_k_for_the_probe(argv):
    with pytest.raises(SystemExit) as stop:
        jp.main(argv)
    assert stop.value.code == 2  # argparse's refusal, before anything is read


def test_the_dry_run_refuses_another_k_for_the_probe(monkeypatch):
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: _stub_asker())
    with pytest.raises(ValueError, match="fixed"):
        jp.dry("probe", _rows(), prefilter_k=100)
    got = jp.dry("probe", _rows())
    assert got["prefilter_k"] == 200 and got["cap_usd"] == 0.06


def test_the_probe_launches_once_and_never_again():
    assert jp.may_launch("probe", [])
    for stop in ("failure", "busy", "done", "cap", "funds"):
        assert not jp.may_launch("probe", [{"event": "start", "stop_kind": stop}])


# ---- the paid path, rehearsed with a costed stub in place of Jev -------------------------------


def _stub_asker() -> br.Asker:
    return br.Asker(br.Stub(), recorded=RecordedDecider([]), memo_failures=True, model_halts=True)


class CostedStub(br.Stub):
    """The dry stub, billed 80 % of each call's estimate, as Jev is (0.77-0.89 on the dev)."""

    async def decide(self, point, state, questions):
        got = await super().decide(point, state, questions)
        bill = 0.8 * estimate_usd(state, questions, price_per_mtok=0.042)
        return dataclasses.replace(got, cost_usd=bill, input_tokens=100)


@pytest.fixture()
def rehearsal(monkeypatch, tmp_path: Path):
    """The probe's lot in tmp_path, every seal and instrument check passed, the preflight and
    the key no-ops, and a costed stub where the live Jev client would be."""
    real_lot = jp.lot

    def lot(phase: str):
        found = real_lot(phase)
        if phase != "probe":
            return found
        return dataclasses.replace(found, fixture=tmp_path / "jev-probe.jsonl",
                                   home=tmp_path / "home")  # fmt: skip

    monkeypatch.setattr(jp, "lot", lot)
    monkeypatch.setattr(jp, "load_rows", lambda phase: _rows())
    monkeypatch.setattr(jp, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(jp, "PROBE_DIR", tmp_path / "results")
    (tmp_path / "results").mkdir()
    for name in ("require_sealed", "require_inputs"):
        monkeypatch.setattr(jp.paid_once, name, lambda the_lot: None)
    monkeypatch.setattr(jp.paid_once, "require_instrument", lambda the_lot: "c" * 40)

    async def preflight(model: str) -> None:
        return None

    def paid(**overrides):
        args = {"load_key": lambda: None, "check": preflight,
                "build_live": lambda the_lot: jp.make_live(the_lot, inner=CostedStub()),
                "sealed_head": lambda the_lot: []} | overrides  # fmt: skip
        return jp.paid("probe", jp.lot("probe").launcher, **args)

    return paid


def test_the_rehearsal_records_every_call_under_the_cap_then_replays_free(rehearsal):
    assert rehearsal() == 0
    the_lot = jp.lot("probe")
    spent = jp.paid_once.spent(the_lot)
    assert 0 < spent <= the_lot.cap_usd
    assert the_lot.fixture.stat().st_size > 0
    assert jp.paid_once.history(the_lot)[0]["plan"]["planned_usd"] >= jp.PROBE_ORACLE_USD
    history = jp.paid_once.history(the_lot)
    assert len(history) == 1 and history[0]["stop_kind"] is None
    assert history[0]["plan"]["prefilter_k"] == 200
    out = jp.replay("probe")  # the recording alone, no live decider
    assert [r["id"] for r in out] == [0, 7] and all(r["p"] is not None for r in out)
    assert (jp.PROBE_DIR / "jev-probe.jsonl").exists()
    assert _probe_read().launched_cleanly(the_lot)[0] is True
    with pytest.raises(SystemExit, match="launch rule"):
        rehearsal()  # a second launch, whatever the first did


def test_the_recording_is_read_gzipped_when_only_the_gz_is_there(rehearsal):
    assert rehearsal() == 0
    the_lot = jp.lot("probe")
    plain = jp.replay("probe")
    gz = the_lot.fixture.with_name(the_lot.fixture.name + ".gz")
    assert jp.recording_path(the_lot) == the_lot.fixture  # the plain file first
    with gzip.open(gz, "wb") as out:
        out.write(the_lot.fixture.read_bytes())
    the_lot.fixture.unlink()
    assert jp.recording_path(the_lot) == gz
    assert jp.replay("probe") == plain  # the same rows from the .gz
    lines = _probe_read().recorded_lines(the_lot)
    assert lines and all(x["model"] == jp.MODEL for x in lines)


def test_the_recording_path_is_the_plain_file_when_neither_exists(tmp_path: Path):
    the_lot = dataclasses.replace(jp.lot("probe"), fixture=tmp_path / "jev-probe.jsonl")
    assert jp.recording_path(the_lot) == the_lot.fixture
    assert jp.recorded(the_lot).decide is not None  # an empty recording, as paid_once's


def test_a_first_launch_is_refused_when_only_a_gzipped_recording_exists(rehearsal):
    the_lot = jp.lot("probe")
    gz = the_lot.fixture.with_name(the_lot.fixture.name + ".gz")
    with gzip.open(gz, "wt", encoding="utf-8") as out:
        out.write('{"key": "k", "model": "jev-1.13.0", "answers": {}}\n')
    with pytest.raises(SystemExit, match="holds answers"):
        rehearsal(load_key=lambda: pytest.fail("the key was read"))


def test_a_probe_is_refused_once_anything_was_spent_even_without_a_launch(rehearsal):
    the_lot = jp.lot("probe")
    ledger = jp.paid_once.ledger_of(the_lot)
    the_lot.ledger.parent.mkdir(parents=True, exist_ok=True)
    assert ledger.reserve(0.001, batch=the_lot.name, batch_cap_usd=the_lot.cap_usd) is not None
    with pytest.raises(SystemExit, match="already spent"):
        rehearsal(load_key=lambda: pytest.fail("the key was read"))


def test_the_ledger_stops_the_probe_at_its_cap(rehearsal, monkeypatch):
    real_dry = jp.dry

    def optimistic(phase, rows=None, prefilter_k=None):  # a plan that fits: the cap must hold
        return real_dry(phase, rows, prefilter_k) | {"pessimistic_usd": 0.0, "planned_usd": 0.0}

    monkeypatch.setattr(jp, "dry", optimistic)
    monkeypatch.setattr(jp, "CAP_USD", {**jp.CAP_USD, "probe": 0.004})
    assert rehearsal() == 2
    the_lot = jp.lot("probe")
    assert the_lot.cap_usd == 0.004 and jp.paid_once.spent(the_lot) <= 0.004
    assert jp.paid_once.history(the_lot)[0]["stop_kind"] == "cap"
    assert _probe_read().launched_cleanly(the_lot)[0] is False  # the rule reads "not run"


# ---- the reading -------------------------------------------------------------------------------


def _q(usd: float, complete: bool = True) -> dict:
    return {"real_usd": usd, "complete": complete}


def _probe_read():
    return _load("lf_probe_read", "benchmarks/longdoc_free/probe_read.py")


def test_the_sealed_rule_reads_the_mean_and_the_dearest_question():
    verdict = _probe_read().probe_verdict
    assert verdict([_q(0.010), _q(0.015), _q(0.020)], ran=True)["prepare_new_dev"] is True
    assert verdict([_q(0.010), _q(0.012), _q(0.0311)], ran=True)["prepare_new_dev"] is False
    assert verdict([_q(0.016), _q(0.016), _q(0.016)], ran=True)["prepare_new_dev"] is False
    not_run = verdict([_q(0.001)] * 3, ran=False)
    assert not_run["prepare_new_dev"] is None and not_run["status"] == "not run"


@pytest.mark.parametrize(("questions", "settled", "stop", "decided"), [
    ([_q(0.001, False)] * 3, 0.059, "cap", True),       # the cap: over the rule's total
    ([_q(0.001, False)] * 3, 0.0451, "funds", True),    # settled past 0.045, then a 402
    ([_q(0.0311), _q(0.0, False), _q(0.0, False)], 0.0311, "failure", True),  # one over 0.031
    # a question's bills only add up: past 0.031 before it completed, it is past 0.031
    ([_q(0.0311, False), _q(0.0, False), _q(0.0, False)], 0.0311, "failure", True),
    ([_q(0.031, False), _q(0.0, False), _q(0.0, False)], 0.031, "failure", False),
    ([_q(0.010), _q(0.0, False), _q(0.0, False)], 0.010, "limit", False),
    ([_q(0.0, False)] * 3, 0.0, "unfinished", False),
])  # fmt: skip
def test_a_stopped_probe_is_decided_by_spend_only_when_the_rule_already_says_no(
    questions, settled, stop, decided
):
    got = _probe_read().probe_verdict(questions, ran=False, settled_usd=settled, stop_kind=stop)
    if decided:
        assert got["prepare_new_dev"] is False and got["status"] == "decided by spend"
    else:
        assert got["prepare_new_dev"] is None and got["status"] == "not run"


def test_a_not_run_report_counts_only_answered_calls():
    counting = dry.Counting(RecordedDecider([]), answered_only=True)
    asker = dry.asker_over(None, counting)
    dry.run(_rows()[:1], asker, 20)
    assert asker.failed_keys and counting.by_row.get("0", {}).get("calls_triage_pages", 0) == 0
    attempted = dry.Counting(RecordedDecider([]))
    dry.run(_rows()[:1], dry.asker_over(None, attempted), 20)
    assert attempted.by_row["0"]["calls_triage_pages"] > 0  # the dry measurement's default


# ---- the launcher ------------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="runs the launcher in cmd.exe")
@pytest.mark.parametrize(("phase", "refusal"), [("probe", "refused: "), ("other", "the phase")])
def test_the_launcher_takes_the_probe_and_still_refuses_unset_values(phase, refusal, tmp_path):
    copy = tmp_path / "longdoc-free-jev-run.cmd"
    copy.write_bytes((ROOT / "longdoc-free-jev-run.cmd").read_bytes())
    env = {k: v for k, v in os.environ.items() if k != "SANCHOPANZA_KEYS_ENV"}
    got = subprocess.run(["cmd.exe", "/c", str(copy), phase], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=60)  # fmt: skip
    assert got.returncode == 1 and refusal in got.stdout
    if phase == "probe":
        assert "the first argument" not in got.stdout
    assert not (tmp_path / "benchmarks").exists()


def test_the_launcher_is_checked_out_with_crlf_and_names_the_probes_folder():
    raw = (ROOT / "longdoc-free-jev-run.cmd").read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") > 0
    text = raw.decode("utf-8")
    assert '"%PHASE%"=="probe"' in text and "longdoc-free-bm25-probe" in text
    assert 'set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"' in text  # never a path in the tracked file


def test_the_seal_is_written_only_with_a_named_instrument_commit(monkeypatch, tmp_path: Path):
    prereg = tmp_path / "prereg-probe.md"
    prereg.write_text("No commit named yet.\n", encoding="utf-8")
    monkeypatch.setattr(jp, "lot", lambda phase: dataclasses.replace(
        jp.paid_once.Lot(name="x", prereg=prereg, launcher=ROOT / "longdoc-free-jev-run.cmd",
                         fixture=tmp_path / "f.jsonl", model=jp.MODEL, cap_usd=0.10,
                         instrument=jp.INSTRUMENT)))  # fmt: skip
    with pytest.raises(SystemExit, match="no instrument commit"):
        jp.main(["seal", "--phase", "probe"])
    prereg.write_text("Instrument commit: `" + "a" * 40 + "`\n", encoding="utf-8")
    assert jp.main(["seal", "--phase", "probe"]) == 0
    sealed = (tmp_path / "prereg-probe.sha256").read_text("utf-8").splitlines()
    assert [line.split("  ")[1] for line in sealed] == ["prereg-probe.md",
                                                        "longdoc-free-jev-run.cmd"]  # fmt: skip


def test_the_probe_replay_refuses_an_incomplete_recording(monkeypatch):
    monkeypatch.setattr(jp, "load_rows", lambda phase: _rows())
    no_live = br.Asker(None, recorded=RecordedDecider([]), memo_failures=True, model_halts=True)
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: no_live)
    with pytest.raises(SystemExit, match="not recorded"):
        jp.replay("probe")


def test_a_costed_stub_answers_like_the_stub():
    got = asyncio.run(CostedStub().decide("gate", {"a": "b"}, {"enough": jp.GATE}))
    assert isinstance(got, Decision) and got.cost_usd > 0 and got.model == jp.MODEL
