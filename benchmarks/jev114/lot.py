"""The paid-lot machinery the 2026-10-16 follow-ups of the 1.14 profile share (checkdone114,
redundant_drop): both Jev versions asked on the same case in one slot, each through its own
recording first and, on a miss, one live call capped by the shared ledger.

What a lot fixes, as data (`Lot`): its name, its results directory, its fixtures, its batch cap
and the files its seal covers. What this module does with it, the same way for every lot:

- `Arm`: replay this lot's fixture; on a miss and only when live, one call through
  `CappedDecider` (ledger cap and batch cap) behind `ModelGuard`, recorded on return;
- `Run`: both arms per case with the order alternating, at most `gate` calls in flight, a halt
  on the first cap, 402 or wrong model, and after `max_failures` failed calls; a `STOP` file in
  the lot's run directory stops it between calls;
- `may_launch`: one relaunch at most, none after a final stop or a completed launch;
- `digest` / `require_seal`: one sha256 over the sealed files, CRLF folded.

Nothing here reads a key or calls a model unless `live=True`, which only `--paid` sets.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.contract import DeciderOutOfFunds, Decision, Question, State  # noqa: E402
from sanchopanza.providers.capped import CappedDecider, SpendCapReached  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

MODELS = {"13r": "jev-1.13.0", "14": "jev-1.14.0"}
ARMS = tuple(MODELS)
LEDGER = Path("C:/sp-runs/jev114/ledger.json")  # shared by every 1.14 lot
LEDGER_CAP = 4.50
FINAL_STOPS = ("SpendCapReached", "spend cap", "DeciderOutOfFunds", "HTTP 402", "out of funds",
               "no_funds", "WrongModel", "asked jev", "served jev")  # fmt: skip


@dataclass(frozen=True)
class Lot:
    name: str  # the ledger's batch
    out: Path  # docs/results/<lot>/
    run: Path  # untracked: launches.jsonl, STOP
    batch_cap: float
    sealed: Sequence[str]  # repo-relative, in seal order
    fixture_stem: str  # fixtures/jev114/<stem>-<arm>.jsonl
    gate: int = 4
    cases_at_once: int = 4
    passes: int = 2
    max_failures: int = 25
    ledger: Path = LEDGER
    ledger_cap: float = LEDGER_CAP
    models: Mapping[str, str] = field(default_factory=lambda: dict(MODELS))

    def fixture(self, arm: str) -> Path:
        return ROOT / "fixtures" / "jev114" / f"{self.fixture_stem}-{arm}.jsonl"


# --- the seal -------------------------------------------------------------------------------


def _folded(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def digest(lot: Lot) -> str:
    h = hashlib.sha256()
    for rel in lot.sealed:
        h.update(_folded(ROOT / rel))
    return h.hexdigest()


def require_seal(lot: Lot) -> None:
    sealed = lot.out / "prereg.sha256"
    if not sealed.exists() or sealed.read_text(encoding="utf-8").split()[0] != digest(lot):
        raise SystemExit("a sealed file changed since the seal: nothing spent")


# --- one arm ----------------------------------------------------------------------------------


class WrongModel(RuntimeError):
    pass


class ModelGuard:
    """Raises before an answer served under another model name reaches the recording."""

    def __init__(self, inner: Any, model: str) -> None:
        self._inner, self._model, self.name = inner, model, inner.name

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        decision = await self._inner.decide(point, state, questions)
        if decision.model != self._model:
            raise WrongModel(f"asked {self._model}, served {decision.model!r}")
        return decision


class Arm:
    def __init__(self, lot: Lot, arm: str, live: Any | None, gate: asyncio.Semaphore) -> None:
        model = lot.models[arm]
        self.name, self.model, self.gate = arm, model, gate
        self.recorded = RecordedDecider.from_file(lot.fixture(arm), model=model)
        self.writer = None
        if live is not None:
            self.writer = RecordingDecider(ModelGuard(live, model), lot.fixture(arm))

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        found = await self.recorded.decide(point, state, questions)
        if found.answers or self.writer is None:
            return found
        async with self.gate:
            return await self.writer.decide(point, state, questions)


def arms_of(lot: Lot, live: bool, gate: asyncio.Semaphore) -> dict[str, Arm]:
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.providers.jev import JevDecider

        ledger = SpendLedger(lot.ledger, cap_usd=lot.ledger_cap)
        for arm, model in lot.models.items():
            jev = JevDecider(model=model, long_context=False, images=False)
            capped[arm] = CappedDecider(jev, ledger=ledger, batch=lot.name, max_usd=lot.batch_cap)
    return {arm: Arm(lot, arm, capped.get(arm), gate) for arm in lot.models}


# --- the live run -----------------------------------------------------------------------------

# ask(case, decider) -> (result, probe | None); answered(case, arm) -> bool
Ask = Callable[[Mapping[str, Any], Any], Awaitable[tuple[Any, Any]]]
Answered = Callable[[Mapping[str, Any], Arm], Awaitable[bool]]
STOPS = (SpendCapReached, DeciderOutOfFunds, WrongModel)


class Run:
    def __init__(self, lot: Lot, ask: Ask) -> None:
        self.lot, self.ask, self.failures, self.tally, self.why = lot, ask, 0, {}, ""
        self.stop = asyncio.Event()
        self.arms = arms_of(lot, True, asyncio.Semaphore(lot.gate))

    def halt(self, why: str) -> None:
        if not self.stop.is_set():
            print(f"stopped: {why}", flush=True)
            self.why = why
        self.stop.set()

    def _failed(self) -> None:
        self.failures += 1
        if self.failures >= self.lot.max_failures:
            self.halt(f"{self.failures} failed calls")

    def outcome_of(self, result: Any, probe: Any) -> str:
        """A bench case runs through a squire, which fails open: a refusal or an outage shows
        only in the probe's calls. A bare decision shows it in itself."""
        if probe is None:
            if result.failed or not result.answers:
                self._failed()
                return "failed"
            return "asked"
        errors = [c["error"] for c in probe.calls if c.get("error")]
        stops = tuple(s.__name__ for s in STOPS)
        if any(e.startswith(stops) for e in errors):
            self.halt(next(e for e in errors if e.startswith(stops)))
            return "stopped"
        if errors or not probe.calls:
            self._failed()
            return "failed"
        return "asked"

    async def one(self, index: int, case: Mapping[str, Any], todo: set[str]) -> None:
        arms = tuple(self.lot.models)
        order = arms if index % 2 == 0 else arms[::-1]
        for arm in order:
            if arm not in todo or self.stop.is_set() or (self.lot.run / "STOP").exists():
                continue
            try:
                result, probe = await self.ask(case, self.arms[arm])
                outcome = self.outcome_of(result, probe)
            except STOPS as error:
                self.halt(f"{type(error).__name__}: {error}")
                outcome = "stopped"
            except Exception as error:  # noqa: BLE001 - counted; asked again in the next pass
                print(f"  {arm}: {type(error).__name__}", flush=True)
                self._failed()
                outcome = "failed"
            self.tally[f"{arm} {outcome}"] = self.tally.get(f"{arm} {outcome}", 0) + 1


