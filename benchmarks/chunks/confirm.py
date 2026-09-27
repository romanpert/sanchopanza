"""The confirmatory chunk run (`prereg-confirm.md`): cuts from 600 questions, tested on 300 new.

python benchmarks/chunks/confirm.py --record-hash
python benchmarks/chunks/confirm.py --live --hotpot FILE --env-file PATH/TO/.env
python benchmarks/chunks/confirm.py --hotpot FILE                 # free, from recordings
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import random
import re
import sys
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("chunk_run", HERE / "run.py")
chunk_run = importlib.util.module_from_spec(_spec)  # both scripts are named run.py
_spec.loader.exec_module(chunk_run)

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.points import triage  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = chunk_run.RESULTS
PREREG = RESULTS / "prereg-confirm.md"
FIXTURE = chunk_run.ROOT / "fixtures" / "chunks-confirm.jsonl"
SEED = 2028


def require_prereg() -> None:
    digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    registered = RESULTS / "prereg-confirm.sha256"
    if not registered.exists() or registered.read_text().strip() != digest:
        raise SystemExit("prereg-confirm.md missing or changed: nothing spent")


def fresh(hotpot: pathlib.Path, used: set[str]) -> list[dict[str, Any]]:
    raw = [json.loads(x) for x in hotpot.read_text(encoding="utf-8").splitlines() if x]
    pool = [r for r in raw if len(r["context"]["title"]) == 10 and r["id"] not in used]
    rows = []
    for r in random.Random(SEED).sample(pool, 300):
        titles = r["context"]["title"]
        sentences = [[s.strip() for s in sents] for sents in r["context"]["sentences"]]
        gold = set(
            zip(r["supporting_facts"]["title"], r["supporting_facts"]["sent_id"], strict=True)
        )
        rows.append(
            {
                "id": r["id"],
                "question": r["question"],
                "titles": titles,
                "sentences": sentences,
                "gold": [
                    [(t, i) in gold for i in range(len(s))]
                    for t, s in zip(titles, sentences, strict=True)
                ],
            }
        )
    return rows


async def page_contribution(rows: list[dict[str, Any]], decider: Any) -> None:
    squire = Squire(decider, thresholds=replace(Thresholds(), max_decisions=1_000_000, max_usd=5.0))
    gate = asyncio.Semaphore(8)

    async def one(row: dict[str, Any], j: int) -> float:
        state, qs = triage.contribution_questions(
            purpose=row["question"], title=row["titles"][j], text=" ".join(row["sentences"][j])
        )
        async with gate:
            d = await squire.decide("triage_contribution", state, qs)
        p = d.answer("contributes").truth
        return float("nan") if p is None else p

    for row in rows:
        row["page_contributes"] = list(
            await asyncio.gather(*(one(row, j) for j in range(len(row["titles"]))))
        )


def derive(rows: list[dict[str, Any]], arm: str, metric: str, target: float) -> float:
    grid = chunk_run.GRIDS[arm]
    scored = [(k, chunk_run.score(rows, arm, k)) for k in grid]
    reaching = [(s["kept_share"], k) for k, s in scored if s[metric] >= target]
    return min(reaching)[1] if reaching else max(scored, key=lambda ks: ks[1][metric])[0]


def cb_mask(row: dict[str, Any], c: float, b: float) -> list[list[bool]]:
    return [
        [(pc is None or pc >= c) and (p is None or p >= b) for p in page]
        for page, pc in zip(row["sentence_p"], row["context_p"], strict=True)
    ]


def cb_score(rows: list[dict[str, Any]], c: float, b: float) -> dict[str, float]:
    saved = chunk_run.mask
    chunk_run.mask = lambda row, arm, knob: cb_mask(row, c, b)  # type: ignore[assignment]
    try:
        return chunk_run.score(rows, "CB", 0.0)
    finally:
        chunk_run.mask = saved  # type: ignore[assignment]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.record_hash:
        digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
        (RESULTS / "prereg-confirm.sha256").write_text(digest + "\n", encoding="utf-8")
        print(digest)
        return 0
    hotpot = pathlib.Path(args.hotpot)
    earlier = chunk_run.samples(hotpot)
    old = earlier["derivation"] + earlier["held_out"]
    asyncio.run(chunk_run.ask(old, RecordedDecider.from_file(chunk_run.FIXTURE)))
    cuts = {
        "A": chunk_run.PAGE_CUT,
        "C": derive(old, "C", "page_joint", 0.97),
        "B": derive(old, "B", "sentence_joint", 0.90),
    }
    cb_grid = [round(i * 0.01, 2) for i in range(101)]
    reaching = [
        (cb_score(old, cuts["C"], b)["kept_share"], b)
        for b in cb_grid
        if cb_score(old, cuts["C"], b)["sentence_joint"] >= 0.90
    ]
    cuts["CB"] = min(reaching)[1] if reaching else 0.0
    print("cuts from 600:", cuts, file=sys.stderr)

    rows = fresh(hotpot, {r["id"] for r in old})
    live = None
    if args.live:
        require_prereg()
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key and args.env_file:
            text = pathlib.Path(args.env_file).read_text(encoding="utf-8")
            key = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")
        live = RecordingDecider(create("jev", api_key=key), FIXTURE)
    replay = chunk_run.triage_run.ReplayFirst(RecordedDecider.from_file(FIXTURE), live)

    async def both() -> None:
        # One event loop: ReplayFirst holds an asyncio.Lock, which a second asyncio.run
        # cannot use (the first attempt lost 2,400 answers to exactly that).
        await chunk_run.ask(rows, replay)
        await page_contribution(rows, replay)

    asyncio.run(both())
    gaps = sum(p != p for r in rows for p in r["page_contributes"]) + sum(
        p is None for r in rows for p in r["context_p"]
    )
    if gaps:
        print(f"INCOMPLETE: {gaps} page or context answers missing", file=sys.stderr)
        return 1
    a = chunk_run.score(rows, "A", cuts["A"])
    c = chunk_run.score(rows, "C", cuts["C"])
    b = chunk_run.score(rows, "B", cuts["B"])
    cb = cb_score(rows, cuts["C"], cuts["CB"])
    report = {
        "cuts_from_600": cuts,
        "A": a,
        "C": c,
        "B": b,
        "CB": cb,
        "P18": c["page_joint"] >= 0.95 and c["kept_share"] <= 0.45,
        "P19": c["page_joint"] >= a["page_joint"] and c["kept_share"] < a["kept_share"],
        "P20": b["sentence_joint"] >= 0.88 and b["kept_share"] <= 0.36,
        "live_calls": replay.asked,
    }
    report["verdict"] = "confirmed" if report["P18"] and report["P19"] else "not confirmed"
    (RESULTS / "confirm-analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
