"""Does the model still answer from the kept sentences? (`docs/results/2026-09-27-answers/`)

python benchmarks/chunks/answers.py --record-hash
python benchmarks/chunks/answers.py --live --hotpot FILE.jsonl    # Claude Code CLI, no API key
python benchmarks/chunks/answers.py --hotpot FILE.jsonl           # free, from the session cache

Kept sets are rebuilt from `fixtures/chunks-confirm.jsonl` with the cuts the confirmatory chunk
run fixed. Every answer goes through our own evaluation harness (`sanchopanza.eval.harness`,
not distributed) and is cached in `fixtures/cli/answers.jsonl`: without `--live`, a prompt
missing from the cache is an error. Not directly comparable with answers obtained through the
API.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


confirm = _load("chunk_confirm", HERE / "confirm.py")  # also loads chunks/run.py
chunk_run = confirm.chunk_run
triage_answers = _load("triage_answers", HERE.parent / "triage_sets" / "answers.py")

from sanchopanza.eval import harness as _harness  # noqa: E402

_h = _harness.load()
CeilingReached, ClaudeCLI, SessionCache = _h.CeilingReached, _h.ClaudeCLI, _h.SessionCache
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

ROOT = chunk_run.ROOT
RESULTS = ROOT / "docs" / "results" / "2026-09-27-answers"
PREREG = RESULTS / "prereg.md"
CACHE = ROOT / "fixtures" / "cli" / "answers.jsonl"
MODEL = "claude-haiku-4-5-20251001"
SYSTEM = triage_answers.SYSTEM
CEILING_USD = 8.0
ARMS = ("all", "C", "CB", "B")


# The second run (`prereg-short.md`): the same arms with the reply forced into one short field,
# because through the CLI there is no `max_tokens` and the containment score rewards length.
SHORT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def mode(short: bool) -> dict[str, Any]:
    if short:
        return {
            "prereg": RESULTS / "prereg-short.md",
            "cache": ROOT / "fixtures" / "cli" / "answers-short.jsonl",
            "schema": SHORT_SCHEMA,
            "out": RESULTS / "analysis-short.json",
        }
    return {"prereg": PREREG, "cache": CACHE, "schema": None, "out": RESULTS / "analysis.json"}


def digest(path: pathlib.Path) -> str:
    """sha256 with line endings normalised: autocrlf must not void a registration."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg(prereg: pathlib.Path = PREREG) -> None:
    registered = prereg.with_suffix(".sha256")
    if not registered.exists() or registered.read_text().strip() != digest(prereg):
        raise SystemExit(f"{prereg.name} missing or changed: nothing spent")


def cuts() -> dict[str, float]:
    fixed = json.loads((chunk_run.RESULTS / "confirm-analysis.json").read_text())["cuts_from_600"]
    return {"C": fixed["C"], "B": fixed["B"], "CB": fixed["CB"]}


def confirm_rows(hotpot: pathlib.Path) -> list[dict[str, Any]]:
    earlier = chunk_run.samples(hotpot)
    used = {r["id"] for r in earlier["derivation"] + earlier["held_out"]}
    rows = confirm.fresh(hotpot, used)
    asyncio.run(chunk_run.ask(rows, RecordedDecider.from_file(confirm.FIXTURE)))
    # Sentences past a page's 40-sentence cap are None by design and kept; a page without its
    # in-context answer is a gap in the recordings.
    if sum(p is None for r in rows for p in r["context_p"]):
        raise SystemExit("the chunk recordings do not cover the confirmatory set")
    return rows


def keep_mask(row: dict[str, Any], arm: str, c: dict[str, float]) -> list[list[bool]]:
    if arm == "all":
        return [[True] * len(s) for s in row["sentences"]]
    if arm == "C":
        return chunk_run.mask(row, "C", c["C"])
    if arm == "B":
        return chunk_run.mask(row, "B", c["B"])
    return confirm.cb_mask(row, c["C"], c["CB"])


def prompt_for(row: dict[str, Any], keep: list[list[bool]]) -> str:
    blocks = []
    for title, sentences, kept in zip(row["titles"], row["sentences"], keep, strict=True):
        text = " ".join(s for s, k in zip(sentences, kept, strict=True) if k)
        if text:
            blocks.append(f"{title}: {text}")
    return "\n\n".join(blocks) + f"\n\nQuestion: {row['question']}"


def items(hotpot: pathlib.Path) -> list[dict[str, Any]]:
    c = cuts()
    out = []
    for row in confirm_rows(hotpot):
        for arm in ARMS:
            out.append(
                {
                    "custom_id": f"{arm}-{row['id']}",
                    "arm": arm,
                    "id": row["id"],
                    "user": prompt_for(row, keep_mask(row, arm, c)),
                }
            )
    for case in triage_answers.cases(hotpot):
        if case["arm"] == "all":
            out.append({**case, "custom_id": f"path-{case['id']}", "arm": "path"})
    return out


def reply_of(session: Any, schema: Any) -> str:
    if schema is None:
        return session.text
    structured = session.structured or {}
    return str(structured.get("answer", ""))