async def missing(
    lot: Lot, cases: Sequence[Mapping[str, Any]], answered: Answered
) -> list[tuple[int, Mapping[str, Any], set[str]]]:
    replays = arms_of(lot, False, asyncio.Semaphore(lot.gate))
    out = []
    for index, case in enumerate(cases):
        todo = {a for a in lot.models if not await answered(case, replays[a])}
        if todo:
            out.append((index, case, todo))
    return out


async def run_cases(
    lot: Lot, cases: Sequence[Mapping[str, Any]], ask: Ask, answered: Answered
) -> tuple[int, str]:
    """Exit code (0, or 2 when something stopped the run) and why it stopped."""
    run = Run(lot, ask)
    slots = asyncio.Semaphore(lot.cases_at_once)

    async def slot(index: int, case: Mapping[str, Any], todo: set[str]) -> None:
        async with slots:
            await run.one(index, case, todo)

    for number in range(1, lot.passes + 1):
        todo = await missing(lot, cases, answered)
        print(f"pass {number}: {len(todo)} cases with an arm to ask", flush=True)
        if not todo or run.stop.is_set():
            break
        run.arms = arms_of(lot, True, asyncio.Semaphore(lot.gate))  # reload what was recorded
        await asyncio.gather(*(slot(i, c, arms) for i, c, arms in todo))
    left = sum(len(arms) for _, _, arms in await missing(lot, cases, answered))
    print(f"{json.dumps(run.tally, sort_keys=True)}; answers still missing {left}", flush=True)
    return (2, run.why) if run.stop.is_set() else (0, "")


# --- launches -----------------------------------------------------------------------------


def launches(lot: Lot) -> Path:
    return lot.run / "launches.jsonl"


def may_launch(lot: Lot) -> str | None:
    """Why a paid launch is refused: one relaunch at most, and none after a cap, a 402, a model
    served under another name, or a launch that completed."""
    path = launches(lot)
    if not path.exists():
        existing = [str(lot.fixture(a)) for a in lot.models if lot.fixture(a).exists()]
        return f"answers recorded before any launch: {existing}" if existing else None
    past = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    started = sum(p.get("outcome") == "started" for p in past)
    if started >= 2:
        return f"{started} launches already"
    if any(any(stop in p.get("why", "") for stop in FINAL_STOPS) for p in past):
        return "an earlier launch stopped on a cap, a 402 or a wrong model"
    if any(p.get("outcome") == "complete" for p in past):
        return "an earlier launch completed"
    return None


