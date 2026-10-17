"""Whether Windows Update is paused long enough for a lot to run through 02:00-08:00, when it
otherwise restarts this machine. Read from the registry Settings writes on "Pause updates";
free: no model, no API, no Jev.

A long lot's quiet hours exist only because of those restarts. They lift when the pause outlasts
the check by `MARGIN`; a pause that ends sooner, or that cannot be read, keeps them."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping

UX = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
# Settings writes both on "Pause updates"; quality updates are the ones that restart overnight.
ENDS = ("PauseUpdatesExpiryTime", "PauseQualityUpdatesEndTime")
# And the update agent's own flag (1 while quality updates are paused): stale UX values left
# after "Resume updates", or a policy, do not count as a pause.
POLICY, PAUSED = r"SOFTWARE\Microsoft\WindowsUpdate\UpdatePolicy\Settings", "PausedQualityStatus"
MARGIN = dt.timedelta(hours=24)  # longer than any lot's remaining wall (guard: 8-16 h; W17: ~4 h)


def _values(path: str, names: tuple[str, ...]) -> dict[str, str]:
    """The `names` present under HKLM\\`path` ({} when none, or off Windows)."""
    try:
        import winreg
    except ImportError:
        return {}
    found: dict[str, str] = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
    except OSError:
        return {}
    with key:
        for name in names:
            try:
                value, _ = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            found[name] = str(value)
    return found


def _read_ux() -> dict[str, str]:
    """The `ENDS` values under `UX` and the `PAUSED` flag under `POLICY`, as found."""
    return {**_values(UX, ENDS), **_values(POLICY, (PAUSED,))}


def _parse(text: str) -> dt.datetime | None:
    try:
        when = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=dt.UTC)


def paused_until(values: Mapping[str, str]) -> dt.datetime | None:
    """The earliest end among the pause values (None when there is none, or one is unreadable:
    a pause half written by Settings is no pause)."""
    ends = [_parse(v) for k, v in values.items() if k in ENDS]
    if not ends:
        return None
    if any(e is None for e in ends):
        return None
    return min(e for e in ends if e is not None)


def quiet_lifted(now: dt.datetime | None = None,
                 read: Callable[[], Mapping[str, str]] = _read_ux) -> str:  # fmt: skip
    """Why the quiet hours are lifted ("" when they hold): updates paused past now + MARGIN,
    with the update agent's flag on."""
    values = read()
    until = paused_until(values) if values.get(PAUSED) == "1" else None
    now = (now or dt.datetime.now()).astimezone(dt.UTC)
    if until is None or until < now + MARGIN:
        return ""
    return f"Windows Update paused until {until:%Y-%m-%d %H:%M} UTC"
