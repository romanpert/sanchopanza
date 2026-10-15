"""Jev 1.14 against 1.13 with the long window, lot L6: LongBench v2 (B3), QASPER (A6) and
LongMemEval (A7). Pre-registered in docs/results/2026-10-15-jev114-l6/prereg.md.

    python benchmarks/jev114/l6.py --run --sets b3 --limit 2          # free: replay only
    python benchmarks/jev114/l6.py --run --sets b3 --live             # spends (caps in code)
    python benchmarks/jev114/l6.py --smoke --live                     # dev items only
    python benchmarks/jev114/l6.py                                    # analysis, free
    python benchmarks/jev114/l6.py --seal                             # seal prereg.md + code

Every experiment crosses model (jev-1.13.0 `j13r`, jev-1.14.0 `j14`, both asked today) with
window: `S` is today's production cut (no long-context header, the shipped `Limits`), `L` sends
`TypeSafe-Danger-Zone-Long-Context` and widens what each point shows (`Limits`, or the whole
document). Cells are named `<model>-<window>`, e.g. `j14-L`.

- `b3`: 50 LongBench v2 tasks of the 2026-10-06 confirmation (the 10 dev tasks out). One Choice
        A-D over the document, middle-cut to `CUT_CHARS[window]` characters. Claude is not
        asked: Sonnet 5.5's recorded answers and costs (clean Claude Code, arm N) are read from
        the sessions file of that run.
- `a6`: the 300 QASPER papers of docs/results/2026-09-27-longdocs. `L`: `Squire.triage_many`
        with every paragraph whole in one call. `S` is the recorded 2026-09-27 tournament
        (`rec13-S`, replayed free); the tournament is not asked again.
- `a7`: the 120 LongMemEval S test questions of docs/results/2026-09-28-memory-gate, in a
        seeded order, as many as the lot's cap allows. `needs_recall` once per model, then the
        triage over every session: `S` at 900 characters each (the shipped gate), `L` with
        every session whole in one call. The recorded 2026-09-28 gate is `rec13-S`.

Every live call goes through `CappedDecider` on the shared ledger and this lot's cap, at most
CONCURRENCY in flight; answers are recorded per cell in OUT (hashed keys, no text), so a
relaunch only asks what is missing. The key comes from TYPESAFE_API_KEY or the `.env` that
SANCHOPANZA_KEYS_ENV names (never printed).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import random
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
for extra in ("src", "benchmarks/h2h", "benchmarks/memory_gate"):
    sys.path.insert(0, str(REPO / extra))
sys.path.insert(0, str(HERE))

import l4  # noqa: E402  (Arm, load_key, preflight_or_stop, MODELS: shared with lot L4)

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.contract import Choice  # noqa: E402
from sanchopanza.limits import Limits  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-15-jev114-l6"
LEDGER_PATH = l4.LEDGER_PATH
LEDGER_CAP_USD = l4.LEDGER_CAP_USD
BATCH = "jev114-l6"
BATCH_CAP_USD = 1.50
SMOKE_CAP_USD = 0.10  # the smoke's own ceiling, on the same batch in the ledger
CONCURRENCY = 4
MODELS = l4.MODELS  # j13r: jev-1.13.0, j14: jev-1.14.0
WINDOWS = ("S", "L")
CELLS = tuple(f"{m}-{w}" for w in WINDOWS for m in MODELS)
TIMEOUT_S = {"S": 30.0, "L": 180.0}
ORDER_SEED = 20261015
SETS = ("b3", "a6", "a7")

# ---- B3: LongBench v2 -------------------------------------------------------------------------

B3_POINT = "longbench_choice"
# Characters of the document shown, head half + tail half (LongBench's own middle cut). S fits
# 32k tokens a question without the header; L fits 262k with it (measured in the smoke).
CUT_CHARS = {"S": 100_000, "L": 900_000}
SHRINK = (1.0, 0.8, 0.64)  # a cell refused (HTTP 400, timeout) is asked again shorter, both models
B3_CUTS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
B3_TAU = 0.9  # the registered substitution cut
B3_MIN_COVERAGE = 0.20
B3_MIN_PRECISION = 0.90
SONNET_SESSIONS = pathlib.Path.home() / ".cache/sanchopanza/longdoc/h2h/longdoc-conf/sessions.jsonl"
SONNET_ARM = "SONNET-CC"  # clean Claude Code, Sonnet 5.5 (arm N of the confirmation)
B3_INSTRUCTIONS = (
    "Which option is the correct answer to `question`? The answer is in `document`: read it "
    "to decide."
)

# ---- A6 and A7: the whole document in one call ------------------------------------------------

LONG_LIMITS = Limits(page_chars=400_000, pages_per_call=1_000)
QASPER = pathlib.Path.home() / ".cache" / "sancho" / "qasper-test.jsonl"
A6_TOURNAMENT = REPO / "fixtures" / "longdocs.jsonl"  # the 2026-09-27 run, jev-1.13.0
A6_BUDGET_SHARE = 0.25  # P28's text bar, used by the threshold-free reading
A7_RECORDED = pathlib.Path.home() / ".cache/sanchopanza/memory_gate/longmemeval/decisions.jsonl"
A7_Q_EST_USD = 0.016  # both models, both windows, needs_recall: 0.012 in the smoke, plus margin
A7_MIN_QUESTIONS = 20
A7_WAVE = 2  # questions in flight at once
A6_EST_USD = 0.54  # both models, 300 papers (smoke): A6 does not start unless it fits
HALTED: list[str] = []  # a cap refusal or an out-of-funds answer: the run stops, rows unwritten


def big_thresholds() -> Thresholds:
    """Production cuts; only the squire's own per-job caps lifted (the ledger caps spend)."""
    return replace(Thresholds(), max_decisions=10**6, max_usd=10.0)


