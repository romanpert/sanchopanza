"""No tracked file names the owner's other projects: not in its path, not in its bytes.

The name is built here so that this file does not hold it either.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PRIVATE = ("inda" + "gis",)


def _tracked() -> list[str]:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True,
                         check=True).stdout  # fmt: skip
    return [p for p in out.decode("utf-8").split("\0") if p]


def test_no_tracked_path_or_file_holds_a_private_name() -> None:
    found = []
    for rel in _tracked():
        path = REPO / rel
        if not path.is_file():
            continue  # deleted in the work tree, not yet staged
        body = path.read_bytes().lower()
        for name in PRIVATE:
            if name in rel.lower() or name.encode() in body:
                found.append(rel)
    assert found == []
