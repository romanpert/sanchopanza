"""Lot lb162 (benchmarks/jev114/lb162.py, lb162_stats.py, benchmarks/h2h/h2h_lb162.py), with
no network and no session: the id selection, phase J on a fake decider, the covered set, the
caps, the ceiling and the clock, the seal on live paths, the verdict rule and rows without text."""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from sanchopanza.contract import Answer, DeciderOutOfFunds, DeciderUnavailable, Decision
from sanchopanza.providers.capped import SpendCapReached

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "results" / "2026-10-15-lb162"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lb = _load("lb162", "benchmarks/jev114/lb162.py")
h2h = _load("h2h_lb162", "benchmarks/h2h/h2h_lb162.py")
st = lb.stats


# --- the 162 ids ----------------------------------------------------------------------------------


def _raw(i: int, domain: str = "Single-Document QA", chars: int = 150_000) -> dict:
    return {"_id": f"id{i:03d}", "domain": domain, "context": "x" * chars, "answer": "A"}


def test_fresh_ids_are_the_eligible_ones_outside_the_used_sorted_and_deterministic():
    rows = [_raw(5), _raw(1), _raw(3, "Code Repository Understanding"), _raw(2, chars=100_000),
            _raw(4, "Multi-Document QA"), _raw(0)]  # fmt: skip
    got = lb.fresh_ids(rows, {"id000"})
    assert got == ["id001", "id004", "id005"]
    assert lb.fresh_ids(list(reversed(rows)), {"id000"}) == got
    assert not set(got) & {"id000"}


def test_the_frozen_list_holds_162_ids_with_its_digest_and_none_of_the_60():
    ids = lb.frozen_ids()
    assert len(ids) == lb.N_TASKS == 162 and len(set(ids)) == 162 and ids == sorted(ids)
    assert lb.digest(lb.IDS_FILE) == lb.IDS_SHA256
    assert (OUT / "ids.sha256").read_text().split()[0] == lb.IDS_SHA256
    l6_rows = (ROOT / "docs/results/2026-10-15-jev114-l6/b3-scored.jsonl").read_text("utf-8")
    used = {json.loads(x)["id"] for x in l6_rows.splitlines() if x.strip()}
    used |= set(lb.read_ids(ROOT / "benchmarks/h2h/longdoc-dev-ids.txt"))
    assert len(used) == 60 and not used & set(ids)


# --- phase J on a fake decider ------------------------------------------------------------------


class FakeTask:
    def __init__(self, path: Path, i: int = 0) -> None:
        self.task_id, self.gold, self.chars = f"t{i}", "B", 1_000
        self.length, self.difficulty, self.domain = "short", "hard", "Single-Document QA"
        self.question = "SECRET-QUESTION about the ledger?"
        self.choices = ("SECRET-A", "SECRET-B", "SECRET-C", "SECRET-D")
        self.doc_path = str(path)


def _decision(letter: str | None, p: float = 0.7, usd: float = 0.001) -> Decision:
    if letter is None:
        return Decision("longbench_choice", {}, "jev", "jev-1.14.0", cost_usd=usd)
    probs = {k: (p if k == letter else (1 - p) / 3) for k in "ABCD"}
    answer = Answer(kind="choice", confidence=p, choice=letter, probabilities=probs)
    return Decision("longbench_choice", {"answer": answer}, "jev", "jev-1.14.0", cost_usd=usd)


class FakeArm:
    def __init__(self, replies: list) -> None:
        self.replies, self.seen = list(replies), []

    async def decide(self, point, state, questions):
        self.seen.append(len(state["document"]))
        return self.replies.pop(0)


