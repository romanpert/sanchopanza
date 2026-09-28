"""Context pruning on real Claude Code sessions: six arms, one dataset (`prereg.md`).

    python benchmarks/context/run.py --dry                     # fake decider, zero cost
    python benchmarks/context/run.py --dry --decider null      # every decider arm defaults
    python benchmarks/context/run.py --estimate                # Jev calls, tokens, USD; no call
    python benchmarks/context/run.py --live --max-usd 1.0      # records; refuses unless registered
    python benchmarks/context/run.py --replay                  # free, from the recordings
    python benchmarks/context/run.py --dry --arms tournament   # the experimental arm, free
    python benchmarks/context/run.py --estimate --arms tournament

The experimental `tournament` arm (`arms.EXPERIMENTAL_ARMS`) is never in the default arms and
`--live` refuses it until an amendment registers it (`EXPERIMENTAL_LIVE` below). Its cut is
derived on dev by the same rule as sanchopanza's, reported under `derived_cut_tournament`.

`--live` wraps `providers.jev.JevDecider` (model pinned to `PINNED_MODEL`) in a
`RecordingDecider` writing to ~/.cache/sanchopanza/context/recordings/, behind one `Squire`
whose meter stops at `--max-usd`. It refuses when prereg.md no longer hashes to prereg.sha256,
when `--max-usd` is above the registered 1 USD, or when the high estimate is above `--max-usd`.
The dataset is built by `build.py` and never leaves ~/.cache.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))


def sibling(name: str):
    """A file of this directory as module `context_bench_<name>`: several benches ship a
    `labels.py` or a `run.py`, so a plain import could pick up another bench's file."""
    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, HERE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


arms_mod = sibling("arms")
metrics = sibling("metrics")

from sanchopanza.context.transcript import calls as calls_of  # noqa: E402

CACHE = Path.home() / ".cache" / "sanchopanza" / "context"
RESULTS = ROOT / "docs" / "results" / "2026-09-28-context"
RECORDINGS = CACHE / "recordings"
PINNED_MODEL = "jev-1.13.0"
REGISTERED_CAP_USD = 1.0
RECALL_TARGET = 0.95
MIN_DEV, MIN_TEST = 8, 12  # prereg.md: below this the run is not made
CUTS = [round(i / 100, 2) for i in range(101)]
BASELINES = ("fastjev", "mask_10", "last_3", "rules")


def prereg_hash() -> str:
    raw = (RESULTS / "prereg.md").read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def require_prereg() -> None:
    registered = RESULTS / "prereg.sha256"
    if not registered.exists() or registered.read_text().strip() != prereg_hash():
        raise SystemExit("prereg.md changed or is not registered: nothing spent")


def load(dataset: Path, split: str) -> list[dict[str, Any]]:
    units = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(dataset.glob("*.json"))]
    return [u for u in units if split == "all" or u["split"] == split]


def decider_for(mode: str, name: str, arm: str) -> Any:
    from sanchopanza.providers import NullDecider, RecordedDecider, RecordingDecider

    if mode == "dry":
        return NullDecider() if name == "null" else arms_mod.FakeDecider()
    path = RECORDINGS / f"{arm}.jsonl"
    if mode == "replay":
        return RecordedDecider.from_file(path)
    from sanchopanza.providers.jev import JevDecider

    return RecordingDecider(JevDecider(model=PINNED_MODEL), path)


