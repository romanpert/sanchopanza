"""Browse, Phase 1e: the description of unnamed elements, with the noise of asking again removed.

python benchmarks/browse/hints_reask.py --record-hash
python benchmarks/browse/hints_reask.py --live --env-file PATH/.env   # <= 1 USD of Jev
python benchmarks/browse/hints_reask.py                               # free: replays

Phase 1d compared DESCRIBED (every group holding a changed line asked again) with BEFORE (every
call replayed from Phase 1c). A group asked again answers differently even when nothing in it
changed, so the difference mixed the description with the noise of asking again. REASK is
BEFORE's reading with exactly the calls DESCRIBED asked again, asked again too: the calls
DESCRIBED served from Phase 1c's recording are served the same way, the others go live. DESCRIBED
minus REASK is the description alone.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordingDecider, key_of  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hints = _load("browse_hints_jev", HERE / "hints_jev.py")
phase1 = hints.phase1
MODE = hints.MODES["confirm"]
PREREG = phase1.RESULTS / "prereg-hints-reask.md"
FIXTURE = ROOT / "fixtures" / "browse-jev-hints-reask.jsonl"
CEILING_USD = 1.00


class Watch:
    """A decider that notes the keys its first recording answered."""

    name = "jev"

    def __init__(self, first: Any, rest: Any) -> None:
        self._first, self._rest = first, rest
        self.reused: set[str] = set()

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        decision = await self._first.decide(point, state, questions)
        if decision.answers:
            self.reused.add(key_of(point, state, questions))
            return decision
        return await self._rest.decide(point, state, questions)


class Split:
    """Keys in `reused` from the recording; every other call asked again (live, recorded)."""

    name = "jev"

    def __init__(self, reused: set[str], recorded: Any, again: Any) -> None:
        self._reused, self._recorded, self._again = reused, recorded, again

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        if key_of(point, state, questions) in self._reused:
            return await self._recorded.decide(point, state, questions)
        return await self._again.decide(point, state, questions)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--record-hash", action="store_true")
    args = ap.parse_args()
    if args.record_hash:
        digest = phase1.digest(PREREG)
        PREREG.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
        print(PREREG.name, digest)
        return 0
    if args.live:
        phase1.require_prereg(PREREG)
    old_steps = hints.load(MODE["steps"])
    new_steps = hints.load(MODE["hinted"])
    watch = Watch(phase1.InOrder(MODE["base"]), phase1.InOrder(MODE["fixture"]))
    live = None
    if args.live:
        live = RecordingDecider(create("jev", api_key=phase1.key_from(args.env_file)), FIXTURE)
    no_ceiling = phase1.Ceiling(0.0, live=False)

    async def arms() -> dict[str, list[dict[str, Any]]]:
        described = await phase1.run_arm("JEV-BLEND", new_steps, watch, no_ceiling)
        again = phase1.ReplayFirst(phase1.InOrder(FIXTURE), live)
        split = Split(watch.reused, phase1.InOrder(MODE["base"]), again)
        ceiling = hints.Ceiling(args.live, FIXTURE)
        reask = await phase1.run_arm("JEV-BLEND", old_steps, split, ceiling)
        return {"DESCRIBED": described, "REASK": reask, "_again": again}

    by_arm = asyncio.run(arms())
    again = by_arm.pop("_again")
    described, reask = by_arm["DESCRIBED"], by_arm["REASK"]
    if [r["id"] for r in described] != [r["id"] for r in reask]:
        raise SystemExit("the two step files are not in the same order: nothing compared")
    report: dict[str, Any] = {"steps": len(reask), "reused_calls": len(watch.reused)}
    for arm, rows in by_arm.items():
        report[arm] = {f"recall@{k}": round(phase1.recall(rows, k), 4) for k in phase1.KS}
    for k in (10, 20):
        report[f"DESCRIBED-minus-REASK@{k}"] = {
            "value": round(phase1.recall(described, k) - phase1.recall(reask, k), 4),
            "bootstrap95": phase1.bootstrap(described, reask, k),
        }
    report["live_calls"], report["missing"] = again.asked, again.missing
    report["jev_usd_spent"] = round(hints.spent(FIXTURE), 4)
    (phase1.RESULTS / "hints-reask.json").write_text(json.dumps(report, indent=1), "utf-8")
    (phase1.RESULTS / "hints-reask.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for rows in by_arm.values() for r in rows), "utf-8"
    )
    print(json.dumps(report, indent=1))
    return 1 if again.missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