def test_an_unanswered_call_is_asked_again_shorter_and_every_attempt_is_paid(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("SECRET-DOCUMENT " * 100_000, encoding="utf-8")
    arm = FakeArm([_decision(None), _decision("B", 0.81)])
    row = asyncio.run(lb.jev_one(FakeTask(doc), arm, lb.Stop()))
    assert row["status"] == "answered" and row[lb.CELL]["tries"] == 2
    assert row[lb.CELL]["usd"] == pytest.approx(0.002)
    assert arm.seen[1] < arm.seen[0] <= lb.WINDOW + 10
    assert row[lb.CELL]["shown_chars"] == int(lb.WINDOW * lb.SHRINK[1])


def test_three_unanswered_lengths_fail_and_a_stop_leaves_the_task_unasked(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("abc", encoding="utf-8")
    row = asyncio.run(lb.jev_one(FakeTask(doc), FakeArm([_decision(None)] * 3), lb.Stop()))
    assert row["status"] == "failed" and row[lb.CELL]["tries"] == 3
    stop = lb.Stop()
    stop.note("limit", "HTTP 429")
    arm = FakeArm([])
    row = asyncio.run(lb.jev_one(FakeTask(doc), arm, stop))
    assert row["status"] == "stopped" and arm.seen == []


class Raising:
    name = "fake"

    def __init__(self, error: Exception | None) -> None:
        self.error, self.calls = error, 0

    async def decide(self, point, state, questions):
        self.calls += 1
        if self.error:
            raise self.error
        return _decision("A")


def test_this_lot_does_not_retry_a_429_but_keeps_529s_retries(monkeypatch):
    from sanchopanza.providers import jev

    monkeypatch.setattr(jev, "RETRYABLE", frozenset({429, 529}))
    monkeypatch.setattr(jev, "BASE_WAIT_S", 0.0)
    lb.no_retry_on_429()
    assert frozenset({529}) == jev.RETRYABLE

    class Response:
        def __init__(self, status: int) -> None:
            self.status_code, self.text = status, ""

        def json(self) -> dict:
            return {}

    class Client:
        def __init__(self, status: int) -> None:
            self.status, self.posts = status, 0

        async def post(self, *args, **kwargs):
            self.posts += 1
            return Response(self.status)

    for status, posts in ((429, 1), (529, jev.MAX_RETRIES + 1)):
        client = Client(status)
        decider = jev.JevDecider("test-key", client=client, model=lb.MODEL)
        with pytest.raises(DeciderUnavailable, match=f"HTTP {status}"):
            asyncio.run(decider._send({}))
        assert client.posts == posts
    assert lb.stop_kind(DeciderUnavailable("jev did not answer: HTTP 429")) == "limit"


@pytest.mark.parametrize("error, kind", [
    (SpendCapReached("spend cap"), "cap"),
    (DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)"), "funds"),
    (DeciderUnavailable("jev did not answer: HTTP 429"), "limit"),
])  # fmt: skip
def test_cap_402_and_429_stop_every_further_call(error, kind):
    inner = Raising(error)
    stop = lb.Stop()
    halting = lb.Halting(inner, stop)
    for _ in range(3):
        with pytest.raises(DeciderUnavailable):
            asyncio.run(halting.decide("p", {}, {}))
    assert stop.kind == kind and inner.calls == 1


def test_a_timeout_does_not_stop_and_a_stop_file_does(tmp_path):
    inner = Raising(DeciderUnavailable("jev unreachable: ReadTimeout"))
    stop = lb.Stop(tmp_path / "STOP")
    halting = lb.Halting(inner, stop)
    for _ in range(2):
        with pytest.raises(DeciderUnavailable):
            asyncio.run(halting.decide("p", {}, {}))
    assert stop.kind is None and inner.calls == 2
    (tmp_path / "STOP").write_text("")
    with pytest.raises(DeciderUnavailable):
        asyncio.run(halting.decide("p", {}, {}))
    assert stop.kind == "manual" and inner.calls == 2


def test_the_jev_plan_must_fit_the_batch_cap():
    assert lb.jev_plan_refusal(0.0, 162) == ""  # 0.78 of 1.20
    assert lb.jev_plan_refusal(0.5, 162) != ""
    assert lb.jev_plan_refusal(1.19, 1) == ""
    assert lb.jev_plan_refusal(1.20, 1) != ""


def test_a_resume_replaces_only_the_rows_asked_again():
    before = [{"id": "a", "status": "answered"}, {"id": "b", "status": "stopped"}]
    after = lb.merged(before, {1: {"id": "b", "status": "failed"}})
    assert [r["status"] for r in after] == ["answered", "failed"]
    assert before[1]["status"] == "stopped"


# --- the covered set ------------------------------------------------------------------------------


def _row(i: int, gold: str, letter: str | None, p: float | None, status: str = "answered",
         length: str = "short", difficulty: str = "easy", usd: float = 0.005) -> dict:  # fmt: skip
    return {"id": f"t{i:03d}", "gold": gold, "chars": 200_000, "length": length,
            "difficulty": difficulty, "status": status,
            lb.CELL: {"letter": letter, "p": p, "probs": {}, "usd": usd, "tries": 1,
                      "tokens": 10, "shown_chars": 200_000}}  # fmt: skip


def test_covered_is_answered_at_or_above_the_cut_in_a_seeded_order():
    rows = [_row(0, "A", "A", 0.6), _row(1, "A", "B", 0.5999),
            _row(2, "A", None, None, "failed"), _row(3, "A", "C", 0.9),
            _row(4, "A", "A", 0.95, "stopped"), _row(5, "A", "D", 1.0)]  # fmt: skip
    got = lb.covered(rows)
    assert sorted(got) == ["t000", "t003", "t005"]
    assert lb.covered(list(reversed(rows))) == got  # order set by the seed, not the rows
    assert lb.TAU == 0.6


def test_phase_s_waits_for_a_final_phase_j():
    full = [_row(i, "A", "A", 0.7) for i in range(lb.N_TASKS)]
    assert lb.phase_j_final(full, None) == ""
    assert lb.phase_j_final(full[:-1], None) != ""
    paused = [*full[:-1], _row(999, "A", None, None, "stopped")]
    assert lb.phase_j_final(paused, {"kind": "limit"}) != ""
    assert lb.phase_j_final(paused, {"kind": "cap"}) == ""  # a cap stop is final


# --- money and clock of phase S ----------------------------------------------------------------


def test_the_registered_constants():
    assert (lb.MODEL, lb.WINDOW, lb.SHRINK) == ("jev-1.14.0", 900_000, lb.l6.SHRINK)
    assert lb.l6.TIMEOUT_S["L"] == lb.TIMEOUT_S and lb.CONCURRENCY <= 4
    assert lb.BATCH_CAP_USD == 1.20 and lb.LEDGER_CAP_USD == 1.20
    assert Path("C:/sp-runs/lb162/ledger.json") == lb.LEDGER_PATH
    assert st.TAU == 0.6 and st.MARGIN == -0.10
    assert h2h.CEILING_USD == 18.00 and h2h.ARM == lb.l6.SONNET_ARM == "SONNET-CC"
    assert h2h.ld.CAPS["SONNET"] == lb.SONNET_CAP_USD
    assert h2h.SESSIONS.parent.name == "lb162"
    assert "'h2h_lb162.py'" in (ROOT / "benchmarks/h2h/launch.ps1").read_text(encoding="utf-8")


def test_phase_s_refuses_only_when_the_expected_cost_alone_passes_the_ceiling():
    assert h2h.expected_refusal(87) == ""
    assert h2h.expected_refusal(120) == ""  # above what the ceiling holds at the mean: starts
    assert h2h.expected_refusal(130) == ""  # 17.94 USD expected
    assert "refused" in h2h.expected_refusal(131)  # 18.08 USD expected
    assert lb.sessions_before_guard(lb.SONNET_EST_USD) == 97  # (18 - 4.68) / 0.138, + 1
    assert lb.guaranteed_sessions() == 3  # every session at 3.00 + 1.68


class Task:
    def __init__(self, i: int) -> None:
        self.task_id = f"c{i:03d}"


@pytest.mark.parametrize("usd, ran", [(0.138, 97), (4.68, 3), (1.0, 14)])
def test_high_coverage_starts_and_the_guard_stops_it_under_18_usd(tmp_path, usd, ran):
    tasks = [Task(i) for i in range(120)]  # 120 covered: 16.56 USD expected
    assert h2h.expected_refusal(len(tasks)) == ""
    seen = []

    def session(item, run, arm):
        seen.append(item[0])
        return {"task": item[0], "task_id": item[0], "run": run, "arm": arm, "list_usd": usd}

    limits = h2h.phase.Limits(session_max_usd=h2h.RESERVE[h2h.MODEL], ceiling_usd=h2h.CEILING_USD)
    code, rows = h2h.phase.run_phase(h2h.steps(tasks), [], limits, session,
                                     tmp_path / "sessions.jsonl")  # fmt: skip
    assert code == 1 and len(rows) == len(seen) == ran
    assert seen == [t.task_id for t in tasks[:ran]]  # the file's (seeded) order, a prefix
    # the last session may still spend its cap plus one worst turn: never past the ceiling
    assert sum(r["list_usd"] for r in rows[:-1]) + h2h.RESERVE[h2h.MODEL] <= h2h.CEILING_USD
    assert sum(r["list_usd"] for r in rows) <= h2h.CEILING_USD


def test_the_covered_order_is_a_seeded_shuffle_so_a_stop_leaves_a_random_subset():
    rows = [_row(i, "A", "A", 0.9) for i in range(120)]
    got = lb.covered(rows)
    assert sorted(got) == [r["id"] for r in rows] and got != sorted(got)
    assert got == lb.covered(rows)


def test_the_phase_loop_never_starts_a_session_that_could_pass_18_usd():
    reserve = h2h.RESERVE[h2h.MODEL]
    assert reserve == pytest.approx(3.00 + 1.68)
    assert h2h.ld.CAPS[h2h.MODEL] == 3.00  # the session's own --max-budget-usd is h2h's
    limits = h2h.phase.Limits(session_max_usd=reserve, ceiling_usd=h2h.CEILING_USD)
    assert h2h.phase.stop_reason([{"list_usd": 13.32}], limits, 0) is None
    assert "ceiling" in h2h.phase.stop_reason([{"list_usd": 13.33}], limits, 0)


def test_the_clock_refuses_early_starts_and_runs_across_midnight():
    day = dt.datetime(2026, 10, 16)
    assert h2h.clock_refusal(day.replace(hour=7, minute=59), 10) != ""
    assert h2h.clock_refusal(day.replace(hour=10), 87) == ""
    assert "midnight" in h2h.clock_refusal(day.replace(hour=22, minute=40), 87)
    assert h2h.clock_refusal(day.replace(hour=23, minute=30), 1) == ""


def test_no_session_starts_near_midnight_or_with_a_stop_file(tmp_path):
    ran = []

    def session(item, run, arm):
        ran.append(item)
        return {}

    late = h2h.guarded(session, clock=lambda: dt.datetime(2026, 10, 16, 23, 55), run_dir=tmp_path)
    with pytest.raises(h2h.common.JointCeiling, match="midnight"):
        late(("t",), 1, h2h.ARM)
    ok = h2h.guarded(session, clock=lambda: dt.datetime(2026, 10, 16, 12), run_dir=tmp_path)
    ok(("t",), 1, h2h.ARM)
    (tmp_path / "STOP").write_text("")
    with pytest.raises(h2h.common.JointCeiling, match="STOP"):
        ok(("t",), 1, h2h.ARM)
    assert len(ran) == 1


def test_live_paths_refuse_without_a_matching_seal(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "OUT", tmp_path)
    monkeypatch.setattr(lb, "REPO", tmp_path)
    called = []
    monkeypatch.setattr(lb.l4, "load_key", lambda: called.append("key"))
    for argv in (["--run", "--live"], ["--smoke", "--live"]):
        with pytest.raises(SystemExit, match="seal"):
            lb.main(argv)
    with pytest.raises(SystemExit, match="seal"):
        h2h.main(["--live"])
    (tmp_path / "prereg.sha256").write_text("0" * 64 + "\n")
    (tmp_path / "prereg.md").write_text("x\n")
    monkeypatch.setattr(lb, "SEALED", ())
    monkeypatch.setattr(lb, "SEALED_DATA", ())
    with pytest.raises(SystemExit, match="seal"):
        lb.main(["--run", "--live"])
    assert called == []


def test_a_seal_round_trip_and_no_quiet_reseal(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "OUT", tmp_path)
    monkeypatch.setattr(lb, "REPO", tmp_path)
    monkeypatch.setattr(lb, "SEALED", ("code.py",))
    monkeypatch.setattr(lb, "SEALED_DATA", ())
    monkeypatch.setattr(lb, "ANSWERS", tmp_path / "answers.jsonl")
    (tmp_path / "prereg.md").write_text("plan\n")
    (tmp_path / "code.py").write_text("x = 1\r\n")
    lb.seal()
    lb.require_prereg()
    (tmp_path / "code.py").write_text("x = 2\n")
    with pytest.raises(SystemExit):
        lb.require_prereg()
    with pytest.raises(SystemExit, match="another seal"):
        lb.seal()
    (tmp_path / "answers.jsonl").write_text("{}\n")
    with pytest.raises(SystemExit, match="amendment"):
        lb.seal(again=True)


# --- the verdict rule ---------------------------------------------------------------------------


def test_the_verdict_rule_at_and_around_minus_ten_points():
    assert st.verdict((-0.0999, 0.05)) == "no peor"
    assert st.verdict((-0.10, 0.05)) == "no concluyente"  # the bound must clear the margin
    assert st.verdict((-0.30, -0.1001)) == "peor"
    assert st.verdict((-0.30, -0.10)) == "no concluyente"
    assert st.verdict((-0.15, 0.02)) == "no concluyente"
    assert st.verdict(None) == "no medido"


def _sonnet(ids_ok: dict[str, bool]) -> dict:
    return {i: {"id": i, "letter": "A" if ok else "B", "ok": ok, "usd": 0.1}
            for i, ok in ids_ok.items()}  # fmt: skip


def test_hybrid_minus_sonnet_counts_covered_disagreements_over_every_task():
    rows = [
        _row(0, "A", "A", 0.9),  # covered, Jev right
        _row(1, "A", "B", 0.8),  # covered, Jev wrong
        _row(2, "A", "A", 0.7),  # covered, Jev right
        _row(3, "A", "B", 0.3),  # uncovered: 0, whatever Sonnet would say
        _row(4, "A", None, None, "failed"),  # uncovered
        _row(5, "A", "C", 0.2),
        _row(6, "A", "A", 0.5, "stopped"),  # unasked: out of n
    ]
    sonnet = _sonnet({"t000": False, "t001": True, "t002": True})
    got = st.analyse(rows, sonnet)
    p = got["primary"]
    assert p["n"] == 6 and p["covered"] == 3 and got["stopped_unasked"] == 1
    assert p["diff"] == pytest.approx(round((1 - 1 + 0) / 6, 4))
    assert p["mcnemar"] == {"jev_only_right": 1, "sonnet_only_right": 1, "p": 1.0}
    assert p["bootstrap"] == {"draws": 10_000, "seed": 20261015, "unit": "task"}
    d = got["descriptive"]
    assert d["coverage"] == 0.5 and d["jev_precision_covered"] == round(2 / 3, 4)
    assert d["sonnet_accuracy_covered"] == round(2 / 3, 4)
    assert d["jev_accuracy_all"] == round(2 / 6, 4)
    c = got["costs"]
    assert c["jev_usd_all"] == pytest.approx(0.03) and c["sonnet_usd_covered"] == pytest.approx(0.3)
    assert c["estimate"]["sonnet_usd_uncovered"] == pytest.approx(3 * 0.123, abs=1e-4)
    assert set(got["by_length"]) == {"short"} and got["by_length"]["short"]["n"] == 6


def test_synthetic_verdicts_no_peor_and_peor():
    good = [_row(i, "A", "A", 0.9) for i in range(100)]
    sonnet = _sonnet({f"t{i:03d}": i % 2 == 0 for i in range(100)})
    assert st.analyse(good, sonnet)["primary"]["verdict"] == "no peor"
    bad = [_row(i, "A", "B", 0.9) for i in range(100)]
    sonnet = _sonnet({f"t{i:03d}": True for i in range(100)})
    p = st.analyse(bad, sonnet)["primary"]
    assert p["diff"] == -1.0 and p["verdict"] == "peor"


def test_a_covered_task_without_sonnet_does_not_shrink_the_gain():
    rows = [_row(0, "A", "B", 0.9), _row(1, "A", "B", 0.9), _row(2, "A", "A", 0.1),
            _row(3, "A", "A", 0.1)]  # fmt: skip
    full = st.units(rows, _sonnet({"t000": True, "t001": True}))
    part = st.units(rows, _sonnet({"t000": True}))
    assert st.estimate(full, [0, 1, 2, 3]) == -0.5
    assert st.estimate(part, [0, 1, 2, 3]) == -0.5  # coverage x mean gain, not -1/4
    assert st.primary(part)["covered_without_sonnet"] == 1


# --- rows without text ----------------------------------------------------------------------------

ALLOWED = {"answered", "failed", "stopped", "short", "medium", "long", "easy", "hard",
           *"ABCD"}  # fmt: skip


def _strings(value) -> list[str]:
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return [value] if isinstance(value, str) else []


def test_jev_rows_hold_ids_letters_and_probabilities_only(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("SECRET-DOCUMENT", encoding="utf-8")
    row = asyncio.run(lb.jev_one(FakeTask(doc), FakeArm([_decision("C", 0.9)]), lb.Stop()))
    text = json.dumps(row)
    assert "SECRET" not in text
    assert set(_strings(row)) - ALLOWED == {"t0"}


def test_sonnet_rows_drop_the_reply_paths_and_the_other_arms():
    session = {"task_id": "t1", "task": "t1", "run": 1, "arm": "SONNET-CC",
               "final_answer": "D", "ok_oficial": True, "list_usd": 0.12, "wall_s": 20.0,
               "turns": 4, "hit_cap": False, "answer": "SECRET reply",
               "workdir": "C:/sp-runs/h2h/lb162/abc/work", "leak_tools": ["SECRET"]}  # fmt: skip
    rows = [session, {**session, "arm": "SONNET-SP"}, {**session, "run": -9},
            {**session, "task_id": "t2", "not_run": True}]  # fmt: skip
    got = h2h.public_rows(rows)
    assert got == [{"id": "t1", "letter": "D", "ok": True, "usd": 0.12, "wall_s": 20.0,
                    "turns": 4, "hit_cap": False, "no_letter": False}]  # fmt: skip
    assert set(got[0]) == {"id", *h2h.ROW_KEYS}
