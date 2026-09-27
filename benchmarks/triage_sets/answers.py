"""Does the model still answer from what triage kept? (`prereg-answers.md`)

    python benchmarks/triage_sets/answers.py --submit  --hotpot FILE --env-file PATH/TO/.env
    python benchmarks/triage_sets/answers.py --collect --env-file PATH/TO/.env
    python benchmarks/triage_sets/answers.py --analyze --hotpot FILE        # free

Kept sets come from `confirm-rows.json`, exactly as the confirmatory run recorded them.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
import string
import sys
import time
from collections import Counter
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Several benches ship a `run.py`: loaded by path under its own name, never as `run`.
_spec_run = importlib.util.spec_from_file_location("triage_sets_run", HERE / "run.py")
run = importlib.util.module_from_spec(_spec_run)
_spec_run.loader.exec_module(run)

RESULTS = run.RESULTS
PREREG = RESULTS / "prereg-answers.md"
PREREG_HASH = RESULTS / "prereg-answers.sha256"
ANSWERS = RESULTS / "answers.jsonl"
BATCH = RESULTS / "answers-batch.json"
MODEL = "claude-haiku-4-5"
ARMS = ("all", "contribution", "shipped", "bm25")
SYSTEM = (
    "Answer the question using only the paragraphs given. Reply with the answer only: a short "
    "span, a name, a number, or yes or no. If the paragraphs do not contain the answer, reply: "
    "unknown."
)


def require_prereg() -> None:
    digest = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if not PREREG_HASH.exists() or PREREG_HASH.read_text().strip() != digest:
        raise SystemExit("prereg-answers.md missing or changed: nothing spent")


def key(env_file: str) -> str:
    text = pathlib.Path(env_file).read_text(encoding="utf-8")
    return re.search(r"^ANTHROPIC_API_KEY=(.*)$", text, re.M).group(1).strip().strip("'\"")


def cases(hotpot: pathlib.Path) -> list[dict[str, Any]]:
    first = run.load(hotpot)
    questions = run.load(hotpot, seed=run.CONFIRM_SEED, exclude=frozenset(q["id"] for q in first))
    rows = {r["id"]: r for r in json.loads((RESULTS / "confirm-rows.json").read_text())}
    k = int(json.loads((RESULTS / "confirm-analysis.json").read_text())["bm25_k"])
    out = []
    for q in questions:
        row = rows[q["id"]]
        keeps = {
            "all": [True] * len(q["pages"]),
            "contribution": run.keep_by(row, "contribution", run.CONFIRM_CUT),
            "shipped": run.keep_by(row, "shipped", 0.0),
            "bm25": run.keep_by(row, "bm25", float(k)),
        }
        for arm in ARMS:
            pages = [p for p, kept in zip(q["pages"], keeps[arm], strict=True) if kept]
            body = "\n\n".join(f"{t}: {x}" for t, x in pages)
            out.append(
                {
                    "custom_id": f"{arm}-{q['id']}",
                    "arm": arm,
                    "id": q["id"],
                    "type": q["type"],
                    "user": f"{body}\n\nQuestion: {q['question']}",
                }
            )
    return out


def gold(hotpot: pathlib.Path) -> dict[str, str]:
    rows = [json.loads(x) for x in hotpot.read_text(encoding="utf-8").splitlines() if x]
    return {r["id"]: r["answer"] for r in rows}


def normalise(text: str) -> str:
    text = text.lower()
    text = "".join(c for c in text if c not in set(string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def correct(reply: str, answer: str) -> bool:
    r, g = normalise(reply), normalise(answer)
    return bool(g) and (r == g or re.search(rf"(^|\s){re.escape(g)}(\s|$)", r) is not None)


def f1(reply: str, answer: str) -> float:
    r, g = normalise(reply).split(), normalise(answer).split()
    common = sum((Counter(r) & Counter(g)).values())
    if not r or not g or not common:
        return 0.0
    precision, recall = common / len(r), common / len(g)
    return 2 * precision * recall / (precision + recall)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--hotpot", default="")
    ap.add_argument("--env-file", default="")
    args = ap.parse_args()
    if args.submit:
        import anthropic

        require_prereg()
        client = anthropic.Anthropic(api_key=key(args.env_file))
        requests = [
            {
                "custom_id": c["custom_id"],
                "params": {
                    "model": MODEL,
                    "max_tokens": 60,
                    "system": SYSTEM,
                    "messages": [{"role": "user", "content": c["user"]}],
                },
            }
            for c in cases(pathlib.Path(args.hotpot))
        ]
        batch = client.messages.batches.create(requests=requests)
        BATCH.write_text(json.dumps({"id": batch.id, "count": len(requests)}), encoding="utf-8")
        print(f"batch {batch.id} with {len(requests)} requests")
        return 0
    if args.collect:
        import anthropic

        client = anthropic.Anthropic(api_key=key(args.env_file))
        batch_id = json.loads(BATCH.read_text())["id"]
        while client.messages.batches.retrieve(batch_id).processing_status != "ended":
            time.sleep(30)
        with ANSWERS.open("w", encoding="utf-8") as out:
            for result in client.messages.batches.results(batch_id):
                row = {"custom_id": result.custom_id, "type": result.result.type}
                if result.result.type == "succeeded":
                    m = result.result.message
                    row["reply"] = "".join(b.text for b in m.content if b.type == "text")
                    row["input_tokens"] = m.usage.input_tokens
                    row["output_tokens"] = m.usage.output_tokens
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("collected")
        return 0
    if args.analyze:
        answers = gold(pathlib.Path(args.hotpot))
        rows = [json.loads(x) for x in ANSWERS.read_text(encoding="utf-8").splitlines() if x]
        by_arm: dict[str, list[dict[str, Any]]] = {a: [] for a in ARMS}
        for r in rows:
            arm, qid = r["custom_id"].split("-", 1)
            by_arm[arm].append({**r, "id": qid})
        report: dict[str, Any] = {"arms": {}}
        for arm, items in by_arm.items():
            ok = [r for r in items if r["type"] == "succeeded"]
            report["arms"][arm] = {
                "n": len(items),
                "failed": len(items) - len(ok),
                "accuracy": round(
                    sum(correct(r["reply"], answers[r["id"]]) for r in ok) / len(items), 4
                ),
                "f1": round(sum(f1(r["reply"], answers[r["id"]]) for r in ok) / len(items), 4),
                "input_tokens": sum(r["input_tokens"] for r in ok),
            }
        a = report["arms"]
        tokens_share = a["contribution"]["input_tokens"] / a["all"]["input_tokens"]
        report["contribution_tokens_share_of_all"] = round(tokens_share, 4)
        report["P10"] = (
            a["contribution"]["accuracy"] >= a["all"]["accuracy"] - 0.03 and tokens_share <= 0.65
        )
        report["P11"] = a["contribution"]["accuracy"] >= a["shipped"]["accuracy"] + 0.20
        report["P12_contribution_minus_bm25"] = round(
            a["contribution"]["accuracy"] - a["bm25"]["accuracy"], 4
        )
        report["verdict"] = (
            "the saving is real on this set" if report["P10"] and report["P11"] else "see criteria"
        )
        (RESULTS / "answers-analysis.json").write_text(json.dumps(report, indent=1), "utf-8")
        print(json.dumps(report, indent=1))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
