"""Jev 1.14 against 1.13, both live today and interleaved per case, on every component bench
(lot L1 of the 1.14 plan: experiment A1, plus A9, the injection point over the whole text).

    python benchmarks/jev114/jev114_components.py plan         # free: cases, calls, estimate
    python benchmarks/jev114/jev114_components.py replay       # free: recorded 1.13, today's code
    python benchmarks/jev114/jev114_components.py run --paid   # Jev only, both models, capped
    python benchmarks/jev114/jev114_components.py report       # free: tables and verdicts
    python benchmarks/jev114/jev114_components.py rerun --out DIR   # free: from fixtures/jev114

Every call goes through `CappedDecider` on the shared ledger (`--ledger`, cap 4.50 USD, this
lot `BATCH_CAP`), then a disk cache per model (a repeat costs 0), then a recording in
`fixtures/jev114/`, and a gate of at most `GATE` requests in flight. Arm order alternates by
case: even cases ask 1.13 first, odd ones 1.14 first. The key comes from TYPESAFE_API_KEY or
the `.env` file SANCHOPANZA_KEYS_ENV names, set only in this process and never printed. A
`STOP` file in the run directory stops scheduling new cases. Rows hold ids, labels, decisions
and numbers, never the texts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.contract import Decider, Decision, Question, State  # noqa: E402
from sanchopanza.eval.bench import Row, load_cases, run_bench  # noqa: E402
from sanchopanza.providers.cached import CachedDecider  # noqa: E402
from sanchopanza.providers.capped import CappedDecider, SpendCapReached  # noqa: E402
from sanchopanza.providers.recorded import (  # noqa: E402
    RecordedDecider,
    RecordingDecider,
    fixture_path,
)

MODELS = {"13r": "jev-1.13.0", "14": "jev-1.14.0"}
BATCH, BATCH_CAP, LEDGER_CAP = "jev114-l1", 0.30, 4.50
GATE, CASES_AT_ONCE = 4, 4
TTL_S = 14 * 86_400.0
RUN = Path(os.environ.get("SANCHOPANZA_JEV114_RUN", "C:/sp-runs/jev114")) / "l1"
LEDGER = Path("C:/sp-runs/jev114/ledger.json")  # shared by every lot: never moved by RUN
ATTEMPTS = 2  # a failed case is asked once more, then counts as that arm's error
FIXTURE = ROOT / "fixtures" / "l1-components.jsonl"
COMPONENT_OF_FILE = {
    "core": "public", "safety": "public", "graph": "public",
    "loop-b": "fifty", "memory-b": "fifty", "graph-build-b": "fifty", "retrieval-b": "fifty",
    "memory-collision-toward-branch": "collision", "memory-d": "collision",
    "steerability": "steerability", "agentdojo-injection": "agentdojo",
}  # fmt: skip
HISTORICAL = ("public-benches", "new-points-50-v2", "new-points", "collision-toward-branch",
              "steerability", "agentdojo-injection", "third-batch", "fourth-batch")  # fmt: skip


def bench_cases() -> list[dict[str, Any]]:
    """Every case of `benches/*.jsonl`, in file order, tagged with its file and component."""
    out = []
    for path in sorted((ROOT / "benches").glob("*.jsonl")):
        for case in load_cases([path]):
            component = COMPONENT_OF_FILE.get(path.stem, "rest")
            if case["point"] == "memory_collision":
                component = "collision"
            out.append({**case, "file": path.stem, "component": component})
    return out


def fixture_for(arm: str, name: str = FIXTURE.name) -> Path:
    """1.14 by `fixture_path`; the 1.13 re-run apart, so no published 1.13 fixture changes."""
    base = FIXTURE.with_name(name)
    if arm == "14":
        return fixture_path(base, MODELS["14"])
    return base.parent / "jev114" / f"{base.stem}-113r{base.suffix}"


def load_key() -> None:
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    if named and Path(named).is_file():
        for line in Path(named).read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                os.environ["TYPESAFE_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")
                return
    raise SystemExit("TYPESAFE_API_KEY is not set and SANCHOPANZA_KEYS_ENV names no key")


class Gated:
    """At most `gate` requests in flight across both arms."""

    def __init__(self, inner: Decider, gate: asyncio.Semaphore) -> None:
        self._inner, self._gate, self.name = inner, gate, inner.name

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        async with self._gate:
            return await self._inner.decide(point, state, questions)


class Probe:
    """Per case and arm: every decision the squire asked for, answers and errors included."""

    def __init__(self, inner: Decider) -> None:
        self._inner, self.name, self.calls = inner, inner.name, []

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        try:
            d = await self._inner.decide(point, state, questions)
        except Exception as error:
            why = f"{type(error).__name__}: {error}"[:300]
            capped = isinstance(error, SpendCapReached)
            self.calls.append({"point": point, "error": why, "capped": capped, "answers": {}})
            raise
        self.calls.append({"point": point, "model": d.model, "provider": d.provider,
                           "error": d.error, "cost_usd": d.cost_usd, "tokens": d.input_tokens,
                           "latency_ms": d.latency_ms,
                           "answers": {k: a.to_dict() for k, a in d.answers.items()}})  # fmt: skip
        return d


def live_stacks(gate: asyncio.Semaphore) -> dict[str, Decider]:
    from sanchopanza.providers.jev import JevDecider

    ledger = SpendLedger(LEDGER, cap_usd=LEDGER_CAP)
    stacks: dict[str, Decider] = {}
    for arm, model in MODELS.items():
        jev = JevDecider(model=model, long_context=False, images=False)
        recorded = RecordingDecider(Gated(jev, gate), fixture_for(arm))
        capped = CappedDecider(recorded, ledger=ledger, batch=BATCH, max_usd=BATCH_CAP)
        stacks[arm] = CachedDecider(capped, ttl_seconds=TTL_S, path=RUN / f"cache-{arm}.jsonl")
    return stacks


def row_dict(result: Row | dict[str, Any], case: Mapping[str, Any], arm: str,
             probe: Probe) -> dict[str, Any]:  # fmt: skip
    base = asdict(result) if isinstance(result, Row) else dict(result)
    return {**base, "arm": arm, "component": case.get("component"), "file": case.get("file"),
            "pair": case.get("pair"), "newer": (case.get("input") or {}).get("newer"),
            "calls": probe.calls, "at": time.time()}  # fmt: skip


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Every whole JSON line; a line cut short by a killed process is skipped."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line)) if line.strip() else None
        except ValueError:
            continue
    return rows


def done_keys(path: Path) -> set[tuple[str, str, str]]:
    """Cases not to ask again: answered, or failed `ATTEMPTS` times (capped runs do not count)."""
    from jev114_paired import capped, failed

    tries: dict[tuple[str, str, str], int] = {}
    done = set()
    for r in read_rows(path):
        key = (r["arm"], r["file"], r["id"])
        if capped(r):
            continue
        if not failed(r):
            done.add(key)
        tries[key] = tries.get(key, 0) + 1
    return done | {k for k, n in tries.items() if n >= ATTEMPTS}


def wrong_model(arm: str, probe: Probe) -> bool:
    """A call the provider answered (not the cache) with another model than the arm's."""
    return any(c.get("provider") == "jev" and c.get("model") != MODELS[arm] for c in probe.calls)