async def ask(
    todo: list[dict[str, Any]], live: bool, concurrency: int = 12, short: bool = False
) -> list[dict[str, Any]]:
    m = mode(short)
    cache = SessionCache(m["cache"])
    if not live:
        absent = [
            t
            for t in todo
            if cache.get(SessionCache.key(MODEL, SYSTEM, m["schema"], t["user"])) is None
        ]
        if absent:
            raise SystemExit(f"{len(absent)} prompts not in the cache; run with --live")
    cli = ClaudeCLI(
        model=MODEL,
        system=SYSTEM,
        ceiling_usd=CEILING_USD,
        cache=cache,
        concurrency=concurrency,
    )
    done = 0

    async def one(item: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        session = await cli.run(item["user"], schema=m["schema"])
        done += 1
        if done % 100 == 0:
            print(f"{done}/{len(todo)}  spent {cli.spent_usd:.3f} USD list", file=sys.stderr)
        return {
            "custom_id": item["custom_id"],
            "arm": item["arm"],
            "id": item["id"],
            "ok": session.ok and (m["schema"] is None or session.structured is not None),
            "reply": reply_of(session, m["schema"]),
            "input_tokens": session.input_tokens,
            "list_cost_usd": session.list_cost_usd,
            "reason": session.reason,
        }

    try:
        rows = await asyncio.gather(*(one(t) for t in todo))
    except CeilingReached as stop:
        raise SystemExit(f"ceiling reached, answers so far are cached: {stop}") from stop
    print(f"spawned {cli.spawned}, spent {cli.spent_usd:.3f} USD list", file=sys.stderr)
    return list(rows)


def analyze(rows: list[dict[str, Any]], hotpot: pathlib.Path) -> dict[str, Any]:
    gold = triage_answers.gold(hotpot)
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)
    report: dict[str, Any] = {"model": MODEL, "path": "claude code cli", "cuts": cuts(), "arms": {}}
    for arm, group in by_arm.items():
        ok = [r for r in group if r["ok"]]
        report["arms"][arm] = {
            "n": len(group),
            "failed": len(group) - len(ok),
            "accuracy": round(
                sum(triage_answers.correct(r["reply"], gold[r["id"]]) for r in ok) / len(group), 4
            ),
            "f1": round(
                sum(triage_answers.f1(r["reply"], gold[r["id"]]) for r in ok) / len(group), 4
            ),
            "exact": round(
                sum(
                    triage_answers.normalise(r["reply"]) == triage_answers.normalise(gold[r["id"]])
                    for r in ok
                )
                / len(group),
                4,
            ),
            "input_tokens": sum(r["input_tokens"] for r in ok),
        }
    a = report["arms"]
    for arm in ("C", "CB", "B"):
        a[arm]["tokens_share_of_all"] = round(a[arm]["input_tokens"] / a["all"]["input_tokens"], 4)
    report["P21"] = a["CB"]["accuracy"] >= a["all"]["accuracy"] - 0.03
    report["P22"] = a["C"]["accuracy"] >= a["all"]["accuracy"] - 0.03
    api = json.loads((triage_answers.RESULTS / "answers-analysis.json").read_text())
    api_all = api["arms"]["all"]["accuracy"]
    report["api_all_accuracy_seed_2027"] = api_all
    report["P24"] = abs(a["path"]["accuracy"] - api_all) <= 0.03
    report["path_agreement"] = path_agreement(rows, gold)
    if report["P21"] and report["P22"]:
        report["verdict"] = "the sentences answer as well as the pages"
    elif report["P22"]:
        report["verdict"] = "the page cut is safe; the sentence cut costs answers"
    else:
        report["verdict"] = "see criteria"
    return report


def path_agreement(rows: list[dict[str, Any]], gold: dict[str, str]) -> dict[str, float]:
    """Per question, does the CLI reply score the same as the API reply on the same prompt?"""
    api = {}
    for line in (triage_answers.ANSWERS).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["custom_id"].startswith("all-") and r["type"] == "succeeded":
            api[r["custom_id"][4:]] = triage_answers.correct(r["reply"], gold[r["custom_id"][4:]])
    cli = {
        r["id"]: triage_answers.correct(r["reply"], gold[r["id"]])
        for r in rows
        if r["arm"] == "path"
    }
    shared = [q for q in cli if q in api]
    same = sum(cli[q] == api[q] for q in shared)
    return {"n": len(shared), "same_score": round(same / len(shared), 4) if shared else 0.0}


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
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--short", action="store_true", help="prereg-short.md: one short field")
    args = ap.parse_args()
    m = mode(args.short)
    if args.record_hash:
        write_hash(m["prereg"].with_suffix(".sha256"), digest(m["prereg"]))
        print(digest(m["prereg"]))
        return 0
    if args.live:
        require_prereg(m["prereg"])
    hotpot = pathlib.Path(args.hotpot)
    rows = asyncio.run(ask(items(hotpot), args.live, args.concurrency, args.short))
    failed = [r for r in rows if not r["ok"]]
    if failed:
        print(f"{len(failed)} sessions failed, e.g. {failed[0]['reason']}", file=sys.stderr)
    report = analyze(rows, hotpot)
    report["run"] = "short answer field" if args.short else "free reply"
    m["out"].write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
