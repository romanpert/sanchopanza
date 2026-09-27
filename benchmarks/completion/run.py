"""A calibrated "is it done?" check on AgentDojo trajectories (`prereg.md` in the results dir).

    python benchmarks/completion/run.py --hash [--record-hash]
    python benchmarks/completion/run.py --jev     --env-file PATH/TO/.env
    python benchmarks/completion/run.py --submit  --env-file PATH/TO/.env
    python benchmarks/completion/run.py --collect --env-file PATH/TO/.env
    python benchmarks/completion/run.py --analyze                          # free

The trajectories are this repository's own AgentDojo runs of 2026-09-24; the label is
AgentDojo's `utility`. The split, tau rule and cascade arithmetic are the cascade bench's.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import hashlib
import importlib.util
import json
import pathlib
import random
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "benchmarks" / "cascade"))

# Several benches ship a `run.py`: loaded by path under its own name, never as `run`.
_spec_cascade = importlib.util.spec_from_file_location(
    "cascade_run", ROOT / "benchmarks" / "cascade" / "run.py"
)
cascade = importlib.util.module_from_spec(_spec_cascade)
_spec_cascade.loader.exec_module(cascade)

from sanchopanza.points import completion  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.llm import answers_from  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-25-completion"
FIXTURE = ROOT / "fixtures" / "completion-jev.jsonl"
ANSWERS = RESULTS / "llm-answers.jsonl"
BATCH = RESULTS / "batch.json"
GLOBS = (
    "docs/results/2026-09-24-agentdojo-e2e/runs/**/*.json",
    "docs/results/2026-09-24-agentdojo-haiku/runs/**/*.json",
)
TOOL_LIMIT = 1_500


def prereg_hash() -> str:
    digest = hashlib.sha256()
    for path in (RESULTS / "prereg.md", ROOT / "src/sanchopanza/points/completion.py"):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != prereg_hash():
        raise SystemExit("prereg.md or points/completion.py changed: nothing spent")


def render(messages: list[dict[str, Any]]) -> tuple[str, str]:
    task, lines = "", []
    for m in messages:
        blocks = m.get("content") or []
        if m["role"] == "user" and not task:
            task = " ".join(b.get("content") or "" for b in blocks if b.get("type") == "text")
        elif m["role"] == "assistant":
            for b in blocks:
                if b.get("type") == "text" and b.get("content"):
                    lines.append(f"AGENT: {b['content']}")
            for call in m.get("tool_calls") or []:
                args = json.dumps(call["args"], ensure_ascii=False)
                lines.append(f"AGENT ACTION: {call['function']}({args})")
        elif m["role"] == "tool":
            text = " ".join(b.get("content") or "" for b in blocks if b.get("type") == "text")
            if m.get("error"):
                text = f"ERROR: {m['error']}"
            lines.append(f"TOOL RESULT: {text[:TOOL_LIMIT]}")
    return task, "\n".join(lines)


def load() -> list[dict[str, Any]]:
    cases = []
    for pattern in GLOBS:
        for path in sorted(glob.glob(str(ROOT / pattern), recursive=True)):
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            if "messages" not in data or "utility" not in data:
                continue
            task, record = render(data["messages"])
            state, qs = completion.questions(task=task, record=record)
            rel = pathlib.Path(path).relative_to(ROOT).as_posix()
            cases.append(
                {
                    "set": "completion",
                    "id": rel,
                    "pipeline": data["pipeline_name"],
                    "point": "completion",
                    "state": state,
                    "questions": qs,
                    "label": "done" if data["utility"] else "not_done",
                }
            )
    return cases


def label_of(answers: dict[str, Any]) -> tuple[str | None, float]:
    a = answers.get("done")
    if a is None or a.truth is None:
        return None, 0.0
    return ("done" if a.truth >= 0.5 else "not_done"), abs(2 * a.truth - 1)


async def run_jev(cases: list[dict[str, Any]], api_key: str) -> None:
    recorded = RecordedDecider.from_file(FIXTURE)
    live = RecordingDecider(create("jev", api_key=api_key), FIXTURE)
    gate = asyncio.Semaphore(6)
    spent = 0.0

    async def one(case: dict[str, Any]) -> None:
        nonlocal spent
        if (await recorded.decide(case["point"], case["state"], case["questions"])).answers:
            return
        async with gate:
            for attempt in range(4):
                try:
                    d = await live.decide(case["point"], case["state"], case["questions"])
                    spent += d.cost_usd
                    return
                except Exception:  # noqa: BLE001 - retried, then reported missing by --analyze
                    await asyncio.sleep(2**attempt)

    await asyncio.gather(*(one(c) for c in cases))
    print(f"jev: {spent:.4f} USD")


async def run_live(cases: list[dict[str, Any]], api_key: str, cap_usd: float = 3.0) -> None:
    """The Sonnet arm through the Messages API, same request body as the batch would send.

    Used on 2026-09-25 because the batch sat unprocessed for over an hour; the batch was
    cancelled first so nothing is paid twice. Latency is recorded per request.
    """
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    have = set()
    if ANSWERS.exists():
        have = {json.loads(x)["custom_id"] for x in ANSWERS.read_text().splitlines() if x}
    gate = asyncio.Semaphore(6)
    spent = 0.0
    lock = asyncio.Lock()

    async def one(case: dict[str, Any]) -> None:
        nonlocal spent
        cid = cascade.custom_id(case, "sonnet")
        if cid in have or spent > cap_usd:
            return
        async with gate:
            if spent > cap_usd:
                return
            start = time.monotonic()
            try:
                m = await client.messages.create(
                    **cascade.request_for(case, cascade.MODELS["sonnet"])
                )
            except Exception as error:  # noqa: BLE001 - written as a failed row
                row = {"custom_id": cid, "type": f"error: {error.__class__.__name__}"}
            else:
                row = {
                    "custom_id": cid,
                    "type": "succeeded",
                    "input_tokens": m.usage.input_tokens,
                    "output_tokens": m.usage.output_tokens,
                    "latency_ms": int((time.monotonic() - start) * 1000),
                    "payload": next((b.input for b in m.content if b.type == "tool_use"), None),
                }
        async with lock:
            if row["type"] == "succeeded":
                spent += cascade.llm_cost(row, "sonnet")
            with ANSWERS.open("a", encoding="utf-8") as out:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

    await asyncio.gather(*(one(c) for c in cases))
    print(f"sonnet live: {spent:.4f} USD")


async def table(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jev = RecordedDecider.from_file(FIXTURE)
    llm = {}
    if ANSWERS.exists():
        for line in ANSWERS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                llm[row["custom_id"]] = row
    rows = []
    for case in cases:
        d = await jev.decide(case["point"], case["state"], case["questions"])
        label, conf = label_of(dict(d.answers))
        truth = d.answer("done").truth
        row = {
            "set": "completion",
            "id": case["id"],
            "pipeline": case["pipeline"],
            "half": cascade.half(case),
            "label": case["label"],
            "jev": label,
            "jev_p": truth,
            "jev_conf": conf,
            "jev_cost": d.cost_usd,
            "trust": "done",
            "trust_cost": 0.0,
        }
        r = llm.get(cascade.custom_id(case, "sonnet"))
        if r and r.get("payload"):
            row["sonnet"], _ = label_of(answers_from(r["payload"], case["questions"]))
            row["sonnet_cost"] = cascade.llm_cost(r, "sonnet")
        else:
            row["sonnet"], row["sonnet_cost"] = None, None
        rows.append(row)
    return rows


def auc(scores: list[float], truths: list[bool]) -> float:
    pos = [s for s, t in zip(scores, truths, strict=True) if t]
    neg = [s for s, t in zip(scores, truths, strict=True) if not t]
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def precision_done(rows: list[dict[str, Any]], arm: str) -> float | None:
    said = [r for r in rows if r[arm] == "done"]
    return round(sum(r["label"] == "done" for r in said) / len(said), 4) if said else None


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing = {a: sum(r[a] is None for r in rows) for a in ("jev", "sonnet")}
    held = [r for r in rows if r["half"] == "held_out"]
    acc = {
        a: round(sum(r[a] == r["label"] for r in rows) / len(rows), 4)
        for a in ("trust", "jev", "sonnet")
    }
    held_acc = {
        a: round(sum(r[a] == r["label"] for r in held) / len(held), 4)
        for a in ("trust", "jev", "sonnet")
    }
    scored = [r for r in rows if r["jev_p"] is not None]
    report: dict[str, Any] = {
        "prereg_sha256": prereg_hash(),
        "n": len(rows),
        "missing": missing,
        "all": acc,
        "held_out": held_acc,
        "precision_done": {a: precision_done(rows, a) for a in ("trust", "jev", "sonnet")},
        "jev_auc": round(
            auc([r["jev_p"] for r in scored], [r["label"] == "done" for r in scored]), 4
        ),
        "per_pipeline": {},
    }
    for p in sorted({r["pipeline"] for r in rows}):
        sub = [r for r in rows if r["pipeline"] == p]
        report["per_pipeline"][p] = {
            "n": len(sub),
            **{
                a: round(sum(r[a] == r["label"] for r in sub) / len(sub), 4)
                for a in ("trust", "jev", "sonnet")
            },
        }
    report["P13"] = held_acc["jev"] >= held_acc["trust"] + 0.15
    if missing["sonnet"] == 0:
        block = cascade.analyze_set(rows, "sonnet")
        block["passes"] = cascade.verdict(block)
        report["cascade_sonnet"] = block
        report["P14"] = block["passes"]
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in (
        "--hash",
        "--record-hash",
        "--jev",
        "--submit",
        "--collect",
        "--analyze",
        "--live",
    ):
        ap.add_argument(flag, action="store_true")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.hash:
        print(prereg_hash())
        if args.record_hash:
            (RESULTS / "prereg.sha256").write_text(prereg_hash() + "\n", encoding="utf-8")
            print("recorded")
        return 0
    cases = load()
    if args.jev:
        require_prereg()
        asyncio.run(run_jev(cases, cascade.key_from_env(args.env_file, "TYPESAFE_API_KEY")))
        return 0
    if args.live:
        require_prereg()
        asyncio.run(run_live(cases, cascade.key_from_env(args.env_file, "ANTHROPIC_API_KEY")))
        return 0
    if args.submit or args.collect:
        import anthropic

        client = anthropic.Anthropic(
            api_key=cascade.key_from_env(args.env_file, "ANTHROPIC_API_KEY")
        )
        if args.submit:
            require_prereg()
            requests = [
                {
                    "custom_id": cascade.custom_id(c, "sonnet"),
                    "params": cascade.request_for(c, cascade.MODELS["sonnet"]),
                }
                for c in cases
            ]
            batch = client.messages.batches.create(requests=requests)
            BATCH.write_text(json.dumps({"id": batch.id, "count": len(requests)}), encoding="utf-8")
            print(f"batch {batch.id} with {len(requests)} requests")
            return 0
        batch_id = json.loads(BATCH.read_text())["id"]
        while client.messages.batches.retrieve(batch_id).processing_status != "ended":
            time.sleep(60)
        with ANSWERS.open("w", encoding="utf-8") as out:
            for result in client.messages.batches.results(batch_id):
                row: dict[str, Any] = {"custom_id": result.custom_id, "type": result.result.type}
                if result.result.type == "succeeded":
                    m = result.result.message
                    row["input_tokens"] = m.usage.input_tokens
                    row["output_tokens"] = m.usage.output_tokens
                    row["payload"] = next(
                        (b.input for b in m.content if b.type == "tool_use"), None
                    )
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("collected")
        return 0
    if args.analyze:
        report = analyze(asyncio.run(table(cases)))
        (RESULTS / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(json.dumps(report, indent=1))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    random.seed(0)
    raise SystemExit(main())
