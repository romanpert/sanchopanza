"""B6: `triage_pages` and `select_passages` in Spanish against English, on the same questions.

    python -I benchmarks/b6_es/b6_run.py --dry       # free: the calls a live run would make, cost
    python -I benchmarks/b6_es/b6_run.py --power     # free: questions needed, free proxies
    python -I benchmarks/b6_es/b6_run.py --seal      # seal prereg.md, the code and the manifest
    python -I benchmarks/b6_es/b6_run.py --smoke --live   # 2 dev questions per bench, own cap
    python -I benchmarks/b6_es/b6_run.py --live      # spends: Jev only, caps in code
    python -I benchmarks/b6_es/b6_run.py             # replay of the recordings and analysis, free

Pre-registered in docs/results/2026-10-16-b6-es/prereg.md. The bench is built by `b6_build.py`
from MLQA v1.0 and Wikipedia (CC BY-SA) under `--data`, outside the repository.

Six arms, jev-1.13.0 (the production DEFAULT_MODEL, as in the English confirmations), shipped
thresholds and limits, no answering model:

- pages, `Squire.triage_pages` over ten pages: `P-es` (Spanish), `P-en` (the same questions and
  pages in English), `P-es900` (Spanish, each page cut to its first 900 characters before the
  call, the consumer's condition; a question whose pages are all 900 or shorter reuses P-es).
- docs, `Squire.select_passages` over a whole article: `D-es`, `D-en`, and `D-es90` (Spanish,
  past 90 paragraphs only the 90 best by BM25 are sent, the consumer's condition; an article of
  90 or fewer reuses D-es).

Every live call goes through `CappedDecider` on this bench's own ledger (LEDGER_PATH) and cap,
recorded in FIXTURE (hashed keys, no text), at most CONCURRENCY in flight, never retried. A cap
refusal or an outage (HTTP 401/402/403/429/5xx, no connection) stops every later call; any
unanswered call leaves the run INCOMPLETE and nothing is scored (a relaunch replays what was
paid and asks the rest). The key comes from TYPESAFE_API_KEY or the `.env` file
SANCHOPANZA_KEYS_ENV names (lot L4's `load_key`), inside the process, never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

import b6_build as bb  # noqa: E402
import b6_score as sc  # noqa: E402

from sanchopanza import Squire, Thresholds, truth  # noqa: E402
from sanchopanza.contract import Decision  # noqa: E402
from sanchopanza.providers.capped import estimate_usd  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, key_of  # noqa: E402
from sanchopanza.text import BM25Index  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-16-b6-es"
PREREG = OUT / "prereg.md"
SEAL = OUT / "prereg.sha256"
FIXTURE = REPO / "fixtures" / "b6-es.jsonl"
SEALED = ("docs/results/2026-10-16-b6-es/prereg.md",
          "docs/results/2026-10-16-b6-es/bench-manifest.json",
          "benchmarks/b6_es/b6_run.py", "benchmarks/b6_es/b6_score.py",
          "benchmarks/b6_es/b6_build.py", "benchmarks/b6_es/b6_wiki.py",
          "benchmarks/jev114/l4.py", "tests/test_b6_es.py")  # fmt: skip
# And every file of src/sanchopanza/**/*.py: the code measured is part of the seal.
MODEL = "jev-1.13.0"
RUN_DIR = Path(os.environ.get("SANCHOPANZA_B6_RUN", "C:/sp-runs/b6-es"))
LEDGER_PATH = RUN_DIR / "ledger.json"
N_PAGES = 300  # the pages questions asked: the whole built file (already in seeded order)
N_DOCS = 400  # the docs questions asked: the whole built file (prereg, Power)
BATCH, SMOKE_BATCH = "b6-es", "b6-es-smoke"
BATCH_CAP_USD = 4.00  # the run; `--dry` must fit its pessimistic estimate under it
SMOKE_CAP_USD = 0.10
LEDGER_CAP_USD = BATCH_CAP_USD + SMOKE_CAP_USD
CONCURRENCY = 4
TIMEOUT_S = 30.0
PAGE_ARMS = ("P-es", "P-es900", "P-en")
DOC_ARMS = ("D-es", "D-es90", "D-en")
MEDIAN_USD = 71e-6  # Jev's median per request (CLAUDE.md), quoted beside the size estimates
# Billed tokens against `estimate_usd`'s three characters a token, measured on the published
# HotpotQA fixtures (chunk_context 4,049 tokens, chunk_sentences 1,449): the reservation is
# pessimistic by these factors, and the expected cost is the reservation times them.
EXPECTED_FACTOR = {"triage_pages": 0.81, "select_sentences": 0.39}
# The dry stub's answers: in an in-context call the STUB_SURE best pages by BM25 at 0.9 (past
# the 0.75 gate), the next up to STUB_MAYBE at 0.5, the rest at 0.05. Fitted to QASPER, where Jev
# sent 8.1 paragraphs a question to the sentence stage (1,766 calls, 219 questions).
STUB_SURE, STUB_MAYBE = 8, 12
OUTAGE = frozenset({401, 402, 403, 429})
MAX_FAILURES_IN_A_ROW = 3  # of any kind (a timeout too): then every later call is refused


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
        return Decision(point, answers, "stub", "stub")


class Asker:
    """Recordings first; on a miss one call to `fallback` (the capped live decider, or the dry
    stub), never retried. Counts calls and estimated dollars per arm, and every failure."""

    def __init__(self, fallback: Any | None, *, live: bool) -> None:
        self.recorded = RecordedDecider.from_file(FIXTURE)
        self.fallback = fallback
        self.live = live
        self.gate = asyncio.Semaphore(CONCURRENCY)
        self.memo: dict[str, Decision] = {}
        self.halted: list[str] = []
        self.failures = 0
        self.in_a_row = 0
        self.calls: dict[str, dict[str, float]] = {}

    def _count(self, arm: str, point: str, state: Any, qs: Mapping[str, Any]) -> None:
        pessimistic = estimate_usd(state, qs, price_per_mtok=0.042)
        row = self.calls.setdefault(arm, {"calls": 0, "pessimistic_usd": 0.0, "expected_usd": 0.0})
        row["calls"] += 1
        row[f"calls_{point}"] = row.get(f"calls_{point}", 0) + 1
        row["pessimistic_usd"] += pessimistic
        row["expected_usd"] += pessimistic * EXPECTED_FACTOR.get(point, 1.0)

    def _failed(self, point: str, why: str, *, stop: bool = False) -> Decision:
        self.failures += 1
        self.in_a_row += 1
        if stop or self.in_a_row >= MAX_FAILURES_IN_A_ROW:
            self.halted.append(why)
        return Decision(point, {}, "b6", "-", error=why)

    async def decide(self, arm: str, point: str, state: Any, qs: Mapping[str, Any]) -> Decision:
        key = key_of(point, state, qs)
        found = self.memo.get(key) or await self.recorded.decide(point, state, qs)
        if found.answers:
            return found
        if self.fallback is None:
            return self._failed(point, "not recorded, no live decider")
        async with self.gate:
            if self.halted:  # a stop met while this call waited: it is not made
                self.failures += 1
                return Decision(point, {}, "b6", "-", error=f"halted: {self.halted[0]}")
            self._count(arm, point, state, qs)
            try:
                decision = await self.fallback.decide(point, state, qs)
            except Exception as error:  # noqa: BLE001 - every failure is counted, none retried
                return self._failed(point, f"{type(error).__name__}: {error}", stop=stops(error))
        if self.live and decision.model != MODEL:
            self.halted.append(f"served {decision.model}, not {MODEL}")
            raise SystemExit(f"asked {MODEL}, served {decision.model}: stopped")
        if decision.failed or not decision.answers:
            return self._failed(point, decision.error or "no answers")
        self.in_a_row = 0
        self.memo[key] = decision
        return decision


def stops(error: Exception) -> bool:
    """A cap refusal, or an outage a later call would meet too."""
    from sanchopanza.providers.capped import SpendCapReached

    if isinstance(error, SpendCapReached):
        return True
    found = re.search(r"HTTP (\d{3})", str(error))
    if found and (int(found.group(1)) in OUTAGE or int(found.group(1)) >= 500):
        return True
    return "unreachable" in str(error) and "Timeout" not in str(error)


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
    if arm == "P-es900":
        return any(len(x) > sc.CONSUMER_PAGE_CHARS for _, x in row["es"]["pages"])
    if arm == "D-es90":
        return len(row["es"]["pages"]) > sc.CONSUMER_PRESELECT
    return True


def arm_order(position: int, arms: Sequence[str]) -> list[str]:
    """Spanish and English alternate first with the question's launch position."""
    return list(arms) if position % 2 == 0 else list(arms)[::-1]


