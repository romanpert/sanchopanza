"""B6: `triage_pages` and `select_passages` in Spanish against English, on the same questions.

    python -I benchmarks/b6_es/b6_run.py --dry                  # free: the calls, their cost
    python -I benchmarks/b6_es/b6_run.py --power                # free: questions needed
    python -I benchmarks/b6_es/b6_run.py --seal                 # once, before any answer
    python -I benchmarks/b6_es/b6_run.py --bench pages --smoke --live
    python -I benchmarks/b6_es/b6_run.py --bench pages --live   # spends: Jev only, caps in code
    python -I benchmarks/b6_es/b6_run.py --bench docs --live    # only once pages is finished
    python -I benchmarks/b6_es/b6_run.py --bench pages          # free replay and analysis

Launched through `b6-es-run.cmd` (repository root). Pre-registered in
docs/results/2026-10-16-b6-es/prereg.md. The bench is built by `b6_build.py` from MLQA v1.0
and Wikipedia (CC BY-SA) under `--data`, outside the repository.

Arms, jev-1.13.0, shipped thresholds and limits, no answering model:

- pages, `Squire.triage_pages` over ten pages: `P-es` and `P-en`, the same questions and pages
  in each language. The decider sees each page's first 900 characters (`chunks.PAGE_LIMIT`);
  the consumer's own cut to 900 is scored free from P-es (`b6_score.page_score`).
- docs, `Squire.select_passages` over a whole article: `D-es`, `D-en`, and `D-es90` (past 90
  paragraphs only the 90 best by BM25 are sent; an article of 90 or fewer reuses D-es).

Every live call goes through `CappedDecider` on this bench's ledger, is recorded in FIXTURE
(hashed keys, no text), at most CONCURRENCY in flight, never retried. Launches are recorded in
`$SANCHOPANZA_B6_RUN/launches.jsonl` and limited by the relaunch rule (`launch_gate`). The key
comes from TYPESAFE_API_KEY or the `.env` file SANCHOPANZA_KEYS_ENV names, inside the process,
never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import b6_analysis as an  # noqa: E402
import b6_build as bb  # noqa: E402
import b6_score as sc  # noqa: E402

from sanchopanza import Squire, Thresholds, truth  # noqa: E402
from sanchopanza.contract import DeciderOutOfFunds, Decision  # noqa: E402
from sanchopanza.providers.capped import SpendCapReached, estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, key_of  # noqa: E402
from sanchopanza.text import BM25Index  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-16-b6-es"
PREREG = OUT / "prereg.md"
SEAL = OUT / "prereg.sha256"
FIXTURE = REPO / "fixtures" / "b6-es.jsonl"
SEALED = ("docs/results/2026-10-16-b6-es/prereg.md",
          "docs/results/2026-10-16-b6-es/bench-manifest.json",
          "benchmarks/b6_es/b6_run.py", "benchmarks/b6_es/b6_analysis.py",
          "benchmarks/b6_es/b6_score.py", "benchmarks/b6_es/b6_build.py",
          "benchmarks/b6_es/b6_wiki.py", "tests/test_b6_es.py", "b6-es-run.cmd")  # fmt: skip
# And every file of src/sanchopanza/**/*.py: the code measured is part of the seal.
MODEL = "jev-1.13.0"
RUN_DIR = Path(os.environ.get("SANCHOPANZA_B6_RUN") or "C:/sp-runs/b6-es")
N_PAGES: int | None = None  # every built row (300)
N_DOCS: int | None = None  # every built row
BENCHES = ("pages", "docs")
ARMS = {"pages": an.PAGE_ARMS, "docs": an.DOC_ARMS}
BATCH_CAP_USD = {"pages": 0.30, "docs": 5.00}  # `--dry` must fit its pessimistic estimate
SMOKE_CAP_USD = 0.10  # each of the two smoke batches (pages, docs)
LEDGER_CAP_USD = sum(BATCH_CAP_USD.values()) + 2 * SMOKE_CAP_USD  # 5.50
MAX_LAUNCHES = 3  # the first and two relaunches; a pause is not a launch
CONCURRENCY = 4
TIMEOUT_S = 30.0
MEDIAN_USD = 71e-6  # Jev's median per request, quoted beside the size estimates
# Billed tokens against `estimate_usd`'s three characters a token, measured on the published
# HotpotQA fixtures (chunk_context 4,049 tokens, chunk_sentences 1,449): the reservation is
# pessimistic by these factors, and the expected cost is the reservation times them.
EXPECTED_FACTOR = {"triage_pages": 0.81, "select_sentences": 0.39}
# The dry stub's answers: in an in-context call the STUB_SURE best pages by BM25 at 0.9 (past
# the 0.75 gate), the next up to STUB_MAYBE at 0.5, the rest at 0.05. Fitted to QASPER, where Jev
# sent 8.1 paragraphs a question to the sentence stage (1,766 calls, 219 questions).
STUB_SURE, STUB_MAYBE = 8, 12
PAUSE_STATUSES = frozenset({401, 402, 403, 429})  # and every 5xx
MAX_FAILURES_IN_A_ROW = 3  # of any kind (a timeout too): then every later call is refused
ROW: contextvars.ContextVar[str] = contextvars.ContextVar("b6_row", default="-")


# ---- deciders ----------------------------------------------------------------------------


class Stub:
    """The dry run's decider: answers every question by BM25 rank, costs nothing."""

    name = "stub"

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        keys = list(questions)
        if point == "triage_pages":
            lines = str(state["pages"]).split("\n")
            scores = BM25Index(lines).scores(str(state["purpose"]))
            order = sorted(range(len(lines)), key=lambda k: (-scores[k], k))
            rank = {k: r for r, k in enumerate(order)}
            p = {k: 0.9 if rank[k] < STUB_SURE else 0.5 if rank[k] < STUB_MAYBE else 0.05
                 for k in range(len(lines))}  # fmt: skip
            answers = {key: truth(p.get(k, 0.05)) for k, key in enumerate(keys)}
        else:
            answers = {key: truth(0.5) for key in keys}
        return Decision(point, answers, "stub", MODEL)


