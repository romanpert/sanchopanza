"""Derive the whole-document rule from recordings only (free, no network).

python benchmarks/lateral/wholedocs/rescore.py --qasper QASPER-TEST.jsonl --hotpot HOTPOT.jsonl

Replays the 261 QASPER questions of `docs/results/2026-09-27-longdocs/` (tournament and
sentence calls both recorded), scores every rule of a small family, and fixes one rule by the
procedure written in `docs/results/2026-09-28-lateral-wholedocs/prereg.md`. Repeated random
halves estimate how much of the derivation's recall survives out of sample. The same family is
also scored on the HotpotQA confirmatory set, descriptively: short pages are not what the rule
is for, and the number is reported so nobody moves a default on the strength of papers alone.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import random
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up while it loads
    spec.loader.exec_module(module)
    return module


data = _load("wholedocs_data", HERE / "data.py")
rules = _load("wholedocs_rules", HERE / "rules.py")

from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-28-lateral-wholedocs"
GATES = [round(0.40 + 0.05 * i, 2) for i in range(11)]
WINDOWS = [0, 1, 2, 3]
CUT = 0.28  # the shipped sentence cut, not re-derived
TEXT_CAP = 0.23  # the derivation's text constraint: two points under the 25 % bar
HALVES = 40
HALF = 130


def family() -> list[Any]:
    return [rules.Rule(gate=g, cut=CUT, window=w) for g in GATES for w in WINDOWS]


def recorded_rows(qasper: pathlib.Path) -> list[dict[str, Any]]:
    papers = data.load_papers(qasper)
    rows, _ = data.ls.enrich(data.ld.build(qasper), papers)
    tournament = data.ld.triage_run.ReplayFirst(RecordedDecider.from_file(data.ld.FIXTURE), None)
    sentences = data.ld.triage_run.ReplayFirst(RecordedDecider.from_file(data.ls.FIXTURE), None)
    asyncio.run(data.probe(rows, tournament, sentences))
    if tournament.missing or sentences.missing:
        raise SystemExit("the longdocs recordings do not cover the 261 questions")
    return rows


def masks(rows: list[dict[str, Any]], rule: Any) -> list[list[list[bool]]]:
    return [rules.document_mask(r["keep"], r["para_final"], r["p_s"], rule) for r in rows]


def score(rows: list[dict[str, Any]], rule: Any) -> dict[str, float]:
    return data.ls.score(rows, masks(rows, rule))


def derive(rows: list[dict[str, Any]], cap: float = TEXT_CAP) -> Any:
    """Highest all-gold recall with text kept <= cap; ties to less text, then the smaller
    window, then the lower gate. The procedure registered in prereg.md."""
    scored = [(rule, score(rows, rule)) for rule in family()]
    allowed = [(rule, s) for rule, s in scored if s["kept_share"] <= cap]
    best = max(
        allowed,
        key=lambda rs: (rs[1]["all_gold"], -rs[1]["kept_share"], -rs[0].window, -rs[0].gate),
    )
    return best[0]


def halves(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = []
    for seed in range(HALVES):
        ids = sorted(r["id"] for r in rows)
        random.Random(seed).shuffle(ids)
        first = set(ids[:HALF])
        a = [r for r in rows if r["id"] in first]
        b = [r for r in rows if r["id"] not in first]
        rule = derive(a)
        held = score(b, rule)
        out.append({"rule": rule.label(), **held})
    n = len(out)
    return {
        "splits": n,
        "mean_all_gold_held_out": round(sum(x["all_gold"] for x in out) / n, 4),
        "mean_kept_share_held_out": round(sum(x["kept_share"] for x in out) / n, 4),
        "both_bars_held_out": sum(x["all_gold"] >= 0.85 and x["kept_share"] <= 0.25 for x in out),
        "min_all_gold_held_out": min(x["all_gold"] for x in out),
        "per_split": out,
    }


def sentence_calls(rows: list[dict[str, Any]], rule: Any) -> int:
    return sum(
        rules.needs_sentence_call(k, f, rule)
        for r in rows
        for k, f in zip(r["keep"], r["para_final"], strict=True)
    )


def hotpot_rows(hotpot: pathlib.Path) -> tuple[list[dict[str, Any]], Any]:
    confirm = _load("chunk_confirm", ROOT / "benchmarks" / "chunks" / "confirm.py")
    run = confirm.chunk_run
    earlier = run.samples(hotpot)
    rows = confirm.fresh(hotpot, {r["id"] for r in earlier["derivation"] + earlier["held_out"]})
    replay = run.triage_run.ReplayFirst(RecordedDecider.from_file(confirm.FIXTURE), None)
    asyncio.run(run.ask(rows, replay))
    return rows, run


def hotpot_score(rows: list[dict[str, Any]], run: Any, rule: Any) -> dict[str, float]:
    saved = run.mask
    run.mask = lambda row, arm, knob: rules.document_mask(  # type: ignore[assignment]
        [True] * len(row["context_p"]), row["context_p"], row["sentence_p"], rule
    )
    try:
        return run.score(rows, "rule", 0.0)
    finally:
        run.mask = saved  # type: ignore[assignment]


def analyze(rows: list[dict[str, Any]], hotpot: pathlib.Path | None) -> dict[str, Any]:
    chosen = derive(rows)
    table = {rule.label(): score(rows, rule) for rule in family()}
    report: dict[str, Any] = {
        "questions": len(rows),
        "family": table,
        "chosen": {"gate": chosen.gate, "cut": chosen.cut, "window": chosen.window},
        "chosen_score": table[chosen.label()],
        "shipped_score": table[rules.SHIPPED.label()],
        "window_only": table[rules.Rule(0.40, CUT, chosen.window).label()],
        "gate_only": table[rules.Rule(chosen.gate, CUT, 0).label()],
        "sentence_calls": {
            "shipped": sentence_calls(rows, rules.SHIPPED),
            "chosen": sentence_calls(rows, chosen),
        },
        "halves": halves(rows),
    }
    if hotpot is not None:
        hp, run = hotpot_rows(hotpot)
        report["hotpot_confirm_descriptive"] = {
            "n": len(hp),
            "shipped": hotpot_score(hp, run, rules.SHIPPED),
            "chosen": hotpot_score(hp, run, chosen),
        }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qasper", required=True)
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--write", action="store_true", help="write derivation.json")
    args = ap.parse_args()
    report = analyze(
        recorded_rows(pathlib.Path(args.qasper)),
        pathlib.Path(args.hotpot) if args.hotpot else None,
    )
    if args.write:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "derivation.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in ("family", "halves")}
    summary["halves"] = {k: v for k, v in report["halves"].items() if k != "per_split"}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
