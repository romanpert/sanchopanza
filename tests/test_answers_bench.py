"""The answers numbers, replayed from the CLI session caches in `fixtures/cli/`. No network.

Needs the local HotpotQA export in SANCHO_HOTPOT (not redistributed), or skips. Pins
`docs/results/2026-09-27-answers/README.md`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOTPOT = os.environ.get("SANCHO_HOTPOT", "")
pytestmark = pytest.mark.skipif(
    not HOTPOT or not pathlib.Path(HOTPOT).exists(), reason="SANCHO_HOTPOT not set"
)


def _run(*extra: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(ROOT / "benchmarks/chunks/answers.py"), "--hotpot", HOTPOT, *extra],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=1200,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _acc(report: dict) -> tuple[float, ...]:
    return tuple(report["arms"][a]["accuracy"] for a in ("all", "C", "CB", "B", "path"))


def test_the_first_run_replays_negative():
    report = _run()
    assert _acc(report) == (0.81, 0.7667, 0.76, 0.76, 0.7467)
    assert (report["P21"], report["P22"], report["P24"]) == (False, False, False)


def test_the_length_controlled_run_replays_confirmed():
    report = _run("--short")
    assert _acc(report) == (0.7, 0.71, 0.7067, 0.69, 0.67)
    assert (report["P21"], report["P22"], report["P24"]) == (True, True, True)
    assert report["verdict"] == "the sentences answer as well as the pages"
