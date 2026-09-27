"""The tournament asks some groups twice; remembering them saves the calls (free, replay only).

python benchmarks/lateral/memo/run.py --qasper QASPER-TEST.jsonl [--hotpot HOTPOT.jsonl]

`hierarchy.tournament` regroups the survivors of each round in order. When a round prunes a
little, and only from later groups, the first group of the next round can be the same pages in
the same order as a group already judged: the same state, asked again. The 2026-09-27 fix
covers the round that prunes nothing; this case is left. Jev is not deterministic, so the
repeat buys only noise, costs a call, and makes a replay walk a different path from the live
run (it happened on 2026-09-28: the live confirmation made 855 tournament calls, its replay
853).

`memoize` wraps a judge so that a group already judged returns its first answers. Replayed on
every recorded tournament in the repository, it must keep exactly the same pages and make fewer
calls: that is what this script checks. No network: a question whose calls are not all recorded
stops the script.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


from sanchopanza import Thresholds  # noqa: E402
from sanchopanza.points import chunks, hierarchy  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-28-lateral-memo"


def memoize(judge: hierarchy.Judge) -> hierarchy.Judge:
    """The candidate change: a group of pages already judged is not judged again."""
    seen: dict[tuple[int, ...], list[float | None]] = {}

    async def remembered(ids: Sequence[int]) -> list[float | None]:
        key = tuple(ids)
        if key not in seen:
            seen[key] = list(await judge(ids))
        return list(seen[key])

    return remembered


async def one(
    question: str, pages: Sequence[tuple[str, str]], decider: Any, point: str, memo: bool
) -> tuple[list[bool], int, int]:
    t = Thresholds()
    asked = {"calls": 0, "missing": 0}

    async def judge(ids: Sequence[int]) -> list[float | None]:
        state, qs = chunks.context_questions(purpose=question, pages=[pages[i] for i in ids])
        decision = await decider.decide(point, state, qs)
        asked["calls"] += 1
        asked["missing"] += not decision.answers
        return [decision.answer(chunks.page_id(k)).truth for k in range(len(ids))]

    result = await hierarchy.tournament(
        len(pages),
        memoize(judge) if memo else judge,
        size=chunks.PAGE_MAX,
        first_cut=t.pages_first_round,
        final_cut=t.pages_in_context,
    )
    return [v.keep for v in result.pages], asked["calls"], asked["missing"]


def compare(name: str, rows: list[dict[str, Any]], fixture: pathlib.Path, point: str) -> dict:
    decider = RecordedDecider.from_file(fixture)

    async def run() -> list[tuple[Any, Any]]:
        out = []
        for row in rows:
            plain = await one(row["question"], row["pages"], decider, point, memo=False)
            memo = await one(row["question"], row["pages"], decider, point, memo=True)
            out.append((plain, memo))
        return out

    pairs = asyncio.run(run())
    missing = sum(p[2] + m[2] for p, m in pairs)
    if missing:
        raise SystemExit(f"{name}: {missing} calls not in {fixture.name}")
    plain_calls = sum(p[1] for p, _ in pairs)
    memo_calls = sum(m[1] for _, m in pairs)
    return {
        "questions": len(rows),
        "calls_as_shipped": plain_calls,
        "calls_memoized": memo_calls,
        "repeated_calls": plain_calls - memo_calls,
        "questions_with_a_repeat": sum(p[1] > m[1] for p, m in pairs),
        "same_pages_kept": sum(p[0] == m[0] for p, m in pairs),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qasper", required=True)
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    qasper = pathlib.Path(args.qasper)
    ld = _load("longdocs_run", ROOT / "benchmarks" / "longdocs" / "run.py")
    confirm = _load("wholedocs_confirm", HERE.parent / "wholedocs" / "confirm.py")
    report = {
        "longdocs_2026_09_27": compare("longdocs", ld.build(qasper), ld.FIXTURE, "triage_pages"),
        "wholedocs_2026_09_28": compare(
            "wholedocs", confirm.build(qasper), confirm.FIXTURE, "triage_pages"
        ),
    }
    if args.hotpot:
        hier = _load("hierarchy_run", ROOT / "benchmarks" / "hierarchy" / "run.py")
        # The 200 held-out questions: `tests/test_hierarchy_bench.py` shows `triage_many`
        # replays them exactly; one derivation question needs calls the bench never made.
        rows = hier.build(pathlib.Path(args.hotpot))[hier.DERIVATION :]
        report["hierarchy_2026_09_27_held_out"] = compare(
            "hierarchy", rows, hier.FIXTURE, "hierarchy_context"
        )
    if args.write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
