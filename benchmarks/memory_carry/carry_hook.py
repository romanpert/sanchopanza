"""The M arm's memory hook: `sanchopanza.harness.memory_hook` with the run's own store and the
TypeSafe key, which the agent's shell never sees (as `benchmarks/adopt/hook_env.py` does).

    "command": "<python> carry_hook.py <run-dir> <keyfile> [rules-on|rules-off]"
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def main(argv: list[str]) -> int:
    run, keyfile = Path(argv[0]), Path(argv[1])
    rules = "off" if len(argv) > 2 and argv[2] == "rules-off" else "on"
    key = keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "TYPESAFE_"))}
    env = {**env, "PYTHONPATH": str(SRC), "SANCHOPANZA_MEMORY_STORE": str(run / "store"),
           "SANCHOPANZA_MEMORY_STORE_LOG": str(run / "hook-log.jsonl"),
           "SANCHOPANZA_MEMORY_RULES": rules,
           **({"TYPESAFE_API_KEY": key} if key else {})}  # fmt: skip
    done = subprocess.run([sys.executable, "-m", "sanchopanza.harness.memory_hook"],
                          input=sys.stdin.buffer.read(), capture_output=True, env=env)  # fmt: skip
    sys.stdout.buffer.write(done.stdout)
    sys.stderr.buffer.write(done.stderr)
    return done.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
