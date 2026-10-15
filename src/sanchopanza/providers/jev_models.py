"""Jev model versions: which one a name pins, and what each version can do.

Kept apart from `providers.jev` so that the recordings (`providers.recorded`) can tell a 1.13
answer from a 1.14 one without importing the HTTP client.

- `jev-1.14.0` (2026-10-14) adds the Box primitive; `jev-1.13.0` answers it with HTTP 400
  "Invalid request." (measured on both, 2026-10-15).
- The two Danger Zone headers (images, long context) work on both versions.
- An alias (`jev-latest`, `jev-preview`) names no version: it moves when a release ships, so
  nothing here can say what it supports. The server decides.
"""

from __future__ import annotations

import re

BOX_SINCE = (1, 14)
# From this version on, a recorded answer's key carries the model (`recorded.key_of`): every
# recording made before 1.14 has a key without it, and those keys must not change.
KEYED_SINCE = (1, 14)

_VERSION = re.compile(r"^jev-(\d+)\.(\d+)(?:\.(\d+))?$")


def version_of(model: str | None) -> tuple[int, int, int] | None:
    """`jev-1.14.0` -> (1, 14, 0). None for an alias or any other provider's model."""
    found = _VERSION.match((model or "").strip())
    if found is None:
        return None
    major, minor, patch = found.groups()
    return int(major), int(minor), int(patch or 0)


def at_least(model: str | None, since: tuple[int, int]) -> bool | None:
    """Whether a pinned version is at least `since`; None when the name pins no version."""
    version = version_of(model)
    return None if version is None else version[:2] >= since


def supports_box(model: str | None) -> bool | None:
    return at_least(model, BOX_SINCE)


def keyed_by_model(model: str | None) -> bool:
    """Whether a recording of this model's answers carries the model in its key."""
    return bool(at_least(model, KEYED_SINCE))
