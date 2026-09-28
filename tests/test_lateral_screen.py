"""A BM25 screen and one in-context call against the five-call tournament, replayed. No network.

Pins `docs/results/2026-09-28-lateral-screen/README.md`. Needs the local HotpotQA export in
SANCHOPANZA_HOTPOT (and QASPER in SANCHOPANZA_QASPER for the boundary), or skips.
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
RESULTS = ROOT / "docs" / "results" / "2026-09-28-lateral-screen"
HOTPOT = dataset("HOTPOT")
QASPER = dataset("QASPER")


def test_the_pre_registration_is_the_hashed_one():
    raw = (RESULTS / "prereg.md").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == (RESULTS / "prereg.sha256").read_text().strip()


def test_the_recording_is_one_call_per_held_out_question_within_its_cap():
    lines = (ROOT / "fixtures" / "lateral-screen.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(x) for x in lines if x.strip()]
    assert len(entries) == 200
    assert {e["point"] for e in entries} == {"triage_pages"}
    assert {e["model"] for e in entries} == {"jev-1.13.0"}
    assert sum(e["cost_usd"] for e in entries) <= 0.12


@pytest.mark.skipif(
    not HOTPOT or not pathlib.Path(HOTPOT).exists(), reason="SANCHOPANZA_HOTPOT not set"
)
def test_the_screen_replays_as_published():
    argv = [sys.executable, str(ROOT / "benchmarks/lateral/screen/run.py"), "--hotpot", HOTPOT]
    if QASPER and pathlib.Path(QASPER).exists():
        argv += ["--qasper", QASPER]
    out = subprocess.run(argv, capture_output=True, text=True, cwd=ROOT, timeout=1200)
    assert out.returncode == 0, out.stderr
    assert "live 0, missing 0" in out.stderr
    report = json.loads(out.stdout)
    held = report["held_out"]
    assert (held["SCREEN"]["page_joint"], held["SCREEN"]["kept_share"]) == (0.96, 0.0343)
    assert (held["TOUR"]["page_joint"], held["TOUR"]["kept_share"]) == (0.965, 0.031)
    assert held["CEILING"]["page_joint"] == 0.99
    assert report["screen_minus_tour"]["ci95"] == [-0.03, 0.02]
    assert report["calls_per_question"] == {"SCREEN": 1, "TOUR": 5.0}
    assert (report["S1"], report["S2"], report["verdict"]) == (True, True, "confirmed")
    if "qasper_boundary" in report:
        boundary = report["qasper_boundary"]
        assert boundary["papers_over_one_call"] == 217
        assert boundary["screen_ceiling_all_evidence"] == 0.8203
        assert boundary["tournament_all_evidence"] == 0.9539
