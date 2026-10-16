"""Ask Jev once for what a recording lacks, under a hard cap; or count it, for free.

Shared by the B4 and A5 runners (`benchmarks/passage_fit/run.py`, `benchmarks/facts_gate/
run.py`). A query is `(point, state, questions)`; a `Lot` names everything one paid run is
bound to. `plan` reads the recording and prices what is missing two ways (the measured median
of a real request, 71 micro-USD, and the estimate `CappedDecider` reserves).

`run_paid` refuses, before the key is read, unless all of these hold:
- the higher estimate fits under the lot's cap;
- `prereg.sha256` holds the sha256 of `prereg.md` and of the launcher `.cmd` (its two local
  values, the python and the key file, read as placeholders);
- the prereg names an instrument commit, an ancestor of HEAD, and the instrument paths are
  identical to it (nothing changed or added under them since);
- every external input has its registered sha256;
- the launch rule: one launch and at most one relaunch, never after a 402, a 429 or the cap;
- no other `paid` of the lot holds its lock.
Then, in ONE event loop (`session`: preflight, the live client built inside it, every call,
its close), it asks each missing query once, in order, through `CappedDecider` on the lot's ledger
(a fixed path under the user's cache, printed), records each answer as it comes, and stops at
the first refusal, failure, empty answer or answer from another model. Every launch is
appended, with HEAD and why it stopped, to `launches.jsonl` beside the ledger.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza import _lockfile  # noqa: E402
from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.providers.capped import (  # noqa: E402
    DEFAULT_PRICE_PER_MTOK,
    CappedDecider,
    estimate_usd,
)
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

MEDIAN_REQUEST_USD = 71e-6  # a real Jev request, median (CLAUDE.md); a short question is ~29
LOCK_STALE_S = 6 * 3600.0  # a paid run holds its lock for minutes; never taken over sooner
NO_RELAUNCH_AFTER = ("funds", "limit", "cap")
COMMIT = re.compile(r"Instrument commit: `([0-9a-f]{40})`")
LOCAL_VALUES = re.compile(r'^(set "(?:PY|SANCHOPANZA_KEYS_ENV)=)[^"\n]*(")', re.MULTILINE)
Query = tuple[str, Any, Any]


@dataclass(frozen=True)
class Lot:
    name: str
    prereg: Path
    launcher: Path
    fixture: Path
    model: str
    cap_usd: float
    instrument: tuple[str, ...]  # repo paths that must be as the instrument commit has them
    inputs: tuple[tuple[Path, str], ...] = field(default=())  # (file, raw sha256)
    home: Path = field(default_factory=lambda: Path.home() / ".cache" / "sanchopanza")
    price_per_mtok: float = DEFAULT_PRICE_PER_MTOK  # what the estimates and reservations use
    model_prefix: bool = False  # True: a served snapshot `<model>-<suffix>` counts as the model

    def serves(self, model: str) -> bool:
        """Whether an answer from `model` is the lot's model."""
        return model == self.model or (self.model_prefix and model.startswith(self.model + "-"))

    @property
    def run_dir(self) -> Path:
        return self.home / self.name

    @property
    def ledger(self) -> Path:
        return self.run_dir / "ledger.jsonl"

    @property
    def launches(self) -> Path:
        return self.run_dir / "launches.jsonl"


# --- hashes and the seal ----------------------------------------------------------------------


def digest(path: Path) -> str:
    """sha256 of a text file with LF line ends."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def raw_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def launcher_digest(path: Path) -> str:
    """sha256 of the launcher with its two local values (python, key file) as placeholders,
    so filling them in the sealed worktree's copy does not break the seal."""
    text = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    return hashlib.sha256(LOCAL_VALUES.sub(r"\1<LOCAL>\2", text).encode("utf-8")).hexdigest()


def sealed_text(lot: Lot) -> str:
    return (
        f"{digest(lot.prereg)}  {lot.prereg.name}\n"
        f"{launcher_digest(lot.launcher)}  {lot.launcher.name}\n"
    )


