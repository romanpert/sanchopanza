"""A frozen install of sanchopanza for the confirmation: one commit, not editable, its own venv.

    python benchmarks/adopt/freeze.py <commit>     # builds it, prints the path to its executable

The development arms ran the package installed editable from the working tree, so an edit by any
session changed the S arms mid-batch (declared in the dev log). The held-out arms run this copy
instead: `ADOPT_SANCHO=<path printed>` makes `run.py` install and `hook_env.py` run hooks from it.
`stamp.json` beside it records the commit, the package version and the tree it was built from.
"""

from __future__ import annotations

import json
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROOT = Path.home() / ".cache" / "sanchopanza" / "adopt" / "frozen"


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          check=True).stdout.strip()  # fmt: skip


def freeze(commit: str) -> Path:
    full = git("rev-parse", "--verify", f"{commit}^{{commit}}")
    target = ROOT / full[:12]
    exe = target / "Scripts" / "sanchopanza.exe"
    if exe.exists():
        return exe
    source = target / "src-tree"
    source.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", full],
                             capture_output=True, check=True).stdout  # fmt: skip
    subprocess.run(["tar", "-x", "-C", str(source)], input=archive, check=True)
    venv.create(target, with_pip=True)
    python = target / "Scripts" / "python.exe"
    subprocess.run([str(python), "-m", "pip", "install", "-q", str(source)], check=True)
    ask = "import sanchopanza; print(sanchopanza.__version__)"
    version = subprocess.run([str(python), "-c", ask], capture_output=True, text=True,
                             check=True).stdout.strip()  # fmt: skip
    stamp = {"commit": full, "version": version, "tree": git("rev-parse", f"{full}^{{tree}}")}
    (target / "stamp.json").write_text(json.dumps(stamp, indent=1), encoding="utf-8")
    return exe


def main(argv: list[str]) -> int:
    print(freeze(argv[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
