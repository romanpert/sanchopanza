"""Sentences inside the paragraphs the tournament kept, on QASPER (`prereg-sentences.md`).

python benchmarks/longdocs/sentences.py --record-hash
python benchmarks/longdocs/sentences.py --live --qasper test.jsonl --env-file PATH/TO/.env
python benchmarks/longdocs/sentences.py --qasper test.jsonl              # free, from recordings

The tournament is replayed from `fixtures/longdocs.jsonl` and never asked again; only the
`select_sentences` calls can be live, recorded in `fixtures/longdocs-sentences.jsonl`.
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
_spec = importlib.util.spec_from_file_location("longdocs_run", HERE / "run.py")
ld = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ld)

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ld.RESULTS
PREREG = RESULTS / "prereg-sentences.md"
FIXTURE = ld.ROOT / "fixtures" / "longdocs-sentences.jsonl"
CAP_USD = 1.50
SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split(paragraph: str) -> list[tuple[int, int]]:
    """Character ranges of the sentences of a whitespace-collapsed paragraph."""
    ranges, start = [], 0
    for m in SPLIT.finditer(paragraph):
        ranges.append((start, m.start()))
        start = m.end()
    ranges.append((start, len(paragraph)))
    return [(a, b) for a, b in ranges if b > a]


def highlighted(paper: dict[str, Any], question: str) -> list[str]:
    asked = [q.strip() for q in paper["qas"]["question"]]
    first = paper["qas"]["answers"][asked.index(question)]["answer"][0]
    return [norm(h) for h in first.get("highlighted_evidence") or []]


def enrich(rows: list[dict[str, Any]], papers: dict[str, dict[str, Any]]) -> tuple[list, list]:
    """Sentences and gold sentences per row; rows whose spans cannot be located are excluded."""
    kept, excluded = [], []
    for row in rows:
        spans = highlighted(papers[row["id"]], row["question"])
        paras = [norm(x) for _, x in row["pages"]]
        sentences: list[list[tuple[int, int]]] = [split(p) for p in paras]
        gold: list[list[bool]] = [[False] * len(s) for s in sentences]
        located = bool(spans) and all(spans)
        for span in spans if located else ():
            needle = span.rstrip(".")
            hits = [i for i, g in enumerate(row["gold"]) if g and needle in paras[i]]
            if not hits:
                located = False
                break
            i = hits[0]
            a = paras[i].index(needle)
            b = a + len(needle)
            gold[i] = [
                g or (s < b and e > a) for g, (s, e) in zip(gold[i], sentences[i], strict=True)
            ]
        if not located:
            excluded.append(row["id"])
            continue
        kept.append({**row, "paras": paras, "sentences": sentences, "gold_s": gold})
    return kept, excluded


async def ask(rows: list[dict[str, Any]], tournament: Any, decider: Any) -> Any:
    loose = replace(Thresholds(), max_decisions=10_000_000, max_usd=5.0)
    many = Squire(tournament, thresholds=loose)
    squire = Squire(
        decider, thresholds=replace(Thresholds(), max_decisions=10_000_000, max_usd=CAP_USD)
    )
    gate = asyncio.Semaphore(6)

    async def one(row: dict[str, Any]) -> None:
        async with gate:
            out = await many.triage_many(purpose=row["question"], pages=row["pages"])
        row["keep"] = [keep for keep, _ in out]
        masks = []
        for (section, _), para, ranges, keep in zip(
            row["pages"], row["paras"], row["sentences"], row["keep"], strict=True
        ):
            if not keep:
                masks.append([False] * len(ranges))
                continue
            async with gate:
                got = await squire.select_sentences(
                    purpose=row["question"], title=section, sentences=[para[a:b] for a, b in ranges]
                )
            masks.append([k for k, _ in got])
        row["keep_s"] = masks

    await asyncio.gather(*(one(r) for r in rows))
    if squire.exhausted:
        raise SystemExit(f"the {CAP_USD} USD cap was reached: answers so far are recorded")
    return squire


def score(rows: list[dict[str, Any]], masks: list[list[list[bool]]]) -> dict[str, float]:
    all_ = any_ = share = 0.0
    for row, mask in zip(rows, masks, strict=True):
        hits = [
            m
            for ms, gs in zip(mask, row["gold_s"], strict=True)
            for m, g in zip(ms, gs, strict=True)
            if g
        ]
        all_ += all(hits)
        any_ += any(hits)
        total = sum(len(p) for p in row["paras"])
        kept = sum(
            b - a
            for ms, ranges in zip(mask, row["sentences"], strict=True)
            for m, (a, b) in zip(ms, ranges, strict=True)
            if m
        )
        share += kept / total
    n = len(rows)
    return {
        "all_gold": round(all_ / n, 4),
        "any_gold": round(any_ / n, 4),
        "kept_share": round(share / n, 4),
        "n": n,
    }


def bm25_masks(rows: list[dict[str, Any]], budgets: list[int]) -> list[list[list[bool]]]:
    out = []
    for row, budget in zip(rows, budgets, strict=True):
        flat = [(i, j) for i, r in enumerate(row["sentences"]) for j in range(len(r))]
        texts = [row["paras"][i][slice(*row["sentences"][i][j])] for i, j in flat]
        scores = ld.triage_run.bm25_scores(row["question"], texts)
        chosen, used = set(), 0
        for k in sorted(range(len(flat)), key=lambda k: scores[k], reverse=True):
            if used >= budget:
                break
            chosen.add(flat[k])
            used += len(texts[k])
        out.append(
            [[(i, j) in chosen for j in range(len(r))] for i, r in enumerate(row["sentences"])]
        )
    return out


def kept_chars(row: dict[str, Any], mask: list[list[bool]]) -> int:
    return sum(
        b - a
        for ms, ranges in zip(mask, row["sentences"], strict=True)
        for m, (a, b) in zip(ms, ranges, strict=True)
        if m
    )


def analyze(rows: list[dict[str, Any]], excluded: list[str], calls: int) -> dict[str, Any]:
    ms_masks = [r["keep_s"] for r in rows]
    m_masks = [[[k] * len(s) for k, s in zip(r["keep"], r["sentences"], strict=True)] for r in rows]
    ms = score(rows, ms_masks)
    bm25 = score(
        rows, bm25_masks(rows, [kept_chars(r, m) for r, m in zip(rows, ms_masks, strict=True)])
    )
    report = {
        "questions": len(rows),
        "excluded": sorted(excluded),
        "sentences_per_paper": round(
            sum(sum(map(len, r["sentences"])) for r in rows) / len(rows), 1
        ),
        "gold_sentences_per_question": round(
            sum(sum(map(sum, r["gold_s"])) for r in rows) / len(rows), 2
        ),
        "M": score(rows, m_masks),
        "MS": ms,
        "BM25_sentences": bm25,
        "P30": ms["all_gold"] >= 0.85 and ms["kept_share"] <= 0.25,
        "P31_ms_minus_bm25": round(ms["all_gold"] - bm25["all_gold"], 4),
        "select_sentences_calls": calls,
    }
    report["P31"] = report["P31_ms_minus_bm25"] >= 0.10
    report["verdict"] = (
        "two stages make whole papers small" if report["P30"] and report["P31"] else "see criteria"
    )
    return report


def write_hash(target: pathlib.Path, value: str) -> None:
    if target.exists() and target.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit(f"{target.name} already holds a different hash: nothing written")
    target.write_text(value + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--qasper", default="")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.record_hash:
        write_hash(RESULTS / "prereg-sentences.sha256", digest())
        print(digest())
        return 0
    path = pathlib.Path(args.qasper)
    papers = {
        p["id"]: p
        for p in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x)
    }
    rows, excluded = enrich(ld.build(path), papers)
    live = None
    if args.live:
        registered = RESULTS / "prereg-sentences.sha256"
        if not registered.exists() or registered.read_text().strip() != digest():
            raise SystemExit("prereg-sentences.md missing or changed: nothing spent")
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key and args.env_file:
            text = pathlib.Path(args.env_file).read_text(encoding="utf-8")
            key = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")
        live = RecordingDecider(create("jev", api_key=key), FIXTURE)
    tournament = ld.triage_run.ReplayFirst(RecordedDecider.from_file(ld.FIXTURE), None)
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else RecordedDecider([])
    sentences = ld.triage_run.ReplayFirst(recorded, live)
    asyncio.run(ask(rows, tournament, sentences))
    print(
        f"tournament missing {tournament.missing}; sentences live {sentences.asked}, "
        f"missing {sentences.missing}",
        file=sys.stderr,
    )
    if tournament.missing or sentences.missing:
        print("INCOMPLETE: some calls have no answer", file=sys.stderr)
        return 1
    calls = sum(sum(r["keep"]) for r in rows)
    report = analyze(rows, excluded, calls)
    (RESULTS / "sentences-analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
