"""`install --memory-native`: the memory bridge's variable, owned by the flag (`memory_native`).

The bridge rides on memory's hooks, so it is wired only with `--memory`; without either, our
variable is taken out of the settings. Nobody else's keys are touched.
"""

from __future__ import annotations

from typing import Any

NATIVE_ENV = {"SANCHOPANZA_MEMORY_NATIVE": "1"}


def merge_memory_native(
    merged: dict[str, Any], on: bool
) -> tuple[dict[str, Any], list[str], list[str]]:
    """The settings with our variable in (`on`) or out, as a new object; (settings, added,
    removed)."""
    env = merged.get("env", {})
    if not isinstance(env, dict):
        return merged, [], []  # someone put something else there; do not fight it
    if on:
        changed = {k: v for k, v in NATIVE_ENV.items() if env.get(k) != v}
        if not changed:
            return merged, [], []
        return ({**merged, "env": {**env, **changed}},
                [f"env: {k}={v}" for k, v in changed.items()], [])  # fmt: skip
    stale = [k for k in NATIVE_ENV if k in env]
    if not stale:
        return merged, [], []
    kept = {k: v for k, v in env.items() if k not in stale}
    return {**merged, "env": kept}, [], [f"env: {k}" for k in stale]
