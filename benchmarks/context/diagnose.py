"""Where the decider arms lose NEEDED results, from the recordings. Free: replay only.

    python benchmarks/context/diagnose.py

Replays both decider arms from ~/.cache/sanchopanza/context/recordings/ (a replay that misses
a recording is counted and reported, never sent anywhere) and writes aggregates to
`docs/results/2026-09-28-context/diagnosis.json`:

- per asked result, the probability the decider gave against the NEEDED label: ROC AUC with a
  95 % bootstrap interval over units, and the p distribution for needed and not needed;
- for sanchopanza, where each NEEDED result was lost: stubbed by a rule, eliminated in the
  tournament's first round (p < `FIRST_ROUND_CUT`), or below `context_keep` in the final;
- the same AUC for the fastjev replica's result question (`result_tN`).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import random
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))


def sibling(name: str):
    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


run = sibling("run")
arms = sibling("arms")

from sanchopanza.context import compact  # noqa: E402
from sanchopanza.context.rules import triage_rules  # noqa: E402
from sanchopanza.points import context as points  # noqa: E402
from sanchopanza.providers import RecordedDecider  # noqa: E402

OUT = run.RESULTS / "diagnosis.json"
BOOT = 2000
SEED = 20260928
BINS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.01)


def auc(pairs: Sequence[tuple[float, bool]]) -> float | None:
    """Mann-Whitney AUC: P(p of a needed result > p of a not-needed one), ties half."""
    pos = [p for p, y in pairs if y]
    neg = [p for p, y in pairs if not y]
    if not pos or not neg:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def auc_ci(units: Sequence[list[tuple[float, bool]]]) -> list[float] | None:
    rng = random.Random(SEED)
    values = []
    for _ in range(BOOT):
        sample = [p for _ in units for p in units[rng.randrange(len(units))]]
        value = auc(sample)
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    return [round(values[int(0.025 * len(values))], 3), round(values[int(0.975 * len(values))], 3)]


def histogram(pairs: Sequence[tuple[float, bool]]) -> dict[str, dict[str, int]]:
    out = {}
    for label, want in (("needed", True), ("not_needed", False)):
        ps = [p for p, y in pairs if y == want]
        out[label] = {
            f"[{lo:.2f},{min(hi, 1.0):.2f})": sum(lo <= p < hi for p in ps)
            for lo, hi in zip(BINS, BINS[1:], strict=False)
        }
    return out


class Spy:
    """Captures the tournament of each sanchopanza plan: ids asked, first and final p."""

    def __init__(self) -> None:
        self.last: Any = None
        self._real = compact.hierarchy.tournament

    async def tournament(self, n, judge, **kw):
        result = await self._real(n, judge, **kw)
        self.last = result
        return result


async def sanchopanza_unit(unit, squire, spy) -> dict[str, Any]:
    history = unit["history"]
    calls = run.calls_of(history)
    verdicts = triage_rules(history, calls)
    ask = [c.id for c in calls if verdicts[c.id].action == "ask"]
    spy.last = None
    await squire.prune_context(history)
    needed = {k: v["needed"] for k, v in unit["labels"].items()}
    stages: Counter = Counter()
    pairs: list[tuple[float, bool]] = []
    first_pairs: list[tuple[float, bool]] = []
    for c in calls:
        if needed[c.id] and verdicts[c.id].action == "stub":
            stages["rule:" + verdicts[c.id].reason] += 1
    pages = spy.last.pages if spy.last is not None else []
    rounds = spy.last.rounds if spy.last is not None else 0
    for cid, v in zip(ask, pages, strict=True):
        p = v.last if v.last is not None else v.first
        if p is not None:
            pairs.append((p, needed[cid]))
        if v.first is not None:
            first_pairs.append((v.first, needed[cid]))
        if not needed[cid]:
            continue
        if v.final is None and rounds:
            stages["tournament_first_round"] += 1
        elif not v.keep:
            stages["final_cut"] += 1
        else:
            stages["kept"] += 1
    return {
        "pairs": pairs,
        "first_pairs": first_pairs,
        "stages": stages,
        "asked": len(ask),
        "rounds": rounds,
        "unanswered": sum(v.last is None for v in pages),
    }


async def fastjev_unit(unit, squire) -> list[tuple[float, bool]]:
    history = unit["history"]
    plan = await compact.plan(squire, history, arm="fastjev")
    needed = {k: v["needed"] for k, v in unit["labels"].items()}
    return [(s.probability, needed[s.id]) for s in plan.steps if s.reason != "pinned"]


async def main_async() -> dict[str, Any]:
    units = run.load(run.CACHE / "dataset", "all")
    spy = Spy()
    compact.hierarchy.tournament = spy.tournament
    ours = arms.squire_for(
        RecordedDecider.from_file(run.RECORDINGS / "sanchopanza.jsonl"), max_usd=1.0
    )
    theirs = arms.squire_for(
        RecordedDecider.from_file(run.RECORDINGS / "fastjev.jsonl"), max_usd=1.0
    )
    report: dict[str, Any] = {"first_round_cut": points.FIRST_ROUND_CUT}
    for split in ("dev", "test"):
        part = [u for u in units if u["split"] == split]
        sp = [await sanchopanza_unit(u, ours, spy) for u in part]
        fj = [await fastjev_unit(u, theirs) for u in part]
        pairs = [p for r in sp for p in r["pairs"]]
        firsts = [p for r in sp for p in r["first_pairs"]]
        fj_pairs = [p for r in fj for p in r]
        stages = sum((r["stages"] for r in sp), Counter())
        report[split] = {
            "sanchopanza": {
                "asked": sum(r["asked"] for r in sp),
                "asked_needed": sum(y for _, y in pairs),
                "units_with_tournament": sum(r["rounds"] > 0 for r in sp),
                "unanswered": sum(r["unanswered"] for r in sp),
                "auc_last_p": _round(auc(pairs)),
                "auc_last_p_ci": auc_ci([r["pairs"] for r in sp]),
                "auc_first_round_p": _round(auc(firsts)),
                "auc_first_round_p_ci": auc_ci([r["first_pairs"] for r in sp]),
                "p_histogram": histogram(pairs),
                "needed_by_stage": dict(stages),
            },
            "fastjev_result_question": {
                "asked": len(fj_pairs),
                "asked_needed": sum(y for _, y in fj_pairs),
                "auc": _round(auc(fj_pairs)),
                "auc_ci": auc_ci(fj),
                "p_histogram": histogram(fj_pairs),
            },
        }
    report["replay_misses"] = {
        "sanchopanza_spent": ours.meter.cost_usd,
        "fastjev_spent": theirs.meter.cost_usd,
    }
    return report


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 3)


def main() -> None:
    report = asyncio.run(main_async())
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
