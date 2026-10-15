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

from sanchopanza.points.rules import (  # noqa: E402
    KEPT,
    questions_for_change,
    questions_for_relation,
)
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

FIXTURE = HERE / "rule_check_fixture.jsonl"
POINT = "memory.rule_check"

QUESTION = KEPT  # the product's question (`points.rules`), not a copy
WHOLE = {**SCENES, **HELD}


def cases(runs: list[Path], whole: bool = False, unrelated: bool = False,
          relation: bool = False) -> list[dict[str, Any]]:  # fmt: skip
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
            rules = [(row["scene"], WHOLE[row["scene"]]["first"] if whole
                      else RULES[row["scene"]], row["fact_kept"])]  # fmt: skip
            if unrelated:  # every other scene's rule against this diff: nothing to break
                rules = [(k, v, True) for k, v in RULES.items() if k != row["scene"]]
            for scene, rule, kept in rules:
                ask = questions_for_relation if relation else questions_for_change
                state, questions = ask(rule, diff)
                out.append({"run": root.name, "scene": row["scene"], "rule_of": scene,
                            "model": row["model"], "arm": row["arm"], "repeat": row["repeat"],
                            "kept": kept, "state": state, "questions": questions})  # fmt: skip
    return out


def api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    env_file = Path(named) if named else None
    if not key and env_file is not None and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    return key


def score(decision: Any) -> float | None:
    """High = kept: Truth `kept` as it is; Choice `relation` as 1 - P(breaks)."""
    if "relation" in decision.answers:
        return 1.0 - float(decision.answer("relation").probabilities.get("breaks", 0.0))
    return decision.answer("kept").truth


def probs(decision: Any) -> dict[str, float]:
    if "relation" in decision.answers:
        return dict(decision.answer("relation").probabilities)
    return {}


async def answer(items: list[dict[str, Any]], live: bool) -> float:
    recorded = RecordedDecider.from_file(FIXTURE) if FIXTURE.exists() else None
    writer = RecordingDecider(create("jev", api_key=api_key()), FIXTURE) if live else None
    gate, spent = asyncio.Semaphore(6), 0.0

    async def one(case: dict[str, Any]) -> None:
        nonlocal spent
        if recorded is not None:
            d = await recorded.decide(POINT, case["state"], case["questions"])
            if d.answers:
                case["p"], case["probs"] = score(d), probs(d)
                return
        if writer is None:
            return
        async with gate:
            d = await writer.decide(POINT, case["state"], case["questions"])
            spent += d.cost_usd
            case["p"], case["probs"] = score(d), probs(d)

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
    print(f"cases {len(items)}, answered {len(scored)}, broken {len(broken)}; "
          f"AUC {auc(scored):.3f}")
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
    parser.add_argument("--every", type=int, default=3, help="with --unrelated, one pair in N")
    parser.add_argument("--relation", action="store_true", help="the three-way Choice")
    parser.add_argument("--unrelated", action="store_true",
                        help="each diff against the other scenes' rules (false-alarm rate)")
    parser.add_argument("--whole", action="store_true",
                        help="the earlier request whole as the rule")
    args = parser.parse_args(argv)
    items = cases([Path(r) for r in args.runs], args.whole, args.unrelated, args.relation)
    if args.unrelated:
        items = items[:: args.every]
    spent = asyncio.run(answer(items, args.live))
    print(f"jev: {spent:.4f} USD")
    report(items, args.cut)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
