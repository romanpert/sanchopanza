"""Lot lbo8: the longdoc router at the 0.8 cut against Opus 5.5 on the LongBench v2 tasks no lot
has used. Registered in docs/results/2026-10-16-lbo8/prereg.md; this module is its plan (free),
phase J's live entry (Jev on the 78 through lb162's runner, this lot's own ledger), the seal and
the analysis (lbo8_stats.py). The paid driver (smoke, phase J, phase O in one process) is
benchmarks/h2h/h2h_lbo8.py.

Lot lb162x found, post hoc, that raising lb162's cut from 0.6 to 0.8 brought the hybrid (Jev 1.14
with the long window where its top choice is >= the cut, Opus 5.5 elsewhere) from -3.7 to -0.6
points of Opus alone, for a smaller saving. This lot would confirm the 0.8 cut on fresh tasks.

The measured population is spent: lb162's 162 tasks and the 60 of 2026-10-06 are every LongBench
v2 task in the Single- and Multi-Document QA domains over 100,000 characters. What is left in
those two domains is 78 tasks of 48,765 to 99,827 characters (`fresh_qa`), all of the set's
"short" band; the other 203 fresh tasks are other domains (code, dialogue, tables, in-context
learning).

    python benchmarks/jev114/lbo8.py --pool         # free: the fresh pool (needs the cache)
    python benchmarks/jev114/lbo8.py --freeze-ids   # free: ids.txt once, metadata only
    python benchmarks/jev114/lbo8.py --prepare      # free: their documents into the cache
    python benchmarks/jev114/lbo8.py --dry          # free: the plan, power, money, replay dry run
    python benchmarks/jev114/lbo8.py --seal         # seal prereg.md + code + inputs
    python benchmarks/jev114/lbo8.py --analyse      # free: the analysis, summary.json

Phase J's live entry (`run_phase_j`, called by the driver only) asks Jev what its recordings
(ANSWERS) lack, through lb162's `run_j` and `Halting`, with this lot's own SpendLedger
(`jev_ledger(run_dir)`, RUN_DIR/jev-ledger.jsonl, batch `lbo8`, cap JEV_CAP_USD on the ledger
and the batch); never lb162's or another lot's ledger. Its stop maps to the driver's kinds
(`jev_kind`): none `done`, the cap `ceiling` (final: scored as it is), STOP `manual`, an HTTP
402 / 429 / outage / three failed tasks in a row `jev` (a pause, exit 4; a Jev 429 is not
the subscription's weekly limit and writes no LIMIT.flag).

The statistics differ from lb162x's on purpose: at 0.8 the covered tasks are few and Jev and Opus
rarely disagree on them (1 disagreement in 27 on lb162x), where a percentile bootstrap or a Wald
interval collapses to a point. Tango's score interval for a paired difference keeps a width even
with no disagreement at all: z^2 / (n + z^2), 4.7 points at 78 tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import math
import pathlib
import random
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in ("src", "benchmarks", "benchmarks/h2h"):
    sys.path.insert(0, str(REPO / extra))
sys.path.insert(0, str(HERE))

import lb162  # noqa: E402  (phase J's question, cut, retries and replay; reading helpers)
import lb162x  # noqa: E402  (the per-session money rule: Phase, cap_for, simulate)
import longdoc_data  # noqa: E402
import meter  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-16-lbo8"
IDS_FILE = OUT / "ids.txt"
N_TASKS = 78
CACHE = longdoc_data.CACHE / "lbo8"
TASKS = CACHE / "tasks.jsonl"
DOCS = CACHE / "docs"
DEV_IDS = REPO / "benchmarks" / "h2h" / "longdoc-dev-ids.txt"
LB162X = REPO / "docs" / "results" / "2026-10-16-lb162x"
CUT = 0.8
MARGIN = -0.05  # hybrid minus Opus over the 78, compared unrounded (the owner's -5, 2026-10-16)
MIN_COVERED_SESSIONS = 8  # covered tasks with an Opus session: fewer is "no medido"
Z = 1.959964
ANSWERS = OUT / f"jev-answers-{lb162.CELL}.jsonl"
JEV_ROWS = OUT / "jev-scored.jsonl"
JEV_STOP = OUT / "jev-stop.json"
SUMMARY = OUT / "summary.json"
# The run's own folder (STOP, LIMIT.flag, phase J's ledger, the driver's log); the driver's
# --run-dir overrides it. Never C:/sp-runs/w17-jev (another lot's ledger) nor lb162's.
RUN_DIR = pathlib.Path("C:/sp-runs/lbo8")
JEV_LEDGER_NAME = "jev-ledger.jsonl"
BATCH = "lbo8"
ORDER_SEED = 20261016  # phase O's order: random.Random(ORDER_SEED).shuffle of the sorted 78
BOOT_SEED = 20261016  # the saving's paired bootstrap
BOOT_DRAWS = 10_000
J_WALL_S = 900  # phase J's clock allowance (78 tasks, four in flight, ~2 s a call)

# Money. Opus 5.5 in clean Claude Code cost 0.099 USD a task on lb162's short band (38 sessions,
# max 0.19) and its cost barely grows with the document (0.111 + 0.0017 per M characters over
# the 162): the plan uses 0.10. Jev: 0.012 USD per M characters shown on lb162's short band.
OPUS_EST_USD = 0.10
JEV_USD_PER_MCHAR = 0.012
JEV_WORST_USD_PER_MCHAR = lb162.JEV_WORST_USD_PER_MCHAR
JEV_CAP_USD = 0.20  # phase J's ledger and batch cap
# Phase O's ceiling leaves room for the smoke's worst turn: --max-budget-usd cuts only between
# turns, so the smoke can spend its 0.80 plus one worst turn (8.64), and 0.80 + 8.64 + 0.20 (J)
# + 21.36 is the 31.00 the owner approved, as a worst case and not only as caps.
PHASE_O = lb162x.Phase("O", "lbo8-opus", "OPUS", meter.OPUS_55, IDS_FILE, N_TASKS,
                       ceiling=21.36, full_cap=lb162x.stats.OPUS_FULL_CAP_USD, floor=1.00,
                       wall_mean_s=25.0, cost_scale=1.0, rows=OUT / "opus-rows.jsonl",
                       stop=OUT / "opus-stop.json")  # fmt: skip
# The smoke: lb162x's (ONE Opus session on lb162's smoke task, a LongBench dev task outside the
# 78, cap and ceiling 0.80 USD) in this lot's own session folder and results.
SMOKE = dataclasses.replace(lb162x.SMOKE, name="lbo8-smoke", rows=OUT / "smoke-rows.jsonl",
                            stop=OUT / "smoke-stop.json")  # fmt: skip


@dataclasses.dataclass(frozen=True)
class JevPhase:
    """Phase J as the driver sees it: a key, its rows and its stop file; its money is the ledger."""

    key: str = "J"
    name: str = "lbo8-jev"
    n: int = N_TASKS
    ceiling: float = JEV_CAP_USD
    rows: pathlib.Path = JEV_ROWS
    stop: pathlib.Path = JEV_STOP


PHASE_J = JevPhase()
DRIVEN = (SMOKE, PHASE_J, PHASE_O)  # what the driver runs, in this order
LOT_CEILING_USD = round(SMOKE.ceiling + JEV_CAP_USD + PHASE_O.ceiling, 2)  # 22.36 in caps
LOT_WORST_USD = round(LOT_CEILING_USD + SMOKE.worst_turn, 2)  # 31.00: the smoke's turn past its cap

read_ids = lb162.read_ids


# ---- the fresh pool ----------


def fresh_qa(rows: Sequence[Mapping[str, Any]], used: set[str]) -> list[str]:
    """Single- and Multi-Document QA tasks outside `used`, at any length, sorted."""
    return sorted(str(r["_id"]) for r in rows
                  if r["domain"] in longdoc_data.DOMAINS and str(r["_id"]) not in used)  # fmt: skip


def used_ids() -> set[str]:  # pragma: no cover - needs the 465 MB cache
    """Every LongBench v2 id an earlier lot drew: the 60 of 2026-10-06 (their 10 dev ids among
    them) and lb162's 162."""
    drawn = {t.task_id for t in longdoc_data.load()}
    return drawn | set(lb162.frozen_ids()) | set(read_ids(DEV_IDS))


