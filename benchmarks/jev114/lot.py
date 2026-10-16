"""The paid-lot machinery the 2026-10-16 follow-ups of the 1.14 profile share (checkdone114,
redundant_drop): both Jev versions asked on the same case in one slot, each through its own
recording first and, on a miss, one live call capped by the shared ledger.

What a lot fixes, as data (`Lot`): its name, its results directory, its run directory, its batch
cap and the files its seal covers. What this module does with it, the same way for every lot:

- `require_sealed_checkout`: a paid run starts only from the sealing commit (the last one that
  touched `prereg.sha256`), with a clean worktree and every sealed file as sealed;
- `Arm`: replay this lot's recording; on a miss and only when live, one call through
  `CappedDecider` (ledger cap and batch cap) behind `ModelGuard`, recorded on return. The
  recordings live in the run directory, outside the repository, so a relaunch from the same
  worktree finds the worktree clean; `publish` copies them into `fixtures/jev114/` afterwards;
- `repair_recording`: a line cut short by a killed process is moved aside and counted before a
  relaunch appends to the file;
- `Run`: both arms per case with the order alternating, cases in a seeded random order (a stop
  leaves a random subset, not the first suites), at most `gate` calls in flight, a halt on the
  first cap, 402 or wrong model, and after `max_failures` failed calls; a `STOP` file in the run
  directory stops it between calls;
- `may_launch`: one relaunch at most, none after a final stop or a completed launch.

Nothing here reads a key or calls a model unless `live=True`, which only `--paid` sets.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import shutil
import subprocess
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
ORDER_SEED = 20261016  # the order cases are asked in; registered
# Every file on the paid path both lots share: this machinery, the key and the probe, the Jev
# client and its model keys, the ledger and the cap, the recording, the squire and what it reads.
# Each lot adds its registration, its inputs, its launcher, its runner and its request code.
COMMON_SEALED = (
    "benchmarks/jev114/lot.py",
    "benchmarks/jev114/lot_stats.py",
    "benchmarks/jev114/jev114_components.py",
    "benchmarks/jev114/jev114_paired.py",
    "benchmarks/jev114/l4_stats.py",
    "src/sanchopanza/_env.py",
    "src/sanchopanza/_lockfile.py",
    "src/sanchopanza/funds.py",
    "src/sanchopanza/budget.py",
    "src/sanchopanza/contract.py",
    "src/sanchopanza/media.py",
    "src/sanchopanza/limits.py",
    "src/sanchopanza/text.py",
    "src/sanchopanza/policy.py",
    "src/sanchopanza/squire.py",
    "src/sanchopanza/journal.py",
    "src/sanchopanza/providers/jev.py",
    "src/sanchopanza/providers/jev_models.py",
    "src/sanchopanza/providers/jev_assets.py",
    "src/sanchopanza/providers/capped.py",
    "src/sanchopanza/providers/cached.py",
    "src/sanchopanza/providers/recorded.py",
    "src/sanchopanza/providers/null.py",
)
FINAL_STOPS = ("SpendCapReached", "spend cap", "DeciderOutOfFunds", "HTTP 402", "out of funds",
               "no_funds", "WrongModel", "asked jev", "served jev")  # fmt: skip


@dataclass(frozen=True)
class Lot:
    name: str  # the ledger's batch
    out: Path  # docs/results/<lot>/
    run: Path  # untracked: recordings, launches.jsonl, STOP
    batch_cap: float
    sealed: Sequence[str]  # repo-relative, in seal order
    fixture_stem: str  # <run>/<stem>-<arm>.jsonl, published as fixtures/jev114/<same name>
    gate: int = 4
    cases_at_once: int = 4
    passes: int = 2
    max_failures: int = 25
    ledger: Path = LEDGER
    ledger_cap: float = LEDGER_CAP
    models: Mapping[str, str] = field(default_factory=lambda: dict(MODELS))

    def fixture(self, arm: str) -> Path:
        """Where a live run records: outside the repository."""
        return self.run / f"{self.fixture_stem}-{arm}.jsonl"

    def published(self, arm: str) -> Path:
        return ROOT / "fixtures" / "jev114" / f"{self.fixture_stem}-{arm}.jsonl"

    def replay(self, arm: str) -> Path:
        """What `rows` reads: the published copy if there is one, else the run's."""
        return self.published(arm) if self.published(arm).exists() else self.fixture(arm)


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


