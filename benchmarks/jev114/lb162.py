"""Lot lb162: Jev 1.14 with the long window as a substitute for Sonnet 5.5 on long documents,
confirmed on the 162 fresh LongBench v2 tasks at a -10-point margin. Pre-registered in
docs/results/2026-10-15-lb162/prereg.md; analysis in lb162_stats.py; phase S (Sonnet 5.5 in
clean Claude Code on the covered tasks) in benchmarks/h2h/h2h_lb162.py.

    python benchmarks/jev114/lb162.py --freeze-ids     # free: the 162 ids, metadata only
    python benchmarks/jev114/lb162.py --prepare        # free: their documents into the cache
    python benchmarks/jev114/lb162.py --plan           # free: counts, bands, cost, wall time
    python benchmarks/jev114/lb162.py --preflight      # free: cache, ids, ledger, seal
    python benchmarks/jev114/lb162.py --seal           # seal prereg.md + code + inputs
    python benchmarks/jev114/lb162.py --smoke --live   # PAID, sealed: one dev task
    python benchmarks/jev114/lb162.py --run --live     # PAID, sealed: phase J, caps in code
    python benchmarks/jev114/lb162.py --run --limit 5  # free: replay only
    python benchmarks/jev114/lb162.py                  # free: the analysis

Phase J asks jev-1.14.0 one Choice per task as lot L6's `j14-L` cell (l6.py): the
long-context header, the document middle-cut to 900,000 characters, the same question, and
when a call is unanswered the same task again at 0.8 and 0.64 of the window (here for this
model alone; L6 shrank both models together). Every live call goes through `CappedDecider` on
this lot's own ledger (LEDGER_PATH) and cap, reserved before the call. A task fails only on an
HTTP 400, a ReadTimeout or a Choice with no probability for its pick, at all three lengths.
Anything else stops every further call (`Stop`): the cap (final), an HTTP 402, an HTTP 429
(taken out of the client's retries, `no_retry_on_429`), any other error ("outage": the network,
5xx, 529 after its bounded retries, 401/403), three failed calls in a row, or a STOP file in
RUN_DIR (pauses). Answers are recorded with hashed keys (no text) in OUT, so a relaunch pays
only for what is missing. The key comes from TYPESAFE_API_KEY or the file SANCHOPANZA_KEYS_ENV
names (never printed).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import pathlib
import random
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in ("src", "benchmarks", "benchmarks/h2h"):
    sys.path.insert(0, str(REPO / extra))
sys.path.insert(0, str(HERE))

import l4  # noqa: E402  (Arm, load_key: lot L4's)
import l6  # noqa: E402  (the B3 question, cut, retry and reading of lot L6)
import lb162_stats as stats  # noqa: E402
import longdoc_data  # noqa: E402
import meter  # noqa: E402  (Claude Code's own price table)

from sanchopanza.contract import DeciderUnavailable  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-15-lb162"
IDS_FILE = OUT / "ids.txt"
IDS_SHA256 = "da7d37d327ac7e57b5456f3e02a4d4f2a7f305bdcac3482f35a7085203f1f771"
N_TASKS = 162
CACHE = longdoc_data.CACHE / "lb162"
TASKS = CACHE / "tasks.jsonl"
DOCS = CACHE / "docs"
RUN_DIR = pathlib.Path("C:/sp-runs/lb162")
LEDGER_PATH = RUN_DIR / "ledger.json"
LEDGER_CAP_USD = 1.20
BATCH = "lb162"
BATCH_CAP_USD = 1.20
SMOKE_CAP_USD = 0.02  # the smoke's own ceiling, on the same batch
MODEL = "jev-1.14.0"
CELL = stats.CELL
WINDOW = l6.CUT_CHARS["L"]
SHRINK = l6.SHRINK
TIMEOUT_S = l6.TIMEOUT_S["L"]
CONCURRENCY = 4
ORDER_SEED = 20261015
TAU = stats.TAU
ANSWERS = OUT / f"jev-answers-{CELL}.jsonl"
SMOKE_ANSWERS = OUT / f"smoke-answers-{CELL}.jsonl"
JEV_ROWS = OUT / "jev-scored.jsonl"
STOP_FILE = OUT / "jev-stop.json"
COVERED_FILE = OUT / "covered-ids.txt"
SONNET_ROWS = OUT / "sonnet-rows.jsonl"
SONNET_STOP = OUT / "sonnet-stop.json"
SUMMARY = OUT / "summary.json"
MAX_CONSECUTIVE_FAILURES = 3  # failed calls in a row (completion order) that pause phase J
# A task fails (and is asked again shorter) only on these; any other error pauses phase J.
TASK_FAILURES = ("HTTP 400", "jev unreachable: ReadTimeout")
PAUSES = ("funds", "limit", "outage", "failures", "manual")

# Estimates for the plan, from lot L6 (j14-L) and the 2026-10-06 confirmation (Sonnet, arm N).
JEV_USD_PER_MCHAR = 0.0117  # L6 j14-L: 0.2386 USD over 20.4 M characters shown, retries included
JEV_WORST_USD_PER_MCHAR = 0.0149  # L6 j14-L's dearest call per character shown
JEV_LATENCY_S = 1.7  # mean latency of a j14-L call
COVERAGE_EST = 0.54  # 27 of 50 at 0.6
SONNET_EST_USD = 0.138  # Sonnet's mean list USD on the tasks Jev covered at 0.6
SONNET_WALL_MEAN_S, SONNET_WALL_MEDIAN_S = 38.0, 23.0
# Phase S's money (enforced in h2h_lb162.py). The session's --max-budget-usd is h2h_longdoc's
# cap for Sonnet; Claude Code stops only between turns, so one turn may pass it. The worst turn
# rewrites Sonnet 5.5's whole 1M-token window to the cache and answers 32,000 tokens, at Claude
# Code's own rates (the ones list_usd and the ceiling are counted in, meter.CLAUDE_CODE_RATES),
# the dearer of its two cache-write rates. The 2026-10-06 confirmation's dearest session was
# 1.87 USD (about 195,000 tokens written to the cache).
SONNET_CEILING_USD = 18.00
SONNET_CAP_USD = 3.00
SONNET_WINDOW_TOKENS = 1_000_000
MAX_OUTPUT_TOKENS = 32_000


def worst_turn_usd() -> float:
    rates = meter.rates_of(meter.CLAUDE_CODE_RATES, meter.SONNET_55)
    write = max(rates.write_5m, rates.write_1h)
    return round((SONNET_WINDOW_TOKENS * write + MAX_OUTPUT_TOKENS * rates.output) / 1e6, 4)


WORST_TURN_USD = worst_turn_usd()  # 4.32: 1M tokens x 4.0 + 32k x 10, per million
SONNET_RESERVE_USD = round(SONNET_CAP_USD + WORST_TURN_USD, 4)  # held before each session


# ---- the 162 tasks ----------------------------------------------------------------------------


def fresh_ids(rows: Sequence[Mapping[str, Any]], used: set[str]) -> list[str]:
    """Eligible LongBench v2 tasks (domain and context length only) outside `used`, sorted."""
    return sorted(str(r["_id"]) for r in longdoc_data.eligible(rows) if str(r["_id"]) not in used)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_ids(path: pathlib.Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [x.strip() for x in lines if x.strip() and not x.startswith("#")]


def freeze_ids() -> str:  # pragma: no cover - needs the 465 MB cache
    """Write IDS_FILE once: the fresh pool of b3conf_power.py --pool, by metadata only."""
    if IDS_FILE.exists():
        raise SystemExit(f"{IDS_FILE.name} exists: the id list is frozen")
    rows = json.loads(longdoc_data.RAW.read_text(encoding="utf-8"))
    used = {t.task_id for t in longdoc_data.load()}
    ids = fresh_ids(rows, used)
    if len(used) != 60 or len(ids) != N_TASKS:
        raise SystemExit(f"expected 60 used and {N_TASKS} fresh, found {len(used)}, {len(ids)}")
    head = (f"# lot lb162: the {len(ids)} LongBench v2 tasks in the Single- and Multi-Document QA "
            "domains with contexts over 100,000 characters, outside the 60 drawn on 2026-10-06 "
            "(longdoc_data.eligible, metadata only), sorted.")  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    IDS_FILE.write_text(head + "\n" + "\n".join(ids) + "\n", encoding="utf-8", newline="\n")
    return digest(IDS_FILE)


def frozen_ids() -> list[str]:
    if not IDS_FILE.exists() or digest(IDS_FILE) != IDS_SHA256:
        raise SystemExit(f"{IDS_FILE} is missing or not the frozen list (sha256 {IDS_SHA256})")
    return read_ids(IDS_FILE)


def prepare() -> int:  # pragma: no cover - needs the 465 MB cache
    """The frozen tasks and their documents into CACHE (as longdoc_data.write_draw does)."""
    rows = {str(r["_id"]): r for r in json.loads(longdoc_data.RAW.read_text(encoding="utf-8"))}
    DOCS.mkdir(parents=True, exist_ok=True)
    tasks = [longdoc_data.to_task(rows[i], DOCS) for i in frozen_ids()]
    for task in tasks:
        path = pathlib.Path(task.doc_path)
        if not path.exists():
            path.write_text(rows[task.task_id]["context"], encoding="utf-8")
    TASKS.write_text("".join(json.dumps(asdict(t), ensure_ascii=False) + "\n" for t in tasks),
                     encoding="utf-8", newline="\n")  # fmt: skip
    return len(tasks)


def load_tasks() -> list[Any]:
    tasks = longdoc_data.load(TASKS)
    if [t.task_id for t in tasks] != frozen_ids():
        raise SystemExit(f"{TASKS} does not hold the frozen ids: run --prepare")
    return tasks


def docs_digest(tasks: Sequence[Any] | None = None) -> str:
    """One sha256 over every prepared document's id and the sha256 of its bytes."""
    lines = []
    for task in tasks if tasks is not None else load_tasks():
        h = hashlib.sha256()
        with pathlib.Path(task.doc_path).open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                h.update(block)
        lines.append(f"{task.task_id} {h.hexdigest()}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def data_problems() -> list[str]:
    try:
        tasks = load_tasks()
    except (SystemExit, FileNotFoundError) as error:
        return [f"lb162 data: {error}"]
    missing = [t.task_id for t in tasks if not pathlib.Path(t.doc_path).is_file()]
    return [f"lb162 data: {len(missing)} documents missing: --prepare"] if missing else []


# ---- phase J ----------------------------------------------------------------------------------


class Stop:
    """Why phase J stopped: `cap` (final: score what is complete), or a pause a relaunch
    resumes: `funds` (402), `limit` (429), `outage` (any other error but a task failure),
    `failures` (MAX_CONSECUTIVE_FAILURES failed calls in a row) or `manual` (STOP file)."""

    def __init__(self, stop_file: pathlib.Path | None = None,
                 max_consecutive: int | None = MAX_CONSECUTIVE_FAILURES) -> None:  # fmt: skip
        self.kind: str | None = None
        self.reason = ""
        self.stop_file = stop_file
        self.max_consecutive = max_consecutive
        self.consecutive = 0

    def call_done(self, answered: bool) -> None:
        """Count failed calls in a row (completion order); an answered call resets."""
        self.consecutive = 0 if answered else self.consecutive + 1
        if self.max_consecutive and self.consecutive >= self.max_consecutive:
            self.note("failures", f"{self.consecutive} failed calls in a row")

    def note(self, kind: str, reason: str) -> None:
        if self.kind is None:
            self.kind, self.reason = kind, reason

    def check(self) -> bool:
        if self.kind is None and self.stop_file is not None and self.stop_file.exists():
            self.note("manual", f"{self.stop_file} exists")
        return self.kind is not None


def stop_kind(error: BaseException) -> str | None:
    """None for a task failure (HTTP 400, ReadTimeout); otherwise the stop it is."""
    from sanchopanza.contract import DeciderOutOfFunds
    from sanchopanza.providers.capped import SpendCapReached

    said = str(error)
    if isinstance(error, SpendCapReached):
        return "cap"
    if isinstance(error, DeciderOutOfFunds) or "HTTP 402" in said:
        return "funds"
    if "HTTP 429" in said:
        return "limit"
    if any(failure in said for failure in TASK_FAILURES):
        return None
    return "outage"


class NotCalled(DeciderUnavailable):
    """Refused before the call: the lot is stopped."""


class Halting:
    """A live decider that stops every further call once one stop happened."""

    def __init__(self, inner: Any, stop: Stop) -> None:
        self._inner, self.stop, self.name = inner, stop, inner.name

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Any:
        if self.stop.check():
            raise NotCalled(f"stopped ({self.stop.kind}): not called")
        try:
            return await self._inner.decide(point, state, questions)
        except Exception as error:
            if kind := stop_kind(error):
                self.stop.note(kind, str(error))
            raise


def live_decider(stop: Stop, cap_usd: float) -> Halting:  # pragma: no cover - network
    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers import CappedDecider
    from sanchopanza.providers.jev import JevDecider

    ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
    inner = JevDecider(model=MODEL, long_context=True, images=False, timeout_s=TIMEOUT_S)
    return Halting(CappedDecider(inner, ledger=ledger, batch=BATCH, max_usd=cap_usd), stop)


def launch_order(n: int) -> list[int]:
    order = list(range(n))
    random.Random(ORDER_SEED).shuffle(order)
    return order


async def jev_one(task: Any, arm: Any, stop: Stop) -> dict[str, Any]:
    """One task, L6's j14-L cell: the full window, then 0.8 and 0.64 of it while unanswered.
    The row holds the id, the letters and the probabilities: no text."""
    text = pathlib.Path(task.doc_path).read_text(encoding="utf-8")
    qs = l6.b3_question(task)
    paid, tries, tokens, limit = 0.0, 0, None, WINDOW
    letter, p, probs = None, None, {}
    for factor in SHRINK:
        if stop.check():
            break
        limit = int(WINDOW * factor)
        state = {"question": task.question.strip(), "document": l6.middle_cut(text, limit)}
        decision = await arm.decide(l6.B3_POINT, state, qs)
        if decision.error == NotCalled.__name__:
            break
        tries += 1
        paid += decision.cost_usd
        tokens = decision.input_tokens
        letter, p, probs = l6.top_of(decision)
        stop.call_done(letter is not None)
        if letter is not None:
            break
    # Failed: every length asked and refused as a task failure, not cut short by a pause.
    tried_all = tries == len(SHRINK) and stop.kind in (None, "failures")
    status = "answered" if letter is not None else "failed" if tried_all else "stopped"
    cell = {"letter": letter, "p": p, "probs": probs, "usd": round(paid, 6), "tries": tries,
            "tokens": tokens, "shown_chars": min(len(text), limit)}  # fmt: skip
    return {"id": task.task_id, "gold": task.gold, "chars": task.chars, "length": task.length,
            "difficulty": task.difficulty, "status": status, CELL: cell}  # fmt: skip


async def run_j(tasks: Sequence[Any], live: Any, answers: pathlib.Path,
                stop: Stop) -> list[dict[str, Any]]:  # fmt: skip
    """Every task through one recorded-first arm (live when `live` is a decider), launched in
    the seeded order, at most CONCURRENCY in flight; rows in the tasks' order."""
    gate = asyncio.Semaphore(CONCURRENCY)  # tasks in flight: each reads its document in turn
    arm = l4.Arm(CELL, answers, MODEL, live, asyncio.Semaphore(CONCURRENCY))

    async def one(task: Any) -> dict[str, Any]:
        async with gate:
            return await jev_one(task, arm, stop)

    order = launch_order(len(tasks))
    done = await asyncio.gather(*(one(tasks[i]) for i in order))
    by_index = dict(zip(order, done, strict=True))
    return [by_index[i] for i in range(len(tasks))]


def batch_spent() -> float:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return 0.0
    return SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD).spent(BATCH)


