"""Lot memgate-long: the memory gate reading every LongMemEval session whole in one call (the
long window), confirmed on jev-1.13.0 on the 84 test questions lot L6 did not reach.
Pre-registered in docs/results/2026-10-15-memgate-long/prereg.md.

    python benchmarks/memgate_long/memgate_long.py --plan          # free: ids, estimate, inputs
    python benchmarks/memgate_long/memgate_long.py --seal          # seal prereg.md + code
    python benchmarks/memgate_long/memgate_long.py --smoke --live  # dev questions, own sub-cap
    python benchmarks/memgate_long/memgate_long.py --run --live    # spends (caps in code)
    python benchmarks/memgate_long/memgate_long.py --run           # free: replay only
    python benchmarks/memgate_long/memgate_long.py                 # analysis, free

The questions: lot L6 launched the 120 LongMemEval S test questions of
docs/results/2026-09-28-memory-gate in a seeded order (20261015) and its soft stop left the first
36. This lot asks the other 84, in the same order. Per question, one model (`j13r`,
jev-1.13.0, the production DEFAULT_MODEL): `needs_recall` once, then the gate's triage in two
windows: `S` as shipped (900 characters a session, a tournament) and `L` with the long-context
header and every session whole in one call (L6's `LONG_LIMITS`). `bm25@3` is computed and the
gate recorded on 2026-09-28 (`rec13-S`) is replayed, both free. L6's functions are imported.

Every live call goes through `CappedDecider` on this lot's own ledger (LEDGER_PATH) and cap,
at most CONCURRENCY in flight. A stop is dead: later calls are refused unasked and the wave
it hit is dropped. A cap refusal ends the lot with the completed waves written; an outage (HTTP
401/402/403/429/5xx, no connection), a wrong model or 3 failed calls in a row is a pause that
writes nothing (a relaunch replays what was paid and asks the rest). Answers are recorded per
cell in OUT (hashed keys, no text). The key comes from TYPESAFE_API_KEY or the `.env` that
SANCHOPANZA_KEYS_ENV names (lot L4's `load_key`), inside the process, never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import hashlib
import json
import pathlib
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "benchmarks" / "jev114"))
sys.path.insert(0, str(HERE))

import l6  # noqa: E402  (puts src, benchmarks/memory_gate and benchmarks/jev114 on the path)

l4 = l6.l4

OUT = REPO / "docs" / "results" / "2026-10-15-memgate-long"
L6_SCORED = l6.OUT / "a7-scored.jsonl"  # L6's 36 questions: excluded here, pooled descriptively
LEDGER_PATH = pathlib.Path("C:/sp-runs/memgate-long/ledger.json")  # this lot's own ledger
LEDGER_CAP_USD = 1.50  # the whole lot, smoke included
BATCH, BATCH_CAP_USD = "memgate-long", 1.50
SMOKE_BATCH, SMOKE_CAP_USD = "memgate-long-smoke", 0.05
SMOKE_QUESTIONS = 2  # LongMemEval dev questions, the first of the seeded order
CONCURRENCY = l6.CONCURRENCY  # 4 calls in flight
WAVE = l6.A7_WAVE  # 2 questions at once
MODEL_KEY = "j13r"
MODEL = l4.MODELS[MODEL_KEY]  # jev-1.13.0
CELLS = (f"{MODEL_KEY}-S", f"{MODEL_KEY}-L")
L6_USED = 36
N_QUESTIONS = 84
# L6's A7 spend: 0.4425 USD for 36 questions x 2 models x (needs_recall + S + L).
L6_A7_USD, L6_A7_QUESTIONS, L6_A7_MODELS = 0.4425, 36, 2
Q_EST_USD = 0.010  # a question's soft-stop estimate, one model (L6 measured 0.0061)
MIN_QUESTIONS = 20
HALTED: list[str] = []  # a cap refusal, a 402 or a 429: every later call is refused unasked


# ---- questions --------------------------------------------------------------------------------


def l6_rows() -> list[dict[str, Any]]:
    rows = [json.loads(x) for x in L6_SCORED.read_text(encoding="utf-8").splitlines() if x]
    return sorted(rows, key=lambda r: r["rank"])


def select(test: Sequence[Mapping[str, Any]], dev_ids: set[str],
           used_ids: Sequence[str]) -> list[Mapping[str, Any]]:  # fmt: skip
    """The test questions after L6's in L6's seeded launch order. Refuses unless L6's are
    exactly the head of that order, and the rest is N_QUESTIONS, disjoint from L6's and dev."""
    order = l6.launch_order(len(test))
    head = [test[i]["question_id"] for i in order[: len(used_ids)]]
    if head != list(used_ids):
        raise SystemExit("L6's questions are not the head of the seeded order: nothing selected")
    rest = [test[i] for i in order[len(used_ids) :]]
    ids = [q["question_id"] for q in rest]
    if len(ids) != N_QUESTIONS or len(set(ids)) != N_QUESTIONS:
        raise SystemExit(f"{len(ids)} questions left, not {N_QUESTIONS}: nothing selected")
    if set(ids) & set(used_ids) or set(ids) & dev_ids:
        raise SystemExit("the questions overlap L6's or the dev slice: nothing selected")
    return rest


