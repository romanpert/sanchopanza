"""The lexical screen on fresh HotpotQA questions: a confirmation (`prereg.md` beside the results).

python benchmarks/lateral/screen/confirm.py --record-hash
python benchmarks/lateral/screen/confirm.py --replay-published --hotpot HOTPOT.jsonl  # free
python benchmarks/lateral/screen/confirm.py --dry-run --hotpot HOTPOT.jsonl           # free
python benchmarks/lateral/screen/confirm.py --live --hotpot HOTPOT.jsonl --env-file ENV
python benchmarks/lateral/screen/confirm.py --replay-live --hotpot HOTPOT.jsonl        # free

The screen of 2026-09-28 (`docs/results/2026-09-28-lateral-screen/`) was scored on the 200
held-out questions of the hierarchy run, against that run's recorded tournament. Here both arms
run on 200 questions no earlier HotpotQA run of this repository drew (`hierarchy.build` with
every used id excluded and a new seed), with the cuts that ship: SCREEN is BM25's top 30 then
one in-context call at `pages_in_context`; TOUR is the tournament at `pages_first_round`, then
`pages_in_context`. Nothing is derived.

- `--replay-published` runs this file's code on the published 200 from the recordings and must
  reproduce the published figures (96.0 % and 96.5 %): the check that the harness is the same.
- `--dry-run` runs the fresh 200 with a hashed fake decider: it counts calls and costs nothing.
- `--live` requires the registered hash and stops at `CAP_USD` of Jev.
- `--replay-live` rescores the live run of 2026-09-28 from `fixtures/screen-confirm.jsonl`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name: str, path: pathlib.Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


screen_run = _load("lateral_screen_run", HERE / "run.py")
hier = screen_run.hier
fake = _load("ab_pages", ROOT / "benchmarks" / "ab" / "pages.py")

from sanchopanza import Decision, Squire, Thresholds  # noqa: E402
from sanchopanza.eval.stats import bootstrap_difference, mcnemar, wilson  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-28-lateral-screen-confirm"
PREREG = RESULTS / "prereg.md"
# Outside `fixtures/lateral-*.jsonl` on purpose: this run has its own bar (prereg.md), and
# the shared lateral total of `ledger.py` has 0.36 USD of room, less than this run needs.
FIXTURE = ROOT / "fixtures" / "screen-confirm.jsonl"
SEED = 2030
N = 200
CAP_USD = 0.50
FIRST_CUT = Thresholds().pages_first_round
FINAL_CUT = Thresholds().pages_in_context
PUBLISHED = {"SCREEN": 0.96, "TOUR": 0.965}


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != digest():
        raise SystemExit("prereg.md missing or changed: nothing spent")


def fresh(hotpot: pathlib.Path) -> list[dict[str, Any]]:
    published = frozenset(r["id"] for r in hier.build(hotpot))
    rows = hier.build(hotpot, seed=SEED, n=N, exclude=published)
    assert not {r["id"] for r in rows} & (published | hier.used_ids(hotpot))
    return rows


class Capped:
    """Refuses (an empty, failed decision) once the recorded spend reaches the cap."""

    name = "jev"

    def __init__(self, inner: Any, cap_usd: float) -> None:
        self._inner = inner
        self.cap_usd = cap_usd
        self.spent_usd = 0.0

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        if self.spent_usd >= self.cap_usd:
            return Decision(point, {}, self.name, "-", error="cap reached")
        decision = await self._inner.decide(point, state, questions)
        self.spent_usd += decision.cost_usd
        return decision


async def run_arms(rows: list[dict[str, Any]], decider: Any) -> Squire:
    await hier.round_one(rows, decider)
    await hier.final_round(rows, decider, FIRST_CUT)
    return await screen_run.screen(rows, decider)


def masks(row: dict[str, Any]) -> dict[str, list[bool]]:
    tour = [p != "out" and (p is None or p >= FINAL_CUT) for p in row["p2"]]
    top = set(row["screen_ids"])
    return {
        "SCREEN": row["screen_keep"],
        "TOUR": tour,
        "CEILING": [i in top for i in range(len(row["pages"]))],
    }


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_arm: dict[str, Any] = {}
    joints: dict[str, list[bool]] = {}
    for arm in ("SCREEN", "TOUR", "CEILING"):
        hits, share, pages = [], 0.0, 0
        for row in rows:
            mask = masks(row)[arm]
            hits.append(all(m for m, g in zip(mask, row["gold"], strict=True) if g))
            sizes = [len(t) + len(x) for t, x in row["pages"]]
            share += sum(s for s, m in zip(sizes, mask, strict=True) if m) / sum(sizes)
            pages += sum(mask)
        _, lo, hi = wilson(sum(hits), len(rows))
        joints[arm] = hits
        per_arm[arm] = {
            "page_joint": round(sum(hits) / len(rows), 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "kept_share": round(share / len(rows), 4),
            "pages_kept": round(pages / len(rows), 2),
            "n": len(rows),
        }
    diff, lo, hi = bootstrap_difference(joints["SCREEN"], joints["TOUR"])
    only_s, only_t, p = mcnemar(joints["SCREEN"], joints["TOUR"])
    s, t = per_arm["SCREEN"], per_arm["TOUR"]
    s1 = s["page_joint"] >= t["page_joint"] - 0.01 and s["kept_share"] <= t["kept_share"] + 0.01
    s2 = lo >= -0.03
    tour_calls = sum(4 + r["final_calls"] for r in rows) / len(rows)
    return {
        "arms": per_arm,
        "screen_minus_tour": {
            "page_joint": round(diff, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "only_screen": only_s,
            "only_tour": only_t,
            "mcnemar_p": round(p, 4),
        },
        "calls_per_question": {"SCREEN": 1, "TOUR": round(tour_calls, 2)},
        "S1": s1,
        "S2": s2,
        "verdict": "confirmed" if s1 and s2 else "not confirmed",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record-hash", action="store_true")
    mode.add_argument("--replay-published", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay-live", action="store_true")
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.record_hash:
        screen_run.ledger.write_hash(RESULTS / "prereg.sha256", digest())
        print(digest())
        return 0
    if args.live:
        require_prereg()  # before anything else, so an unregistered run cannot begin
    hotpot = pathlib.Path(args.hotpot)
    if args.replay_published:
        rows = hier.build(hotpot)[hier.DERIVATION :]
        replay = hier.triage_run.ReplayFirst
        tour = replay(RecordedDecider.from_file(hier.FIXTURE), None)
        asyncio.run(hier.round_one(rows, tour))
        asyncio.run(hier.final_round(rows, tour, FIRST_CUT))
        screened = replay(RecordedDecider.from_file(screen_run.FIXTURE), None)
        asyncio.run(screen_run.screen(rows, screened))
        missing = tour.missing + screened.missing
    else:
        rows = fresh(hotpot)
        if args.replay_live:
            decider = hier.triage_run.ReplayFirst(RecordedDecider.from_file(FIXTURE), None)
        elif args.dry_run:
            decider = fake.EveryQuestion()
        else:
            live = Capped(
                RecordingDecider(
                    create("jev", api_key=screen_run.key_from(args.env_file)), FIXTURE
                ),
                CAP_USD,
            )
            recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else None
            decider = hier.triage_run.ReplayFirst(recorded or RecordedDecider([]), live)
        squire = asyncio.run(run_arms(rows, decider))
        missing = getattr(decider, "missing", 0) + int(squire.exhausted)
    report = score(rows)
    if args.dry_run:
        calls = decider.calls
        report["dry_run"] = {
            "decider_calls": calls,
            "estimate_usd": round(N * (1.76e-3 + 0.49e-3), 3),
            "note": "fake answers: the arms' figures mean nothing, the call count does",
        }
    elif args.replay_published:
        report["published"] = PUBLISHED
    print(json.dumps(report, indent=1))
    if missing:
        print(f"INCOMPLETE: {missing} missing answers; nothing is a result", file=sys.stderr)
        return 1
    if args.live:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