def seal(lot: Lot) -> str:
    """Write the seal once; a different one already there is refused, never overwritten (a
    prereg edited after its seal is an amendment, not a new seal)."""
    if instrument_commit(lot.prereg) is None:
        raise SystemExit("prereg.md names no instrument commit: write it before sealing")
    target = lot.prereg.with_suffix(".sha256")
    text = sealed_text(lot)
    if target.exists() and target.read_text(encoding="utf-8").strip() not in ("", text.strip()):
        raise SystemExit(f"{target.name} already holds a different seal: nothing written")
    target.write_text(text, encoding="utf-8", newline="\n")
    return text


def require_sealed(lot: Lot) -> None:
    target = lot.prereg.with_suffix(".sha256")
    if (
        not target.exists()
        or target.read_text(encoding="utf-8").strip() != sealed_text(lot).strip()
    ):
        raise SystemExit("prereg.md or its launcher is not sealed, or changed since: nothing spent")


def require_file(path: Path, sha256: str) -> None:
    """The exact text (LF) the prereg names, or nothing is spent or scored."""
    if digest(path) != sha256:
        raise SystemExit(f"{path.name} is not the sealed file: nothing spent or scored")


# --- the instrument ---------------------------------------------------------------------------


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=60
    )


def head() -> str:
    got = git("rev-parse", "HEAD")
    return got.stdout.strip() if got.returncode == 0 else "unknown"


def instrument_commit(prereg: Path) -> str | None:
    found = COMMIT.search(prereg.read_text(encoding="utf-8"))
    return found.group(1) if found else None


