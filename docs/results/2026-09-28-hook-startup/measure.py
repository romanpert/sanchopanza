"""Wall time of the Claude Code hook process, before and after a change. Free.

    python measure.py <python> <runs> <src-before> <src-after>

Each src directory is put first on PYTHONPATH and `sanchopanza hook` (the installed command,
so the launcher is included) is run on three recorded-shape inputs, interleaved with the other
src and with a bare `python -c pass`, so drift on the machine hits every arm alike. Null
provider, no key, journal in the temp directory: nothing is called and nothing is paid.
Prints the median and minimum per arm and input.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

BASH_RESULT = {
    "interrupted": False,
    "isImage": False,
    "noOutputExpected": False,
    "stderr": "",
    "stdout": "a\nb",
}
INPUTS = {
    "pre-bash": {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "ls -la"}},
    "post-bash-ls": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                     "tool_input": {"command": "ls"}, "tool_response": BASH_RESULT},
    "stop-off": {"hook_event_name": "Stop", "stop_hook_active": False},
}  # fmt: skip


def run(command: list[str], env: dict[str, str], raw: str) -> float:
    started = time.perf_counter()
    subprocess.run(command, input=raw, text=True, env=env, capture_output=True)
    return time.perf_counter() - started


def main() -> None:
    python, runs, sources = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
    hook = shutil.which("sanchopanza", path=os.path.dirname(python)) or "sanchopanza"
    base = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
    base.update(
        SANCHO_PROVIDER="null",
        SANCHO_SCAN_CONTENT="1",
        SANCHO_JOURNAL=os.path.join(tempfile.gettempdir(), "sancho-hook-startup.jsonl"),
    )
    times: dict[tuple[str, str], list[float]] = {}
    for i in range(runs + 1):  # the first round warms the disk cache and is dropped
        t = run([python, "-c", "pass"], base, "")
        if i:
            times.setdefault(("python -c pass", ""), []).append(t)
        for label, src in (("before", sources[0]), ("after", sources[1])):
            env = {**base, "PYTHONPATH": src}
            for name, data in INPUTS.items():
                t = run([hook, "hook"], env, json.dumps(data))
                if i:
                    times.setdefault((label, name), []).append(t)
    for (label, name), ts in times.items():
        print(f"{label:15} {name:13} median {statistics.median(ts):.3f} s"
              f"  min {min(ts):.3f}  n={len(ts)}")  # fmt: skip


if __name__ == "__main__":
    main()
