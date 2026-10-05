"""v6.3 candidates (benchmarks/memory_real/variants_v63.py): which shell writes are appends."""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from sanchopanza.context import shell

from .helpers import bench_module

ROOT = pathlib.Path(__file__).resolve().parents[1]
v = bench_module(ROOT / "benchmarks" / "memory_real", "variants_v63")


def test_home_paths_are_outside_the_repository(tmp_path: pathlib.Path) -> None:
    """Review of 2026-10-01 (H3): `~/.claude/...` was joined under the command's folder."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    v.cl.root_of.cache_clear()
    cwd = tmp_path.as_posix()
    assert v._inside_repo("src/a.py", cwd, cwd)
    for raw in ("~/.claude/context/errors.md", "$HOME/.claude/x.md", "%USERPROFILE%/n.md"):
        assert not v._inside_repo(raw, cwd, cwd), raw


@pytest.mark.parametrize(
    ("command", "path", "expected"),
    [
        ('echo "- x" >> ~/.claude/context/errors.md', "~/.claude/context/errors.md", True),
        ("printf 'a\\n' >>notes.md", "notes.md", True),
        ("echo x | tee -a log.txt", "log.txt", True),
        ("Add-Content -Path notes.md -Value 'x'", "notes.md", True),
        ("'x' | Out-File notes.md -Append", "notes.md", True),
        ("python - <<'E'\nopen('notes.md', 'a').write('x')\nE", "notes.md", True),
        ("cat notes.md && echo x >> notes.md", "notes.md", False),  # a read keeps the give
        ("echo x > notes.md", "notes.md", False),
        # the review's: an append elsewhere never makes an overwrite an append
        (
            "python - <<'E'\nopen('log.txt','a').write('x')\nopen('notes.md','w').write('y')\nE",
            "notes.md",
            False,
        ),
        ("'x' | Out-File log.txt -Append; 'y' | Out-File notes.md", "notes.md", False),
        ("echo x >> notes.md && cp a notes.md", "notes.md", False),
        ("echo x >> notes.md && perl -pi -e 's/a/b/' notes.md", "notes.md", False),
        ("echo x >> notes.md && echo y | tee notes.md", "notes.md", False),
        ("echo x >> notes.md && echo y >| notes.md", "notes.md", False),
        ("echo x >> notes.md.bak && cp a notes.md", "notes.md", False),
        ("echo x > notes.md && echo y >> notes.md", "notes.md", False),
        ("sed -i 's/a/b/' notes.md", "notes.md", False),
        ("python - <<'E'\nopen('a.py', 'w').write('x')\nE", "a.py", False),
        ("echo x | tee log.txt", "log.txt", False),
        ("cp a.md b.md", "b.md", False),
        ("echo x >> other.md", "notes.md", False),
    ],
    ids=[
        "append",
        "nospace",
        "tee-a",
        "add-content",
        "out-file",
        "py-a",
        "read-then-append",
        "overwrite",
        "py-mixed",
        "ps-mixed",
        "app-cp",
        "app-perl",
        "app-tee",
        "app-clobber",
        "bak",
        "both",
        "sed-i",
        "py-w",
        "tee",
        "cp",
        "absent",
    ],  # fmt: skip
)
def test_appended(command: str, path: str, expected: bool) -> None:
    assert v.appended(command, path) is expected


def test_every_append_case_is_a_write_the_parser_sees() -> None:
    """The filter only removes what `shell.written` gives: each append case is written."""
    for command, path in [('echo "- x" >> errors.md', "errors.md"),
                          ("echo x | tee -a log.txt", "log.txt"),
                          ("Add-Content -Path notes.md -Value 'x'", "notes.md")]:  # fmt: skip
        assert path in shell.written(command)