def shown_chars(tasks: Sequence[Any]) -> int:
    return sum(min(t.chars, WINDOW) for t in tasks)


def jev_est_usd(tasks: Sequence[Any], rate: float = JEV_USD_PER_MCHAR) -> float:
    return shown_chars(tasks) * rate / 1e6


def jev_plan_refusal(spent: float, tasks: Sequence[Any], cap: float = BATCH_CAP_USD) -> str:
    """Empty when `tasks` (those without a recorded answer) at L6's cost per character shown
    fit under the cap after `spent`."""
    need = spent + jev_est_usd(tasks)
    return "" if need <= cap else (f"phase J does not fit: {spent:.4f} spent + {len(tasks)} "
                                   f"tasks, {need - spent:.4f} expected = {need:.4f} > {cap:g} "
                                   "USD")  # fmt: skip


def unrecorded(tasks: Sequence[Any]) -> list[Any]:
    """The tasks a free replay of ANSWERS leaves unanswered: what a live run would pay for."""
    rows = asyncio.run(run_j(tasks, None, ANSWERS, Stop(max_consecutive=None)))
    return [t for t, r in zip(tasks, rows, strict=True) if r["status"] != "answered"]


def no_retry_on_429() -> None:
    """The shipped client retries a 429 three times with backoff; this lot stops at the first
    (as lot memgate-long does). 529 keeps its bounded retries."""
    from sanchopanza.providers import jev

    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})


