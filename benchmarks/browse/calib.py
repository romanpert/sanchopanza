"""Browse, phase 4a (development, free): when is the ranking sure enough to act on alone?

python benchmarks/browse/calib.py              # replays Phases 1 and 1c, spends nothing

The cascade needs a number, not a feeling. Two questions, both answerable from rankings
already paid for and recorded in `fixtures/browse-jev.jsonl` (Phase 1's 169 development
steps) and `fixtures/browse-jev-confirm.jsonl` (Phase 1c's 142 confirmation steps):

1. **Is there a cut above which the top element is the right one?** If `p1 >= c` implies the
   target is first often enough, those steps need no model at all: the loop clicks.
2. **Is there a cut below which the shortlist is probably missing the target?** Those are the
   steps to escalate: show the whole page to the large model instead of the top 20.

Both are derived on the development steps and read off the confirmation steps, which were
already used once for the published recalls: this is a development measure and claims nothing
on its own. What it decides is the design of the live phase, and whether the cascade has a
lever at all.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.browse import BLEND, Element, rank  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-02-browse-nav"
KEEP = 50
CONCURRENT = 8
CUTS = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase1 = _load("browse_run", HERE / "run.py")


async def one(step: dict[str, Any], decider: Any, gate: asyncio.Semaphore) -> dict[str, Any]:
    elements = [Element.from_dict(e) for e in step["elements"]]
    positives = set(step["positives"])
    async with gate:
        squire = Squire(decider, thresholds=Thresholds(max_usd=0.05, max_decisions=80))
        ranked = await rank(
            step["task"], elements, squire=squire, done=step["previous"], keep=KEEP, blend=BLEND
        )
    ps = [r.p for r in ranked if r.p is not None]
    return {
        "id": step["id"],
        "split": step["split"],
        "elements": len(elements),
        "position": phase1.position(ranked, positives),
        "p1": ps[0] if ps else None,
        "p2": ps[1] if len(ps) > 1 else None,
        "answered": len(ps),
        "cost_usd": squire.meter.cost_usd,
    }


async def rows_for(steps_path: pathlib.Path, fixture: pathlib.Path) -> list[dict[str, Any]]:
    phase1.STEPS = steps_path
    steps = phase1.load_steps()
    decider = phase1.InOrder(fixture)
    gate = asyncio.Semaphore(CONCURRENT)
    rows = await asyncio.gather(*(one(s, decider, gate) for s in steps))
    missing = [r["id"] for r in rows if r["p1"] is None]
    if missing:
        raise SystemExit(f"{len(missing)} steps have no recording in {fixture.name}: {missing[:3]}")
    return list(rows)


def act_alone(rows: list[dict[str, Any]], cut: float) -> dict[str, Any]:
    """Steps whose best element scores at least `cut`: how often it is the right one."""
    part = [r for r in rows if (r["p1"] or 0.0) >= cut]
    right = sum(r["position"] == 1 for r in part)
    return {
        "cut": cut,
        "steps": len(part),
        "coverage": round(len(part) / len(rows), 4),
        "top1_right": round(right / len(part), 4) if part else None,
        "wilson95": phase1.wilson(right, len(part)),
    }


def escalate(rows: list[dict[str, Any]], cut: float, k: int = 20) -> dict[str, Any]:
    """Steps below `cut`: how often the top k is missing the target (so the page is needed)."""
    low = [r for r in rows if (r["p1"] or 0.0) < cut]
    high = [r for r in rows if (r["p1"] or 0.0) >= cut]

    def inside(part: list[dict[str, Any]]) -> float | None:
        if not part:
            return None
        return round(
            sum(r["position"] is not None and r["position"] <= k for r in part) / len(part), 4
        )

    return {
        "cut": cut,
        "below": len(low),
        "in_top_k_below": inside(low),
        "in_top_k_above": inside(high),
        "k": k,
    }


def report(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    top1 = sum(r["position"] == 1 for r in rows)
    return {
        "set": name,
        "steps": n,
        "top1_overall": round(top1 / n, 4),
        "in_top_20_overall": round(
            sum(r["position"] is not None and r["position"] <= 20 for r in rows) / n, 4
        ),
        "p1_quartiles": [
            round(sorted(r["p1"] for r in rows)[int(q * (n - 1))], 4) for q in (0.25, 0.5, 0.75)
        ],
        "act_alone": [act_alone(rows, c) for c in CUTS],
        "escalate": [escalate(rows, c) for c in CUTS],
    }


async def main() -> int:
    dev = await rows_for(phase1.STEPS, phase1.FIXTURE)
    confirm = await rows_for(phase1.CONFIRM_STEPS, phase1.CONFIRM_FIXTURE)
    out = {
        # Nothing is spent here: `InOrder` serves recordings and never reaches a network. The
        # figure is what those calls cost when Phases 1 and 1c paid for them.
        "spent_now_usd": 0.0,
        "recorded_usd": round(sum(r["cost_usd"] for r in dev + confirm), 4),
        "development": report("phase 1 development steps", dev),
        "already_used": report("phase 1c confirmation steps (used once already)", confirm),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calib.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (OUT / "calib-rows.jsonl").write_text(
        "".join(json.dumps({**r, "set": s}) + "\n" for s, rs in
                (("dev", dev), ("used", confirm)) for r in rs),
        encoding="utf-8",
    )  # fmt: skip
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
