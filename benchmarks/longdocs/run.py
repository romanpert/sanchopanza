"""The tournament on whole QASPER papers, cuts transferred (`docs/results/2026-09-27-longdocs/`).

python benchmarks/longdocs/run.py --record-hash
python benchmarks/longdocs/run.py --live --qasper test.jsonl --env-file PATH/TO/.env
python benchmarks/longdocs/run.py --qasper test.jsonl               # free, from recordings

Reads the QASPER test split as JSONL, one paper per line (the parquet of `allenai/qasper`
converted row by row). Nothing is derived here: `Squire.triage_many`
runs with the shipped thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import random
import re
import sys
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]

_spec = importlib.util.spec_from_file_location(
    "triage_sets_run", ROOT / "benchmarks" / "triage_sets" / "run.py"
)
triage_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage_run)

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-27-longdocs"
FIXTURE = ROOT / "fixtures" / "longdocs.jsonl"
PREREG = RESULTS / "prereg.md"
SEED = 2030
PAPERS = 300


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != digest():
        raise SystemExit("prereg.md missing or changed: nothing spent")


def eligible(answer: dict[str, Any], paragraphs: set[str]) -> list[str] | None:
    if answer.get("unanswerable"):
        return None
    evidence = [e.strip() for e in answer.get("evidence") or [] if e and e.strip()]
    if not evidence or any(e not in paragraphs for e in evidence):
        return None
    return evidence


def build(qasper: pathlib.Path) -> list[dict[str, Any]]:
    papers = [json.loads(x) for x in qasper.read_text(encoding="utf-8").splitlines() if x]
    rows = []
    for paper in papers:
        ft = paper["full_text"]
        pages = [
            (str(section or ""), str(p).strip())
            for section, paras in zip(ft["section_name"], ft["paragraphs"], strict=True)
            for p in paras
            if p and str(p).strip()
        ]
        texts = {x for _, x in pages}
        options = []
        for question, answers in zip(
            paper["qas"]["question"], paper["qas"]["answers"], strict=True
        ):
            first = (answers.get("answer") or [None])[0]
            if first is None:
                continue
            evidence = eligible(first, texts)
            if evidence:
                options.append((question.strip(), evidence))
        if not options:
            continue
        question, evidence = random.Random(f"{SEED}-{paper['id']}").choice(options)
        rows.append(
            {
                "id": paper["id"],
                "question": question,
                "pages": pages,
                "gold": [x in set(evidence) for _, x in pages],
            }
        )
    rows.sort(key=lambda r: r["id"])
    random.Random(SEED).shuffle(rows)
    return rows[:PAPERS]


async def ask(rows: list[dict[str, Any]], decider: Any) -> None:
    squire = Squire(
        decider, thresholds=replace(Thresholds(), max_decisions=10_000_000, max_usd=5.0)
    )
    gate = asyncio.Semaphore(6)

    async def one(row: dict[str, Any]) -> None:
        async with gate:
            out = await squire.triage_many(purpose=row["question"], pages=row["pages"])
        row["keep"] = [keep for keep, _ in out]

    await asyncio.gather(*(one(r) for r in rows))
    if squire.exhausted:
        raise SystemExit("the squire's budget ran out")


def score(rows: list[dict[str, Any]], masks: list[list[bool]]) -> dict[str, float]:
    all_ = any_ = share = kept = 0.0
    for row, mask in zip(rows, masks, strict=True):
        hits = [m for m, g in zip(mask, row["gold"], strict=True) if g]
        all_ += all(hits)
        any_ += any(hits)
        sizes = [len(t) + len(x) for t, x in row["pages"]]
        share += sum(s for s, m in zip(sizes, mask, strict=True) if m) / sum(sizes)
        kept += sum(mask)
    n = len(rows)
    return {
        "all_evidence": round(all_ / n, 4),
        "any_evidence": round(any_ / n, 4),
        "kept_share": round(share / n, 4),
        "paragraphs_kept": round(kept / n, 2),
        "n": n,
    }


def bm25_masks(rows: list[dict[str, Any]], k: int) -> list[list[bool]]:
    masks = []
    for row in rows:
        scores = triage_run.bm25_scores(row["question"], [f"{t} {x}" for t, x in row["pages"]])
        top = set(sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k])
        masks.append([i in top for i in range(len(scores))])
    return masks


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    many = score(rows, [r["keep"] for r in rows])
    k = math.ceil(many["paragraphs_kept"])
    bm25 = score(rows, bm25_masks(rows, k))
    sizes = [len(r["pages"]) for r in rows]
    report = {
        "papers": len(rows),
        "paragraphs_per_paper": {"mean": round(sum(sizes) / len(sizes), 1), "max": max(sizes)},
        "evidence_per_question": round(sum(sum(r["gold"]) for r in rows) / len(rows), 2),
        "MANY": many,
        f"BM25_top{k}": bm25,
        "P28": many["all_evidence"] >= 0.85 and many["kept_share"] <= 0.25,
        "P29_many_minus_bm25": round(many["all_evidence"] - bm25["all_evidence"], 4),
    }
    report["P29"] = report["P29_many_minus_bm25"] >= 0.10
    report["verdict"] = (
        "the tournament transfers to long documents"
        if report["P28"] and report["P29"]
        else "see criteria"
    )
    return report


def write_hash(target: pathlib.Path, value: str) -> None:
    """Register a hash once. A different hash already there means the registration changed
    after it was recorded: refuse, and let a person delete the old one on purpose."""
    if target.exists() and target.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit(f"{target.name} already holds a different hash: nothing written")
    target.write_text(value + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--qasper", default="")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--dry", action="store_true", help="build the sample and stop")
    args = ap.parse_args()
    if args.record_hash:
        write_hash(RESULTS / "prereg.sha256", digest())
        print(digest())
        return 0
    rows = build(pathlib.Path(args.qasper))
    if args.dry:
        sizes = [len(r["pages"]) for r in rows]
        chars = [sum(len(x) for _, x in r["pages"]) for r in rows]
        print(len(rows), sum(sizes) / len(sizes), max(sizes), sum(chars) / len(chars))
        return 0
    live = None
    if args.live:
        require_prereg()
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key and args.env_file:
            text = pathlib.Path(args.env_file).read_text(encoding="utf-8")
            key = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")
        live = RecordingDecider(create("jev", api_key=key), FIXTURE)
    replay = triage_run.ReplayFirst(RecordedDecider.from_file(FIXTURE), live)
    asyncio.run(ask(rows, replay))
    print(f"live calls {replay.asked}, missing {replay.missing}", file=sys.stderr)
    if replay.missing:
        print("INCOMPLETE: some calls have no answer", file=sys.stderr)
        return 1
    report = analyze(rows)
    (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
