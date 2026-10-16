"""D1: OpenAI's Decisions API as a provider, on the public benches, against Jev's recording.

Pre-registered in `docs/results/2026-10-16-openai-decisions/prereg.md`.

    python benchmarks/openai_decisions/run.py dry      # free: the 301 queries, priced
    python benchmarks/openai_decisions/run.py seal     # sha256 of prereg.md and the launcher, once
    python benchmarks/openai_decisions/run.py paid     # OpenAI, through openai-decisions-run.cmd
    python benchmarks/openai_decisions/run.py report   # free once recorded: the verdict

The public benches (core, safety, graph: 245 cases) ask 301 distinct queries whatever the
answers (checked: the same set under null answers and under Jev's recording), so the lot is a
fixed list asked once through `paid_once.run_paid`: the seal, the instrument commit, the cap in
the lot's own ledger, one launch and one relaunch at most, never after a 402, a 429 or the cap.
The live client is `OpenAIDecisionsClient`; `run_paid` puts it behind `CappedDecider` on the
lot's ledger at OpenAI's price. The key is `OPENAI_API_KEY`, read from the file
SANCHOPANZA_KEYS_ENV names (the launcher's copy only), never printed.

`report` replays the bench twice, free: Jev from `fixtures/public-benches.jsonl` (jev-1.13.0, the
public run) and OpenAI from this lot's recording, under the shipped policy and thresholds, and
pairs the cases.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import paid_once  # noqa: E402

from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.contract import Choice, Decision, Score, Truth  # noqa: E402
from sanchopanza.eval import stats  # noqa: E402
from sanchopanza.eval.bench import Row, load_cases, run_bench, summarize  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers import openai_decisions as od  # noqa: E402
from sanchopanza.providers.capped import CappedDecider  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, key_of  # noqa: E402

BENCHES = tuple(ROOT / "benches" / f"{n}.jsonl" for n in ("core", "safety", "graph"))
JEV_FIXTURE = ROOT / "fixtures" / "public-benches.jsonl"
RESULTS = ROOT / "docs" / "results" / "2026-10-16-openai-decisions"
QUERIES = 301
MARGIN = -0.05  # OpenAI minus Jev, share of the 244 rows right under the shipped policy
BOOT_DRAWS = 10_000
BOOT_SEED = 20261016
PREFLIGHT_STATE = "A launcher checks that the decision service answers before a paid run."
PREFLIGHT_QUESTIONS = {
    "ok": Truth("Is this text about checking that a service answers?"),
    "kind": Choice(
        "What kind of text is this?",
        {"operations": "running or checking a system", "fiction": "a story"},
    ),
    "urgency": Score("How urgent does the text sound?", ["not urgent", "somewhat", "very"]),
}
TIMEOUT_S = 60.0
# Decisions in a row with no usable answer at all that stop the run: more than the longest run of
# one point's queries (94 dependency), so a provider refusing a whole point does not stop it.
EMPTY_STREAK = 100

LOT = paid_once.Lot(
    name="openai-decisions",
    prereg=RESULTS / "prereg.md",
    launcher=ROOT / "openai-decisions-run.cmd",
    fixture=ROOT / "fixtures" / "openai-decisions" / "public-benches.jsonl",
    model=od.DEFAULT_MODEL,
    cap_usd=0.10,
    instrument=(
        "src",
        "benchmarks/openai_decisions/run.py",
        "benchmarks/paid_once.py",
        "benches/core.jsonl",
        "benches/safety.jsonl",
        "benches/graph.jsonl",
        "fixtures/public-benches.jsonl",
    ),
    price_per_mtok=od.DEFAULT_PRICE_PER_MTOK,
    snapshot=r"\d{4}-\d{2}-\d{2}",
    empty_streak=EMPTY_STREAK,
)


class _Capture:
    """Records each query the bench asks and answers nothing (the bench's policies then fall to
    their defaults); the set of queries does not depend on the answers."""

    name = "capture"

    def __init__(self) -> None:
        self.queries: dict[str, tuple[str, Any, Any]] = {}

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.queries.setdefault(key_of(point, state, questions), (point, state, questions))
        return Decision(point=point, answers={}, provider=self.name, model="-")


def queries() -> list[tuple[str, Any, Any]]:
    capture = _Capture()
    asyncio.run(run_bench(load_cases(BENCHES), capture, concurrency=1))
    asks = list(capture.queries.values())
    if len(asks) != QUERIES:
        raise SystemExit(f"the benches ask {len(asks)} queries, not the registered {QUERIES}")
    return asks


# --- live: preflight and client -------------------------------------------------------------


PLANNED: dict[str, float] = {}  # the run's estimated total, set by `main` before run_paid


def check_preflight(decision: Decision, estimate_usd: float, planned_usd: float, spent_usd: float,
                    cap_usd: float) -> dict[str, Any]:  # fmt: skip
    """The preflight's rule, free: every type answered, a token count reported, and the run's
    estimate scaled by this call's real/estimated ratio still under the cap."""
    missing = [k for k in PREFLIGHT_QUESTIONS if decision.answer(k).empty]
    if missing or not LOT.serves(decision.model):
        raise SystemExit(f"preflight: no usable answer to {missing} (served {decision.model})")
    if decision.input_tokens <= 0:
        raise SystemExit("preflight: no input token count came back; the ledger could not bound "
                         "what is billed")  # fmt: skip
    ratio = max(1.0, decision.cost_usd / estimate_usd) if estimate_usd > 0 else 1.0
    projected = spent_usd + planned_usd * ratio
    if projected > cap_usd:
        raise SystemExit(f"preflight: the run projects {projected:.4f} USD at {ratio:.2f}x the "
                         f"estimate, over the {cap_usd} cap")  # fmt: skip
    return {"preflight": "ok", "served": decision.model, "usd": decision.cost_usd,
            "ratio": round(ratio, 3), "projected_usd": round(projected, 6)}  # fmt: skip