async def ask_pages(rows: Sequence[Mapping[str, Any]], asker: Asker, cap: float) -> dict:
    squires = {arm: squire(asker, arm, cap) for arm in PAGE_ARMS}

    async def one(position: int, row: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"id": row["id"]}
        for arm in arm_order(position, PAGE_ARMS):
            if not needs_own_call(row, arm):
                continue
            pages = sc.page_texts(row, arm)
            question = row[sc.lang_of(arm)]["question"]
            got = await squires[arm].triage_pages(purpose=question, pages=pages)
            out[arm] = [[keep, p] for keep, p in got]
        out.setdefault("P-es900", out["P-es"])
        return out

    return {"rows": await shuffled(one, rows)}


async def ask_docs(rows: Sequence[Mapping[str, Any]], asker: Asker, cap: float) -> dict:
    squires = {arm: squire(asker, arm, cap) for arm in DOC_ARMS}

    async def one(position: int, row: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"id": row["id"]}
        for arm in arm_order(position, DOC_ARMS):
            if not needs_own_call(row, arm):
                continue
            question, pages, _ = sc.doc_inputs(row, arm)
            got = await squires[arm].select_passages(purpose=question, pages=pages)
            out[arm] = [None if e is None else [[k, p] for k, p in e] for e in got]
        out.setdefault("D-es90", out["D-es"])
        return out

    return {"rows": await shuffled(one, rows)}