def questions(dev: bool = False) -> list[Mapping[str, Any]]:
    test = l6.a7_questions(False)
    dev_qs = l6.a7_questions(True)
    if dev:
        return [dev_qs[i] for i in l6.launch_order(len(dev_qs))][:SMOKE_QUESTIONS]
    used = [r["id"] for r in l6_rows()]
    return select(test, {q["question_id"] for q in dev_qs}, used)


# ---- arms -------------------------------------------------------------------------------------


CAP, PAUSE = "cap", "pause"
STOP_STATUSES = frozenset({401, 402, 403, 429})  # and every 5xx (after 529's bounded retries)
MAX_CONSECUTIVE_FAILURES = 3
_FAILS = {"consecutive": 0}


def halt(kind: str, why: str) -> None:
    HALTED.append(f"{kind}: {why}")


def halt_kind() -> str | None:
    """CAP when the first stop was a cap refusal (the money is spent: completed waves are the
    run), PAUSE for any other stop (an outage: nothing written, a relaunch resumes)."""
    return HALTED[0].split(":", 1)[0] if HALTED else None


def reset() -> None:
    HALTED.clear()
    _FAILS["consecutive"] = 0


def stops(error: Exception) -> bool:
    """An outage that a later call would meet too: 401, 402, 403, 429, a 5xx, or no connection.
    A timeout and an HTTP 400 (one request too long, say) are that cell's failure."""
    import re

    text = str(error)
    found = re.search(r"HTTP (\d{3})", text)
    if found and (int(found.group(1)) in STOP_STATUSES or int(found.group(1)) >= 500):
        return True
    return "unreachable" in text and "Timeout" not in text


def error_class(error: Exception) -> str:
    """A failed call's class, a name with no text: the transport error (`ReadTimeout`,
    `ConnectTimeout`, `ConnectError`), `HTTP<status>`, or the exception's class."""
    import re

    text = str(error)
    if found := re.search(r"unreachable: (\w+)", text):
        return found.group(1)
    if found := re.search(r"HTTP (\d{3})", text):
        return f"HTTP{found.group(1)}"
    return type(error).__name__


# The question being asked: `one` sets a fresh dict, StopDead notes each failed call's class in
# it under the cell (or the look). Each question runs in its own task, so they do not mix.
CELL_ERRORS: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "memgate_long_cell_errors", default=None
)


class StopDead:
    """A live decider that stops the lot dead: at a cap refusal (CAP), and at an outage
    (`stops`), an answer served by another model, or MAX_CONSECUTIVE_FAILURES failed calls in a
    row of any kind (PAUSE). The reason is noted in HALTED and every later call raises without
    being made. A wrong-model answer raises before `RecordingDecider` can record it. Each failed
    call's class goes to the question's CELL_ERRORS under `cell` (`<model>-look` for the look)."""

    def __init__(self, inner: Any, cell: str = "") -> None:
        self._inner, self.name, self._cell = inner, inner.name, cell

    def _note(self, point: str, label: str) -> None:
        errors = CELL_ERRORS.get()
        if errors is not None:
            key = f"{MODEL_KEY}-look" if point == "recall" else self._cell
            errors.setdefault(key, label)

    def _failed(self, why: str) -> None:
        _FAILS["consecutive"] += 1
        if _FAILS["consecutive"] >= MAX_CONSECUTIVE_FAILURES and not HALTED:
            halt(PAUSE, f"{MAX_CONSECUTIVE_FAILURES} failed calls in a row, the last: {why}")

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Any:
        from sanchopanza.contract import DeciderUnavailable
        from sanchopanza.providers.capped import SpendCapReached

        if HALTED:
            raise DeciderUnavailable(f"halted, not called: {HALTED[0]}")
        try:
            decision = await self._inner.decide(point, state, questions)
        except SpendCapReached as error:
            halt(CAP, str(error))
            self._note(point, "SpendCapReached")
            raise
        except Exception as error:
            if stops(error):
                halt(PAUSE, str(error))
            self._note(point, error_class(error))
            self._failed(f"{type(error).__name__}: {error}")
            raise
        if decision.model != MODEL:
            halt(PAUSE, f"asked {MODEL}, served {decision.model}: not recorded")
            self._note(point, "WrongModel")
            raise DeciderUnavailable(HALTED[-1])
        if decision.failed or not decision.answers:
            self._note(point, "NoAnswer")
            self._failed(decision.error or "no answers")
        else:
            _FAILS["consecutive"] = 0
        return decision


