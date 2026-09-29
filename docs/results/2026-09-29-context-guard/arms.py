"""The three arms as files and commands. Nothing here calls a model.

Every arm forks the same phase A (no hooks) and differs only from phase B on:

- N: Claude Code's native auto-compaction; no hooks.
- G: the same native compaction, plus the guard's three command hooks (`PreCompact`,
  `SessionStart` with matcher `compact`, `PostToolUse` on `Bash`), rule chooser, no decider.
- GJ: as G with the decider chooser (`jev-1.13.0` through the owner's key, read by the wrapper
  from a key file; the session never carries it).
- K (amendment A2): as G with the `keep` chooser (`context.keep`, prereg-prompt-recall.md
  amendment 5): the guard built at the SessionStart after the summary, the decider scoring
  blocks then lines with the requests in full and the native summary as notes, the rule's
  lines free, the rule on any failure. Same key handling as GJ.

Every session: CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000 and CLAUDE_AUTOCOMPACT_PCT_OVERRIDE per
model, and no ANTHROPIC_*, TYPESAFE_*, SANCHOPANZA_*, SANCHO_* or CLAUDE_* variable of this
process (the leak found in 2026-09-28-context-lean). No MCP server in any arm or phase, so the
tool list is the same everywhere.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = Path.home() / ".cache" / "sanchopanza" / "context-guard"
PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")
WRAPPER = str(HERE / "guard_wrapper.py")
TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep")
WINDOW = "100000"
PCT = {"haiku": "63", "sonnet": "80"}  # the lean run's amendment A1; re-derived in the pilot
ARMS = ("N", "G", "GJ", "K")
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
    "haiku": Model("haiku", "claude-haiku-4-5-20251001", 0.80, 10, ("N", "G", "GJ"),
                   {"in": 1.0, "out": 5.0, "cw5m": 1.25, "cw1h": 2.0, "cr": 0.10}),
    "sonnet": Model("sonnet", "claude-sonnet-5", 2.00, 3, ("N", "G"),
                    {"in": 2.0, "out": 10.0, "cw5m": 2.5, "cw1h": 4.0, "cr": 0.20}),
}  # fmt: skip


@dataclass(frozen=True)
class ArmConfig:
    arm: str
    env: dict[str, str]
    settings: Path | None
    notes: dict[str, Any]


def tree(model: str) -> Path:
    return ROOT / model


def base_env(model: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(DROP)}
    return {**env, "CLAUDE_CODE_AUTO_COMPACT_WINDOW": WINDOW, "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": PCT[model]}


def hook_command(ev: Path, chooser: str, keyfile: Path | None) -> str:
    parts = [PYTHON, WRAPPER, str(ev), chooser]
    if keyfile is not None:
        parts.append(str(keyfile))
    if any(" " in p for p in parts):
        raise SystemExit(f"a path has a space: {parts}")
    return " ".join(parts).replace("\\", "/")  # Claude Code runs hooks through a POSIX shell


def guard_settings(ev: Path, chooser: str, keyfile: Path | None) -> Path:
    command = hook_command(ev, chooser, keyfile)
    entry = [{"type": "command", "command": command, "timeout": 120}]
    data = {
        "hooks": {
            "PreCompact": [{"hooks": entry}],
            "SessionStart": [{"matcher": "compact", "hooks": entry}],
            "PostToolUse": [{"matcher": "Bash", "hooks": entry}],
        }
    }
    path = ev / "settings.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def config(arm: str, model: str, ev: Path, keyfile: Path | None = None) -> ArmConfig:
    ev.mkdir(parents=True, exist_ok=True)
    env = base_env(model)
    if arm in ("N", "phaseA"):
        return ArmConfig(arm, env, None, {})
    if arm == "G":
        return ArmConfig(arm, env, guard_settings(ev, "rule", None), {"chooser": "rule"})
    if arm in ("GJ", "K"):
        if keyfile is None:
            raise SystemExit(f"arm {arm} needs the key file")
        chooser = "decider" if arm == "GJ" else "keep"
        return ArmConfig(arm, env, guard_settings(ev, chooser, keyfile), {"chooser": chooser})
    raise SystemExit(f"unknown arm {arm}")


def argv(prompt: str, model: Model, cfg: ArmConfig, resume: str | None = None) -> list[str]:
    cmd = ["claude", "-p", prompt, "--model", model.id, "--max-budget-usd", f"{model.cap:.2f}",
           "--output-format", "json", "--setting-sources", "project", "--strict-mcp-config",
           "--permission-mode", "dontAsk"]  # fmt: skip
    if resume:
        cmd += ["--resume", resume, "--fork-session"]
    if cfg.settings is not None:
        cmd += ["--settings", str(cfg.settings)]
    return [*cmd, "--allowedTools", *TOOLS]


def claude_version() -> str:
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=60)
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"unknown ({error.__class__.__name__})"