async def shuffled(one: Any, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`one(position, row)` for every row in a seeded launch order; results in row order."""
    order = list(range(len(rows)))
    random.Random(bb.SEED).shuffle(order)
    done = await asyncio.gather(*(one(rank, rows[i]) for rank, i in enumerate(order)))
    by_index = dict(zip(order, done, strict=True))
    return [by_index[i] for i in range(len(rows))]


# ---- inputs ------------------------------------------------------------------------------


def load_rows(data: Path, name: str, n: int | None = None) -> list[dict[str, Any]]:
    path = data / f"{name}.jsonl"
    manifest = json.loads((OUT / "bench-manifest.json").read_text(encoding="utf-8"))
    if bb.sha256_of(path) != manifest[name]["sha256"]:
        raise SystemExit(f"{path} is not the file in the manifest: rebuild with b6_build.py")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    return rows if n is None else rows[:n]


def sealed_files() -> list[str]:
    package = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "src").rglob("*.py"))
    return [*SEALED, *package]


def digest() -> str:
    """sha256 over `path NUL content` of every sealed file, text read with LF line ends."""
    h = hashlib.sha256()
    for name in sealed_files():
        h.update(name.encode() + b"\0" + (REPO / name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def require_seal() -> None:
    if not SEAL.exists() or SEAL.read_text(encoding="utf-8").split()[0] != digest():
        raise SystemExit(
            "prereg.md, the code or the manifest changed since the seal: nothing spent"
        )


# ---- dry ---------------------------------------------------------------------------------


def upper_bound(docs: Sequence[Mapping[str, Any]], pages: Sequence[Mapping[str, Any]]) -> int:
    """Calls if every page passed every cut: one call a page set; per article, its groups of
    30 (the first round stalls) plus one sentence call per paragraph sent."""
    calls = sum(1 + needs_own_call(r, "P-es900") for r in pages) + len(pages)
    for row in docs:
        for arm in DOC_ARMS:
            if needs_own_call(row, arm):
                n = len(sc.doc_inputs(row, arm)[1])
                calls += (1 if n <= 30 else -(-n // 30)) + n
    return calls


def dry(data: Path, n_pages: int, n_docs: int) -> dict[str, Any]:
    pages = load_rows(data, "pages", n_pages)
    docs = load_rows(data, "docs", n_docs)
    asker = Asker(Stub(), live=False)

    async def both() -> None:
        await ask_pages(pages, asker, 1e9)
        await ask_docs(docs, asker, 1e9)

    asyncio.run(both())
    total = {k: round(sum(a[k] for a in asker.calls.values()), 4)
             for k in ("calls", "pessimistic_usd", "expected_usd")}  # fmt: skip
    total["median_71u_usd"] = round(total["calls"] * MEDIAN_USD, 4)
    report = {
        "questions": {"pages": len(pages), "docs": len(docs)},
        "docs_over_90_paragraphs_es": sum(needs_own_call(r, "D-es90") for r in docs),
        "pages_with_a_page_over_900": sum(needs_own_call(r, "P-es900") for r in pages),
        "by_arm": {
            a: {k: round(v, 4) for k, v in c.items()} for a, c in sorted(asker.calls.items())
        },
        "jev_total": total,
        "jev_upper_bound_calls": upper_bound(docs, pages),
        "claude_usd": 0.0,
        "cap_usd": BATCH_CAP_USD,
        "fits_under_cap": total["pessimistic_usd"] <= BATCH_CAP_USD,
    }
    return report


# ---- analysis ----------------------------------------------------------------------------


def analyze(pages: list[dict], docs: list[dict], page_out: list[dict], doc_out: list[dict],
            all_docs: list[dict]) -> dict[str, Any]:  # fmt: skip
    ps = {arm: [sc.page_score(r, arm, o[arm]) for r, o in zip(pages, page_out, strict=True)]
          for arm in PAGE_ARMS}  # fmt: skip
    ds = {arm: [sc.doc_score(r, arm, sc.doc_mask(r, arm, o[arm]))
                for r, o in zip(docs, doc_out, strict=True)] for arm in DOC_ARMS}  # fmt: skip
    long_docs = [k for k, r in enumerate(docs) if needs_own_call(r, "D-es90")]
    hit = {arm: [s["hit"] for s in ps[arm]] for arm in PAGE_ARMS}
    gold = {arm: [s["all_gold"] for s in ds[arm]] for arm in DOC_ARMS}
    share = {arm: [s["kept_share"] for s in v] for arm, v in {**ps, **ds}.items()}
    report: dict[str, Any] = {
        "H1_pages_es_vs_en": {
            **sc.paired(hit["P-es"], hit["P-en"]),
            "text": sc.text_side(share["P-es"], share["P-en"]),
        },
        "H2_docs_es_vs_en": {
            **sc.paired(gold["D-es"], gold["D-en"]),
            "text": sc.text_side(share["D-es"], share["D-en"]),
            "any_gold": sc.paired(
                [s["any_gold"] for s in ds["D-es"]], [s["any_gold"] for s in ds["D-en"]]
            ),  # fmt: skip
        },
        "C1_pages_cut_900": {
            **sc.paired([s["delivered"] for s in ps["P-es900"]], hit["P-es"]),
            "answer_past_900": sum(r["es"]["answer_span"][1] > 900 for r in pages),
            "kept_share_of_full": round(
                sum(s["kept_share_of_full"] for s in ps["P-es900"]) / len(pages), 4
            ),
        },
        "C2_docs_bm25_90": {
            **(
                sc.paired(
                    [gold["D-es90"][k] for k in long_docs], [gold["D-es"][k] for k in long_docs]
                )
                if long_docs
                else {"n": 0}
            ),  # fmt: skip
            "preselection_keeps_gold_paragraph_all_built": sc.proportion(
                [x for r in all_docs if (x := sc.preselect_keeps_gold(r, "es")) is not None]
            ),
        },
        "anchors": {
            "pages_es": sc.proportion(hit["P-es"]),
            "pages_en": sc.proportion(hit["P-en"]),
            "docs_es": sc.proportion(gold["D-es"]),
            "docs_en": sc.proportion(gold["D-en"]),
            "published_english": sc.PUBLISHED,
        },  # fmt: skip
        "bm25_at_same_text": {
            "pages_es": sum(
                sc.bm25_pages_at(r, "P-es", s["kept_chars"])
                for r, s in zip(pages, ps["P-es"], strict=True)
            )
            / len(pages),
            "docs_es": sum(
                sc.bm25_sentences_at(r, "es", s["kept_chars"])
                for r, s in zip(docs, ds["D-es"], strict=True)
            )
            / len(docs),
        },  # fmt: skip
        "kept_share": {arm: round(sum(v) / len(v), 4) for arm, v in share.items()},
    }
    return report


def power(data: Path) -> dict[str, Any]:
    """The questions needed, and two free proxies of the Spanish-English disagreement: BM25 at
    a third of the pages' text, and BM25 over sentences at a fifth of an article."""
    pages = load_rows(data, "pages")
    docs = load_rows(data, "docs")
    third = {lang: [sc.bm25_pages_at(r, f"P-{lang}", sum(len(x) for _, x in r[lang]["pages"]) // 3)
                    for r in pages] for lang in ("es", "en")}  # fmt: skip
    fifth = {lang: [sc.bm25_sentences_at(r, lang, sum(len(t) for _, t in r[lang]["pages"]) // 5)
                    for r in docs] for lang in ("es", "en")}  # fmt: skip
    return {
        "table": sc.power_table([0.03, 0.05, 0.08, 0.10, 0.15, 0.20], [240, N_PAGES, N_DOCS]),
        "proxy_pages_bm25_third": sc.paired(third["es"], third["en"]),
        "proxy_docs_bm25_fifth": sc.paired(fifth["es"], fifth["en"]),
    }


# ---- live --------------------------------------------------------------------------------


def live_decider(batch: str, cap: float) -> Any:
    sys.path.insert(0, str(REPO / "benchmarks" / "jev114"))
    from l4 import load_key

    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers import CappedDecider, jev
    from sanchopanza.providers.jev import JevDecider
    from sanchopanza.providers.recorded import RecordingDecider

    jev.RETRYABLE = frozenset(jev.RETRYABLE - {429})  # a 429 stops the run; 529 keeps its retries
    load_key()
    ledger = SpendLedger(LEDGER_PATH, cap_usd=LEDGER_CAP_USD)
    inner = JevDecider(model=MODEL, long_context=False, images=False, timeout_s=TIMEOUT_S)
    return RecordingDecider(CappedDecider(inner, ledger=ledger, batch=batch, max_usd=cap), FIXTURE)


def preflight() -> None:
    from sanchopanza.providers.jev import apreflight

    result = asyncio.run(apreflight(model=MODEL))
    if not result.ok or result.model != MODEL:
        raise SystemExit(f"preflight {MODEL}: {result.reason}, served {result.model}")


def run(data: Path, *, live: bool, smoke: bool) -> int:
    prefix = "smoke-" if smoke else ""
    pages = load_rows(data, f"{prefix}pages", None if smoke else N_PAGES)
    docs = load_rows(data, f"{prefix}docs", None if smoke else N_DOCS)
    cap = SMOKE_CAP_USD if smoke else BATCH_CAP_USD
    fallback = None
    if live:
        require_seal()
        plan = dry(data, len(pages), len(docs)) if not smoke else None
        if plan is not None and not plan["fits_under_cap"]:
            raise SystemExit("the dry estimate does not fit under the cap: nothing spent")
        preflight()
        fallback = live_decider(SMOKE_BATCH if smoke else BATCH, cap)
    asker = Asker(fallback, live=live)

    async def both() -> tuple[dict, dict]:
        return await ask_pages(pages, asker, cap), await ask_docs(docs, asker, cap)

    page_out, doc_out = asyncio.run(both())
    spent = {a: {k: round(v, 4) for k, v in c.items()} for a, c in asker.calls.items()}
    print(json.dumps({"live_calls_by_arm": spent, "failures": asker.failures,
                      "halted": asker.halted[:1]}), file=sys.stderr)  # fmt: skip
    if asker.failures or asker.halted:
        print("INCOMPLETE: unanswered calls or a stop; nothing scored", file=sys.stderr)
        return 1
    if smoke:
        return 0
    all_docs = load_rows(data, "docs")
    report = analyze(pages, docs, page_out["rows"], doc_out["rows"], all_docs)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_bytes((json.dumps(report, indent=1) + "\n").encode())
    print(json.dumps(report, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=bb.DEFAULT_DATA)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--power", action="store_true")
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--n-pages", type=int, default=N_PAGES, help="--dry only: a what-if size")
    ap.add_argument("--n-docs", type=int, default=N_DOCS, help="--dry only: a what-if size")
    args = ap.parse_args()
    if args.seal:
        SEAL.write_bytes((digest() + "\n").encode())
        print(digest())
        return 0
    if args.dry:
        print(json.dumps(dry(args.data, args.n_pages, args.n_docs), indent=1))
        return 0
    if args.power:
        print(json.dumps(power(args.data), indent=1))
        return 0
    return run(args.data, live=args.live, smoke=args.smoke)


if __name__ == "__main__":
    raise SystemExit(main())