async def run_cases(cases: list[dict[str, Any]], stacks: Mapping[str, Decider], out: Path,
                    ask: Any) -> dict[str, int]:  # fmt: skip
    """Each case asked of both arms, order alternating; `ask(case, decider)` -> result."""
    done = done_keys(out)
    sem = asyncio.Semaphore(CASES_AT_ONCE)
    counts = {"asked": 0, "skipped": 0, "capped": 0, "wrong_model": 0}
    stop = RUN / "STOP"
    out.parent.mkdir(parents=True, exist_ok=True)

    async def one(index: int, case: dict[str, Any]) -> None:
        order = ("13r", "14") if index % 2 == 0 else ("14", "13r")
        async with sem:
            for arm in order:
                if (arm, case["file"], case["id"]) in done:
                    counts["skipped"] += 1
                    continue
                if stop.exists() or counts["capped"] or counts["wrong_model"]:
                    return
                probe = Probe(stacks[arm])
                result = await ask(case, probe)
                row = row_dict(result, case, arm, probe)
                counts["asked"] += 1
                counts["capped"] += any(c.get("capped") for c in probe.calls)
                counts["wrong_model"] += wrong_model(arm, probe)
                with out.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    await asyncio.gather(*(one(i, c) for i, c in enumerate(cases)))
    return counts


