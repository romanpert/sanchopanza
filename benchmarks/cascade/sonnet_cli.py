"""P1, P2 and P9 of 2026-09-25: the Jev > Sonnet 5 cascade, Sonnet through the Claude Code CLI.

    python benchmarks/cascade/sonnet_cli.py --pilot 3 --rjudge R-JUDGE --register REG.json
    python benchmarks/cascade/sonnet_cli.py --record-hash
    python benchmarks/cascade/sonnet_cli.py --live --rjudge R-JUDGE --register REG.json \
        --codex test.json                                      # subscription, no key
    python benchmarks/cascade/sonnet_cli.py --rjudge ... --register ... --codex ...   # free

`docs/results/2026-09-25-cascade/prereg.md` and `prereg-codex.md` fix the design;
`docs/results/2026-09-28-cascade-sonnet/prereg-cli.md` changes only the path to Sonnet. Jev's
answers replay from `fixtures/cascade-jev.jsonl`; Sonnet's sessions are cached in
`fixtures/cli/cascade-sonnet.jsonl`, so a rerun without `--live` spends nothing.
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
_spec = importlib.util.spec_from_file_location("cascade_run", HERE / "run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

from sanchopanza.providers.claude_cli import (  # noqa: E402
    CeilingReached,
    ClaudeCLI,
    SessionCache,
)
from sanchopanza.providers.llm import SYSTEM, answers_from, build_schema  # noqa: E402

ROOT = run.ROOT
OUT = ROOT / "docs" / "results" / "2026-09-28-cascade-sonnet"
BASE = ROOT / "docs" / "results" / "2026-09-25-cascade"
CACHE = ROOT / "fixtures" / "cli" / "cascade-sonnet.jsonl"
MODEL = "claude-sonnet-5"
ARM = "sonnet"
CEILING_USD = 25.0  # prereg-cli.md: ~18 USD estimated from the pilot, hard stop at list price


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_preregs() -> None:
    run.require_prereg()  # prereg.md and points/actions.py, hashed together
    run.require_codex_prereg()
    registered = OUT / "prereg-cli.sha256"
    if not registered.exists() or registered.read_text().strip() != digest(OUT / "prereg-cli.md"):
        raise SystemExit("prereg-cli.md missing or changed: nothing spent")


def prompt_of(case: dict[str, Any]) -> str:
    return "state:\n" + json.dumps(case["state"], ensure_ascii=False, default=str)


async def ask(cases: list[dict[str, Any]], live: bool, ceiling: float) -> dict[str, dict[str, Any]]:
    cache = SessionCache(CACHE)
    cli = ClaudeCLI(model=MODEL, system=SYSTEM, ceiling_usd=ceiling, cache=cache, concurrency=6)
    done = 0

    async def one(case: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        nonlocal done
        schema = build_schema(case["questions"])
        key = SessionCache.key(MODEL, SYSTEM, schema, prompt_of(case))
        session = cache.get(key)
        if session is None and live:
            for _ in range(2):  # one retry, then the case counts as cancelled
                session = await cli.run(prompt_of(case), schema=schema)
                if session.ok and session.structured is not None:
                    break
        done += 1
        if done % 100 == 0:
            print(f"{done}/{len(cases)}  spent {cli.spent_usd:.2f} USD list", file=sys.stderr)
        ident = run.custom_id(case, ARM)
        if session is None or not session.ok or session.structured is None:
            return ident, {"label": None, "cost": None}
        answers = answers_from(session.structured, case["questions"])
        label, _ = run.label_of(case, answers)
        return ident, {"label": label, "cost": session.list_cost_usd}

    try:
        pairs = await asyncio.gather(*(one(c) for c in cases))
    except CeilingReached as stop:
        raise SystemExit(f"ceiling reached; answers so far are cached: {stop}") from stop
    print(f"spawned {cli.spawned}, spent {cli.spent_usd:.2f} USD list", file=sys.stderr)
    return dict(pairs)


def with_sonnet(rows: list[dict[str, Any]], cases, answers) -> list[dict[str, Any]]:
    """The recorded table, with the batch-era `sonnet` columns replaced by the CLI's."""
    by_id = {(c["set"], c["id"]): run.custom_id(c, ARM) for c in cases}
    out = []
    for r in rows:
        got = answers[by_id[(r["set"], r["id"])]]
        out.append({**r, ARM: got["label"], f"{ARM}_cost": got["cost"]})
    return out


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"model": MODEL, "path": "claude code cli", "sets": {}}
    for name in sorted({r["set"] for r in rows}):
        subset = [r for r in rows if r["set"] == name]
        answered = [r for r in subset if r[ARM] is not None]
        block = run.analyze_set(subset, ARM)
        block["passes"] = run.verdict(block)
        entry = {
            "cases": len(subset),
            "answered": len(answered),
            "cancelled": len(subset) - len(answered),
            "sonnet_acc_answered": round(
                sum(r[ARM] == r["label"] for r in answered) / len(answered), 4
            ),
            "jev_acc_same_cases": round(
                sum(r["jev"] == r["label"] for r in answered) / len(answered), 4
            ),
            "cascade": block,
        }
        if name in ("rjudge", "codex"):
            held = [r for r in subset if r["half"] == "held_out" and r[ARM] is not None]
            picked = [
                r["jev"] if r["jev"] is not None and r["jev_conf"] >= block["tau"] else r[ARM]
                for r in held
            ]
            entry["held_out_rates"] = {
                "cascade": run.rates(held, picked),
                "sonnet": run.rates(held, [r[ARM] for r in held]),
                "jev": run.rates(held, [r["jev"] for r in held]),
            }
        result["sets"][name] = entry
    sets = result["sets"]
    p1 = sets.get("rjudge", {}).get("cascade", {}).get("passes")
    p2 = sets.get("register", {}).get("cascade", {}).get("passes")
    result["P1_rjudge"], result["P2_register"] = p1, p2
    result["P9_codex"] = sets.get("codex", {}).get("cascade", {}).get("passes")
    result["verdict_P1_P2"] = "solid" if p1 and p2 else "partial" if (p1 or p2) else "negative"
    return result


def write_hash(target: pathlib.Path, value: str) -> None:
    if target.exists() and target.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit(f"{target.name} already holds a different hash: nothing written")
    target.write_text(value + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--pilot", type=int, default=0, help="ask the first N R-Judge cases only")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--rjudge", default="")
    ap.add_argument("--register", default="")
    ap.add_argument("--codex", default="")
    args = ap.parse_args()
    if args.record_hash:
        write_hash(OUT / "prereg-cli.sha256", digest(OUT / "prereg-cli.md"))
        print(digest(OUT / "prereg-cli.md"))
        return 0
    cases = run.load_all(args)
    if args.pilot:
        # Cost only: labels are never compared with the gold here.
        pilot = cases[: args.pilot]
        asyncio.run(ask(pilot, live=True, ceiling=0.5))
        costs = [s.list_cost_usd for s in SessionCache(CACHE)._rows.values()]  # noqa: SLF001
        print(f"pilot sessions {len(costs)}, mean {sum(costs) / max(len(costs), 1):.4f} USD")
        return 0
    if args.live:
        require_preregs()
    answers = asyncio.run(ask(cases, args.live, CEILING_USD))
    rows = with_sonnet(asyncio.run(run.table(cases)), cases, answers)
    result = report(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