def jev_inner(cell: str) -> Any:
    from sanchopanza.providers.jev import JevDecider

    window = cell.split("-")[1]
    return JevDecider(model=MODEL, long_context=window == "L", images=False,
                      timeout_s=l6.TIMEOUT_S[window])  # fmt: skip


def cell_arms(name: str, live: bool, gate: asyncio.Semaphore, batch: str, cap_usd: float,
              make_inner: Callable[[str], Any] = jev_inner) -> dict[str, Any]:  # fmt: skip
    """One recorded-first arm per cell (`l4.Arm`, answers in OUT); live through this lot's
    ledger and `cap_usd` on `batch` when `live`."""
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.budget import SpendLedger
        from sanchopanza.providers import CappedDecider

        ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
        for cell in CELLS:
            inner = make_inner(cell)
            capped[cell] = StopDead(CappedDecider(inner, ledger=ledger, batch=batch,
                                                  max_usd=cap_usd), cell)  # fmt: skip
    return {cell: l4.Arm(cell, OUT / f"{name}-answers-{cell}.jsonl", MODEL, capped.get(cell),
                         gate) for cell in CELLS}  # fmt: skip


def spent(batch: str | None = None) -> float:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return 0.0
    return SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD).spent(batch)


# ---- one question -----------------------------------------------------------------------------


async def one(position: int, q: Mapping[str, Any], arms: Mapping[str, Any],
              rec: Any | None) -> dict[str, Any]:  # fmt: skip
    """L6's A7 row for one model: ids, gold, sizes, bm25@3, the excerpt ceiling, the look and
    the kept session indexes per window (no text). The window order alternates with the rank.
    `errors`: the class of each live cell's first failed call (no text), when any failed."""
    import longmemeval as lme

    errors: dict[str, str] = {}
    CELL_ERRORS.set(errors)  # this question's task only
    ms = lme.memories_of(q)
    seen, total = lme.excerpt_ceiling(q)
    row: dict[str, Any] = {"id": q["question_id"], "type": q["question_type"],
                           "gold": sorted(lme.gold_of(q)), "sizes": [len(m.body) for m in ms],
                           "bm25@3": sorted(lme.arm_bm25(q, ms, 3)),
                           "excerpt_seen": seen, "excerpt_total": total}  # fmt: skip
    row[f"{MODEL_KEY}-look"] = await l6.a7_look(arms[CELLS[0]], q)
    windows = ("S", "L") if position % 2 == 0 else ("L", "S")
    for window in windows:
        cell = f"{MODEL_KEY}-{window}"
        row[cell] = await l6.a7_triage(arms[cell], q, ms, window)
    if rec is not None:
        row["rec13-look"] = await l6.a7_look(rec, q)
        row["rec13-S"] = await l6.a7_triage(rec, q, ms, "S")
    if errors:
        row["errors"] = dict(sorted(errors.items()))
    return row


