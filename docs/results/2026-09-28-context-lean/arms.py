"""The four arms as files and commands: environment, plugin, settings, MCP config, argv.

Nothing here calls a model. Every arm forks the same phase A; the arms differ only from
phase B on:

- N: Claude Code's native auto-compaction; no plugin, no hooks, no MCP.
- K: the function-hook plugin (`compact_hook.ts`, copied from `src/` into one plugin folder per
  run tree), whose command is the logging wrapper of the e2e run around
  `sanchopanza compact --stdin --arm mask --provider null --stub-style cleared`.
- L: the plugin as K with `--stub-style index`, plus the classic hooks and the archive MCP
  server that `sanchopanza install --autopilot --lean` writes; the hooks point at the e2e
  `hook_wrapper.py`, which logs every event. No decider, no key.
- A (prepared, not in the main plan): the current autopilot with Jev, as `run_round2.py` ran it.

Every arm's session gets CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000 and
CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80 (threshold 64,000 tokens), and no ANTHROPIC_*, TYPESAFE_*,
SANCHOPANZA_* or SANCHO_* variable from this process.
"""

# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# `sanchopanza install` as it was when this ran: the defaults grew on 2026-09-30 (guard,
# context budget, find_in_repo, skill), so a rerun opts out of them to measure the same arms.
PRE_0930 = ["--no-guard", "--no-find", "--no-skill", "--context-budget", "0",
            "--guard-profile", "sandbox"]

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
E2E = HERE.parent / "2026-09-28-context-e2e"
ROOT = Path.home() / ".cache" / "sanchopanza" / "context-lean"
PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")
SANCHO = str(REPO / ".venv" / "Scripts" / "sanchopanza.exe")
COMPACT_WRAPPER = str(E2E / "compact_wrapper.py")
HOOK_WRAPPER = str(E2E / "hook_wrapper.py")
HOOK_TS = REPO / "src" / "sanchopanza" / "harness" / "compact_hook.ts"
TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep")
WINDOW = "100000"
# Amendment A1 (pilot, 2026-09-29): Haiku phase A ended at 37.9k and phase B peaked at
# 54-60k, so 64k never fired; Sonnet counts ~27 % more tokens (its phase A: 48.3k).
PCT = {"haiku": "63", "sonnet": "80"}  # 50,400 and 64,000 tokens of the 80k effective window
MASK_TURNS = 10
ARMS = ("N", "K", "L", "A")
STYLE = {"K": "cleared", "L": "index"}
MCP_NAME = "sanchopanza_archive"  # one name in every arm and phase: identical tool list
# CLAUDE_* too: launched from inside Claude Code, the parent leaks CLAUDE_EFFORT,
# CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING, its session id and messaging socket into every child.
DROP = ("ANTHROPIC_", "TYPESAFE_", "SANCHOPANZA_", "SANCHO_", "CLAUDE_", "CLAUDECODE")


@dataclass(frozen=True)
class Model:
    key: str
    id: str
    cap: float
    tasks: int
    arms: tuple[str, ...]
    prices: dict[str, float]  # USD per million tokens


MODELS = {
    "haiku": Model("haiku", "claude-haiku-4-5-20251001", 0.80, 8, ("N", "K", "L"),
                   {"in": 1.0, "out": 5.0, "cw5m": 1.25, "cw1h": 2.0, "cr": 0.10}),
    "sonnet": Model("sonnet", "claude-sonnet-5", 2.00, 3, ("N", "L"),
                    {"in": 2.0, "out": 10.0, "cw5m": 2.5, "cw1h": 4.0, "cr": 0.20}),
}  # fmt: skip


@dataclass(frozen=True)
class ArmConfig:
    arm: str
    env: dict[str, str]
    plugin: Path | None
    settings: Path | None
    mcp_config: Path | None
    extra_tools: tuple[str, ...]
    notes: dict[str, Any]


def tree(model: str) -> Path:
    return ROOT / model


def base_env(model: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(DROP)}
    return {**env, "CLAUDE_CODE_AUTO_COMPACT_WINDOW": WINDOW, "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": PCT[model]}


