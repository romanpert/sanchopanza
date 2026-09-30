"""Browse, development: why Phase 2c's TOP arm lost to FULL. Free: replays every cache.

python benchmarks/browse/diagnose.py

For each of Phase 2c's 60 steps: where Jev ranked the target, where it ranked what Sonnet picked
in each arm, and Jev's probabilities at the top. Nothing here is a registered result; it points
at what the next registered test should change.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.browse import Element, rank  # noqa: E402
from sanchopanza.eval import harness as _harness  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


answers = _load("browse_answers", HERE / "answers.py")
phase1 = answers.phase1


async def ranking(step: dict[str, Any], recorded: Any) -> list[Any]:
    elements = [Element.from_dict(e) for e in step["elements"]]
    squire = Squire(recorded, thresholds=Thresholds(max_usd=1.0, max_decisions=500))
    return await rank(
        step["task"], elements, squire=squire, done=step["previous"], keep=len(elements)
    )


async def main() -> int:
    h = _harness.load()
    cli = h.ClaudeCLI(
        model=answers.MODEL, system=answers.SYSTEM, ceiling_usd=0.01, max_budget_usd=0.01,
        concurrency=1, cache=h.SessionCache(answers.CACHE), count_cached=True,
        spawn=answers.refuse_to_spawn,
    )  # fmt: skip
    recorded = phase1.InOrder(phase1.CONFIRM_FIXTURE)
    rows = []
    for step in answers.chosen_steps():
        ranked = await ranking(step, recorded)
        order = [r.element.key for r in ranked]
        pos = set(step["positives"])
        target = min((order.index(k) + 1 for k in pos if k in order), default=None)
        full = [Element.from_dict(e) for e in step["elements"]]
        top = [r.element for r in ranked[: answers.TOP]]
        picks = {}
        for arm, shown in (("FULL", full), ("TOP", top)):
            try:
                s = await cli.run(answers.prompt(step, shown), schema=answers.SCHEMA)
            except RuntimeError:
                picks[arm] = None
                continue
            n = (s.structured or {}).get("element")
            key = shown[n - 1].key if isinstance(n, int) and 1 <= n <= len(shown) else None
            picks[arm] = {
                "right": key in pos,
                "jev_rank": order.index(key) + 1 if key in order else None,
                "shown_at": n,
            }
        ps = [r.p or 0.0 for r in ranked[:25]]
        rows.append({
            "id": step["id"], "split": step["split"], "task": step["task"],
            "previous": step["previous"][-2:], "elements": len(full),
            "target_rank": target, "picks": picks,
            "p_top5": [round(p, 3) for p in ps[:5]],
            "p_20": round(ps[19], 3) if len(ps) > 19 else None,
            "target_line": next((e.line() for e in full if e.key in pos), None),
            "top_pick_line": (top[picks["TOP"]["shown_at"] - 1].line()
                              if picks.get("TOP") and picks["TOP"]["shown_at"] else None),
        })  # fmt: skip
    out = HERE.parents[1] / "docs" / "results" / "2026-09-30-browse" / "diagnose-2c.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    both = [r for r in rows if r["picks"].get("FULL") and r["picks"].get("TOP")]
    lost = [r for r in both if r["picks"]["FULL"]["right"] and not r["picks"]["TOP"]["right"]]
    won = [r for r in both if r["picks"]["TOP"]["right"] and not r["picks"]["FULL"]["right"]]
    print(f"steps {len(rows)}, both answered {len(both)}, TOP lost {len(lost)}, TOP won {len(won)}")
    for label, group in (("LOST", lost), ("WON", won)):
        for r in group:
            print(label, r["target_rank"], r["picks"], r["p_top5"], r["p_20"])
            print("   task:", r["task"][:110])
            print("   target:", (r["target_line"] or "")[:140])
            print("   TOP pick:", (r["top_pick_line"] or "")[:140])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