async def run(qs: Sequence[Mapping[str, Any]], *, live: bool, name: str, batch: str,
              cap_usd: float, first_rank: int = L6_USED, with_rec: bool = True,
              make_inner: Callable[[str], Any] = jev_inner) -> list[dict[str, Any]]:  # fmt: skip
    """Every question in `qs`, WAVE at a time; the completed waves' rows. Live, a wave is not
    started when Q_EST_USD a question would not fit in the room left (`room`); a halt drops the
    wave it stopped and ends the run, as the soft stop does."""
    reset()
    gate = asyncio.Semaphore(CONCURRENCY)
    arms = cell_arms(name, live, gate, batch, cap_usd, make_inner)
    rec = l6.recorded_arm("rec13-S", l6.A7_RECORDED, gate) if with_rec else None
    rows: list[dict[str, Any]] = []
    for start in range(0, len(qs), WAVE):
        wave = qs[start : start + WAVE]
        if live and Q_EST_USD * len(wave) > room(batch, cap_usd):
            print(f"soft stop before question {start}: the cap would not hold", file=sys.stderr)
            break
        got = await asyncio.gather(*(one(start + k, q, arms, rec) for k, q in enumerate(wave)))
        if HALTED:
            print(f"stopped in the wave at question {start}, dropped: {HALTED[0]}",
                  file=sys.stderr)  # fmt: skip
            break
        rows = [*rows, *(r | {"rank": first_rank + start + k} for k, r in enumerate(got))]
    return rows


def room(batch: str, cap_usd: float) -> float:
    """Dollars left under both the batch's cap and the ledger's."""
    return min(cap_usd - spent(batch), LEDGER_CAP_USD - spent())


# ---- cost, plan -------------------------------------------------------------------------------


def estimate(qs84: Sequence[Mapping[str, Any]], qs36: Sequence[Mapping[str, Any]]) -> dict:
    """L6's A7 spend per question and model, scaled by the sessions' characters (the L call,
    every session whole, is most of a question's cost)."""
    import longmemeval as lme

    def chars(qs: Sequence[Mapping[str, Any]]) -> int:
        return sum(len(m.body) for q in qs for m in lme.memories_of(q))

    per_model = L6_A7_USD / L6_A7_MODELS
    c84, c36 = chars(qs84), chars(qs36)
    usd = per_model * c84 / c36
    return {"l6_usd_per_question_model": round(per_model / L6_A7_QUESTIONS, 5),
            "chars_84": c84, "chars_36": c36, "expected_usd": round(usd, 4),
            "smoke_usd": round(SMOKE_QUESTIONS * per_model / L6_A7_QUESTIONS, 4),
            "cap_usd": BATCH_CAP_USD, "smoke_cap_usd": SMOKE_CAP_USD}  # fmt: skip


def plan() -> int:
    """Free: the inputs exist, the 84 are selected, the estimate and the power. No key read,
    nothing asked."""
    import longmemeval as lme
    import memgate_long_analysis as an

    missing = [p for p in SEALED_DATA if not (pathlib.Path.home() / p).is_file()]
    missing += [p for p in SEALED if not (REPO / p).is_file()]
    for p in missing:
        print(f"missing: {p}", file=sys.stderr)
    if missing:
        return 2
    qs = questions()
    by_id = {q["question_id"]: q for q in l6.a7_questions(False)}
    old = l6_rows()
    ids = {q["question_id"] for q in qs}
    dev_ids = {q["question_id"] for q in l6.a7_questions(True)}
    disjoint = not ids & {r["id"] for r in old} and not ids & dev_ids
    gold = [lme.gold_of(q) for q in qs]
    bm25 = sum(
        len(lme.arm_bm25(q, lme.memories_of(q), 3) & g) for q, g in zip(qs, gold, strict=True)
    )
    out = {
        "questions": len(qs), "distinct": len(ids), "disjoint_from_l6_and_dev": disjoint,
        "first_ids": [q["question_id"] for q in qs[:3]],
        "estimate": estimate(qs, [by_id[r["id"]] for r in old]),
        "bm25@3_recall_on_84": round(bm25 / sum(len(g) for g in gold), 4),
        "power": an.power(old, len(qs)),
        "ledger": str(LEDGER_PATH), "ledger_spent": round(spent(), 6),
        "sealed": seal_ok(),
    }  # fmt: skip
    print(json.dumps(out, indent=1))
    return 0


# ---- seal -------------------------------------------------------------------------------------

