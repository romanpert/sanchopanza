"""Browse, phase 1: rank Mind2Web elements for the next action (`docs/results/2026-09-30-browse/`).

python benchmarks/browse/run.py --record-hash
python benchmarks/browse/run.py --live --env-file PATH/TO/.env     # spends Jev, records it
python benchmarks/browse/run.py                                    # free: replays the recording

Arms BM25, JEV and JEV-SHORT as registered in `prereg.md`. Every Jev call is recorded in
`fixtures/browse-jev.jsonl`; a replay reproduces the published numbers without a key.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import pathlib
import random
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.browse import BLEND, Element, rank  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-30-browse"
PREREG = RESULTS / "prereg.md"
FIXTURE = ROOT / "fixtures" / "browse-jev.jsonl"
STEPS = pathlib.Path.home() / ".cache" / "sanchopanza" / "mind2web" / "steps.jsonl"
CONFIRM_STEPS = STEPS.with_name("steps-confirm.jsonl")
CONFIRM_FIXTURE = ROOT / "fixtures" / "browse-jev-confirm.jsonl"
CONFIRM_PREREG = RESULTS / "prereg-confirm.md"
KS = (1, 5, 10, 20, 30)
KEEP = 50
SHORTLIST = 90
JEV_CEILING_USD = 1.50
CONCURRENT_STEPS = 3


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ReplayFirst = _load("triage_sets_run", ROOT / "benchmarks" / "triage_sets" / "run.py").ReplayFirst


def digest(path: pathlib.Path = PREREG) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg(path: pathlib.Path = PREREG) -> None:
    registered = path.with_suffix(".sha256")
    if not registered.exists() or registered.read_text().strip() != digest(path):
        raise SystemExit(f"{path.name} missing or changed since it was registered: nothing spent")


def recorded_spend() -> float:
    if not FIXTURE.exists():
        return 0.0
    return sum(
        float(json.loads(line).get("cost_usd") or 0.0)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


class InOrder:
    """A replay that serves a call recorded more than once in the order it was recorded.

    Jev is not deterministic, and five final-round calls of Phase 1 were asked twice live (once
    per arm: the JEV and JEV-SHORT arms can reach the same 30 finalists) with different answers.
    Each arm used the answer it got; a replay that served the first twice made the JEV-SHORT arm
    ask three calls the live run never made. Arms run in order, so the n-th use of a key gets
    the n-th recording of it (the last one past that). Empty recordings are skipped."""

    name = "jev"

    def __init__(self, path: pathlib.Path) -> None:
        self._queues: dict[str, list[RecordedDecider]] = {}
        self._used: dict[str, int] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line) if line.strip() else None
                if entry and entry.get("answers"):
                    self._queues.setdefault(entry["key"], []).append(RecordedDecider([entry]))

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        from sanchopanza.providers.recorded import key_of

        key = key_of(point, state, questions)
        queue = self._queues.get(key)
        if not queue:
            return await RecordedDecider([]).decide(point, state, questions)
        n = self._used.get(key, 0)
        self._used[key] = n + 1
        return await queue[min(n, len(queue) - 1)].decide(point, state, questions)


def recording() -> InOrder:
    return InOrder(FIXTURE)


def load_steps() -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in STEPS.read_text(encoding="utf-8").splitlines() if line]
    order = {"test_website": 0, "test_domain": 1, "test_task": 2}
    return sorted(rows, key=lambda r: order[r["split"]])  # stable: file order within a split


def position(ranked: list[Any], positives: set[str]) -> int | None:
    """1-based rank of the first positive, None when it is not in the returned list."""
    for i, r in enumerate(ranked, 1):
        if r.element.key in positives:
            return i
    return None


class Ceiling:
    """Stops a live run before the phase's Jev spend passes its bar. The spend is what the
    recording holds (every live call is appended to it), never replayed answers counted again;
    a replay spends nothing and is never stopped."""

    def __init__(self, bar: float, *, live: bool) -> None:
        self.bar = bar
        self.live = live

    def check(self) -> None:
        if self.live and recorded_spend() >= self.bar:
            raise SystemExit(f"Jev ceiling reached: {recorded_spend():.4f} of {self.bar:.2f} USD")


async def run_arm(arm: str, steps: list[dict[str, Any]], decider: Any, ceiling: Ceiling) -> list:
    gate = asyncio.Semaphore(CONCURRENT_STEPS)

    async def one(step: dict[str, Any]) -> dict[str, Any]:
        elements = [Element.from_dict(e) for e in step["elements"]]
        positives = set(step["positives"])
        async with gate:
            ceiling.check()
            squire = None
            if arm != "BM25":
                squire = Squire(decider, thresholds=Thresholds(max_usd=0.05, max_decisions=80))
            ranked = await rank(
                step["task"],
                elements,
                squire=squire,
                done=step["previous"],
                keep=KEEP,
                shortlist=SHORTLIST if arm == "JEV-SHORT" else None,
                # Phase 1 as registered: the final round's answer wins. JEV-BLEND: the default.
                blend=0.0 if arm in ("JEV", "JEV-SHORT") else BLEND,
            )
            cost = squire.meter.cost_usd if squire else 0.0
            calls = squire.meter.decisions if squire else 0
        answered = sum(r.p is not None for r in ranked)
        return {
            "id": step["id"],
            "split": step["split"],
            "arm": arm,
            "elements": len(elements),
            "position": position(ranked, positives),
            "cost_usd": cost,
            "calls": calls,
            "answered": answered,
        }

    return list(await asyncio.gather(*(one(s) for s in steps)))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(centre - half, 4), round(centre + half, 4))


def recall(rows: list[dict[str, Any]], k: int) -> float:
    return sum(r["position"] is not None and r["position"] <= k for r in rows) / len(rows)


def bootstrap(a: list[dict], b: list[dict], k: int, reps: int = 5000) -> tuple[float, float]:
    rng = random.Random(2030)
    hits_a = [r["position"] is not None and r["position"] <= k for r in a]
    hits_b = [r["position"] is not None and r["position"] <= k for r in b]
    n = len(a)
    diffs = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(hits_a[i] - hits_b[i] for i in idx) / n)
    diffs.sort()
    return (round(diffs[int(0.025 * reps)], 4), round(diffs[int(0.975 * reps)], 4))


def analyze(by_arm: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {"steps": len(next(iter(by_arm.values())))}
    for arm, rows in by_arm.items():
        n = len(rows)
        out[arm] = {
            f"recall@{k}": {
                "value": round(recall(rows, k), 4),
                "wilson95": wilson(
                    sum(r["position"] is not None and r["position"] <= k for r in rows), n
                ),
            }
            for k in KS
        }
        out[arm]["usd_per_step"] = round(sum(r["cost_usd"] for r in rows) / n, 6)
        out[arm]["calls_per_step"] = round(sum(r["calls"] for r in rows) / n, 2)
        out[arm]["by_split"] = {
            split: {f"recall@{k}": round(recall(part, k), 4) for k in (1, 10, 30)}
            for split in sorted({r["split"] for r in rows})
            if (part := [r for r in rows if r["split"] == split])
        }
    out["elements_per_step_mean"] = round(
        sum(r["elements"] for r in by_arm["BM25"]) / len(by_arm["BM25"]), 1
    )
    for arm in ("JEV", "JEV-SHORT", "JEV-BLEND"):
        if arm in by_arm:
            for k in (10, 20):
                out[f"{arm}-minus-BM25@{k}"] = {
                    "value": round(recall(by_arm[arm], k) - recall(by_arm["BM25"], k), 4),
                    "bootstrap95": bootstrap(by_arm[arm], by_arm["BM25"], k),
                }
    return out


def key_from(env_file: str | None) -> str:
    import os

    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key and env_file:
        text = pathlib.Path(env_file).read_text(encoding="utf-8")
        found = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M)
        key = found.group(1).strip().strip("'\"") if found else ""
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY: nothing spent")
    return key


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--limit", type=int, default=0, help="first N steps only (a smoke run)")
    ap.add_argument("--confirm", action="store_true", help="prereg-confirm.md: new steps")
    args = ap.parse_args()
    global STEPS, FIXTURE
    prereg = CONFIRM_PREREG if args.confirm else PREREG
    if args.confirm:
        STEPS, FIXTURE = CONFIRM_STEPS, CONFIRM_FIXTURE
    if args.record_hash:
        prereg.with_suffix(".sha256").write_text(digest(prereg) + "\n", encoding="utf-8")
        print(digest(prereg))
        return 0
    steps = load_steps()
    if args.limit:
        steps = steps[: args.limit]
    live = None
    if args.live:
        require_prereg(prereg)
        live = RecordingDecider(create("jev", api_key=key_from(args.env_file)), FIXTURE)
    replay = ReplayFirst(recording(), live)
    ceiling = Ceiling(JEV_CEILING_USD, live=live is not None)

    arms = ("BM25", "JEV-BLEND") if args.confirm else ("BM25", "JEV", "JEV-SHORT")

    async def every() -> dict[str, list[dict[str, Any]]]:
        return {arm: await run_arm(arm, steps, replay, ceiling) for arm in arms}

    by_arm = asyncio.run(every())
    unanswered = sum(r["answered"] == 0 for arm in arms[1:] for r in by_arm[arm])
    print(f"live calls {replay.asked}, missing {replay.missing}, steps with no answer {unanswered}",
          file=sys.stderr)  # fmt: skip
    report = analyze(by_arm)
    report["incomplete"] = bool(replay.missing or unanswered)
    tag = ("-confirm" if args.confirm else "") + ("-smoke" if args.limit else "")
    (RESULTS / f"analysis{tag}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (RESULTS / f"steps{tag}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for arm in by_arm.values() for r in arm), encoding="utf-8"
    )
    print(json.dumps(report, indent=1))
    return 1 if report["incomplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
