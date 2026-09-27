"""`sanchopanza install`: write the harness wiring instead of asking people to copy it.

The package shipped the hook and left the settings block in a docstring, which means every
install is a transcription exercise and every typo is a silent no-op: a hook that never
matches looks exactly like a hook that decided nothing. This module builds the block from
the same `HarnessConfig` the Guardian will use at runtime, so the matcher and the code can
never disagree.

It prints by default and only touches a file under `--write`. The file ends up matching the
flags of the last run, and running the same command twice changes nothing:

- Our own entries are recognised by their command line (`sanchopanza hook`, or the one given
  with `--command-line`), not by their matcher. A run with different flags replaces them
  instead of adding a second entry next to the first, which is how `install` followed by
  `install --scan-content` used to leave two PostToolUse entries and review every `Task`
  result twice (review of 2026-09-25). Every other hook, and every other key in the file, is
  preserved; an entry that also holds someone else's hook keeps that hook.
- `SANCHO_SCAN_CONTENT` and `SANCHO_CONTENT_TOOLS` follow `--scan-content`: a run without it
  removes them. `SANCHO_PROVIDER` is only ever set, never removed, since it is also read by
  other entry points.
- The first write keeps the untouched original in `<file>.bak` and never overwrites it;
  later writes keep what they replaced in `<file>.bak.<UTC timestamp>`.
- The write is atomic: a temporary file in the same directory, then `os.replace`. An
  interrupted write leaves the previous file whole.
- A settings file that is not a JSON object (a list, a string, `null`) is refused, as is
  invalid JSON, rather than overwritten.

The one decision worth understanding is `--scan-content`, which is off unless asked for. It
adds a PostToolUse scan of arriving content for instructions aimed at the model. That is a
detection control and not a barrier - by PostToolUse the bytes are in the transcript and the
harness offers no way to replace a tool result - so it warns the operator, names the passage
as data in front of the model, and journals the event. `points.injection` argues the case.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .generic import HarnessConfig

COMMAND = "sanchopanza hook"
# Owned by `--scan-content`: removed by a run without it.
SCAN_ENV = ("SANCHO_SCAN_CONTENT", "SANCHO_CONTENT_TOOLS", "SANCHO_CHECK_DONE")


@dataclass(frozen=True, slots=True)
class Settings:
    """A settings file and what would change in it."""

    path: Path
    merged: dict[str, Any]
    added: tuple[str, ...]
    removed: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def _pattern(names: frozenset[str]) -> str:
    # Claude Code reads the matcher as a regex: a tool name with a `.` or a `+` in it
    # would otherwise match other tools too, or none.
    return "|".join(re.escape(name) for name in sorted(names))


def matchers(config: HarnessConfig) -> dict[str, str]:
    """Event -> matcher regex, derived from the config rather than written twice."""
    pre = config.delegate_tools | config.search_tools | config.shell_tools
    post = config.delegate_tools | (config.content_tools if config.scan_content else frozenset())
    # Stop takes no tool matcher; "*" matches every stop. Empty means: not wired (and removed).
    return {
        "PreToolUse": _pattern(pre),
        "PostToolUse": _pattern(post),
        "Stop": "*" if config.check_done else "",
    }


def environment(config: HarnessConfig, *, provider: str = "") -> dict[str, str]:
    env: dict[str, str] = {}
    if provider:
        env["SANCHO_PROVIDER"] = provider
    if config.check_done:
        env["SANCHO_CHECK_DONE"] = "1"
    if config.scan_content:
        env["SANCHO_SCAN_CONTENT"] = "1"
        if config.content_tools != HarnessConfig().content_tools:
            env["SANCHO_CONTENT_TOOLS"] = ",".join(sorted(config.content_tools))
    return env


def _entry(matcher: str, command: str) -> dict[str, Any]:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}


def block(config: HarnessConfig, *, command: str = COMMAND, provider: str = "") -> dict[str, Any]:
    """The settings fragment on its own, for people who would rather paste it."""
    hooks = {
        event: [_entry(matcher, command)] for event, matcher in matchers(config).items() if matcher
    }
    fragment: dict[str, Any] = {"hooks": hooks}
    env = environment(config, provider=provider)
    if env:
        fragment["env"] = env
    return fragment


def _is_ours(hook: Any, commands: frozenset[str]) -> bool:
    return isinstance(hook, Mapping) and hook.get("command") in commands


def _owned(entries: list[Any], commands: frozenset[str]) -> list[Mapping[str, Any]]:
    """Entries holding at least one of our hooks."""
    return [
        e
        for e in entries
        if isinstance(e, Mapping) and any(_is_ours(h, commands) for h in e.get("hooks") or [])
    ]


def _already_wired(entries: list[Any], matcher: str, commands: frozenset[str]) -> bool:
    """Exactly one hook of ours, in an entry with the wanted matcher."""
    owned = _owned(entries, commands)
    if len(owned) != 1 or owned[0].get("matcher") != matcher:
        return False
    return sum(_is_ours(h, commands) for h in owned[0].get("hooks") or []) == 1


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


def _merge_hooks(
    hooks: dict[str, Any], config: HarnessConfig, command: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    commands = frozenset({command, COMMAND})
    out = dict(hooks)
    added: list[str] = []
    removed: list[str] = []
    for event, matcher in matchers(config).items():
        entries = out.get(event, [])
        if not isinstance(entries, list):  # someone put something else there; do not fight it
            continue
        if matcher and _already_wired(entries, matcher, commands):
            continue
        removed.extend(f"{event}: {e.get('matcher', '')}" for e in _owned(entries, commands))
        kept = _without_ours(entries, commands)
        if matcher:
            kept = [*kept, _entry(matcher, command)]
            added.append(f"{event}: {matcher}")
        out = {**out, event: kept}
    return out, added, removed


def _merge_env(
    env: dict[str, Any], config: HarnessConfig, provider: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    wanted = environment(config, provider=provider)
    stale = [k for k in SCAN_ENV if k in env and k not in wanted]
    changed = {k: v for k, v in wanted.items() if env.get(k) != v}
    out = {**{k: v for k, v in env.items() if k not in stale}, **changed}
    return (
        out,
        [f"env: {k}={v}" for k, v in changed.items()],
        [f"env: {k}" for k in stale],
    )


def merge(
    current: Mapping[str, Any], config: HarnessConfig, *, command: str = COMMAND, provider: str = ""
) -> tuple[dict[str, Any], list[str]]:
    """Existing settings plus ours. Other people's hooks and keys are never removed.

    Returns the merged settings and what was added. `plan` also reports what was removed
    (our own earlier entries and the scan variables); use it when that matters.
    """
    merged, added, _removed = _merge(current, config, command=command, provider=provider)
    return merged, added


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    names = {list: "array", str: "string", int: "number", float: "number"}
    return names.get(type(value), type(value).__name__)


def _merge(
    current: Any, config: HarnessConfig, *, command: str, provider: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    if current is None:
        current = {}
    if not isinstance(current, Mapping):
        raise ValueError(
            f"settings hold a JSON {_kind(current)}, not a JSON object; not touching it"
        )
    merged: dict[str, Any] = json.loads(json.dumps(current))
    added: list[str] = []
    removed: list[str] = []
    hooks = merged.get("hooks", {})
    if isinstance(hooks, dict):
        new_hooks, plus, minus = _merge_hooks(hooks, config, command)
        if plus or minus:
            merged = {**merged, "hooks": new_hooks}
        added, removed = [*added, *plus], [*removed, *minus]
    env = merged.get("env", {})
    if isinstance(env, dict):
        new_env, plus, minus = _merge_env(env, config, provider)
        if plus or minus:
            merged = {**merged, "env": new_env}
        added, removed = [*added, *plus], [*removed, *minus]
    return merged, added, removed


def default_path(scope: str = "user", root: Path | None = None) -> Path:
    """Where Claude Code keeps settings for that scope."""
    if scope == "project":
        return (root or Path.cwd()) / ".claude" / "settings.json"
    if scope == "local":
        return (root or Path.cwd()) / ".claude" / "settings.local.json"
    return Path.home() / ".claude" / "settings.json"


def plan(
    path: Path, config: HarnessConfig, *, command: str = COMMAND, provider: str = ""
) -> Settings:
    current: Any = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as error:
            raise ValueError(f"{path} is not valid JSON ({error}); not touching it") from error
        if not isinstance(current, dict):
            raise ValueError(
                f"{path} holds a JSON {_kind(current)}, not a JSON object; not touching it"
            )
    merged, added, removed = _merge(current, config, command=command, provider=provider)
    return Settings(path, merged, tuple(added), tuple(removed))


def _atomic_write(path: Path, data: bytes, *, mode_from: Path | None = None) -> None:
    """Write `data` to `path` through a temporary file in the same directory."""
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode_from is not None and mode_from.exists():
            with contextlib.suppress(OSError):
                shutil.copymode(mode_from, temporary)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def _backup_path(path: Path) -> Path:
    first = path.with_name(path.name + ".bak")
    if not first.exists():
        return first
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = path.with_name(f"{path.name}.bak.{stamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak.{stamp}-{counter}")
        counter += 1
    return candidate


def apply(settings: Settings) -> Path | None:
    """Write atomically, keeping a copy of whatever was there. Returns the backup, if any.

    The first backup (`<file>.bak`) is the file as it was before sancho ever wrote to it and
    is never overwritten; each later write keeps what it replaced in a timestamped copy.
    """
    path = settings.path
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.exists():
        backup = _backup_path(path)
        _atomic_write(backup, path.read_bytes(), mode_from=path)
    text = json.dumps(settings.merged, ensure_ascii=False, indent=2) + "\n"
    _atomic_write(path, text.encode("utf-8"), mode_from=path)
    return backup