def raw_rows() -> list[dict[str, Any]]:  # pragma: no cover - needs the 465 MB cache
    return json.loads(longdoc_data.RAW.read_text(encoding="utf-8"))


def pool() -> dict[str, Any]:  # pragma: no cover - needs the 465 MB cache
    rows, used = raw_rows(), used_ids()
    fresh = [r for r in rows if str(r["_id"]) not in used]
    qa = [r for r in fresh if r["domain"] in longdoc_data.DOMAINS]
    chars = sorted(len(r["context"]) for r in qa)
    return {"rows": len(rows), "used": len(used), "fresh": len(fresh),
            "fresh_by_domain": dict(Counter(r["domain"] for r in fresh).most_common()),
            "fresh_qa": len(qa), "fresh_qa_by_length": dict(Counter(r["length"] for r in qa)),
            "fresh_qa_by_difficulty": dict(Counter(r["difficulty"] for r in qa)),
            "fresh_qa_chars": [chars[0], chars[len(chars) // 2], chars[-1]],
            "measured_population_left": sum(len(r["context"]) > longdoc_data.MIN_CHARS
                                            for r in qa)}  # fmt: skip


def freeze_ids() -> str:  # pragma: no cover - needs the 465 MB cache
    """Write IDS_FILE once, by metadata only."""
    if IDS_FILE.exists():
        raise SystemExit(f"{IDS_FILE.name} exists: the id list is frozen")
    ids = fresh_qa(raw_rows(), used_ids())
    if len(ids) != N_TASKS:
        raise SystemExit(f"expected {N_TASKS} fresh QA tasks, found {len(ids)}")
    head = (f"# lot lbo8 (draft): the {len(ids)} LongBench v2 tasks in the Single- and "
            "Multi-Document QA domains outside the 60 drawn on 2026-10-06 and lb162's 162, at any "
            "length (all under 100,000 characters), metadata only, sorted.")  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    IDS_FILE.write_text(head + "\n" + "\n".join(ids) + "\n", encoding="utf-8", newline="\n")
    return lb162.digest(IDS_FILE)


def prepare() -> int:  # pragma: no cover - needs the 465 MB cache
    """The frozen tasks and their documents into CACHE (as lb162.prepare does)."""
    rows = {str(r["_id"]): r for r in raw_rows()}
    DOCS.mkdir(parents=True, exist_ok=True)
    tasks = [longdoc_data.to_task(rows[i], DOCS) for i in read_ids(IDS_FILE)]
    for task in tasks:
        path = pathlib.Path(task.doc_path)
        if not path.exists():
            path.write_text(rows[task.task_id]["context"], encoding="utf-8")
    TASKS.write_text("".join(json.dumps(asdict(t), ensure_ascii=False) + "\n" for t in tasks),
                     encoding="utf-8", newline="\n")  # fmt: skip
    return len(tasks)


def load_tasks() -> list[Any]:  # pragma: no cover - needs the prepared cache
    tasks = longdoc_data.load(TASKS)
    if [t.task_id for t in tasks] != read_ids(IDS_FILE):
        raise SystemExit(f"{TASKS} does not hold the frozen ids: run --prepare")
    return tasks


def opus_order(ids: Sequence[str] | None = None) -> list[str]:
    """Phase O's order: the 78 frozen ids, sorted, in random.Random(ORDER_SEED).shuffle order."""
    found = list(ids) if ids is not None else read_ids(IDS_FILE)
    if len(found) != N_TASKS or len(set(found)) != N_TASKS:
        raise SystemExit(f"{IDS_FILE.name} does not hold {N_TASKS} distinct ids")
    return lb162x.shuffled(found, ORDER_SEED)


# ---- phase J, live (called by the driver only) ----------


def jev_ledger(run_dir: pathlib.Path = RUN_DIR) -> pathlib.Path:
    return run_dir / JEV_LEDGER_NAME


def batch_spent(run_dir: pathlib.Path = RUN_DIR) -> float:
    from sanchopanza.budget import SpendLedger

    path = jev_ledger(run_dir)
    return SpendLedger(path, cap_usd=JEV_CAP_USD).spent(BATCH) if path.exists() else 0.0


def jev_plan_refusal(spent: float, todo: Sequence[Any], cap: float = JEV_CAP_USD) -> str:
    """Empty when the tasks a replay leaves unanswered fit under the cap after `spent`, at the
    dearest rate per character shown before retries (lb162's), three tries each at most."""
    shown = sum(min(t.chars, lb162.WINDOW) for t in todo)
    need = shown * JEV_WORST_USD_PER_MCHAR / 1e6
    if spent + need <= cap:
        return ""
    return (f"phase J does not fit: {spent:.4f} spent + {len(todo)} tasks at "
            f"{need:.4f} = {spent + need:.4f} > {cap:g} USD")  # fmt: skip


def jev_kind(stop: str | None) -> str:
    """lb162's phase J stop as the driver's kind: finished `done`, the cap `ceiling` (final),
    STOP `manual`, every other stop (402, 429, outage, failures) `jev`, a pause."""
    if stop is None:
        return "done"
    return {"cap": "ceiling", "manual": "manual"}.get(stop, "jev")


def phase_j_final(rows: Sequence[Mapping[str, Any]] | None,
                  stop: Mapping[str, Any] | None) -> str:  # fmt: skip
    """Empty when phase J is over: every one of the 78 asked, or stopped by its cap (final);
    otherwise why phase J is not over."""
    if not rows or len(rows) != N_TASKS:
        return f"phase J has not scored the {N_TASKS} tasks"
    if any(r["status"] == "stopped" for r in rows) and (stop or {}).get("kind") != "ceiling":
        return f"phase J paused ({(stop or {}).get('kind')}): relaunch it first"
    return ""


def unrecorded(tasks: Sequence[Any]) -> list[Any]:  # pragma: no cover - reads the documents
    """The tasks a free replay of ANSWERS leaves unanswered: what a live run would pay for."""
    rows = asyncio.run(lb162.run_j(tasks, None, ANSWERS, lb162.Stop(max_consecutive=None)))
    return [t for t, r in zip(tasks, rows, strict=True) if r["status"] != "answered"]


def live_decider(stop: Any, run_dir: pathlib.Path) -> Any:  # pragma: no cover - network
    """lb162's live decider, on THIS lot's ledger and batch: reserved before every call."""
    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers import CappedDecider
    from sanchopanza.providers.jev import JevDecider

    ledger = SpendLedger(jev_ledger(run_dir), cap_usd=JEV_CAP_USD)
    inner = JevDecider(model=lb162.MODEL, long_context=True, images=False,
                       timeout_s=lb162.TIMEOUT_S)  # fmt: skip
    return lb162.Halting(CappedDecider(inner, ledger=ledger, batch=BATCH, max_usd=JEV_CAP_USD),
                         stop)  # fmt: skip


def go_live() -> None:  # pragma: no cover - one real decision, about 13 micro-USD
    """The key (TYPESAFE_API_KEY, or the file SANCHOPANZA_KEYS_ENV names; never printed), the
    first 429 a stop, and `jev-preflight` for jev-1.14.0."""
    lb162.l4.load_key()
    lb162.no_retry_on_429()
    lb162.preflight_or_stop()


def run_phase_j(run_dir: pathlib.Path = RUN_DIR, tasks: Sequence[Any] | None = None,
                decider: Callable[[Any, pathlib.Path], Any] = live_decider,
                start: Callable[[], None] = go_live,
                todo_of: Callable[[Sequence[Any]], list[Any]] = unrecorded) -> str:  # fmt: skip
    """Phase J: the tasks not yet scored (all, or the ones a pause left `stopped`) through
    lb162's runner, recorded first, live on a miss; rows without text into JEV_ROWS. Returns
    the driver's kind. A refusal (no room under the cap) raises SystemExit."""
    before = lb162.read_jsonl(JEV_ROWS)
    if before is not None and not any(r["status"] == "stopped" for r in before):
        return "done"  # scored already: frozen
    every = list(tasks) if tasks is not None else load_tasks()
    todo = ([i for i, r in enumerate(before) if r["status"] == "stopped"] if before
            else list(range(len(every))))  # fmt: skip
    if why := jev_plan_refusal(batch_spent(run_dir), todo_of([every[i] for i in todo])):
        raise SystemExit(why)
    start()
    stop = lb162.Stop(run_dir / "STOP")
    got = asyncio.run(lb162.run_j([every[i] for i in todo], decider(stop, run_dir), ANSWERS,
                                  stop))  # fmt: skip
    rows = lb162.merged(before or [{} for _ in every], dict(zip(todo, got, strict=True)))
    lb162.write_jsonl(JEV_ROWS, rows)  # "stopped" rows after a pause: resumed, not frozen
    said = {"phase": "J", "stop": stop.kind, "spent": round(batch_spent(run_dir), 6),
            "answered": sum(r["status"] == "answered" for r in rows),
            "covered": sum(lb162.stats.is_covered(r, CUT) for r in rows)}  # fmt: skip
    print(json.dumps(said), file=sys.stderr)
    if stop.kind:
        print(f"phase J stopped ({stop.kind}): {stop.reason}", file=sys.stderr)
    return jev_kind(stop.kind)


# ---- descriptive: lb162's Jev answers and lb162x's Opus sessions ----------


def recorded() -> list[dict[str, Any]]:
    """One row a task of the 162: Jev's pick probability and grade, Opus's grade, both costs."""
    jev = lb162.read_jsonl(lb162.JEV_ROWS) or []
    opus = {r["id"]: r for r in lb162.read_jsonl(LB162X / "opus-rows.jsonl") or []}
    out = []
    for r in lb162x.stats.lbs.asked(jev):
        cell, o = r[lb162.CELL], opus[r["id"]]
        out.append({"id": r["id"], "length": r["length"], "p": cell["p"],
                    "jev_ok": lb162x.stats.lbs.jev_right(r), "opus_ok": bool(o["ok"]),
                    "opus_usd": float(o["usd"]), "jev_usd": float(cell["usd"])})  # fmt: skip
    return out


def cut_table(rows: Sequence[Mapping[str, Any]], cuts: Sequence[float]) -> list[dict[str, Any]]:
    """At each cut: coverage, grades on the covered, hybrid minus Opus, Opus's cost avoided and
    the net saving (Opus alone minus Jev on every task and Opus on the uncovered)."""
    n = len(rows)
    opus_total = sum(r["opus_usd"] for r in rows)
    jev_total = sum(r["jev_usd"] for r in rows)
    out = []
    for cut in cuts:
        cov = [r for r in rows if r["p"] is not None and r["p"] >= cut]
        jev_only = sum(r["jev_ok"] and not r["opus_ok"] for r in cov)
        opus_only = sum(r["opus_ok"] and not r["jev_ok"] for r in cov)
        avoided = sum(r["opus_usd"] for r in cov)
        net = avoided - jev_total
        out.append({"cut": cut, "covered": len(cov), "coverage": round(len(cov) / n, 3),
                    "jev_right": sum(r["jev_ok"] for r in cov),
                    "opus_right": sum(r["opus_ok"] for r in cov),
                    "jev_only": jev_only, "opus_only": opus_only,
                    "hybrid_minus_opus_pts": round((jev_only - opus_only) / n * 100, 2),
                    "tango_95": [round(x * 100, 2) for x in tango_ci(jev_only, opus_only, n)[1:]],
                    "opus_avoided_usd": round(avoided, 3),
                    "net_saving_usd": round(net, 3),
                    "net_saving_share": round(net / opus_total, 3)})  # fmt: skip
    return out


# ---- Tango's score interval for a paired difference of proportions ----------


def tango_p21(b: int, c: int, n: int, delta: float) -> float:
    """The maximum-likelihood p21 under p12 - p21 = delta (Tango 1998), b = n12, c = n21."""
    w = -b - c + (2 * n - b + c) * delta
    return (math.sqrt(max(0.0, w * w + 8 * n * c * delta * (1 - delta))) - w) / (4 * n)


def tango_z(b: int, c: int, n: int, delta: float) -> float:
    """The score statistic at `delta`; it falls as `delta` grows."""
    var = n * (2 * tango_p21(b, c, n, delta) + delta * (1 - delta))
    gap = b - c - n * delta
    return gap / math.sqrt(var) if var > 0 else math.copysign(math.inf, gap)


def _solve(b: int, c: int, n: int, target: float, lo: float, hi: float) -> float:
    for _ in range(200):
        mid = (lo + hi) / 2
        if tango_z(b, c, n, mid) > target:  # the statistic falls as delta grows
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def tango_ci(b: int, c: int, n: int, z: float = Z) -> tuple[float, float, float]:
    """(estimate, lower, upper) of p12 - p21 at the two-sided level of `z`: here b counts the
    tasks where only the hybrid (Jev) is right, c those where only Opus is, n every task."""
    est = (b - c) / n
    edge = 1 - 1e-12
    return est, _solve(b, c, n, z, -edge, est), _solve(b, c, n, -z, est, edge)


def verdict(lo: float, hi: float, margin: float = MARGIN) -> str:
    if lo > margin:
        return "no peor"
    if hi < margin:
        return "peor"
    return "no concluyente"


# ---- power ----------


def power(n: int, *, coverage: float, jev_only: float, opus_only: float, margin: float = MARGIN,
          draws: int = 2000, seed: int = 20261016) -> float:  # fmt: skip
    """The chance of "no peor" with `n` tasks when a task is covered with probability
    `coverage`, and a covered task is a Jev-only or an Opus-only right answer with those rates."""
    rng = random.Random(seed)
    p_b, p_c = coverage * jev_only, coverage * (jev_only + opus_only)
    passed = 0
    for _ in range(draws):
        b = c = 0
        for _ in range(n):
            u = rng.random()
            b += u < p_b
            c += p_b <= u < p_c
        passed += tango_ci(b, c, n)[1] > margin
    return passed / draws


# Planning scenarios, from lb162x's covered tasks: (coverage, Jev-only rate, Opus-only rate).
SCENARIOS = {
    "as lb162x at 0.8 (27 covered: 0 Jev-only, 1 Opus-only)": (27 / 162, 0 / 27, 1 / 27),
    "0.7's disagreement rates (2, 6 of 41) at 0.8's coverage": (27 / 162, 2 / 41, 6 / 41),
    "0.6's disagreement rates (4, 10 of 60) at 0.8's coverage": (27 / 162, 4 / 60, 10 / 60),
    "0.6's disagreement rates at 25 % coverage, the most pessimistic": (0.25, 4 / 60, 10 / 60),
}
MARGINS = (-0.03, -0.05, -0.07, -0.10)
SIZES = (N_TASKS, 162, 281)


def power_table(draws: int = 1000) -> dict[str, dict[str, float]]:
    return {f"{name}; n={n}": {f"{m:+.2f}": power(n, coverage=cov, jev_only=jb, opus_only=oc,
                                                   margin=m, draws=draws) for m in MARGINS}
            for name, (cov, jb, oc) in SCENARIOS.items() for n in SIZES}  # fmt: skip


# ---- money and the dry run ----------


def opus_costs_by_band() -> dict[str, list[float]]:
    """lb162x's real Opus session costs by the length band of their task."""
    band = {r["id"]: r["length"] for r in recorded()}
    out: dict[str, list[float]] = {}
    for o in lb162.read_jsonl(LB162X / "opus-rows.jsonl") or []:
        out.setdefault(band[o["id"]], []).append(float(o["usd"]))
    return out


def money_lines(tasks: Sequence[Any] | None) -> list[str]:
    phase = PHASE_O
    bands = [t.length for t in tasks] if tasks else ["short"] * N_TASKS
    shown = sum(min(t.chars, lb162.WINDOW) for t in tasks) if tasks else None
    lines = [f"phase O: {phase.model_id}, {len(bands)} sessions; expected "
             f"{len(bands) * OPUS_EST_USD:.2f} USD at {OPUS_EST_USD} a task; ceiling "
             f"{phase.ceiling:g} (hard), cap {phase.full_cap:g} a session (arm N's), worst turn "
             f"{phase.worst_turn:g}, floor {phase.floor:g}; "
             f"{lb162x.at_mean(phase, OPUS_EST_USD * 1.6, phase.n)} of {phase.n} sessions at 1.6 x "
             f"the expected cost, {lb162x.guaranteed(phase)} guaranteed at worst"]  # fmt: skip
    for scale in (1.0, 1.6):
        lines.append(
            f"  simulated on lb162x's Opus sessions x{scale:g}: "
            f"{json.dumps(lb162x.simulate(phase, bands, opus_costs_by_band(), scale))}"
        )
    if shown is not None:
        lines.append(f"phase J: Jev {lb162.MODEL}, {shown / 1e6:.2f} M characters shown; expected "
                     f"{shown / 1e6 * JEV_USD_PER_MCHAR:.3f} USD, "
                     f"{shown / 1e6 * JEV_WORST_USD_PER_MCHAR:.3f} at the dearest rate before "
                     f"retries; cap {JEV_CAP_USD} (ledger and batch)")  # fmt: skip
    return lines


def replay_dry(tasks: Sequence[Any]) -> dict[str, Any]:  # pragma: no cover - needs the cache
    """Phase J through lb162's own runner with no live decider and no recordings: every task's
    document read, middle-cut and asked of the replay at all three lengths; nothing is called."""
    rows = asyncio.run(lb162.run_j(tasks, None, ANSWERS, lb162.Stop(max_consecutive=None)))
    import h2h_longdoc

    prompts = [h2h_longdoc.prompt(t) for t in tasks]
    graded = longdoc_data.last_answer("Reading done.\nThe correct answer is (B)")
    return {"rows": len(rows), "status": dict(Counter(r["status"] for r in rows)),
            "usd": sum(r[lb162.CELL]["usd"] for r in rows),
            "tries": sum(r[lb162.CELL]["tries"] for r in rows),
            "prompts_built": len(prompts), "prompt_chars_max": max(map(len, prompts)),
            "official_grade_of_a_canned_reply": graded}  # fmt: skip


def dry(with_power: bool = True) -> list[str]:  # pragma: no cover - CLI
    try:
        tasks = load_tasks()
    except (SystemExit, FileNotFoundError) as error:
        tasks, why = None, str(error)
    else:
        why = ""
    lines = [
        f"cut table (lb162 + lb162x, descriptive): "
        f"{json.dumps(cut_table(recorded(), (0.6, 0.7, 0.8, 0.9)))}"
    ]
    lines += money_lines(tasks)
    if tasks:
        lines.append(f"phase J replay dry run: {json.dumps(replay_dry(tasks))}")
        lines.append(f"tasks: {json.dumps(longdoc_data.summary(tasks))}")
    else:
        lines.append(f"no prepared tasks ({why}): --prepare for the replay dry run")
    if with_power:
        lines.append(f"power of 'no peor' (Tango 95 %): {json.dumps(power_table(), indent=1)}")
    return lines


# ---- seal ----------

# Every file the driver, phase J and the analysis load or run (lb162x's sealed set, which holds
# the session runner, the hooks and the launcher, and lb162's runner), lbo8's own files, and the
# recordings the prereg's descriptive figures come from.
SEALED = tuple(dict.fromkeys((
    "benchmarks/jev114/lbo8.py", "benchmarks/jev114/lbo8_stats.py",
    "benchmarks/h2h/h2h_lbo8.py", "tests/test_lbo8.py", "tests/test_lbo8_live.py",
    "tests/test_lbo8_stats.py", "docs/results/2026-10-16-lbo8/ids.txt",
    "docs/results/2026-10-16-lb162x/opus-rows.jsonl",
    *lb162x.SEALED,
)))  # fmt: skip
SEALED_GLOBS = lb162x.SEALED_GLOBS  # every file of the package, __pycache__ aside
# Inputs outside the repository, by their place under the home folder: the LongBench set, the
# draw the smoke task comes from, this lot's prepared tasks, and the pinned Claude Code build.
SEALED_DATA = (
    ".cache/sanchopanza/longdoc/hf/data.json",
    ".cache/sanchopanza/longdoc/tasks.jsonl",
    ".cache/sanchopanza/longdoc/lbo8/tasks.jsonl",
)
PIN_FILES = lb162x.PIN_FILES
DOCS_KEY = "~/.cache/sanchopanza/longdoc/lbo8/docs/*"  # lb162.docs_digest of the 78 documents
# This lot's own outputs, written into the results folder during the run: a resume of a sealed
# checkout must not count them as a change to the instrument.
OUTPUTS = tuple(
    p.relative_to(REPO).as_posix()
    for p in (SMOKE.rows, SMOKE.stop, JEV_ROWS, JEV_STOP, ANSWERS, PHASE_O.rows, PHASE_O.stop,
              SUMMARY)
)  # fmt: skip


def sealed_paths() -> list[str]:
    globbed = sorted({p.relative_to(REPO).as_posix() for g in SEALED_GLOBS for p in REPO.glob(g)
                      if p.is_file() and "__pycache__" not in p.parts})  # fmt: skip
    return [*SEALED, *(p for p in globbed if p not in SEALED)]


def docs_digest() -> str:  # pragma: no cover - needs the prepared cache
    return lb162.docs_digest(load_tasks())


def manifest() -> dict[str, str]:
    doc = (OUT / "prereg.md").relative_to(REPO).as_posix()
    out = {p: lb162.digest(REPO / p) for p in (doc, *sealed_paths())}
    data = {f"~/{p}": lb162.raw_digest(pathlib.Path.home() / p) for p in (*SEALED_DATA, *PIN_FILES)}
    return out | data | {DOCS_KEY: docs_digest()}


def any_session() -> bool:
    return ANSWERS.exists() or any(p.rows.exists() or p.stop.exists() for p in DRIVEN)


def seal(again: bool = False) -> str:
    """prereg.manifest.json and prereg.sha256 (lb162x's scheme). Another seal already there is
    refused unless `again`, and then only while no session or answer of this lot exists."""
    found = manifest()
    value = lb162.combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        if not again:
            raise SystemExit("prereg.sha256 already holds another seal: nothing written")
        if any_session():
            raise SystemExit("sessions of this lot exist: a re-seal is an amendment, not a seal")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def require_prereg() -> str:
    """The seal's value, refused unless everything it covers matches."""
    target = OUT / "prereg.sha256"
    value = lb162.combined(manifest())
    if not target.exists() or target.read_text().strip() != value:
        raise SystemExit("prereg.md, the code or the inputs differ from the seal: nothing spent")
    return value


def seal_state() -> str:
    target = OUT / "prereg.sha256"
    if not target.exists():
        return "not sealed"
    same = target.read_text().strip() == lb162.combined(manifest())
    return "sealed, matches" if same else "MISMATCH"


def docs_problems() -> list[str]:
    path = OUT / "prereg.manifest.json"
    if not path.exists():
        return []
    sealed = json.loads(path.read_text(encoding="utf-8")).get(DOCS_KEY)
    return [] if sealed == docs_digest() else ["the prepared documents differ from the seal"]


def checkout_problems(seal_value: str, git: Any = None) -> list[str]:
    """The live run's checkout: HEAD detached, at the commit whose message carries the seal,
    and nothing changed but this lot's outputs. `git(args) -> (code, stdout)`."""
    run = git or lb162x._git
    found = []
    if run(["symbolic-ref", "-q", "HEAD"])[0] == 0:
        found.append("HEAD is on a branch: run from `git worktree add --detach <sealed commit>`")
    if seal_value not in run(["log", "-1", "--format=%B", "HEAD"])[1]:
        found.append("HEAD's commit message does not carry the seal")
    changed = [line[3:].strip().strip('"') for line in
               run(["status", "--porcelain", "--untracked-files=all"])[1].splitlines()
               if line.strip()]  # fmt: skip
    if dirty := [c for c in changed if c not in OUTPUTS]:
        found.append(f"the tree is not clean: {', '.join(dirty[:5])}")
    return found


# ---- analysis ----------


def stop_of(phase: Any) -> dict[str, Any] | None:
    return (lb162.read_jsonl(phase.stop) or [None])[0]


def pause_reasons(run_dir: pathlib.Path = RUN_DIR) -> list[str]:
    """Why no verdict may be read yet: a LIMIT.flag or STOP in the run folder, phase J not over,
    or phase O not ended by finishing or by its ceiling."""
    reasons = [f"{name} in the run folder" for name in ("LIMIT.flag", "STOP")
               if (run_dir / name).exists()]  # fmt: skip
    if why := phase_j_final(lb162.read_jsonl(JEV_ROWS), stop_of(PHASE_J)):
        reasons.append(why)
    kind = (stop_of(PHASE_O) or {}).get("kind")
    if kind not in lb162x.FINAL:
        reasons.append(f"phase O {kind or 'not run'}")
    return reasons


def analysis(run_dir: pathlib.Path = RUN_DIR) -> dict[str, Any]:
    import lbo8_stats

    rows = lb162.read_jsonl(JEV_ROWS)
    if rows is None:
        raise SystemExit(f"no {JEV_ROWS.name}: phase J has not run")
    opus = {r["id"]: r for r in lb162.read_jsonl(PHASE_O.rows) or []}
    out = lbo8_stats.analyse(rows, opus, pause_reasons(run_dir)) | {
        "stops": {p.key: (stop_of(p) or {}).get("kind") for p in DRIVEN},
        "jev_ledger_batch_usd": round(batch_spent(run_dir), 6),
    }
    lbo8_stats.write_summary(SUMMARY, out)
    return out


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    for flag in ("--pool", "--freeze-ids", "--prepare", "--dry", "--seal", "--analyse"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--no-power", action="store_true")
    ap.add_argument("--reseal", action="store_true", help="with --seal: replace a seal")
    args = ap.parse_args(argv)
    if args.pool:
        print(json.dumps(pool(), indent=1))
    elif args.freeze_ids:
        print(freeze_ids())
    elif args.prepare:
        print(prepare())
    elif args.seal:
        print(seal(again=args.reseal))
    elif args.analyse:
        print(json.dumps(analysis()["primary"], indent=1))
    else:
        print("\n".join(dry(with_power=not args.no_power)))
        print(f"seal: {seal_state()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
