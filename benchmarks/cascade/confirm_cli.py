"""The Jev > Opus 5 cascade at tau 0.45 on ATBench-Codex, Opus through the Claude Code CLI.

    python benchmarks/cascade/confirm_cli.py --record-hash
    python benchmarks/cascade/confirm_cli.py --live --codex test.json     # subscription, no key
    python benchmarks/cascade/confirm_cli.py --codex test.json            # free, from the cache
    python benchmarks/cascade/confirm_cli.py --rest --live --codex test.json  # other half

`docs/results/2026-09-27-cascade-frontier/prereg-confirm.md` fixes the design and
`prereg-confirm-cli.md` the path and the held-out half; `prereg-confirm-rest.md` adds the
other half and all 500, after the held-out verdict. Jev's answers replay from
`fixtures/cascade-jev.jsonl`; Opus's are cached in `fixtures/cli/cascade-opus.jsonl`, so a
rerun without `--live` spends nothing.
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
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

ROOT = run.ROOT
OUT = ROOT / "docs" / "results" / "2026-09-27-cascade-frontier"
PREREGS = ("prereg-confirm", "prereg-confirm-cli")
REST = "prereg-confirm-rest"
CACHE = ROOT / "fixtures" / "cli" / "cascade-opus.jsonl"
MODEL = "claude-opus-5"
TAU = 0.45
BAND = (0.35, 0.65)
CEILING_USD = 10.0  # prereg-confirm-cli.md: the held-out half, about 8.3 USD at list price


def digest(name: str) -> str:
    # Line endings normalised, as `tests/test_cascade_frontier.py` does: a checkout with
    # autocrlf turns LF into CRLF without changing one word of the registration.
    raw = (OUT / f"{name}.md").read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def require_preregs(names: tuple[str, ...] = PREREGS) -> None:
    for name in names:
        registered = OUT / f"{name}.sha256"
        if not registered.exists() or registered.read_text().strip() != digest(name):
            raise SystemExit(f"{name}.md missing or changed: nothing spent")


def prompt_of(case: dict[str, Any]) -> str:
    return "state:\n" + json.dumps(case["state"], ensure_ascii=False, default=str)


async def ask_opus(cases: list[dict[str, Any]], live: bool) -> dict[str, dict[str, Any]]:
    cache = SessionCache(CACHE)
    cli = ClaudeCLI(model=MODEL, system=SYSTEM, ceiling_usd=CEILING_USD, cache=cache, concurrency=6)
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
        if done % 50 == 0:
            print(f"{done}/{len(cases)}  spent {cli.spent_usd:.2f} USD list", file=sys.stderr)
        if session is None or not session.ok or session.structured is None:
            return case["id"], {"label": None, "cost": None}
        answers = answers_from(session.structured, case["questions"])
        label, _ = run.label_of(case, answers)
        return case["id"], {"label": label, "cost": session.list_cost_usd}

    try:
        pairs = await asyncio.gather(*(one(c) for c in cases))
    except CeilingReached as stop:
        raise SystemExit(f"ceiling reached; answers so far are cached: {stop}") from stop
    print(f"spawned {cli.spawned}, spent {cli.spent_usd:.2f} USD list", file=sys.stderr)
    return dict(pairs)


async def jev_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jev = RecordedDecider.from_file(run.JEV_FIXTURE)
    rows = []
    for case in cases:
        decision = await jev.decide(case["point"], case["state"], case["questions"])
        label, conf = run.label_of(case, dict(decision.answers))
        rows.append(
            {
                "id": case["id"],
                "label": case["label"],
                "jev": label,
                "jev_conf": conf,
                "jev_cost": decision.cost_usd,
            }
        )
    return rows


def at(rows: list[dict[str, Any]], tau: float) -> dict[str, Any]:
    hits, cost, escalated = run.cascade(rows, "opus", tau)
    alone_hits, alone_cost = run.alone(rows, "opus")
    diff, low, high = run.paired_bootstrap(hits, alone_hits)
    answers = [
        r["jev"] if r["jev"] is not None and r["jev_conf"] >= tau else r["opus"] for r in rows
    ]
    return {
        "tau": tau,
        "cascade_acc": round(sum(hits) / len(rows), 4),
        "opus_acc": round(sum(alone_hits) / len(rows), 4),
        "diff": round(diff, 4),
        "ci95": [round(low, 4), round(high, 4)],
        "cost_ratio": round(cost / alone_cost, 4),
        "escalated": escalated,
        "false_allow_cascade": run.rates(rows, answers)["fnr"],
        "false_allow_opus": run.rates(rows, [r["opus"] for r in rows])["fnr"],
        "false_allow_jev": run.rates(rows, [r["jev"] for r in rows])["fnr"],
    }


def analyze(rows: list[dict[str, Any]], opus: dict[str, dict[str, Any]]) -> dict[str, Any]:
    joined = [
        {**r, "opus": opus[r["id"]]["label"], "opus_cost": opus[r["id"]]["cost"]} for r in rows
    ]
    answered = [r for r in joined if r["opus"] is not None and r["jev"] is not None]
    main = at(answered, TAU)
    report = {
        "model": MODEL,
        "path": "claude code cli",
        "n": len(joined),
        "answered": len(answered),
        "cancelled": len(joined) - len(answered),
        "jev_acc": round(sum(r["jev"] == r["label"] for r in answered) / len(answered), 4),
        "primary": main,
        "band": [at(answered, t) for t in BAND],
        "C1": main["diff"] >= -0.02,
        "C2": main["ci95"][0] >= -0.06,
        "C3": main["cost_ratio"] <= 0.50,
    }
    report["verdict"] = (
        "confirmed" if report["C1"] and report["C2"] and report["C3"] else "negative"
    )
    return report


def write_hash(target: pathlib.Path, value: str) -> None:
    """Register a hash once. A different hash already there means the registration changed
    after it was recorded: refuse, and let a person delete the old one on purpose."""
    if target.exists() and target.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit(f"{target.name} already holds a different hash: nothing written")
    target.write_text(value + "\n", encoding="utf-8")


def measure(cases: list[dict[str, Any]], live: bool) -> dict[str, Any]:
    rows = asyncio.run(jev_rows(cases))
    if any(r["jev"] is None for r in rows):
        print("some Jev answers are missing from the recording", file=sys.stderr)
    return analyze(rows, asyncio.run(ask_opus(cases, live)))


def rest(args: argparse.Namespace) -> int:
    """prereg-confirm-rest.md: the derivation half, then all 500. Held-out answers replay."""
    require_preregs((*PREREGS, REST))
    cases = run.load_codex(pathlib.Path(args.codex))
    other = [c for c in cases if run.half(c) == "derivation"]
    report = {
        "other_half": measure(other, args.live),
        "all_500": measure(cases, False),  # every session is cached by now: nothing spent
    }
    (OUT / "confirm-rest-analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--rest", action="store_true", help="prereg-confirm-rest.md")
    ap.add_argument("--codex", default="")
    args = ap.parse_args()
    if args.record_hash:
        name = REST if args.rest else "prereg-confirm-cli"
        write_hash(OUT / f"{name}.sha256", digest(name))
        print(digest(name))
        return 0
    if args.rest:
        return rest(args)
    require_preregs()
    # prereg-confirm-cli.md registers the held-out half (a cost pilot put all 500 cases at
    # ~16.5 USD list): `run.half`, a hash of the case id fixed before any of this.
    cases = [c for c in run.load_codex(pathlib.Path(args.codex)) if run.half(c) == "held_out"]
    report = measure(cases, args.live)
    (OUT / "confirm-cli-analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
