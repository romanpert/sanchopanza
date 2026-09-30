"""Label a corpus: Jev, Haiku through `claude -p`, and the cascade (docs/results/2026-09-30-label).

python benchmarks/label/run.py --record-hash
python benchmarks/label/run.py --pilot --live --env-file PATH/.env   # 5 items per set, excluded
python benchmarks/label/run.py --live --env-file PATH/.env           # spends, records
python benchmarks/label/run.py                                       # free: replays recordings

Jev calls are recorded in `fixtures/label-jev.jsonl`; Haiku sessions in
`fixtures/cli/label-haiku.jsonl` (our own evaluation harness, list prices, not the API).
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
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.eval import harness as _harness  # noqa: E402
from sanchopanza.label import Item, Rubric, label  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.llm import LLMDecider  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-30-label"
PREREG = RESULTS / "prereg.md"
JEV_FIXTURE = ROOT / "fixtures" / "label-jev.jsonl"
CLI_CACHE = ROOT / "fixtures" / "cli" / "label-haiku.jsonl"
DATA = pathlib.Path.home() / ".cache" / "sanchopanza" / "label"
SETS = ("agnews", "dbpedia")
HAIKU = "claude-haiku-4-5-20251001"
PILOT = 5
JEV_CEILING_USD = 0.10
CLI_CEILING_USD = 6.00
SESSION_MAX_USD = 0.05
HAIKU_IN, HAIKU_OUT = 1.0, 5.0  # USD per MTok, list
COVERAGES = (0.8, 0.6)


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ReplayFirst = _load("triage_sets_run", ROOT / "benchmarks" / "triage_sets" / "run.py").ReplayFirst


def digest() -> str:
    return hashlib.sha256(PREREG.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != digest():
        raise SystemExit("prereg.md missing or changed since it was registered: nothing spent")


def key_from(env_file: str | None) -> str:
    import os

    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key and env_file:
        found = re.search(
            r"^TYPESAFE_API_KEY=(.*)$", pathlib.Path(env_file).read_text(encoding="utf-8"), re.M
        )
        key = found.group(1).strip().strip("'\"") if found else ""
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY: nothing spent")
    return key


def load(name: str) -> tuple[list[dict[str, Any]], Rubric]:
    rows = [
        json.loads(x) for x in (DATA / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return rows, Rubric.load(DATA / f"{name}.rubric.json")


def argmax(dist: dict[str, float]) -> str | None:
    return max(dist, key=lambda k: dist[k]) if dist else None


async def jev_arm(
    rows: list[dict], rubric: Rubric, decider: Any
) -> tuple[list[dict[str, Any]], float]:
    squire = Squire(decider, thresholds=Thresholds(max_usd=JEV_CEILING_USD, max_decisions=2000))
    items = [Item(r["key"], r["text"]) for r in rows]
    out = await label(items, rubric, squire=squire, concurrency=8)
    return [
        {"key": o.key, "gold": r["gold"], "label": argmax(dict(o.probabilities)),
         "gated": o.label, "p": o.p, "margin": o.margin, "provider": o.provider}
        for o, r in zip(out, rows, strict=True)
    ], squire.meter.cost_usd  # fmt: skip


async def haiku_arm(rows: list[dict], rubric: Rubric, cli: Any) -> list[dict[str, Any]]:
    squire = Squire(LLMDecider(cli.completer(), model=HAIKU), thresholds=Thresholds(classify=0.0))
    items = [Item(r["key"], r["text"]) for r in rows]
    out = await label(items, rubric, squire=squire, concurrency=4)
    return [
        {"key": o.key, "gold": r["gold"], "label": argmax(dict(o.probabilities))}
        for o, r in zip(out, rows, strict=True)
    ]


def haiku_cost(cli: Any, cache: Any) -> dict[str, float]:
    """List dollars the CLI reported, and the API-equivalent from token counts."""
    sessions = [cache.get(k) for k in cache._rows]  # noqa: SLF001 - our own harness
    listed = sum(s.list_cost_usd for s in sessions)
    api = (
        sum(
            (s.input_tokens + s.cache_read_tokens * 0.1 + s.cache_write_tokens * 1.25) * HAIKU_IN
            + s.output_tokens * HAIKU_OUT
            for s in sessions
        )
        / 1_000_000
    )
    return {"sessions": len(sessions), "list_usd": listed, "api_equivalent_usd": api}


# --- analysis -------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if not n:
        return [0.0, 0.0]
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 4), round(centre + half, 4)]


def auroc(scores: list[float], right: list[bool]) -> float:
    pos = [s for s, r in zip(scores, right, strict=True) if r]
    neg = [s for s, r in zip(scores, right, strict=True) if not r]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def selective(rows: list[dict], key: str, coverage: float) -> float:
    kept = sorted(rows, key=lambda r: -r[key])[: max(1, round(coverage * len(rows)))]
    return sum(r["label"] == r["gold"] for r in kept) / len(kept)


def selective_diff(rows: list[dict], coverage: float, reps: int = 4000) -> list[float]:
    rng = random.Random(2031)
    diffs = []
    for _ in range(reps):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        diffs.append(selective(sample, "margin", coverage) - selective(sample, "p", coverage))
    diffs.sort()
    return [round(diffs[int(0.025 * reps)], 4), round(diffs[int(0.975 * reps)], 4)]


def cascade(jev: list[dict], haiku: list[dict]) -> dict[str, Any]:
    half = len(jev) // 2
    dev_j, test_j, dev_h, test_h = jev[:half], jev[half:], haiku[:half], haiku[half:]
    haiku_dev_acc = sum(h["label"] == h["gold"] for h in dev_h) / len(dev_h)
    tau = 1.01
    for candidate in sorted({round(j["p"], 2) for j in dev_j}):
        kept = [j for j in dev_j if j["p"] >= candidate]
        if kept and sum(j["label"] == j["gold"] for j in kept) / len(kept) >= haiku_dev_acc:
            tau = candidate
            break
    picks = [j if j["p"] >= tau else h for j, h in zip(test_j, test_h, strict=True)]
    escalated = sum(j["p"] < tau for j in test_j)
    right = sum(p["label"] == p["gold"] for p in picks)
    return {
        "tau_from_first_half": tau,
        "held_out_items": len(test_j),
        "escalated_share": round(escalated / len(test_j), 4),
        "accuracy": round(right / len(test_j), 4),
        "haiku_accuracy_held_out": round(
            sum(h["label"] == h["gold"] for h in test_h) / len(test_h), 4
        ),
        "jev_accuracy_held_out": round(
            sum(j["label"] == j["gold"] for j in test_j) / len(test_j), 4
        ),
    }


def analyze(name: str, jev: list[dict], haiku: list[dict] | None, costs: dict) -> dict:
    n = len(jev)
    right = [j["label"] == j["gold"] for j in jev]
    gated = [j for j in jev if j["gated"] is not None]
    out: dict[str, Any] = {
        "items": n,
        "jev": {
            "accuracy": round(sum(right) / n, 4),
            "wilson95": wilson(sum(right), n),
            "at_classify_0.60": {
                "coverage": round(len(gated) / n, 4),
                "accuracy": round(
                    sum(j["gated"] == j["gold"] for j in gated) / max(1, len(gated)), 4
                ),
            },
            "usd_per_1000": round(costs["jev_usd"] / n * 1000, 5),
        },
        "question3": {
            "auroc_p1": auroc([j["p"] for j in jev], right),
            "auroc_margin": auroc([j["margin"] for j in jev], right),
            **{
                f"selective@{c}": {
                    "p1": round(selective(jev, "p", c), 4),
                    "margin": round(selective(jev, "margin", c), 4),
                    "margin_minus_p1_bootstrap95": selective_diff(jev, c),
                }
                for c in COVERAGES
            },
        },
    }
    if haiku:
        hr = [h["label"] == h["gold"] for h in haiku]
        out["haiku"] = {
            "accuracy": round(sum(hr) / n, 4),
            "wilson95": wilson(sum(hr), n),
            "unanswered": sum(h["label"] is None for h in haiku),
        }
        out["cascade"] = cascade(jev, haiku)
    return out


async def refuse_to_spawn(*_: Any) -> tuple[int, bytes, bytes]:
    """Replay mode: a session missing from the cache is unanswered, never paid for."""
    raise RuntimeError("not in the cache and not --live: nothing spent")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--jev-only", action="store_true")
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    if args.record_hash:
        (RESULTS / "prereg.sha256").write_text(digest() + "\n", encoding="utf-8")
        print(digest())
        return 0
    live = None
    if args.live:
        require_prereg()
        live = RecordingDecider(create("jev", api_key=key_from(args.env_file)), JEV_FIXTURE)
    recorded = (
        RecordedDecider.from_file(JEV_FIXTURE) if JEV_FIXTURE.exists() else RecordedDecider([])
    )
    jev = ReplayFirst(recorded, live)
    cli = cache = None
    if not args.jev_only:
        h = _harness.load()
        cache = h.SessionCache(CLI_CACHE)
        cli = h.ClaudeCLI(
            model=HAIKU,
            system="You label items. Answer every question from the state given.",
            ceiling_usd=CLI_CEILING_USD,
            max_budget_usd=SESSION_MAX_USD,
            concurrency=4,
            cache=cache,
            count_cached=True,
            spawn=None if args.live else refuse_to_spawn,
        )

    report: dict[str, Any] = {}

    async def every_set() -> None:
        # One event loop for the whole run: ReplayFirst's pacing lock and the CLI's semaphore
        # bind to the loop they are first used on, and a second `asyncio.run` made every call
        # of the next set fail before it left (the 2026-09-30 pilot: 3 of 5 unanswered).
        for name in SETS:
            rows, rubric = load(name)
            rows = rows[:PILOT] if args.pilot else rows
            before = jev.asked
            j, jev_usd = await jev_arm(rows, rubric, jev)
            hk = await haiku_arm(rows, rubric, cli) if cli is not None else None
            report[name] = analyze(name, j, hk, {"jev_usd": jev_usd})
            report[name]["jev_live_calls"] = jev.asked - before
            report[name]["jev_unanswered"] = sum(x["label"] is None for x in j)
            (RESULTS / f"{'pilot-' if args.pilot else ''}{name}-rows.jsonl").write_text(
                "".join(json.dumps({**a, "haiku": (b or {}).get("label")}) + "\n"
                        for a, b in zip(j, hk or [None] * len(j), strict=True)),
                encoding="utf-8",
            )  # fmt: skip

    asyncio.run(every_set())
    if cache is not None:
        report["haiku_cost"] = haiku_cost(cli, cache)
    report["jev_missing"] = jev.missing
    report["incomplete"] = bool(
        jev.missing
        or any(report[s]["jev_unanswered"] for s in SETS)
        or any(report[s].get("haiku", {}).get("unanswered") for s in SETS)
    )
    name = "pilot.json" if args.pilot else "analysis.json"
    (RESULTS / name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 1 if report["incomplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