def require_instrument(lot: Lot) -> str:
    """HEAD descends from the registered commit and the instrument is unchanged since."""
    commit = instrument_commit(lot.prereg)
    if commit is None:
        raise SystemExit("prereg.md names no instrument commit: nothing spent")
    if git("merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
        raise SystemExit(f"HEAD does not descend from the instrument commit {commit[:12]}")
    if git("diff", "--quiet", commit, "--", *lot.instrument).returncode != 0:
        raise SystemExit("the instrument differs from its registered commit: nothing spent")
    loose = git("status", "--porcelain", "--untracked-files=all", "--", *lot.instrument)
    if loose.returncode != 0 or loose.stdout.strip():
        raise SystemExit("files under the instrument paths are not committed: nothing spent")
    return commit


def require_inputs(lot: Lot) -> None:
    for path, sha in lot.inputs:
        if not path.exists() or raw_digest(path) != sha:
            raise SystemExit(f"{path.name} is not the registered input: nothing spent")


# --- launches ---------------------------------------------------------------------------------


def history(lot: Lot) -> list[dict[str, Any]]:
    """One entry per launch: its `start` line, updated by its `end` line if it wrote one (a
    launch killed mid-run has none and counts as a launch, stopped `unfinished`)."""
    if not lot.launches.exists():
        return []
    launches: list[dict[str, Any]] = []
    for line in lot.launches.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("event") == "start":
            launches.append({**row, "stop_kind": "unfinished"})
        elif launches:
            launches[-1] = {**launches[-1], **row}
    return launches


def _note(lot: Lot, row: dict[str, Any]) -> None:
    lot.run_dir.mkdir(parents=True, exist_ok=True)
    with lot.launches.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def may_launch(past: Sequence[dict[str, Any]]) -> bool:
    """One launch and one relaunch at most; no relaunch after a 402, a 429 or the cap."""
    if not past:
        return True
    return len(past) == 1 and past[0].get("stop_kind") not in NO_RELAUNCH_AFTER


def stop_kind(stopped: str | None) -> str | None:
    if stopped is None:
        return None
    if "SpendCapReached" in stopped:
        return "cap"
    if "402" in stopped or "OutOfFunds" in stopped:
        return "funds"
    if "429" in stopped:
        return "limit"
    if stopped.startswith("model moved"):
        return "model"
    return "failure"


def unanswered_blocks(lot: Lot, missing: int) -> bool:
    """A report refuses while answers are missing and a launch is still allowed; after that,
    what is missing is scored as unanswered and reported."""
    return missing > 0 and may_launch(history(lot))


# --- plan and ask -----------------------------------------------------------------------------


def recorded(lot: Lot) -> RecordedDecider:
    """The lot's recording, only the lines its model answered: `RecordingDecider` writes a
    line before `ask_missing` sees the model, so an answer from another model is on disk but
    never counts as answered."""
    if not lot.fixture.exists():
        return RecordedDecider(())
    lines = [json.loads(x) for x in lot.fixture.read_text(encoding="utf-8").splitlines() if x]
    return RecordedDecider([e for e in lines if lot.serves(str(e.get("model") or ""))])


async def _missing(queries: Sequence[Query], lot: Lot) -> list[Query]:
    replay = recorded(lot)
    out = []
    for point, state, qs in queries:
        if not (await replay.decide(point, state, qs)).answers:
            out.append((point, state, qs))
    return out


def spent(lot: Lot) -> float:
    """What the lot's ledger already holds (reserved or settled), 0 before any launch."""
    return SpendLedger(lot.ledger, cap_usd=lot.cap_usd).spent() if lot.ledger.exists() else 0.0


def plan(queries: Sequence[Query], lot: Lot) -> dict[str, Any]:
    missing = asyncio.run(_missing(queries, lot))
    pessimistic = sum(estimate_usd(s, q, price_per_mtok=lot.price_per_mtok) for _, s, q in missing)
    return {
        "calls": len(queries),
        "recorded": len(queries) - len(missing),
        "to_ask": len(missing),
        "usd_at_median_request": round(len(missing) * MEDIAN_REQUEST_USD, 6),
        "usd_estimate_capped_decider": round(pessimistic, 6),
        "usd_spent_on_ledger": round(spent(lot), 6),
        "cap_usd": lot.cap_usd,
        "ledger": str(lot.ledger),
        "launches_so_far": len(history(lot)),
    }


def require_room(plan_: dict[str, Any], cap_usd: float) -> None:
    """Refuse a run whose higher estimate, on top of what the ledger already holds, does not
    fit under its cap: a relaunch is refused up front rather than stopped halfway."""
    most = max(plan_["usd_at_median_request"], plan_["usd_estimate_capped_decider"])
    total = most + plan_.get("usd_spent_on_ledger", 0.0)
    if total > cap_usd:
        raise SystemExit(f"{total:.4f} USD (spent + estimate) does not fit under {cap_usd}")


def load_key(variable: str = "TYPESAFE_API_KEY") -> None:
    """`variable` into this process from the file SANCHOPANZA_KEYS_ENV names, if unset.
    The value is never printed; a missing file or line is a refusal."""
    if os.environ.get(variable):
        return
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    if not named or not Path(named).is_file():
        raise SystemExit(f"{variable} unset and SANCHOPANZA_KEYS_ENV names no file")
    for line in Path(named).read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition("=")
        if name.strip() == variable and value.strip():
            os.environ[variable] = value.strip().strip('"').strip("'")
            return
    raise SystemExit(f"no {variable} line in the file SANCHOPANZA_KEYS_ENV names")


def jev_live(model: str) -> Any:  # pragma: no cover - builds the real client
    """The live decider: plain requests, no long context, no images, the lot's model."""
    from sanchopanza.providers.jev import JevDecider

    return JevDecider(model=model, long_context=False, images=False)


async def ask_missing(queries: Sequence[Query], lot: Lot, *, live: Any) -> dict[str, Any]:
    """Ask `live` (a Jev decider) for each missing query, in order, one at a time."""
    todo = await _missing(queries, lot)
    capped = CappedDecider(
        live,
        ledger=SpendLedger(lot.ledger, cap_usd=lot.cap_usd),
        batch=lot.name,
        max_usd=lot.cap_usd,
        price_per_mtok=lot.price_per_mtok,
    )
    recorder = RecordingDecider(capped, lot.fixture)
    asked, spent = 0, 0.0

    def out(stopped: str | None) -> dict[str, Any]:
        return {"asked": asked, "usd": round(spent, 6), "missing_at_start": len(todo),
                "stopped": stopped, "stop_kind": stop_kind(stopped)}  # fmt: skip

    for point, state, qs in todo:
        try:
            decision = await recorder.decide(point, state, qs)
        except Exception as error:  # noqa: BLE001 - any refusal or failure stops the run
            return out(f"{type(error).__name__}: {str(error)[:200]}")
        asked += 1
        spent += decision.cost_usd
        if decision.failed or not decision.answers:
            return out(f"failed or empty answer: {str(decision.error)[:200]}")
        if not lot.serves(decision.model):
            return out(f"model moved: {decision.model} != {lot.model}")
    return out(None)


async def session(
    queries: Sequence[Query],
    lot: Lot,
    *,
    make_live: Callable[[], Any],
    check: Callable[[str], Awaitable[None]],
    on_start: Callable[[], None],
) -> dict[str, Any]:
    """The whole live part in ONE event loop: the preflight, then the live decider built
    inside this loop, every call, and its close. A client made in one `asyncio.run` and used
    in another fails with "Event loop is closed" on every call (it cost another lot 498 of
    500 calls), so nothing live crosses a loop here."""
    await check(lot.model)
    on_start()
    live = make_live()
    try:
        return await ask_missing(queries, lot, live=live)
    finally:
        close = getattr(live, "aclose", None)
        if close is not None:
            await close()


def run_paid(
    lot: Lot,
    queries: Sequence[Query],
    *,
    load_key: Callable[[], None] = load_key,
    make_live: Callable[[], Any] | None = None,
    check: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Every check, then the key, then `session` in a single event loop. `load_key`,
    `make_live` and `check` default to the real ones; tests pass traps."""
    plan_ = plan(queries, lot)
    print(json.dumps(plan_, indent=1))
    if plan_["to_ask"] == 0:
        return {"head": head(), "asked": 0, "stopped": None, "note": "nothing missing"}
    require_room(plan_, lot.cap_usd)
    require_sealed(lot)
    commit = require_instrument(lot)
    require_inputs(lot)
    lot.run_dir.mkdir(parents=True, exist_ok=True)
    with _lockfile.locked(lot.run_dir / "paid", wait_s=1.0, stale_s=LOCK_STALE_S, strict=True):
        past = history(lot)
        if not may_launch(past):
            raise SystemExit("launch rule: no launch left (one relaunch at most, none after "
                             "a 402, a 429 or the cap)")  # fmt: skip
        if not past and lot.fixture.exists():
            raise SystemExit(f"first launch, but {lot.fixture.name} already exists: nothing spent")
        load_key()
        start = {"event": "start", "head": head(), "instrument": commit,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "to_ask": plan_["to_ask"]}  # fmt: skip
        result = asyncio.run(
            session(
                queries, lot, make_live=make_live or (lambda: jev_live(lot.model)),
                check=check or preflight, on_start=lambda: _note(lot, start),
            )
        )  # fmt: skip
        _note(lot, {"event": "end", **result})
    return {**start, **result}


async def preflight(model: str) -> None:  # pragma: no cover - one real decision, ~13 micro-USD
    """`jev-preflight` in the caller's loop, with its own client: the service answers, with
    the model asked for, before anything is asked."""
    from sanchopanza.providers.jev import apreflight

    result = await apreflight(model=model)
    if not result.ok or result.model != model:
        raise SystemExit(f"preflight {model}: {result.reason}, served {result.model}")
