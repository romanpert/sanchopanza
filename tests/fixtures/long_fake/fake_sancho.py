"""A stand-in for a frozen `sanchopanza.exe` that has the passages hook (the `lean` branch), for the
pilot-A dry runs: `install` writes the project settings the real install writes (captured from
`lean` edd37bb with `--passages --provider jev --scope project --write --no-guard --no-find
--no-skill --context-budget 0`), and `passages-hook --help` answers. Free: no hook ever runs here
(the stand-in `claude` writes the hook's journal events itself, `FAKE_PASSAGES`).

    python fake_sancho.py install --scope project --write --passages [--passages-fraction F] ...
    python fake_sancho.py passages-hook --help

FAKE_NO_PASSAGES=1: an older commit, whose CLI has no `passages-hook` (exit 2, as argparse).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE = "sanchopanza hook"
PASSAGES = "sanchopanza passages-hook"


def _entry(matcher: str, command: str, timeout: int = 0) -> dict:
    hook = {"type": "command", "command": command, **({"timeout": timeout} if timeout else {})}
    return {"matcher": matcher, "hooks": [hook]}


def _value(argv: list[str], name: str, default: str) -> str:
    return argv[argv.index(name) + 1] if name in argv else default


def install(argv: list[str]) -> int:
    post = [_entry("Agent|Task", BASE)]
    pre = [_entry("Agent|Bash|PowerShell|Task|WebSearch|bash|execute|run_command|shell", BASE)]
    env = {"SANCHOPANZA_GUARD_PROFILE": "coding"}
    if "--provider" in argv:
        env = {"SANCHOPANZA_PROVIDER": _value(argv, "--provider", ""), **env}
    if "--passages" in argv:
        post = [*post, _entry("Bash|PowerShell|Read", PASSAGES, 30)]
        pre = [*pre, _entry("Write|Edit|MultiEdit|NotebookEdit", PASSAGES, 10)]
        fraction = float(_value(argv, "--passages-fraction", "0.25"))
        env = {
            **env,
            "SANCHOPANZA_PASSAGES_FRACTION": f"{fraction:g}",
            "SANCHOPANZA_PASSAGES_TOKENS": _value(argv, "--passages-tokens", "2000"),
        }
    if _value(argv, "--context-budget", "160000") != "0":
        env = {**env, "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "193000"}
    guard = {} if "--no-guard" in argv else {
        "SessionStart": [_entry("compact", "sanchopanza guard-hook")]}  # fmt: skip
    settings = {
        "hooks": {
            "PreToolUse": pre,
            "PostToolUse": post,
            "Stop": [],
            "UserPromptSubmit": [],
            **guard,
        },
        "env": env,
    }
    folder = Path(".claude")
    folder.mkdir(exist_ok=True)
    (folder / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    if "--no-find" not in argv:
        servers = {"sanchopanza": {"command": "sanchopanza", "args": ["find-mcp"]}}
        Path(".mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    print("written (fake sanchopanza)")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["install"]:
        return install(argv[1:])
    if argv[:1] == ["passages-hook"]:
        if os.environ.get("FAKE_NO_PASSAGES") == "1":
            sys.stderr.write(
                "sanchopanza: error: argument command: invalid choice: 'passages-hook'\n"
            )
            return 2
        print("usage: sanchopanza passages-hook [-h]")
        return 0
    sys.stderr.write(f"fake sanchopanza: not {argv}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
