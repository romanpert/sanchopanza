"""Score memory selectors on the items of build.py (development unless --split held).

    python benchmarks/memory_real/score.py --select bm25,recent,top5          # free
    python benchmarks/memory_real/score.py --select decider --cap 1.0         # Jev, capped

`decider` is what `install --memory` ships: BM25 proposes MEMORY_K records of the pool, the
decider keeps those it judges at KEEP_AT or above, `render` fits them under the character cap.
Its answers are cached by request and records (CACHE/answers.jsonl), so a pass is paid once.
The repository gets the metrics only (OUT/scores-<split>.json).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

CACHE = Path.home() / ".cache" / "sanchopanza" / "memory-real"
OUT = REPO / "docs" / "results" / "2026-10-01-memory-real"
ANSWERS = CACHE / "answers.jsonl"
INDAGIS_ENV = Path(r"C:\Users\roman\Desktop\proyectos\apps\indagis\.env")


def load_items(split: str) -> list[dict[str, Any]]:
    rows = []
    for line in (CACHE / "items.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["split"] == split and item["pool"]:
            rows.append({**item, "pool": [ep.Episode.from_dict(d) for d in item["pool"]]})
    return rows


# ---- selectors ---------------------------------------------------------------------------------


def bm25(item: dict[str, Any]) -> list[str]:
    found = mh.candidates(item["request"], item["pool"], mh.K)
    return [e.key for e in found[: mh.BM25_KEEP]]


def top5(item: dict[str, Any]) -> list[str]:
    return [e.key for e in mh.candidates(item["request"], item["pool"], mh.K)]


def recent(item: dict[str, Any]) -> list[str]:
    newest = max(item["pool"], key=lambda e: (e.at, e.index))
    return [newest.key]


TOUCH_PER_FILE = 2


def touch_pass(
    items: list[dict[str, Any]], per_file: int = TOUCH_PER_FILE,
    tools: tuple[str, ...] = ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"),
) -> tuple[dict[int, list[str]], dict[str, Any]]:  # fmt: skip
    """Just in time: when the agent opens or changes a file an earlier record changed, that
    record (the TOUCH_PER_FILE newest per file), once per session. Code only, no model."""
    shown: dict[int, list[str]] = {}
    given: dict[str, set[str]] = {}
    early = late = 0
    order = sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"]))
    for n in order:
        item = items[n]
        seen = given.setdefault(item["session"], set())
        by_file: dict[str, list[ep.Episode]] = {}
        for e in sorted(item["pool"], key=lambda e: -e.at):
            for path in e.changed:
                by_file.setdefault(path, []).append(e)
        first_edit = next((i for i, (tool, _) in enumerate(item["touched"]) if tool != "Read"),
                          None)  # fmt: skip
        out: list[str] = []
        for position, (tool, path) in enumerate(item["touched"]):
            if tool not in tools:
                continue
            for e in by_file.get(path, [])[:per_file]:
                if e.key not in seen:
                    seen.add(e.key)
                    out.append(e.key)
                    if item["labels"][e.key] != "none":
                        early += first_edit is None or position <= first_edit
                        late += first_edit is not None and position > first_edit
        shown[n] = out
    return shown, {"related_given_before_first_edit": early, "related_given_after": late}


def _key(request: str, keys: Sequence[str]) -> str:
    return hashlib.sha256(json.dumps([request, list(keys)]).encode()).hexdigest()


def _answers() -> dict[str, dict[str, float | None]]:
    if not ANSWERS.exists():
        return {}
    rows = (json.loads(line) for line in ANSWERS.read_text(encoding="utf-8").splitlines())
    return {r["key"]: r["probabilities"] for r in rows}


def squire_with_key(cap: float) -> Any:
    from sanchopanza.harness.claude_code import squire_from_env

    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key:
        for line in INDAGIS_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise SystemExit("no TypeSafe key")
    env = {**os.environ, "TYPESAFE_API_KEY": key, "SANCHOPANZA_T_MAX_USD": str(cap),
           "SANCHOPANZA_JOURNAL": str(CACHE / "journal.jsonl")}  # fmt: skip
    return squire_from_env(env, redact=True)


async def decider_pass(
    items: list[dict[str, Any]], cap: float, keep_at: float = mh.KEEP_AT, min_chars: int = 0,
    first_only: bool = False,
) -> dict[int, list[str]]:  # fmt: skip
    cached = _answers()
    squire = None
    shown: dict[int, list[str]] = {}
    with ANSWERS.open("a", encoding="utf-8", newline="\n") as log:
        for n, item in enumerate(items):
            found = mh.candidates(item["request"], item["pool"], mh.K)
            if (not found or len(item["request"]) < min_chars
                    or (first_only and not item["first"])):  # fmt: skip
                shown[n] = []
                continue
            key = _key(item["request"], [e.key for e in found])
            if key not in cached:
                squire = squire or squire_with_key(cap)
                if squire.meter.cost_usd >= cap:
                    raise SystemExit(f"cap {cap} USD reached after {n} items")
                _, probabilities = await mh.keep_by_decider(squire, item["request"], found)
                cached[key] = probabilities
                log.write(json.dumps({"key": key, "probabilities": probabilities}) + "\n")
                log.flush()
            probabilities = cached[key]
            kept = sorted((e for e in found if (probabilities.get(e.key) or 0) >= keep_at),
                          key=lambda e: -(probabilities.get(e.key) or 0))  # fmt: skip
            _, keys = mh.render(kept)
            shown[n] = keys
    if squire is not None:
        print(f"decider spent {squire.meter.cost_usd:.4f} USD", flush=True)
    return shown


# ---- metrics -----------------------------------------------------------------------------------


def in_context(items: list[dict[str, Any]], shown: dict[int, list[str]]) -> dict[int, set[str]]:
    """What each request has in view: shown to it or to an earlier request of its session (no
    compaction is simulated: SWE-chat sessions rarely reach one)."""
    order = sorted(range(len(items)), key=lambda n: (items[n]["session"], items[n]["index"]))
    seen: dict[str, set[str]] = {}
    out: dict[int, set[str]] = {}
    for n in order:
        acc = seen.setdefault(items[n]["session"], set())
        acc |= set(shown[n])
        out[n] = set(acc)
    return out


def metrics(items: list[dict[str, Any]], shown: dict[int, list[str]]) -> dict[str, Any]:
    """recall: requests with a related record in the pool that have one in view; precision:
    records shown that are related to the request they were shown to; noise: requests with no
    related record in the pool that were shown anything."""
    view = in_context(items, shown)
    out: dict[str, Any] = {}
    for scope, keep in (("all", lambda i: True), ("first", lambda i: i["first"])):
        for name, related in (("lineage", {"lineage"}), ("any", {"lineage", "file"})):
            chosen = [n for n, i in enumerate(items) if keep(i)]
            rel = [n for n in chosen if related & set(items[n]["labels"].values())]
            unrel = [n for n in chosen if n not in set(rel)]
            hits = sum(any(items[n]["labels"].get(k) in related for k in view[n]) for n in rel)
            total_shown = sum(len(shown[n]) for n in chosen)
            good = sum(items[n]["labels"][k] in related for n in chosen for k in shown[n])
            out[f"{scope}/{name}"] = {
                "requests": len(chosen), "with_related": len(rel),
                "recall": round(hits / len(rel), 3) if rel else None,
                "precision": round(good / total_shown, 3) if total_shown else None,
                "noise": round(sum(bool(shown[n]) for n in unrel) / len(unrel), 3)
                if unrel else None,
                "shown_per_request": round(total_shown / len(chosen), 2) if chosen else None,
            }  # fmt: skip
    return out


SELECTORS: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "bm25": bm25, "top5": top5, "recent": recent,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--select", default="bm25,recent,top5")
    parser.add_argument("--split", default="dev", choices=("dev", "held"))
    parser.add_argument("--cap", type=float, default=0.0, help="USD for the decider (required)")
    parser.add_argument("--tag", default="", help="suffix of the scores file")
    args = parser.parse_args(argv)
    items = load_items(args.split)
    results = {}
    for name in args.select.split(","):
        if name == "decider":
            if args.cap <= 0:
                raise SystemExit("--cap is required for the decider")
            shown = asyncio.run(decider_pass(items, args.cap))
        elif name == "touch":
            shown, timing = touch_pass(items)
        else:
            shown = {n: SELECTORS[name](i) for n, i in enumerate(items)}
        results[name] = metrics(items, shown)
        if name == "touch":
            results[name]["timing"] = timing
            print("timing", timing)
        print(name, json.dumps(results[name]["all/any"]), json.dumps(results[name]["first/any"]))
    target = OUT / f"scores-{args.split}{args.tag}.json"
    old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    target.write_text(json.dumps({**old, **results}, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