def log_launch(lot: Lot, outcome: str, why: str) -> None:
    lot.run.mkdir(parents=True, exist_ok=True)
    with launches(lot).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"outcome": outcome, "why": why[:300]}) + "\n")


def preflight_both(lot: Lot, ledger: SpendLedger) -> str:
    """ "" when both versions answer under their own names, else why not."""
    from sanchopanza.providers.jev import preflight

    for arm, model in lot.models.items():
        rid = ledger.reserve(0.0001, batch=lot.name, batch_cap_usd=lot.batch_cap)
        if rid is None:
            return "preflight: SpendCapReached: the ledger has no room"
        result = preflight(model=model)
        ledger.settle(rid, result.cost_usd)
        print(f"preflight {arm}: {result.reason}; served {result.model}")
        if result.reason == "no_funds":
            return "preflight: no_funds (HTTP 402)"
        if result.ok and result.model != model:
            return f"preflight: asked {model}, served jev {result.model!r}"
        if not result.ok:
            return f"preflight: {result.reason}"
    return ""


def ledger_room(lot: Lot) -> dict[str, float]:
    """Read-only: what the shared ledger and this lot's batch have spent, and what is left."""
    if not lot.ledger.exists():
        return {"ledger_spent": 0.0, "ledger_room": lot.ledger_cap, "batch_spent": 0.0}
    ledger = SpendLedger(lot.ledger, cap_usd=lot.ledger_cap)
    spent = ledger.spent()
    return {"ledger_spent": round(spent, 4), "ledger_room": round(lot.ledger_cap - spent, 4),
            "batch_spent": round(ledger.spent(lot.name), 4)}  # fmt: skip


def paired_auc(
    labels: Sequence[bool], new: Sequence[float], old: Sequence[float], clusters: Sequence[str],
    *, replicas: int = 2000, seed: int = 7,
) -> dict[str, Any]:  # fmt: skip
    """AUC of each arm (rank-based, `recalconf_analysis.auc`) and the difference's 95 % interval
    by a paired bootstrap over clusters. Descriptive in both lots: `l4_stats.paired_auc` counts
    pairs, which is too slow at these sizes."""
    import random

    from recalconf_analysis import auc

    def area(scores: Sequence[float], idx: Sequence[int]) -> float | None:
        return auc([scores[i] for i in idx], [labels[i] for i in idx])

    everything = list(range(len(labels)))
    whole = {"new": area(new, everything), "old": area(old, everything)}
    if None in whole.values():
        return {"n": len(labels), "new": None, "old": None, "diff": None, "ci95_cluster": None}
    groups: dict[str, list[int]] = {}
    for i, key in enumerate(clusters):
        groups.setdefault(key, []).append(i)
    units, rng, diffs = list(groups.values()), random.Random(seed), []
    for _ in range(replicas):
        idx = [i for _ in units for i in units[rng.randrange(len(units))]]
        a, b = area(new, idx), area(old, idx)
        if a is not None and b is not None:
            diffs.append(a - b)
    diffs.sort()
    ci = (round(diffs[int(0.025 * (len(diffs) - 1))], 4),
          round(diffs[int(0.975 * (len(diffs) - 1))], 4))  # fmt: skip
    return {"n": len(labels), "positives": sum(labels), "new": round(whole["new"], 4),
            "old": round(whole["old"], 4), "diff": round(whole["new"] - whole["old"], 4),
            "ci95_cluster": ci}  # fmt: skip


def paid_launch(lot: Lot, run_all: Callable[[], tuple[int, str]]) -> int:
    """The registered launch: seal checked by the caller, one relaunch at most, preflight of
    both versions, then `run_all`, logged."""
    from jev114_components import load_key

    refused = may_launch(lot)
    if refused:
        raise SystemExit(f"launch refused: {refused}")
    load_key()
    ledger = SpendLedger(lot.ledger, cap_usd=lot.ledger_cap)
    log_launch(lot, "started", "")
    failed_preflight = preflight_both(lot, ledger)
    if failed_preflight:
        log_launch(lot, "stopped", failed_preflight)
        return 3
    code, why = run_all()
    print(f"ledger {ledger.spent():.4f} of {lot.ledger_cap}; {lot.name} "
          f"{ledger.spent(lot.name):.4f} of {lot.batch_cap}", flush=True)  # fmt: skip
    if code or (lot.run / "STOP").exists():
        log_launch(lot, "stopped", why or "STOP file")
        return code or 5
    log_launch(lot, "complete", "")
    return 0