async def preflight(model: str) -> None:  # pragma: no cover - one real decision, cents of a cent
    """One call with a predicate, a choice and a score through the lot's own ledger, in the
    caller's loop, before anything is asked (`check_preflight`)."""
    client = od.OpenAIDecisionsClient(timeout_s=TIMEOUT_S)
    ledger = SpendLedger(LOT.ledger, cap_usd=LOT.cap_usd)
    try:
        capped = CappedDecider(
            client,
            ledger=ledger,
            batch=f"{LOT.name}-preflight",
            max_usd=LOT.cap_usd,
            price_per_mtok=LOT.price_per_mtok,
        )
        decision = await capped.decide("preflight", PREFLIGHT_STATE, PREFLIGHT_QUESTIONS)
    finally:
        await client.aclose()
    estimate = od.estimate_usd(PREFLIGHT_STATE, PREFLIGHT_QUESTIONS)
    print(json.dumps(check_preflight(decision, estimate, PLANNED.get("usd", 0.0), ledger.spent(),
                                     LOT.cap_usd)))  # fmt: skip


def live() -> Any:  # pragma: no cover - builds the real client
    return od.OpenAIDecisionsClient(timeout_s=TIMEOUT_S)


# --- report ---------------------------------------------------------------------------------


def _rows(decider: Any) -> list[Row]:
    results = asyncio.run(run_bench(load_cases(BENCHES), decider, concurrency=1))
    return [r for r in results if isinstance(r, Row)]


class _Watch:
    """Passes decisions through and notes whether any question asked had no usable answer."""

    name = "watch"

    def __init__(self, inner: Any) -> None:
        self.inner, self.short = inner, False

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        decision = await self.inner.decide(point, state, questions)
        self.short = self.short or not paid_once.complete(decision, questions)
        return decision


def flagged_rows(decider: Any) -> list[tuple[Row, bool]]:
    """Each case's rows with whether any of its queries lacked a usable answer, one case at a
    time so a flag belongs to its own case."""
    out: list[tuple[Row, bool]] = []
    for case in load_cases(BENCHES):
        watch = _Watch(decider)
        results = asyncio.run(run_bench([case], watch, concurrency=1))
        out += [(r, watch.short) for r in results if isinstance(r, Row)]
    return out


