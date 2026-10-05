"""The audit bench (`benchmarks/memory_carry/audit_bench.py`, `audit_judges.py`) with a fake
decider: the judges map answers back to the right rule whatever the option order, the scope gate
clears only a file-scoped rule held against other files, and the report counts sessions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sanchopanza.contract import Answer, Decision

from .helpers import bench_module

FOLDER = Path(__file__).resolve().parents[1] / "benchmarks" / "memory_carry"
judges = bench_module(FOLDER, "audit_judges")
bench = bench_module(FOLDER, "audit_bench")


def _session(sid: str, kept: bool = True, written: tuple[str, ...] = ("app/b.py",)) -> dict:
    rules = [{"text": f"rule {i} of {sid}", "files": [f"app/r{i}.py"], "own": i == 0}
             for i in range(8)]  # fmt: skip
    return {"id": sid, "scene": "s", "arm": "M", "own_kept": kept, "written": list(written),
            "change": "+++ b/app/b.py\n+x = 1\n", "rules": rules}  # fmt: skip


def _decision(key: str, answer: Answer) -> Decision:
    return Decision(point="p", answers={key: answer}, provider="fake", model="fake")


def test_order_is_a_permutation_and_moves_the_own_rule() -> None:
    orders = [judges._order(f"session-{n}", 8) for n in range(40)]
    assert all(sorted(o) == list(range(8)) for o in orders)
    assert len({o.index(0) for o in orders}) > 3


def test_all_in_view_maps_probabilities_back_to_rules() -> None:
    sessions = [_session("a"), _session("b")]

    async def decide(point: str, state: Any, questions: Any) -> Decision:
        options = questions["broken"].options
        # the option that quotes rule 3 gets 0.9, whatever its position
        probs = {k: (0.9 if "rule 3 of" in v else 0.0) for k, v in options.items()}
        return _decision("broken", Answer(kind="choice", confidence=0.8,
                                          choice=max(probs, key=probs.get),
                                          probabilities=probs))  # fmt: skip

    asyncio.run(judges.all_in_view(sessions, decide))
    for s in sessions:
        assert s["score"]["all"].index(0.9) == 3


def test_gate_clears_a_file_rule_only_away_from_its_file() -> None:
    near = _session("near", written=("app/r1.py",))
    far = _session("far")

    async def decide(point: str, state: Any, questions: Any) -> Decision:
        if "scope" in questions:  # every rule judged about its own file
            return _decision("scope", Answer(kind="truth", confidence=0.8, truth=0.1))
        probs = {"breaks": 0.8, "keeps": 0.1, "already": 0.05, "unrelated": 0.05}
        return _decision("relation", Answer(kind="choice", confidence=0.6, choice="breaks",
                                            probabilities=probs))  # fmt: skip

    asyncio.run(judges.JUDGES["gate_scoped"]([near, far], decide))
    assert near["score"]["gate_scoped"][1] == 0.8  # its rule's file was written
    assert near["score"]["gate_scoped"][2] == 0.0
    assert far["score"]["gate_scoped"] == [0.0] * 8


def test_report_counts_sessions() -> None:
    broken, clean = _session("x", kept=False), _session("y")
    broken["score"] = {"j": [0.9, 0.1, 0, 0, 0, 0, 0, 0]}
    clean["score"] = {"j": [0.0, 0.7, 0, 0, 0, 0, 0, 0]}
    r = bench.report("j", [broken, clean], 0.5)
    assert (r["caught"], r["missed"], r["false_lure"], r["false_own"]) == (1, 0, 1, 0)
    assert (r["delivered"], r["caught_delivered"]) == (1, 1)
    r = bench.report("j", [broken, clean], 0.95)
    assert (r["caught"], r["missed"], r["false_lure"]) == (0, 1, 0)


def test_unanswered_sessions_are_left_out() -> None:
    s = _session("z")
    s["score"] = {"j": [0.2, None, 0, 0, 0, 0, 0, 0]}
    assert bench.report("j", [s], 0.5)["sessions"] == 0
