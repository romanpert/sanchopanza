"""Lot longdoc-free's phase J: Jev's passages and gate per question, recorded once, replayed free.

    python -I benchmarks/longdoc_free/jev_phase.py dry --phase dev       # free: calls and cost
    python -I benchmarks/longdoc_free/jev_phase.py seal --phase dev      # once, before any call
    python -I benchmarks/longdoc_free/jev_phase.py paid --phase dev --launcher <the .cmd>  # PAID
    python -I benchmarks/longdoc_free/jev_phase.py rows --phase dev      # free once recorded

Per question (docs/results/2026-10-16-longdoc-free/design.md, design (b)): the shipped
`Squire.select_passages` over the novel's pages (`pages.pages_of`) with `fit_chars=FIT_CHARS`
in the free order (`fit_score=False`, the 0.3.2 default), no `max_calls` (as every published
run), then one Truth over the question and the kept text (`GATE`), both through one asker:
B6's (`b6_run.Asker`: recording first, one live call on a miss, never retried, at most 4 in
flight, a memo so a repeated call is asked once, stopped by a cap refusal, an outage, another
model or three failures in a row) over this phase's recording. Jev is `b6_run.MODEL`,
jev-1.13.0, the model the 0.3.2 default ships and C5b measured `select_passages` on.

Each phase (dev, confirm) is its own `paid_once.Lot`: its prereg, recording, ledger and cap
(1.50 and 12.50 USD; the owner's 14.00 for the lot, raised from 11.50 on 2026-10-17 when
the confirmation's dry run came to 12.32 USD pessimistic). `rows` replays the recording (no
call) and writes each question's kept text to PRIVATE/<phase>/passages/<id>.txt, the file arm H
reads, and the public row: id, novel, the gate's p (None when it gave no usable answer), kept
characters. A paid run starts only from the seal commit itself (`sealed_head_problems`).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "benchmarks" / "b6_es"))
import b6_run as br  # noqa: E402
import paid_once  # noqa: E402

from sanchopanza import _lockfile  # noqa: E402
from sanchopanza.contract import Truth  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HERE = pathlib.Path(__file__).resolve().parent
pool = _load("lf_pool", HERE / "pool.py")
pages = _load("lf_pages", HERE / "pages.py")

NAME = "longdoc-free"
RESULTS = pool.LOT_DIR
HOME = pathlib.Path.home() / ".cache" / "sanchopanza"
PRIVATE = pool.CACHE / "private"
MODEL = br.MODEL  # jev-1.13.0
FIT_CHARS = 60_000  # about 20,000 tokens: under Jev's 32k a question, H's file
# Dev 1.50 at the seal; 1.80 by amendment 1 (the owner, 2026-10-17, after the first launch met
# the cap: real Jev made about 39 % more tournament calls than the dry run's stub). The lot's Jev:
# 14.30.
CAP_USD = {"dev": 1.80, "confirm": 12.50}
# Amendment 1: one more launch of the dev, only after its first launch, from the original seal,
# stopped at the cap.
ORIGINAL_DEV_SEAL = "6fd974705d223d7e3a0eeeb13a933da3459ea54e"
SQUIRE_CAP_USD = 1e9  # the squire's own meter is no cap (C5's lesson): the ledger's is
POINT = "longdoc_free_gate"
GATE = Truth(
    "`passages` are excerpts of one novel. They state everything needed to answer `question`."
)
IDS_REL = "docs/results/2026-10-16-longdoc-free/ids.json"
INSTRUMENT = ("src", "benchmarks/longdoc_free", "benchmarks/b6_es", "benchmarks/paid_once.py",
              IDS_REL)  # fmt: skip
PHASES = ("dev", "confirm")


def lot(phase: str) -> paid_once.Lot:
    suffix = "" if phase == "confirm" else f"-{phase}"
    prereg = RESULTS / ("prereg-dev-a1.md" if phase == "dev" else f"prereg{suffix}.md")
    return paid_once.Lot(
        name=f"{NAME}{suffix}",
        prereg=prereg,
        launcher=ROOT / "longdoc-free-jev-run.cmd",
        fixture=ROOT / "fixtures" / NAME / f"jev-{phase}.jsonl",
        model=MODEL,
        cap_usd=CAP_USD[phase],
        instrument=INSTRUMENT,
        inputs=((pool.RAW, pool.SHA256),),
        home=HOME,
    )


def sealed_head_problems(the_lot: paid_once.Lot, git: Any = paid_once.git) -> list[str]:
    """A paid run starts from the seal commit itself: HEAD detached, the checkout clean, the
    seal file tracked and HEAD the last commit that touched it (review of 2026-10-17). The
    launcher filled in place is the one change allowed: `paid` checks its digest with the local
    values masked."""
    seal = the_lot.prereg.with_suffix(".sha256").relative_to(ROOT).as_posix()
    launcher = the_lot.launcher.relative_to(ROOT).as_posix()
    found = []
    if git("symbolic-ref", "-q", "HEAD").returncode == 0:
        found.append("HEAD is on a branch: run from a worktree detached at the seal commit")
    status = git("status", "--porcelain", "--untracked-files=no")
    changed = [line for line in status.stdout.splitlines()
               if line.strip() and line[3:].strip().strip('"') != launcher]  # fmt: skip
    if status.returncode != 0 or changed:
        found.append("the checkout has changes")
    if git("ls-files", "--error-unmatch", seal).returncode != 0:
        found.append(f"{seal} is not committed")
    else:
        head = git("rev-parse", "HEAD").stdout.strip()
        last = git("log", "-1", "--format=%H", "--", seal).stdout.strip()
        if not head or head != last:
            found.append(f"HEAD is not the commit that sealed {seal}")
    return found


def may_launch(phase: str, past: list[dict[str, Any]]) -> bool:
    """paid_once's rule (one launch and one relaunch, none after a 402, a 429, the cap or another
    model), and amendment 1's one exception: the dev's single launch from the original seal,
    stopped at the cap, may be followed by one launch."""
    if paid_once.may_launch(past):
        return True
    return (phase == "dev" and len(past) == 1 and past[0].get("stop_kind") == "cap"
            and past[0].get("head") == ORIGINAL_DEV_SEAL)  # fmt: skip


def lot_asker(phase: str, fallback: Any | None) -> br.Asker:
    return br.Asker(
        fallback, recorded=paid_once.recorded(lot(phase)), memo_failures=True, model_halts=True
    )


# ---- the questions ---------------------------------------------------------------------------


def load_rows(phase: str) -> list[dict[str, Any]]:
    """The phase's questions in id order, each with its novel's pages (built once a novel)."""
    pool.require_pinned()
    ids = set(pool.phase_ids(pool.read_frozen(), phase))
    items, texts = pool.items(pool.rows())
    built: dict[str, list[tuple[str, str]]] = {}
    out = []
    for item in sorted((i for i in items if i.id in ids), key=lambda i: i.id):
        if item.novel not in built:
            built[item.novel] = pages.pages_of(texts[item.novel])
        out.append({"id": item.id, "novel": item.novel, "question": item.question,
                    "answers": list(item.answers), "pages": built[item.novel]})  # fmt: skip
    return out


async def ask(rows: list[dict[str, Any]], asker: br.Asker) -> list[dict[str, Any]]:
    """Per question: the passages, then the gate over them."""
    squire = br.squire(asker, "select", SQUIRE_CAP_USD)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        br.ROW.set(str(row["id"]))
        entries = await squire.select_passages(purpose=row["question"], pages=row["pages"],
                                               fit_chars=FIT_CHARS, fit_score=False)  # fmt: skip
        kept = pages.kept_text(row["pages"], entries)
        state = {"question": row["question"], "passages": kept}
        decision = await asker.decide("gate", POINT, state, {"enough": GATE})
        p = None if decision.failed else decision.answer("enough").truth
        return {"id": row["id"], "novel": row["novel"], "p": p, "kept": kept}

    return list(await asyncio.gather(*(one(row) for row in rows)))


def gold_in(kept: str, answers: list[str]) -> bool:
    """A normalised reference appears in the normalised kept text (∞Bench's normaliser)."""
    score = _load("lf_infbench_score", HERE / "infbench_score.py")
    text = f" {score.normalize_answer(kept)} "
    return any(f" {score.normalize_answer(a)} " in text for a in answers
               if score.normalize_answer(a))  # fmt: skip


# ---- free: the dry run and the replay ----------------------------------------------------------


def dry(phase: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = load_rows(phase) if rows is None else rows
    asker = lot_asker(phase, br.Stub())
    asyncio.run(ask(rows, asker))
    calls = {arm: {k: round(v, 4) for k, v in c.items()} for arm, c in asker.calls.items()}
    pessimistic = sum(c["pessimistic_usd"] for c in asker.calls.values())
    return {"phase": phase, "questions": len(rows), "calls": calls,
            "pessimistic_usd": round(pessimistic, 4), "cap_usd": CAP_USD[phase],
            "fits_under_cap": pessimistic <= CAP_USD[phase], "claude_usd": 0.0}  # fmt: skip


def passages_path(phase: str, item_id: int) -> pathlib.Path:
    return PRIVATE / phase / "passages" / f"{item_id}.txt"


def replay(phase: str) -> list[dict[str, Any]]:
    """The recording read back (no call): public rows; the kept text into PRIVATE."""
    rows = load_rows(phase)
    asker = lot_asker(phase, None)
    got = asyncio.run(ask(rows, asker))
    if asker.failed_keys:
        raise SystemExit(f"{len(asker.failed_keys)} calls not recorded: the phase is not complete")
    by_id = {r["id"]: r for r in rows}
    out = []
    for g in got:
        path = passages_path(phase, g["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(g["kept"].encode("utf-8"))
        out.append({"id": g["id"], "novel": g["novel"], "p": g["p"], "kept_chars": len(g["kept"]),
                    "empty": g["kept"] == pages.EMPTY,
                    "gold_in_kept": gold_in(g["kept"], by_id[g["id"]]["answers"])})  # fmt: skip
    target = RESULTS / f"jev-{phase}.jsonl"
    target.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    return out


# ---- paying (C5b's `free_confirm.paid`, per phase) -------------------------------------------


def make_live(the_lot: paid_once.Lot) -> tuple[Any, Any]:  # pragma: no cover - real client
    from sanchopanza.providers import CappedDecider, jev
    from sanchopanza.providers.jev import JevDecider
    from sanchopanza.providers.recorded import RecordingDecider

    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})
    inner = JevDecider(model=MODEL, long_context=False, images=False, timeout_s=br.TIMEOUT_S)
    capped = CappedDecider(inner, ledger=paid_once.ledger_of(the_lot), batch=the_lot.name,
                           max_usd=the_lot.cap_usd)  # fmt: skip
    the_lot.fixture.parent.mkdir(parents=True, exist_ok=True)
    return inner, RecordingDecider(capped, the_lot.fixture)


def stopped_by(asker: br.Asker) -> str | None:
    if asker.halted:
        kind, why = asker.halted[0]
        if kind == "model":
            return f"model moved: {why}"
        return f"SpendCapReached: {why}" if kind == "cap" else why
    return f"{asker.failures} calls unanswered" if asker.failures else None


async def session(phase: str, rows: list[dict[str, Any]], the_lot: paid_once.Lot, check: Any,
                  build_live: Any, on_start: Any) -> dict[str, Any]:  # fmt: skip
    await check(MODEL)
    on_start()
    inner, live = build_live(the_lot)
    asker = lot_asker(phase, live)
    try:
        await ask(rows, asker)
    finally:
        close = getattr(inner, "aclose", None)
        if close is not None:
            await close()
    why = stopped_by(asker)
    return {"calls": {a: round(c["calls"]) for a, c in asker.calls.items()},
            "stopped": why, "stop_kind": paid_once.stop_kind(why)}  # fmt: skip


def paid(phase: str, launcher: pathlib.Path | None, *, load_key: Any = paid_once.load_key,
         check: Any = paid_once.preflight, build_live: Any = make_live,
         sealed_head: Any = sealed_head_problems) -> int:  # fmt: skip
    the_lot = lot(phase)
    if (
        launcher is None
        or not launcher.is_file()
        or paid_once.launcher_digest(launcher) != paid_once.launcher_digest(the_lot.launcher)
    ):
        raise SystemExit(
            f"a paid run starts from {the_lot.launcher.name} (--launcher): nothing spent"
        )
    rows = load_rows(phase)
    plan = dry(phase, rows)
    room = paid_once.room(the_lot)
    if plan["pessimistic_usd"] > room:
        raise SystemExit(f"{plan['pessimistic_usd']} USD does not fit in the {room:.4f} left")
    paid_once.require_sealed(the_lot)
    commit = paid_once.require_instrument(the_lot)
    paid_once.require_inputs(the_lot)
    if found := sealed_head(the_lot):
        raise SystemExit("; ".join(found) + ": nothing spent")
    the_lot.run_dir.mkdir(parents=True, exist_ok=True)
    with _lockfile.locked(the_lot.run_dir / "paid", wait_s=1.0,
                          stale_s=paid_once.LOCK_STALE_S, strict=True):  # fmt: skip
        past = paid_once.history(the_lot)
        if not may_launch(phase, past):
            raise SystemExit("launch rule: no launch left (one relaunch at most, none after "
                             "a 402, a 429, the cap or another model; amendment 1's one "
                             "exception spent or not met)")  # fmt: skip
        if not past and the_lot.fixture.exists() and the_lot.fixture.stat().st_size:
            raise SystemExit(
                f"first launch, but {the_lot.fixture.name} holds answers: nothing spent"
            )
        load_key()
        start = {"event": "start", "phase": phase, "head": paid_once.head(), "instrument": commit,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "plan": plan}  # fmt: skip
        result = asyncio.run(session(phase, rows, the_lot, check, build_live,
                                     lambda: paid_once._note(the_lot, start)))  # fmt: skip
        paid_once._note(the_lot, {"event": "end", **result})
    print(json.dumps(result, indent=1))
    return 0 if result["stopped"] is None else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("action", choices=("dry", "seal", "paid", "rows"))
    ap.add_argument("--phase", choices=PHASES, required=True)
    ap.add_argument("--launcher", type=pathlib.Path)
    args = ap.parse_args(argv)
    if args.action == "dry":
        print(json.dumps(dry(args.phase), indent=1))
        return 0
    if args.action == "seal":
        print(paid_once.seal(lot(args.phase)))
        return 0
    if args.action == "paid":
        return paid(args.phase, args.launcher)
    out = replay(args.phase)
    covered = sum(r["p"] is not None and r["p"] >= 0.5 for r in out)
    print(json.dumps({"rows": len(out), "gate_p_at_least_0.5": covered}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