def preflight_or_stop() -> None:  # pragma: no cover - one real decision, about 13 micro-USD
    from sanchopanza.providers.jev import apreflight

    result = asyncio.run(apreflight(model=MODEL))
    if not result.ok or result.model != MODEL:
        raise SystemExit(f"preflight {MODEL}: {result.reason}, served {result.model}")


def write_jsonl(path: pathlib.Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def covered(rows: Sequence[Mapping[str, Any]], tau: float = TAU) -> list[str]:
    """Phase S's tasks: covered at tau, in a seeded random order (a stop leaves a random rest)."""
    ids = sorted(r["id"] for r in rows if stats.is_covered(r, tau))
    random.Random(ORDER_SEED).shuffle(ids)
    return ids


def merged(before: Sequence[Mapping[str, Any]],
           fresh: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:  # fmt: skip
    """`before` with the rows asked again (by index) in their place; a new list."""
    return [dict(fresh.get(i, row)) for i, row in enumerate(before)]


def phase_j_final(rows: Sequence[Mapping[str, Any]] | None,
                  stop: Mapping[str, Any] | None) -> str:  # fmt: skip
    """Empty when phase J is over: every task asked, or stopped by the cap (final, scored as it
    is); otherwise why phase S may not start."""
    if not rows or len(rows) != N_TASKS:
        return "phase J has not scored the 162 tasks"
    if any(r["status"] == "stopped" for r in rows) and (stop or {}).get("kind") != "cap":
        return f"phase J paused ({(stop or {}).get('kind')}): relaunch it first"
    return ""


def jev_exit(kind: str | None) -> int:
    """0 when phase J is over (finished, or final at its cap); 2 on a pause."""
    return 2 if kind in PAUSES else 0


def phase_j_live() -> int:  # pragma: no cover - network
    before = read_jsonl(JEV_ROWS)
    if before is not None and not any(r["status"] == "stopped" for r in before):
        print("phase J: scored already, frozen: not asked again", file=sys.stderr)
        return 0
    if (read_jsonl(STOP_FILE) or [{}])[0].get("kind") == "cap":
        raise SystemExit("phase J stopped at its cap: final, scored as it is; not relaunched")
    tasks = load_tasks()
    # A resume asks only the tasks a stop left unasked: a task already failed stays failed.
    todo = [i for i, r in enumerate(before) if r["status"] == "stopped"] if before else \
        list(range(len(tasks)))  # fmt: skip
    if why := jev_plan_refusal(batch_spent(), unrecorded([tasks[i] for i in todo])):
        raise SystemExit(why)
    l4.load_key()
    no_retry_on_429()
    preflight_or_stop()
    stop = Stop(RUN_DIR / "STOP")
    got = asyncio.run(run_j([tasks[i] for i in todo], live_decider(stop, BATCH_CAP_USD),
                            ANSWERS, stop))  # fmt: skip
    rows = merged(before or [{} for _ in tasks], dict(zip(todo, got, strict=True)))
    write_jsonl(JEV_ROWS, rows)  # with "stopped" rows after a pause: not frozen, resumed
    if stop.kind:
        print(f"phase J stopped ({stop.kind}): {stop.reason}", file=sys.stderr)
        STOP_FILE.write_text(json.dumps({"kind": stop.kind}) + "\n", encoding="utf-8",
                             newline="\n")  # fmt: skip
    elif STOP_FILE.exists():
        STOP_FILE.unlink()
    if not phase_j_final(rows, {"kind": stop.kind}):
        ids = covered(rows)
        COVERED_FILE.write_text(f"# lot lb162: {len(ids)} tasks covered at {TAU} (seeded order)\n"
                                + "".join(f"{i}\n" for i in ids), encoding="utf-8",
                                newline="\n")  # fmt: skip
    said = {"stop": stop.kind, "spent": round(batch_spent(), 6), "covered": len(covered(rows)),
            "tasks": len(rows)}  # fmt: skip
    print(json.dumps(said), file=sys.stderr)
    return jev_exit(stop.kind)


def smoke(live: bool) -> int:  # pragma: no cover - network when live
    """One LongBench dev task (lot L6's smoke task, outside the 162), its own answers file."""
    if live:
        l4.load_key()
        no_retry_on_429()
        preflight_or_stop()
    stop = Stop(RUN_DIR / "STOP")
    decider = live_decider(stop, SMOKE_CAP_USD) if live else None
    rows = asyncio.run(run_j(l6.b3_tasks(dev=True)[:1], decider, SMOKE_ANSWERS, stop))
    write_jsonl(OUT / "smoke-scored.jsonl", rows)
    print(json.dumps({"stop": stop.kind, "rows": rows}), file=sys.stderr)
    return jev_exit(stop.kind)


# ---- plan -------------------------------------------------------------------------------------


def sessions_before_guard(per_session_usd: float) -> int:
    """Sessions phase S runs before its guard stops it (a session starts only while spent +
    SONNET_RESERVE_USD <= the ceiling) when every session costs `per_session_usd`."""
    room = SONNET_CEILING_USD - SONNET_RESERVE_USD
    return math.floor(room / per_session_usd + 1e-9) + 1


def guaranteed_sessions() -> int:
    """At worst (every session at its cap plus one worst turn) the ceiling still runs this many."""
    return sessions_before_guard(SONNET_RESERVE_USD)


def plan(tasks: Sequence[Any], covered_ids: Sequence[str] | None) -> dict[str, Any]:
    n_cov = len(covered_ids) if covered_ids is not None else round(COVERAGE_EST * len(tasks))
    calls = len(tasks) * 1.1  # about one task in ten asked again shorter (L6: 5 of 50)
    pessimistic = jev_est_usd(tasks, JEV_WORST_USD_PER_MCHAR)
    return {
        "tasks": len(tasks),
        "by_length": dict(sorted(Counter(t.length for t in tasks).items())),
        "by_difficulty": dict(sorted(Counter(t.difficulty for t in tasks).items())),
        "whole_in_window": sum(t.chars <= WINDOW for t in tasks),
        "middle_cut": sum(t.chars > WINDOW for t in tasks),
        "phase_j": {"model": MODEL, "shown_mchars": round(shown_chars(tasks) / 1e6, 2),
                    "est_usd": round(jev_est_usd(tasks), 2),
                    "pessimistic_usd_before_retries": round(pessimistic, 2),
                    "cap_usd": BATCH_CAP_USD,
                    "est_wall_min": round(calls * JEV_LATENCY_S / CONCURRENCY / 60, 1)},
        "phase_s": {"sessions": n_cov, "measured": covered_ids is not None,
                    "est_usd": round(n_cov * SONNET_EST_USD, 2),
                    "ceiling_usd": SONNET_CEILING_USD, "worst_turn_usd": WORST_TURN_USD,
                    "reserve_per_session_usd": SONNET_RESERVE_USD,
                    "expected_within_ceiling": n_cov * SONNET_EST_USD <= SONNET_CEILING_USD,
                    "sessions_before_guard_at_mean": sessions_before_guard(SONNET_EST_USD),
                    "sessions_guaranteed_at_worst": guaranteed_sessions(),
                    "est_wall_min_mean": round(n_cov * SONNET_WALL_MEAN_S / 60, 1),
                    "est_wall_min_median": round(n_cov * SONNET_WALL_MEDIAN_S / 60, 1)},
    }  # fmt: skip


# ---- seal -------------------------------------------------------------------------------------

# Every file the two runners load or run (h2h_gaia's _load, gaia_arms' s_line, the hooks a
# session runs, the launcher), and every module of the package (SEALED_GLOBS).
SEALED = (
    "benchmarks/jev114/lb162.py", "benchmarks/jev114/lb162_stats.py", "tests/test_lb162.py",
    "tests/test_lb162_stops.py",
    "docs/results/2026-10-15-lb162/ids.txt",
    "benchmarks/jev114/l6.py", "benchmarks/jev114/l6_analysis.py", "benchmarks/jev114/l4.py",
    "benchmarks/jev114/l4_stats.py", "benchmarks/jev114/b3conf_power.py", "benchmarks/meter.py",
    "benchmarks/h2h/h2h_lb162.py", "benchmarks/h2h/h2h_longdoc.py",
    "benchmarks/h2h/longdoc_data.py", "benchmarks/h2h/longdoc-dev-ids.txt",
    "benchmarks/h2h/offline_common.py", "benchmarks/h2h/h2h_gaia.py",
    "benchmarks/h2h/gaia_arms.py", "benchmarks/h2h/gaia_session.py",
    "benchmarks/h2h/gaia_stats.py", "benchmarks/h2h/gaia_data.py",
    "benchmarks/h2h/gaia_scorer.py", "benchmarks/h2h/s_line.py", "benchmarks/h2h/s_install.json",
    "benchmarks/h2h/local_hook.py", "benchmarks/h2h/deny_hook.py", "benchmarks/h2h/launch.ps1",
    "benchmarks/browse/phase.py",
)  # fmt: skip
SEALED_GLOBS = ("src/sanchopanza/**/*.py",)
# Inputs outside the repository (not redistributed), hashed by their place under the home folder.
SEALED_DATA = (
    ".cache/sanchopanza/longdoc/hf/data.json",
    ".cache/sanchopanza/longdoc/tasks.jsonl",
    ".cache/sanchopanza/longdoc/lb162/tasks.jsonl",
)
DOCS_KEY = "~/.cache/sanchopanza/longdoc/lb162/docs/*"  # docs_digest of the 162 documents


def sealed_paths() -> list[str]:
    globbed = sorted({p.relative_to(REPO).as_posix() for g in SEALED_GLOBS for p in REPO.glob(g)
                      if "__pycache__" not in p.parts})  # fmt: skip
    return [*SEALED, *(p for p in globbed if p not in SEALED)]


def raw_digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest() -> dict[str, str]:
    """`<path> -> sha256` of prereg.md, the code (LF bytes), the external inputs and the
    prepared documents (one aggregate)."""
    doc = (OUT / "prereg.md").relative_to(REPO).as_posix()
    out = {p: digest(REPO / p) for p in (doc, *sealed_paths())}
    data = {f"~/{p}": raw_digest(pathlib.Path.home() / p) for p in SEALED_DATA}
    return out | data | {DOCS_KEY: docs_digest()}


def combined(found: Mapping[str, str]) -> str:
    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in found.items()).encode()).hexdigest()


