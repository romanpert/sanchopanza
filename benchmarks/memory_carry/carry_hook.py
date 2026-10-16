"""The hook arms' launcher: sanchopanza's hooks with the run's own state and the TypeSafe key, which
the agent's shell never sees (as `benchmarks/adopt/hook_env.py` does).

    "command": "<python> carry_hook.py <run-dir> <keyfile> [rules-on|rules-off]"
    "command": "<python> carry_hook.py <run-dir> <keyfile> sub <subcommand> [args...]"

The first form is the M and V arms' memory hook (`sanchopanza.harness.memory_hook`). The second is
arm S (`carry_s.install`): every command `sanchopanza install` wrote (`sanchopanza hook`,
`guard-hook`, `memory-hook`, and the `find-mcp` server of `.mcp.json`) runs as
`python -m sanchopanza <subcommand>` from this checkout's `src` (never the venv's editable install
of another checkout), with each piece of state under the pair's folder. A hook gets its event on
stdin and gives its output back unchanged; a server keeps the client's stdio. One line per call
goes to `<run-dir>/hooks.jsonl` (subcommand, event, session, tool, exit, seconds, output size,
stderr tail), with no event text. The OAuth token Claude Code was started with is not passed on.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"
CAP_FILE = "jev-cap.json"  # beside the run's key: {"cap_usd": ...} (handoff.CAP_FILE)
LEDGER = "jev-ledger.jsonl"  # beside the run's key: the hooks' SpendLedger


def key_of(keyfile: Path) -> str:
    return keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""


def base_env(keyfile: Path) -> dict[str, str]:
    """This process's environment without any key but the TypeSafe one, read from `keyfile`."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ANTHROPIC_", "TYPESAFE_")) and k != TOKEN}  # fmt: skip
    key = key_of(keyfile)
    return {**env, "PYTHONPATH": str(SRC), **({"TYPESAFE_API_KEY": key} if key else {})}


def s_env(run: Path, keyfile: Path) -> dict[str, str]:
    """Arm S's hooks: the install's own settings, with every state folder in the pair's folder.
    The memory store and its log are where the M and V arms keep them, so `carry.seed`,
    `carry.given` and `sendbacks.py` read S as they read V."""
    return {**base_env(keyfile),
            "SANCHOPANZA_MEMORY_STORE": str(run / "store"),
            "SANCHOPANZA_MEMORY_STORE_LOG": str(run / "hook-log.jsonl"),
            "SANCHOPANZA_JOURNAL": str(run / "journal.jsonl"),
            "SANCHOPANZA_GUARD_DIR": str(run / "guard"),
            "SANCHOPANZA_FUNDS_DIR": str(run / "funds")}  # fmt: skip


def log_call(run: Path, row: dict[str, object]) -> None:
    with (run / "hooks.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(row) + "\n")


def command_of(keyfile: Path, name: str, rest: list[str]) -> list[str]:
    """`python -m sanchopanza <name> ...`; when the run wrote CAP_FILE beside its key (W17), the
    same command through `capped_sub.py`, so every decision the hook asks goes through
    `CappedDecider` on the run's own ledger (`jev-ledger.jsonl` beside the key)."""
    cap_file = keyfile.parent / CAP_FILE
    if not cap_file.is_file():
        return [sys.executable, "-m", "sanchopanza", name, *rest]
    cap = float(json.loads(cap_file.read_text(encoding="utf-8"))["cap_usd"])
    return [sys.executable, str(HERE / "capped_sub.py"), str(keyfile.parent / LEDGER), str(cap),
            name, *rest]  # fmt: skip


def sub(run: Path, keyfile: Path, name: str, rest: list[str]) -> int:
    env = s_env(run, keyfile)
    command = command_of(keyfile, name, rest)
    key = "TYPESAFE_API_KEY" in env
    if name.endswith("-mcp"):  # a server: the client's stdio, for as long as it runs
        log_call(run, {"sub": name, "event": "server start", "key": key})
        code = subprocess.run(command, env=env).returncode
        log_call(run, {"sub": name, "event": "server end", "key": key, "exit": code})
        return code
    payload = sys.stdin.buffer.read()
    try:
        event = json.loads(payload.decode("utf-8"))
    except ValueError:
        event = {}
    event = event if isinstance(event, dict) else {}
    started = time.time()
    done = subprocess.run(command, input=payload, capture_output=True, env=env)
    log_call(run, {"sub": name, "args": rest, "event": event.get("hook_event_name"),
                   "session": event.get("session_id"), "source": event.get("source"),
                   "tool": event.get("tool_name"), "exit": done.returncode,
                   "seconds": round(time.time() - started, 2), "out_chars": len(done.stdout),
                   "key": key,
                   **({"stderr": done.stderr.decode("utf-8", "replace")[-500:]}
                      if done.stderr else {})})  # fmt: skip
    sys.stdout.buffer.write(done.stdout)
    sys.stderr.buffer.write(done.stderr)
    return done.returncode


def v_env(run: Path, keyfile: Path, rules: str) -> dict[str, str]:
    """The M and V arms' memory hook. With the rules on, the Stop audit is on as well: every V
    run (v7 to v8.1) was measured with it, and it has been opt-in since 2026-10-14."""
    return {**base_env(keyfile), "SANCHOPANZA_MEMORY_STORE": str(run / "store"),
            "SANCHOPANZA_MEMORY_STORE_LOG": str(run / "hook-log.jsonl"),
            "SANCHOPANZA_MEMORY_RULES": rules,
            "SANCHOPANZA_MEMORY_RULES_AUDIT": "on" if rules == "on" else "off"}  # fmt: skip


def memory(run: Path, keyfile: Path, rules: str) -> int:
    env = v_env(run, keyfile, rules)
    done = subprocess.run([sys.executable, "-m", "sanchopanza.harness.memory_hook"],
                          input=sys.stdin.buffer.read(), capture_output=True, env=env)  # fmt: skip
    sys.stdout.buffer.write(done.stdout)
    sys.stderr.buffer.write(done.stderr)
    return done.returncode


def main(argv: list[str]) -> int:
    run, keyfile = Path(argv[0]), Path(argv[1])
    if len(argv) > 3 and argv[2] == "sub":
        return sub(run, keyfile, argv[3], argv[4:])
    rules = "off" if len(argv) > 2 and argv[2] == "rules-off" else "on"
    return memory(run, keyfile, rules)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
