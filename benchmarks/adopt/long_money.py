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
from typing import Any

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
