"""Sentences instead of pages, and pages judged in each other's context (`prereg.md`).

python benchmarks/chunks/run.py --hash [--record-hash]
python benchmarks/chunks/run.py --live --hotpot FILE.jsonl --env-file PATH/TO/.env
python benchmarks/chunks/run.py --analyze --hotpot FILE.jsonl       # free, from recordings
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

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks" / "triage_sets"))

# Several benches ship a `run.py`: loaded by path under its own name, never as `run`.
_spec_triage_run = importlib.util.spec_from_file_location(
    "triage_sets_run", ROOT / "benchmarks" / "triage_sets" / "run.py"
)
triage_run = importlib.util.module_from_spec(_spec_triage_run)
_spec_triage_run.loader.exec_module(triage_run)

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.points import chunks  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-27-chunks"
FIXTURE = ROOT / "fixtures" / "chunks.jsonl"
TRIAGE = ROOT / "docs" / "results" / "2026-09-25-triage"
PAGE_CUT = 0.28
TARGET = 0.90


def prereg_hash() -> str:
    digest = hashlib.sha256()
    for path in (RESULTS / "prereg.md", ROOT / "src/sanchopanza/points/chunks.py"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != prereg_hash():
        raise SystemExit("prereg.md or points/chunks.py changed: nothing spent")


def samples(hotpot: pathlib.Path) -> dict[str, list[dict[str, Any]]]:
    """Both sets, with sentences, sentence gold and the recorded page-contribution answers."""
    raw = {}
    for line in hotpot.read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            raw[r["id"]] = r
    first = triage_run.load(hotpot)
    second = triage_run.load(
        hotpot, seed=triage_run.CONFIRM_SEED, exclude=frozenset(q["id"] for q in first)
    )
    recorded = {
        r["id"]: r["contributes"]
        for f in ("rows.json", "confirm-rows.json")
        for r in json.loads((TRIAGE / f).read_text())
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for name, questions in (("derivation", first), ("held_out", second)):
        rows = []
        for q in questions:
            r = raw[q["id"]]
            titles = r["context"]["title"]
            sentences = [[s.strip() for s in sents] for sents in r["context"]["sentences"]]
            gold = set(
                zip(r["supporting_facts"]["title"], r["supporting_facts"]["sent_id"], strict=True)
            )
            rows.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "titles": titles,
                    "sentences": sentences,
                    "gold": [
                        [(t, i) in gold for i in range(len(sents))]
                        for t, sents in zip(titles, sentences, strict=True)
                    ],
                    "page_contributes": recorded[q["id"]],
                }
            )
        out[name] = rows
    return out


async def ask(rows: list[dict[str, Any]], decider: Any) -> None:
    """Add `sentence_p` (per page, per sentence) and `context_p` (per page) to each row."""
    squire = Squire(decider, thresholds=replace(Thresholds(), max_decisions=1_000_000, max_usd=5.0))
    gate = asyncio.Semaphore(8)

    async def page(row: dict[str, Any], j: int) -> list[float | None]:
        state, qs = chunks.sentence_questions(
            purpose=row["question"], title=row["titles"][j], sentences=row["sentences"][j]
        )
        async with gate:
            d = await squire.decide("chunk_sentences", state, qs)
        return [d.answer(chunks.sentence_id(i)).truth for i in range(len(row["sentences"][j]))]

    async def context(row: dict[str, Any]) -> list[float | None]:
        pages = [(t, " ".join(s)) for t, s in zip(row["titles"], row["sentences"], strict=True)]
        state, qs = chunks.context_questions(purpose=row["question"], pages=pages)
        async with gate:
            d = await squire.decide("chunk_context", state, qs)
        return [d.answer(chunks.page_id(j)).truth for j in range(len(pages))]

    async def one(row: dict[str, Any]) -> None:
        row["sentence_p"] = list(
            await asyncio.gather(*(page(row, j) for j in range(len(row["sentences"]))))
        )
        row["context_p"] = await context(row)

    await asyncio.gather(*(one(r) for r in rows))
    if squire.exhausted:
        raise SystemExit("the squire's budget ran out")


def missing(rows: list[dict[str, Any]]) -> int:
    n = sum(p is None for r in rows for page in r["sentence_p"] for p in page)
    return n + sum(p is None for r in rows for p in r["context_p"])


# --- the arms, as a keep mask over sentences --------------------------------------------------


def bm25_sentence_scores(row: dict[str, Any]) -> list[list[float]]:
    flat = [
        (j, i, f"{row['titles'][j]} {s}")
        for j, sents in enumerate(row["sentences"])
        for i, s in enumerate(sents)
    ]
    scores = triage_run.bm25_scores(row["question"], [text for _, _, text in flat])
    out = [[0.0] * len(s) for s in row["sentences"]]
    for (j, i, _), score in zip(flat, scores, strict=True):
        out[j][i] = score
    return out


def mask(row: dict[str, Any], arm: str, knob: float) -> list[list[bool]]:
    sents = row["sentences"]
    if arm == "A":
        return [[row["page_contributes"][j] >= PAGE_CUT] * len(s) for j, s in enumerate(sents)]
    if arm == "B":
        return [[p is None or p >= knob for p in page] for page in row["sentence_p"]]
    if arm == "E":
        return [
            [row["page_contributes"][j] >= PAGE_CUT and (p is None or p >= knob) for p in page]
            for j, page in enumerate(row["sentence_p"])
        ]
    if arm == "C":
        return [
            [p is None or p >= knob] * len(s) for s, p in zip(sents, row["context_p"], strict=True)
        ]
    scores = row.setdefault("_bm25", bm25_sentence_scores(row))
    ranked = sorted(
        ((sc, j, i) for j, page in enumerate(scores) for i, sc in enumerate(page)), reverse=True
    )
    top = {(j, i) for _, j, i in ranked[: int(knob)]}
    return [[(j, i) in top for i in range(len(s))] for j, s in enumerate(sents)]


def score(rows: list[dict[str, Any]], arm: str, knob: float) -> dict[str, float]:
    sentence_joint = page_joint = 0
    share = 0.0
    for row in rows:
        keep = mask(row, arm, knob)
        gold_sents = [
            keep[j][i] for j, page in enumerate(row["gold"]) for i, g in enumerate(page) if g
        ]
        sentence_joint += all(gold_sents)
        gold_pages = [j for j, page in enumerate(row["gold"]) if any(page)]
        page_joint += all(any(keep[j]) for j in gold_pages)
        total = sum(len(s) for page in row["sentences"] for s in page)
        kept = sum(
            len(s)
            for j, page in enumerate(row["sentences"])
            for i, s in enumerate(page)
            if keep[j][i]
        )
        share += kept / total
    n = len(rows)
    return {
        "sentence_joint": round(sentence_joint / n, 4),
        "page_joint": round(page_joint / n, 4),
        "kept_share": round(share / n, 4),
        "n": n,
    }


GRIDS = {
    "A": [PAGE_CUT],
    "B": [round(i * 0.01, 2) for i in range(101)],
    "E": [round(i * 0.01, 2) for i in range(101)],
    "C": [round(i * 0.01, 2) for i in range(101)],
    "D": [float(k) for k in range(1, 41)],
}


def derive(rows: list[dict[str, Any]], arm: str) -> float:
    scored = [(k, score(rows, arm, k)) for k in GRIDS[arm]]
    reaching = [(s["kept_share"], k) for k, s in scored if s["sentence_joint"] >= TARGET]
    if reaching:
        return min(reaching)[1]
    return max(scored, key=lambda ks: (ks[1]["sentence_joint"], -ks[1]["kept_share"]))[0]


def analyze(sets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    derivation, held = sets["derivation"], sets["held_out"]
    arms: dict[str, Any] = {}
    for arm in ("A", "B", "E", "C"):
        knob = derive(derivation, arm)
        arms[arm] = {
            "knob": knob,
            "derivation": score(derivation, arm, knob),
            "held_out": score(held, arm, knob),
        }
    best = min(
        ("B", "E"),
        key=lambda a: (
            arms[a]["held_out"]["kept_share"]
            if arms[a]["held_out"]["sentence_joint"] >= TARGET
            else 9
        ),
    )
    b = arms[best]["held_out"]
    k = next(
        (
            float(k)
            for k in range(1, 41)
            if score(held, "D", float(k))["kept_share"] >= b["kept_share"]
        ),
        40.0,
    )
    arms["D"] = {
        "knob": k,
        "held_out": score(held, "D", k),
        "note": "k at matched budget on held-out",
    }
    arms["D_derived"] = {"knob": derive(derivation, "D")}
    arms["D_derived"]["held_out"] = score(held, "D", arms["D_derived"]["knob"])
    a, c = arms["A"]["held_out"], arms["C"]["held_out"]
    p15 = any(
        arms[x]["held_out"]["sentence_joint"] >= TARGET
        and arms[x]["held_out"]["kept_share"] <= 0.35
        for x in ("B", "E")
    )
    p16 = c["page_joint"] >= a["page_joint"] - 0.02 and c["kept_share"] <= a["kept_share"]
    p17 = b["sentence_joint"] >= arms["D"]["held_out"]["sentence_joint"] + 0.10
    return {
        "prereg_sha256": prereg_hash(),
        "arms": arms,
        "best_sentence_arm": best,
        "P15": p15,
        "P16": p16,
        "P17": p17,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("--hash", "--record-hash", "--live", "--analyze"):
        ap.add_argument(flag, action="store_true")
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.hash:
        print(prereg_hash())
        if args.record_hash:
            (RESULTS / "prereg.sha256").write_text(prereg_hash() + "\n", encoding="utf-8")
            print("recorded")
        return 0
    sets = samples(pathlib.Path(args.hotpot))
    rows = sets["derivation"] + sets["held_out"]
    live = None
    if args.live:
        require_prereg()
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key and args.env_file:
            text = pathlib.Path(args.env_file).read_text(encoding="utf-8")
            key = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")
        live = RecordingDecider(create("jev", api_key=key), FIXTURE)
    for attempt in range(3):
        replay = triage_run.ReplayFirst(RecordedDecider.from_file(FIXTURE), live)
        asyncio.run(ask(rows, replay))
        gaps = missing(rows)
        print(f"pass {attempt}: live {replay.asked}, missing answers {gaps}", file=sys.stderr)
        if not gaps or live is None:
            break
    if missing(rows):
        print("INCOMPLETE: no verdict.", file=sys.stderr)
        return 1
    report = analyze(sets)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    kept = [{k: v for k, v in r.items() if k in ("id", "sentence_p", "context_p")} for r in rows]
    (RESULTS / "answers.json").write_text(json.dumps(kept), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