# ---- arms -------------------------------------------------------------------------------------


def cell_arms(set_name: str, live: bool, gate: asyncio.Semaphore,
              cap_usd: float = BATCH_CAP_USD) -> dict[str, l4.Arm]:  # fmt: skip
    """One recorded-first arm per cell; live through the cap when `live`."""
    capped: dict[str, Any] = {}
    if live:
        from sanchopanza.budget import SpendLedger
        from sanchopanza.providers import CappedDecider
        from sanchopanza.providers.jev import JevDecider

        ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
        for cell in CELLS:
            model, window = cell.split("-")
            inner = JevDecider(model=MODELS[model], long_context=window == "L", images=False,
                               timeout_s=TIMEOUT_S[window])  # fmt: skip
            capped[cell] = Halting(
                CappedDecider(inner, ledger=ledger, batch=BATCH, max_usd=cap_usd)
            )
    return {
        cell: l4.Arm(
            cell,
            OUT / f"{set_name}-answers-{cell}.jsonl",
            MODELS[cell.split("-")[0]],
            capped.get(cell),
            gate,
        )  # fmt: skip
        for cell in CELLS
    }


class Halting:
    """A live decider that notes a cap refusal or a 402 before `l4.Arm` counts it as a model
    failure: the runner then stops and writes no rows (a relaunch replays what was paid)."""

    def __init__(self, inner: Any) -> None:
        self._inner, self.name = inner, inner.name

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Any:
        from sanchopanza.contract import DeciderOutOfFunds
        from sanchopanza.providers.capped import SpendCapReached

        try:
            return await self._inner.decide(point, state, questions)
        except (SpendCapReached, DeciderOutOfFunds) as error:
            HALTED.append(str(error))
            raise


