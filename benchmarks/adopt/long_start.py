"""Before a long run asks anything (`long_run.py`): why it may not start, and the midnight rule.
Free: no model, no API, no Jev."""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "memory_carry"))

import carry  # noqa: E402
import docker_env  # noqa: E402
import long_guard  # noqa: E402
import run  # noqa: E402
import winupdate  # noqa: E402
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


QUIET = (0, 8)  # no chain starts in these hours: past midnight, and Windows Update's 02:00-08:00


def quiet_refusal(profile: Any, allow: bool, now: dt.datetime | None = None,
                  lifted: Callable[[], str] = winupdate.quiet_lifted) -> str:  # fmt: skip
    """A day-only profile (the guard-pointers lot) starts no chain between 00:00 and 08:00:
    Windows Update restarts the PC in 02:00-08:00 (the close-out lost a call to it at 05:04).
    Amendment 1 (sealed before any data): the hours lift while updates are paused for at least
    another `winupdate.MARGIN` (`winupdate.quiet_lifted`), checked at every call."""
    hour = (now or dt.datetime.now()).hour
    if getattr(profile, "day_only", False) and not allow and QUIET[0] <= hour < QUIET[1]:
        if lifted():
            return ""
        return f"no chain starts between {QUIET[0]:02d}:00 and {QUIET[1]:02d}:00 (Windows Update)"
    return ""


_WINDOWS = r"SOFTWARE\Microsoft\Windows\CurrentVersion"
RESTART_KEYS = (_WINDOWS + r"\WindowsUpdate\Auto Update\RebootRequired",
                _WINDOWS + r"\Component Based Servicing\RebootPending")


def restart_pending() -> str:
    """The first of `RESTART_KEYS` present under HKLM ("" when none, or off Windows)."""
    try:
        import winreg
    except ImportError:
        return ""
    for key in RESTART_KEYS:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key))
        except OSError:
            continue
        return key.rsplit("\\", 1)[-1]
    return ""


def restart_refusal(profile: Any, allow: bool) -> str:
    """A day-only profile starts no chain while Windows has a restart pending (checked before
    each chain, not only at the launch: an update can land mid-lot)."""
    if not getattr(profile, "day_only", False) or allow:
        return ""
    found = restart_pending()
    return f"Windows has a restart pending ({found})" if found else ""


def midnight_refusal(profile: Any, model: str, allow: bool) -> str:
    hours = profile.hours.get(model, 4.0) * len(profile.arms)
    if not allow and long_guard.crosses_midnight(dt.datetime.now(), hours):
        return f"a chain of ~{hours:.1f} h started now would cross midnight (pre-mortem 6)"
    return ""
