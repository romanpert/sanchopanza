"""Candor without the status block, measured (pre-registered in prereg-derive.md).

Three arms on every report of rounds 2-4 and on errata-bench's real sessions:

- `block`: the report as written, with its four-line block (rounds only; the reference);
- `prose`: the report without its block;
- `derived`: the prose checked with `candor.extract.check_with_derived` (one Jev call a report):
  the prose's findings plus what the derived block adds, capped at `high`. Its lock rate is the
  prose's by construction; what it can change is the review tier.

The rules are the same in every arm (v5, with the snapshot where the session took one). The
answers are recorded in `derive-answers.jsonl` (hashed keys, choices and probabilities, no text)
and replay free.

    python benchmarks/candor/derive.py              # replay only; unrecorded reports fall to prose
    python benchmarks/candor/derive.py --live       # Jev, capped (CAP_USD)
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "candor_external"))
OUT = HERE.parents[1] / "docs" / "results" / "2026-09-29-candor"
ANSWERS = OUT / "derive-answers.jsonl"
SCORED = OUT / "derive-scored.jsonl"
CAP_USD = 0.15
ROUNDS = ("2", "3", "4")


class _AskerSquire:
    """`monitors.Asker` behind the two methods `candor.extract` calls. An answer that is not
    recorded (replay) or not affordable raises, and the report stays prose."""

    def __init__(self, asker: Any) -> None:
        self.asker = asker

    async def decide(self, point: str, state: Any, questions: dict[str, Any]) -> Any:
        decision = await self.asker.ask(point, state, questions)
        if decision is None:
            raise LookupError("no recorded answer")
        return decision

    def record(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _round_items(name: str) -> list[dict[str, Any]]:
    os.environ["CANDOR_ROUND"] = name
    import rounds

    importlib.reload(rounds)
    import monitors

    importlib.reload(monitors)
    return [{**item, "round": name} for item in monitors.items()]


def _errata_items() -> list[dict[str, Any]]:
    import errata

    try:
        return [{**item, "round": "errata", "changed": None} for item in errata.items()]
    except OSError:
        return []  # gated data not fetched: the errata arm is NOT RUN


def _group(item: dict[str, Any]) -> str:
    if item["round"] == "errata":
        return "errata:objected" if item["positive"] else "errata:accepted"
    return f"r{item['round']}:{item['set']}:{'pos' if item['positive'] else 'neg'}"


async def _score(item: dict[str, Any], squire: Any) -> dict[str, Any]:
    import monitors

    from sanchopanza.candor import should_lock
    from sanchopanza.candor.claims import without_block
    from sanchopanza.candor.extract import check_with_derived
    from sanchopanza.candor.rules import check

    def verdict(report: Any) -> dict[str, Any]:
        found = [f.to_dict() for f in report.findings]
        added = [f for f in found if f.get("origin") == "model"]
        return {"critical": should_lock(found), "high": should_lock(found, on="high"),
                "added": sorted({f["rule"] for f in added})}  # fmt: skip

    def turn(said: str) -> Any:
        return monitors.turn_of({**item, "said": said}, block=True, snapshot=True)

    prose = without_block(item["said"])
    derived = verdict(await check_with_derived(squire, turn(prose)))
    row = {"id": item["id"], "round": item["round"], "group": _group(item),
           "positive": bool(item["positive"]), "derived_added": bool(derived["added"]),
           "prose": verdict(check(turn(prose))), "derived": derived}  # fmt: skip
    if item["round"] != "errata":
        row["block"] = verdict(check(turn(item["said"])))
    return row


async def run(live: bool) -> list[dict[str, Any]]:
    import monitors

    decider = None
    if live:
        from sanchopanza.providers import create

        decider = create("jev", api_key=os.environ["TYPESAFE_API_KEY"])
    asker = monitors.Asker("jev", decider, monitors.Store(ANSWERS), CAP_USD, live)
    squire = _AskerSquire(asker)
    out = []
    for name in ROUNDS:
        items = _round_items(name)
        out += await asyncio.gather(*(_score(i, squire) for i in items))
    out += await asyncio.gather(*(_score(i, squire) for i in _errata_items()))
    sys.stderr.write(f"Jev spent {asker.spent:.4f} USD (cap {CAP_USD})\n")
    return list(out)


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    table: dict[str, Counter[str]] = {}
    for r in rows:
        cell = table.setdefault(r["group"], Counter())
        cell["n"] += 1
        cell["derived_added"] += r["derived_added"]
        for arm in ("block", "prose", "derived"):
            if arm in r:
                cell[f"{arm}_critical"] += r[arm]["critical"]
                cell[f"{arm}_high"] += r[arm]["high"]
    return {g: dict(c) for g, c in sorted(table.items())}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="derive.py")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    rows = asyncio.run(run(args.live))
    SCORED.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    sys.stdout.write(json.dumps(summary(rows), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
