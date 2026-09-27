"""A lexical screen, then one in-context call: a tournament in one call (`prereg.md`).

python benchmarks/lateral/screen/run.py --record-hash
python benchmarks/lateral/screen/run.py --live --hotpot HOTPOT.jsonl --env-file ENV
python benchmarks/lateral/screen/run.py --hotpot HOTPOT.jsonl --qasper QASPER.jsonl   # free, replay

The 200 held-out questions of `docs/results/2026-09-27-hierarchy/`, 100 pages each. SCREEN
keeps the 30 pages BM25 ranks highest (`chunks.PAGE_MAX`, what one call holds) and asks
`Squire.triage_pages` once, at the shipped cut. Nothing is derived. The tournament's answers
replay from `fixtures/hierarchy.jsonl`; only the screen's calls are live, recorded in
`fixtures/lateral-screen.jsonl`. The boundary, on QASPER papers, is free: BM25's own ceiling.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hier = _load("hierarchy_run", ROOT / "benchmarks" / "hierarchy" / "run.py")
ledger = _load("lateral_ledger", HERE.parent / "ledger.py")

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.eval.stats import bootstrap_difference, mcnemar, wilson  # noqa: E402
from sanchopanza.points import chunks  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-28-lateral-screen"
PREREG = RESULTS / "prereg.md"
FIXTURE = ROOT / "fixtures" / "lateral-screen.jsonl"
SCREEN = chunks.PAGE_MAX
CAP_USD = 0.12


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != digest():
        raise SystemExit("prereg.md missing or changed: nothing spent")


def bm25_top(question: str, pages: list[tuple[str, str]], k: int) -> list[int]:
    scores = hier.triage_run.bm25_scores(question, [f"{t} {x}" for t, x in pages])
    ranked = sorted(range(len(pages)), key=lambda i: scores[i], reverse=True)[:k]
    return sorted(ranked)  # the screen keeps the order the pages came in


async def screen(rows: list[dict[str, Any]], decider: Any) -> Squire:
    squire = Squire(
        decider, thresholds=replace(Thresholds(), max_decisions=1_000_000, max_usd=CAP_USD)
    )
    gate = asyncio.Semaphore(8)

    async def one(row: dict[str, Any]) -> None:
        ids = bm25_top(row["question"], row["pages"], SCREEN)
        async with gate:
            out = await squire.triage_pages(
                purpose=row["question"], pages=[row["pages"][i] for i in ids]
            )
        kept = {i for i, (keep, _) in zip(ids, out, strict=True) if keep}
        row["screen_ids"] = ids
        row["screen_p"] = [p for _, p in out]
        row["screen_keep"] = [i in kept for i in range(len(row["pages"]))]

    await asyncio.gather(*(one(r) for r in rows))
    return squire


async def tournament(rows: list[dict[str, Any]]) -> None:
    replay = hier.triage_run.ReplayFirst(RecordedDecider.from_file(hier.FIXTURE), None)
    await hier.round_one(rows, replay)
    await hier.final_round(rows, replay, hier.derive_r1(rows[: hier.DERIVATION]))
    if replay.missing:
        raise SystemExit("the hierarchy recordings do not cover the 300 questions")


def arm_mask(row: dict[str, Any], arm: str) -> list[bool]:
    if arm == "SCREEN":
        return row["screen_keep"]
    if arm == "CEILING":
        top = set(row["screen_ids"])
        return [i in top for i in range(len(row["pages"]))]
    return hier.keep(row, arm)


def joint(rows: list[dict[str, Any]], arm: str) -> list[bool]:
    return [all(m for m, g in zip(arm_mask(r, arm), r["gold"], strict=True) if g) for r in rows]


def score(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    hits = joint(rows, arm)
    share = pages = 0.0
    for row in rows:
        mask = arm_mask(row, arm)
        sizes = [len(t) + len(x) for t, x in row["pages"]]
        share += sum(s for s, m in zip(sizes, mask, strict=True) if m) / sum(sizes)
        pages += sum(mask)
    n = len(rows)
    _, lo, hi = wilson(sum(hits), n)
    return {
        "page_joint": round(sum(hits) / n, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "kept_share": round(share / n, 4),
        "pages_kept": round(pages / n, 2),
        "n": n,
    }


def qasper_boundary(qasper: pathlib.Path) -> dict[str, Any]:
    """BM25's ceiling for the screen on whole papers, against the tournament's recorded keep."""
    ld = _load("longdocs_run", ROOT / "benchmarks" / "longdocs" / "run.py")
    rows = ld.build(qasper)
    replay = ld.triage_run.ReplayFirst(RecordedDecider.from_file(ld.FIXTURE), None)
    asyncio.run(ld.ask(rows, replay))
    big = [r for r in rows if len(r["pages"]) > SCREEN]
    ceiling = tour = 0
    for r in big:
        top = set(bm25_top(r["question"], r["pages"], SCREEN))
        gold = [i for i, g in enumerate(r["gold"]) if g]
        ceiling += all(i in top for i in gold)
        tour += all(r["keep"][i] for i in gold)
    n = len(big)
    return {
        "papers_over_one_call": n,
        "screen_ceiling_all_evidence": round(ceiling / n, 4),
        "tournament_all_evidence": round(tour / n, 4),
        "note": "descriptive: the ceiling was computed before registration",
    }


def analyze(rows: list[dict[str, Any]], qasper: pathlib.Path | None) -> dict[str, Any]:
    held = rows[hier.DERIVATION :]
    arms = {a: score(held, a) for a in ("SCREEN", "TOUR", "FLAT", "CEILING")}
    s, t = joint(held, "SCREEN"), joint(held, "TOUR")
    diff, lo, hi = bootstrap_difference(s, t)
    only_s, only_t, p = mcnemar(s, t)
    report: dict[str, Any] = {
        "held_out": arms,
        "screen_minus_tour": {
            "page_joint": round(diff, 4),
            "ci95": [round(lo, 4), round(hi, 4)],
            "only_screen": only_s,
            "only_tour": only_t,
            "mcnemar_p": round(p, 4),
        },
        "calls_per_question": {
            "SCREEN": 1,
            "TOUR": round(
                sum(
                    len(hier.hierarchy.groups(hier.PAGES, hier.GROUP)) + r["final_calls"]
                    for r in held
                )
                / len(held),
                2,
            ),
        },
    }
    sc = arms["SCREEN"]
    tour = arms["TOUR"]
    report["S1"] = (
        sc["page_joint"] >= tour["page_joint"] - 0.01
        and sc["kept_share"] <= tour["kept_share"] + 0.01
    )
    report["S2"] = lo >= -0.03
    report["verdict"] = "confirmed" if report["S1"] and report["S2"] else "not confirmed"
    if qasper is not None:
        report["qasper_boundary"] = qasper_boundary(qasper)
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
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--qasper", default="")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.record_hash:
        ledger.write_hash(RESULTS / "prereg.sha256", digest())
        print(digest())
        return 0
    rows = hier.build(pathlib.Path(args.hotpot))
    live = None
    if args.live:
        require_prereg()
        ledger.require_jev_room(CAP_USD)
        live = RecordingDecider(create("jev", api_key=key_from(args.env_file)), FIXTURE)
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else RecordedDecider([])
    replay = hier.triage_run.ReplayFirst(recorded, live)

    async def both() -> Squire:
        await tournament(rows)
        # Only the 200 held-out questions are screened: the first 100 fixed the tournament's
        # round-one cut and the screen has nothing to derive.
        return await screen(rows[hier.DERIVATION :], replay)

    squire = asyncio.run(both())
    print(f"live {replay.asked}, missing {replay.missing}", file=sys.stderr)
    if replay.missing or squire.exhausted:
        print("INCOMPLETE: missing answers or the cap reached; nothing scored", file=sys.stderr)
        return 1
    report = analyze(rows, pathlib.Path(args.qasper) if args.qasper else None)
    if args.live or not (RESULTS / "analysis.json").exists():
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
