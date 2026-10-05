"""Browse, development: free-task sessions with mixed outcomes, to calibrate a "cut losses" lever.

python benchmarks/browse/free_calib.py --plan          # free: the order it would run, no model
python benchmarks/browse/free_calib.py --smoke         # the plan's first Haiku AB session
python benchmarks/browse/free_calib.py --live          # the phase, under its ceiling
python benchmarks/browse/free_calib.py                 # free: the report so far

The pilot (`free_e2e.py --pilot`) gave Sonnet five BrowseComp tasks and five failures, each at
its cap. A failing free session spends its whole budget searching in circles, and a cheap
decision mid-session that says "this is not converging" could replace turns that buy nothing.
To place such a cut it needs sessions that go both ways in the same arm, so this phase runs:

- AssistantBench dev, every short-answer task, Sonnet (cap 1.50 USD) and Haiku (cap 0.60);
- BrowseComp, ten tasks the pilot did not run, Haiku (cap 0.40).

The three streams are interleaved in proportion, so a ceiling stop cuts all three alike (the
pilot ran all of BrowseComp first and never reached AssistantBench). Same session as the pilot
(`free_e2e.one_session`: the question, the ANSWER instruction, Claude Code's normal tools, no
hook), and each row also keeps the session's cost trajectory call by call, its web tool counts
and whether it opened the browser (`free_trace.summary`), for the offline cut analysis
(`free_cut.py`). No hook runs here: this phase only records.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


free = _load("browse_free_e2e", HERE / "free_e2e.py")
phase = free.nav.phase
SESSIONS = free.RESULTS / "calib-sessions.jsonl"
REPORT = free.RESULTS / "calib.json"
CEILING_USD = 40.0
CAPS = {("SONNET", "AB"): 1.50, ("HAIKU", "AB"): 0.60, ("HAIKU", "BC"): 0.40}
RESERVE_USD = max(CAPS.values())  # the ceiling keeps the largest cap free before each session
PILOT_BC = frozenset({"BC57", "BC1248", "BC10", "BC693", "BC293"})
N_BC = 10


def cap_for(arm: str, tid: str) -> float:
    return CAPS[(arm, tid[:2])]


def interleave(streams: Sequence[Sequence[Any]]) -> list[Any]:
    """Every item of every stream, spread in proportion: item k of a stream of n sits at
    (k + 0.5) / n of the way through. Order within a stream is kept; ties go to the earlier
    stream."""
    keyed = [
        ((k + 0.5) / len(stream), j, k, item)
        for j, stream in enumerate(streams)
        for k, item in enumerate(stream)
    ]
    return [item for *_, item in sorted(keyed, key=lambda x: x[:3])]


def fresh_browsecomp(n: int, exclude: frozenset[str]) -> list[dict[str, str]]:
    """n BrowseComp tasks from the runner's seeded sample, none of `exclude`."""
    k = n + len(exclude)
    while True:
        picked = [t for t in free.browsecomp(k) if t["tid"] not in exclude][:n]
        if len(picked) == n:
            return picked
        k += n


def plan() -> list[tuple]:
    """(index, task, run, arm) for `phase.run_phase`, interleaved."""
    ab = [(t["tid"], "", t["question"], t["gold"]) for t in free.assistantbench(100)]
    bc = [(t["tid"], "", t["question"], t["gold"]) for t in fresh_browsecomp(N_BC, PILOT_BC)]
    streams = [[(t, "SONNET") for t in ab], [(t, "HAIKU") for t in ab], [(t, "HAIKU") for t in bc]]
    return [(i, task, 1, arm) for i, (task, arm) in enumerate(interleave(streams))]


def session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    return free.one_session(task, run, arm, session_max_usd=cap_for(arm, task[0]))


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = free.report(rows)
    spent = sum(r["list_usd"] for r in rows)
    return {"sessions": len(rows), "list_usd": round(spent, 2), "by_arm": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--live", action="store_true")
    args = ap.parse_args()
    free.RESULTS.mkdir(parents=True, exist_ok=True)
    steps = plan()
    if args.plan:
        for i, task, _run, arm in steps:
            print(i, task[0], arm, cap_for(arm, task[0]))
        return 0
    rows = free.nav.done_sessions(SESSIONS)
    limits = phase.Limits(session_max_usd=RESERVE_USD, ceiling_usd=CEILING_USD)
    code = 0
    if args.smoke:
        # The first Haiku AssistantBench step of the plan, as itself: a live run skips it after.
        first = next(s for s in steps if s[3] == "HAIKU" and s[1][0].startswith("AB"))
        code, rows = phase.run_phase([first], rows, limits, session, SESSIONS)
    elif args.live:
        code, rows = phase.run_phase(steps, rows, limits, session, SESSIONS)
    counted = phase.counted(rows)
    if counted:
        result = report(counted)
        REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
