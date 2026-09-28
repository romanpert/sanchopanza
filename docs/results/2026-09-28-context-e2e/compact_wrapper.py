"""The command the compaction hook runs in this experiment: `sanchopanza compact`, logged.

    SANCHOPANZA_COMPACT_COMMAND="<python> compact_wrapper.py <arm> <evidence-dir> [<keyfile>]"

The hook (`compact_hook.ts`) appends `--session <id> --out <file>` and pipes the conversation
on stdin. This passes all of that through to the installed `sanchopanza compact --stdin` with
the arm's `--arm`/`--provider`, and writes one line to `<evidence-dir>/wrapper.jsonl`: the
exit code (0 pruned, 3 below the minimum reduction, 2 failure), the report, the seconds. Exit
code, stdout and stderr are the command's own, so the hook sees exactly what it would see
without the wrapper.

For the Jev arms the TypeSafe key is read from `<keyfile>` and put in this process's child
environment only; the Claude Code session never carries it. Each compaction's Jev spend is
capped at `JEV_PER_COMPACTION` by the squire's own budget (`SANCHOPANZA_T_MAX_USD`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SANCHO = str(REPO / ".venv" / "Scripts" / "sanchopanza.exe")
JEV_PER_COMPACTION = 0.05
ARMS = {
    "R": ("rules", "null"),
    "S": ("sanchopanza", "jev"),
    "F": ("fastjev", "jev"),
    "M": ("mask", "null"),  # round 2: the autopilot's compaction, free, no decider
}


def command(arm: str, rest: list[str]) -> list[str]:
    name, provider = ARMS[arm]
    return [SANCHO, "compact", "--stdin", "--arm", name, "--provider", provider, *rest]


def child_env(arm: str, evidence: Path, keyfile: str | None) -> dict[str, str]:
    drop = ("ANTHROPIC_", "TYPESAFE_", "SANCHOPANZA_", "SANCHO_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    env = {
        **env,
        "SANCHOPANZA_JOURNAL": str(evidence / "journal.jsonl"),
        "SANCHOPANZA_T_MAX_USD": str(JEV_PER_COMPACTION),
    }
    if ARMS[arm][1] == "jev":
        if not keyfile or not Path(keyfile).exists():
            raise SystemExit("compact_wrapper: a Jev arm needs its key file")
        env = {**env, "TYPESAFE_API_KEY": Path(keyfile).read_text(encoding="utf-8").strip()}
    return env


def main(argv: list[str]) -> int:
    arm, evidence = argv[0], Path(argv[1])
    keyfile = argv[2] if len(argv) > 2 and not argv[2].startswith("--") else None
    rest = argv[3:] if keyfile else argv[2:]
    evidence.mkdir(parents=True, exist_ok=True)
    payload = sys.stdin.buffer.read()
    started = time.time()
    proc = subprocess.run(
        command(arm, rest),
        input=payload,
        capture_output=True,
        env=child_env(arm, evidence, keyfile),
    )
    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    try:
        report = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else None
    except json.JSONDecodeError:
        report = None
    line = {
        "arm": arm, "exit": proc.returncode, "seconds": round(time.time() - started, 2),
        "input_bytes": len(payload), "rest": rest, "report": report, "stderr": stderr[-800:],
    }  # fmt: skip
    with (evidence / "wrapper.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(line) + "\n")
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
