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
- `SANCHOPANZA_SCAN_CONTENT` and `SANCHOPANZA_CONTENT_TOOLS` follow `--scan-content`: a run
  without it removes them. `SANCHOPANZA_PROVIDER` is only ever set, never removed, since it is
  also read by other entry points.
- A variable written under its new `SANCHOPANZA_*` name replaces the same one under the old
  `SANCHO_*` name, so a file wired before the rename is migrated rather than doubled.
- The first write keeps the untouched original in `<file>.bak` and never overwrites it;
  later writes keep what they replaced in `<file>.bak.<UTC timestamp>`.
- The write is atomic: a temporary file in the same directory, then `os.replace`. An
  interrupted write leaves the previous file whole.
- A settings file that is not a JSON object (a list, a string, `null`) is refused, as is
  invalid JSON, rather than overwritten.

`--compact` also writes a small Claude Code plugin (default `~/.sanchopanza/claude-plugin`)
holding the function-hook module `compact_hook.ts`, which prunes tool results at `/compact`
instead of summarising (`sanchopanza.context`), and wires it: a directory marketplace in
`extraKnownMarketplaces`, the plugin in `enabledPlugins`, and
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` in `env`, since function hooks are early access and off
without it. The plugin entries are ours and a run without `--compact` removes them; the
variable is only ever set, never removed, because other plugins may need it. On its first start
with these settings Claude Code registers the marketplace in
`~/.claude/plugins/known_marketplaces.json` (checked with 2.1.282);
`claude plugin marketplace remove sanchopanza-local` takes it out again.

`--autopilot` wires the three autopilot pieces in one go (`harness.autopilot`): PostToolUse on
every tool (`*`: the arrival cut and recall on tool calls; the hook's fast path returns before
loading anything for results under the threshold), UserPromptSubmit (recall over memory files
and the archive), and the compaction plugin as `--compact` does, with the plugin set to the
free `mask` arm and to compact by itself when the context reaches
`SANCHOPANZA_COMPACT_AT_PERCENT` (60 unless already set). Its variables (`AUTOPILOT`,
`COMPACT_COMMAND`, `COMPACT_AT_PERCENT`) are owned by the flag: a run without it removes them.

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

from .. import _env
from .generic import HarnessConfig

PLUGIN = "sanchopanza-compact"
MARKETPLACE = "sanchopanza-local"
PLUGIN_KEY = f"{PLUGIN}@{MARKETPLACE}"
FUNCTION_HOOKS = "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"
HOOK_MODULE = "compact_hook.ts"

COMMAND = "sanchopanza hook"
AUTOPILOT_ENV = {
    "SANCHOPANZA_AUTOPILOT": "1",
    "SANCHOPANZA_COMPACT_COMMAND": "sanchopanza compact --stdin --arm mask",
    "SANCHOPANZA_COMPACT_AT_PERCENT": "60",
}
# Owned by `--scan-content`: removed by a run without it.
_SCAN = ("SCAN_CONTENT", "CONTENT_TOOLS", "CHECK_DONE")
SCAN_ENV = tuple(key for name in _SCAN for key in _env.names(name))
# New spelling -> old spelling, for every variable this module writes.
_LEGACY = {
    new: old for new, old in (_env.names(n) for n in (*_SCAN, "PROVIDER", "SCAN_SHELL_FETCHES"))
}


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


def matchers(config: HarnessConfig, *, autopilot: bool = False) -> dict[str, str]:
    """Event -> matcher regex, derived from the config rather than written twice."""
    pre = config.delegate_tools | config.search_tools | config.shell_tools
    post = config.after_tools()
    # Stop and UserPromptSubmit take no tool matcher; "*" matches every one. Empty means: not
    # wired (and removed). The autopilot sees every tool result: which to cut is per call.
    return {
        "PreToolUse": _pattern(pre),
        "PostToolUse": "*" if autopilot else _pattern(post),
        "Stop": "*" if config.check_done else "",
        "UserPromptSubmit": "*" if autopilot else "",
    }


def environment(
    config: HarnessConfig, *, provider: str = "", autopilot: bool = False, current: Any = None
) -> dict[str, str]:
    env: dict[str, str] = {}
    if autopilot:
        # A percentage the owner set is theirs; only a missing one gets the default.
        mine = current if isinstance(current, Mapping) else {}
        env.update({k: str(mine.get(k) or v) for k, v in AUTOPILOT_ENV.items()})
    if provider:
        env["SANCHOPANZA_PROVIDER"] = provider
    if config.check_done:
        env["SANCHOPANZA_CHECK_DONE"] = "1"
    if config.scan_content:
        env["SANCHOPANZA_SCAN_CONTENT"] = "1"
        if config.content_tools != HarnessConfig().content_tools:
            env["SANCHOPANZA_CONTENT_TOOLS"] = ",".join(sorted(config.content_tools))
        if not config.scan_shell_fetches:
            env["SANCHOPANZA_SCAN_SHELL_FETCHES"] = "0"
    return env


def portable_command(command: str, *, windows: bool | None = None) -> str:
    """Forward slashes in a hook command on Windows.

    Claude Code runs command hooks through a POSIX shell there, which reads a backslash as an
    escape: `C:\\Users\\me\\python.exe` arrives as `C:Usersmepython.exe`, the hook never runs, and
    nothing reports it (measured: 0 events of 1 with backslashes, 1 of 1 with forward slashes).
    """
    windows = os.name == "nt" if windows is None else windows
    return command.replace("\\", "/") if windows else command


def _entry(matcher: str, command: str) -> dict[str, Any]:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}


def block(
    config: HarnessConfig, *, command: str = COMMAND, provider: str = "", autopilot: bool = False
) -> dict[str, Any]:
    """The settings fragment on its own, for people who would rather paste it."""
    hooks = {
        event: [_entry(matcher, command)]
        for event, matcher in matchers(config, autopilot=autopilot).items()
        if matcher
    }
    fragment: dict[str, Any] = {"hooks": hooks}
    env = environment(config, provider=provider, autopilot=autopilot)
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
    hooks: dict[str, Any], config: HarnessConfig, command: str, autopilot: bool = False
) -> tuple[dict[str, Any], list[str], list[str]]:
    commands = frozenset({command, COMMAND})
    out = dict(hooks)
    added: list[str] = []
    removed: list[str] = []
    for event, matcher in matchers(config, autopilot=autopilot).items():
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
    env: dict[str, Any], config: HarnessConfig, provider: str, autopilot: bool = False
) -> tuple[dict[str, Any], list[str], list[str]]:
    wanted = environment(config, provider=provider, autopilot=autopilot, current=env)
    owned = (*SCAN_ENV, *AUTOPILOT_ENV)
    stale = [k for k in owned if k in env and k not in wanted]
    stale += [_LEGACY[k] for k in wanted if _LEGACY.get(k) in env and _LEGACY[k] not in stale]
    changed = {k: v for k, v in wanted.items() if env.get(k) != v}
    out = {**{k: v for k, v in env.items() if k not in stale}, **changed}
    return (
        out,
        [f"env: {k}={v}" for k, v in changed.items()],
        [f"env: {k}" for k in stale],
    )


def _without_key(value: Any, key: str) -> Any:
    return {k: v for k, v in value.items() if k != key} if isinstance(value, dict) else value


def _merge_compact(
    merged: dict[str, Any], root: Path | None
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Wire the compaction plugin (`root` given) or unwire it (None). Never removes the
    function-hooks variable: other plugins may rely on it."""
    markets = merged.get("extraKnownMarketplaces", {})
    enabled = merged.get("enabledPlugins", {})
    if not isinstance(markets, dict) or not isinstance(enabled, dict):
        return merged, [], []  # someone put something else there; do not fight it
    if root is None:
        gone = [k for k, d in ((MARKETPLACE, markets), (PLUGIN_KEY, enabled)) if k in d]
        if not gone:
            return merged, [], []
        out = {
            **merged,
            "extraKnownMarketplaces": _without_key(markets, MARKETPLACE),
            "enabledPlugins": _without_key(enabled, PLUGIN_KEY),
        }
        return out, [], [f"plugin: {k}" for k in gone]
    source = {"source": {"source": "directory", "path": str(root)}}
    env = merged.get("env", {}) if isinstance(merged.get("env", {}), dict) else {}
    added = []
    if markets.get(MARKETPLACE) != source:
        added.append(f"marketplace: {MARKETPLACE} -> {root}")
    if enabled.get(PLUGIN_KEY) is not True:
        added.append(f"plugin: {PLUGIN_KEY}")
    if env.get(FUNCTION_HOOKS) != "1":
        added.append(f"env: {FUNCTION_HOOKS}=1")
    if not added:
        return merged, [], []
    out = {
        **merged,
        "extraKnownMarketplaces": {**markets, MARKETPLACE: source},
        "enabledPlugins": {**enabled, PLUGIN_KEY: True},
    }
    if isinstance(merged.get("env", {}), dict):
        out["env"] = {**env, FUNCTION_HOOKS: "1"}
    return out, added, []


def default_plugin_root() -> Path:
    return _env.home_dir() / "claude-plugin"


def plugin_files() -> dict[str, str]:
    """The plugin, file by file: manifest, one-plugin marketplace, hooks list and module."""
    from importlib import resources

    from .. import __version__

    module = (resources.files("sanchopanza.harness") / HOOK_MODULE).read_text(encoding="utf-8")
    about = "Prunes old tool results at /compact instead of summarising (sanchopanza)."

    def dump(value: Any) -> str:
        return json.dumps(value, indent=2) + "\n"

    return {
        ".claude-plugin/plugin.json": dump(
            {
                "name": PLUGIN,
                "version": __version__,
                "description": about,
                "author": {"name": "sanchopanza"},
                "license": "Apache-2.0",
            }
        ),
        ".claude-plugin/marketplace.json": dump(
            {
                "name": MARKETPLACE,
                "owner": {"name": "sanchopanza"},
                "description": "The local sanchopanza compaction plugin.",
                "plugins": [{"name": PLUGIN, "source": "./", "description": about}],
            }
        ),
        "hooks/hooks.json": dump({"modules": [f"./{HOOK_MODULE}"]}),
        f"hooks/{HOOK_MODULE}": module,
    }


def plugin_changes(root: Path) -> list[str]:
    """The plugin files that are missing or differ under `root`."""
    return [
        name
        for name, text in plugin_files().items()
        if not (root / name).exists() or (root / name).read_text(encoding="utf-8") != text
    ]


def write_plugin(root: Path) -> list[str]:
    """Write the files that changed, atomically each. Running it twice writes nothing."""
    files = plugin_files()
    written = plugin_changes(root)
    for name in written:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, files[name].encode("utf-8"))
    return written


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
    current: Any,
    config: HarnessConfig,
    *,
    command: str,
    provider: str,
    compact_root: Path | None = None,
    autopilot: bool = False,
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
        new_hooks, plus, minus = _merge_hooks(hooks, config, command, autopilot)
        if plus or minus:
            merged = {**merged, "hooks": new_hooks}
        added, removed = [*added, *plus], [*removed, *minus]
    env = merged.get("env", {})
    if isinstance(env, dict):
        new_env, plus, minus = _merge_env(env, config, provider, autopilot)
        if plus or minus:
            merged = {**merged, "env": new_env}
        added, removed = [*added, *plus], [*removed, *minus]
    merged, plus, minus = _merge_compact(merged, compact_root)
    return merged, [*added, *plus], [*removed, *minus]


def default_path(scope: str = "user", root: Path | None = None) -> Path:
    """Where Claude Code keeps settings for that scope."""
    if scope == "project":
        return (root or Path.cwd()) / ".claude" / "settings.json"
    if scope == "local":
        return (root or Path.cwd()) / ".claude" / "settings.local.json"
    return Path.home() / ".claude" / "settings.json"


def plan(
    path: Path,
    config: HarnessConfig,
    *,
    command: str = COMMAND,
    provider: str = "",
    compact_root: Path | None = None,
    autopilot: bool = False,
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
    if autopilot and compact_root is None:
        raise ValueError("the autopilot needs the compaction plugin: pass its root")
    command = portable_command(command)
    merged, added, removed = _merge(
        current,
        config,
        command=command,
        provider=provider,
        compact_root=compact_root,
        autopilot=autopilot,
    )
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

    The first backup (`<file>.bak`) is the file as it was before sanchopanza ever wrote to it and
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
