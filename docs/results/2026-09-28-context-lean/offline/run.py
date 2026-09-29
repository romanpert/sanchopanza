"""Offline benchmarks for the context-lean iteration: O1 index stubs, O2 arrival, O3 API rival.

    python docs/results/2026-09-28-context-lean/offline/run.py smoke            # 2 units, free
    python docs/results/2026-09-28-context-lean/offline/run.py free             # 40 units, free
    python docs/results/2026-09-28-context-lean/offline/run.py estimate         # jev arm, no call
    python docs/results/2026-09-28-context-lean/offline/run.py jev --cap 0.20 --env-file PATH
    python docs/results/2026-09-28-context-lean/offline/run.py jev --replay     # free, recordings

Data: the 40 units of docs/results/2026-09-28-context (built by `benchmarks/context/build.py
--fetch` into ~/.cache, never the repository), same cut points and NEEDED labels.

`jev` is the only arm that spends. It refuses unless `--prereg` (default: ../prereg.md) exists
and hashes to the sha256 written next to it, unless the high estimate fits under `--cap`, and
it stops at `--cap` through one Squire's meter. The key is read in-process from `--env-file`
(`TYPESAFE_API_KEY=...`) and handed to the provider; it is never printed or written. Every
decision is recorded under ~/.cache for a free replay.

Results go to `results.json` next to this file, one section per subcommand.
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
ROOT = HERE.parents[3]
BENCH = ROOT / "benchmarks" / "context"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(HERE))


def sibling(name: str):
    """A file of benchmarks/context as `context_bench_<name>`, as the bench itself loads it."""
    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, BENCH / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


bench_run = sibling("run")
metrics = sibling("metrics")
arms_mod = sibling("arms")

import measures as m  # noqa: E402

from sanchopanza.context import arrival  # noqa: E402
from sanchopanza.context.transcript import calls as calls_of  # noqa: E402

CACHE = bench_run.CACHE
RESULTS = HERE / "results.json"
RECORDINGS = CACHE / "recordings-lean" / "arrival-jev.jsonl"
PINNED_MODEL = bench_run.PINNED_MODEL
USD_PER_DECISION = 29e-6  # the planning figure for one Jev decision
SMOKE_UNITS = 2
FREE_O2_ARMS = ("head_tail", "free_cut", "bm25_at_free_cut", "bm25_at_head_tail")
O3_ARMS = ("mask_10", "mask_3", "api_T30k", "api_T50k", "api_T100k", "api_always")


def new_api():
    """`compact.index_of` and `arrival.free_cut`, added to src/ by this iteration."""
    from sanchopanza.context import compact

    index_of = getattr(compact, "index_of", None)
    if index_of is None:
        try:
            from sanchopanza.context.index import index_of
        except ImportError:
            index_of = None
    free_cut = getattr(arrival, "free_cut", None)
    missing = [n for n, f in (("index_of", index_of), ("free_cut", free_cut)) if f is None]
    if missing:
        raise SystemExit(f"src/ does not provide {missing} yet: nothing measured")
    return index_of, free_cut


def load_units(limit: int | None) -> list[dict[str, Any]]:
    units = bench_run.load(CACHE / "dataset", "all")
    if not units:
        raise SystemExit("no units: run benchmarks/context/build.py --fetch, then build.py")
    return units[:limit] if limit else units


def write_section(name: str, body: Mapping[str, Any]) -> None:
    current = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    RESULTS.write_text(json.dumps({**current, name: body}, indent=1), encoding="utf-8")


# --- O3 summary through the bench's own metrics ------------------------------------------------


def o3_summary(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    per_arm: dict[str, list[dict[str, Any]]] = {a: [] for a in O3_ARMS}
    for unit in units:
        found = calls_of(unit["history"])
        for arm, actions in m.o3_arm_actions(unit).items():
            row = metrics.unit_metrics(unit["labels"], found, actions, archives=False)
            per_arm[arm].append({**row, "split": unit["split"]})
    out: dict[str, Any] = {"triggered_units": m.o3_triggered(units)}
    for split in m.SPLITS:
        out[split] = {
            arm: metrics.summarize(m.in_split(rows, split)) for arm, rows in per_arm.items()
        }
    return out


# --- free arms ---------------------------------------------------------------------------------


def run_free(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    index_of, free_cut = new_api()
    settings = arrival.Settings()
    o1 = [r for u in units for r in m.o1_rows(u, index_of)]
    o2 = [r for u in units for r in m.o2_free_rows(u, free_cut, settings)]
    return {
        "units": len(units),
        "splits": {s: sum(u["split"] == s for u in units) for s in ("dev", "test")},
        "o1_index_stubs": m.o1_summary(o1),
        "o2_arrival": m.o2_summary(o2, FREE_O2_ARMS),
        "o3_api_rival": o3_summary(units),
        "o2_rows": [{k: v for k, v in r.items() if k != "wanted"} for r in o2],
    }


# --- the Jev arm (prepared; spends only with a registered prereg and a cap) --------------------


def estimate(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    simulate = sibling("simulate")
    got = simulate.arrival_estimate(units, arrival.Settings())
    return {
        **got,
        "usd_at_29e-6": round(got["calls"] * USD_PER_DECISION, 4),
        "usd_high_at_29e-6": round(got["calls_high"] * USD_PER_DECISION, 4),
        "model": PINNED_MODEL,
    }


def require_prereg(path: Path) -> None:
    digest = path.with_suffix(".sha256")
    if not path.exists() or not digest.exists():
        raise SystemExit(f"no registered prereg at {path.name}: nothing spent")
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    # the last line registers the file with every amendment so far (the first, the original)
    last = digest.read_text().strip().splitlines()[-1].split()[0]
    if last != hashlib.sha256(raw).hexdigest():
        raise SystemExit("prereg changed since it was hashed: nothing spent")


def key_from(env_file: Path) -> str:
    """TYPESAFE_API_KEY from an env file, kept in memory only."""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name.strip().removeprefix("export ").strip() == "TYPESAFE_API_KEY":
            return value.strip().strip("'\"")
    raise SystemExit("TYPESAFE_API_KEY not in the env file: nothing spent")


def jev_decider(replay: bool, env_file: Path | None) -> Any:
    from sanchopanza.providers import RecordedDecider, RecordingDecider

    if replay:
        return RecordedDecider.from_file(RECORDINGS)
    from sanchopanza.providers.jev import JevDecider

    if env_file is None:
        raise SystemExit("--env-file is required for a live run")
    return RecordingDecider(JevDecider(key_from(env_file), model=PINNED_MODEL), RECORDINGS)


async def jev_rows(units, squire) -> list[dict[str, Any]]:
    settings = arrival.Settings()
    rows = []
    for unit in units:
        for call in m.large_calls(unit):
            row = m.o2_base(unit, call)
            result = await arrival.cut(
                squire,
                call.result,
                tool=call.tool,
                tool_input=call.input,
                purpose=m.purpose_for(unit, call),
                settings=settings,
            )
            text, cut = m.as_text(result, call.result)
            m.score_arm(row, call, "jev", text, cut)
            row["jev_reason"] = result.reason
            rows.append(row)
    return rows


def run_jev(args: argparse.Namespace, units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    est = estimate(units)
    if not args.replay:
        require_prereg(args.prereg)
        if args.cap is None or args.cap <= 0:
            raise SystemExit("--cap USD is required for a live run")
        if max(est["usd_high"], est["usd_high_at_29e-6"]) > args.cap:
            raise SystemExit(f"high estimate above --cap {args.cap}: nothing spent")
        if RECORDINGS.exists():
            raise SystemExit("recordings already exist: replay them (--replay) or move them")
    counter = arms_mod.CountingDecider(jev_decider(args.replay, args.env_file))
    squire = sibling("simulate").squire_for(counter, args.cap or 1.0)
    rows = asyncio.run(jev_rows(units, squire))  # the only event loop
    report = counter.report()
    return {
        "mode": "replay" if args.replay else "live",
        "model": PINNED_MODEL,
        "estimate": est,
        "o2_arrival_jev": m.o2_summary(rows, ("jev",)),
        "jev_spent_usd": round(squire.meter.cost_usd, 6),
        "exhausted": squire.exhausted,
        "decider_calls": report,
        "complete": report["complete"] and not squire.exhausted,
        "o2_rows_jev": [{k: v for k, v in r.items() if k != "wanted"} for r in rows],
    }


# --- command line ------------------------------------------------------------------------------


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("smoke", help=f"free arms on the first {SMOKE_UNITS} units")
    sub.add_parser("free", help="free arms on every unit")
    sub.add_parser("estimate", help="Jev calls and USD of the jev arm, no call")
    jev = sub.add_parser("jev", help="the Jev arm of O2 (spends unless --replay)")
    jev.add_argument("--cap", type=float, default=None, help="hard USD ceiling")
    jev.add_argument("--env-file", type=Path, default=None)
    jev.add_argument("--prereg", type=Path, default=HERE.parent / "prereg.md")
    jev.add_argument("--replay", action="store_true")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse(argv)
    units = load_units(SMOKE_UNITS if args.command == "smoke" else None)
    if args.command == "estimate":
        body = {"units": len(units), **estimate(units)}
        write_section("jev_estimate", body)
    elif args.command == "jev":
        body = run_jev(args, units)
        write_section("jev", body)
    else:
        body = run_free(units)
        write_section(args.command, body)
    shown = {k: v for k, v in body.items() if not k.startswith("o2_rows")}
    print(json.dumps(shown, indent=1))
    print(f"written {RESULTS.relative_to(ROOT).as_posix()}")
    if args.command == "jev" and not body["complete"]:
        raise SystemExit("decider calls failed, came back empty or hit the cap: incomplete")


if __name__ == "__main__":
    main()
