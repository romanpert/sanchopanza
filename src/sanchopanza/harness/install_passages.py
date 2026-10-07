"""`sanchopanza install --passages`: passages on arrival (`harness.passages_hook`), opt-in.

One `PostToolUse` entry on `Bash|PowerShell|Read` and the arm's two settings in the env block,
both owned by the flag: a run without it takes them out, beside everyone else's hooks. Not
`--lean` (the autopilot's no-decider configuration) nor `--prune` (browser snapshots, measured on
its own): this is a separate arm with its own measure, the re-request rate. It refuses
`--autopilot`, whose arrival cut also rewrites tool results: two hooks replacing one result have
no documented merge (the last write wins).

    sanchopanza install --passages --provider jev                          # 25 %, T = 2,000
    sanchopanza install --passages --passages-fraction 0.10 --provider jev  # the 10 % arm
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..context.passages import DEFAULT_FRACTION, DEFAULT_TOKENS
from .install import Settings
from .install_hooks import _merge_owned

PASSAGES_COMMAND = "sanchopanza passages-hook"
PASSAGES_HOOKS = {"PostToolUse": "Bash|PowerShell|Read"}
FRACTION_ENV = "SANCHOPANZA_PASSAGES_FRACTION"
TOKENS_ENV = "SANCHOPANZA_PASSAGES_TOKENS"
PASSAGES_ENV = (FRACTION_ENV, TOKENS_ENV)
MIN_TOKENS = 100


def check(on: bool, fraction: float, tokens: int, *, autopilot: bool) -> None:
    """Raise ValueError for settings the hook would ignore, or a clash with the autopilot."""
    if not on:
        return
    if not 0 < fraction < 1:
        raise ValueError(f"--passages-fraction must be between 0 and 1, not {fraction}")
    if tokens < MIN_TOKENS:
        raise ValueError(f"--passages-tokens must be at least {MIN_TOKENS}, not {tokens}")
    if autopilot:
        raise ValueError("--passages and --autopilot both cut tool results on arrival; pick one")


def _env(merged: dict[str, Any], wanted: Mapping[str, str]) -> tuple[dict, list, list]:
    env = merged.get("env", {})
    if not isinstance(env, dict):
        return merged, [], []  # someone put something else there; do not fight it
    stale = [k for k in PASSAGES_ENV if k in env and k not in wanted]
    changed = {k: v for k, v in wanted.items() if env.get(k) != v}
    if not stale and not changed:
        return merged, [], []
    out = {**{k: v for k, v in env.items() if k not in stale}, **changed}
    return ({**merged, "env": out}, [f"env: {k}={v}" for k, v in changed.items()],
            [f"env: {k}" for k in stale])  # fmt: skip


def with_passages(
    settings: Settings,
    *,
    on: bool,
    fraction: float = DEFAULT_FRACTION,
    tokens: int = DEFAULT_TOKENS,
) -> Settings:
    """`settings` with the passages hook and its env wired (`on`) or taken out."""
    merged, added, removed = _merge_owned(
        dict(settings.merged), on, PASSAGES_HOOKS, PASSAGES_COMMAND, PASSAGES_COMMAND, "passages"
    )
    wanted = {FRACTION_ENV: f"{fraction:g}", TOKENS_ENV: str(int(tokens))} if on else {}
    merged, plus, minus = _env(merged, wanted)
    return Settings(settings.path, merged, (*settings.added, *added, *plus),
                    (*settings.removed, *removed, *minus))  # fmt: skip