def halt_kind(error: Exception) -> str | None:
    """ "cap" for a cap refusal; "pause" for an outage a later call would meet too (401, 402,
    403, 429, a 5xx, no connection); None for this call's own failure (a timeout, a 400)."""
    if isinstance(error, SpendCapReached):
        return "cap"
    if isinstance(error, DeciderOutOfFunds):
        return "pause"
    found = re.search(r"HTTP (\d{3})", str(error))
    if found and (int(found.group(1)) in PAUSE_STATUSES or int(found.group(1)) >= 500):
        return "pause"
    if "unreachable" in str(error) and "Timeout" not in str(error):
        return "pause"
    return None


def recordings() -> RecordedDecider:
    """FIXTURE's lines answered by MODEL only: a line from any other model is ignored, so its
    query is a miss and is asked again live (the new line is written after it and wins)."""
    if not FIXTURE.exists():
        return RecordedDecider([])
    lines = [json.loads(x) for x in FIXTURE.read_text(encoding="utf-8").splitlines() if x.strip()]
    return RecordedDecider([x for x in lines if x.get("model") == MODEL])


class Asker:
    """Recordings first; on a miss one call to `fallback` (the capped live decider, or the dry
    stub), never retried. A recorded or live answer counts only when it comes from MODEL and
    answers every question asked. Counts calls and estimated dollars per arm, every failure
    and the question it hit (`ROW`), and the first stop and its kind."""

    def __init__(self, fallback: Any | None) -> None:
        self.recorded = recordings()
        self.fallback = fallback
        self.gate = asyncio.Semaphore(CONCURRENCY)
        self.memo: dict[str, Decision] = {}
        self.halted: list[tuple[str, str]] = []  # (kind, why)
        self.failures = 0
        self.failed_ids: set[str] = set()
        self.in_a_row = 0
        self.calls: dict[str, dict[str, float]] = {}

    def _count(self, arm: str, point: str, state: Any, qs: Mapping[str, Any]) -> None:
        pessimistic = estimate_usd(state, qs, price_per_mtok=0.042)
        row = self.calls.setdefault(arm, {"calls": 0, "pessimistic_usd": 0.0, "expected_usd": 0.0})
        row["calls"] += 1
        row[f"calls_{point}"] = row.get(f"calls_{point}", 0) + 1
        row["pessimistic_usd"] += pessimistic
        row["expected_usd"] += pessimistic * EXPECTED_FACTOR.get(point, 1.0)

    def _failed(self, point: str, why: str, kind: str | None = None) -> Decision:
        self.failures += 1
        self.failed_ids.add(ROW.get())
        self.in_a_row += 1
        if kind is None and self.in_a_row >= MAX_FAILURES_IN_A_ROW:
            kind = "failures"
        if kind is not None and not self.halted:
            self.halted.append((kind, why))
        return Decision(point, {}, "b6", "-", error=why)

    @staticmethod
    def complete(decision: Decision, qs: Mapping[str, Any]) -> bool:
        return all(not decision.answer(k).empty for k in qs)

    async def decide(self, arm: str, point: str, state: Any, qs: Mapping[str, Any]) -> Decision:
        key = key_of(point, state, qs)
        found = self.memo.get(key) or await self.recorded.decide(point, state, qs)
        if found.answers and found.model == MODEL and self.complete(found, qs):
            return found  # a partial recording is a miss: asked again, the new line wins
        if self.fallback is None:
            return self._failed(point, "not recorded, no live decider")
        async with self.gate:
            if self.halted:  # a stop met while this call waited: it is not made
                self.failures += 1
                self.failed_ids.add(ROW.get())
                return Decision(point, {}, "b6", "-", error=f"halted: {self.halted[0][1]}")
            self._count(arm, point, state, qs)
            try:
                decision = await self.fallback.decide(point, state, qs)
            except Exception as error:  # noqa: BLE001 - every failure is counted, none retried
                why = f"{type(error).__name__}: {error}"
                return self._failed(point, why, halt_kind(error))
        if decision.model != MODEL:
            self.halted.append(("pause", f"served {decision.model}, not {MODEL}"))
            raise SystemExit(f"asked {MODEL}, served {decision.model}: stopped")
        if decision.failed or not self.complete(decision, qs):
            return self._failed(point, decision.error or "partial answer")
        self.in_a_row = 0
        self.memo[key] = decision
        return decision