def seal(again: bool = False) -> str:
    """prereg.manifest.json and prereg.sha256 (lot L6's scheme). A different seal already there
    is refused unless `again` (a re-seal before any answer of the 162, said in prereg)."""
    found = manifest()
    value = combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        if not again:
            raise SystemExit("prereg.sha256 already holds another seal: nothing written")
        if ANSWERS.exists():
            raise SystemExit("answers of the 162 exist: a re-seal is an amendment, not a seal")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def require_prereg() -> None:
    target = OUT / "prereg.sha256"
    if not target.exists() or target.read_text().strip() != combined(manifest()):
        raise SystemExit("prereg.md, the code or the inputs differ from the seal: nothing spent")


def seal_state() -> str:
    target = OUT / "prereg.sha256"
    if not target.exists():
        return "not sealed"
    return "sealed, matches" if target.read_text().strip() == combined(manifest()) else "MISMATCH"


def docs_problems() -> list[str]:
    """The 162 prepared documents against the seal's aggregate (nothing to compare unsealed)."""
    path = OUT / "prereg.manifest.json"
    if not path.exists():
        return []
    sealed = json.loads(path.read_text(encoding="utf-8")).get(DOCS_KEY)
    return [] if sealed == docs_digest() else ["the prepared documents differ from the seal"]


