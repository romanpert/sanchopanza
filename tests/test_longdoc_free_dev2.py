"""Lot longdoc-free's dev2 (docs/results/2026-10-17-lfree-dev2/prereg-dev2.md): phase J2 of
jev_phase.py (the BM25 prefilter at the probe's K on the 41 dev questions, its own lot, one
launch), stage dev2 of h2h_lfree.py (smoke, N again, then H alone) and dev2_read.py (the sealed
dev's rules on dev2's N and H, the dev's H0 and HC reused, N's rerun described). No network,
no key, no session."""

from __future__ import annotations

import asyncio
import dataclasses
import gzip
import hashlib
import importlib.util
import json
import os
import statistics
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
h2h = _load("lf_h2h", "benchmarks/h2h/h2h_lfree.py")
dr = _load("lf_dev_read", "benchmarks/longdoc_free/dev_read.py")
d2 = _load("lf_dev2_read", "benchmarks/longdoc_free/dev2_read.py")
br = jp.br
from sanchopanza.providers.capped import estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402


def _benchmarks_off_the_path() -> None:
    """As test_longdoc_free_jev: benchmarks/ off sys.path between tests (agentdojo's skip)."""
    for entry in (str(ROOT / "benchmarks"), str(ROOT / "benchmarks" / "b6_es")):
        while entry in sys.path:
            sys.path.remove(entry)


_benchmarks_off_the_path()
CACHED = jp.pool.RAW.exists() and jp.pool.IDS_FILE.exists()
DEV = ROOT / "docs/results/2026-10-16-longdoc-free"
PROBE_READ = json.loads((jp.PROBE_DIR / "probe-read.json").read_text("utf-8"))


