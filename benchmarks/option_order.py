"""Does the order of a Choice's options move the answer? Measured on our own labelled cases.

    python benchmarks/option_order.py --offline                   # replay, free
    python benchmarks/option_order.py --env-file PATH/TO/.env  # asks only what is missing

Pre-registered on 2026-09-25 before the first call. An external study (jev-behavior-study,
432 arithmetic calls) reports 88 % accuracy with the correct option listed first and 57 %
with it last. Our `facts` point is a three-option Choice with 50 labelled cases and a recorded
answer in the shipped order (agree, conflict, unrelated), asked on 2026-09-24.

  H3. Reversing the order flips the top label on at most 2 of the 50 cases, and so does the
      rotation. A fourth arm asks the shipped order again on the day of the measurement, so
      the day-to-day drift of the provider is measured on the same cases and subtracted.
  Secondary: median and maximum |delta p| of the shipped top label; hits of the shipped policy
  (act at confidence >= 0.60) per order; mean probability mass on the first listed option.

Cost of the live run: 150 decisions, 0.0045 USD, all recorded to
`docs/results/2026-09-25-order/option-order.jsonl` with the order fingerprint (`order_of`),
which is what makes an order-sensitivity measurement replayable at all: `key_of` sorts keys
and cannot tell two orders apart on its own.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import statistics
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza import Thresholds  # noqa: E402
from sanchopanza.contract import Choice, Question  # noqa: E402
from sanchopanza.eval.bench import load_cases  # noqa: E402
from sanchopanza.points import entities  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-25-order"
FIXTURE = RESULTS / "option-order.jsonl"
SHIPPED = ("agree", "conflict", "unrelated")
ORDERS: dict[str, tuple[str, ...]] = {
    "shipped": SHIPPED,  # replayed from the repository's fixtures (2026-09-24)
    "reversed": ("unrelated", "conflict", "agree"),
    "rotated": ("conflict", "unrelated", "agree"),
    "today": SHIPPED,  # the shipped order asked again on the day of the measurement
}


def _key(env_file: str | None) -> str | None:
    key = os.environ.get("TYPESAFE_API_KEY")
    if key or not env_file:
        return key or None
    text = pathlib.Path(env_file).read_text(encoding="utf-8")
    match = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M)
    return match.group(1).strip().strip("'\"") if match else None


def _repository_recordings() -> RecordedDecider:
    entries: list[dict[str, Any]] = []
    for path in sorted((ROOT / "fixtures").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return RecordedDecider(entries)


def reordered(questions: dict[str, Question], order: tuple[str, ...]) -> dict[str, Question]:
    q = questions["relation"]
    assert isinstance(q, Choice)
    return {"relation": Choice(q.instructions, {k: q.options[k] for k in order})}


def _arm(rows: list[dict[str, Any]], name: str, order: tuple[str, ...]) -> dict[str, Any]:
    base = [r["arms"]["shipped"] for r in rows]
    arm = [r["arms"][name] for r in rows]
    pairs = list(zip(arm, base, strict=True))
    deltas = [
        abs(a["probabilities"].get(b["choice"], 0.0) - b["probabilities"].get(b["choice"], 0.0))
        for a, b in pairs
        if b["choice"] is not None
    ]
    mass = [a["probabilities"].get(order[0], 0.0) for a in arm if a["probabilities"]]
    decided = [(a, r) for a, r in zip(arm, rows, strict=True) if a["decided"]]
    return {
        "order": list(order),
        "flips_vs_shipped": sum(a["choice"] != b["choice"] for a, b in pairs),
        "median_delta_p": round(statistics.median(deltas), 3) if deltas else None,
        "max_delta_p": round(max(deltas), 3) if deltas else None,
        "mass_on_first": round(sum(mass) / len(mass), 3) if mass else None,
        "decided": len(decided),
        "hits": sum(a["choice"] == r["expected"] for a, r in decided),
        "unanswered": sum(a["choice"] is None for a in arm),
    }


async def run(*, offline: bool, env_file: str | None = None) -> dict[str, Any]:
    # The 50 facts cases the order study was run on. A glob over benches/ picked up every later
    # facts batch (the fifth, graph-e.jsonl, is unrecorded here) and failed the counts.
    every = load_cases(ROOT / "benches" / name for name in ("graph.jsonl", "graph-c.jsonl"))
    cases = [c for c in every if c["point"] == "facts"]
    key = None if offline else _key(env_file)
    own = RecordedDecider.from_file(FIXTURE)
    live = None if key is None else RecordingDecider(create("jev", api_key=key), FIXTURE)
    sources = {
        name: [_repository_recordings()] if name == "shipped" else [own, *([live] if live else [])]
        for name in ORDERS
    }
    t = Thresholds()
    rows: list[dict[str, Any]] = []
    cost = 0.0
    for case in cases:
        inp = case["input"]
        state, qs = entities.fact_questions(fact_a=inp["fact_a"], fact_b=inp["fact_b"])
        arms: dict[str, Any] = {}
        for name, order in ORDERS.items():
            asked = qs if order == SHIPPED else reordered(qs, order)
            decision = None
            for source in sources[name]:
                decision = await source.decide("facts", state, asked)
                if not decision.failed and not decision.answer("relation").empty:
                    break
            assert decision is not None
            answer = decision.answer("relation")
            if decision.provider == "jev":
                cost += decision.cost_usd
            arms[name] = {
                "choice": answer.choice,
                "confidence": answer.confidence,
                "probabilities": dict(answer.probabilities),
                "provider": decision.provider,
                "decided": answer.choice is not None and answer.confidence >= t.relax,
            }
        rows.append({"id": case["id"], "expected": case["expected"], "arms": arms})
    summary: dict[str, Any] = {
        "cases": len(rows),
        "live_cost_usd": round(cost, 6),
        "arms": {name: _arm(rows, name, order) for name, order in ORDERS.items()},
    }
    return {"summary": summary, "rows": rows}


def report(result: dict[str, Any]) -> str:
    s = result["summary"]
    lines = [
        f"facts, {s['cases']} cases; live cost this run {s['live_cost_usd']:.4f} USD",
        "",
        "| arm | order | flips vs shipped | median delta p | max delta p | mass on first "
        "| hits / decided |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, a in s["arms"].items():
        lines.append(
            f"| {name} | {', '.join(a['order'])} | {a['flips_vs_shipped']} | "
            f"{a['median_delta_p']} | {a['max_delta_p']} | {a['mass_on_first']} | "
            f"{a['hits']}/{a['decided']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="replay only; never call a provider")
    ap.add_argument("--env-file", default=None, help="a .env holding TYPESAFE_API_KEY")
    ap.add_argument("--out", default=str(RESULTS / "option-order.json"))
    args = ap.parse_args()
    result = asyncio.run(run(offline=args.offline, env_file=args.env_file))
    unanswered = sum(a["unanswered"] for a in result["summary"]["arms"].values())
    if unanswered:
        sys.stderr.write(f"{unanswered} answers missing from the recording\n")
    pathlib.Path(args.out).write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    sys.stdout.write(report(result))
    return 1 if unanswered else 0


if __name__ == "__main__":
    raise SystemExit(main())
