"""Answer QASPER questions from the whole paper and from what GW keeps (`prereg-answers.md`).

python benchmarks/lateral/wholedocs/answers.py --record-hash
python benchmarks/lateral/wholedocs/answers.py --pilot --live --qasper QASPER-TEST.jsonl
python benchmarks/lateral/wholedocs/answers.py --live --qasper QASPER-TEST.jsonl
python benchmarks/lateral/wholedocs/answers.py --qasper QASPER-TEST.jsonl        # free, cache

Kept sets are rebuilt from `fixtures/lateral-wholedocs.jsonl` with the frozen rule. Every answer
goes through our own evaluation harness (`sanchopanza.eval.harness`, not distributed) and is
cached in `fixtures/cli/lateral-wholedocs-answers.jsonl`. Not directly comparable with answers
obtained through the API.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import pathlib
import random
import re
import string
import sys
from collections import Counter
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


confirm = _load("wholedocs_confirm", HERE / "confirm.py")
data, rules, ledger = confirm.data, confirm.rules, confirm.ledger

from sanchopanza.eval import harness as _harness  # noqa: E402
from sanchopanza.eval.stats import bootstrap_difference  # noqa: E402

_h = _harness.load()
CeilingReached, ClaudeCLI, SessionCache = _h.CeilingReached, _h.ClaudeCLI, _h.SessionCache
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

RESULTS = confirm.RESULTS
PREREG = RESULTS / "prereg-answers.md"
CACHE = ROOT / "fixtures" / "cli" / "lateral-wholedocs-answers.jsonl"
MODEL = "claude-haiku-4-5-20251001"
SYSTEM = (
    "Answer the question using only the paper text given. Reply with the answer only: a short "
    "phrase, a short list of phrases, a number, or yes or no. If the text does not contain the "
    "answer, reply: unknown."
)
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
ARMS = ("FULL", "GW")
ORDER_SEED = 2033
PILOT = 10
CEILING_USD = 4.50
BUDGET_FOR_N_USD = 4.30
SAFETY = 1.15
SESSION_MAX_USD = 0.15
CONCURRENCY = 4


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg-answers.sha256"
    if not registered.exists() or registered.read_text().strip() != digest():
        raise SystemExit("prereg-answers.md missing or changed: nothing spent")


# --- QASPER's answer F1 (normalisation as in the official evaluator) -------------------------


def normalise(text: str) -> str:
    text = text.lower()
    text = "".join(c for c in text if c not in set(string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def token_f1(reply: str, gold: str) -> float:
    r, g = normalise(reply).split(), normalise(gold).split()
    common = sum((Counter(r) & Counter(g)).values())
    if not r or not g or not common:
        return float(r == g)
    precision, recall = common / len(r), common / len(g)
    return 2 * precision * recall / (precision + recall)


def references(paper: dict[str, Any], question: str) -> list[str]:
    """Every annotator's answer to `question`, as QASPER's evaluator builds them."""
    asked = [q.strip() for q in paper["qas"]["question"]]
    out = []
    for answer in paper["qas"]["answers"][asked.index(question)]["answer"]:
        if answer.get("unanswerable"):
            continue
        if answer.get("yes_no") is not None:
            out.append("Yes" if answer["yes_no"] else "No")
        elif answer.get("extractive_spans"):
            out.append(", ".join(s.strip() for s in answer["extractive_spans"]))
        elif (answer.get("free_form_answer") or "").strip():
            out.append(answer["free_form_answer"].strip())
    return out


def f1(reply: str, refs: list[str]) -> float:
    return max((token_f1(reply, g) for g in refs), default=0.0)


# --- prompts ---------------------------------------------------------------------------------


def prompt_full(row: dict[str, Any]) -> str:
    blocks = [
        f"{section}: {para}" if section else para
        for (section, _), para in zip(row["pages"], row["paras"], strict=True)
    ]
    return "\n\n".join(blocks) + f"\n\nQuestion: {row['question']}"


def prompt_kept(row: dict[str, Any], mask: list[list[bool]]) -> str:
    blocks = []
    for (section, _), para, ranges, kept in zip(
        row["pages"], row["paras"], row["sentences"], mask, strict=True
    ):
        text = " ".join(para[a:b] for (a, b), k in zip(ranges, kept, strict=True) if k)
        if text:
            blocks.append(f"{section}: {text}" if section else text)
    return "\n\n".join(blocks) + f"\n\nQuestion: {row['question']}"


def ordered_rows(qasper: pathlib.Path) -> list[dict[str, Any]]:
    rows = confirm.build(qasper)
    recorded = RecordedDecider.from_file(confirm.FIXTURE)
    replay = data.ld.triage_run.ReplayFirst(recorded, None)
    asyncio.run(data.probe(rows, replay, replay))
    if replay.missing:
        raise SystemExit("the whole-document recordings do not cover the 219 questions")
    rows.sort(key=lambda r: (r["id"], r["question"]))
    random.Random(ORDER_SEED).shuffle(rows)
    return rows


def items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        mask = rules.document_mask(row["keep"], row["para_final"], row["p_s"], confirm.FROZEN)
        qid = f"{row['id']}|{row['question']}"
        out.append({"qid": qid, "arm": "FULL", "user": prompt_full(row)})
        out.append({"qid": qid, "arm": "GW", "user": prompt_kept(row, mask)})
    return out


def cached(cache: SessionCache, item: dict[str, Any]) -> Any:
    return cache.get(SessionCache.key(MODEL, SYSTEM, SCHEMA, item["user"]))


async def ask(todo: list[dict[str, Any]], live: bool) -> list[dict[str, Any]]:
    cache = SessionCache(CACHE)
    if not live:
        absent = [t for t in todo if cached(cache, t) is None]
        if absent:
            raise SystemExit(f"{len(absent)} prompts not in the cache; run with --live")
    cli = ClaudeCLI(
        model=MODEL,
        system=SYSTEM,
        ceiling_usd=CEILING_USD,
        max_budget_usd=SESSION_MAX_USD,
        concurrency=CONCURRENCY,
        cache=cache,
        count_cached=True,
    )

    async def one(item: dict[str, Any]) -> dict[str, Any]:
        session = await cli.run(item["user"], schema=SCHEMA)
        if not (session.ok and session.structured is not None):
            session = await cli.run(item["user"], schema=SCHEMA)  # one retry, registered
        ok = session.ok and session.structured is not None
        return {
            **{k: item[k] for k in ("qid", "arm")},
            "ok": ok,
            "reply": str((session.structured or {}).get("answer", "")) if ok else "",
            "input_tokens": session.input_tokens
            + session.cache_read_tokens
            + session.cache_write_tokens,
            "list_cost_usd": session.list_cost_usd,
            "reason": session.reason,
        }

    try:
        out = await asyncio.gather(*(one(t) for t in todo))
    except CeilingReached as stop:
        raise SystemExit(f"ceiling reached, answers so far are cached: {stop}") from stop
    print(
        f"spawned {cli.spawned}, spent {cli.spent_usd:.3f} USD list (cache counted)",
        file=sys.stderr,
    )
    return list(out)


def size_from_pilot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """N from the pilot's measured cost, by the registered rule."""
    cache = SessionCache(CACHE)
    pilot = items(rows[:PILOT])
    got = [cached(cache, t) for t in pilot]
    if any(s is None for s in got):
        raise SystemExit("run the pilot first (--pilot --live)")
    spent = sum(s.list_cost_usd for s in got)
    per_question = spent / PILOT
    n = min(len(rows), math.floor(BUDGET_FOR_N_USD / (SAFETY * per_question)))
    return {"pilot_usd": round(spent, 4), "per_question_usd": round(per_question, 5), "n": n}


