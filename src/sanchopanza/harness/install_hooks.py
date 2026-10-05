"""The hook-set machinery of `sanchopanza install`, and the browse sets built on it.

One set of our hooks is an event -> matcher map and a command line. `_merge_owned` wires it
or takes it out, beside everyone else's hooks: our entries are recognised by their command (or,
for an `mcp_tool` hook, by its server and tool), never by their matcher, so a second run with
other flags replaces them instead of adding a second entry. `install` builds its own sets (the
guard, candor, memory, find) on the same function.

The browse sets live here: crawl (`--crawl`), snapshot pruning (`--prune`), sources
(`--sources`) and the WebFetch hook (`--fetch`). `merge_browse` applies the four in that order.
This module never imports `install`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .crawl_hook import V8_HOOKS, V81_HOOKS
from .fetch_hook import FETCH_COMMAND, FETCH_HOOKS
from .sources_hook import SOURCES_COMMAND, SOURCES_HOOKS

__all__ = [
    "CRAWL_COMMAND",
    "CRAWL_HOOKS",
    "CRAWL_INSTALL_HOOKS",
    "FETCH_COMMAND",
    "FETCH_HOOKS",
    "PRUNE_COMMAND",
    "PRUNE_HOOKS",
    "SOURCES_COMMAND",
    "SOURCES_HOOKS",
    "hook_key",
    "merge_browse",
]

Merged = tuple[dict[str, Any], list[str], list[str]]

CRAWL_COMMAND = "sanchopanza crawl-hook"
# Event -> matcher for crawl (`--crawl`, `harness.crawl_hook`): the strategy line at every session
# start, and the time limit on any MCP server's browser_evaluate.
CRAWL_HOOKS = {"SessionStart": "", "PreToolUse": r"mcp__.*__browser_evaluate"}
# What `install --crawl` wires: every event the crawl hook answers. v8 and v8.1 (the line on
# gathering prompts, the echo cut, the notes at the head, the first screenshot denied) are switched
# on by env alone, and with only `CRAWL_HOOKS` wired their env did nothing, or (`LINE_AT=prompt`)
# took the line away. Without that env the extra events answer nothing. `CRAWL_HOOKS` and
# `_merge_crawl` stay as sealed benchmarks import them.
CRAWL_INSTALL_HOOKS = {**CRAWL_HOOKS, **V8_HOOKS, **V81_HOOKS}
PRUNE_COMMAND = "sanchopanza browse-hook"
# Event -> matcher for snapshot pruning (`--prune`, `harness.browse_hook`): inline snapshots on any
# MCP server's browser tools (a result past Claude Code's limit is read back by the hook itself).
# Never `browser_evaluate`: crawl owns its result (echo cut, notes at the head), and prune's
# confirmed result is about page snapshots (indagis-a1, S seal 2026-10-05).
PRUNE_HOOKS = {"PostToolUse": r"mcp__.*__browser_(?!evaluate$).*"}


def _entry(matcher: str, command: str) -> dict[str, Any]:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}


def hook_key(hook: Mapping[str, Any]) -> Any:
    """What makes a hook ours: its command, or for an `mcp_tool` hook its server and tool."""
    if hook.get("type") == "mcp_tool":
        return f"mcp_tool:{hook.get('server')}/{hook.get('tool')}"
    return hook.get("command")


def _is_ours(hook: Any, commands: frozenset[str]) -> bool:
    return isinstance(hook, Mapping) and hook_key(hook) in commands


def _owned(entries: list[Any], commands: frozenset[str]) -> list[Mapping[str, Any]]:
    """Entries holding at least one of our hooks."""
    return [
        e
        for e in entries
        if isinstance(e, Mapping) and any(_is_ours(h, commands) for h in e.get("hooks") or [])
    ]


def _already_wired(
    entries: list[Any],
    matcher: str,
    commands: frozenset[str],
    wanted: Mapping[str, Any] | None = None,
) -> bool:
    """Exactly one hook of ours, in an entry with the wanted matcher (and equal to `wanted`
    when the hook is more than a command)."""
    owned = _owned(entries, commands)
    if len(owned) != 1 or owned[0].get("matcher") != matcher:
        return False
    ours = [h for h in owned[0].get("hooks") or [] if _is_ours(h, commands)]
    return len(ours) == 1 and (wanted is None or ours[0] == wanted)


def _without_ours(entries: list[Any], commands: frozenset[str]) -> list[Any]:
    """The entries minus our hooks; an entry left with no hooks goes too."""
    out: list[Any] = []
    for entry in entries:
        hooks = entry.get("hooks") if isinstance(entry, Mapping) else None
        if not isinstance(hooks, list) or not any(_is_ours(h, commands) for h in hooks):
            out.append(entry)
            continue
        rest = [h for h in hooks if not _is_ours(h, commands)]
        if rest:
            out.append({**entry, "hooks": rest})
    return out


def _merge_owned(
    merged: dict[str, Any],
    on: bool,
    wanted: Mapping[str, str],
    command: str,
    default: str,
    label: str,
    hook: Mapping[str, Any] | None = None,
) -> Merged:
    """Wire one set of our hooks (event -> matcher), or take ours out. Other hooks on the same
    events are kept; our entries are recognised by their command (`command` or `default`), or
    for a `hook` that is not a command (`mcp_tool`) by its `hook_key`."""
    hooks = merged.get("hooks", {})
    if not isinstance(hooks, dict):
        return merged, [], []  # someone put something else there; do not fight it
    commands = frozenset({command, default} if hook is None else {hook_key(hook)})
    out = dict(hooks)
    added: list[str] = []
    removed: list[str] = []
    for event, matcher in wanted.items():
        entries = out.get(event, [])
        if not isinstance(entries, list):
            continue
        if on and _already_wired(entries, matcher, commands, hook):
            continue
        removed.extend(
            f"{event}: {e.get('matcher', '')} ({label})" for e in _owned(entries, commands)
        )
        kept = _without_ours(entries, commands)
        if on:
            wired = _entry(matcher, command) if hook is None else {
                "matcher": matcher, "hooks": [dict(hook)]}  # fmt: skip
            kept = [*kept, wired]
            added.append(f"{event}: {matcher} ({label})")
        others = {k: v for k, v in out.items() if k != event}
        out = {**out, event: kept} if kept else others
    if not (added or removed):
        return merged, [], []
    return {**merged, "hooks": out}, added, removed


def _merge_crawl(merged: dict[str, Any], on: bool, command: str = CRAWL_COMMAND) -> Merged:
    """Crawl's two hooks (`--crawl`)."""
    return _merge_owned(merged, on, CRAWL_HOOKS, command, CRAWL_COMMAND, "crawl")


