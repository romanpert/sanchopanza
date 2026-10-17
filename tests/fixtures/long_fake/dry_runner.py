"""`long_run.py` for dry runs of the launchers: the runner itself, with Docker stood in for (the
working copy is a local git repository, Docker's health and labels answer at once, pytest in the
grade passes the odd-numbered bugs' tests) and no memory-file check above the run root. Every
other step is the runner's own: clean user, caps, rows, stop files, resume, windows. Free: the
`claude` it starts is `fake_claude.py`, and the S arm's key is a fake.

    python dry_runner.py <long_run.py arguments>
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADOPT = HERE.parents[2] / "benchmarks" / "adopt"
sys.path.insert(0, str(ADOPT))

import long_run  # noqa: E402


def export(tag: str, dest: Path) -> str:
    dest.mkdir(parents=True)
    (dest / "pkg.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    git = ["git", "-C", str(dest), "-c", "user.name=t", "-c", "user.email=t@t"]
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "start"]):
        subprocess.run([*git, *step], check=True, capture_output=True)
    return subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()  # fmt: skip


def pytest(tag: str, patch: str, nodes: list[str], **_kw: object) -> dict[str, str]:
    """Odd bugs pass, even ones fail: a grade with something on both sides."""
    out = {}
    for node in nodes:
        found = re.search(r"t(\d+)$", node)
        out[node] = "PASSED" if found and int(found.group(1)) % 2 else "FAILED"
    return out


def main(argv: list[str]) -> int:
    long_run.docker_env.export = export
    long_run.docker_env.health = lambda: ""
    long_run.docker_env.remove_labelled = lambda _v: []
    long_run.docker_env.pytest = pytest
    long_run.carry.ancestors_memory = lambda _p: []
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path(".")
    long_run.run.KEYS = root / "keys"
    if not os.environ.get("ADOPT_SEAL_REPO"):  # a dry run checks the seal only against a sealed
        long_run.seal_refusal = lambda *_a, **_k: ""  # scratch repository (guard lot)
    if probe := os.environ.get("FAKE_DECIDER_PROBE"):  # a stand-in sanchopanza has no Python
        long_run.run.decider_probe = lambda _key: probe
    return long_run.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