class ArmView:
    """What a Squire sees: the shared asker, tagged with the arm."""

    def __init__(self, asker: Asker, arm: str) -> None:
        self.asker, self.arm, self.name = asker, arm, "jev"

    async def decide(self, point: str, state: Any, qs: Mapping[str, Any]) -> Decision:
        return await self.asker.decide(self.arm, point, state, qs)


def squire(asker: Asker, arm: str, cap: float) -> Squire:
    loose = replace(Thresholds(), max_decisions=10**7, max_usd=cap)
    return Squire(ArmView(asker, arm), thresholds=loose)


# ---- arms --------------------------------------------------------------------------------


def needs_own_call(row: Mapping[str, Any], arm: str) -> bool:
    return arm != "D-es90" or len(row["es"]["pages"]) > sc.CONSUMER_PRESELECT


def arm_order(position: int, arms: Sequence[str]) -> list[str]:
    """Spanish and English alternate first with the question's launch position."""
    return list(arms) if position % 2 == 0 else list(arms)[::-1]


async def ask_pages(rows: Sequence[Mapping[str, Any]], asker: Asker, cap: float) -> list[dict]:
    squires = {arm: squire(asker, arm, cap) for arm in an.PAGE_ARMS}

    async def one(position: int, row: Mapping[str, Any]) -> dict[str, Any]:
        ROW.set(str(row["id"]))
        out: dict[str, Any] = {"id": row["id"]}
        for arm in arm_order(position, an.PAGE_ARMS):
            lang = sc.lang_of(arm)
            got = await squires[arm].triage_pages(
                purpose=row[lang]["question"], pages=sc.page_texts(row, lang)
            )
            out[arm] = [[keep, p] for keep, p in got]
        return out

    return await shuffled(one, rows)


async def ask_docs(rows: Sequence[Mapping[str, Any]], asker: Asker, cap: float) -> list[dict]:
    squires = {arm: squire(asker, arm, cap) for arm in an.DOC_ARMS}

    async def one(position: int, row: Mapping[str, Any]) -> dict[str, Any]:
        ROW.set(str(row["id"]))
        out: dict[str, Any] = {"id": row["id"]}
        for arm in arm_order(position, an.DOC_ARMS):
            if not needs_own_call(row, arm):
                continue
            question, pages, _ = sc.doc_inputs(row, arm)
            got = await squires[arm].select_passages(purpose=question, pages=pages)
            out[arm] = [None if e is None else [[k, p] for k, p in e] for e in got]
        out.setdefault("D-es90", out["D-es"])
        return out

    return await shuffled(one, rows)