def _git(*args: str) -> str:
    done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()[:200]}")
    return done.stdout.strip()


def sealing_commit(lot: Lot) -> str:
    rel = (lot.out / "prereg.sha256").relative_to(ROOT).as_posix()
    return _git("log", "-1", "--format=%H", "--", rel)


def require_sealed_checkout(lot: Lot) -> None:
    """HEAD is the sealing commit and nothing in the worktree differs from it."""
    head, sealed = _git("rev-parse", "HEAD"), sealing_commit(lot)
    if not sealed or head != sealed:
        raise SystemExit(f"HEAD {head[:9]} is not the sealing commit {sealed[:9]}: nothing spent")
    if _git("status", "--porcelain"):
        raise SystemExit("the worktree is not clean: nothing spent")
    require_seal(lot)


# --- recordings -------------------------------------------------------------------------------


def read_recording(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Every whole line, and how many could not be read (a line cut short by a kill)."""
    if not path.exists():
        return [], 0
    entries, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            bad += 1
    return entries, bad


def repair_recording(path: Path) -> int:
    """Before appending: move unreadable lines to `<name>.truncated` and keep the rest, each
    ending in a newline. Returns how many were moved."""
    entries, bad = read_recording(path)
    raw = path.read_bytes() if path.exists() else b""
    if not bad and (not raw or raw.endswith(b"\n")):
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    broken = [x for x in lines if x.strip() and not _readable(x)]
    with path.with_name(path.name + ".truncated").open("a", encoding="utf-8") as aside:
        aside.writelines(x + "\n" for x in broken)
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
                    encoding="utf-8")  # fmt: skip
    return len(broken)


def _readable(line: str) -> bool:
    try:
        json.loads(line)
    except ValueError:
        return False
    return True


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
    def __init__(
        self, lot: Lot, arm: str, live: Any | None, gate: asyncio.Semaphore, *, path: Path
    ) -> None:
        model = lot.models[arm]
        self.name, self.model, self.gate = arm, model, gate
        entries, self.unreadable = read_recording(path)
        self.recorded = RecordedDecider(entries, model=model)
        self.writer, self.client = None, None
        if live is not None:
            self.writer = RecordingDecider(ModelGuard(live, model), path)
            self.client = getattr(live, "inner", None)  # the JevDecider, closed by `close_arms`

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        found = await self.recorded.decide(point, state, questions)
        if found.answers or self.writer is None:
            return found
        async with self.gate:
            return await self.writer.decide(point, state, questions)


class _Live:
    """The capped decider of one live arm, with the Jev client under it kept in reach."""

    def __init__(self, capped: Any, inner: Any) -> None:
        self._capped, self.inner, self.name = capped, inner, capped.name

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        return await self._capped.decide(point, state, questions)


def arms_of(lot: Lot, live: bool, gate: asyncio.Semaphore) -> dict[str, Arm]:
    """Live arms record into the run directory; replaying arms read what `rows` reads.

    ONE EVENT LOOP. A live arm's Jev client binds to the loop of its first call, so live arms
    are built only inside `run_cases`, which runs whole under one `asyncio.run`, and are closed
    there (`close_arms`) before the next pass builds fresh ones. The preflight builds and
    closes its own client in its own loop."""
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.providers.jev import JevDecider

        ledger = SpendLedger(lot.ledger, cap_usd=lot.ledger_cap)
        for arm, model in lot.models.items():
            jev = JevDecider(model=model, long_context=False, images=False)
            cap = CappedDecider(jev, ledger=ledger, batch=lot.name, max_usd=lot.batch_cap)
            capped[arm] = _Live(cap, jev)
    return {
        arm: Arm(
            lot, arm, capped.get(arm), gate, path=lot.fixture(arm) if live else lot.replay(arm)
        )  # fmt: skip
        for arm in lot.models
    }


async def close_arms(arms: Mapping[str, Arm]) -> None:
    for arm in arms.values():
        close = getattr(arm.client, "aclose", None)
        if close is not None:
            await close()


# --- the live run -----------------------------------------------------------------------------

# ask(case, decider) -> (result, probe | None); answered(case, arm) -> bool
Ask = Callable[[Mapping[str, Any], Any], Awaitable[tuple[Any, Any]]]
Answered = Callable[[Mapping[str, Any], Arm], Awaitable[bool]]
STOPS = (SpendCapReached, DeciderOutOfFunds, WrongModel)


def shuffled(cases: Sequence[Mapping[str, Any]], seed: int = ORDER_SEED) -> list[Mapping[str, Any]]:
    """The registered asking order: a stop part way leaves a random subset of the cases."""
    order = list(cases)
    random.Random(seed).shuffle(order)
    return order


class Run:
    def __init__(self, lot: Lot, ask: Ask) -> None:
        self.lot, self.ask, self.failures, self.tally, self.why = lot, ask, 0, {}, ""
        self.stop = asyncio.Event()
        self.arms: dict[str, Arm] = {}  # built per pass, inside the run's loop

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
    lot: Lot, cases: Sequence[Mapping[str, Any]], answered: Answered, *, live_paths: bool
) -> list[tuple[int, Mapping[str, Any], set[str]]]:
    gate = asyncio.Semaphore(lot.gate)
    replays = {
        a: Arm(lot, a, None, gate, path=lot.fixture(a) if live_paths else lot.replay(a))
        for a in lot.models
    }
    out = []
    for index, case in enumerate(cases):
        todo = {a for a in lot.models if not await answered(case, replays[a])}
        if todo:
            out.append((index, case, todo))
    return out


async def run_cases(
    lot: Lot, cases: Sequence[Mapping[str, Any]], ask: Ask, answered: Answered
) -> tuple[int, str]:
    """Exit code (0, or 2 when something stopped the run) and why it stopped. Cases are asked
    in the registered shuffled order."""
    for arm in lot.models:
        moved = repair_recording(lot.fixture(arm))
        if moved:
            print(f"{arm}: {moved} unreadable recorded line(s) moved aside", flush=True)
    cases = shuffled(cases)
    run = Run(lot, ask)
    slots = asyncio.Semaphore(lot.cases_at_once)

    async def slot(index: int, case: Mapping[str, Any], todo: set[str]) -> None:
        async with slots:
            await run.one(index, case, todo)

    try:
        for number in range(1, lot.passes + 1):
            todo = await missing(lot, cases, answered, live_paths=True)
            print(f"pass {number}: {len(todo)} cases with an arm to ask", flush=True)
            if not todo or run.stop.is_set():
                break
            await close_arms(run.arms)
            run.arms = arms_of(lot, True, asyncio.Semaphore(lot.gate))  # reload what was recorded
            await asyncio.gather(*(slot(i, c, arms) for i, c, arms in todo))
    finally:
        await close_arms(run.arms)
    left = sum(len(a) for _, _, a in await missing(lot, cases, answered, live_paths=True))
    print(f"{json.dumps(run.tally, sort_keys=True)}; answers still missing {left}", flush=True)
    return (2, run.why) if run.stop.is_set() else (0, "")


# --- launches -----------------------------------------------------------------------------


def launches(lot: Lot) -> Path:
    return lot.run / "launches.jsonl"


def read_launches(path: Path) -> list[dict[str, Any]]:
    return read_recording(path)[0]


def may_launch(lot: Lot) -> str | None:
    """Why a paid launch is refused: one relaunch at most, and none after a cap, a 402, a model
    served under another name, or a launch that completed."""
    path = launches(lot)
    if not path.exists():
        existing = [str(lot.fixture(a)) for a in lot.models if lot.fixture(a).exists()]
        return f"answers recorded before any launch: {existing}" if existing else None
    past = read_launches(path)
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


def publish(lot: Lot) -> list[str]:
    """Free, after a launch: the run's recordings to `fixtures/jev114/` and its launch log to
    the results directory (the analysis reads whether the last launch completed)."""
    done = []
    for arm in lot.models:
        if lot.fixture(arm).exists():
            lot.published(arm).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(lot.fixture(arm), lot.published(arm))
            done.append(lot.published(arm).relative_to(ROOT).as_posix())
    if launches(lot).exists():
        shutil.copyfile(launches(lot), lot.out / "launches.jsonl")
        done.append((lot.out / "launches.jsonl").relative_to(ROOT).as_posix())
    return done


def preflight_both(lot: Lot, ledger: SpendLedger) -> str:
    """ "" when both versions answer under their own names, else why not. The preflight cannot
    read the TypeSafe balance (it learns only "a call came back" or a 402): the balance check
    of the registration is the owner's, before the launch."""
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


def paid_launch(lot: Lot, run_all: Callable[[], tuple[int, str]]) -> int:
    """The registered launch: sealed checkout checked by the caller, one relaunch at most,
    preflight of both versions, then `run_all`, logged."""
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
