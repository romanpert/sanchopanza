"""Environment variables and default directories, under the `sanchopanza` name.

Every variable is read as `SANCHOPANZA_<NAME>` first and `SANCHO_<NAME>` second, silently:
the project was called `sancho` until 2026-09-28 and existing settings files, shells and
recorded experiment scripts still set the old names. The new name wins when both are set.

The same goes for directories: `~/.sanchopanza` and `~/.cache/sanchopanza` are the
defaults, and the old `~/.sancho` or `~/.cache/sancho` is used only when the new one does
not exist and the old one does, so a journal or a dataset cache is not orphaned by the
rename.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

PREFIX = "SANCHOPANZA_"
LEGACY_PREFIX = "SANCHO_"
NAME = "sanchopanza"
LEGACY_NAME = "sancho"


def names(name: str) -> tuple[str, str]:
    """The new and the old spelling of one variable, e.g. `PROVIDER`."""
    return PREFIX + name, LEGACY_PREFIX + name


def get(name: str, default: str = "", env: Mapping[str, str] | None = None) -> str:
    """`SANCHOPANZA_<name>`, else `SANCHO_<name>`, else `default`."""
    source = os.environ if env is None else env
    for key in names(name):
        value = source.get(key)
        if value is not None:
            return value
    return default


def with_prefix(prefix: str, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Every variable under `SANCHOPANZA_<prefix>` or `SANCHO_<prefix>`, keyed by the rest
    of its name. The new spelling overrides the old one for the same key."""
    source = os.environ if env is None else env
    out: dict[str, str] = {}
    for full in reversed(names(prefix)):  # old first, so the new one overwrites it
        out.update({k[len(full) :]: v for k, v in source.items() if k.startswith(full)})
    return out


def _preferred(new: Path, old: Path) -> Path:
    return old if not new.exists() and old.exists() else new


def home_dir() -> Path:
    """`~/.sanchopanza`, or `~/.sancho` if only that one exists."""
    home = Path.home()
    return _preferred(home / f".{NAME}", home / f".{LEGACY_NAME}")


def cache_dir() -> Path:
    """`~/.cache/sanchopanza`, or `~/.cache/sancho` if only that one exists."""
    cache = Path.home() / ".cache"
    return _preferred(cache / NAME, cache / LEGACY_NAME)
