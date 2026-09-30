"""Wall time of a v4 touch on a Read of a long file (the hook prints every line it is shown), a
new process per event as Claude Code runs it. Free.

    python benchmarks/memory_real/latency_v4.py [--runs 8] [--lines 2000]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

from sanchopanza.context import episodes as ep  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--lines", type=int, default=2000)
    args = parser.parse_args(argv)
    content = "\n".join(f"    value_{i} = compute_something(argument_{i}, other_{i})"
                        for i in range(args.lines))  # fmt: skip
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        records = [ep.Episode(session=f"s{i // 10}", index=i % 10 + 1, request=f"r{i}",
                              report="done " * 200, changed=("src/big.py",),
                              wrote=tuple(ep.line_print(f"value_{i * 5 + j} = compute_something("
                                                        f"argument_{i * 5 + j}, other_{i * 5 + j})")
                                          for j in range(5)),
                              at=1_790_000_000.0 + i) for i in range(ep.LOAD_LIMIT)]  # fmt: skip
        ep.save(root / "store" / "proj", records, keep_days=10_000)
        env = {**os.environ, "PYTHONPATH": str(SRC),
               "SANCHOPANZA_MEMORY_STORE": str(root / "store"),
               "SANCHOPANZA_MEMORY_STORE_LOG": str(root / "log.jsonl")}  # fmt: skip
        times = []
        for run in range(args.runs):
            event = {"hook_event_name": "PostToolUse", "session_id": f"x{run}",
                     "transcript_path": str(root / "projects" / "proj" / "x.jsonl"), "cwd": "",
                     "tool_name": "Read", "tool_input": {"file_path": "src/big.py"},
                     "tool_response": {"type": "text", "file": {"content": content}}}
            began = time.perf_counter()
            done = subprocess.run([sys.executable, "-m", "sanchopanza", "memory-hook"],
                                  input=json.dumps(event).encode(), env=env,
                                  capture_output=True)  # fmt: skip
            times.append(time.perf_counter() - began)
            assert done.returncode == 0, done.stderr
        print(f"Read of {args.lines} lines over {ep.LOAD_LIMIT} records of that file: median "
              f"{statistics.median(times):.3f} s, max {max(times):.3f} s, "
              f"out {len(done.stdout)} bytes")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