@pytest.fixture(autouse=True)
def _benchmarks_on_the_path_while_testing(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks"))
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks" / "b6_es"))


def _novel(paragraphs: int = 300, at: int = 57) -> list:
    words = ["meadow", "river", "letter", "carriage", "garden", "ball", "rain", "church"]
    text = [
        f"Part {i}. Emma saw the {words[i % 8]} near Hartfield and spoke of the {words[i % 5]} "
        f"for a while. " * 6
        for i in range(paragraphs)
    ]
    text[at] = "Harriet sang an old ballad at the harvest supper in Donwell Abbey."
    return jp.pages.pages_of("\n\n".join(text))


def _rows(novel: list | None = None) -> list[dict]:
    novel = novel or _novel()
    return [{"id": i, "novel": "n0", "question": q, "answers": ["Donwell Abbey"], "pages": novel}
            for i, q in enumerate(("Where did Harriet sing the ballad?",
                                   "What did Emma see near Hartfield?"))]  # fmt: skip


def _stub_asker() -> br.Asker:
    return br.Asker(br.Stub(), recorded=RecordedDecider([]), memo_failures=True, model_halts=True)


# ---- phase J2: the lot, its K, its money -------------------------------------------------------


def test_dev2_is_its_own_lot_with_the_probes_launcher_and_model():
    dev2 = jp.lot("dev2")
    others = [jp.lot(p) for p in ("dev", "confirm", "probe")]
    assert dev2.name == "longdoc-free-dev2" and dev2.cap_usd == 1.00
    assert dev2.prereg == ROOT / "docs/results/2026-10-17-lfree-dev2/prereg-dev2.md"
    assert dev2.fixture.name == "jev-dev2.jsonl"
    assert all(dev2.fixture != o.fixture and dev2.ledger != o.ledger for o in others)
    assert dev2.launcher == others[0].launcher and dev2.model == "jev-1.13.0"
    assert set(jp.DEV_ROWS) <= set(dev2.instrument)  # the reused rows are bound
    assert all(set(o.instrument) == set(jp.INSTRUMENT) for o in others)  # the others unchanged
    assert jp.passages_path("dev2", 7) == jp.PRIVATE / "dev2" / "passages" / "7.txt"
    assert jp.results_dir("dev2") == jp.DEV2_DIR and jp.results_dir("dev") == jp.RESULTS


def test_dev2s_worst_total_and_the_lots_jev_stay_within_the_owners_14_30():
    worst = jp.CAP_USD["dev2"] + jp.PROBE_IN_FLIGHT * jp.PROBE_MAX_BILL_USD + jp.PROBE_PREFLIGHT_USD
    assert worst == pytest.approx(1.0026, abs=5e-5)
    spent_before = 1.6072 + PROBE_READ["ledger_spent_usd"]  # the dev's and the probe's ledgers
    left = jp.JEV_LOT_USD - spent_before - worst
    assert left >= 11.6
    # what a confirmation with the prefilter would plan (the stub at K = 200 times the ratio)
    assert left >= d2.CONFIRM_STUB_PESSIMISTIC_USD * jp.PROBE_STUB_RATIO * dr.JEV_MARGIN


def test_the_cap_is_set_from_the_probes_real_cost_not_the_stub():
    real = [q["real_usd"] for q in PROBE_READ["questions"]]
    cap = jp.CAP_USD["dev2"]
    assert cap >= 41 * max(real)  # every question at the probe's dearest: 0.83
    assert cap >= 1.5 * 41 * statistics.fmean(real)  # 1.5 times the probe's mean: 0.71
    assert cap >= 2 * 0.492  # twice the dry run's plan (stub x 1.417), prereg section 3


def test_dev2_takes_the_probes_k_and_launches_once_only():
    assert jp.prefilter_for("dev2") == jp.PROBE_K == 200
    assert jp.prefilter_for("dev") is None and jp.prefilter_for("confirm") is None
    assert jp.may_launch("dev2", [])
    for stop in ("failure", "busy", "done", "cap", "funds", "unfinished"):
        assert not jp.may_launch("dev2", [{"event": "start", "stop_kind": stop}])


def test_the_dev2_oracle_is_the_dry_measurements_41_questions():
    measured = json.loads((jp.PROBE_DIR / "bm25-dry.json").read_text("utf-8"))
    at_k = next(k for k in measured["by_k"] if k["k"] == jp.PROBE_K)["jev_usd_oracle_by_id"]
    assert len(at_k) == 41
    assert sum(at_k.values()) == pytest.approx(jp.DEV2_ORACLE_USD, abs=5e-5)


# The K = 200 path's output and calls on a novel of 499 pages, taken from the code before dev2
# existed (main 61dbd2e, the probe's path): dev2 runs that path unchanged.
K200_DIGEST = "57e33209d0d1961587ff31db95fe50fb7da794f4b4012dc0b4ec9683e58d3f07"


def test_the_k200_path_is_the_probes_byte_for_byte():
    rows = _rows(_novel(500, 357))
    assert len(rows[0]["pages"]) == 499
    asker = _stub_asker()
    got = asyncio.run(jp.ask(rows, asker, jp.prefilter_for("dev2")))
    body = json.dumps({"got": got, "calls": asker.calls}, sort_keys=True)
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == K200_DIGEST


@pytest.mark.skipif(not CACHED, reason="∞Bench En.QA or its frozen ids not cached")
def test_dev2s_questions_are_the_devs():
    assert jp.phase_ids("dev2") == jp.phase_ids("dev") and len(jp.phase_ids("dev2")) == 41


@pytest.mark.parametrize("argv", [
    ["paid", "--phase", "dev2", "--prefilter-k", "200"],
    ["rows", "--phase", "dev2", "--prefilter-k", "200"],
    ["dry", "--phase", "dev2", "--prefilter-k", "100"],
])  # fmt: skip
def test_the_cli_takes_no_other_k_for_dev2(argv):
    with pytest.raises(SystemExit) as stop:
        jp.main(argv)
    assert stop.value.code == 2


def test_dev2s_plan_is_the_larger_of_the_corrected_stub_and_the_oracle(monkeypatch):
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: _stub_asker())
    with pytest.raises(ValueError, match="fixed"):
        jp.dry("dev2", _rows(), prefilter_k=100)
    got = jp.dry("dev2", _rows())
    corrected = got["pessimistic_usd"] * jp.PROBE_STUB_RATIO
    assert got["planned_usd"] == round(max(corrected, jp.DEV2_ORACLE_USD), 4)
    assert got["prefilter_k"] == 200 and got["cap_usd"] == 1.00
    assert got["fits_under_cap"] == (got["planned_usd"] <= 1.00)


# ---- phase J2's paid path, rehearsed with a costed stub in place of Jev ------------------------


class CostedStub(br.Stub):
    """The dry stub, billed 80 % of each call's estimate, as Jev is (0.77-0.89 on the dev)."""

    async def decide(self, point, state, questions):
        got = await super().decide(point, state, questions)
        bill = 0.8 * estimate_usd(state, questions, price_per_mtok=0.042)
        return dataclasses.replace(got, cost_usd=bill, input_tokens=100)