class Watched:
    """One call site's view of an arm: its own failures and cost, not the arm's running count
    (items run concurrently, so the arm's counter moves under every other item)."""

    def __init__(self, arm: Any) -> None:
        self.arm, self.name = arm, arm.name
        self.failed, self.usd = 0, 0.0

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Any:
        decision = await self.arm.decide(point, state, questions)
        self.usd += decision.cost_usd
        if decision.failed or not decision.answers:
            self.failed += 1
        return decision


def recorded_arm(name: str, path: pathlib.Path, gate: asyncio.Semaphore) -> l4.Arm:
    return l4.Arm(name, path, None, None, gate)


def model_order(position: int) -> tuple[str, ...]:
    """Both models on every item, the first alternating with the item's rank."""
    return tuple(MODELS) if position % 2 == 0 else tuple(MODELS)[::-1]


def launch_order(n: int) -> list[int]:
    order = list(range(n))
    random.Random(ORDER_SEED).shuffle(order)
    return order


def batch_spent() -> float:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return 0.0
    return SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD).spent(BATCH)


# ---- B3 ---------------------------------------------------------------------------------------


def middle_cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n[...]\n" + text[-half:]


def b3_question(task: Any) -> dict[str, Choice]:
    letters = ("A", "B", "C", "D")
    return {"answer": Choice(B3_INSTRUCTIONS, dict(zip(letters, task.choices, strict=True)))}


def top_of(decision: Any) -> tuple[str | None, float | None, dict[str, float]]:
    """(letter, its probability, the distribution) of the Choice; Nones when unanswered."""
    answer = decision.answer("answer") if decision.answers else None
    if answer is None or answer.empty:
        return None, None, {}
    probs = {k: round(float(v), 4) for k, v in answer.probabilities.items()}
    letter = answer.choice
    if letter not in probs:  # no probability for the pick: not on the registered scale
        return None, None, probs
    return letter, probs[letter], probs


def b3_tasks(dev: bool) -> list[Any]:
    import h2h_longdoc
    import longdoc_data

    tasks = longdoc_data.load()
    ids = {x.strip() for x in h2h_longdoc.DEV_IDS.read_text().splitlines()
           if x.strip() and not x.startswith("#")}  # fmt: skip
    return [t for t in tasks if (t.task_id in ids) == dev]


def sonnet_answers() -> dict[str, dict[str, Any]]:
    rows = [json.loads(x) for x in SONNET_SESSIONS.read_text(encoding="utf-8").splitlines() if x]
    out = {}
    for r in rows:
        if r.get("arm") == SONNET_ARM:
            out[r["task_id"]] = {"letter": r.get("final_answer"), "ok": bool(r.get("ok_oficial")),
                                 "usd": round(float(r.get("list_usd") or 0.0), 6)}  # fmt: skip
    return out


async def b3_one(position: int, task: Any, arms: dict[str, l4.Arm]) -> dict[str, Any]:
    text = pathlib.Path(task.doc_path).read_text(encoding="utf-8")
    qs = b3_question(task)
    row: dict[str, Any] = {"id": task.task_id, "gold": task.gold, "chars": len(text),
                           "length": task.length, "difficulty": task.difficulty}  # fmt: skip
    for window in WINDOWS:
        paid = dict.fromkeys(MODELS, 0.0)  # every attempt counts, the discarded ones too
        tries = 0
        for factor in SHRINK:
            limit = int(CUT_CHARS[window] * factor)
            state = {"question": task.question.strip(), "document": middle_cut(text, limit)}
            got = {}
            tries += 1
            for model in model_order(position):
                decision = await arms[f"{model}-{window}"].decide(B3_POINT, state, qs)
                paid[model] += decision.cost_usd
                got[model] = (decision, top_of(decision))
            if all(v[1][0] is not None for v in got.values()) or HALTED:
                break
        for model, (decision, (letter, p, probs)) in got.items():
            row[f"{model}-{window}"] = {"letter": letter, "p": p, "probs": probs,
                                        "usd": round(paid[model], 6), "tries": tries,
                                        "tokens": decision.input_tokens,
                                        "shown_chars": min(len(text), limit)}  # fmt: skip
    return row