def analyze(
    rows: list[dict[str, Any]], answers: list[dict[str, Any]], papers: dict[str, Any]
) -> dict[str, Any]:
    by = {(a["qid"], a["arm"]): a for a in answers}
    refs = {f"{r['id']}|{r['question']}": references(papers[r["id"]], r["question"]) for r in rows}
    both = [q for q in refs if all(by.get((q, arm), {}).get("ok") for arm in ARMS)]
    scores = {arm: [f1(by[(q, arm)]["reply"], refs[q]) for q in both] for arm in ARMS}
    report: dict[str, Any] = {
        "model": MODEL,
        "path": "claude code cli, one short field",
        "questions": len(refs),
        "answered_by_both": len(both),
        "excluded": sorted(set(refs) - set(both)),
        "arms": {},
    }
    for arm in ARMS:
        s = scores[arm]
        report["arms"][arm] = {
            "f1": round(sum(s) / len(s), 4),
            "exact": round(
                sum(
                    any(normalise(by[(q, arm)]["reply"]) == normalise(g) for g in refs[q])
                    for q in both
                )
                / len(both),
                4,
            ),
            "unknown": sum(normalise(by[(q, arm)]["reply"]) == "unknown" for q in both),
            "input_tokens": sum(by[(q, arm)]["input_tokens"] for q in both),
            "list_cost_usd": round(sum(by[(q, arm)]["list_cost_usd"] for q in both), 4),
        }
    # Paired difference of mean F1, bootstrap by question (continuous scores: resample means).
    diffs = [g - f for g, f in zip(scores["GW"], scores["FULL"], strict=True)]
    rng = random.Random(7)
    reps = sorted(
        sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs) for _ in range(2000)
    )
    delta = sum(diffs) / len(diffs)
    report["GW_minus_FULL_f1"] = {
        "mean": round(delta, 4),
        "ci95": [round(reps[50], 4), round(reps[1949], 4)],
    }
    hit = [x >= 0.5 for x in scores["GW"]], [x >= 0.5 for x in scores["FULL"]]
    report["f1_at_least_half_diff"] = [round(v, 4) for v in bootstrap_difference(*hit)]
    a = report["arms"]
    report["tokens_share_GW_of_FULL"] = round(
        a["GW"]["input_tokens"] / a["FULL"]["input_tokens"], 4
    )
    report["A1"] = a["GW"]["f1"] >= a["FULL"]["f1"] - 0.03
    report["A2"] = report["GW_minus_FULL_f1"]["ci95"][0] >= -0.06
    report["verdict"] = "confirmed" if report["A1"] and report["A2"] else "not confirmed"
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--qasper", default="")
    args = ap.parse_args()
    if args.record_hash:
        ledger.write_hash(RESULTS / "prereg-answers.sha256", digest())
        print(digest())
        return 0
    if args.live:
        require_prereg()
        ledger.require_cli_room(
            CEILING_USD - SessionCache(CACHE).total_cost_usd() if CACHE.exists() else CEILING_USD
        )
    qasper = pathlib.Path(args.qasper)
    rows = ordered_rows(qasper)
    if args.pilot:
        todo = items(rows[:PILOT])
        asyncio.run(ask(todo, args.live))
        print(json.dumps(size_from_pilot(rows)))
        return 0
    sizing = size_from_pilot(rows)
    chosen = rows[: sizing["n"]]
    answers = asyncio.run(ask(items(chosen), args.live))
    report = analyze(chosen, answers, data.load_papers(qasper))
    report["sizing"] = sizing
    (RESULTS / "answers-analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
