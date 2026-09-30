"""`runtests <pytest arguments>`: the agent's way to run the project's tests, in both arms alike.

The project's environment lives in a Docker image (ADOPT_TAG); the working copy is on the host.
This takes everything changed in the working copy since ADOPT_BASE, applies it inside a fresh
container of the image and runs `python -m pytest <arguments>` there, printing pytest's output
and exiting with its code.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from docker_env import agent_diff  # noqa: E402

TIMEOUT_S = 1200


def main(argv: list[str]) -> int:
    tag, base = os.environ.get("ADOPT_TAG", ""), os.environ.get("ADOPT_BASE", "")
    if not tag or not base:
        print("runtests: the test environment is not configured here", file=sys.stderr)
        return 2
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    root = Path(top.stdout.strip() or os.getcwd())
    patch = agent_diff(root, base)
    with tempfile.TemporaryDirectory() as io_dir:
        (Path(io_dir) / "work.patch").write_bytes(patch.encode("utf-8"))
        script = ("cd /testbed && (test ! -s /io/work.patch || git apply --whitespace=nowarn "
                  "/io/work.patch || { echo 'runtests: your changes did not apply'; exit 3; }) "
                  '&& python -m pytest -p no:cacheprovider "$@"')  # fmt: skip
        cmd = ["docker", "run", "--rm", "-v", f"{Path(io_dir).as_posix()}:/io:ro", tag,
               "bash", "-lc", script, "runtests", *argv]  # fmt: skip
        try:
            return subprocess.run(cmd, timeout=TIMEOUT_S).returncode
        except subprocess.TimeoutExpired:
            print(f"runtests: stopped after {TIMEOUT_S} s", file=sys.stderr)
            return 124


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
