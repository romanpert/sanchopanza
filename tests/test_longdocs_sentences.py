"""Sentences inside the kept paragraphs on QASPER, replayed. No network.

Needs the local QASPER test export in SANCHOPANZA_QASPER (not redistributed), or skips. Pins
`docs/results/2026-09-27-longdocs/README.md`, section "Sentences inside the kept paragraphs".
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

from .helpers import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results" / "2026-09-27-longdocs"
QASPER = dataset("QASPER")


def test_the_pre_registration_is_the_hashed_one():
    raw = (RESULTS / "prereg-sentences.md").read_bytes().replace(b"\r\n", b"\n")
    registered = (RESULTS / "prereg-sentences.sha256").read_text().strip()
    assert hashlib.sha256(raw).hexdigest() == registered


@pytest.mark.skipif(
    not QASPER or not pathlib.Path(QASPER).exists(), reason="SANCHOPANZA_QASPER not set"
)
def test_the_sentence_stage_replays_as_published():
    out = subprocess.run(
        [sys.executable, str(ROOT / "benchmarks/longdocs/sentences.py"), "--qasper", QASPER],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=1200,
    )
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    assert (report["questions"], len(report["excluded"])) == (261, 39)
    assert report["select_sentences_calls"] == 5308
    assert (report["M"]["all_gold"], report["M"]["kept_share"]) == (0.9579, 0.4908)
    assert (report["MS"]["all_gold"], report["MS"]["kept_share"]) == (0.8314, 0.3148)
    assert report["BM25_sentences"]["all_gold"] == 0.5211
    assert (report["P30"], report["P31"]) == (False, True)
    assert "sentences live 0, missing 0" in out.stderr
