"""Browse, development: Jev's ranking with unnamed elements described (classes, holder).

python benchmarks/browse/hints_jev.py --live --env-file PATH/.env   # new calls only, <= 1 USD
python benchmarks/browse/hints_jev.py                               # free: replays both fixtures

Phase 1's development steps, read by the current reader (`steps-hints.jsonl`, see `hints.py`)
against the same steps as Phase 1 read them. A call whose group of elements did not change is
served from Phase 1's recording; only groups holding a changed line are asked, and recorded in
`fixtures/browse-jev-hints.jsonl`. Development data: a gain here goes to new steps before it
is claimed.
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
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase1 = _load("browse_run", HERE / "run.py")
HINTS_STEPS = phase1.STEPS.with_name("steps-hints.jsonl")
HINTS_FIXTURE = ROOT / "fixtures" / "browse-jev-hints.jsonl"
CEILING_USD = 1.00
MODES = {
    "dev": {"steps": phase1.STEPS, "hinted": HINTS_STEPS, "base": phase1.FIXTURE,
            "fixture": HINTS_FIXTURE, "out": "hints-jev-dev"},
    "confirm": {"steps": phase1.CONFIRM_STEPS,
                "hinted": phase1.CONFIRM_STEPS.with_name("steps-confirm-hints.jsonl"),
                "base": phase1.CONFIRM_FIXTURE,
                "fixture": ROOT / "fixtures" / "browse-jev-hints-confirm.jsonl",
                "out": "hints-jev-confirm", "prereg": phase1.RESULTS / "prereg-hints.md"},
}  # fmt: skip


class Chain:
    """Phase 1's recording, then this run's; an empty answer means neither holds the call."""

    name = "jev"

    def __init__(self, *recordings: Any) -> None:
        self._recordings = recordings

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        decision = None
        for recording in self._recordings:
            decision = await recording.decide(point, state, questions)
            if decision.answers:
                return decision
        return (
            decision
            if decision is not None
            else await RecordedDecider([]).decide(point, state, questions)
        )


def spent(fixture: pathlib.Path = HINTS_FIXTURE) -> float:
    if not fixture.exists():
        return 0.0
    rows = fixture.read_text(encoding="utf-8").splitlines()
    return sum(float(json.loads(x).get("cost_usd") or 0.0) for x in rows if x.strip())


class Ceiling:
    def __init__(self, live: bool, fixture: pathlib.Path) -> None:
        self.live = live
        self.fixture = fixture

    def check(self) -> None:
        if self.live and spent(self.fixture) >= CEILING_USD:
            used = spent(self.fixture)
            raise SystemExit(f"Jev ceiling reached: {used:.4f} of {CEILING_USD:.2f} USD")


def load(path: pathlib.Path) -> list[dict[str, Any]]:
    phase1.STEPS = path
    return phase1.load_steps()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--confirm", action="store_true", help="prereg-hints.md: new steps")
    ap.add_argument("--record-hash", action="store_true")
    args = ap.parse_args()
    mode = MODES["confirm" if args.confirm else "dev"]
    if args.record_hash:
        prereg = MODES["confirm"]["prereg"]
        digest = phase1.digest(prereg)
        prereg.with_suffix(".sha256").write_text(digest + "\n", encoding="utf-8")
        print(prereg.name, phase1.digest(prereg))
        return 0
    if args.live and args.confirm:
        phase1.require_prereg(mode["prereg"])
    old_steps = load(mode["steps"])
    new_steps = load(mode["hinted"])
    live = None
    if args.live:
        key = phase1.key_from(args.env_file)
        live = RecordingDecider(create("jev", api_key=key), mode["fixture"])
    hinted = Chain(phase1.InOrder(mode["base"]), phase1.InOrder(mode["fixture"]))
    replay = phase1.ReplayFirst(hinted, live)

    async def both() -> dict[str, list[dict[str, Any]]]:
        before = await phase1.run_arm(
            "JEV-BLEND", old_steps, phase1.InOrder(mode["base"]), phase1.Ceiling(0.0, live=False)
        )
        ceiling = Ceiling(args.live, mode["fixture"])
        after = await phase1.run_arm("JEV-BLEND", new_steps, replay, ceiling)
        return {"BEFORE": before, "HINTS": after}

    by_arm = asyncio.run(both())
    before, after = by_arm["BEFORE"], by_arm["HINTS"]
    if [r["id"] for r in before] != [r["id"] for r in after]:
        raise SystemExit("the two step files are not in the same order: nothing compared")
    report: dict[str, Any] = {"steps": len(after), "dev": not args.confirm}
    for arm, rows in by_arm.items():
        report[arm] = {f"recall@{k}": round(phase1.recall(rows, k), 4) for k in phase1.KS} | {
            "usd_per_step": round(sum(r["cost_usd"] for r in rows) / len(rows), 6)
        }
    for k in (10, 20):
        report[f"HINTS-minus-BEFORE@{k}"] = {
            "value": round(phase1.recall(after, k) - phase1.recall(before, k), 4),
            "bootstrap95": phase1.bootstrap(after, before, k),
        }
    report["live_calls"], report["missing"] = replay.asked, replay.missing
    report["jev_usd_spent"] = round(spent(mode["fixture"]), 4)
    out = phase1.RESULTS / f"{mode['out']}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    (phase1.RESULTS / f"{mode['out']}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for arm in by_arm.values() for r in arm), encoding="utf-8"
    )
    print(json.dumps(report, indent=1))
    return 1 if replay.missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