async def run_b3(live: bool, limit: int | None, dev: bool = False) -> list[dict[str, Any]]:
    tasks = b3_tasks(dev)[: limit if limit is not None else None]
    gate = asyncio.Semaphore(CONCURRENCY)
    arms = cell_arms("b3-dev" if dev else "b3", live, gate, SMOKE_CAP_USD if dev else BATCH_CAP_USD)
    order = launch_order(len(tasks))
    done = await asyncio.gather(*(b3_one(rank, tasks[i], arms) for rank, i in enumerate(order)))
    by_index = dict(zip(order, done, strict=True))
    sonnet = sonnet_answers()
    return [by_index[i] | {"sonnet": sonnet.get(tasks[i].task_id)} for i in range(len(tasks))]


# ---- A6 ---------------------------------------------------------------------------------------


def longdocs_module() -> Any:
    """benchmarks/longdocs/run.py under its own name: memory_gate has a `run` module too."""
    import importlib.util

    if "longdocs_run" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "longdocs_run", REPO / "benchmarks" / "longdocs" / "run.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["longdocs_run"] = module
        spec.loader.exec_module(module)
    return sys.modules["longdocs_run"]


def a6_rows(extra: bool = False) -> list[dict[str, Any]]:
    """The 300 papers of longdocs (`run.build`); `extra` gives eligible papers past them."""
    longdocs = longdocs_module()
    if not extra:
        return longdocs.build(QASPER)
    saved = longdocs.PAPERS
    try:
        longdocs.PAPERS = 10**6
        return longdocs.build(QASPER)[saved:]
    finally:
        longdocs.PAPERS = saved


async def a6_one(position: int, row: dict[str, Any], arms: dict[str, l4.Arm],
                 rec: l4.Arm | None) -> dict[str, Any]:  # fmt: skip
    out: dict[str, Any] = {"id": row["id"], "gold": row["gold"],
                           "sizes": [len(t) + len(x) for t, x in row["pages"]]}  # fmt: skip
    cells = [(f"{m}-L", arms[f"{m}-L"], LONG_LIMITS) for m in model_order(position)]
    if rec is not None:
        cells.append(("rec13-S", rec, Limits()))
    for name, arm, limits in cells:
        watched = Watched(arm)
        squire = Squire(watched, thresholds=big_thresholds(), limits=limits)
        verdicts = await squire.triage_many(purpose=row["question"], pages=row["pages"])
        failed = watched.failed > 0 or all(p is None for _, p in verdicts)
        out[name] = None if failed else {"keep": [k for k, _ in verdicts],
                                         "p": [p for _, p in verdicts]}  # fmt: skip
    return out


async def run_a6(live: bool, limit: int | None, dev: bool = False) -> list[dict[str, Any]]:
    rows = a6_rows(extra=dev)[: limit if limit is not None else None]
    gate = asyncio.Semaphore(CONCURRENCY)
    arms = cell_arms("a6-dev" if dev else "a6", live, gate, SMOKE_CAP_USD if dev else BATCH_CAP_USD)
    rec = None if dev else recorded_arm("rec13-S", A6_TOURNAMENT, gate)
    order = launch_order(len(rows))
    done = await asyncio.gather(*(a6_one(k, rows[i], arms, rec) for k, i in enumerate(order)))
    by_index = dict(zip(order, done, strict=True))
    return [by_index[i] for i in range(len(rows))]


# ---- A7 ---------------------------------------------------------------------------------------


def a7_questions(dev: bool) -> list[Any]:
    import longmemeval as lme

    parts = lme.slices(lme.load())
    return parts["dev"] if dev else parts["test"]


