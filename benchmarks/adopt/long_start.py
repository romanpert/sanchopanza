"""Before a long run asks anything (`long_run.py`): why it may not start, and the midnight rule.
Free: no model, no API, no Jev."""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "memory_carry"))

import carry  # noqa: E402
import docker_env  # noqa: E402
import long_guard  # noqa: E402
import run  # noqa: E402
from long_money import held  # noqa: E402


def start_refusal(ctx: Any, names: list[str], known: Mapping[str, Any],
                  models: list[str]) -> str:  # fmt: skip
    """Why the run may not start ("" when it may). Free: no model is asked anything."""
    layout, profile = ctx.layout, ctx.profile
    if unknown := [n for n in names if n not in known]:
        return f"unknown chains {unknown}"
    if invalid := [n for n in names if not known[n].get("valid")]:
        return f"invalid chains {invalid}"
    if why := long_guard.manifest_refusal(names, known, ctx.manifests, run.chain_digest):
        return why
    if why := long_guard.stop_reason(layout.root, layout.limit):
        return why
    blocks, outside = held(layout, profile, names, models)
    if why := long_guard.plan_refusal(blocks, ctx.ceiling, outside):
        return why
    if why := docker_env.health():
        return why
    layout.root.mkdir(parents=True, exist_ok=True)
    if why := long_guard.disk_refusal(layout.root):
        return why
    carry.refuse_unclean(layout.root)  # no token, or memory files above the run root: exits
    carry.record_claude(layout.root, False, True, ctx.claude)  # not 2.1.287: exits
    return ""


def midnight_refusal(profile: Any, model: str, allow: bool) -> str:
    hours = profile.hours.get(model, 4.0) * len(profile.arms)
    if not allow and long_guard.crosses_midnight(dt.datetime.now(), hours):
        return f"a chain of ~{hours:.1f} h started now would cross midnight (pre-mortem 6)"
    return ""
