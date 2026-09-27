"""The whole-document rule on QASPER questions it was not derived on (`prereg.md`).

python benchmarks/lateral/wholedocs/confirm.py --qasper QASPER-TEST.jsonl --dry
python benchmarks/lateral/wholedocs/confirm.py --record-hash
python benchmarks/lateral/wholedocs/confirm.py --live --qasper QASPER-TEST.jsonl --env-file ENV
python benchmarks/lateral/wholedocs/confirm.py --qasper QASPER-TEST.jsonl          # free, replay

The rule is frozen below (`FROZEN`), fixed on the 261 recorded questions by `rescore.py`.
Two sets nothing was derived on: every eligible QASPER test paper the 2026-09-27 run did not
use (fresh papers), and a second question, never asked, on 130 of the papers it did use.
Tournament and sentence calls are recorded to `fixtures/lateral-wholedocs.jsonl`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import random
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


data = _load("wholedocs_data", HERE / "data.py")
rules = _load("wholedocs_rules", HERE / "rules.py")
ledger = _load("lateral_ledger", HERE.parent / "ledger.py")

from sanchopanza.eval.stats import bootstrap_difference, mcnemar, wilson  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-28-lateral-wholedocs"
PREREG = RESULTS / "prereg.md"
FIXTURE = ROOT / "fixtures" / "lateral-wholedocs.jsonl"
FROZEN = rules.Rule(gate=0.75, cut=0.28, window=2)
SECOND_SEED = 2031
ORDER_SEED = 2032
SECOND_QUESTIONS = 130
CAP_TOURNAMENT_USD = 0.45
CAP_SENTENCES_USD = 0.32


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != digest():
        raise SystemExit("prereg.md missing or changed: nothing spent")


def pages_of(paper: dict[str, Any]) -> list[tuple[str, str]]:
    ft = paper["full_text"]
    return [
        (str(section or ""), str(p).strip())
        for section, paras in zip(ft["section_name"], ft["paragraphs"], strict=True)
        for p in paras
        if p and str(p).strip()
    ]


def second_question(paper: dict[str, Any], used: str) -> dict[str, Any] | None:
    pages = pages_of(paper)
    texts = {x for _, x in pages}
    options = []
    for question, answers in zip(paper["qas"]["question"], paper["qas"]["answers"], strict=True):
        first = (answers.get("answer") or [None])[0]
        if first is None or question.strip() == used:
            continue
        evidence = data.ld.eligible(first, texts)
        if evidence:
            options.append((question.strip(), evidence))
    if not options:
        return None
    question, evidence = random.Random(f"{SECOND_SEED}-{paper['id']}").choice(options)
    return {
        "id": paper["id"],
        "question": question,
        "pages": pages,
        "gold": [x in set(evidence) for _, x in pages],
    }


def build(qasper: pathlib.Path) -> list[dict[str, Any]]:
    """Fresh papers first, then second questions; each row says which set it belongs to."""
    papers = data.load_papers(qasper)
    used = data.ld.build(qasper)  # the 300 of 2026-09-27, as that run drew them
    used_ids = {r["id"] for r in used}
    saved = data.ld.PAPERS
    data.ld.PAPERS = 10**9
    try:
        every = data.ld.build(qasper)
    finally:
        data.ld.PAPERS = saved
    fresh, _ = data.ls.enrich([r for r in every if r["id"] not in used_ids], papers)
    candidates = [second_question(papers[r["id"]], r["question"]) for r in used]
    seconds, _ = data.ls.enrich([c for c in candidates if c is not None], papers)
    seconds.sort(key=lambda r: r["id"])
    random.Random(ORDER_SEED).shuffle(seconds)
    rows = [{**r, "set": "fresh"} for r in fresh]
    rows += [{**r, "set": "second"} for r in seconds[:SECOND_QUESTIONS]]
    return rows


def arms(rows: list[dict[str, Any]]) -> dict[str, list[list[list[bool]]]]:
    def by(rule: Any) -> list[list[list[bool]]]:
        return [rules.document_mask(r["keep"], r["para_final"], r["p_s"], rule) for r in rows]

    return {
        "MS_shipped": by(rules.SHIPPED),
        "GW_frozen": by(FROZEN),
        "W_window_only": by(rules.Rule(0.40, FROZEN.cut, FROZEN.window)),
        "G_gate_only": by(rules.Rule(FROZEN.gate, FROZEN.cut, 0)),
    }


def hits(rows: list[dict[str, Any]], masks: list[list[list[bool]]]) -> list[bool]:
    out = []
    for row, mask in zip(rows, masks, strict=True):
        gold = [
            m
            for ms, gs in zip(mask, row["gold_s"], strict=True)
            for m, g in zip(ms, gs, strict=True)
            if g
        ]
        out.append(all(gold))
    return out


def with_interval(rows: list[dict[str, Any]], masks: list[list[list[bool]]]) -> dict[str, Any]:
    s = data.ls.score(rows, masks)
    h = hits(rows, masks)
    p, lo, hi = wilson(sum(h), len(h))
    return {**s, "all_gold_hits": sum(h), "all_gold_ci95": [round(lo, 4), round(hi, 4)]}


def report_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by = arms(rows)
    out = {name: with_interval(rows, m) for name, m in by.items()}
    budgets = [data.ls.kept_chars(r, m) for r, m in zip(rows, by["GW_frozen"], strict=True)]
    out["BM25_sentences_at_GW_text"] = with_interval(rows, data.ls.bm25_masks(rows, budgets))
    gw, ms = hits(rows, by["GW_frozen"]), hits(rows, by["MS_shipped"])
    only_gw, only_ms, p = mcnemar(gw, ms)
    diff, lo, hi = bootstrap_difference(gw, ms)
    out["GW_minus_MS"] = {
        "all_gold": round(diff, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "only_GW": only_gw,
        "only_MS": only_ms,
        "mcnemar_p": round(p, 4),
        "text_points": round(out["GW_frozen"]["kept_share"] - out["MS_shipped"]["kept_share"], 4),
    }
    return out


def analyze(rows: list[dict[str, Any]], calls: dict[str, int]) -> dict[str, Any]:
    pooled = report_for(rows)
    gw, ms, bm = pooled["GW_frozen"], pooled["MS_shipped"], pooled["BM25_sentences_at_GW_text"]
    report: dict[str, Any] = {
        "rule": {"gate": FROZEN.gate, "cut": FROZEN.cut, "window": FROZEN.window},
        "questions": len(rows),
        "by_set": {s: sum(r["set"] == s for r in rows) for s in ("fresh", "second")},
        "pooled": pooled,
        "fresh_only": report_for([r for r in rows if r["set"] == "fresh"]),
        "second_only": report_for([r for r in rows if r["set"] == "second"]),
        "calls": calls,
        "Q1": gw["all_gold"] >= 0.85 and gw["kept_share"] <= 0.25,
        "Q2": gw["all_gold"] >= ms["all_gold"] and gw["kept_share"] <= ms["kept_share"] - 0.05,
        "Q3_gw_minus_bm25": round(gw["all_gold"] - bm["all_gold"], 4),
    }
    report["Q3"] = report["Q3_gw_minus_bm25"] >= 0.10
    report["verdict"] = (
        "confirmed" if report["Q1"] and report["Q2"] and report["Q3"] else "not confirmed"
    )
    return report


def key_from(env_file: str | None) -> str:
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key and env_file:
        text = pathlib.Path(env_file).read_text(encoding="utf-8")
        key = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY")
    return key


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--dry", action="store_true", help="build the sets and stop")
    ap.add_argument("--qasper", default="")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.record_hash:
        ledger.write_hash(RESULTS / "prereg.sha256", digest())
        print(digest())
        return 0
    rows = build(pathlib.Path(args.qasper))
    if args.dry:
        paras = [len(r["pages"]) for r in rows]
        print(
            json.dumps(
                {
                    "questions": len(rows),
                    "by_set": {s: sum(r["set"] == s for r in rows) for s in ("fresh", "second")},
                    "paragraphs_mean": round(sum(paras) / len(paras), 1),
                    "over_one_call": sum(p > 30 for p in paras),
                }
            )
        )
        return 0
    live = None
    if args.live:
        require_prereg()
        ledger.require_jev_room(CAP_TOURNAMENT_USD + CAP_SENTENCES_USD)
        live = RecordingDecider(create("jev", api_key=key_from(args.env_file)), FIXTURE)
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else RecordedDecider([])
    # One throttle for both stages: two would allow twice the registered 12 calls a second.
    replay = data.ld.triage_run.ReplayFirst(recorded, live)
    squire = asyncio.run(
        data.probe(
            rows,
            replay,
            replay,
            cap_usd=CAP_SENTENCES_USD,
            cap_tournament_usd=CAP_TOURNAMENT_USD,
        )
    )
    print(f"live {replay.asked}, missing {replay.missing}", file=sys.stderr)
    if replay.missing or squire.exhausted:
        print("INCOMPLETE: missing answers or a cap reached; nothing scored", file=sys.stderr)
        return 1
    calls = {
        "tournament": sum(r["t_calls"] for r in rows),
        "sentences_asked_all_kept_paragraphs": sum(sum(r["keep"]) for r in rows),
        "sentences_needed_by_rule": sum(
            rules.needs_sentence_call(k, f, FROZEN)
            for r in rows
            for k, f in zip(r["keep"], r["para_final"], strict=True)
        ),
    }
    report = analyze(rows, calls)
    if args.live or not (RESULTS / "analysis.json").exists():
        (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