async def shuffled(one: Any, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`one(position, row)` for every row in a seeded launch order; results in row order."""
    order = list(range(len(rows)))
    random.Random(bb.SEED).shuffle(order)
    done = await asyncio.gather(*(one(rank, rows[i]) for rank, i in enumerate(order)))
    by_index = dict(zip(order, done, strict=True))
    return [by_index[i] for i in range(len(rows))]


ASK = {"pages": ask_pages, "docs": ask_docs}


# ---- inputs and the seal -----------------------------------------------------------------


def load_rows(data: Path, name: str, n: int | None = None) -> list[dict[str, Any]]:
    path = data / f"{name}.jsonl"
    manifest = json.loads((OUT / "bench-manifest.json").read_text(encoding="utf-8"))
    if bb.sha256_of(path) != manifest[name]["sha256"]:
        raise SystemExit(f"{path} is not the file in the manifest: rebuild with b6_build.py")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    return rows if n is None else rows[:n]


LAUNCHER = "b6-es-run.cmd"
# The launcher's three local values, read as their placeholders: the repository holds the
# placeholders, an untracked filled copy runs, and both hash alike.
LOCAL_VALUES = {"PY": "<PYTHON>", "SANCHOPANZA_KEYS_ENV": "<KEYS_ENV_PATH>", "WT": "<WORKTREE>",
                "SANCHOPANZA_B6_DATA": "<DATA_DIR>"}  # fmt: skip
_LOCAL_LINE = re.compile(
    r'^(set "(PY|SANCHOPANZA_KEYS_ENV|WT|SANCHOPANZA_B6_DATA)=)[^"\n]*(")', re.MULTILINE
)


def launcher_text(path: Path) -> bytes:
    """The launcher with LF line ends and its local values back to their placeholders."""
    text = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    return _LOCAL_LINE.sub(lambda m: f"{m[1]}{LOCAL_VALUES[m[2]]}{m[3]}", text).encode()


def sealed_files() -> list[str]:
    package = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "src").rglob("*.py"))
    return [*SEALED, *package]


def digest() -> str:
    """sha256 over `path NUL content` of every sealed file, text read with LF line ends and
    the launcher's local values as placeholders (`launcher_text`)."""
    h = hashlib.sha256()
    for name in sealed_files():
        path = REPO / name
        body = (
            launcher_text(path) if name == LAUNCHER else path.read_bytes().replace(b"\r\n", b"\n")
        )
        h.update(name.encode() + b"\0" + body)
    return h.hexdigest()


def require_launcher(path: Path | None) -> None:
    """A live run starts from the sealed launcher, or a copy differing only in local values."""
    if path is None or not path.is_file():
        raise SystemExit("a live run starts from b6-es-run.cmd (--launcher): nothing spent")
    if launcher_text(path) != launcher_text(REPO / LAUNCHER):
        raise SystemExit(f"{path} differs from the sealed launcher beyond its local values")


def seal() -> str:
    """Write the seal, once: refused when one exists or any answer is already recorded."""
    if SEAL.exists():
        raise SystemExit("already sealed: a new seal is an amendment, written by hand")
    if FIXTURE.exists() and FIXTURE.stat().st_size:
        raise SystemExit(f"{FIXTURE.name} already holds answers: no seal after data")
    value = digest()
    SEAL.write_bytes((value + "\n").encode())
    return value


def require_seal() -> None:
    if not SEAL.exists() or SEAL.read_text(encoding="utf-8").split()[0] != digest():
        raise SystemExit(
            "prereg.md, the code or the manifest changed since the seal: nothing spent"
        )


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def require_seal_in_head() -> None:
    """The seal is a tracked file: with a clean tree it is the one HEAD holds. An untracked
    seal would let an unsealed tree seal itself and launch with a fresh launch count."""
    try:
        git("ls-files", "--error-unmatch", SEAL.relative_to(REPO).as_posix())
    except (subprocess.CalledProcessError, ValueError) as error:
        raise SystemExit("prereg.sha256 is not committed: launch from the sealed commit") from error


def require_seal_commit() -> str:
    """HEAD is the seal commit: one parent, and its only change is prereg.sha256, so a seal
    commit cannot carry code. Returns the parent, the instrument the seal hashes."""
    seal = SEAL.relative_to(REPO).as_posix()
    commits = git("rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(commits) != 2:
        raise SystemExit("HEAD is not a seal commit with one parent: launch from the seal commit")
    changed = git("diff", "--name-only", "HEAD^", "HEAD").splitlines()
    if changed != [seal]:
        raise SystemExit(f"the seal commit changes {changed}, not only {seal}: nothing spent")
    return commits[1]


def require_clean_tree() -> str:
    """The commit a live launch runs from; refused when a tracked file differs from it."""
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked files differ from HEAD: launch from the sealed commit only")
    return git("rev-parse", "HEAD")


# ---- launches ----------------------------------------------------------------------------


def launches(bench: str, value: str) -> list[dict[str, Any]]:
    """This bench's launches under this seal: `{"id", "outcome"}`, "started" while unfinished."""
    path = RUN_DIR / "launches.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x] \
        if path.exists() else []  # fmt: skip
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("bench") == bench and row.get("digest") == value:
            out.setdefault(row["id"], {"id": row["id"], "outcome": "started"})
            out[row["id"]].update({k: v for k, v in row.items() if k in ("outcome", "failed_ids")})
    return list(out.values())


def record_launch(row: Mapping[str, Any]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    with (RUN_DIR / "launches.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def counted(history: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Launches that count against MAX_LAUNCHES: incomplete ones, and any never finished."""
    return [h for h in history if h["outcome"] in ("incomplete", "started")]


def launch_gate(bench: str, value: str) -> None:
    """The relaunch rule (prereg): a complete bench is replayed, never asked again; a cap
    reached ends it until a sealed amendment; after MAX_LAUNCHES counted launches the bench is
    terminal, "no verdict". A pause (401/402/403/429/5xx, no connection) is not a launch. The
    docs bench waits for the pages bench to be complete or terminal; a pages bench ended by its
    cap blocks docs too, until a sealed amendment."""
    history = launches(bench, value)
    outcomes = {h["outcome"] for h in history}
    if "complete" in outcomes:
        raise SystemExit(f"{bench} is complete: replay it, free, without --live")
    if "cap" in outcomes:
        raise SystemExit(f"{bench} reached its cap: raising it is a sealed amendment")
    if len(counted(history)) >= MAX_LAUNCHES:
        raise SystemExit(f"{bench} is terminal after {MAX_LAUNCHES} launches: no verdict")
    if bench == "docs":
        pages = launches("pages", value)
        if any(h["outcome"] == "cap" for h in pages):
            raise SystemExit("the pages bench ended at its cap: docs waits for a sealed amendment")
        done = any(h["outcome"] == "complete" for h in pages)
        if not done and len(counted(pages)) < MAX_LAUNCHES:
            raise SystemExit("the pages bench runs first, to completion (prereg)")


def outcome_of(asker: Asker) -> str:
    if asker.halted and asker.halted[0][0] in ("cap", "pause"):
        return asker.halted[0][0]
    return "incomplete" if asker.failures else "complete"


# ---- live --------------------------------------------------------------------------------


def load_key() -> None:
    """TYPESAFE_API_KEY into this process's environment from SANCHOPANZA_KEYS_ENV if unset."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    if not named or not Path(named).is_file():
        raise SystemExit("TYPESAFE_API_KEY unset and SANCHOPANZA_KEYS_ENV names no file")
    for line in Path(named).read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition("=")
        if name.strip() == "TYPESAFE_API_KEY" and value.strip():
            os.environ["TYPESAFE_API_KEY"] = value.strip().strip('"').strip("'")
            return
    raise SystemExit("no TYPESAFE_API_KEY line in the file SANCHOPANZA_KEYS_ENV names")


def preflight() -> None:
    """One call, its own client in its own event loop, closed before the run's loop starts."""
    from sanchopanza.providers.jev import apreflight

    result = asyncio.run(apreflight(model=MODEL))
    if not result.ok or result.model != MODEL:
        raise SystemExit(f"preflight {MODEL}: {result.reason}, served {result.model}")


def make_live(batch: str, cap: float) -> Any:
    """The capped, recording Jev decider. Called inside the run's one event loop: Jev's HTTP
    client belongs to the loop that first uses it, and a second `asyncio.run` with the same
    client fails every call ("Event loop is closed")."""
    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers import CappedDecider, jev
    from sanchopanza.providers.jev import JevDecider
    from sanchopanza.providers.recorded import RecordingDecider

    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})  # a 429 pauses the run; 529 keeps retries
    ledger = SpendLedger(RUN_DIR / "ledger.json", cap_usd=LEDGER_CAP_USD)
    inner = JevDecider(model=MODEL, long_context=False, images=False, timeout_s=TIMEOUT_S)
    return RecordingDecider(CappedDecider(inner, ledger=ledger, batch=batch, max_usd=cap), FIXTURE)


# ---- dry and power -----------------------------------------------------------------------


def upper_bound(bench: str, rows: Sequence[Mapping[str, Any]]) -> int:
    """Calls if every page passed every cut: one call a page set; per article, its groups of
    30 (the first round stalls) plus one sentence call per paragraph sent."""
    if bench == "pages":
        return 2 * len(rows)
    calls = 0
    for row in rows:
        for arm in an.DOC_ARMS:
            if needs_own_call(row, arm):
                n = len(sc.doc_inputs(row, arm)[1])
                calls += (1 if n <= 30 else -(-n // 30)) + n
    return calls


def bench_rows(data: Path, bench: str, smoke: bool = False) -> list[dict[str, Any]]:
    if smoke:
        return load_rows(data, f"smoke-{bench}")
    return load_rows(data, bench, N_PAGES if bench == "pages" else N_DOCS)


def dry(data: Path, benches: Sequence[str] = BENCHES) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for bench in benches:
        rows = bench_rows(data, bench)
        asker = Asker(Stub())
        asyncio.run(ASK[bench](rows, asker, 1e9))
        total = {k: round(sum(a[k] for a in asker.calls.values()), 4)
                 for k in ("calls", "pessimistic_usd", "expected_usd")}  # fmt: skip
        total["median_71u_usd"] = round(total["calls"] * MEDIAN_USD, 4)
        report[bench] = {
            "questions": len(rows),
            "by_arm": {
                a: {k: round(v, 4) for k, v in c.items()} for a, c in sorted(asker.calls.items())
            },  # fmt: skip
            "jev": total,
            "upper_bound_calls": upper_bound(bench, rows),
            "cap_usd": BATCH_CAP_USD[bench],
            "fits_under_cap": total["pessimistic_usd"] <= BATCH_CAP_USD[bench],
        }
        if bench == "docs":
            report[bench]["over_90_paragraphs_es"] = sum(needs_own_call(r, "D-es90") for r in rows)
    report["claude_usd"] = 0.0
    return report


def power(data: Path) -> dict[str, Any]:
    """The questions needed, and free proxies of the Spanish-English disagreement: BM25 at a
    third of the pages' text, and BM25 over sentences at a fifth of an article."""
    pages = bench_rows(data, "pages")
    docs = bench_rows(data, "docs")
    seen = [r for r in pages if sc.answer_in_view(r, "es") and sc.answer_in_view(r, "en")]
    third = {lang: [sc.bm25_pages_at(r, lang, sum(len(x) for _, x in r[lang]["pages"]) // 3)
                    for r in seen] for lang in ("es", "en")}  # fmt: skip
    fifth = {lang: [sc.bm25_sentences_at(r, lang, sum(len(t) for _, t in r[lang]["pages"]) // 5)
                    for r in docs] for lang in ("es", "en")}  # fmt: skip
    return {
        "rows": {"pages": len(pages), "pages_primary": len(seen), "docs": len(docs)},
        "table": sc.power_table(
            [0.03, 0.05, 0.10, 0.16, 0.20, 0.23], [len(seen), 400, len(docs)]
        ),  # fmt: skip
        "proxy_pages_bm25_third": sc.describe(third["es"], third["en"]),
        "proxy_docs_bm25_fifth": sc.describe(fifth["es"], fifth["en"]),
    }


# ---- run ---------------------------------------------------------------------------------


def spent_in(batch: str) -> float:
    """What the ledger already counts for `batch` (settled calls, open reservations)."""
    from sanchopanza.budget import SpendLedger

    return SpendLedger(RUN_DIR / "ledger.json", cap_usd=LEDGER_CAP_USD).spent(batch)


def versions() -> dict[str, str]:
    """The interpreter and HTTP client a launch ran with, for its row in launches.jsonl."""
    try:
        import httpx

        client = str(httpx.__version__)
    except ImportError:
        client = "absent"
    return {"python": sys.version, "httpx": client}


def run(data: Path, bench: str, *, live: bool, smoke: bool, launcher: Path | None = None) -> int:
    rows = bench_rows(data, bench, smoke)
    cap = SMOKE_CAP_USD if smoke else BATCH_CAP_USD[bench]
    batch = f"b6-es-{'smoke-' if smoke else ''}{bench}"
    value = launch_id = head = parent = ""
    if live:
        require_seal()
        require_launcher(launcher)
        head = require_clean_tree()
        require_seal_in_head()
        parent = require_seal_commit()
        value = digest()
        if not smoke:
            launch_gate(bench, value)
            room = cap - spent_in(batch)
            plan = dry(data, [bench])[bench]
            if plan["jev"]["pessimistic_usd"] > room:
                raise SystemExit(f"what is left to ask does not fit in the {room:.4f} USD left")
        load_key()  # before the preflight, which needs it
        preflight()
        launch_id = uuid.uuid4().hex
        if not smoke:
            record_launch({"id": launch_id, "bench": bench, "digest": value, "head": head,
                           "instrument": parent, "at": time.time(), **versions()})  # fmt: skip

    async def ask() -> tuple[Asker, list[dict]]:
        asker = Asker(make_live(batch, cap) if live else None)  # inside this loop, only this one
        return asker, await ASK[bench](rows, asker, cap)

    asker, out = asyncio.run(ask())
    spent = {a: {k: round(v, 4) for k, v in c.items()} for a, c in asker.calls.items()}
    status = {"bench": bench, "live_calls_by_arm": spent, "failures": asker.failures,
              "halted": asker.halted[:1], "failed_ids": sorted(asker.failed_ids)}  # fmt: skip
    print(json.dumps(status), file=sys.stderr)
    if live and not smoke:
        ended = {"outcome": outcome_of(asker), "failed_ids": sorted(asker.failed_ids)}
        record_launch({"id": launch_id, "bench": bench, "digest": value, **ended})
    if asker.failures or asker.halted:
        history = launches(bench, value or digest()) if not smoke else []
        if len(counted(history)) >= MAX_LAUNCHES:
            last = history[-1].get("failed_ids", sorted(asker.failed_ids))
            print(f"TERMINAL, no verdict for {bench}: unanswered questions {last}", file=sys.stderr)
        else:
            print("INCOMPLETE: unanswered calls or a stop; nothing scored", file=sys.stderr)
        return 1
    if smoke:
        return 0
    report = (an.pages_report(rows, out) if bench == "pages"
              else an.docs_report(rows, out, load_rows(data, "docs")))  # fmt: skip
    report["head"] = head or "replay"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"analysis-{bench}.json").write_bytes((json.dumps(report, indent=1) + "\n").encode())
    print(json.dumps(report, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=bb.DEFAULT_DATA)
    ap.add_argument("--bench", choices=BENCHES)
    ap.add_argument("--launcher", type=Path, help="the .cmd this run was started from")
    for flag in ("--dry", "--power", "--seal", "--live", "--smoke"):
        ap.add_argument(flag, action="store_true")
    args = ap.parse_args()
    if args.seal:
        print(seal())
        return 0
    if args.dry:
        print(json.dumps(dry(args.data, [args.bench] if args.bench else BENCHES), indent=1))
        return 0
    if args.power:
        print(json.dumps(power(args.data), indent=1))
        return 0
    if not args.bench:
        raise SystemExit("--bench pages|docs: one bench a run, pages first")
    return run(args.data, args.bench, live=args.live, smoke=args.smoke, launcher=args.launcher)


if __name__ == "__main__":
    raise SystemExit(main())