async def a7_triage(arm: Any, q: Any, ms: Sequence[Any], window: str) -> list[int] | None:
    """Kept session indexes, or None when a call of this triage failed or none answered (the
    analysis reads None both ways: out of the complete-case comparison, and as an empty
    injection, the original runner's reading)."""
    from sanchopanza.harness import memory_gate as mg

    arm = Watched(arm)
    if window == "S":
        squire = Squire(arm, thresholds=big_thresholds())
        verdicts = await mg.triage_memories(squire, q["question"], ms)
    else:
        squire = Squire(arm, thresholds=big_thresholds(), limits=LONG_LIMITS)
        pages = mg.pages_of(ms, purpose=q["question"], limit=LONG_LIMITS.page_chars)
        verdicts = await squire.triage_many(purpose=q["question"], pages=pages)
    if arm.failed or not any(p is not None for _, p in verdicts):
        return None
    return [i for i, (keep, _) in enumerate(verdicts) if keep]


async def a7_one(position: int, q: Any, arms: dict[str, l4.Arm],
                 rec: l4.Arm | None) -> dict[str, Any]:  # fmt: skip
    import longmemeval as lme

    ms = lme.memories_of(q)
    seen, total = lme.excerpt_ceiling(q)
    row: dict[str, Any] = {"id": q["question_id"], "type": q["question_type"],
                           "gold": sorted(lme.gold_of(q)), "sizes": [len(m.body) for m in ms],
                           "bm25@3": sorted(lme.arm_bm25(q, ms, 3)),
                           "excerpt_seen": seen, "excerpt_total": total}  # fmt: skip
    windows = WINDOWS if position % 4 < 2 else WINDOWS[::-1]
    for model in model_order(position):
        row[f"{model}-look"] = await a7_look(arms[f"{model}-S"], q)
        for window in windows:
            kept = await a7_triage(arms[f"{model}-{window}"], q, ms, window)
            row[f"{model}-{window}"] = kept
    if rec is not None:
        row["rec13-look"] = await a7_look(rec, q)
        row["rec13-S"] = await a7_triage(rec, q, ms, "S")
    return row


async def a7_look(arm: Any, q: Any) -> bool | None:
    """`needs_recall`'s look, None when the call failed (the point itself fails open to look)."""
    watched = Watched(arm)
    look = (await Squire(watched, thresholds=big_thresholds()).needs_recall(q["question"])).look
    return None if watched.failed else look


async def run_a7(live: bool, limit: int | None, dev: bool = False) -> list[dict[str, Any]]:
    questions = a7_questions(dev)
    order = launch_order(len(questions))[: limit if limit is not None else None]
    gate = asyncio.Semaphore(CONCURRENCY)
    arms = cell_arms("a7-dev" if dev else "a7", live, gate, SMOKE_CAP_USD if dev else BATCH_CAP_USD)
    rec = None if dev else recorded_arm("rec13-S", A7_RECORDED, gate)
    done_before = None if dev or live or limit is not None else read_rows("a7")
    if done_before is not None:  # the questions of the run of record, replayed; never fewer
        order = order[: len(done_before)]
    elif live:
        room = BATCH_CAP_USD - batch_spent()
        print(f"a7: {room:.4f} USD left, about {int(room / A7_Q_EST_USD)} questions",
              file=sys.stderr)  # fmt: skip
    rows: list[dict[str, Any]] = []
    for start in range(0, len(order), A7_WAVE):
        wave = order[start : start + A7_WAVE]
        fresh = done_before is None and live
        if fresh and batch_spent() + A7_Q_EST_USD * len(wave) > BATCH_CAP_USD:
            print(f"a7: soft stop before rank {start}: the cap would not hold", file=sys.stderr)
            break
        got = await asyncio.gather(
            *(a7_one(start + k, questions[i], arms, rec) for k, i in enumerate(wave))
        )
        rows = [*rows, *(r | {"rank": start + k} for k, r in enumerate(got))]
        if HALTED:
            break
    return rows


RUN: dict[str, Callable[..., Any]] = {"b3": run_b3, "a6": run_a6, "a7": run_a7}


