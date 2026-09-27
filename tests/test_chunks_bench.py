"""The chunk numbers, replayed from `fixtures/chunks*.jsonl`. No network.

Needs the local HotpotQA export in SANCHO_HOTPOT (not redistributed), or skips. Pins
`docs/results/2026-09-27-chunks/README.md`.
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


def test_the_confirmatory_run_replays_confirmed(tmp_path):
    out = subprocess.run(
        [sys.executable, str(ROOT / "benchmarks/chunks/confirm.py"), "--hotpot", HOTPOT],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=1200,
    )
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    assert report["live_calls"] == 0
    assert report["cuts_from_600"] == {"A": 0.28, "C": 0.4, "B": 0.31, "CB": 0.28}
    assert (report["C"]["page_joint"], report["C"]["kept_share"]) == (0.9833, 0.3362)
    assert (report["A"]["page_joint"], report["A"]["kept_share"]) == (0.9433, 0.5285)
    assert (report["CB"]["sentence_joint"], report["CB"]["kept_share"]) == (0.9033, 0.2234)
    assert report["verdict"] == "confirmed"
