"""Parts or groups? Separating the two things the tool-selection failures were confounded on.

    python benchmarks/agentdojo/parts_bench.py --offline   # replay, free
    python benchmarks/agentdojo/parts_bench.py             # ~180 decisions, ~0.03 USD

On 2026-09-24 the selector kept every needed group on 53/53 one-group tasks and 33/37
two-group ones, and a page-triage run failed only on composite questions. In AgentDojo a task
that asks three things usually needs three groups, so "asks several things" and "needs
several groups" never varied apart, and the effect had no mechanism.

Here they vary apart. Each request joins 1 to 3 clauses written from templates whose group is
known, so the ground truth is by construction. The grid holds the number of distinct groups
fixed while the number of parts grows, and the other way round:

    parts 1: groups 1          parts 2: groups 1, 2          parts 3: groups 1, 2, 3

PRE-REGISTERED, before any decision was run (2026-09-25):

- H-groups: per-group recall falls with the number of DISTINCT groups needed, at a fixed
  number of parts. The independent per-group question has to say yes several times, and
  the known misses were groups the request mentions only in passing.
- H-parts: per-group recall falls with the number of PARTS, at a fixed number of groups:
  a longer request dilutes each clause.
- The two are compared on the cells (parts 3, groups 1) vs (parts 1, groups 1) for parts, and
  (parts 3, groups 3) vs (parts 3, groups 1) for groups. With 30 requests per cell the
  difference is reported with a paired-free two-proportion Wilson interval and called only if
  the intervals do not overlap. Otherwise the answer is "not separated at this n".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import random
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE.parents[1] / "benchmarks"))

from tools_bench import catalog  # noqa: E402

FIXTURE = HERE.parents[1] / "fixtures" / "parts.jsonl"
OUT = HERE.parents[1] / "docs" / "results" / "2026-09-25-window"
PER_CELL = 30
SEED = 11
CELLS = ((1, 1), (2, 1), (2, 2), (3, 1), (3, 2), (3, 3))

# Two or three clauses per group, written from the tools' own descriptions, before any run.
CLAUSES: dict[str, tuple[str, ...]] = {
    "calendar": (
        "move my dentist appointment to Thursday afternoon",
        "check who is invited to the team offsite",
        "create a meeting with Sara for next Monday at ten",
    ),
    "email": (
        "reply to the last email from the landlord",
        "find the email where Tom sent the contract",
        "send Lucia a short note saying I will be late",
    ),
    "files": (
        "share the budget spreadsheet with the finance team",
        "find the document with the onboarding checklist",
        "append today's notes to the project log file",
    ),
    "contacts": (
        "look up Marta's phone number",
        "find the email address of the new supplier contact",
    ),
    "hotels": (
        "find a hotel in Lisbon under 150 euros a night",
        "check the reviews of the Hotel Maris in Porto",
    ),
    "restaurants": (
        "book a table for four at an Italian place in Madrid",
        "find a vegan restaurant open late in Paris",
    ),
    "car_rental": (
        "rent an electric car in Berlin for the weekend",
        "compare the daily price of car rental companies in Rome",
    ),
    "flights": (
        "find the cheapest flight from London to Dublin on Friday",
        "check the flight times from Madrid to Lisbon next week",
    ),
    "accounts": (
        "tell me my current bank balance",
        "update the address on my bank account",
    ),
    "transactions": (
        "pay the electricity bill of 84 euros",
        "show my last ten transactions",
        "schedule a monthly transfer of 300 euros to my savings",
    ),
    "channels": (
        "add Pedro to the marketing channel",
        "list the members of the general channel",
    ),
    "messaging": (
        "post the release notes in the dev channel",
        "send a direct message to Ana saying thanks",
        "read the latest messages in the random channel",
    ),
    "web": (
        "summarise the article at www.example-news.com/ai-rules",
        "publish the event page at www.our-events.com/launch",
    ),
}
JOINERS = (", then ", ", and ", "; also ")


def requests() -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    groups = sorted(CLAUSES)
    out = []
    for parts, distinct in CELLS:
        # A group asked more than once needs that many distinct clauses: repeating a clause
        # verbatim would test a request no person writes.
        repeat = parts - distinct + 1
        eligible = [g for g in groups if len(CLAUSES[g]) >= repeat] if repeat > 1 else groups
        for i in range(PER_CELL):
            chosen = rng.sample(eligible, distinct)
            # distribute `parts` clauses over `distinct` groups, each group at least once
            plan = chosen + [rng.choice(chosen) for _ in range(parts - distinct)]
            rng.shuffle(plan)
            used: dict[str, list[str]] = {}
            clauses = []
            for g in plan:
                left = [c for c in CLAUSES[g] if c not in used.get(g, [])]
                clause = rng.choice(left or list(CLAUSES[g]))
                used.setdefault(g, []).append(clause)
                clauses.append(clause)
            text = clauses[0]
            for c in clauses[1:]:
                text += rng.choice(JOINERS) + c
            out.append(
                {
                    "id": f"pb-{parts}{distinct}-{i:02d}",
                    "parts": parts,
                    "groups": distinct,
                    "purpose": "Please " + text + ".",
                    "needed": sorted(set(plan)),
                }
            )
    return out


def decider(offline: bool) -> Any:
    from sanchopanza.providers import create
    from sanchopanza.providers.chain import FallbackDecider
    from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

    recorded = RecordedDecider.from_file(FIXTURE)
    if offline:
        return recorded
    live = RecordingDecider(create("jev", api_key=os.environ.get("TYPESAFE_API_KEY")), FIXTURE)
    return FallbackDecider([recorded, live])


async def run(offline: bool) -> list[dict[str, Any]]:
    from sanchopanza import MemoryJournal, Squire

    squire = Squire(decider(offline), journal=MemoryJournal())
    squire._t = squire.thresholds.with_(max_decisions=1000, max_usd=0.05)  # noqa: SLF001
    rows = []
    for req in requests():
        sel = await squire.select_tools(purpose=req["purpose"], catalog=catalog())
        kept = set(sel.keep)
        rows.append(
            {
                **req,
                "kept": sorted(kept),
                "hit": sorted(set(req["needed"]) & kept),
                "probabilities": sel.probabilities,
                "deferred": sel.deferred,
                "answered": bool(sel.probabilities),
            }
        )
    return rows


def report(rows: list[dict[str, Any]]) -> str:
    from thresholds import wilson_lower

    def wilson(k: int, n: int) -> tuple[float, float]:
        return wilson_lower(k, n), 1 - wilson_lower(n - k, n)

    lines = [
        "| parts | distinct groups | requests | all needed kept | per-group recall | 95 % Wilson | "
        "groups kept (mean) |",
        "|---|---|---|---|---|---|---|",
    ]
    cell: dict[tuple[int, int], tuple[int, int]] = {}
    for parts, distinct in CELLS:
        sub = [r for r in rows if r["parts"] == parts and r["groups"] == distinct]
        need = sum(len(r["needed"]) for r in sub)
        hit = sum(len(r["hit"]) for r in sub)
        cell[(parts, distinct)] = (hit, need)
        lo, hi = wilson(hit, need)
        lines.append(
            f"| {parts} | {distinct} | {len(sub)} | "
            f"{sum(len(r['hit']) == len(r['needed']) for r in sub)}/{len(sub)} | "
            f"{hit}/{need} = {hit / need:.0%} | {lo:.0%}-{hi:.0%} | "
            f"{sum(len(r['kept']) for r in sub) / len(sub):.1f} |"
        )

    def verdict(a: tuple[int, int], b: tuple[int, int]) -> str:
        la, ha = wilson(*a)
        lb, hb = wilson(*b)
        return "separated" if ha < lb or hb < la else "not separated at this n"

    lines += [
        "",
        f"H-parts, (3 parts, 1 group) vs (1 part, 1 group): {verdict(cell[(3, 1)], cell[(1, 1)])}.",
        f"H-groups, (3 parts, 3 groups) vs (3 parts, 1 group): "
        f"{verdict(cell[(3, 3)], cell[(3, 1)])}.",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    rows = asyncio.run(run(args.offline))
    if not all(r["answered"] for r in rows):
        raise SystemExit("some requests have no recorded answer: run without --offline")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "parts.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    text = report(rows)
    (OUT / "parts.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
