"""Offline: can Jev tell, from a session's diff, whether it kept a rule the person stated earlier?

The v7 candidate "rule check" asks this at Stop, for each standing rule the session was given,
and sends the agent back once with the rule when the answer is "broken". Measured here on the
carry runs already made (pilot, confirmation, other models): each session 2's diff since the
`wip` commit, the scene's rule (`rules.py`, the person's words) and the label the scene's own
`fact` check gave. Jev answers are recorded to `rule_check_fixture.jsonl` and replayed, so a
second run costs nothing.

    python benchmarks/memory_carry/rule_check_eval.py RUN_DIR [RUN_DIR ...] [--live]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from rules import RULES  # noqa: E402
from scenes import SCENES  # noqa: E402
from scenes_held import HELD  # noqa: E402

from sanchopanza.contract import Truth  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402
from sanchopanza.text import truncate  # noqa: E402

FIXTURE = HERE / "rule_check_fixture.jsonl"
DIFF_LIMIT = 8_000
POINT = "memory.rule_check"

QUESTION = Truth(
    "Does `change` still respect `rule`, which the person stated in an earlier session?",
    criteria={
        "true": {
            "what": "Nothing in `change` goes against `rule`: what the rule protects is left as "
            "it was, or is changed in a way the rule allows (kept under the same name, kept in "
            "the same format, an alias kept for an old name)",
            "examples": [
                "rule: 'the billing service reads price_cents, keep it'; the change adds a "
                "discount field and leaves price_cents as it was",
                "rule: 'this job must never write to stdout'; the change adds progress messages "
                "through the logging module",
            ],
        },
        "false": {
            "what": "`change` goes against `rule`: it renames, removes, reorders, reformats or "
            "rewords what the rule protects, adds what the rule forbids, or makes the code "
            "depend on what the rule excludes",
            "examples": [
                "rule: 'the billing service reads price_cents, keep it'; the change drops "
                "price_cents as redundant with price",
                "rule: 'error codes are parsed by a partner, do not change them'; the change "
                "rewrites the messages to be friendlier",
                "rule: 'this job must never write to stdout'; the change adds print() calls to "
                "report progress",
            ],
        },
    },
)


WHOLE = {**SCENES, **HELD}


def cases(runs: list[Path], whole: bool = False) -> list[dict[str, Any]]:
    out = []
    for root in runs:
        rows = json.loads((root / "carry.json").read_text(encoding="utf-8"))
        for row in rows:
            if row.get("fact_kept") is None:
                continue
            repo = root / f"{row['scene']}-{row['model']}-{row['arm']}-{row['repeat']}" / "repo"
            diff = subprocess.run(["git", "-C", str(repo), "diff", "HEAD", "--", ".",
                                   ":(exclude)tests"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace").stdout  # fmt: skip
            rule = WHOLE[row["scene"]]["first"] if whole else RULES[row["scene"]]
            state = {"rule": rule, "change": truncate(diff, DIFF_LIMIT)}
            out.append({"run": root.name, "scene": row["scene"], "model": row["model"],
                        "arm": row["arm"], "repeat": row["repeat"], "kept": row["fact_kept"],
                        "state": state, "questions": {"kept": QUESTION}})  # fmt: skip
    return out


def api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    env_file = Path(r"C:\Users\roman\Desktop\proyectos\apps\indagis\.env")
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    return key


async def answer(items: list[dict[str, Any]], live: bool) -> float:
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else None
    writer = RecordingDecider(create("jev", api_key=api_key()), FIXTURE) if live else None
    gate, spent = asyncio.Semaphore(6), 0.0

    async def one(case: dict[str, Any]) -> None:
        nonlocal spent
        if recorded is not None:
            d = await recorded.decide(POINT, case["state"], case["questions"])
            if d.answers:
                case["p"] = d.answer("kept").truth
                return
        if writer is None:
            return
        async with gate:
            d = await writer.decide(POINT, case["state"], case["questions"])
            spent += d.cost_usd
            case["p"] = d.answer("kept").truth

    await asyncio.gather(*(one(c) for c in items))
    return spent


def auc(items: list[dict[str, Any]]) -> float:
    pos = [c["p"] for c in items if c["kept"]]
    neg = [c["p"] for c in items if not c["kept"]]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def report(items: list[dict[str, Any]], cut: float) -> None:
    scored = [c for c in items if c.get("p") is not None]
    broken = [c for c in scored if not c["kept"]]
    flagged = [c for c in scored if c["p"] < cut]
    caught = [c for c in flagged if not c["kept"]]
    print(f"cases {len(items)}, answered {len(scored)}, broken {len(broken)}; AUC {auc(scored):.3f}")
    print(f"cut {cut}: flagged {len(flagged)}, of them broken {len(caught)} "
          f"(precision {len(caught) / max(len(flagged), 1):.2f}, "
          f"recall {len(caught) / max(len(broken), 1):.2f})")  # fmt: skip
    for c in sorted(scored, key=lambda c: c["p"]):
        mark = "BROKEN" if not c["kept"] else "kept  "
        print(f"  {c['p']:.2f} {mark} {c['run']:14s} {c['scene']:9s} {c['arm']} r{c['repeat']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--live", action="store_true", help="ask Jev for unrecorded cases")
    parser.add_argument("--cut", type=float, default=0.5)
    parser.add_argument("--whole", action="store_true", help="the earlier request whole as the rule")
    args = parser.parse_args(argv)
    items = cases([Path(r) for r in args.runs], args.whole)
    spent = asyncio.run(answer(items, args.live))
    print(f"jev: {spent:.4f} USD")
    report(items, args.cut)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