SEALED_FIXED = (
    "benchmarks/memgate_long/memgate_long.py", "benchmarks/memgate_long/memgate_long_analysis.py",
    "tests/test_memgate_long.py", "benchmarks/jev114/l6.py", "benchmarks/jev114/l6_analysis.py",
    "benchmarks/jev114/l4.py", "benchmarks/jev114/l4_stats.py",
    "docs/results/2026-10-15-jev114-l6/a7-scored.jsonl",
    "benchmarks/triage_sets/run.py",  # memory_gate/run.py loads it for BM25
)  # fmt: skip
# Every module a run can load: the whole package and the memory-gate benchmark, by glob.
SEALED_GLOBS = ("src/sanchopanza/**/*.py", "benchmarks/memory_gate/*.py")


def sealed_paths() -> tuple[str, ...]:
    found = {p.relative_to(REPO).as_posix() for g in SEALED_GLOBS for p in REPO.glob(g)
             if "__pycache__" not in p.parts}  # fmt: skip
    return (*SEALED_FIXED, *sorted(found - set(SEALED_FIXED)))


SEALED = sealed_paths()
# Inputs outside the repository (not redistributed), hashed by their place under the home folder.
SEALED_DATA = (
    ".cache/sanchopanza/memory_gate/longmemeval/longmemeval_s_cleaned.json",
    ".cache/sanchopanza/memory_gate/longmemeval/decisions.jsonl",
)


def manifest() -> dict[str, str]:
    """`<path> -> sha256` of prereg.md, the code (LF bytes) and the external inputs (L6's)."""

    def digest(path: pathlib.Path, text: bool) -> str:
        data = path.read_bytes()
        return hashlib.sha256(data.replace(b"\r\n", b"\n") if text else data).hexdigest()

    doc = (OUT / "prereg.md").relative_to(REPO).as_posix()
    out = {p: digest(REPO / p, True) for p in (doc, *SEALED)}
    return out | {f"~/{p}": digest(pathlib.Path.home() / p, False) for p in SEALED_DATA}


def seal(again: bool = False) -> str:
    """prereg.manifest.json and prereg.sha256 (L6's scheme). Written once: a different seal
    already there is refused unless `again`, and `again` is refused once anything was spent in
    this lot's ledger or any answer was recorded (a re-seal only before the first live call)."""
    found = manifest()
    value = l6.combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value) and not again:
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    if again and (spent() > 0 or any(OUT.glob("*-answers-*.jsonl"))):
        raise SystemExit("answers or spend exist already: no re-seal, nothing written")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_ok() -> bool:
    target = OUT / "prereg.sha256"
    return target.exists() and target.read_text().strip() == l6.combined(manifest())


def require_prereg() -> None:
    if not seal_ok():
        raise SystemExit("prereg.md, the code or the inputs differ from the seal: nothing spent")


# ---- live -------------------------------------------------------------------------------------


def no_retry_on_429() -> None:
    """The shipped client retries a 429 three times with backoff; this lot stops at the first."""
    from sanchopanza.providers import jev

    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})


def preflight_or_stop() -> None:
    """`jev-preflight` for jev-1.13.0 only (one Truth, tens of micro-dollars, off the ledger)."""
    from sanchopanza.providers.jev import apreflight

    result = asyncio.run(apreflight(model=MODEL))
    if not result.ok or result.model != MODEL:
        raise SystemExit(f"preflight {MODEL}: {result.reason}, served {result.model}")
    print(f"preflight {MODEL}: ok", file=sys.stderr)


def go_live() -> None:
    require_prereg()
    l4.load_key()
    no_retry_on_429()
    preflight_or_stop()


def write_rows(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}-scored.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                              encoding="utf-8", newline="\n")  # fmt: skip


def read_rows(name: str) -> list[dict[str, Any]] | None:
    path = OUT / f"{name}-scored.jsonl"
    if not path.exists():
        return None
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def finish(name: str, rows: list[dict[str, Any]], batch: str, cap_usd: float) -> int:
    """A pause (an outage, a wrong model, failures in a row, or a cap refusal while the room
    left still holds a question: a ledger fault) writes nothing and exits 2: a relaunch replays
    what was paid and asks the rest. A cap stop writes the completed waves (the cap is the end
    of the lot's money) and exits 0, as the soft stop does. No rows: nothing written, 2."""
    kind = halt_kind()
    if kind == CAP and room(batch, cap_usd) >= Q_EST_USD:
        # The ledger refused with money left: a lock it could not take, a file it could not
        # write. Not the end of the money: a pause.
        print(f"{name}: PAUSE, the ledger refused with room left, rows not written: "
              f"{HALTED[0]}", file=sys.stderr)  # fmt: skip
        return 2
    if kind == PAUSE:
        print(f"{name}: PAUSE, rows not written: {HALTED[0]}", file=sys.stderr)
        return 2
    if not rows:
        print(f"{name}: no question completed, nothing written", file=sys.stderr)
        return 2
    if kind == CAP:
        print(f"{name}: cap reached, {len(rows)} questions of completed waves written",
              file=sys.stderr)  # fmt: skip
    write_rows(name, rows)
    return 0


