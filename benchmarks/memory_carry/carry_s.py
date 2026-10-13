"""Arm S of the carry runner: Claude Code with sanchopanza as a user installs it in a project.

`install` runs `sanchopanza install --scope project --memory --write` (`S_INSTALL`) in the scene's
repository before its start commit, from this checkout's `src`, exactly as a user would type it;
every flag but `--memory` is at its default on the commit the run is sealed at (the Guardian hook,
the compaction guard, the context budget, the coding guard profile, `find_in_repo` in `.mcp.json`
and the `sanchopanza-code` skill). Then, and only then, each command it wrote (`sanchopanza ...`)
is put behind `carry_hook.py ... sub`, which runs the same subcommand with the pair's own state
and the TypeSafe key; nothing else in the files changes. The files as written and as rewired are
kept under `<pair>/install/`.

The checks below make a pair NOT RUN and stop the run (`carry.run_plan`, "harness") when S did not
run as S: a session where the memory hook never answered a prompt, where the `sanchopanza` MCP
server was not connected, or a pair whose decisions all failed or that asked the decider nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
LAUNCHER = HERE / "carry_hook.py"
S_INSTALL = ("install", "--scope", "project", "--memory", "--write")
SERVER = "sanchopanza"  # install_defaults.FIND_SERVER
JEV_RESERVE = 0.05  # USD of Jev held per S session before a pair (at ~3e-5 a decision: ~1,600)
INSTALLED = (".claude/settings.json", ".claude/skills/sanchopanza-code/SKILL.md", ".mcp.json")


def prefix(run: Path, keyfile: Path) -> str:
    parts = (Path(sys.executable), LAUNCHER, run, keyfile)
    return " ".join(f'"{p.as_posix()}"' for p in parts) + " sub"


def rewired(command: str, run: Path, keyfile: Path) -> str:
    """`sanchopanza <sub> [args]` behind the launcher; any other command unchanged."""
    words = command.split(" ", 1)
    if words[0] != "sanchopanza" or len(words) < 2:
        return command
    return f"{prefix(run, keyfile)} {words[1]}"


def rewire_settings(settings: Mapping[str, Any], run: Path, keyfile: Path) -> dict[str, Any]:
    """The settings with every hook command rewired, as a new object."""
    hooks = {event: [{**entry, "hooks": [{**h, "command": rewired(h["command"], run, keyfile)}
                                         if "command" in h else dict(h)
                                         for h in entry.get("hooks", [])]}
                     for entry in entries]
             for event, entries in (settings.get("hooks") or {}).items()}  # fmt: skip
    return {**settings, "hooks": hooks}


def rewire_mcp(data: Mapping[str, Any], run: Path, keyfile: Path) -> dict[str, Any]:
    """`.mcp.json` with our server started through the launcher, as a new object."""
    servers = {}
    for name, server in (data.get("mcpServers") or {}).items():
        if server.get("command") == "sanchopanza":
            args = [LAUNCHER.as_posix(), run.as_posix(), keyfile.as_posix(), "sub",
                    *server.get("args", [])]  # fmt: skip
            server = {**server, "command": Path(sys.executable).as_posix(), "args": args}
        servers[name] = server
    return {**data, "mcpServers": servers}


def _keep(repo: Path, into: Path) -> None:
    for rel in INSTALLED:
        if (repo / rel).is_file():
            (into / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(repo / rel, into / rel)


def install(run: Path, repo: Path, keyfile: Path, env: Mapping[str, str]) -> None:
    """`sanchopanza install` in `repo` as a user runs it, then its commands rewired. `env` is the
    agent's environment (no key of any kind); this checkout's `src` goes first on PYTHONPATH."""
    done = subprocess.run([sys.executable, "-m", "sanchopanza", *S_INSTALL], cwd=repo,
                          env={**env, "PYTHONPATH": str(SRC)}, capture_output=True,
                          text=True, timeout=120, check=False)  # fmt: skip
    (run / "install.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
    missing = [rel for rel in INSTALLED if not (repo / rel).is_file()]
    if done.returncode or missing:
        raise RuntimeError(f"sanchopanza install failed ({done.returncode}, missing {missing}): "
                           f"{done.stderr[-400:]}")  # fmt: skip
    _keep(repo, run / "install" / "as-written")
    settings = repo / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8"))
    text = json.dumps(rewire_settings(data, run, keyfile), indent=2) + "\n"
    settings.write_text(text, encoding="utf-8", newline="\n")
    mcp = repo / ".mcp.json"
    data = json.loads(mcp.read_text(encoding="utf-8"))
    mcp.write_text(json.dumps(rewire_mcp(data, run, keyfile), indent=2) + "\n", encoding="utf-8",
                   newline="\n")  # fmt: skip
    _keep(repo, run / "install" / "rewired")


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        out += [row] if isinstance(row, dict) else []
    return out


def jev(run: Path) -> dict[str, Any]:
    """The pair's decisions from its journal: how many, how many failed, and their cost."""
    decisions = [r.get("data") or {} for r in _rows(run / "journal.jsonl")
                 if r.get("kind") == "decision"]  # fmt: skip
    failed = sum(1 for d in decisions if d.get("provider") in (None, "null") or d.get("error"))
    usd = sum(float(d.get("cost_usd") or 0.0) for d in decisions)
    return {"jev_decisions": len(decisions), "jev_failed": failed, "jev_usd": round(usd, 6)}


def hook_rows(run: Path) -> int:
    """How many calls the hooks have logged so far (sessions run one at a time)."""
    return len(_rows(run / "hooks.jsonl"))


def session_breaks(run: Path, result: Mapping[str, Any], since: int = 0) -> list[str]:
    """Why a finished S session did not run as S: among the hook calls logged after the first
    `since` (this session's), the memory hook never answered a prompt; or the find server was not
    connected at its start."""
    out = []
    prompts = [r for r in _rows(run / "hooks.jsonl")[since:]
               if r.get("sub") == "memory-hook" and r.get("event") == "UserPromptSubmit"
               and r.get("exit") == 0]  # fmt: skip
    if not prompts:
        out.append("the memory hook answered no prompt of this session")
    status = ((result.get("init") or {}).get("mcp") or {}).get(SERVER)
    if status != "connected":
        out.append(f"MCP server {SERVER}: {status}")
    return out


def pair_breaks(facts: Mapping[str, Any]) -> list[str]:
    """Why a finished S pair did not run as S: the decider was never asked, or always failed."""
    if not facts.get("jev_decisions"):
        return ["the decider was asked nothing in the whole pair"]
    if facts["jev_failed"] == facts["jev_decisions"]:
        return [f"all {facts['jev_decisions']} decisions failed or had no provider"]
    return []


def preflight(keyfile: Path, env: Mapping[str, str]) -> dict[str, Any]:
    """One real Jev decision (`sanchopanza jev-preflight`) with the run's key, before any S pair."""
    key = keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""
    done = subprocess.run([sys.executable, "-m", "sanchopanza", "jev-preflight", "--json"],
                          env={**env, "PYTHONPATH": str(SRC), "TYPESAFE_API_KEY": key},
                          capture_output=True, text=True, timeout=120, check=False)  # fmt: skip
    try:
        found = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        found = {"ok": False, "reason": "no answer", "detail": done.stderr[-300:]}
    return {**found, "exit": done.returncode}