def _merge_crawl_all(merged: dict[str, Any], on: bool, command: str = CRAWL_COMMAND) -> Merged:
    """Every event crawl answers (`--crawl`), its v8 and v8.1 behaviour left to the env."""
    return _merge_owned(merged, on, CRAWL_INSTALL_HOOKS, command, CRAWL_COMMAND, "crawl")


def _merge_prune(merged: dict[str, Any], on: bool, command: str = PRUNE_COMMAND) -> Merged:
    """Snapshot pruning's hook (`--prune`)."""
    return _merge_owned(merged, on, PRUNE_HOOKS, command, PRUNE_COMMAND, "prune")


def _merge_sources(merged: dict[str, Any], on: bool, command: str = SOURCES_COMMAND) -> Merged:
    """The sources request at the main agent's stop (`--sources`)."""
    return _merge_owned(merged, on, SOURCES_HOOKS, command, SOURCES_COMMAND, "sources")


def _merge_fetch(merged: dict[str, Any], on: bool, command: str = FETCH_COMMAND) -> Merged:
    """WebFetch sent to `fetch_passages` once per URL (`--fetch`)."""
    return _merge_owned(merged, on, FETCH_HOOKS, command, FETCH_COMMAND, "fetch")


def merge_browse(
    merged: dict[str, Any], *, crawl: bool, prune: bool, sources: bool, fetch: bool
) -> Merged:
    """The four browse sets, in order: crawl, prune, sources, fetch (each wired or taken out)."""
    added: list[str] = []
    removed: list[str] = []
    steps = ((_merge_crawl_all, crawl), (_merge_prune, prune), (_merge_sources, sources),
             (_merge_fetch, fetch))  # fmt: skip
    for step, on in steps:
        merged, plus, minus = step(merged, on)
        added, removed = [*added, *plus], [*removed, *minus]
    return merged, added, removed
