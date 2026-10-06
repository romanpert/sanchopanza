"""The money a long run has spent and holds against its ceiling, read from the rows under its
root (owner USD, `meter.OWNER_RATES`). Shared by `long_run.py` and `long_launch.py`; nothing here
calls `claude`, an API or Jev.

- `spent`: every call under the root, earlier runs included (a cut call counts its caps).
- `blocks`: each chain and model at its caps (chain cap per arm times the arms).
- `held`: what a (re)started run holds: each chain and model at the larger of its caps and what it
  already spent, plus what was spent outside them. Counting the whole caps on top of the spend, a
  resume after real spending was refused at a ceiling the run fits under.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))  # benchmarks/meter.py

Block = tuple[str, str, float]


def rows_under(layout: Any) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(layout.runs.glob("*/*/row.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return rows


def spent(layout: Any) -> float:
    """Owner USD of every call under the root, earlier runs included."""
    return round(sum(c.get("owner_usd", 0.0) for r in rows_under(layout) for c in r["calls"]), 6)


def blocks(profile: Any, names: list[str], models: list[str]) -> list[Block]:
    return [(n, m, profile.chain_cap[m] * len(profile.arms)) for m in models for n in names]


def held(layout: Any, profile: Any, names: list[str],
         models: list[str]) -> tuple[list[Block], float]:  # fmt: skip
    """(blocks at the larger of caps and spend, the spend outside them)."""
    spent_in: dict[str, float] = {}
    for row in rows_under(layout):
        key = str(row.get("run", ""))
        spent_in[key] = spent_in.get(key, 0.0) + sum(c.get("owner_usd", 0.0) for c in row["calls"])
    out = [(n, m, max(cap, spent_in.get(f"{n}-{m}", 0.0)))
           for n, m, cap in blocks(profile, names, models)]  # fmt: skip
    inside = sum(spent_in.get(f"{n}-{m}", 0.0) for n, m, _c in out)
    return out, round(spent(layout) - inside, 6)


def ceiling_of(profile: Any, asked: float) -> float:
    ceiling = asked if asked > 0 else profile.ceiling
    if profile.hard_cap is not None and ceiling > profile.hard_cap:
        raise SystemExit(f"{profile.name}: the ceiling is at most {profile.hard_cap} USD (in code)")
    return ceiling


# ---- one turn past the cap -----------------------------------------------------------------------
# `--max-budget-usd` stops Claude Code BETWEEN turns, never inside one (live probe, 2026-10-06: a
# resumed Opus 5.5 call given 0.34 USD spent 0.94, its first turn writing the whole context to
# the cache again). So a call can pass any cap by one turn. The worst turn writes its whole
# context at the 1-hour cache-write rate and emits a maximal answer.

MAX_OUTPUT = 32_000  # output tokens one turn may emit (Claude Code's default ceiling)
CONTEXT_MARGIN = 50_000  # what a call adds to the context before its first turn (prompt, results)
DEFAULT_WINDOW = {"claude-haiku-4-5-20251001": 200_000, "claude-sonnet-5-5": 1_000_000,
                  "claude-opus-5-5": 1_000_000}  # fmt: skip
MIN_BUDGET = 0.05  # below this a call cannot take one turn


def turn_cost(model: str, context: int) -> float:
    """Owner USD of one turn that writes `context` tokens to the cache and answers MAX_OUTPUT."""
    import meter

    rates = meter.rates_of(meter.OWNER_RATES, model)
    return (context * rates.write_1h + MAX_OUTPUT * rates.output) / 1e6


def overshoot(model: str, context: int, window: int | None) -> float:
    """What the next call may spend past its budget: one turn at the context it can reach, the
    last call's peak plus CONTEXT_MARGIN, never above the window it compacts at."""
    limit = window or DEFAULT_WINDOW.get(model, 1_000_000)
    return round(turn_cost(model, min(limit, int(context) + CONTEXT_MARGIN)), 4)


def room_refusal(spent_now: float, cap: float, over: float, limit: float, what: str) -> str:
    """"" when a call of `cap` plus one turn `over` fits under `limit` after `spent_now`."""
    need = round(spent_now + cap + over, 4)
    return "" if need <= limit else (f"{what}: spent {spent_now:.2f} + call cap {cap:.2f} + one "
                                     f"turn {over:.2f} = {need:.2f} > {limit:.2f}")  # fmt: skip
