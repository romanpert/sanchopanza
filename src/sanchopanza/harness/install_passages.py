"""`sanchopanza install --passages`: passages on arrival (`harness.passages_hook`), opt-in.

Two entries, both owned by the flag and both with a `timeout`: `PostToolUse` on
`Bash|PowerShell|Read` (the cut) and `PreToolUse` on `Write|Edit|MultiEdit|NotebookEdit` (the
guard that denies rewriting a file from a cut view, `harness.passages_guard`). The env block gets
the arm's two settings and an explicit `SANCHOPANZA_PROVIDER` (the `--provider` given, `null`
without one), so an arm never ranks with Jev because a key happened to be in the environment. A
run without the flag takes ours out beside everyone else's hooks, and a `null` provider with it.

Not `--lean` (the autopilot's no-decider configuration) nor `--prune` (browser snapshots, measured
on its own): a separate arm with its own measure, the re-request rate. It refuses
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
GUARD_HOOKS = {"PreToolUse": "Write|Edit|MultiEdit|NotebookEdit"}
# Seconds Claude Code waits: the decision has 15 (`passages_hook.DECIDE_TIMEOUT_S`); the guard
# reads one small file.
POST_TIMEOUT_S = 30
PRE_TIMEOUT_S = 10
FRACTION_ENV = "SANCHOPANZA_PASSAGES_FRACTION"
TOKENS_ENV = "SANCHOPANZA_PASSAGES_TOKENS"
PROVIDER_ENV = "SANCHOPANZA_PROVIDER"
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


def _env(merged: dict[str, Any], wanted: Mapping[str, str],
         drop: tuple[str, ...]) -> tuple[dict, list, list]:  # fmt: skip
    env = merged.get("env", {})
    if not isinstance(env, dict):
        return merged, [], []  # someone put something else there; do not fight it
    stale = [k for k in drop if k in env and k not in wanted]
    changed = {k: v for k, v in wanted.items() if env.get(k) != v}
    if not stale and not changed:
        return merged, [], []
    out = {**{k: v for k, v in env.items() if k not in stale}, **changed}
    return ({**merged, "env": out}, [f"env: {k}={v}" for k, v in changed.items()],
            [f"env: {k}" for k in stale])  # fmt: skip


def _hook(timeout: int) -> dict[str, Any]:
    return {"type": "command", "command": PASSAGES_COMMAND, "timeout": timeout}


def with_passages(
    settings: Settings,
    *,
    on: bool,
    fraction: float = DEFAULT_FRACTION,
    tokens: int = DEFAULT_TOKENS,
    provider: str = "",
) -> Settings:
    """`settings` with the passages hook, its guard and its env wired (`on`) or taken out."""
    merged, added, removed = dict(settings.merged), [], []
    for events, timeout in ((PASSAGES_HOOKS, POST_TIMEOUT_S), (GUARD_HOOKS, PRE_TIMEOUT_S)):
        merged, plus, minus = _merge_owned(merged, on, events, PASSAGES_COMMAND,
                                           PASSAGES_COMMAND, "passages", hook=_hook(timeout))
        added, removed = [*added, *plus], [*removed, *minus]  # fmt: skip
    wanted = {FRACTION_ENV: f"{fraction:g}", TOKENS_ENV: str(int(tokens)),
              PROVIDER_ENV: provider or "null"} if on else {}  # fmt: skip
    env = merged.get("env") if isinstance(merged.get("env"), dict) else {}
    ours = (PROVIDER_ENV,) if not provider and env.get(PROVIDER_ENV) == "null" else ()
    merged, plus, minus = _env(merged, wanted, (*PASSAGES_ENV, *ours))
    return Settings(settings.path, merged, (*settings.added, *added, *plus),
                    (*settings.removed, *removed, *minus))  # fmt: skip
