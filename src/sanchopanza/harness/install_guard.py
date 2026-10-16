"""The compaction guard's hooks, as `sanchopanza install --guard` wires them.

Three events (`harness.guard_hook`): `PreCompact` on `manual|auto` builds the guard, `SessionStart`
on `compact` attaches it after the summary, `PostToolUse` on `Bash` gives a re-run its earlier
output.

By default (since 2026-10-16) the hook's own default chooser, the pointer block
(`context.pointers`: requests verbatim, files changed, pointers to earlier output and archived
files for output that cannot be had again), fits one hook's inline limit: one command per event,
no chooser in the settings. `--guard-full` restores the whole-results block (`context.structural`):
it writes `SANCHOPANZA_GUARD_CHOOSER=struct`, and since Claude Code keeps each hook's context
inline only up to 10,000 characters that block is split (`context.parts`): `PreCompact` runs as
`sanchopanza guard-hook --parts K` and the `SessionStart` entry holds K commands,
`sanchopanza guard-hook --part i --parts K`, each printing its own part or nothing. K is
`context.parts.default_parts` of the struct budget and the inline cap (6 at the defaults) unless
`--guard-parts` says otherwise; 1 wires the single capped block. A chooser the owner set is
theirs: ours is marked (`SANCHOPANZA_GUARD_CHOOSER_BY=sanchopanza`), and only a marked one is
ever overwritten or taken out.

Our hooks are recognised by their command (`sanchopanza guard-hook`, with or without `--part` and
`--parts`), never by their matcher, so a run with another K replaces them and a run without the
flag takes them all out.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .install_hooks import _owned, _without_ours

GUARD_COMMAND = "sanchopanza guard-hook"
# Event -> matcher for the compaction guard (`--guard`, `harness.guard_hook`).
GUARD_HOOKS = {"PreCompact": "manual|auto", "SessionStart": "compact", "PostToolUse": "Bash"}

Merged = tuple[dict[str, Any], list[str], list[str]]


CHOOSER = "SANCHOPANZA_GUARD_CHOOSER"
FULL_CHOOSER = "struct"  # the whole-results block, `--guard-full`
CHOOSER_BY = "SANCHOPANZA_GUARD_CHOOSER_BY"  # marks the chooser as written by `--guard-full`
MARK = "sanchopanza"


def default_guard_parts(full: bool = False) -> int:
    """K for this environment: 1 for the pointer block; for the whole-results block (`full`),
    from the struct budget and inline cap the hooks will read."""
    from ..context import parts, structural
    from .guard_hook import _cap, _int

    if not full:
        return 1
    return parts.default_parts(
        _int("GUARD_STRUCT_CHARS", structural.STRUCT_CHARS),
        _cap("GUARD_INLINE_CHARS", structural.INLINE_CHARS),
    )


def guard_commands(parts: int, command: str = GUARD_COMMAND) -> dict[str, tuple[str, ...]]:
    """Event -> the commands of its one entry, in order."""
    if parts <= 1:
        return dict.fromkeys(GUARD_HOOKS, (command,))
    return {
        "PreCompact": (f"{command} --parts {parts}",),
        "SessionStart": tuple(f"{command} --part {i} --parts {parts}" for i in range(1, parts + 1)),
        "PostToolUse": (command,),
    }


def is_guard_command(value: Any, command: str = GUARD_COMMAND) -> bool:
    """Our guard hook's command line, with any `--part` and `--parts`."""
    if not isinstance(value, str):
        return False
    return value == command or value.startswith(f"{command} --part")


def _guard_commands_in(entries: list[Any]) -> frozenset[str]:
    return frozenset(
        hook["command"]
        for entry in entries
        if isinstance(entry, Mapping)
        for hook in entry.get("hooks") or []
        if isinstance(hook, Mapping) and is_guard_command(hook.get("command"))
    )


def _wired(owned: list[Mapping[str, Any]], matcher: str, commands: tuple[str, ...],
           ours: frozenset[str]) -> bool:  # fmt: skip
    if len(owned) != 1 or owned[0].get("matcher") != matcher:
        return False
    found = [h.get("command") for h in owned[0].get("hooks") or [] if h.get("command") in ours]
    return found == list(commands)


def owner_chooser(merged: Mapping[str, Any]) -> str | None:
    """The chooser the owner set themselves (no marker of ours beside it), or None."""
    env = merged.get("env", {})
    if not isinstance(env, Mapping) or CHOOSER not in env or env.get(CHOOSER_BY) == MARK:
        return None
    return str(env.get(CHOOSER))


def merge_guard_chooser(merged: dict[str, Any], full: bool) -> Merged:
    """`SANCHOPANZA_GUARD_CHOOSER=struct` with `full`, marked ours (`CHOOSER_BY`); without it,
    ours out. A chooser the owner set (no marker) is never overwritten nor removed: `cli` says
    so when `--guard-full` meets one (`owner_chooser`)."""
    env = merged.get("env", {})
    if not isinstance(env, dict) or owner_chooser(merged) is not None:
        return merged, [], []
    ours = {CHOOSER: FULL_CHOOSER, CHOOSER_BY: MARK}
    if full:
        if all(env.get(k) == v for k, v in ours.items()):
            return merged, [], []
        return {**merged, "env": {**env, **ours}}, [f"env: {CHOOSER}=struct"], []
    if CHOOSER not in env and CHOOSER_BY not in env:
        return merged, [], []
    rest = {k: v for k, v in env.items() if k not in ours}
    return {**merged, "env": rest}, [], [f"env: {CHOOSER}"]


def merge_guard(merged: dict[str, Any], on: bool, parts: int = 1) -> Merged:
    """Wire the guard's hooks for `parts` parts, or take every guard hook out."""
    hooks = merged.get("hooks", {})
    if not isinstance(hooks, dict):
        return merged, [], []  # someone put something else there; do not fight it
    wanted = guard_commands(parts)
    out = dict(hooks)
    added: list[str] = []
    removed: list[str] = []
    for event, matcher in GUARD_HOOKS.items():
        entries = out.get(event, [])
        if not isinstance(entries, list):
            continue
        ours = _guard_commands_in(entries)
        owned = _owned(entries, ours)
        if (on and _wired(owned, matcher, wanted[event], ours)) or not (on or owned):
            continue
        removed.extend(f"{event}: {e.get('matcher', '')} (guard)" for e in owned)
        kept = _without_ours(entries, ours)
        if on:
            commands = wanted[event]
            hooks_of = [{"type": "command", "command": c} for c in commands]
            kept = [*kept, {"matcher": matcher, "hooks": hooks_of}]
            count = f", {len(commands)} parts" if len(commands) > 1 else ""
            added.append(f"{event}: {matcher} (guard{count})")
        others = {k: v for k, v in out.items() if k != event}
        out = {**out, event: kept} if kept else others
    if not (added or removed):
        return merged, [], []
    return {**merged, "hooks": out}, added, removed