@pytest.fixture()
def rehearsal(monkeypatch, tmp_path: Path):
    real_lot = jp.lot

    def lot(phase: str):
        found = real_lot(phase)
        if phase != "dev2":
            return found
        return dataclasses.replace(found, fixture=tmp_path / "jev-dev2.jsonl",
                                   home=tmp_path / "home")  # fmt: skip

    monkeypatch.setattr(jp, "lot", lot)
    monkeypatch.setattr(jp, "load_rows", lambda phase: _rows())
    monkeypatch.setattr(jp, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(jp, "DEV2_DIR", tmp_path / "results")
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
        return jp.paid("dev2", jp.lot("dev2").launcher, **args)

    return paid


def test_the_rehearsal_records_under_the_cap_writes_dev2s_passages_and_never_relaunches(
    rehearsal, tmp_path
):
    assert rehearsal() == 0
    the_lot = jp.lot("dev2")
    assert 0 < jp.paid_once.spent(the_lot) <= the_lot.cap_usd
    history = jp.paid_once.history(the_lot)
    assert len(history) == 1 and history[0]["stop_kind"] is None
    assert history[0]["plan"]["prefilter_k"] == 200
    assert history[0]["plan"]["planned_usd"] >= jp.DEV2_ORACLE_USD
    out = jp.replay("dev2")
    assert [r["id"] for r in out] == [0, 1] and all(r["p"] is not None for r in out)
    assert (tmp_path / "results" / "jev-dev2.jsonl").exists()
    kept = (tmp_path / "private" / "dev2" / "passages" / "0.txt").read_text("utf-8")
    assert len(kept) == out[0]["kept_chars"]
    assert not (tmp_path / "private" / "dev").exists()  # the dev's passages are not touched
    got = d2.jev_by_question(the_lot, _rows(), jp.PROBE_K)
    assert got["complete"] and got["questions"] == 2 and 0 < got["mean_usd"] <= got["max_usd"]
    with pytest.raises(SystemExit, match="launch rule"):
        rehearsal()


def test_dev2_is_refused_once_anything_was_spent_or_recorded(rehearsal):
    the_lot = jp.lot("dev2")
    gz = the_lot.fixture.with_name(the_lot.fixture.name + ".gz")
    with gzip.open(gz, "wt", encoding="utf-8") as out:
        out.write('{"key": "k", "model": "jev-1.13.0", "answers": {}}\n')
    with pytest.raises(SystemExit, match="holds answers"):
        rehearsal(load_key=lambda: pytest.fail("the key was read"))
    gz.unlink()
    the_lot.ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger = jp.paid_once.ledger_of(the_lot)
    assert ledger.reserve(0.001, batch=the_lot.name, batch_cap_usd=the_lot.cap_usd) is not None
    with pytest.raises(SystemExit, match="already spent"):
        rehearsal(load_key=lambda: pytest.fail("the key was read"))


def test_the_ledger_stops_dev2_at_its_cap(rehearsal, monkeypatch):
    real_dry = jp.dry

    def optimistic(phase, rows=None, prefilter_k=None):
        return real_dry(phase, rows, prefilter_k) | {"pessimistic_usd": 0.0, "planned_usd": 0.0}

    monkeypatch.setattr(jp, "dry", optimistic)
    monkeypatch.setattr(jp, "CAP_USD", {**jp.CAP_USD, "dev2": 0.004})
    assert rehearsal() == 2
    the_lot = jp.lot("dev2")
    assert jp.paid_once.spent(the_lot) <= 0.004
    assert jp.paid_once.history(the_lot)[0]["stop_kind"] == "cap"


# ---- the launcher ------------------------------------------------------------------------------


def test_the_launcher_keeps_crlf_and_its_placeholders_and_takes_dev2():
    raw = (ROOT / "longdoc-free-jev-run.cmd").read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") > 0
    text = raw.decode("utf-8")
    assert '"%PHASE%"=="dev2"' in text and "prereg-dev2.md" in text
    assert 'set "PY=<PYTHON>"' in text and 'set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"' in text
    assert 'if "%HOUR%" LSS "08"' in text  # never between 00:00 and 08:00


@pytest.mark.skipif(sys.platform != "win32", reason="runs the launcher in cmd.exe")
@pytest.mark.parametrize(("phase", "refusal"), [("dev2", "refused: "), ("dev3", "the phase")])
def test_the_launcher_takes_dev2_and_still_refuses_unset_values(phase, refusal, tmp_path):
    copy = tmp_path / "longdoc-free-jev-run.cmd"
    copy.write_bytes((ROOT / "longdoc-free-jev-run.cmd").read_bytes())
    env = {k: v for k, v in os.environ.items() if k != "SANCHOPANZA_KEYS_ENV"}
    got = subprocess.run(["cmd.exe", "/c", str(copy), phase], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=60)  # fmt: skip
    assert got.returncode == 1 and refusal in got.stdout
    if phase == "dev2":
        assert "the first argument" not in got.stdout
    assert not (tmp_path / "benchmarks").exists()


# ---- stage dev2 of the Claude driver -----------------------------------------------------------


def _dev_rows(name: str) -> list[dict]:
    return [json.loads(x) for x in (DEV / name).read_text("utf-8").splitlines() if x.strip()]


def test_stage_dev2_is_the_devs_design_with_n_run_again_and_h_on_dev2s_passages():
    assert h2h.STAGES["dev2"] == (h2h.DEV2_SMOKE, h2h.DEV2_N, h2h.DEV2_H)
    assert h2h.STAGES["dev"] == (h2h.SMOKE, h2h.DEV_N, h2h.DEV_HAIKU)  # unchanged
    assert h2h.variants_of(h2h.DEV2_N, 3) == ["N"] and h2h.variants_of(h2h.DEV2_H, 1) == ["H"]
    assert h2h.variants_of(h2h.DEV_HAIKU, 1) == ["H0", "HC", "H"]
    task = h2h.FreeTask("7:H", 7, "H", "abc", "Who?", ("Peyton",), "dev2")
    assert h2h.document_of(task) == jp.passages_path("dev2", 7)
    n = dataclasses.replace(task, key="7:N", variant="N")
    assert h2h.document_of(n) == h2h.pool.novel_path("abc")
    assert h2h.prompt(task) == h2h.prompt(dataclasses.replace(task, stage="dev")) == h2h.prompt(n)
    for new, old in ((h2h.DEV2_SMOKE, h2h.SMOKE), (h2h.DEV2_N, h2h.DEV_N)):
        same = ("model_id", "full_cap", "ceiling", "floor")  # the dev's own caps
        assert [getattr(new, k) for k in same] == [getattr(old, k) for k in same]
    assert h2h.DEV2_H.model_id == h2h.DEV_HAIKU.model_id and h2h.DEV2_H.full_cap == 1.50
    dev_names = {p.name for p in h2h.STAGES["dev"]}
    assert all(p.name not in dev_names for p in h2h.STAGES["dev2"])  # their own sessions
    assert all(p.rows.parent == jp.DEV2_DIR for p in h2h.STAGES["dev2"])
    assert len(h2h.STAGE_OF) == 6


@pytest.mark.skipif(not CACHED, reason="∞Bench En.QA or its frozen ids not cached")
def test_stage_dev2_asks_every_dev_question_once_per_arm_in_the_devs_order():
    n, h = h2h.tasks_of(h2h.DEV2_N), h2h.tasks_of(h2h.DEV2_H)
    assert len(n) == len(h) == 41 and {t.variant for t in n} == {"N"}
    assert {t.variant for t in h} == {"H"}
    assert [t.item for t in n] == [t.item for t in h] == [t.item for t in h2h.tasks_of(h2h.DEV_N)]
    smoke = h2h.tasks_of(h2h.DEV2_SMOKE)
    assert [(t.item, t.variant) for t in smoke] == [(t.item, t.variant)
                                                    for t in h2h.tasks_of(h2h.SMOKE)]  # fmt: skip
    assert {t.stage for t in [*n, *h, *smoke]} == {"dev2"}


def _room_for(phase, rows: list[dict], arm: str) -> tuple[float, float]:
    usd = [float(r["usd"]) for r in rows if r["variant"] == arm]
    per = max(1.5 * statistics.fmean(usd), dr.percentile(usd, 0.95))
    return phase.ceiling - phase.worst_turn - phase.floor, phase.n * per


def test_dev2s_ceilings_hold_41_sessions_at_the_devs_measured_cost_and_fit_the_lot():
    room, need = _room_for(h2h.DEV2_N, _dev_rows("dev-sonnet-rows.jsonl"), "N")
    assert room >= need  # 7.18 against 41 x 0.1307 = 5.36
    room, need = _room_for(h2h.DEV2_H, _dev_rows("dev-haiku-rows.jsonl"), "H")
    assert room >= need  # 2.54 against 41 x 0.0534 = 2.19
    got = h2h.money("dev2")
    assert got["S2"]["most_usd"] == pytest.approx(0.80 + 4.32)  # the smoke reserves no turn
    assert got["D2N"]["most_usd"] == 12.00 and got["D2H"]["most_usd"] == 5.00
    assert got["most_usd"] == pytest.approx(22.12)
    spent_so_far = 8.196  # the dev's Claude: smoke, N and the Haiku arms, at list price
    assert spent_so_far + got["most_usd"] <= dr.CLAUDE_CAP_USD  # 30.32 of 105
    assert h2h.money("dev")["most_usd"] == pytest.approx(0.80 + 4.32 + 12.00 + 9.00)


def test_each_smoke_has_its_own_cap_rule_and_the_others_cap_for():
    rule, reserve = h2h.money_rules(h2h.DEV2_SMOKE)
    assert reserve == 0.80 and rule(0.0) == 0.80 and rule(0.10) is None  # one session
    rule, reserve = h2h.money_rules(h2h.DEV2_N)
    assert rule is None and reserve == pytest.approx(0.50 + 4.32)
    assert h2h.money_rules(h2h.SMOKE)[1] == 0.80


def test_a_failed_dev2_smoke_stops_the_stage_and_only_a_passed_one_is_final(tmp_path, monkeypatch):
    ran = []

    def run_one(phase):
        ran.append(phase.key)
        return "smoke" if phase.key == "S2" else "done"

    kind, kinds = h2h.x.drive(h2h.STAGES["dev2"], run_one, final=lambda p: None)
    assert ran == ["S2"] and kind != "done"
    stop = tmp_path / "stop.json"
    monkeypatch.setattr(h2h, "DEV2_SMOKE", dataclasses.replace(h2h.DEV2_SMOKE, stop=stop))
    smoke = h2h.DEV2_SMOKE
    monkeypatch.setitem(h2h.SMOKES, smoke.key, smoke)
    stop.write_text('{"kind": "ceiling"}\n', "utf-8")
    assert h2h.final_kind(smoke) is None  # a smoke is final only when it passed
    stop.write_text('{"kind": "done"}\n', "utf-8")
    assert h2h.final_kind(smoke) == "done"


def test_the_stage_clock_budgets_83_sessions_at_a_minute_and_a_half_and_its_margin():
    phases = h2h.STAGES["dev2"]
    seconds = h2h.clock_budget_s(phases, sum(p.n for p in phases))
    assert seconds == 83 * 60 * 1.5 + 600 == 8070  # 2 h 14.5 min: start by 21:45
    late = h2h.dt.datetime(2026, 10, 18, 21, 46)
    assert h2h.s162.crosses_midnight(late, seconds)
    assert not h2h.s162.crosses_midnight(h2h.dt.datetime(2026, 10, 18, 21, 45), seconds)


def test_dev2s_claude_lot_binds_its_prereg_and_the_reused_rows():
    lot = h2h.claude_lot("dev2")
    assert lot.prereg == jp.lot("dev2").prereg and lot.name == "longdoc-free-dev2"
    assert lot.instrument == (*h2h.INSTRUMENT, *jp.DEV_ROWS)
    assert h2h.claude_lot("dev").instrument == h2h.INSTRUMENT  # the dev's, unchanged


def test_dev2s_data_check_reads_its_own_rows_and_passages(tmp_path, monkeypatch):
    table = {"items": [{"id": 1, "novel": "k1", "chars": 3, "phase": "dev"}]}
    monkeypatch.setattr(h2h.pool, "require_pinned", lambda: None)
    monkeypatch.setattr(h2h.pool, "read_frozen", lambda: table)
    novel = tmp_path / "k1.txt"
    novel.write_text("abc", "utf-8")
    monkeypatch.setattr(h2h.pool, "novel_path", lambda key: novel)
    monkeypatch.setattr(h2h.pool, "novel_key", lambda text: "k1")
    asked = []

    def passages(phase, item):
        asked.append(phase)
        return tmp_path / f"{phase}-{item}.txt"

    monkeypatch.setattr(h2h.jev_phase, "passages_path", passages)
    (tmp_path / "dev2-1.txt").write_text("kept", "utf-8")
    monkeypatch.setattr(h2h, "DEV2_OUT", tmp_path / "dev2")
    assert any("no jev-dev2.jsonl" in p for p in h2h.data_problems("dev2"))
    (tmp_path / "dev2").mkdir()
    (tmp_path / "dev2" / "jev-dev2.jsonl").write_text('{"id": 1, "kept_chars": 4}\n', "utf-8")
    assert h2h.data_problems("dev2") == [] and set(asked) == {"dev2"}


def test_an_unsealed_dev2_is_refused_before_any_session(tmp_path, monkeypatch):
    kind, why = h2h.refusal("dev2", h2h.dt.datetime(2026, 10, 18, 9, 0), run_dir=tmp_path)
    assert kind == "preflight"  # prereg-dev2.sha256 does not exist before the seal


# ---- the reading -------------------------------------------------------------------------------


def test_the_reused_rows_are_the_sealed_devs():
    d2.require_reused()  # raises when a digest differs
    assert set(d2.REUSED_SHA256) == {Path(p).name for p in jp.DEV_ROWS}


def test_the_sealed_devs_reading_is_unchanged():
    """dev_read.read with its defaults reproduces the published dev.json (the dev's Jev spend
    and plans, its Claude spend 8.196)."""
    published = json.loads((DEV / "dev.json").read_text("utf-8"))
    jev = _dev_rows("jev-dev.jsonl")
    sessions = [*_dev_rows("dev-sonnet-rows.jsonl"), *_dev_rows("dev-haiku-rows.jsonl")]
    got = dr.read(jev, sessions, 1.6072, 1.6035, 12.3211, 8.196)
    money = got.pop("confirm_money")
    expected_money = published.pop("confirm_money")
    assert got == published
    assert money == {**expected_money, "claude_with_dev": pytest.approx(143.1, abs=0.02)}


def _jev(n: int = 40, per: int = 5) -> list[dict]:
    return [{"id": i, "novel": f"n{i // per}", "p": 0.9 if i % 2 else 0.2, "kept_chars": 9,
             "empty": False, "gold_in_kept": bool(i % 3)} for i in range(n)]  # fmt: skip


def _sessions(n: int = 40, h_f1: float = 0.6, arms=("N", "H", "H0", "HC"),
              n_f1: float = 0.6) -> list[dict]:  # fmt: skip
    cost = {"N": 0.07, "H": 0.03, "H0": 0.08, "HC": 0.018}
    f1 = {"N": n_f1, "H": h_f1, "H0": 0.5, "HC": 0.01}
    return [{"id": i, "variant": a, "f1": f1[a] + (0.1 if i % 4 == 0 else 0.0), "usd": cost[a],
             "answer_words": 2, "has_answer_line": True, "no_answer": False, "hit_cap": False}
            for i in range(n) for a in arms]  # fmt: skip


def _read(dev_h_f1: float = 0.0, new_h_f1: float = 0.6, dev_n_f1: float = 0.6, **kw):
    args = {"jev_spent": 0.45, "jev_planned": 0.49, "confirm_planned": 3.139,
            "claude_spent": 12.4, "jev_room": 11.66} | kw  # fmt: skip
    return d2.read(_jev(), _sessions(h_f1=dev_h_f1, n_f1=dev_n_f1),
                   _sessions(h_f1=new_h_f1, arms=("N", "H")), **args)  # fmt: skip


def test_combine_takes_the_devs_h0_hc_and_dev2s_n_and_h():
    got = d2.combine(_sessions(h_f1=0.0, n_f1=0.0), _sessions(h_f1=0.6, arms=("N", "H")))
    for arm in ("N", "H"):
        mine = [r for r in got if r["variant"] == arm]
        assert len(mine) == 40 and all(r["f1"] >= 0.6 for r in mine)  # the dev's (0.0) unread
    assert {r["variant"] for r in got} == {"N", "H", "H0", "HC"}
    assert len([r for r in got if r["variant"] == "H0"]) == 40
    with pytest.raises(SystemExit, match="does not run"):
        d2.combine(_sessions(), _sessions(arms=("H", "H0")))


def test_r_minus_n_uses_dev2s_n_and_the_rerun_is_reported_beside_it():
    got = _read(dev_n_f1=0.2)  # the dev's N far lower: it must not enter R - N
    assert got["cut"] == 0.5 and got["by_cut"]["0.5"]["router_minus_n"] == pytest.approx(0.0)
    rerun = got["n_rerun"]
    assert rerun["questions"] == 40 and rerun["moved"] == 40
    assert rerun["n_dev2_minus_n_dev"]["estimate"] == pytest.approx(40.0)
    assert rerun["sd_points"] == pytest.approx(0.0) and rerun["usd_dev2"] == pytest.approx(2.8)
    assert got["money"]["N"]["sessions"] == 40  # N's money is dev2's, not both runs'


def test_a_tie_sets_the_cut_with_intervals_and_seals_by_the_money_without_h0():
    got = _read()
    assert got["status"] == "run" and got["cut"] == 0.5
    at = got["at_cut"]
    assert at["router_minus_n"]["low"] <= at["router_minus_n"]["estimate"] <= at[
        "router_minus_n"]["high"]  # fmt: skip
    assert at["saving"]["clusters"] == 8 and at["coverage"] == pytest.approx(0.5)
    assert got["confirm_money"]["jev_cap"] == 11.66  # what the lot's Jev leaves
    without, with_h0 = got["confirm_money"], got["confirm_money_with_h0"]
    assert with_h0["haiku_ceiling"] > without["haiku_ceiling"]
    assert without["haiku_ceiling"] == pytest.approx(310 * 0.045 + 2.16 + 0.30)
    assert got["seal_confirmation"] == (got["n_needed"] <= 310 and without["fits"])
    assert got["expected_confirm_usd"]["claude_without_h0"] == pytest.approx(310 * 0.10)
    assert got["expected_confirm_usd"]["jev"] == pytest.approx(310 * 0.45 / 40, abs=0.01)
    assert got["vs_dev"]["h_mean_f1_dev"] < got["vs_dev"]["h_mean_f1_dev2"]
    assert set(got["by_cut"]) == {str(c) for c in (0.5, 0.6, 0.7, 0.8, 0.9)}


def test_jev_does_not_fit_when_its_plan_exceeds_what_the_lot_leaves():
    got = _read(jev_room=3.0)  # 3.139 planned over 3.00 left
    assert not got["confirm_money"]["jev_fits"] and not got["seal_confirmation"]


def test_a_losing_h_sets_no_cut_and_no_phase_j2_means_not_run():
    got = _read(new_h_f1=0.3)
    assert got["cut"] is None and got["at_cut"] is None and not got["seal_confirmation"]
    none = d2.read([], _sessions(), [], jev_spent=0.0, jev_planned=0.0, confirm_planned=3.139,
                   claude_spent=8.2, jev_room=12.0)  # fmt: skip
    assert d2.rerun_n(_jev(), _sessions(), []) is None
    assert none["status"] == "not run" and none["seal_confirmation"] is False


def test_the_registered_confirmation_plan_is_the_k200_dry_run():
    assert d2.CONFIRM_STUB_PESSIMISTIC_USD == 2.2152
    assert d2.CONFIRM_STUB_PESSIMISTIC_USD < dr.JEV_CONFIRM_CAP_USD  # far under the sealed 12.50


# ---- review of 2026-10-17 (revisor-prereg: "can be sealed", with fixes) -------------------------


def _final_all(phase):
    return "done"


@pytest.mark.parametrize("unfinished", ["S2", "D2N", "D2H"])
def test_the_reading_waits_for_every_claude_phase_to_be_final(unfinished, tmp_path):
    phases = h2h.STAGES["dev2"]
    final = lambda p: None if p.key == unfinished else "done"  # noqa: E731
    reasons = d2.pause_reasons(phases, final, tmp_path)
    assert reasons == [f"phase {unfinished} not over"]
    assert d2.pause_reasons(phases, _final_all, tmp_path) == []


@pytest.mark.parametrize("flag", ["LIMIT.flag", "STOP"])
def test_the_reading_waits_while_a_limit_or_stop_file_is_in_the_run_folder(flag, tmp_path):
    (tmp_path / flag).write_text("x", "utf-8")
    assert d2.pause_reasons(h2h.STAGES["dev2"], _final_all, tmp_path) == [
        f"{flag} in the run folder"
    ]


def test_a_paused_dev2_is_not_read_and_seals_nothing():
    got = _read(paused=["phase D2H not over"])
    assert got["status"] == "not read" and got["seal_confirmation"] is False
    assert got["paused"] == ["phase D2H not over"] and "cut" not in got
    assert _read(paused=[])["status"] == "run"
    none = d2.read([], _sessions(), [], jev_spent=0.0, jev_planned=0.0, confirm_planned=3.139,
                   claude_spent=8.2, jev_room=12.0, paused=["STOP in the run folder"])  # fmt: skip
    assert none["status"] == "not run"  # no complete J2 comes first


def test_h2h_final_kind_is_the_readings_final(tmp_path, monkeypatch):
    stop = tmp_path / "stop.json"
    phase = dataclasses.replace(h2h.DEV2_N, stop=stop)
    assert h2h.final_kind(phase) is None  # not run
    for kind, final in (("done", "done"), ("ceiling", "ceiling"), ("limit", None),
                        ("clock", None), ("manual", None)):  # fmt: skip
        stop.write_text(json.dumps({"kind": kind}) + "\n", "utf-8")
        assert h2h.final_kind(phase) == final


def _fake_git(diff_rc: int = 0, loose: str = ""):
    calls = []

    def git(*args):
        calls.append(args)
        if args[0] == "diff":
            return subprocess.CompletedProcess(args, diff_rc, "", "")
        if args[0] == "status":
            return subprocess.CompletedProcess(args, 0, loose, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    return git, calls


def test_the_reading_runs_only_where_its_code_equals_the_instrument(monkeypatch):
    git, calls = _fake_git()
    monkeypatch.setattr(jp.paid_once, "git", git)
    assert d2.require_reading_instrument() == jp.paid_once.instrument_commit(jp.lot("dev2").prereg)
    diffed = next(c for c in calls if c[0] == "diff")
    for path in ("src", "benchmarks", jp.IDS_REL, *jp.DEV_ROWS):  # meter, lb162x, browse too
        assert path in diffed
    git, _ = _fake_git(diff_rc=1)
    monkeypatch.setattr(jp.paid_once, "git", git)
    with pytest.raises(SystemExit, match="instrument differs"):
        d2.require_reading_instrument()
    git, _ = _fake_git(loose="?? benchmarks/h2h/new.py\n")
    monkeypatch.setattr(jp.paid_once, "git", git)
    with pytest.raises(SystemExit, match="not committed"):
        d2.require_reading_instrument()


def test_main_refuses_before_reading_anything_off_the_instrument(monkeypatch, tmp_path):
    monkeypatch.setattr(d2, "DEV2_DIR", tmp_path)

    def refuse():
        raise SystemExit("the instrument differs from its registered commit: nothing spent")

    monkeypatch.setattr(d2, "require_reading_instrument", refuse)
    monkeypatch.setattr(d2.jp.paid_once, "history", lambda lot: pytest.fail("read the lot"))
    with pytest.raises(SystemExit, match="instrument differs"):
        d2.main([])
    assert not (tmp_path / "dev2.json").exists()


def test_a_failed_dev2_smoke_settles_as_smoke_and_is_voided(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions.jsonl"
    row = {"arm": "SONNET-CC", "task_id": "164:N", "run": 1, "reservation": "r1",
           "list_usd": 0.0, "ok": False, "subtype": "error_during_execution",
           "final_answer": None, "usd_by_model": {},
           "tokens": {"input": 0, "output": 0}}  # a refused request: a known 0 USD  # fmt: skip
    sessions.write_text(json.dumps(row) + "\n", "utf-8")
    monkeypatch.setattr(h2h, "sessions_of", lambda phase: sessions)
    assert h2h.settle_smoke("ceiling", h2h.DEV2_SMOKE) == "smoke"
    assert json.loads(sessions.read_text("utf-8"))["not_run"] is True  # asked again on a resume
    assert h2h.settle_smoke("limit", h2h.DEV2_SMOKE) == "limit"
    ran = []
    h2h.x.drive(
        h2h.STAGES["dev2"],
        lambda p: (
            ran.append(p.key) or (h2h.settle_smoke("ceiling", p) if p.key == "S2" else "done")
        ),
        final=lambda p: None,
    )
    assert ran == ["S2"]  # N and H never start


def test_the_lots_claude_rule_counts_spent_and_the_ceilings_of_what_remains():
    todo = list(h2h.STAGES["dev2"])
    spent = {"S": 0.0997, "DN": 2.84, "DH": 5.26}  # the dev's phases, about 8.20
    got = h2h.lot_claude_worst("dev2", todo, lambda p: spent.get(p.key, 0.0))
    assert got == pytest.approx(sum(spent.values()) + 22.12)
    assert h2h.lot_problem("dev2", todo, lambda p: spent.get(p.key, 0.0)) is None
    half = [h2h.DEV2_H]  # smoke and N over: their spend, not their ceilings
    spent_now = {**spent, "S2": 0.10, "D2N": 2.9}
    got = h2h.lot_claude_worst("dev2", half, lambda p: spent_now.get(p.key, 0.0))
    assert got == pytest.approx(sum(spent_now.values()) + 5.00)
    too_much = h2h.lot_problem("dev2", todo, lambda p: 90.0 if p.key == "DN" else 0.0)
    assert too_much and "105" in too_much


def test_refusal_applies_the_lots_claude_rule(tmp_path, monkeypatch):
    for name in ("require_sealed", "require_inputs"):
        monkeypatch.setattr(h2h.paid_once, name, lambda lot: None)
    monkeypatch.setattr(h2h.paid_once, "require_instrument", lambda lot: "c" * 40)
    monkeypatch.setattr(h2h.jev_phase, "sealed_head_problems", lambda lot, git: [])
    monkeypatch.setattr(h2h.x, "pin_problems", lambda: [])
    monkeypatch.setattr(h2h, "data_problems", lambda stage: [])
    monkeypatch.setattr(h2h, "launcher_problems", lambda: [])
    monkeypatch.setattr(h2h, "final_kind", lambda p: None)
    monkeypatch.setattr(h2h, "done_now", lambda p: 0)
    monkeypatch.setattr(h2h, "phase_spent", lambda p: 30.0 if p.key == "DH" else 0.0)
    now = h2h.dt.datetime(2026, 10, 18, 9, 0)
    assert h2h.refusal("dev2", now, run_dir=tmp_path) is None  # 30 + 22.12 <= 105
    monkeypatch.setattr(h2h, "phase_spent", lambda p: 90.0 if p.key == "DH" else 0.0)
    kind, why = h2h.refusal("dev2", now, run_dir=tmp_path)
    assert kind == "preflight" and "105" in why


def test_each_phases_session_dates_come_from_its_reservations(tmp_path, monkeypatch):
    def reservations(phase):
        return tmp_path / f"{phase.key}.jsonl"

    monkeypatch.setattr(h2h, "reservations_of", reservations)
    lines = {"S2": ["2026-10-18T09:00:00"], "D2N": ["2026-10-18T09:01:00", "2026-10-18T09:20:00"],
             "D2H": ["2026-10-18T23:50:00", "2026-10-19T09:00:00"]}  # fmt: skip
    for key, starts in lines.items():
        (tmp_path / f"{key}.jsonl").write_text(
            "".join(json.dumps({"rid": "x", "started": s}) + "\n" for s in starts), "utf-8"
        )
    got = h2h.phase_dates("dev2")
    assert got == {"S2": ["2026-10-18"], "D2N": ["2026-10-18"],
                   "D2H": ["2026-10-18", "2026-10-19"]}  # fmt: skip
    assert d2.same_day(got) is False
    assert d2.same_day({"D2N": ["2026-10-18"], "D2H": ["2026-10-18"]}) is True


def _launcher_at(tmp_path, hour: str) -> Path:
    """The launcher's copy with its clock read as `hour` (the tracked file reads %TIME%)."""
    raw = (ROOT / "longdoc-free-jev-run.cmd").read_bytes().decode("utf-8")
    assert raw.count("%TIME:~0,2%") == 1
    copy = tmp_path / "longdoc-free-jev-run.cmd"
    copy.write_bytes(raw.replace("%TIME:~0,2%", hour).encode("utf-8"))
    return copy


@pytest.mark.skipif(sys.platform != "win32", reason="runs the launcher in cmd.exe")
@pytest.mark.parametrize(("phase", "hour", "refusal"), [
    ("dev2", "22", "dev2 starts before 22:00"),
    ("dev2", "23", "dev2 starts before 22:00"),
    ("dev2", "21", "set PY in this copy"),
    ("probe", "23", "set PY in this copy"),
    ("dev2", "07", "not between 00:00 and 08:00"),
])  # fmt: skip
def test_the_launcher_refuses_dev2_after_22_00_and_keeps_the_others_hours(
    phase, hour, refusal, tmp_path
):
    copy = _launcher_at(tmp_path, hour)
    env = {k: v for k, v in os.environ.items() if k != "SANCHOPANZA_KEYS_ENV"}
    got = subprocess.run(["cmd.exe", "/c", str(copy), phase], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=60)  # fmt: skip
    assert got.returncode == 1 and refusal in got.stdout
    assert not (tmp_path / "benchmarks").exists()


def test_the_launchers_dev2_hour_check_is_tracked_with_crlf():
    raw = (ROOT / "longdoc-free-jev-run.cmd").read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")
    text = raw.decode("utf-8")
    assert 'if "%PHASE%"=="dev2" if "%HOUR%" GEQ "22" (' in text
    assert "the probe and dev2 one launch, never another" in text
