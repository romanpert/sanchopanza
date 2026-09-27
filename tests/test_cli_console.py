"""The command line must survive a console that cannot encode everything it prints.

Found on 2026-09-25 on Windows: `sanchopanza install` merges the user's own settings.json
into its dry-run output, that file carried a character outside cp1252, and the command died
with `UnicodeEncodeError` before printing the plan. A console's encoding is not ours to
choose; what we print must degrade instead of crash. And `python -m sanchopanza` must work,
because that is how a venv without the console script on PATH is driven.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

from sanchopanza import cli

ROOT = Path(__file__).resolve().parent.parent


def test_install_dry_run_survives_a_cp1252_console(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo ✅"}]}]}}),
        encoding="utf-8",
    )
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    code = cli.main(["install", "--path", str(settings)])
    stream.flush()
    printed = stream.buffer.getvalue().decode("cp1252")
    assert code == 0
    assert "Nothing written" in printed


def test_python_dash_m_runs_the_command_line():
    completed = subprocess.run(
        [sys.executable, "-m", "sanchopanza", "providers"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "null" in completed.stdout
