"""A tournament of in-context calls over 100 pages (`docs/results/2026-09-27-hierarchy/prereg.md`).

python benchmarks/hierarchy/run.py --record-hash
python benchmarks/hierarchy/run.py --live --hotpot FILE.jsonl --env-file PATH/TO/.env
python benchmarks/hierarchy/run.py --hotpot FILE.jsonl            # free, from recordings
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


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


confirm = _load("chunk_confirm", ROOT / "benchmarks" / "chunks" / "confirm.py")
chunk_run = confirm.chunk_run
triage_run = chunk_run.triage_run

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.points import chunks, hierarchy  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-27-hierarchy"
FIXTURE = ROOT / "fixtures" / "hierarchy.jsonl"
SEED = 2029
PAGES = 100
DERIVATION = 100
FINAL_CUT = 0.40
GROUP = chunks.PAGE_MAX
HASHED = (
    RESULTS / "prereg.md",
    ROOT / "src" / "sanchopanza" / "points" / "hierarchy.py",
    ROOT / "src" / "sanchopanza" / "points" / "chunks.py",
)


def prereg_hash() -> str:
    digest = hashlib.sha256()
    for path in HASHED:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != prereg_hash():
        raise SystemExit("prereg.md, hierarchy.py or chunks.py changed: nothing spent")


def used_ids(hotpot: pathlib.Path) -> set[str]:
    earlier = chunk_run.samples(hotpot)
    old = earlier["derivation"] + earlier["held_out"]
    third = confirm.fresh(hotpot, {r["id"] for r in old})
    return {r["id"] for r in old + third}


def build(hotpot: pathlib.Path) -> list[dict[str, Any]]:
    raw = [json.loads(x) for x in hotpot.read_text(encoding="utf-8").splitlines() if x]
    used = used_ids(hotpot)
    pool = [r for r in raw if len(r["context"]["title"]) == 10 and r["id"] not in used]
    chosen = random.Random(SEED).sample(pool, 300)
    chosen_ids = {r["id"] for r in chosen}
    donors = [
        (t, " ".join(s.strip() for s in sents))
        for r in raw
        if r["id"] not in chosen_ids and r["id"] not in used
        for t, sents in zip(r["context"]["title"], r["context"]["sentences"], strict=True)
    ]
    rows = []
    for r in chosen:
        rng = random.Random(f"{SEED}-{r['id']}")
        own_titles = set(r["context"]["title"])
        gold_titles = set(r["supporting_facts"]["title"])
        own = [
            (t, " ".join(s.strip() for s in sents), t in gold_titles)
            for t, sents in zip(r["context"]["title"], r["context"]["sentences"], strict=True)
        ]
        extra: list[tuple[str, str, bool]] = []
        while len(extra) < PAGES - len(own):
            t, x = donors[rng.randrange(len(donors))]
            if t not in own_titles and all(t != e[0] for e in extra):
                extra.append((t, x, False))
        pages = own + extra
        rng.shuffle(pages)
        rows.append(
            {
                "id": r["id"],
                "question": r["question"],
                "pages": [(t, x) for t, x, _ in pages],
                "gold": [g for _, _, g in pages],
            }
        )
    return rows


def squire_for(decider: Any) -> Squire:
    return Squire(decider, thresholds=replace(Thresholds(), max_decisions=1_000_000, max_usd=5.0))


def judge_for(squire: Squire, row: dict[str, Any], gate: asyncio.Semaphore) -> Any:
    async def judge(ids: list[int]) -> list[float | None]:
        state, qs = chunks.context_questions(
            purpose=row["question"], pages=[row["pages"][i] for i in ids]
        )
        async with gate:
            d = await squire.decide("hierarchy_context", state, qs)
        return [d.answer(chunks.page_id(k)).truth for k in range(len(ids))]

    return judge


async def round_one(rows: list[dict[str, Any]], decider: Any) -> None:
    squire, gate = squire_for(decider), asyncio.Semaphore(8)

    async def one(row: dict[str, Any]) -> None:
        judge = judge_for(squire, row, gate)
        probs, _ = await hierarchy._judge_all(list(range(PAGES)), judge, GROUP)
        row["p1"] = [probs[i] for i in range(PAGES)]

    await asyncio.gather(*(one(r) for r in rows))


def derive_r1(rows: list[dict[str, Any]]) -> float:
    best = 0.0
    for step in range(41):
        cut = round(step * 0.01, 2)
        kept = sum(
            all(p is None or p >= cut for p, g in zip(r["p1"], r["gold"], strict=True) if g)
            for r in rows
        )
        if kept / len(rows) >= 0.99:
            best = cut
    return best


async def final_round(rows: list[dict[str, Any]], decider: Any, r1: float) -> None:
    squire, gate = squire_for(decider), asyncio.Semaphore(8)

    async def one(row: dict[str, Any]) -> None:
        survivors = [i for i, p in enumerate(row["p1"]) if p is None or p >= r1]
        judge = judge_for(squire, row, gate)
        probs, calls = await hierarchy._judge_all(survivors, judge, GROUP) if survivors else ({}, 0)
        row["p2"] = [probs.get(i) if i in probs else "out" for i in range(PAGES)]
        row["final_calls"] = calls

    await asyncio.gather(*(one(r) for r in rows))


def keep(row: dict[str, Any], arm: str, k: int = 0) -> list[bool]:
    p1, p2 = row["p1"], row.get("p2")

    def ok(p: float | None) -> bool:
        return p is None or p >= FINAL_CUT

    if arm == "FLAT":
        return [ok(p) for p in p1]
    if arm == "TOUR":
        return [p != "out" and ok(p) for p in p2]
    if arm == "BLEND":
        return [
            p != "out" and (ok(p) if p is None or a is None else 0.5 * a + 0.5 * p >= FINAL_CUT)
            for a, p in zip(p1, p2, strict=True)
        ]
    scores = row.setdefault(
        "_bm25", triage_run.bm25_scores(row["question"], [f"{t} {x}" for t, x in row["pages"]])
    )
    top = set(sorted(range(PAGES), key=lambda i: scores[i], reverse=True)[:k])
    return [i in top for i in range(PAGES)]


def score(rows: list[dict[str, Any]], arm: str, k: int = 0) -> dict[str, float]:
    joint = share = pages = 0.0
    for row in rows:
        mask = keep(row, arm, k)
        joint += all(m for m, g in zip(mask, row["gold"], strict=True) if g)
        sizes = [len(t) + len(x) for t, x in row["pages"]]
        share += sum(s for s, m in zip(sizes, mask, strict=True) if m) / sum(sizes)
        pages += sum(mask)
    n = len(rows)
    return {
        "page_joint": round(joint / n, 4),
        "kept_share": round(share / n, 4),
        "pages_kept": round(pages / n, 2),
        "n": n,
    }


def analyze(rows: list[dict[str, Any]], r1: float) -> dict[str, Any]:
    held = rows[DERIVATION:]
    tour = score(held, "TOUR")
    k = math.ceil(tour["pages_kept"])
    report: dict[str, Any] = {
        "r1_from_derivation": r1,
        "final_cut": FINAL_CUT,
        "held_out": {
            "FLAT": score(held, "FLAT"),
            "TOUR": tour,
            "BLEND": score(held, "BLEND"),
            f"BM25_top{k}": score(held, "BM25", k),
        },
        "derivation": {
            "FLAT": score(rows[:DERIVATION], "FLAT"),
            "TOUR": score(rows[:DERIVATION], "TOUR"),
        },
        "calls_per_question": round(
            sum(len(hierarchy.groups(PAGES, GROUP)) + r["final_calls"] for r in held) / len(held), 2
        ),
    }
    h = report["held_out"]
    report["P25"] = tour["page_joint"] >= 0.95 and tour["kept_share"] <= 0.08
    report["P26"] = (
        tour["page_joint"] >= h["FLAT"]["page_joint"] - 0.01
        and tour["kept_share"] < h["FLAT"]["kept_share"]
    )
    report["P27_tour_minus_bm25"] = round(tour["page_joint"] - h[f"BM25_top{k}"]["page_joint"], 4)
    report["verdict"] = "confirmed" if report["P25"] and report["P26"] else "not confirmed"
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
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.record_hash:
        write_hash(RESULTS / "prereg.sha256", prereg_hash())
        print(prereg_hash())
        return 0
    rows = build(pathlib.Path(args.hotpot))
    live = None
    if args.live:
        require_prereg()
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key and args.env_file:
            text = pathlib.Path(args.env_file).read_text(encoding="utf-8")
            key = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")
        live = RecordingDecider(create("jev", api_key=key), FIXTURE)
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else RecordedDecider([])
    replay = triage_run.ReplayFirst(recorded, live)

    async def both() -> float:
        await round_one(rows, replay)
        r1 = derive_r1(rows[:DERIVATION])
        await final_round(rows, replay, r1)
        return r1

    r1 = asyncio.run(both())
    gaps = sum(p is None for r in rows for p in r["p1"])
    print(
        f"live calls {replay.asked}, unanswered pages {gaps}, missing {replay.missing}",
        file=sys.stderr,
    )
    if replay.missing or gaps:
        print("INCOMPLETE: some calls have no answer", file=sys.stderr)
        return 1
    report = analyze(rows, r1)
    (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