def openai_recording() -> RecordedDecider:
    return paid_once.recorded(LOT)


def right(row: Row) -> bool:
    return bool(row.decided and row.correct)


def paired(a: Sequence[bool], b: Sequence[bool]) -> dict[str, Any]:
    """`a` minus `b`, share of cases right: exact McNemar and a paired bootstrap 95 % interval
    (`stats.bootstrap_difference`: draws 250 and 9,749 of the 10,000 sorted)."""
    n = len(a)
    only_a, only_b, p = stats.mcnemar(a, b)
    diff, lo, hi = stats.bootstrap_difference(a, b, replicas=BOOT_DRAWS, seed=BOOT_SEED)
    return {"n": n, "a_right": sum(a), "b_right": sum(b), "only_a": only_a, "only_b": only_b,
            "mcnemar_p": p, "difference": diff, "ci95": [lo, hi]}  # fmt: skip


def verdict(lo: float, hi: float, margin: float = MARGIN) -> str:
    """The sealed rule, unrounded: "mejor" above 0, "no peor" above the margin, "peor" when the
    whole interval is under it, else "no concluyente"."""
    if lo > 0:
        return "mejor"
    if lo > margin:
        return "no peor"
    if hi < margin:
        return "peor"
    return "no concluyente"


def report() -> dict[str, Any]:
    missing_queries = len(asyncio.run(paid_once._missing(queries(), LOT)))
    if paid_once.unanswered_blocks(LOT, missing_queries):
        raise SystemExit(f"{missing_queries} queries not yet asked and a launch is still allowed")
    jev = flagged_rows(create("recorded", path=str(JEV_FIXTURE)))
    oai = flagged_rows(openai_recording())
    by_id = {r.id: (r, f) for r, f in jev}
    pairs = [((o, fo), by_id[o.id]) for o, fo in oai if o.id in by_id]
    if len(pairs) != len(jev) or len(oai) != len(jev):
        raise SystemExit(
            f"cases do not pair: {len(oai)} OpenAI, {len(jev)} Jev, {len(pairs)} paired"
        )
    # A row any of whose questions got no usable answer is not right, whatever the default says.
    primary = paired(
        [right(o) and not fo for (o, fo), _ in pairs], [right(j) and not fj for _, (j, fj) in pairs]
    )
    out = {
        "primary": {
            **primary,
            "margin": MARGIN,
            "verdict": "no medido" if missing_queries else verdict(*primary["ci95"]),
        },  # fmt: skip
        "queries_not_asked": missing_queries,
        "rows_without_a_usable_answer": {
            "openai": sum(f for _, f in oai),
            "jev": sum(f for _, f in jev),
        },  # fmt: skip
        "served_models": sorted({o.model for o, _ in oai if o.model not in ("-", "code")}),
        "openai": summarize([o for o, _ in oai]),
        "jev": summarize([j for j, _ in jev]),
    }
    return out


def dry() -> dict[str, Any]:
    asks = queries()
    plan = paid_once.plan(asks, LOT)
    tokens = sum(od.estimate_usd(s, q) / od.DEFAULT_PRICE_PER_MTOK * 1e6 for _, s, q in asks)
    return {"head": paid_once.head(), "queries": len(asks), "estimated_tokens": round(tokens),
            **plan}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("dry", "seal", "paid", "report"))
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.action == "seal":
        print(paid_once.seal(LOT))
        return 0
    if args.action == "dry":
        print(json.dumps(dry(), indent=1))
        return 0
    if args.action == "report":
        result = report()
        (RESULTS / "analysis.json").write_text(json.dumps(result, indent=1, default=str) + "\n",
                                               "utf-8")  # fmt: skip
        print(json.dumps(result["primary"], indent=1))
        return 0
    asks = queries()
    todo = asyncio.run(paid_once._missing(asks, LOT))  # a relaunch is priced on what is left
    PLANNED["usd"] = sum(od.estimate_usd(s, q) for _, s, q in todo)
    result = paid_once.run_paid(
        LOT,
        asks,
        load_key=functools.partial(paid_once.load_key, "OPENAI_API_KEY"),
        make_live=live,
        check=preflight,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0 if result["stopped"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
