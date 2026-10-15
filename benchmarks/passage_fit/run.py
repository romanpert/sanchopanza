"""B4: order the approved paragraphs that do not fit (`docs/results/2026-10-16-b4-order/`).

    python benchmarks/passage_fit/run.py free     # free: recordings only, the free orders
    python benchmarks/passage_fit/run.py dry      # free: the Score calls, recorded and priced
    python benchmarks/passage_fit/run.py seal     # sha256 of prereg.md, once
    python benchmarks/passage_fit/run.py paid     # Jev: only what is missing, capped, once
    python benchmarks/passage_fit/run.py report   # free once recorded: every arm, the verdict

QASPER test split as JSONL (`--qasper`, default ~/.cache/sancho/qasper-test.jsonl). The two
stages are replayed from the recordings of the whole-papers runs, nothing re-asked: the 261
derivation questions (`fixtures/longdocs*.jsonl`) fix the size budget, gold-blind (median of
what the shipped rule delivers, rounded down to 100 characters), and with the 219
confirmation questions (`fixtures/lateral-wholedocs.jsonl`) are scored. Only the questions
whose delivered text exceeds the budget can differ between arms; the primary set is those of
both sets, pooled. The paid arm asks one four-level Score per delivered paragraph of those
questions (`passages.fit_questions`, 12 per call), recorded in
`fixtures/b4-order/recording.jsonl`. The key comes from TYPESAFE_API_KEY or the file
SANCHOPANZA_KEYS_ENV names, never printed.

Arms (`orders.py`): PAGE, the order the output has today; PROB, the tournament probability;
BM25 over the delivered text; FREE, `select_passages(fit_chars=..., fit_score=False)` (best
sentence probability, then tournament); L4, `fit_score=True` (the Score first); GOLD, the
ceiling, descriptive.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(HERE))

import orders as od  # noqa: E402
import paid_once  # noqa: E402

from sanchopanza.eval.stats import bootstrap_difference, mcnemar, wilson  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


WHOLEDOCS = ROOT / "benchmarks" / "lateral" / "wholedocs"
RESULTS = ROOT / "docs" / "results" / "2026-10-16-b4-order"
PREREG = RESULTS / "prereg.md"
# One level below `fixtures/`: the analyses that read every `fixtures/*.jsonl` keep their sets.
FIXTURE = ROOT / "fixtures" / "b4-order" / "recording.jsonl"
QASPER = pathlib.Path.home() / ".cache" / "sancho" / "qasper-test.jsonl"
MODEL = "jev-1.13.0"
BATCH = "b4-order"
CAP_USD = 0.10  # hard, in the ledger; the pessimistic estimate of the plan must fit under it
RUN = pathlib.Path(
    os.environ.get("SANCHOPANZA_B4_RUN", pathlib.Path.home() / ".cache" / "sanchopanza" / BATCH)
)
NONINFERIOR = 0.02  # L4 may trail the free order by at most this much recall (prereg)


def rows_of(qasper: pathlib.Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(derivation 261, confirmation 219), both stages replayed from their recordings."""
    data = _load("wholedocs_data", WHOLEDOCS / "data.py")
    confirm = _load("wholedocs_confirm", WHOLEDOCS / "confirm.py")
    rescore = _load("wholedocs_rescore", WHOLEDOCS / "rescore.py")
    derivation = rescore.recorded_rows(qasper)
    rows = confirm.build(qasper)
    replay = data.ld.triage_run.ReplayFirst(RecordedDecider.from_file(confirm.FIXTURE), None)
    asyncio.run(data.probe(rows, replay, replay))
    if replay.missing:
        raise SystemExit("the whole-papers recordings do not cover the 219 questions")
    for row in derivation + rows:
        row["mask"] = confirm.rules.document_mask(
            row["keep"], row["para_final"], row["p_s"], confirm.FROZEN
        )
        row["items"] = od.delivered(row, row["mask"])
    return derivation, rows


def queries(rows: list[dict[str, Any]], budget: int) -> list[tuple[str, Any, Any]]:
    out = []
    for row in rows:
        if od.total(row["items"]) > budget:
            for group in od.groups(row["items"]):
                out.append(("passage_fit", *od.fit_query(row, row["items"], group)))
    return out


async def recorded_scores(rows: list[dict[str, Any]], budget: int) -> int:
    """Fill `scores` on every overflowing row from the recording; return how many calls lack."""
    recorded = RecordedDecider.from_file(FIXTURE)
    lacking = 0
    for row in rows:
        if od.total(row["items"]) <= budget:  # it all fits: no call, every arm sends it all
            row["scores"] = [None] * len(row["items"])
            continue
        scores: list[float | None] = []
        for group in od.groups(row["items"]):
            d = await recorded.decide("passage_fit", *od.fit_query(row, row["items"], group))
            lacking += not d.answers
            scores += [d.answer(f"P{k + 1:02d}").score for k in range(len(group))]
        row["scores"] = scores
    return lacking


def arm_results(row: dict[str, Any], budget: int) -> dict[str, dict[str, Any]]:
    items = row["items"]
    by_arm = od.orders(row, items, scores=row.get("scores"))
    out = {}
    for arm, order in by_arm.items():
        mask = od.under_budget(row["mask"], items, order, budget)
        hit, gold = od.gold_kept(row, mask)
        sent = sum(it.size for it in items if any(mask[it.index]))
        out[arm] = {"recall": hit / gold if gold else 0.0, "all": hit == gold, "chars": sent}
    return out


