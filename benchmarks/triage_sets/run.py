"""Page triage on multi-part questions: HotpotQA, labels by construction.

    python benchmarks/triage_sets/run.py --hash [--record-hash]
    python benchmarks/triage_sets/run.py --live --hotpot FILE.jsonl --env-file PATH/TO/.env
    python benchmarks/triage_sets/run.py --analyze --hotpot FILE.jsonl     # free, from recordings

The design, the sample, the split, the rule that sets each knob and the verdict are fixed in
`docs/results/2026-09-25-triage/prereg.md`. `--live` refuses to spend if that file or
`points/triage.py` changed since `--record-hash`.

HotpotQA is read from a local JSONL export of the Hugging Face parquet; it is not
redistributed. This directory keeps answers, keys and the analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import pathlib
import random
import re
import sys
from collections import Counter
from dataclasses import replace
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.points import triage  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-25-triage"
PREREG = RESULTS / "prereg.md"
PREREG_HASH = RESULTS / "prereg.sha256"
FIXTURE = ROOT / "fixtures" / "triage-sets.jsonl"
SAMPLE = 300
SEED = 2026
STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "or",
        "with",
        "by",
        "from",
        "at",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "how",
        "did",
        "does",
        "do",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "his",
        "her",
        "their",
        "than",
        "same",
        "both",
    ]
)


def prereg_hash() -> str:
    digest = hashlib.sha256()
    for path in (PREREG, ROOT / "src" / "sanchopanza" / "points" / "triage.py"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def require_prereg() -> None:
    if not PREREG_HASH.exists() or PREREG_HASH.read_text().strip() != prereg_hash():
        raise SystemExit("pre-registration missing or changed: nothing spent")


# --- data ----------------------------------------------------------------------------------


def load(
    path: pathlib.Path, *, seed: int = SEED, exclude: frozenset[str] = frozenset()
) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ten = [r for r in rows if len(r["context"]["title"]) == 10 and r["id"] not in exclude]
    picked = random.Random(seed).sample(ten, SAMPLE)
    questions = []
    for r in picked:
        titles = r["context"]["title"]
        texts = [" ".join(s.strip() for s in sents) for sents in r["context"]["sentences"]]
        gold = set(r["supporting_facts"]["title"])
        questions.append(
            {
                "id": r["id"],
                "question": r["question"],
                "type": r["type"],
                "pages": list(zip(titles, texts, strict=True)),
                "gold": [t in gold for t in titles],
            }
        )
    return questions


def half(q: dict[str, Any]) -> str:
    return (
        "derivation"
        if int(hashlib.sha256(q["id"].encode()).hexdigest()[:8], 16) % 2 == 0
        else "held_out"
    )


# --- the four arms -------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOP]


def bm25_scores(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    tokenised = [_words(d) for d in docs]
    avg = sum(len(t) for t in tokenised) / len(tokenised)
    df = Counter(w for t in tokenised for w in set(t))
    n = len(docs)
    scores = []
    for t in tokenised:
        tf = Counter(t)
        s = 0.0
        for w in set(_words(query)):
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(t) / avg))
        scores.append(s)
    return scores


async def answers(
    questions: list[dict[str, Any]], decider: Any, *, ask_set: bool = True
) -> list[dict[str, Any]]:
    """Every raw number each arm needs, one row per question."""
    # The per-job cap (400 decisions, 0.10 USD) is right in production and wrong here: it made
    # the first run of 2026-09-25 stop asking after 400 decisions and answer the rest with
    # empty decisions, which keep every page. Every other threshold stays the shipped one.
    squire = Squire(decider, thresholds=replace(Thresholds(), max_decisions=1_000_000, max_usd=5.0))
    gate = asyncio.Semaphore(8)

    async def page(q: dict[str, Any], title: str, text: str) -> tuple[bool, float, float]:
        async with gate:
            shipped = await squire.triage_page(purpose=q["question"], title=title, text=text)
            state, qs = triage.contribution_questions(purpose=q["question"], title=title, text=text)
            d = await squire.decide("triage_contribution", state, qs)
        c = d.answer("contributes")
        return shipped.keep, shipped.relevance, (c.truth if c.truth is not None else float("nan"))

    async def one(q: dict[str, Any]) -> dict[str, Any]:
        per_page = await asyncio.gather(*(page(q, t, x) for t, x in q["pages"]))
        dist: dict[str, float] = {}
        if ask_set:
            state, qs = triage.set_questions(purpose=q["question"], pages=q["pages"])
            async with gate:
                d = await squire.decide("triage_set", state, qs)
            dist = dict(d.answer("needed").probabilities)
        return {
            "id": q["id"],
            "type": q["type"],
            "half": half(q),
            "gold": q["gold"],
            "chars": [len(x) for _, x in q["pages"]],
            "shipped_keep": [p[0] for p in per_page],
            "relevance": [p[1] for p in per_page],
            "contributes": [p[2] for p in per_page],
            "set": [dist.get(triage.page_id(i)) for i in range(len(q["pages"]))],
            "bm25": bm25_scores(q["question"], [f"{t} {x}" for t, x in q["pages"]]),
        }

    rows = list(await asyncio.gather(*(one(q) for q in questions)))
    if squire.exhausted:
        raise SystemExit("the squire's budget ran out: the rows are not answers")
    return rows


# --- the analysis --------------------------------------------------------------------------


def keep_by(row: dict[str, Any], arm: str, knob: float) -> list[bool]:
    if arm == "shipped":
        return row["shipped_keep"]
    if arm == "shipped_derived":
        return [r >= knob for r in row["relevance"]]
    if arm == "contribution":
        return [not (c < knob) for c in row["contributes"]]  # NaN keeps: no data, no drop
    if arm == "set":
        if any(s is None for s in row["set"]):
            return [True] * len(row["set"])
        return [s >= knob for s in row["set"]]
    order = sorted(range(len(row["bm25"])), key=lambda i: -row["bm25"][i])
    top = set(order[: int(knob)])
    return [i in top for i in range(len(row["bm25"]))]


def score(rows: list[dict[str, Any]], arm: str, knob: float) -> dict[str, float]:
    joint = gold_hit = gold_n = 0
    share = 0.0
    for r in rows:
        keep = keep_by(r, arm, knob)
        hits = [k for k, g in zip(keep, r["gold"], strict=True) if g]
        joint += all(hits)
        gold_hit += sum(hits)
        gold_n += len(hits)
        share += sum(c for c, k in zip(r["chars"], keep, strict=True) if k) / sum(r["chars"])
    n = len(rows)
    return {
        "joint_recall": round(joint / n, 4),
        "gold_recall": round(gold_hit / gold_n, 4),
        "kept_share": round(share / n, 4),
        "n": n,
    }


GRIDS: dict[str, list[float]] = {
    "shipped": [0.0],
    "shipped_derived": [round(i * 0.01, 2) for i in range(0, 101)],
    "contribution": [round(i * 0.01, 2) for i in range(0, 101)],
    "set": [round(i * 0.01, 2) for i in range(0, 51)],
    "bm25": [float(k) for k in range(1, 11)],
}


def derive(rows: list[dict[str, Any]], arm: str) -> float:
    scored = [(knob, score(rows, arm, knob)) for knob in GRIDS[arm]]
    reaching = [(s["kept_share"], knob) for knob, s in scored if s["joint_recall"] >= 0.95]
    if reaching:
        return min(reaching)[1]
    return max(scored, key=lambda ks: (ks[1]["joint_recall"], -ks[1]["kept_share"]))[0]


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    derivation = [r for r in rows if r["half"] == "derivation"]
    held = [r for r in rows if r["half"] == "held_out"]
    out: dict[str, Any] = {"prereg_sha256": prereg_hash(), "n": len(rows), "arms": {}}
    for arm in GRIDS:
        knob = derive(derivation, arm)
        out["arms"][arm] = {
            "knob": knob,
            "held_out": score(held, arm, knob),
            "held_out_bridge": score([r for r in held if r["type"] == "bridge"], arm, knob),
            "held_out_comparison": score([r for r in held if r["type"] == "comparison"], arm, knob),
        }
    a = out["arms"]
    b, c, d, s = (
        a["contribution"]["held_out"],
        a["set"]["held_out"],
        a["bm25"]["held_out"],
        a["shipped"]["held_out"],
    )
    p3 = (
        b["joint_recall"] >= 0.90
        and b["kept_share"] <= 0.50
        and b["joint_recall"] - s["joint_recall"] >= 0.10
    )
    p4 = c["joint_recall"] >= 0.90 and c["kept_share"] <= 0.40
    best = min(
        (x for x in (b, c) if x["joint_recall"] >= d["joint_recall"] - 0.02),
        key=lambda x: x["kept_share"],
        default=None,
    )
    p5 = best is not None and d["kept_share"] - best["kept_share"] >= 0.05
    out["P3"], out["P4"], out["P5"] = p3, p4, p5
    out["verdict"] = (
        "solid"
        if (p3 or p4) and p5
        else "works but a free baseline does it"
        if (p3 or p4)
        else "negative"
    )
    return out


class ReplayFirst:
    """Recording first; live (throttled, retried) only for what is missing; counts both."""

    name = "jev"
    PER_SECOND = 12.0

    def __init__(self, recorded: RecordedDecider, live: Any | None) -> None:
        self._recorded = recorded
        self._live = live
        self._lock = asyncio.Lock()
        self._next = 0.0
        self.asked = 0
        self.missing = 0

    async def _turn(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            wait = self._next - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            self._next = max(loop.time(), self._next) + 1.0 / self.PER_SECOND

    async def decide(self, point: str, state: Any, qs: Any) -> Any:
        d = await self._recorded.decide(point, state, qs)
        if d.answers:
            return d
        if self._live is not None:
            for attempt in range(4):
                await self._turn()
                try:
                    d = await self._live.decide(point, state, qs)
                    self.asked += 1
                    if d.answers:
                        return d
                except Exception:  # noqa: BLE001 - counted below, never silent
                    await asyncio.sleep(2**attempt)
        self.missing += 1
        return d


CONFIRM_SEED = 2027
CONFIRM_CUT = 0.28  # derived on all 300 first-run questions (prereg-confirm.md)
CONFIRM_SHIPPED_DERIVED = 0.04
CONFIRM_PREREG = RESULTS / "prereg-confirm.md"
CONFIRM_HASH = RESULTS / "prereg-confirm.sha256"


def require_confirm() -> None:
    digest = hashlib.sha256(CONFIRM_PREREG.read_bytes()).hexdigest()
    if not CONFIRM_HASH.exists() or CONFIRM_HASH.read_text().strip() != digest:
        raise SystemExit("prereg-confirm.md missing or changed: nothing spent")


def confirm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    contribution = score(rows, "contribution", CONFIRM_CUT)
    k = next(
        (
            float(k)
            for k in range(1, 11)
            if score(rows, "bm25", float(k))["kept_share"] >= contribution["kept_share"]
        ),
        10.0,
    )
    bm25 = score(rows, "bm25", k)
    shipped = score(rows, "shipped", 0.0)
    shipped_derived = score(rows, "shipped_derived", CONFIRM_SHIPPED_DERIVED)
    p6 = (
        contribution["joint_recall"] >= 0.90
        and contribution["joint_recall"] >= bm25["joint_recall"] + 0.10
    )
    p7 = contribution["joint_recall"] >= shipped["joint_recall"] + 0.50
    by_type = {
        t: {
            "contribution": score([r for r in rows if r["type"] == t], "contribution", CONFIRM_CUT),
            "bm25": score([r for r in rows if r["type"] == t], "bm25", k),
            "shipped": score([r for r in rows if r["type"] == t], "shipped", 0.0),
        }
        for t in ("bridge", "comparison")
    }
    return {
        "n": len(rows),
        "contribution_cut": CONFIRM_CUT,
        "contribution": contribution,
        "bm25_k": k,
        "bm25": bm25,
        "shipped_045": shipped,
        "shipped_004": shipped_derived,
        "by_type": by_type,
        "P6": p6,
        "P7": p7,
        "verdict": "confirmed" if p6 and p7 else "not confirmed",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hash", action="store_true")
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--confirm", action="store_true", help="the run of prereg-confirm.md")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.hash:
        print(prereg_hash())
        if args.record_hash:
            PREREG_HASH.write_text(prereg_hash() + "\n", encoding="utf-8")
            print("recorded")
        return 0
    questions = load(pathlib.Path(args.hotpot))
    if args.confirm:
        first = frozenset(q["id"] for q in questions)
        questions = load(pathlib.Path(args.hotpot), seed=CONFIRM_SEED, exclude=first)
    recorded = RecordedDecider.from_file(FIXTURE)
    live = None
    if args.live:
        require_prereg()
        if args.confirm:
            require_confirm()
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key and args.env_file:
            text = pathlib.Path(args.env_file).read_text(encoding="utf-8")
            key = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")
        live = RecordingDecider(create("jev", api_key=key), FIXTURE)
    replay = ReplayFirst(recorded, live)
    rows = asyncio.run(answers(questions, replay, ask_set=not args.confirm))
    for _ in range(3):
        if not (live and replay.missing):
            break
        print(f"{replay.missing} decisions missing; asking again", file=sys.stderr)
        replay = ReplayFirst(RecordedDecider.from_file(FIXTURE), live)
        rows = asyncio.run(answers(questions, replay, ask_set=not args.confirm))
    print(f"live decisions this run: {replay.asked}, missing: {replay.missing}", file=sys.stderr)
    if replay.missing:
        # The run of 2026-09-25 that hit the rate limit reported "negative" from answers
        # that were never given: a missing answer keeps the page, so every arm kept
        # everything. No verdict is printed while any answer is missing.
        print("INCOMPLETE: no verdict. Re-run --live to fill the gaps.", file=sys.stderr)
        return 1
    if args.confirm:
        report = confirm(rows)
        (RESULTS / "confirm-analysis.json").write_text(json.dumps(report, indent=1), "utf-8")
        (RESULTS / "confirm-rows.json").write_text(json.dumps(rows), encoding="utf-8")
        print(json.dumps(report, indent=1))
        return 0
    report = analyze(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (RESULTS / "rows.json").write_text(json.dumps(rows), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
