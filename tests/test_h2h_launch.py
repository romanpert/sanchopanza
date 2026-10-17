"""`benchmarks/h2h/launch.ps1` names no local path: its Python is -Py, else the `.venv` of the main
checkout found by git's common directory, and it stops with a message outside a checkout."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

LAUNCH = Path(__file__).resolve().parents[1] / "benchmarks" / "h2h" / "launch.ps1"


def test_the_launcher_names_no_local_path() -> None:
    text = LAUNCH.read_text(encoding="utf-8")
    assert "C:\\Users" not in text and "proyectos" not in text
    assert "[string]$Py = ''" in text and "$python = $Py" in text
    # the main checkout's .venv, and a stop when git finds no checkout
    assert "rev-parse --path-format=absolute --git-common-dir" in text
    assert 'if (-not $commonDir) { throw "not a git checkout: pass -Py" }' in text
    assert '"$python" benchmarks\\h2h\\$Runner' in text


def test_no_variable_overwrites_a_parameter() -> None:
    # PowerShell names are case-blind: `$py = ...` would rewrite -Py, `$runner = ...` -Runner
    text = LAUNCH.read_text(encoding="utf-8")
    for name in ("Py", "Runner", "Log", "PidFile", "Pin", "KeysEnv", "RunnerArgs"):
        assert not re.search(rf"(?im)^\s*\${name}\s*=", text), name


@pytest.mark.skipif(shutil.which("powershell") is None, reason="no Windows PowerShell")
def test_the_launcher_parses() -> None:
    script = (
        "$e = $null; $t = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{LAUNCH}', [ref]$t, "
        "[ref]$e); $e.Count"
    )
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=120, check=True)  # fmt: skip
    assert done.stdout.strip() == "0"
