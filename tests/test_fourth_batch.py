"""The points that had no sample, replayed from `fixtures/fourth-batch.jsonl`.

`facts`, `edge` and `memory_collision` went to 50 cases each on 2026-09-24. Before that they
had 20, 20 and 16, and two of them shipped with a disclaimer in the README for that reason.

These tests pin what the bigger sample found, including the two things it took away.

**`edge` lost a published claim.** The README said "8 edges committed, 0 of them wrong", and
that was true of a bench whose `reversed` label had two instances. With eleven, the point
commits a backwards edge - `ed-26`, `(Industrias Belmonte, audita a, Marquez y Asociados)`
against a text that says the opposite - and that is the one error nothing downstream catches.
The number is pinned here so the claim cannot quietly come back.

**And `edge` gained a fix that cost nothing to verify.** `reversed` fired zero times out of
eleven, not because the model did not know but because `decide_edge` gated on `stated`'s
confidence before it ever read `direction`. On `ed-22` the same decision already carried
`direction` 0.05 at confidence 0.90. Reading the direction first, and refusing to commit when
the direction is in doubt, takes the point from 28/37 to 31/38 and finds 4 of the 11 - and it
is a **policy-only change measured by replaying the identical recorded answers**, so none of
that difference can be sampling.

**`memory_collision` is the good news and the reason to write cases for a label nobody has
tested.** Its `duplicate` branch had never fired in any run. With eight cases of it, it fires
eight times and is right eight times, and all four of the point's errors are `keep_both` -
the branch that stores both and asks nobody. Not one wrong `replace`, not one wrong
`duplicate`.

**`facts` is the one with a located defect.** It never confuses `conflict` with `unrelated`.
Its whole problem is that it cannot say `unrelated` at all: eight of ten such cases abstain
and two are called `agree`. The `unrelated` option is the only one of the three whose Choice
criteria carry no examples, which is the most likely cause and is not fixed here, because
fixing it on the cases that exposed it is how a bench stops measuring anything.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sanchopanza.eval.bench import load_cases, run_bench, summarize
from sanchopanza.providers import RecordedDecider

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "fourth-batch.jsonl"
FILES = ["graph.jsonl", "graph-c.jsonl", "memory.jsonl", "memory-d.jsonl", "graph-build.jsonl"]


# Skipping when nothing is present is right: a clone without this batch should not fail.
# Skipping when the RECORDING is present and a bench is not is wrong, and it is the only
# state that is unambiguously data loss - the run happened, so the bench existed. On
# 2026-09-24 a bench file in this list was overwritten by another session and these tests
# went green-by-skip instead of failing: losing a bench looked exactly like never having
# had one. A guard that cannot tell those apart is not a guard.
def _faltantes() -> list[str]:
    return [f for f in FILES if not (ROOT / "benches" / f).exists()]


@pytest.fixture(scope="module")
def run():
    faltan = _faltantes()
    if not FIXTURE.exists():
        pytest.skip("fourth-batch fixture not present")
    if faltan:
        pytest.fail(
            f"la grabacion {FIXTURE.name} existe pero faltan sus bancos: {faltan}. "
            "Esa combinacion solo puede significar que el banco se perdio despues de "
            "correrlo. No es un salto, es perdida de datos: restaura el fichero o borra "
            "la grabacion a proposito."
        )
    cases = load_cases(ROOT / "benches" / f for f in FILES)
    results = asyncio.run(run_bench(cases, RecordedDecider.from_file(FIXTURE)))
    return summarize(results), results


def test_the_three_points_reached_fifty_cases(run):
    points = run[0]["points"]
    for point in ("facts", "edge", "memory_collision"):
        assert points[point]["n"] == 50, point


def test_memory_collision_fires_every_branch_and_errs_only_into_keep_both(run):
    """The `duplicate` branch had never fired in any published run. It does now, 8 for 8."""
    summary, results = run
    rows = [r for r in results if getattr(r, "point", None) == "memory_collision"]
    assert summary["points"]["memory_collision"]["hits"] == 46
    emitted = {str(r.predicted) for r in rows}
    assert {"duplicate", "replace", "flag", "keep_both"} <= emitted
    duplicates = [r for r in rows if r.predicted == "duplicate"]
    assert len(duplicates) == 8 and all(r.expected == "duplicate" for r in duplicates)
    wrong = [r for r in rows if r.correct is False]
    assert len(wrong) == 4
    assert all(r.predicted == "keep_both" for r in wrong), [
        (r.id, r.predicted) for r in wrong if r.predicted != "keep_both"
    ]


def test_edge_commits_exactly_one_wrong_direction_edge(run):
    """The number that replaced "0 of them wrong". Raising it is a regression."""
    _, results = run
    edges = [r for r in results if getattr(r, "point", None) == "edge"]
    committed = [r for r in edges if r.predicted == "supported"]
    wrong = [r for r in committed if r.expected != "supported"]
    assert len(committed) == 17
    assert [r.id for r in wrong] == ["ed-26"]


def test_reading_the_direction_first_is_what_finds_a_reversed_edge(run):
    """Zero of eleven before the gate order was fixed, four after, same recorded answers."""
    _, results = run
    reversed_cases = [
        r for r in results if getattr(r, "point", None) == "edge" and r.expected == "reversed"
    ]
    assert len(reversed_cases) == 11
    caught = [r for r in reversed_cases if r.predicted == "reversed"]
    assert len(caught) == 4
    # and the ones it still misses go somewhere harmless, except the one pinned above
    assert {str(r.predicted) for r in reversed_cases if r not in caught} <= {
        "review",
        "unsupported",
        "supported",
    }


def test_facts_cannot_say_unrelated_and_that_is_the_whole_defect(run):
    """It never confuses conflict with unrelated. It just never reaches `unrelated`."""
    _, results = run
    rows = [r for r in results if getattr(r, "point", None) == "facts"]
    unrelated = [r for r in rows if r.expected == "unrelated"]
    assert len(unrelated) == 12
    assert sum(1 for r in unrelated if r.predicted == "unrelated") <= 4
    # No conflict is ever called unrelated, and no unrelated is ever called conflict.
    assert not [r for r in rows if r.expected == "conflict" and r.predicted == "unrelated"]
    assert not [r for r in rows if r.expected == "unrelated" and r.predicted == "conflict"]
