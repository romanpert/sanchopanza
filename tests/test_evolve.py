"""The evolution interface: what an outer self-improvement loop may touch, and how.

No test here calls a paid provider. Recordings are built in the test with the real question
builders and `key_of`, so a replay goes through the same policy code production runs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import Squire, Thresholds
from sanchopanza.contract import Decision, Truth
from sanchopanza.eval.stats import wilson
from sanchopanza.evolve import (
    Admission,
    Edit,
    Evaluator,
    FreshSplitSpent,
    Knobs,
    Ledger,
    RecordingInvalidated,
    RecordingMiss,
    Split,
    UnexercisedEdit,
    admit,
    diff,
    dormant_gates,
    drift_magnitude,
    edit_budget,
    edits_hash,
    leak_check,
    noise_floor,
)
from sanchopanza.journal import MemoryJournal
from sanchopanza.points import triage
from sanchopanza.providers import RecordedDecider
from sanchopanza.providers.recorded import key_of

ROOT = Path(__file__).resolve().parents[1]

# --- a small bench of `redundant_page` cases, recorded here --------------------------------


def _case(i: int, expected: str) -> dict[str, Any]:
    return {
        "id": f"rp-{i:02d}",
        "point": "redundant_page",
        "input": {
            "purpose": f"flood damage survey number {i}",
            "text": f"page {i} repeats the flood figures",
            "known": f"digest {i}",
        },
        "expected": expected,
    }


def _entry(case: dict[str, Any], p: float) -> dict[str, Any]:
    inp = case["input"]
    state, qs = triage.redundancy_questions(
        purpose=inp["purpose"], text=inp["text"], known=inp["known"]
    )
    return {
        "key": key_of("redundant_page", state, qs),
        "point": "redundant_page",
        "model": "jev-1.13.0",
        "cost_usd": 3e-5,
        "answers": {
            "adds_nothing": {
                "kind": "truth",
                "truth": p,
                "confidence": abs(2 * p - 1),
                "probabilities": {},
            }
        },
    }


# (expected, recorded probability). At the shipped 0.59: 8 of 10 correct.
BENCH = [
    ("drop", 0.95),
    ("drop", 0.90),
    ("drop", 0.70),
    ("drop", 0.62),  # 0.03 above the cut: a re-ask can flip it
    ("drop", 0.50),  # missed at 0.59, caught at 0.45
    ("keep", 0.10),
    ("keep", 0.20),
    ("keep", 0.30),
    ("keep", 0.40),
    ("keep", 0.75),  # a false drop at any cut below 0.75
]


@pytest.fixture
def bench() -> tuple[list[dict[str, Any]], RecordedDecider]:
    cases = [_case(i, label) for i, (label, _) in enumerate(BENCH)]
    entries = [_entry(c, p) for c, (_, p) in zip(cases, BENCH, strict=True)]
    return cases, RecordedDecider(entries)


def _all_evolve(cases: list[dict[str, Any]]) -> Split:
    return Split(evolve=tuple(cases), holdout=(), fresh=())


BASE = Knobs.from_thresholds(Thresholds())


# --- Knobs and Edit ---------------------------------------------------------------------------


def test_knobs_capture_the_squire_catalog_and_window_flags():
    squire = Squire(thresholds=Thresholds().with_(adds_nothing=0.5))
    catalog = [{"name": "mail", "about": "send and read mail"}, {"name": "web", "about": "fetch"}]
    knobs = Knobs.from_squire(squire, catalog=catalog, scan_untrusted=False)
    assert knobs.threshold("adds_nothing") == 0.5
    assert knobs.about == {"mail": "send and read mail", "web": "fetch"}
    assert knobs.flag == {"scan_untrusted": False, "wait_on_deferred": True}
    assert knobs.question == {}
    assert knobs.to_thresholds() == Thresholds().with_(adds_nothing=0.5)


def test_knobs_round_trip_through_json():
    knobs = Knobs.from_squire(Squire(), catalog=[{"name": "mail", "about": "mail"}]).with_question(
        "loop:goal_met", "Is the goal met?"
    )
    raw = json.loads(json.dumps(knobs.to_dict()))
    assert Knobs.from_dict(raw) == knobs
    assert Knobs.from_dict(raw).fingerprint() == knobs.fingerprint()


def test_knobs_refuse_unknown_names_instead_of_ignoring_them():
    raw = BASE.to_dict()
    with pytest.raises(ValueError, match="threshold"):
        Knobs.from_dict({**raw, "thresholds": {**raw["thresholds"], "adds_nothin": 0.5}})
    with pytest.raises(ValueError, match="flag"):
        Knobs.from_dict({**raw, "flags": {"scan_everything": True}})
    with pytest.raises(ValueError, match="point:question"):
        BASE.with_question("goal_met", "text")


def test_diff_is_atomic_and_marks_what_invalidates_a_recording():
    a = Knobs.from_squire(Squire(), catalog=[{"name": "mail", "about": "mail"}])
    b = (
        a.with_threshold("adds_nothing", 0.5)
        .with_threshold("remember", 0.65)
        .with_question("loop:goal_met", "new wording")
        .with_about("mail", "send mail")
        .with_flag("scan_untrusted", False)
    )
    edits = diff(a, b)
    assert [(e.kind, e.key) for e in edits] == [
        ("threshold", "adds_nothing"),
        ("threshold", "remember"),
        ("question", "loop:goal_met"),
        ("about", "mail"),
        ("flag", "scan_untrusted"),
    ]
    assert [e.invalidates_recordings for e in edits] == [False, False, True, True, False]
    assert edits[2].before is None  # the shipped wording
    assert diff(a, a) == ()
    assert a.apply(edits) == b


def test_applying_a_stale_edit_fails_loudly():
    edit = Edit("threshold", "adds_nothing", 0.80, 0.50)  # but the incumbent holds 0.59
    with pytest.raises(ValueError, match="stale"):
        BASE.apply([edit])


def test_edit_kinds_are_closed():
    with pytest.raises(ValueError):
        Edit("prompt", "system", None, "x")


def test_edits_hash_ignores_order_and_the_incumbent_value():
    one = Edit("threshold", "adds_nothing", 0.59, 0.5)
    two = Edit("threshold", "remember", 0.70, 0.65)
    assert edits_hash([one, two]) == edits_hash([two, one])
    assert edits_hash([one]) == edits_hash([Edit("threshold", "adds_nothing", 0.80, 0.5)])
    assert edits_hash([one]) != edits_hash([two])


# --- Split ------------------------------------------------------------------------------------


def test_split_is_deterministic_by_case_id_and_partitions(bench):
    cases, _ = bench
    many = [_case(i, "keep") for i in range(200)]
    a = Split.by_hash(many, holdout=0.25, fresh=0.25)
    b = Split.by_hash(list(reversed(many)), holdout=0.25, fresh=0.25)
    ids = lambda part: sorted(c["id"] for c in part)  # noqa: E731
    assert ids(a.evolve) == ids(b.evolve) and ids(a.holdout) == ids(b.holdout)
    everything = ids(a.evolve) + ids(a.holdout) + ids(a.fresh)
    assert sorted(everything) == sorted(c["id"] for c in many)
    assert len(set(everything)) == 200
    assert 70 < len(a.evolve) < 130  # about half


def test_split_rejects_impossible_fractions_and_accepts_nothing():
    with pytest.raises(ValueError):
        Split.by_hash([], holdout=0.6, fresh=0.4)
    empty = Split.by_hash([], holdout=0.25, fresh=0.25)
    assert empty.evolve == empty.holdout == empty.fresh == ()


# --- Evaluator --------------------------------------------------------------------------------


def test_replay_scores_through_the_real_policy(bench):
    cases, recording = bench
    ev = Evaluator(_all_evolve(cases), recording=recording, base=BASE)
    shipped = ev.score(BASE, "evolve")
    assert (shipped.hits, shipped.n, shipped.misses) == (8, 10, 0)
    assert shipped.accuracy == pytest.approx(0.8)
    assert shipped.per_point == {"redundant_page": (8, 10)}
    assert shipped.costly_errors == 1  # the 0.75 keep, dropped; the missed 0.50 is cheap
    lower = ev.score(BASE.with_threshold("adds_nothing", 0.45), "evolve")
    assert lower.hits == 9  # 0.50 is now caught
    assert lower.costly_errors == 1
    reckless = ev.score(BASE.with_threshold("adds_nothing", 0.05), "evolve")
    assert reckless.costly_errors == 5  # every keep dropped
    assert lower.outcomes != shipped.outcomes


def test_an_inert_edit_leaves_the_outcomes_unchanged(bench):
    cases, recording = bench
    ev = Evaluator(_all_evolve(cases), recording=recording, base=BASE)
    inert = ev.score(BASE.with_threshold("saturated", 0.9), "evolve")  # not read by this point
    assert inert.outcomes == ev.score(BASE, "evolve").outcomes


def test_a_question_edit_is_refused_on_a_recording(bench):
    cases, recording = bench
    ev = Evaluator(_all_evolve(cases), recording=recording, base=BASE)
    reworded = BASE.with_question("redundant_page:adds_nothing", "Is it all old news?")
    with pytest.raises(RecordingInvalidated, match="redundant_page:adds_nothing"):
        ev.score(reworded, "evolve")


def test_a_question_edit_goes_to_an_explicit_live_decider_with_the_new_wording(bench):
    cases, recording = bench
    seen: list[str] = []

    class Live:
        name = "live"
        accepts_attachments = False

        async def decide(self, point, state, questions):
            question = questions["adds_nothing"]
            assert isinstance(question, Truth)
            seen.append(str(question.instructions))
            from sanchopanza.answers import truth

            return Decision(point, {"adds_nothing": truth(0.99)}, "live", "m")

    ev = Evaluator(_all_evolve(cases), recording=recording, base=BASE, live=Live())
    reworded = BASE.with_question("redundant_page:adds_nothing", "Is it all old news?")
    score = ev.score(reworded, "evolve")
    assert seen and set(seen) == {"Is it all old news?"}
    assert score.hits == 5  # drops everything: right on the five drops only
    assert score.live


def test_catalog_and_window_edits_are_refused_rather_than_scored_as_free(bench):
    cases, recording = bench
    ev = Evaluator(_all_evolve(cases), recording=recording, base=BASE)
    with pytest.raises(UnexercisedEdit):
        ev.score(BASE.with_flag("scan_untrusted", False), "evolve")
    base = BASE.with_about("mail", "mail")
    ev2 = Evaluator(_all_evolve(cases), recording=recording, base=base)
    with pytest.raises(UnexercisedEdit):
        ev2.score(base.with_about("mail", "send mail"), "evolve")
    with pytest.raises(UnexercisedEdit):  # the bench runner overrides it
        ev.score(BASE.with_threshold("allow_upgrade", True), "evolve")


def test_an_empty_split_scores_zero_of_zero(bench):
    _, recording = bench
    ev = Evaluator(Split((), (), ()), recording=recording, base=BASE)
    score = ev.score(BASE, "evolve")
    assert (score.n, score.hits, score.accuracy) == (0, 0, 0.0)


def test_all_missing_answers_raise_instead_of_scoring_the_default(bench):
    """An empty answer falls back to the harness default, and on a gate whose default is the
    right label that scores as a hit. A missing recording must not look like a result."""
    cases, _ = bench
    ev = Evaluator(_all_evolve(cases), recording=RecordedDecider(()), base=BASE)
    with pytest.raises(RecordingMiss, match="10 of 10"):
        ev.score(BASE, "evolve")
    lax = Evaluator(
        _all_evolve(cases), recording=RecordedDecider(()), base=BASE, allow_missing=True
    )
    score = lax.score(BASE, "evolve")
    assert score.misses == 10
    assert score.hits == 5  # the five `keep` cases, right by default and by nothing else


def test_holdout_reads_are_counted_and_journaled(bench):
    cases, recording = bench
    journal = MemoryJournal()
    split = Split(evolve=tuple(cases[:5]), holdout=tuple(cases[5:]), fresh=())
    ev = Evaluator(split, recording=recording, base=BASE, journal=journal)
    ev.score(BASE, "evolve")
    assert ev.holdout_reads == 0
    ev.score(BASE, "holdout")
    ev.score(BASE.with_threshold("adds_nothing", 0.45), "holdout")
    assert ev.holdout_reads == 2
    events = [e for e in journal.events if e["kind"] == "holdout_read"]
    assert [e["data"]["read"] for e in events] == [1, 2]
    assert events[1]["data"]["knobs"] == BASE.with_threshold("adds_nothing", 0.45).fingerprint()


def test_the_fresh_split_is_read_once(bench):
    cases, recording = bench
    ev = Evaluator(Split((), (), tuple(cases)), recording=recording, base=BASE)
    ev.score(BASE, "fresh")
    with pytest.raises(FreshSplitSpent):
        ev.score(BASE, "fresh")


def test_the_fresh_read_can_compare_snapshots_declared_together(bench):
    """Final against base is one read, declared up front; a third snapshot later is not."""
    cases, recording = bench
    ev = Evaluator(Split((), (), tuple(cases)), recording=recording, base=BASE)
    final = BASE.with_threshold("adds_nothing", 0.45)
    got_final, got_base = ev.score_fresh(final, BASE)
    assert (got_final.hits, got_base.hits) == (9, 8)
    assert got_final.part == got_base.part == "fresh"
    with pytest.raises(FreshSplitSpent):
        ev.score_fresh(BASE.with_threshold("adds_nothing", 0.40))
    with pytest.raises(ValueError):
        Evaluator(Split((), (), tuple(cases)), recording=recording, base=BASE).score_fresh()


def test_drift_flips_count_cases_within_reach_of_the_cut(bench):
    cases, recording = bench
    ev = Evaluator(_all_evolve(cases), recording=recording, base=BASE)
    assert ev.flips_under_drift(BASE, "evolve", 0.0) == 0
    assert ev.flips_under_drift(BASE, "evolve", 0.05) == 1  # 0.62 falls under 0.59
    assert ev.flips_under_drift(BASE, "evolve", 0.10) == 2  # and 0.50 rises over it


# --- noise floor --------------------------------------------------------------------------------


def test_drift_magnitude_is_a_nearest_rank_quantile_of_absolute_deltas():
    assert drift_magnitude(()) == 0.0
    measured = (0.09, -0.08, 0.02, 0.02, 0.02, 0.02)
    assert drift_magnitude(measured) == pytest.approx(0.09)
    assert drift_magnitude(measured, quantile=0.5) == pytest.approx(0.02)
    with pytest.raises(ValueError):
        drift_magnitude(measured, quantile=0.0)


def test_noise_floor_is_the_wilson_half_width_plus_the_drift_share():
    _, low, high = wilson(80, 100)
    floor = noise_floor(100, 0.80)
    assert floor.sampling == pytest.approx((high - low) / 2)
    assert floor.drift == 0.0
    assert floor.delta == pytest.approx(floor.sampling)
    with_drift = noise_floor(100, 0.80, drift_flips=3)
    assert with_drift.drift == pytest.approx(0.03)
    assert with_drift.delta == pytest.approx(floor.sampling + 0.03)


def test_noise_floor_edges():
    assert noise_floor(0, 0.0).delta == 1.0  # nothing measured: nothing admissible
    perfect = noise_floor(10_000, 1.0)
    assert perfect.delta >= 1 / 10_000  # never below one case
    with pytest.raises(ValueError):
        noise_floor(10, 1.5)


# --- admission ----------------------------------------------------------------------------------


def _edit() -> Edit:
    return Edit("threshold", "adds_nothing", 0.59, 0.45)


def test_admit_needs_a_gain_above_the_floor_within_cost_and_budget():
    ok = admit(
        0.90, 0.80, delta=0.05, cost_delta=0.0, beta0=0.0, beta1=0.0, edits=[_edit()], budget=1
    )
    assert isinstance(ok, Admission)
    assert ok.admitted and ok.reasons == ()
    assert ok.gain == pytest.approx(0.10)


def test_a_gain_equal_to_the_floor_is_not_admitted():
    at = admit(
        0.85, 0.80, delta=0.05, cost_delta=0.0, beta0=0.0, beta1=0.0, edits=[_edit()], budget=1
    )
    assert not at.admitted
    assert any("noise floor" in r for r in at.reasons)


def test_admit_collects_every_failed_reason():
    edits = [_edit(), Edit("threshold", "remember", 0.70, 0.65)]
    verdict = admit(
        0.70, 0.80, delta=0.05, cost_delta=0.01, beta0=0.0, beta1=0.01, edits=edits, budget=1
    )
    assert not verdict.admitted
    assert len(verdict.reasons) == 3
    joined = " ".join(verdict.reasons)
    assert "noise floor" in joined and "cost" in joined and "budget" in joined


def test_the_cost_rule_lets_extra_cost_buy_gain():
    edits = [_edit()]
    cheap = admit(
        0.95, 0.80, delta=0.05, cost_delta=0.002, beta0=0.001, beta1=0.01, edits=edits, budget=1
    )
    assert cheap.admitted  # allowance 0.001 + 0.01 * 0.15 = 0.0025
    dear = admit(
        0.95, 0.80, delta=0.05, cost_delta=0.003, beta0=0.001, beta1=0.01, edits=edits, budget=1
    )
    assert not dear.admitted


def test_admit_refuses_an_empty_edit_set():
    verdict = admit(0.9, 0.8, delta=0.0, cost_delta=0.0, beta0=0.0, beta1=0.0, edits=[], budget=3)
    assert not verdict.admitted


# --- edit budget ---------------------------------------------------------------------------------


def test_edit_budget_anneals_from_max_to_min_on_a_cosine():
    budgets = [edit_budget(r, 10, 5, 1) for r in range(10)]
    assert budgets[0] == 5 and budgets[-1] == 1
    assert all(a >= b for a, b in zip(budgets, budgets[1:], strict=False))
    assert edit_budget(4, 9, 5, 1) == 3  # the midpoint of a cosine is the mean
    assert edit_budget(0, 1, 5, 1) == 5


def test_edit_budget_rejects_nonsense():
    with pytest.raises(ValueError):
        edit_budget(10, 10, 5, 1)
    with pytest.raises(ValueError):
        edit_budget(0, 10, 1, 5)
    with pytest.raises(ValueError):
        edit_budget(0, 0, 5, 1)
    with pytest.raises(ValueError):
        edit_budget(0, 10, 5, 0)


# --- ledger --------------------------------------------------------------------------------------


def _record(ledger: Ledger, edits: list[Edit], verdict: str, candidate: float = 0.7) -> bool:
    return ledger.record(
        edits,
        incumbent=BASE.fingerprint(),
        part="evolve",
        candidate=candidate,
        incumbent_score=0.8,
        delta=0.05,
        verdict=verdict,
        reasons=("gain below the floor",) if verdict == "refuted" else (),
    )


def test_ledger_remembers_refuted_hypotheses_across_processes(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    edits = [_edit()]
    assert not ledger.already_refuted(edits)
    assert _record(ledger, edits, "refuted")
    assert ledger.already_refuted(edits)
    assert Ledger(path).already_refuted(edits)
    other = [Edit("threshold", "remember", 0.70, 0.65)]
    _record(ledger, other, "admitted", candidate=0.9)
    assert not ledger.already_refuted(other)


def test_ledger_is_idempotent(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path)
    assert _record(ledger, [_edit()], "refuted")
    assert not _record(ledger, [_edit()], "refuted")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert len(ledger.entries) == 1


def test_ledger_can_scope_a_refutation_to_its_incumbent():
    ledger = Ledger()
    _record(ledger, [_edit()], "refuted")
    assert ledger.already_refuted([_edit()], incumbent=BASE.fingerprint())
    other = BASE.with_threshold("remember", 0.65).fingerprint()
    assert not ledger.already_refuted([_edit()], incumbent=other)


def test_ledger_rejects_unknown_verdicts():
    with pytest.raises(ValueError):
        _record(Ledger(), [_edit()], "maybe")


# --- leak critic ---------------------------------------------------------------------------------

LEAK_CASES = [
    {
        "id": "mw-17",
        "point": "memory_write",
        "input": {"fact": "Inversiones Delta paid the fine of 1,240 euros on 3 March"},
        "expected": "store",
    }
]


def test_threshold_and_flag_edits_cannot_leak():
    assert leak_check(_edit(), LEAK_CASES).ok
    assert leak_check(Edit("flag", "scan_untrusted", True, False), LEAK_CASES).ok


def test_a_question_that_quotes_a_case_is_a_leak():
    edit = Edit("question", "memory_write:durable", None, "Store it if it says paid the fine of")
    check = leak_check(edit, LEAK_CASES)
    assert not check.ok
    assert "paid the fine of" in check.ngrams


def test_a_number_a_name_or_an_id_from_the_bench_is_a_leak():
    for text in (
        "Treat amounts like 1,240 as durable",
        "Payments by Inversiones Delta are durable",
        "Remember what case mw-17 shows",
    ):
        check = leak_check(Edit("about", "mail", "mail", text), LEAK_CASES)
        assert not check.ok, text
        assert check.literals


def test_generic_wording_is_not_a_leak():
    edit = Edit(
        "question",
        "memory_write:durable",
        None,
        "Will this fact still matter to the client's work next month?",
    )
    assert leak_check(edit, LEAK_CASES).ok


def test_an_ngram_the_old_text_already_had_is_not_introduced_by_the_edit():
    before = "Keep a record when someone paid the fine of a court"
    edit = Edit("about", "legal", before, before + " or a regulator")
    assert leak_check(edit, LEAK_CASES).ok


def test_leak_check_needs_ngrams_of_four_or_more():
    with pytest.raises(ValueError):
        leak_check(_edit(), LEAK_CASES, n=3)


# --- dormant gates -------------------------------------------------------------------------------


def _decision_event(point: str, **outcome: Any) -> dict[str, Any]:
    return {
        "kind": "decision",
        "data": {"point": point, "provider": "jev", "error": None, "outcome": outcome},
    }


def test_a_gate_that_never_acted_is_reported_not_removed():
    events = [_decision_event("redundant_page", drop=False) for _ in range(60)]
    events += [_decision_event("recall", look=bool(i % 2)) for i in range(60)]
    events += [_decision_event("guard", denied=False) for _ in range(10)]  # too few
    gates = dormant_gates(events, min_decisions=50)
    assert [(g.point, g.kind) for g in gates] == [("redundant_page", "never_acts")]
    assert gates[0].decisions == 60


def test_a_gate_that_always_acts_is_reported_as_such():
    data = [
        {"point": "extract_gate", "provider": "jev", "error": None, "outcome": {"extract": False}}
        for _ in range(50)
    ]
    gates = dormant_gates(data, min_decisions=50)
    assert [(g.point, g.kind, g.value) for g in gates] == [("extract_gate", "always_acts", False)]


def test_failed_and_code_decisions_do_not_count_as_evidence():
    events = [_decision_event("redundant_page", drop=False) for _ in range(40)]
    events += [
        {
            "kind": "decision",
            "data": {
                "point": "redundant_page",
                "provider": "jev",
                "error": "timeout",
                "outcome": {"drop": False},
            },
        }
        for _ in range(20)
    ]
    events += [{"kind": "warning", "data": {"message": "x"}}]
    assert dormant_gates(events, min_decisions=50) == ()


def test_dormant_gates_reads_a_real_squire_journal():
    quiet = {"kind": "truth", "truth": 0.1, "confidence": 0.8, "probabilities": {}}
    # The unused exact entry keeps the recording truthy: `Squire.__init__` reads
    # `decider or NullDecider()`, and a RecordedDecider with only default entries has len 0.
    recording = RecordedDecider(
        [
            {
                "point": "loop",
                "default": True,
                "answers": {"goal_met": quiet, "repeats_check": quiet},
            },
            {"key": "unused", "point": "none", "answers": {}},
        ]
    )
    journal = MemoryJournal()
    squire = Squire(recording, journal=journal)

    async def run() -> None:
        for _ in range(5):
            await squire.check_loop(goal="g", done="d")

    asyncio.run(run())
    gates = dormant_gates(journal.events, min_decisions=5)
    assert [(g.point, g.kind) for g in gates] == [("loop", "never_acts")]


# --- the fifty-case bench, replayed -------------------------------------------------------------

FIFTY = ["loop-b.jsonl", "memory-b.jsonl", "graph-build-b.jsonl", "retrieval-b.jsonl"]
FIFTY_FIXTURE = ROOT / "fixtures" / "new-points-50-v2.jsonl"


@pytest.fixture(scope="module")
def fifty():
    from sanchopanza.eval.bench import load_cases

    if not FIFTY_FIXTURE.exists() or not all((ROOT / "benches" / f).exists() for f in FIFTY):
        pytest.skip("fifty-case benches or fixture not present")
    return load_cases(ROOT / "benches" / f for f in FIFTY)


def test_the_evaluator_reproduces_the_published_fifty_bench(fifty):
    ev = Evaluator(
        Split(tuple(fifty), (), ()),
        recording=RecordedDecider.from_file(FIFTY_FIXTURE),
        base=BASE,
    )
    score = ev.score(BASE, "evolve")
    assert (score.hits, score.n, score.misses) == (200, 212, 0)
    assert score.per_point["redundant_page"] == (33, 34)
    old = ev.score(BASE.with_threshold("adds_nothing", 0.80), "evolve")
    assert old.per_point["redundant_page"] == (26, 34)  # the knob it shared until 2026-09-24


def test_the_loop_bench_exercises_saturated(fifty):
    """goal_met and repeats_check are scored at the policy's `saturated` since 2026-09-25
    (they were scored at 0.5 before, and this test pinned that the knob was inert)."""
    ev = Evaluator(
        Split(tuple(fifty), (), ()),
        recording=RecordedDecider.from_file(FIFTY_FIXTURE),
        base=BASE,
    )
    assert (
        ev.score(BASE.with_threshold("saturated", 0.95), "evolve").outcomes
        != ev.score(BASE, "evolve").outcomes
    )


def test_split_sizes_on_the_fifty_bench_are_stable(fifty):
    split = Split.by_hash(fifty, holdout=0.25, fresh=0.25)
    sizes = (len(split.evolve), len(split.holdout), len(split.fresh))
    assert sum(sizes) == 212
    assert sizes == Split.by_hash(fifty, holdout=0.25, fresh=0.25).sizes
    assert all(size > 0 for size in sizes)


def test_decisions_without_answers_are_not_evidence_of_a_dormant_gate():
    events = [
        {
            "kind": "decision",
            "data": {
                "point": "loop",
                "provider": "recorded",
                "error": None,
                "answers": {},
                "outcome": {"message": None},
            },
        }
        for _ in range(60)
    ]
    assert dormant_gates(events, min_decisions=50) == ()