def _no_space(parts: list[str]) -> str:
    if any(" " in p for p in parts):
        raise SystemExit(f"a path has a space; the hook splits its command on whitespace: {parts}")
    return " ".join(parts)


def compact_command(arm: str, ev: Path) -> str:
    """What SANCHOPANZA_COMPACT_COMMAND holds; the plugin appends `--session <s> --out <f>`."""
    parts = [PYTHON, COMPACT_WRAPPER, "M", str(ev)]
    if arm in STYLE:
        parts += ["--stub-style", STYLE[arm], "--mask-turns", str(MASK_TURNS)]
    return _no_space(parts)


def hook_command(ev: Path, keyfile: Path) -> str:
    return _no_space([PYTHON, HOOK_WRAPPER, str(ev), str(keyfile)])


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_plugin(model: str) -> Path:
    """The per-tree plugin: the function-hook module from src/, unchanged."""
    root = tree(model) / "plugin"
    hooks = root / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    shutil.copy(HOOK_TS, hooks / "compact_hook.ts")
    (hooks / "hooks.json").write_text(json.dumps({"modules": ["./compact_hook.ts"]}), "utf-8")
    return root


def _function_hook_env(arm: str, ev: Path) -> dict[str, str]:
    return {
        "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1",
        "SANCHOPANZA_COMPACT_COMMAND": compact_command(arm, ev),
        "SANCHOPANZA_COMPACT_MARKER": str(ev / "marker.txt"),
    }


def _install(ev: Path, flags: list[str], hook: str) -> tuple[Path, dict[str, Any], str]:
    """Run `sanchopanza install ... --write` into the run's evidence folder."""
    path = ev / "settings.json"
    cmd = [SANCHO, "install", *PRE_0930, *flags, "--plugin-dir", str(ev / "install-plugin"),
           "--path", str(path), "--command-line", hook, "--write"]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ev,
                          env={k: v for k, v in os.environ.items() if not k.startswith(DROP)})  # fmt: skip
    if proc.returncode != 0:
        raise RuntimeError(f"install {' '.join(flags)} exited {proc.returncode}: {proc.stderr[-600:]}")
    return path, json.loads(path.read_text("utf-8")), proc.stdout


def _find_mcp(ev: Path, data: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The archive MCP server `install --lean` wrote: in the settings, or in a `.mcp.json`."""
    if isinstance(data.get("mcpServers"), dict) and data["mcpServers"]:
        return data["mcpServers"], "settings.json"
    for candidate in sorted(ev.rglob(".mcp.json")):
        servers = json.loads(candidate.read_text("utf-8")).get("mcpServers") or {}
        if servers:
            return servers, candidate.relative_to(ev).as_posix()
    raise RuntimeError("install --lean wrote no MCP server (neither in settings nor a .mcp.json)")


def mcp_for(ev: Path, servers: dict[str, Any], work: Path) -> tuple[Path, str, dict[str, Any]]:
    """The archive server as the session runs it: the entry `install` derived from our hook
    command names the wrapper, so the command is the venv's `sanchopanza archive-mcp` with the
    work copy's archive named explicitly (the same root the hooks and the compaction use)."""
    names = sorted(servers, key=lambda n: ("archive" not in n.lower(), n))
    path, tool = shared_mcp(ev, work)
    return path, tool, {"installed_entry": servers[names[0]], "installed_name": names[0]}


def shared_mcp(ev: Path, work: Path) -> tuple[Path, str]:
    """The archive server, under one fixed name, in EVERY arm and in phase A: the tool list is
    then byte-identical across arms and phases, so no arm pays a cache rewrite for it. In N and
    K the archive stays empty (K's `cleared` stubs archive nothing) and a search says so."""
    archive = str(work / ".sanchopanza" / "archive")
    entry = {"command": SANCHO, "args": ["archive-mcp", "--archive", archive]}
    path = ev / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {MCP_NAME: entry}}, indent=2) + "\n", "utf-8")
    return path, f"mcp__{MCP_NAME}__search_archive"


