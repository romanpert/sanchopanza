"""Wall time of `sanchopanza memory-hook` on a PostToolUse event, as Claude Code runs it: a new
process per event, over a store of LOAD_LIMIT records. Free.

    python benchmarks/memory_real/latency.py [--runs 10]
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

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
sys.path.insert(0, str(SRC))

from sanchopanza.context import episodes as ep  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = root / "store" / "proj"
        records = [ep.Episode(session=f"s{i // 10}", index=i % 10 + 1, request=f"request {i}",
                              report="done " * 200, changed=(f"src/m{i}.py",),
                              at=1_790_000_000.0 + i) for i in range(ep.LOAD_LIMIT)]  # fmt: skip
        ep.save(store, records, keep_days=10_000)
        env = {**os.environ, "PYTHONPATH": str(SRC),
               "SANCHOPANZA_MEMORY_STORE": str(root / "store"),
               "SANCHOPANZA_MEMORY_STORE_LOG": str(root / "log.jsonl")}  # fmt: skip
        for label, path in (("miss", "src/none.py"), ("hit", "src/m7.py")):
            times = []
            for run in range(args.runs):
                event = {"hook_event_name": "PostToolUse", "session_id": f"x{run}",
                         "transcript_path": str(root / "projects" / "proj" / "x.jsonl"),
                         "cwd": "", "tool_name": "Read", "tool_input": {"file_path": path}}
                began = time.perf_counter()
                done = subprocess.run([sys.executable, "-m", "sanchopanza", "memory-hook"],
                                      input=json.dumps(event).encode(), env=env,
                                      capture_output=True)  # fmt: skip
                times.append(time.perf_counter() - began)
                assert done.returncode == 0, done.stderr
            print(f"{label}: median {statistics.median(times):.3f} s, max {max(times):.3f} s, "
                  f"out {len(done.stdout)} bytes")  # fmt: skip
        began = time.perf_counter()
        subprocess.run([sys.executable, "-c", "pass"], env=env)
        print(f"bare python: {time.perf_counter() - began:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