def smoke(live: bool) -> int:
    """SMOKE_QUESTIONS dev questions, both cells, on the smoke's own batch and sub-cap."""
    if live:
        go_live()
    rows = asyncio.run(run(questions(dev=True), live=live, name="smoke", batch=SMOKE_BATCH,
                           cap_usd=SMOKE_CAP_USD, first_rank=0, with_rec=False))  # fmt: skip
    code = finish("smoke", rows, SMOKE_BATCH, SMOKE_CAP_USD)
    print(json.dumps({"smoke": round(spent(SMOKE_BATCH), 6), "ledger": round(spent(), 6)}),
          file=sys.stderr)  # fmt: skip
    return code


def run_live() -> int:
    """The run of record. 0 when its rows were written; 2 when it paused."""
    if read_rows("a7") is not None:
        print("a7: scored already, frozen: not asked again", file=sys.stderr)
        return 0
    go_live()
    rows = asyncio.run(run(questions(), live=True, name="a7", batch=BATCH,
                           cap_usd=BATCH_CAP_USD))  # fmt: skip
    return finish("a7", rows, BATCH, BATCH_CAP_USD)


def analyse_and_write() -> int:
    import memgate_long_analysis as an

    rows = read_rows("a7")
    if rows is None:
        print("no a7-scored.jsonl yet: nothing to analyse", file=sys.stderr)
        return 0
    summary = an.analyse(rows, min_questions=MIN_QUESTIONS, l6_rows=l6_rows())
    summary["spent"] = {"batch": round(spent(BATCH), 6), "smoke": round(spent(SMOKE_BATCH), 6),
                        "ledger": round(spent(), 6)}  # fmt: skip
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8",
                                      newline="\n")  # fmt: skip
    print(json.dumps({"confirmation": summary["confirmation"],
                      "bm25": summary["bm25_verdicts"]}, indent=1), file=sys.stderr)  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", "--dry", action="store_true", help="free: inputs and estimate")
    parser.add_argument("--run", action="store_true", help="ask (replay first) and score")
    parser.add_argument("--live", action="store_true", help="ask Jev what is not recorded")
    parser.add_argument("--smoke", action="store_true", help="dev questions only")
    parser.add_argument("--seal", action="store_true", help="seal prereg.md and the code")
    parser.add_argument("--reseal", action="store_true", help="with --seal: replace a seal")
    args = parser.parse_args(argv)
    if args.plan:
        return plan()
    if args.seal:
        print(seal(again=args.reseal))
        return 0
    if args.smoke:
        return smoke(args.live)
    if args.run and args.live:
        if run_live():
            return 2
    elif args.run:
        replay()
    return analyse_and_write()


def replay() -> None:
    """Free. With the run of record scored, its questions replayed and its file rewritten;
    before it, the replay goes to `replay-scored.jsonl`, so it never freezes the live run."""
    done = read_rows("a7")
    qs = questions() if done is None else questions()[: len(done)]
    rows = asyncio.run(run(qs, live=False, name="a7", batch=BATCH, cap_usd=BATCH_CAP_USD))
    if done is not None:
        rows = with_live_errors(rows, done)
    write_rows("replay" if done is None else "a7", rows)


def with_live_errors(rows: list[dict[str, Any]], done: list[dict[str, Any]]) -> list[dict]:
    """A failed call is not recorded, so its class is only in the live run's rows: a replay
    takes `errors` from the run of record, question by question."""
    errors = {r["id"]: r["errors"] for r in done if "errors" in r}
    return [  # the live run's key order: `errors` before `rank`
        {k: v for k, v in r.items() if k not in ("errors", "rank")}
        | ({"errors": errors[r["id"]]} if r["id"] in errors else {})
        | {"rank": r["rank"]}
        for r in rows
    ]


if __name__ == "__main__":
    raise SystemExit(main())