async def ask_bench(case: Mapping[str, Any], decider: Decider) -> Row | dict[str, Any]:
    return (await run_bench([case], decider, concurrency=1))[0]


def historical() -> RecordedDecider:
    """Every published 1.13 recording at once (unkeyed lines only)."""
    entries = []
    for name in HISTORICAL:
        path = ROOT / "fixtures" / f"{name}.jsonl"
        if path.exists():
            entries += [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()
                        if x.strip()]  # fmt: skip
    for path in sorted((ROOT / "fixtures" / "fifth-batch").glob("*.jsonl")):
        entries += [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()
                    if x.strip()]  # fmt: skip
    return RecordedDecider(entries)


def cmd_plan(_: argparse.Namespace) -> int:
    from jev114_extras import a9_cases, supersede_cases

    cases = bench_cases()
    by: dict[str, int] = {}
    for c in cases:
        by[c["component"]] = by.get(c["component"], 0) + 1
    chars = sum(len(json.dumps(c["input"], ensure_ascii=False)) for c in cases)
    sup, a9 = supersede_cases(), a9_cases()
    a9_chars = sum(len(c["input"]["text"]) for c in a9)
    print(f"bench cases {len(cases)} {by}; input chars {chars}")
    print(f"supersede cases {len(sup)}; A9 long cases {len(a9)} ({a9_chars} chars)")
    # Recorded 1.13: 0.0060 USD for 212 fifty cases, 0.0078 for 245 public: ~30 micro-USD a
    # case; agentdojo 34. Two arms. A9: whole text ~ chars/4 tokens, windows ~ the same again.
    bench_usd = len(cases) * 34e-6 * 2
    sup_usd = len(sup) * 34e-6 * 2
    a9_usd = (a9_chars / 4 + 600 * len(a9)) * 0.042e-6 * 2 * 2
    total = bench_usd + sup_usd + a9_usd
    print(f"estimate: bench {bench_usd:.4f} + supersede {sup_usd:.4f} + A9 {a9_usd:.4f} "
          f"= {total:.4f} USD (cap {BATCH_CAP})")  # fmt: skip
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    """The recorded 1.13 answers through today's code: the historical reference row."""
    from jev114_extras import supersede_historical

    decider = historical()

    async def go() -> list[dict[str, Any]]:
        rows = []
        for case in bench_cases():
            probe = Probe(decider)
            rows.append(row_dict(await ask_bench(case, probe), case, "113rec", probe))
        return rows

    rows = asyncio.run(go()) + supersede_historical()
    out = Path(args.out or RUN / "rows-113rec.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n",
                   encoding="utf-8")  # fmt: skip
    print(f"{len(rows)} rows -> {out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from jev114_extras import a9_cases, ask_a9_whole, ask_a9_windows, ask_supersede, supersede_cases

    if not args.paid:
        print("dry: nothing asked; pass --paid to spend")
        return cmd_plan(args)
    load_key()
    ledger = SpendLedger(LEDGER, cap_usd=LEDGER_CAP)
    if not preflight_both(ledger):
        return 3
    print(f"ledger {ledger.spent():.4f} of {LEDGER_CAP}; {BATCH} {ledger.spent(BATCH):.4f} "
          f"of {BATCH_CAP}")  # fmt: skip

    async def go() -> int:
        stacks = live_stacks(asyncio.Semaphore(GATE))
        parts = [("bench", bench_cases(), ask_bench), ("supersede", supersede_cases(),
                 ask_supersede), ("a9-windows", a9_cases(), ask_a9_windows),
                 ("a9-whole", a9_cases(), ask_a9_whole)]  # fmt: skip
        for name, cases, ask in parts:
            if args.only and name not in args.only:
                continue
            started = time.time()
            cases = cases[: args.limit] if args.limit else cases
            counts = await run_cases(cases, stacks, RUN / f"rows-{name}.jsonl", ask)
            print(f"{name}: {counts} in {time.time() - started:.0f} s; {BATCH} "
                  f"{ledger.spent(BATCH):.4f} USD", flush=True)  # fmt: skip
            if counts["capped"]:
                print(f"a call was refused (cap, or the ledger lock not taken in time): ledger "
                      f"{ledger.spent():.4f} of {LEDGER_CAP}, {BATCH} {ledger.spent(BATCH):.4f} "
                      f"of {BATCH_CAP}; stopping")  # fmt: skip
                return 2
            if counts["wrong_model"]:
                print("the provider answered with another model than the arm's: stopping")
                return 4
            if (RUN / "STOP").exists():
                print("STOP file: stopping")
                return 5
        return 0

    code = asyncio.run(go())
    print(f"ledger {ledger.spent():.4f}; {BATCH} {ledger.spent(BATCH):.4f}")
    return code


def preflight_both(ledger: SpendLedger) -> bool:
    """`jev-preflight` for each model (balance, key, served model), its cost on the ledger."""
    from sanchopanza.providers.jev import preflight

    ok = True
    for arm, model in MODELS.items():
        rid = ledger.reserve(0.0001, batch=BATCH, batch_cap_usd=BATCH_CAP)
        if rid is None:
            print("preflight refused by the ledger")
            return False
        result = preflight(model=model)
        ledger.settle(rid, result.cost_usd)
        served_ok = result.model == model
        print(f"preflight {arm}: {'ok' if result.ok else result.reason}; HTTP "
              f"{result.http_status}; served {result.model}; {result.cost_usd:.6f} USD")
        ok = ok and result.ok and served_ok
    return ok


def recorded_stacks() -> dict[str, Decider]:
    """Both live arms as recorded today: 13r unkeyed in its own file, 14 keyed by its model."""
    return {"13r": RecordedDecider.from_file(fixture_for("13r")),
            "14": RecordedDecider.from_file(fixture_for("14"), model=MODELS["14"])}  # fmt: skip


async def rerun_all(out: Path) -> None:
    """Every part of the run again, from the recordings: the rows `report` reads, for free."""
    from jev114_extras import a9_cases, ask_a9_whole, ask_a9_windows, ask_supersede, supersede_cases

    stacks = recorded_stacks()
    parts = [("bench", bench_cases(), ask_bench), ("supersede", supersede_cases(),
             ask_supersede), ("a9-windows", a9_cases(), ask_a9_windows),
             ("a9-whole", a9_cases(), ask_a9_whole)]  # fmt: skip
    for name, cases, ask in parts:
        await run_cases(cases, stacks, out / f"rows-{name}.jsonl", ask)


def cmd_rerun(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if any(out.glob("rows-*.jsonl")):
        raise SystemExit(f"{out} already holds rows; give an empty directory")
    asyncio.run(rerun_all(out))
    cmd_replay(argparse.Namespace(out=str(out / "rows-113rec.jsonl")))
    from jev114_report import write_report

    return write_report(out, out)


def cmd_report(args: argparse.Namespace) -> int:
    """From the run directory, or from `--rows` (the rows committed with the results); the 1.13
    reference is replayed from the published recordings when the rows directory lacks it."""
    from jev114_report import write_report

    run = Path(args.rows) if args.rows else RUN
    out = Path(args.out) if args.out else None
    hist = run / "rows-113rec.jsonl"
    if not hist.exists():
        hist = (out or run) / "rows-113rec.jsonl"
        cmd_replay(argparse.Namespace(out=str(hist)))
    return write_report(run, out, hist)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan").set_defaults(fn=cmd_plan)
    r = sub.add_parser("replay")
    r.add_argument("--out", default="")
    r.set_defaults(fn=cmd_replay)
    p = sub.add_parser("run")
    p.add_argument("--paid", action="store_true")
    p.add_argument("--only", nargs="*", default=None,
                   help="bench, supersede, a9-windows, a9-whole")  # fmt: skip
    p.add_argument("--limit", type=int, default=0, help="first N cases of each part (smoke)")
    p.set_defaults(fn=cmd_run)
    rr = sub.add_parser("rerun")
    rr.add_argument("--out", required=True)
    rr.set_defaults(fn=cmd_rerun)
    q = sub.add_parser("report")
    q.add_argument("--out", default="")
    q.add_argument("--rows", default="", help="a directory of rows-*.jsonl instead of the run")
    q.set_defaults(fn=cmd_report)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
