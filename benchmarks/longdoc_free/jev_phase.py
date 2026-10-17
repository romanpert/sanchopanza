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

Phase "probe" (docs/results/2026-10-17-lfree-bm25-dry/prereg-probe.md, the owner's approval of
2026-10-17): Jev only on the dev questions PROBE_IDS, with the free BM25 prefilter at PROBE_K
(`pages.bm25_shortlist`), both fixed here. Its own lot (`longdoc-free-bm25-probe`: prereg,
recording, ledger capped at 0.06 USD, 0.0626 with its worst overshoot and the preflight, under
the owner's hard 0.10) and one launch only: none
after any launch, any spend in its ledger or any answer in its recording.

Phase "dev2" (docs/results/2026-10-17-lfree-dev2/prereg-dev2.md, the owner's approval of
2026-10-17 after the probe): the 41 dev questions with the same prefilter at PROBE_K, fixed here,
its own lot (`longdoc-free-dev2`: prereg, recording, ledger capped at DEV2 cap below, passages in
PRIVATE/dev2/) and the probe's refusals: one launch only, none after any launch, any spend in its
ledger or any answer in its recording. The probe and dev2 are the only phases with a prefilter
on a paid path.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
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
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402


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
# The probe: the owner's hard 0.10 USD bounds the ledger's cap, plus the most the calls in flight
# when it bites can bill past their reservations (each less than its whole bill, at most the
# dev's dearest call: a gate over the 60,000 kept characters, the largest input the probe
# sends), plus the preflight, which is outside the ledger. The cap itself is 0.06: past the
# rule's 3 x 0.015 a stop at the cap already decides "no", so nothing more is worth paying for.
PROBE_HARD_CAP_USD = 0.10
PROBE_MAX_BILL_USD = 0.000645  # the dev's dearest billed call: 0.000644616
PROBE_IN_FLIGHT = br.CONCURRENCY  # 4
PROBE_PREFLIGHT_USD = 13e-6  # `jev-preflight`: one short decision, not in the ledger
# probe: 0.06 + 4 x 0.000645 + 0.000013 = 0.0626
# dev2 (prereg-dev2.md section 3): 1.00, set from the probe's real cost, not the stub: 41 times
# its dearest question (0.0203) is 0.83, its mean (0.0115) 0.47. Its worst total, with the same
# in-flight bound and the preflight: 1.00 + 4 x 0.000645 + 0.000013 = 1.0026.
CAP_USD = {"dev": 1.80, "confirm": 12.50, "probe": 0.06, "dev2": 1.00}
JEV_LOT_USD = 14.30  # the owner's Jev for the whole longdoc-free lot (dev, probe, dev2, confirm)
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
PROBE = "probe"
DEV2 = "dev2"
PHASES = ("dev", "confirm", PROBE, DEV2)
PROBE_DIR = ROOT / "docs" / "results" / "2026-10-17-lfree-bm25-dry"
DEV2_DIR = ROOT / "docs" / "results" / "2026-10-17-lfree-dev2"
PROBE_IDS = (0, 7, 375)  # the dearest, cheapest and median by the dry oracle at K = 200
PROBE_K = 200
# The probe's plan before the launch (docs/results/2026-10-17-lfree-bm25-dry/bm25-dry.json): the
# stub undercounts real Jev's tournament calls, 1.417 times pooled on the dev, and the oracle
# expects 0.0199 + 0.0056 + 0.0111 USD for these ids at this K; the larger of the stub's estimate
# so corrected and the oracle's must fit in the ledger's room.
PROBE_STUB_RATIO = 1.417
PROBE_ORACLE_USD = 0.0366
# dev2's plan, by the same rule: the oracle's 41 questions at K = 200 (bm25-dry.json).
DEV2_ORACLE_USD = 0.4439
ORACLE_USD = {PROBE: PROBE_ORACLE_USD, DEV2: DEV2_ORACLE_USD}
# Phases whose K is fixed here and that launch once only, never again (the probe's refusals).
FIXED_K = {PROBE: PROBE_K, DEV2: PROBE_K}
ONE_LAUNCH = (PROBE, DEV2)
# dev2 reuses the sealed dev's N, H0 and HC sessions (prereg-dev2.md section 4): bound to its
# instrument, so a change to them after its instrument commit refuses every dev2 run.
DEV_ROWS = ("docs/results/2026-10-16-longdoc-free/dev-sonnet-rows.jsonl",
            "docs/results/2026-10-16-longdoc-free/dev-haiku-rows.jsonl")  # fmt: skip


def prefilter_for(phase: str) -> int | None:
    """The BM25 prefilter a phase runs with: the probe's and dev2's K, none for the others."""
    return FIXED_K.get(phase)


def results_dir(phase: str) -> pathlib.Path:
    return {PROBE: PROBE_DIR, DEV2: DEV2_DIR}.get(phase, RESULTS)


def lot(phase: str) -> paid_once.Lot:
    name = {"dev": f"{NAME}-dev", "confirm": NAME, PROBE: f"{NAME}-bm25-probe",
            DEV2: f"{NAME}-dev2"}[phase]  # fmt: skip
    prereg = {"dev": RESULTS / "prereg-dev-a1.md", "confirm": RESULTS / "prereg.md",
              PROBE: PROBE_DIR / "prereg-probe.md",
              DEV2: DEV2_DIR / "prereg-dev2.md"}[phase]  # fmt: skip
    return paid_once.Lot(
        name=name,
        prereg=prereg,
        launcher=ROOT / "longdoc-free-jev-run.cmd",
        fixture=ROOT / "fixtures" / NAME / f"jev-{phase}.jsonl",
        model=MODEL,
        cap_usd=CAP_USD[phase],
        instrument=INSTRUMENT + (DEV_ROWS if phase == DEV2 else ()),
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
    stopped at the cap, may be followed by one launch. The probe and dev2: one launch, never
    another."""
    if phase in ONE_LAUNCH:
        return not past
    if paid_once.may_launch(past):
        return True
    return (phase == "dev" and len(past) == 1 and past[0].get("stop_kind") == "cap"
            and past[0].get("head") == ORIGINAL_DEV_SEAL)  # fmt: skip


def recording_path(the_lot: paid_once.Lot) -> pathlib.Path:
    """The lot's recording: the plain file, else its committed `.gz`, else the plain path."""
    gz = the_lot.fixture.with_name(the_lot.fixture.name + ".gz")
    return gz if not the_lot.fixture.exists() and gz.exists() else the_lot.fixture


def recorded(the_lot: paid_once.Lot) -> Any:
    """`paid_once.recorded` over the plain file, unchanged; over the `.gz` the same lines."""
    path = recording_path(the_lot)
    if path == the_lot.fixture:
        return paid_once.recorded(the_lot)
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        lines = [json.loads(x) for x in handle if x.strip()]
    return RecordedDecider([e for e in lines if the_lot.serves(str(e.get("model") or ""))])


def lot_asker(phase: str, fallback: Any | None) -> br.Asker:
    return br.Asker(fallback, recorded=recorded(lot(phase)), memo_failures=True, model_halts=True)


# ---- the questions ---------------------------------------------------------------------------


def phase_ids(phase: str) -> set[int]:
    """The frozen ids of a phase; the probe's, which must be dev questions; dev2's, the dev's."""
    if phase == DEV2:
        return set(pool.phase_ids(pool.read_frozen(), "dev"))
    if phase != PROBE:
        return set(pool.phase_ids(pool.read_frozen(), phase))
    dev = set(pool.phase_ids(pool.read_frozen(), "dev"))
    if not set(PROBE_IDS) <= dev:
        raise SystemExit(f"the probe's ids {PROBE_IDS} are not all dev questions")
    return set(PROBE_IDS)


def load_rows(phase: str) -> list[dict[str, Any]]:
    """The phase's questions in id order, each with its novel's pages (built once a novel)."""
    pool.require_pinned()
    ids = phase_ids(phase)
    items, texts = pool.items(pool.rows())
    built: dict[str, list[tuple[str, str]]] = {}
    out = []
    for item in sorted((i for i in items if i.id in ids), key=lambda i: i.id):
        if item.novel not in built:
            built[item.novel] = pages.pages_of(texts[item.novel])
        out.append({"id": item.id, "novel": item.novel, "question": item.question,
                    "answers": list(item.answers), "pages": built[item.novel]})  # fmt: skip
    return out


async def ask(
    rows: list[dict[str, Any]], asker: br.Asker, prefilter_k: int | None = None
) -> list[dict[str, Any]]:
    """Per question: the passages, then the gate over them. `prefilter_k` (opt-in, None in every
    sealed run, which it leaves unchanged): only the K pages BM25 scores best for the question
    (`pages.bm25_shortlist`) enter the tournament; the rest are not kept."""
    if prefilter_k is not None and prefilter_k < 1:
        raise ValueError("prefilter_k must be >= 1 (or None for no prefilter)")
    squire = br.squire(asker, "select", SQUIRE_CAP_USD)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        br.ROW.set(str(row["id"]))
        novel = row["pages"]
        shortlist = None
        if prefilter_k is not None:
            shortlist = pages.bm25_shortlist(novel, row["question"], prefilter_k)
        seen = novel if shortlist is None else [novel[i] for i in shortlist]
        entries = await squire.select_passages(purpose=row["question"], pages=seen,
                                               fit_chars=FIT_CHARS, fit_score=False)  # fmt: skip
        if shortlist is not None:
            entries = pages.spread(entries, shortlist, len(novel))
        kept = pages.kept_text(novel, entries)
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


def dry(
    phase: str, rows: list[dict[str, Any]] | None = None, prefilter_k: int | None = None
) -> dict[str, Any]:
    """The phase's calls and pessimistic cost with the stub, free. `prefilter_k` measures a K
    on a sealed phase's questions; the probe and dev2 run with their own K, and no other. Their
    plan is the larger of the stub's estimate times PROBE_STUB_RATIO and the oracle's."""
    if phase in FIXED_K and prefilter_k not in (None, FIXED_K[phase]):
        raise ValueError(f"{phase}'s K is fixed at {FIXED_K[phase]}")
    prefilter_k = prefilter_for(phase) if prefilter_k is None else prefilter_k
    rows = load_rows(phase) if rows is None else rows
    asker = lot_asker(phase, br.Stub())
    asyncio.run(ask(rows, asker, prefilter_k))
    calls = {arm: {k: round(v, 4) for k, v in c.items()} for arm, c in asker.calls.items()}
    pessimistic = sum(c["pessimistic_usd"] for c in asker.calls.values())
    out = {"phase": phase, "questions": len(rows), "calls": calls,
           "pessimistic_usd": round(pessimistic, 4), "cap_usd": CAP_USD[phase],
           "fits_under_cap": pessimistic <= CAP_USD[phase], "claude_usd": 0.0}  # fmt: skip
    if phase in ORACLE_USD:
        planned = max(pessimistic * PROBE_STUB_RATIO, ORACLE_USD[phase])
        out = {**out, "planned_usd": round(planned, 4), "fits_under_cap": planned <= CAP_USD[phase]}
    return out if prefilter_k is None else {**out, "prefilter_k": prefilter_k}


def passages_path(phase: str, item_id: int) -> pathlib.Path:
    return PRIVATE / phase / "passages" / f"{item_id}.txt"


def replay(phase: str) -> list[dict[str, Any]]:
    """The recording read back (no call): public rows; the kept text into PRIVATE."""
    rows = load_rows(phase)
    asker = lot_asker(phase, None)
    got = asyncio.run(ask(rows, asker, prefilter_for(phase)))
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
    target = results_dir(phase) / f"jev-{phase}.jsonl"
    target.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    return out


# ---- paying (C5b's `free_confirm.paid`, per phase) -------------------------------------------


def make_live(the_lot: paid_once.Lot, inner: Any | None = None) -> tuple[Any, Any]:
    """The live decider: `inner` (the real Jev client when None) behind the lot's capped ledger,
    every answer recorded. Tests rehearse the paid path with a costed stub as `inner`."""
    from sanchopanza.providers import CappedDecider
    from sanchopanza.providers.recorded import RecordingDecider

    if inner is None:  # pragma: no cover - the real client
        from sanchopanza.providers import jev
        from sanchopanza.providers.jev import JevDecider

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
        await ask(rows, asker, prefilter_for(phase))
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
    needed = plan.get("planned_usd", plan["pessimistic_usd"])  # the probe's/dev2's, else the stub's
    if needed > room:
        raise SystemExit(f"{needed} USD does not fit in the {room:.4f} left")
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
                             "exception spent or not met; the probe and dev2: one "
                             "launch)")  # fmt: skip
        if phase in ONE_LAUNCH and paid_once.spent(the_lot) > 0:
            raise SystemExit(f"{the_lot.name}'s ledger has already spent: one launch only, "
                             "nothing spent")  # fmt: skip
        held = recording_path(the_lot)
        if not past and held.exists() and held.stat().st_size:
            raise SystemExit(f"first launch, but {held.name} holds answers: nothing spent")
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
    ap.add_argument("--prefilter-k", type=int,
                    help="dry, dev or confirm only: BM25's K best pages enter Jev")  # fmt: skip
    args = ap.parse_args(argv)
    if args.prefilter_k is not None and args.action != "dry":
        ap.error("--prefilter-k is for the dry run only: a paid path takes its phase's K")
    if args.prefilter_k is not None and args.phase in FIXED_K:
        ap.error(f"{args.phase}'s K is fixed at {FIXED_K[args.phase]} in code")
    if args.action == "dry":
        print(json.dumps(dry(args.phase, prefilter_k=args.prefilter_k), indent=1))
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