def summary(rows: list[dict[str, Any]], budget: int) -> dict[str, Any]:
    per = [arm_results(r, budget) for r in rows]
    arms = [a for a in per[0] if all(a in p for p in per)] if per else []
    out: dict[str, Any] = {"n": len(rows)}
    for arm in arms:
        rec = [p[arm]["recall"] for p in per]
        alls = [p[arm]["all"] for p in per]
        _, lo, hi = wilson(sum(alls), len(alls))
        out[arm] = {
            "recall": round(sum(rec) / len(rec), 4),
            "all_gold": round(sum(alls) / len(alls), 4),
            "all_gold_ci95": [round(lo, 4), round(hi, 4)],
            "chars_mean": round(sum(p[arm]["chars"] for p in per) / len(per), 1),
        }
    pairs = [("FREE", "PAGE"), ("PROB", "PAGE"), ("BM25", "PAGE"), ("FREE", "PROB")]
    if od.PAID_ARM in arms:
        pairs = [("L4", "PAGE"), ("L4", "BM25"), ("L4", "FREE"), ("L4", "PROB")] + pairs
    out["paired"] = {f"{a}-{b}": compare(per, a, b) for a, b in pairs}
    return out


def compare(per: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    ra = [p[a]["recall"] for p in per]
    rb = [p[b]["recall"] for p in per]
    diff, lo, hi = bootstrap_difference(ra, rb)
    only_a, only_b, p = mcnemar([x[a]["all"] for x in per], [x[b]["all"] for x in per])
    return {
        "recall_diff": round(diff, 4),
        "recall_ci95": [round(lo, 4), round(hi, 4)],
        "all_gold_only_first": only_a,
        "all_gold_only_second": only_b,
        "mcnemar_p": round(p, 4),
    }


def verdict(paired: dict[str, Any]) -> str:
    """The rule of prereg.md, applied as written."""

    def low(key: str) -> float:
        return paired[key]["recall_ci95"][0]

    beats_today = low("L4-PAGE") > 0 and low("L4-BM25") > 0
    over_free = min(low("L4-FREE"), low("L4-PROB"))
    if beats_today and over_free > 0:
        return "L4 confirmed: the Score pays over both free orders"
    if beats_today and over_free > -NONINFERIOR:
        return "L4 no better than the free orders: the Score is not worth its calls"
    return "L4 not confirmed"


def analysis(qasper: pathlib.Path, *, paid: bool) -> dict[str, Any]:
    derivation, rows = rows_of(qasper)
    budget = od.budget_from([od.total(r["items"]) for r in derivation])
    if paid:
        lacking = asyncio.run(recorded_scores(derivation + rows, budget))
        if lacking:
            raise SystemExit(f"{lacking} Score calls not recorded: run `paid` first")
    over = [r for r in rows if od.total(r["items"]) > budget]
    derived_over = [r for r in derivation if od.total(r["items"]) > budget]
    report = {
        "budget_chars": budget,
        "questions": {"derivation": len(derivation), "confirmation": len(rows)},
        "overflowing": {"derivation": len(derived_over), "confirmation": len(over)},
        "primary_pooled_overflowing": summary(derived_over + over, budget),
        "confirmation_overflowing": summary(over, budget),
        "derivation_overflowing": summary(derived_over, budget),
        "confirmation_all_219": summary(rows, budget),
    }
    if paid:
        report["verdict"] = verdict(report["primary_pooled_overflowing"]["paired"])
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("free", "dry", "seal", "paid", "report"))
    ap.add_argument("--qasper", type=pathlib.Path, default=QASPER)
    args = ap.parse_args()
    if args.action == "seal":
        print(paid_once.seal(PREREG))
        return 0
    if args.action in ("free", "report"):
        report = analysis(args.qasper, paid=args.action == "report")
        name = "free.json" if args.action == "free" else "analysis.json"
        (RESULTS / name).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=1))
        return 0
    derivation, rows = rows_of(args.qasper)
    budget = od.budget_from([od.total(r["items"]) for r in derivation])
    asks = queries(derivation + rows, budget)
    plan = {"budget_chars": budget, **paid_once.plan(asks, FIXTURE), "cap_usd": CAP_USD}
    print(json.dumps(plan, indent=1))
    if args.action == "dry":
        return 0
    paid_once.require_room(plan, CAP_USD)
    paid_once.require_sealed(PREREG)
    import l4  # noqa: PLC0415  (jev114/l4.py: the key loader every lot uses)

    l4.load_key()
    paid_once.preflight(MODEL)
    from sanchopanza.providers.jev import JevDecider

    RUN.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(
        paid_once.ask_missing(
            asks,
            FIXTURE,
            live=JevDecider(model=MODEL),
            ledger=RUN / "ledger.jsonl",
            batch=BATCH,
            cap_usd=CAP_USD,
        )
    )
    print(json.dumps(result, indent=1))
    return 0 if result["stopped"] is None else 2


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))
    raise SystemExit(main())
