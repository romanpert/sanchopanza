"""The long-document numbers, replayed from `fixtures/longdocs.jsonl`. No network.

Needs the local QASPER test export in SANCHOPANZA_QASPER (not redistributed), or skips. Pins
`docs/results/2026-09-27-longdocs/README.md`.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from .helpers import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
QASPER = dataset("QASPER")
pytestmark = pytest.mark.skipif(
    not QASPER or not pathlib.Path(QASPER).exists(), reason="SANCHOPANZA_QASPER not set"
)


def test_the_long_documents_replay_as_published():
    out = subprocess.run(
        [sys.executable, str(ROOT / "benchmarks/longdocs/run.py"), "--qasper", QASPER],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=1200,
    )
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    assert report["papers"] == 300
    many = report["MANY"]
    assert (many["all_evidence"], many["kept_share"]) == (0.9467, 0.4892)
    assert report["BM25_top22"]["all_evidence"] == 0.7833
    assert (report["P28"], report["P29"]) == (False, True)
    assert "live calls 0" in out.stderr