async def run_units(
    units: Sequence[Mapping[str, Any]], arm_names: Sequence[str], squires: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Per unit: its calls and each arm's result. Units in order, one at a time."""
    out = []
    for unit in units:
        history = unit["history"]
        calls = calls_of(history)
        results = {}
        for arm in arm_names:
            results[arm] = await arms_mod.run_arm(arm, history, calls, squires.get(arm))
        out.append({"unit": unit, "calls": calls, "arms": results})
    return out


EXPERIMENTAL_LIVE = False  # the lead flips this with the amendment that registers the arm


def actions_for(row: Mapping[str, Any], arm: str, cut: float) -> dict[str, str]:
    result = row["arms"][arm]
    return arms_mod.at_cut(result, cut) if arm in arms_mod.CUT_ARMS else dict(result.actions)


def arm_rows(rows, arm: str, cut: float, label_key: str = "needed") -> list[dict[str, Any]]:
    return [
        metrics.unit_metrics(
            r["unit"]["labels"],
            r["calls"],
            actions_for(r, arm, cut),
            archives=arm in arms_mod.ARCHIVING,
            label_key=label_key,
        )
        for r in rows
    ]


def derive_cut(dev_rows: Sequence[Mapping[str, Any]], arm: str = "sanchopanza") -> dict[str, Any]:
    """The highest cut whose pooled dev recall of NEEDED is >= RECALL_TARGET."""
    if not dev_rows or arm not in dev_rows[0]["arms"]:
        return {"cut": None, "reason": f"no dev units or no {arm} arm"}
    curve = {c: metrics.pooled(arm_rows(dev_rows, arm, c)) for c in CUTS}
    passing = [c for c in CUTS if (curve[c]["recall"] or 0.0) >= RECALL_TARGET]
    chosen = max(passing) if passing else min(CUTS)
    return {
        "cut": chosen,
        "reached_target": bool(passing),
        "dev_recall": curve[chosen]["recall"],
        "dev_freed": round(curve[chosen]["freed"], 4),
    }


def kept_sets(rows, arm: str, cut: float) -> list[set[str]]:
    return [{k for k, v in actions_for(r, arm, cut).items() if v == "keep"} for r in rows]


def needed_sets(rows) -> list[set[str]]:
    return [{k for k, v in r["unit"]["labels"].items() if v["needed"]} for r in rows]


def analyze(
    rows, arm_names: Sequence[str], cut: float | None, cuts: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """`cut` is sanchopanza's; `cuts` may give another cut arm its own (the tournament's)."""
    use = 0.5 if cut is None else cut

    def cut_of(arm: str) -> float:
        own = (cuts or {}).get(arm)
        return use if own is None else own

    by_split: dict[str, Any] = {}
    for split in ("dev", "test"):
        part = [r for r in rows if r["unit"]["split"] == split]
        by_split[split] = {
            arm: {
                "needed": metrics.summarize(arm_rows(part, arm, cut_of(arm))),
                "needed_before_refetch": metrics.pooled(
                    arm_rows(part, arm, cut_of(arm), "needed_before_refetch")
                ),
            }
            for arm in arm_names
        }
    test = [r for r in rows if r["unit"]["split"] == "test"]
    comparisons = {}
    if "sanchopanza" in arm_names:
        for other in (b for b in BASELINES if b in arm_names):
            comparisons[f"sanchopanza_vs_{other}"] = metrics.paired(
                arm_rows(test, "sanchopanza", use),
                arm_rows(test, other, use),
                kept_sets(test, "sanchopanza", use),
                kept_sets(test, other, use),
                needed_sets(test),
            )
    if "tournament" in arm_names:
        t = cut_of("tournament")
        for other in (b for b in (*BASELINES, "sanchopanza") if b in arm_names):
            comparisons[f"tournament_vs_{other}"] = metrics.paired(
                arm_rows(test, "tournament", t),
                arm_rows(test, other, cut_of(other)),
                kept_sets(test, "tournament", t),
                kept_sets(test, other, cut_of(other)),
                needed_sets(test),
            )
    return {"cut_used": use, "splits": by_split, "test_comparisons": comparisons}


def estimate(units: Sequence[Mapping[str, Any]], experimental: Sequence[str] = ()) -> dict:
    totals: dict[str, dict[str, float]] = {}
    estimators = [
        ("sanchopanza", metrics.estimate_sanchopanza),
        ("fastjev", metrics.estimate_fastjev),
    ]
    if "tournament" in experimental:
        estimators.append(("tournament", metrics.estimate_tournament))
    for unit in units:
        history = unit["history"]
        calls = calls_of(history)
        for arm, fn in estimators:
            got = fn(history, calls)
            t = totals.setdefault(arm, dict.fromkeys(got, 0))
            for k, v in got.items():
                t[k] = t.get(k, 0) + v
    for t in totals.values():
        t["usd"] = round(metrics.usd(t.get("tokens", 0)), 4)
        t["usd_high"] = round(metrics.usd(t.get("tokens_high", 0)), 4)
    return {"units": len(units), "model": PINNED_MODEL, "arms": totals}


def labels_base_rate(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out = {}
    for split in ("dev", "test"):
        labels = [v for u in units if u["split"] == split for v in u["labels"].values()]
        n = len(labels)
        out[split] = {
            "units": sum(u["split"] == split for u in units),
            "results": n,
            **{
                k: round(sum(v[k] for v in labels) / n, 4) if n else None
                for k in ("needed", "needed_before_refetch", "needed_sole", "reread")
            },
        }
    return out


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay", action="store_true")
    p.add_argument("--decider", choices=("fake", "null"), default="fake")
    p.add_argument("--arms", default=",".join(arms_mod.ARMS))
    p.add_argument("--split", choices=("dev", "test", "all"), default="all")
    p.add_argument("--max-usd", type=float, default=REGISTERED_CAP_USD)
    p.add_argument("--dataset", type=Path, default=CACHE / "dataset")
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args()


def guard_live(args: argparse.Namespace, units: Sequence[Mapping[str, Any]]) -> None:
    require_prereg()
    if args.split != "all":
        raise SystemExit("the live run scores both splits: --split all")
    sides = [u["split"] for u in units]
    if sides.count("dev") < MIN_DEV or sides.count("test") < MIN_TEST:
        raise SystemExit(
            f"{sides.count('dev')} dev / {sides.count('test')} test units, below the registered "
            f"{MIN_DEV} / {MIN_TEST}: not measurable on this dataset, nothing spent"
        )
    if args.max_usd > REGISTERED_CAP_USD:
        raise SystemExit(f"--max-usd above the registered {REGISTERED_CAP_USD} USD: refused")
    high = sum(a["usd_high"] for a in estimate(units)["arms"].values())
    if high > args.max_usd:
        raise SystemExit(f"high estimate {high:.4f} USD exceeds --max-usd: refused")


def main() -> None:
    args = parse()
    arm_names = [a for a in args.arms.split(",") if a]
    unknown = set(arm_names) - set(arms_mod.KNOWN_ARMS)
    if unknown:
        raise SystemExit(f"unknown arms {sorted(unknown)}")
    experimental = [a for a in arm_names if a in arms_mod.EXPERIMENTAL_ARMS]
    units = load(args.dataset, args.split)
    if args.estimate:
        print(json.dumps(estimate(units, experimental), indent=1))
        return
    mode = "live" if args.live else "replay" if args.replay else "dry"
    if args.live:
        if experimental and not EXPERIMENTAL_LIVE:
            raise SystemExit(f"{experimental} not registered for a live run: nothing spent")
        guard_live(args, units)
    paid = [a for a in arm_names if a in (*arms_mod.DECIDER_ARMS, *experimental)]
    # One squire per decider arm, the ceiling split between them: the total never passes it.
    share = args.max_usd / max(1, len(paid))
    counters = {a: arms_mod.CountingDecider(decider_for(mode, args.decider, a)) for a in paid}
    squires = {a: arms_mod.squire_for(counters[a], max_usd=share) for a in paid}
    rows = asyncio.run(run_units(units, arm_names, squires))  # the only event loop
    spent = {a: round(s.meter.cost_usd, 6) for a, s in squires.items()}
    dev = [r for r in rows if r["unit"]["split"] == "dev"]
    derived = derive_cut(dev)
    derived_t = derive_cut(dev, "tournament") if "tournament" in arm_names else None
    report = {
        "mode": mode,
        "decider": args.decider if mode == "dry" else PINNED_MODEL,
        "units": len(units),
        "labels": labels_base_rate(units),
        "derived_cut": derived,
        "derived_cut_tournament": derived_t,
        "analysis": analyze(
            rows, arm_names, derived["cut"], {"tournament": (derived_t or {}).get("cut")}
        ),
        "jev_spent_usd": spent,
        "exhausted": {a: s.exhausted for a, s in squires.items()},
        "decider_calls": {a: c.report() for a, c in counters.items()},
        # A null decider answers nothing by design; anywhere else an empty answer is a loss.
        "complete": all(c.complete or args.decider == "null" for c in counters.values())
        and not any(s.exhausted for s in squires.values()),
    }
    default = RESULTS / "analysis.json" if mode != "dry" else CACHE / "analysis-dry.json"
    out = args.out or default
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ("mode", "units", "labels", "derived_cut")}, indent=1))
    print(f"written {out}")
    if any(report["exhausted"].values()):
        raise SystemExit("a squire hit its USD ceiling: the run is incomplete")
    if not report["complete"]:
        raise SystemExit("decider calls failed or came back empty: the run is incomplete")


if __name__ == "__main__":
    main()