# ---- analysis, seal, main ---------------------------------------------------------------------


def analyse(results: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    import l6_analysis as an

    out: dict[str, Any] = {}
    if "b3" in results:
        out["b3"] = an.analyse_b3(results["b3"], cuts=B3_CUTS, tau=B3_TAU,
                                  min_cov=B3_MIN_COVERAGE, min_prec=B3_MIN_PRECISION)  # fmt: skip
    if "a6" in results:
        out["a6"] = an.analyse_a6(results["a6"], share=A6_BUDGET_SHARE)
    if "a7" in results:
        out["a7"] = an.analyse_a7(results["a7"], min_questions=A7_MIN_QUESTIONS)
    return out


def spent_in_ledger() -> dict[str, float] | None:
    from sanchopanza.budget import SpendLedger

    if not LEDGER_PATH.exists():
        return None
    ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
    return {"batch": round(ledger.spent(BATCH), 6), "ledger": round(ledger.spent(), 6)}


SEALED = (
    "benchmarks/jev114/l6.py", "benchmarks/jev114/l6_analysis.py", "tests/test_jev114_l6.py",
    "benchmarks/jev114/l4.py", "benchmarks/jev114/l4_stats.py",
    "benchmarks/h2h/longdoc_data.py", "benchmarks/h2h/h2h_longdoc.py",
    "benchmarks/h2h/longdoc-dev-ids.txt", "benchmarks/longdocs/run.py",
    "benchmarks/triage_sets/run.py", "benchmarks/memory_gate/longmemeval.py",
    "benchmarks/memory_gate/run.py", "fixtures/longdocs.jsonl",
    "src/sanchopanza/harness/memory_gate.py", "src/sanchopanza/providers/__init__.py",
    "src/sanchopanza/providers/jev.py", "src/sanchopanza/providers/jev_models.py",
    "src/sanchopanza/providers/capped.py", "src/sanchopanza/providers/recorded.py",
    "src/sanchopanza/budget.py", "src/sanchopanza/_lockfile.py", "src/sanchopanza/funds.py",
    "src/sanchopanza/media.py", "src/sanchopanza/redact.py", "src/sanchopanza/contract.py",
    "src/sanchopanza/squire.py", "src/sanchopanza/policy.py", "src/sanchopanza/limits.py",
    "src/sanchopanza/text.py", "src/sanchopanza/points/chunks.py",
    "src/sanchopanza/points/hierarchy.py", "src/sanchopanza/points/memory.py",
    "src/sanchopanza/points/passages.py", "src/sanchopanza/points/triage.py",
)  # fmt: skip
# Inputs outside the repository (not redistributed), hashed by their place under the home folder.
SEALED_DATA = (
    ".cache/sanchopanza/longdoc/tasks.jsonl",
    ".cache/sanchopanza/longdoc/h2h/longdoc-conf/sessions.jsonl",
    ".cache/sanchopanza/memory_gate/longmemeval/decisions.jsonl",
    ".cache/sanchopanza/memory_gate/longmemeval/longmemeval_s_cleaned.json",
    ".cache/sancho/qasper-test.jsonl",
)


def manifest() -> dict[str, str]:
    """`<path> -> sha256` of prereg.md, the code (LF bytes) and the external inputs."""
    import hashlib

    def digest(path: pathlib.Path, text: bool) -> str:
        data = path.read_bytes()
        return hashlib.sha256(data.replace(b"\r\n", b"\n") if text else data).hexdigest()

    doc = (OUT / "prereg.md").relative_to(REPO).as_posix()
    out = {p: digest(REPO / p, True) for p in (doc, *SEALED)}
    return out | {f"~/{p}": digest(pathlib.Path.home() / p, False) for p in SEALED_DATA}


def combined(found: Mapping[str, str]) -> str:
    import hashlib

    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in found.items()).encode()).hexdigest()