# ---- analysis and main ------------------------------------------------------------------------


def sonnet_by_id() -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in read_jsonl(SONNET_ROWS) or []}


def pause_reasons(rows: Sequence[Mapping[str, Any]], jev_stop: Mapping[str, Any] | None,
                  sonnet_stop: Mapping[str, Any] | None,
                  run_dir: pathlib.Path | None = None) -> list[str]:  # fmt: skip
    """Why no verdict may be read yet: a LIMIT.flag or STOP in the run folder, phase J not
    over, or phase S (when it has covered tasks to run) not ended by finishing or its ceiling."""
    reasons = [f"{name} in the run folder" for name in ("LIMIT.flag", "STOP")
               if ((run_dir or RUN_DIR) / name).exists()]  # fmt: skip
    if why := phase_j_final(rows, jev_stop):
        return [*reasons, why]
    kind = (sonnet_stop or {}).get("kind")
    if covered(rows) and kind not in ("done", "ceiling"):
        reasons.append(f"phase S {kind or 'not run'}")
    return reasons


def analysis() -> dict[str, Any]:
    rows = read_jsonl(JEV_ROWS)
    if rows is None:
        raise SystemExit(f"no {JEV_ROWS.name}: phase J has not run")
    jev_stop = (read_jsonl(STOP_FILE) or [None])[0]
    sonnet_stop = (read_jsonl(SONNET_STOP) or [None])[0]
    paused = pause_reasons(rows, jev_stop, sonnet_stop)
    out = stats.analyse(rows, sonnet_by_id(), paused=paused) | {
        "jev_stop": (jev_stop or {}).get("kind"),
        "sonnet_stop": (sonnet_stop or {}).get("kind"),
        "ledger_batch_usd": round(batch_spent(), 6),
    }
    SUMMARY.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def preflight() -> list[str]:
    problems = [*data_problems()]
    if not longdoc_data.RAW.exists():
        problems.append(f"no LongBench cache at {longdoc_data.RAW}")
    if not problems:
        problems.extend(docs_problems())
        if why := jev_plan_refusal(batch_spent(), unrecorded(load_tasks())):
            problems.append(why)
        print(f"documents: sha256 {docs_digest()}", file=sys.stderr)
    state = seal_state()
    print(f"seal: {state}; ledger {LEDGER_PATH} batch {BATCH} spent {batch_spent():.4f}",
          file=sys.stderr)  # fmt: skip
    return [*problems, *([] if state != "MISMATCH" else ["seal mismatch"])]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--freeze-ids", "--prepare", "--plan", "--preflight", "--seal", "--smoke",
                 "--run"):  # fmt: skip
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--live", action="store_true", help="with --run or --smoke: PAID")
    ap.add_argument("--limit", type=int, default=None, help="with --run (replay): first N tasks")
    ap.add_argument("--reseal", action="store_true", help="with --seal: replace a seal")
    args = ap.parse_args(argv)
    if args.live and not (args.run or args.smoke):
        ap.error("--live goes with --run or --smoke")
    if args.live:
        if args.limit is not None:
            ap.error("--live runs the registered tasks whole: no --limit")
        require_prereg()  # before anything else of a live path
        return smoke(True) if args.smoke else phase_j_live()
    if args.freeze_ids:
        print(freeze_ids())
        return 0
    if args.prepare:
        print(f"{prepare()} tasks in {TASKS}")
        return 0
    if args.seal:
        print(seal(again=args.reseal))
        return 0
    if args.plan:
        rows = read_jsonl(JEV_ROWS)
        ids = read_ids(COVERED_FILE) if COVERED_FILE.exists() else None
        print(json.dumps(plan(load_tasks(), ids if rows else None), indent=1))
        return 0
    if args.preflight:
        problems = preflight()
        print("preflight: " + ("; ".join(problems) or "ok"), file=sys.stderr)
        return 3 if problems else 0
    if args.smoke:
        return smoke(False)
    if args.run:
        tasks = load_tasks()[: args.limit]
        rows = asyncio.run(run_j(tasks, None, ANSWERS, Stop()))
        write_jsonl(CACHE / f"replay-first{len(tasks)}.jsonl", rows)  # private, not a result
        print(json.dumps(Counter(r["status"] for r in rows)), file=sys.stderr)
        return 0
    print(json.dumps(analysis()["primary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