def lean_settings(ev: Path, work: Path) -> tuple[Path, Path, str, dict[str, Any]]:
    """Settings for L: what `install --autopilot --lean` writes, hooks pointed at the logging
    wrapper, marketplace keys stripped (the plugin comes by `--plugin-dir`), the compaction
    command and marker ours, and no between-turn trigger (`COMPACT_AT_PERCENT=0`: the plugin
    acts as in K, on Claude Code's own mid-turn auto-compaction)."""
    path, data, stdout = _install(ev, ["--autopilot", "--lean"], hook_command(ev, ev / "no-key"))
    servers, source = _find_mcp(ev, data)
    data = {k: v for k, v in data.items() if k not in ("extraKnownMarketplaces", "enabledPlugins", "mcpServers")}
    installed_env = dict(data.get("env", {}))
    data["env"] = {**installed_env, **_function_hook_env("L", ev), "SANCHOPANZA_COMPACT_AT_PERCENT": "0"}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    mcp_path, tool, mcp_notes = mcp_for(ev, servers, work)
    notes = {"installed_env": installed_env, "mcp_source": source, **mcp_notes,
             "install_stdout": stdout[-400:]}
    return path, mcp_path, tool, notes


def autopilot_settings(ev: Path, keyfile: Path) -> Path:
    """Arm A, as run_round2.settings_for wrote it (Jev provider), with this run's plugin."""
    path, data, _ = _install(ev, ["--autopilot", "--provider", "jev"], hook_command(ev, keyfile))
    data = {k: v for k, v in data.items() if k not in ("extraKnownMarketplaces", "enabledPlugins")}
    data["env"] = {**data.get("env", {}), "SANCHOPANZA_COMPACT_COMMAND": compact_command("A", ev),
                   "SANCHOPANZA_COMPACT_MARKER": str(ev / "marker.txt")}  # fmt: skip
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def config(arm: str, model: str, ev: Path, work: Path, keyfile: Path | None = None) -> ArmConfig:
    ev.mkdir(parents=True, exist_ok=True)
    env = base_env(model)
    plugin = tree(model) / "plugin"
    if arm in ("N", "phaseA"):
        mcp, tool = shared_mcp(ev, work)
        return ArmConfig(arm, env, None, None, mcp, (tool,), {})
    if arm == "K":
        mcp, tool = shared_mcp(ev, work)
        return ArmConfig(arm, {**env, **_function_hook_env("K", ev)}, plugin, None, mcp, (tool,),
                         {"plugin_sha256": sha256(plugin / "hooks" / "compact_hook.ts")})  # fmt: skip
    if arm == "L":
        settings, mcp, tool, notes = lean_settings(ev, work)
        return ArmConfig(arm, {**env, **_function_hook_env("L", ev)}, plugin, settings, mcp, (tool,),
                         {**notes, "plugin_sha256": sha256(plugin / "hooks" / "compact_hook.ts")})  # fmt: skip
    if arm == "A":
        settings = autopilot_settings(ev, keyfile or ev / "no-key")
        return ArmConfig(arm, {**env, "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"}, plugin, settings,
                         None, (), {})  # fmt: skip
    raise SystemExit(f"unknown arm {arm}")


def argv(prompt: str, model: Model, cfg: ArmConfig, resume: str | None = None) -> list[str]:
    cmd = ["claude", "-p", prompt, "--model", model.id, "--max-budget-usd", f"{model.cap:.2f}",
           "--output-format", "json", "--setting-sources", "project", "--strict-mcp-config",
           "--permission-mode", "dontAsk"]  # fmt: skip
    if resume:
        cmd += ["--resume", resume, "--fork-session"]
    if cfg.plugin is not None:
        cmd += ["--plugin-dir", str(cfg.plugin)]
    if cfg.settings is not None:
        cmd += ["--settings", str(cfg.settings)]
    if cfg.mcp_config is not None:
        cmd += ["--mcp-config", str(cfg.mcp_config)]
    return [*cmd, "--allowedTools", *TOOLS, *cfg.extra_tools]


def claude_version() -> str:
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"unknown ({error.__class__.__name__})"