def seal(again: bool = False) -> str:
    """prereg.manifest.json and prereg.sha256 (lot L4's scheme). Written once: a different seal
    already there is refused unless `again` (a re-seal before any live call, said in prereg)."""
    found = manifest()
    value = combined(found)
    target = OUT / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value) and not again:
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    (OUT / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                              encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def require_prereg() -> None:
    target = OUT / "prereg.sha256"
    if not target.exists() or target.read_text().strip() != combined(manifest()):
        raise SystemExit("prereg.md, the code or the inputs differ from the seal: nothing spent")


def write_rows(name: str, rows: list[dict[str, Any]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}-scored.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n"
    )


def read_rows(name: str) -> list[dict[str, Any]] | None:
    path = OUT / f"{name}-scored.jsonl"
    if not path.exists():
        return None
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def smoke(live: bool) -> None:
    """Dev items only: one LongBench dev task, two QASPER papers outside the 300, one
    LongMemEval dev question; every cell. Tokens, cost and failures, for the constants."""
    if live:
        l4.load_key()
        l4.preflight_or_stop()
    for name, limit in (("b3", 1), ("a6", 2), ("a7", 1)):
        rows = asyncio.run(RUN[name](live, limit, dev=True))
        write_rows(f"smoke-{name}", rows)
    print(json.dumps(spent_in_ledger()), file=sys.stderr)


def run_live_set(name: str) -> int:
    """One set of the run of record. 0 when its rows were written; 2 when the run stopped."""
    if read_rows(name) is not None:
        print(f"{name}: scored already, frozen: not asked again", file=sys.stderr)
        return 0
    if name == "a6" and batch_spent() + A6_EST_USD > BATCH_CAP_USD:
        print(f"a6: {BATCH_CAP_USD - batch_spent():.4f} USD left, under the {A6_EST_USD} it "
              "needs: not started", file=sys.stderr)  # fmt: skip
        return 2
    rows = asyncio.run(RUN[name](True, None))
    if HALTED:
        print(f"{name}: STOP, rows not written: {HALTED[0]}", file=sys.stderr)
        return 2
    write_rows(name, rows)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="ask (replay first) and score")
    parser.add_argument("--sets", default=",".join(SETS))
    parser.add_argument("--live", action="store_true", help="ask Jev what is not recorded")
    parser.add_argument("--limit", type=int, default=None, help="with --run: first N items")
    parser.add_argument("--smoke", action="store_true", help="dev items only")
    parser.add_argument("--seal", action="store_true", help="seal prereg.md and the code")
    parser.add_argument("--reseal", action="store_true", help="with --seal: replace a seal")
    args = parser.parse_args(argv)
    if args.seal:
        print(seal(again=args.reseal))
        return 0
    if args.smoke:
        smoke(args.live)
        return 0
    names = [s for s in args.sets.split(",") if s]
    if any(s not in SETS for s in names):
        parser.error(f"--sets among {SETS}")
    if args.run and args.live:
        if args.limit is not None:
            parser.error("--live runs the registered sets whole: no --limit")
        require_prereg()
        l4.load_key()
        l4.preflight_or_stop()
        for name in names:
            if run_live_set(name):
                return 2
    elif args.run:
        for name in names:
            rows = asyncio.run(RUN[name](False, args.limit))
            write_rows(name if args.limit is None else f"{name}-first{args.limit}", rows)
        if args.limit is not None:
            return 0
    results = {n: rows for n in SETS if (rows := read_rows(n)) is not None}
    summary = analyse(results) | {"spent": spent_in_ledger()}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8",
                                      newline="\n")  # fmt: skip
    print(json.dumps({k: {n: (v["diff"], v["ci95"], v["p_holm"], v["verdict"])
                          for n, v in s.get("family", {}).items()}
                      for k, s in summary.items() if isinstance(s, dict)}, indent=1),
          file=sys.stderr)  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
