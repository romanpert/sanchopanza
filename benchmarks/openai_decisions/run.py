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
import random
import sys
from collections.abc import Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import paid_once  # noqa: E402

from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.contract import Decision, Truth  # noqa: E402
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
MARGIN = -0.05  # OpenAI minus Jev, share of the 245 cases right under the shipped policy
BOOT_DRAWS = 10_000
BOOT_SEED = 20261016
PREFLIGHT_STATE = "A launcher checks that the decision service answers before a paid run."
PREFLIGHT_QUESTION = "Is this text about checking that a service answers?"

LOT = paid_once.Lot(
    name="openai-decisions",
    prereg=RESULTS / "prereg.md",
    launcher=ROOT / "openai-decisions-run.cmd",
    fixture=ROOT / "fixtures" / "openai-decisions" / "public-benches.jsonl",
    model=od.DEFAULT_MODEL,
    cap_usd=0.10,
    instrument=(
        "benchmarks/openai_decisions/run.py",
        "benchmarks/paid_once.py",
        "src/sanchopanza/providers/openai_decisions.py",
        "src/sanchopanza/providers/capped.py",
        "src/sanchopanza/providers/recorded.py",
        "src/sanchopanza/eval/bench.py",
        "src/sanchopanza/points",
        "src/sanchopanza/policy.py",
        "benches/core.jsonl",
        "benches/safety.jsonl",
        "benches/graph.jsonl",
        "fixtures/public-benches.jsonl",
    ),
    price_per_mtok=od.DEFAULT_PRICE_PER_MTOK,
    model_prefix=True,
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


async def preflight(model: str) -> None:  # pragma: no cover - one real decision, cents of a cent
    """One predicate through the lot's own ledger, in the caller's loop: the service answers,
    with a model of the lot's name, before anything is asked."""
    client = od.OpenAIDecisionsClient()
    try:
        capped = CappedDecider(
            client,
            ledger=SpendLedger(LOT.ledger, cap_usd=LOT.cap_usd),
            batch=f"{LOT.name}-preflight",
            max_usd=LOT.cap_usd,
            price_per_mtok=LOT.price_per_mtok,
        )
        decision = await capped.decide(
            "preflight", PREFLIGHT_STATE, {"ok": Truth(PREFLIGHT_QUESTION)}
        )
    finally:
        await client.aclose()
    if decision.answer("ok").empty or not LOT.serves(decision.model):
        raise SystemExit(f"preflight: no usable answer from {model} (served {decision.model})")
    print(json.dumps({"preflight": "ok", "served": decision.model, "usd": decision.cost_usd}))


def live() -> Any:  # pragma: no cover - builds the real client
    return od.OpenAIDecisionsClient()


# --- report ---------------------------------------------------------------------------------


def _rows(decider: Any) -> list[Row]:
    results = asyncio.run(run_bench(load_cases(BENCHES), decider, concurrency=1))
    return [r for r in results if isinstance(r, Row)]


def openai_recording() -> RecordedDecider:
    return paid_once.recorded(LOT)


def right(row: Row) -> bool:
    return bool(row.decided and row.correct)


def paired(a: Sequence[bool], b: Sequence[bool]) -> dict[str, Any]:
    """`a` minus `b`, share of cases right: exact McNemar and a paired bootstrap 95 % interval."""
    n = len(a)
    only_a, only_b, p = stats.mcnemar(a, b)
    diff = (sum(a) - sum(b)) / n
    rng = random.Random(BOOT_SEED)
    draws = []
    for _ in range(BOOT_DRAWS):
        idx = [rng.randrange(n) for _ in range(n)]
        draws.append(sum(a[i] - b[i] for i in idx) / n)
    draws.sort()
    lo, hi = draws[int(0.025 * BOOT_DRAWS)], draws[int(0.975 * BOOT_DRAWS) - 1]
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
    jev = _rows(create("recorded", path=str(JEV_FIXTURE)))
    oai = _rows(openai_recording())
    by_id = {r.id: r for r in jev}
    pairs = [(o, by_id[o.id]) for o in oai if o.id in by_id]
    if len(pairs) != len(jev) or len(oai) != len(jev):
        raise SystemExit(
            f"cases do not pair: {len(oai)} OpenAI, {len(jev)} Jev, {len(pairs)} paired"
        )
    primary = paired([right(o) for o, _ in pairs], [right(j) for _, j in pairs])
    missing = len(asyncio.run(paid_once._missing(queries(), LOT)))
    out = {
        "primary": {**primary, "margin": MARGIN, "verdict": verdict(*primary["ci95"])},  # fmt: skip
        "queries_unanswered_in_recording": missing,
        "openai": summarize(oai),
        "jev": summarize(jev),
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
    result = paid_once.run_paid(
        LOT,
        queries(),
        load_key=functools.partial(paid_once.load_key, "OPENAI_API_KEY"),
        make_live=live,
        check=preflight,
    )
    print(json.dumps(result, indent=1, default=str))
    return 0 if result["stopped"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
