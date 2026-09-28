"""The screen's confirmation harness reproduces the published run, and draws fresh questions.

Needs the local HotpotQA export in SANCHOPANZA_HOTPOT (not redistributed), or skips. Free: the
published arms replay from recordings, the fresh draw is only built, never asked.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from .helpers import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOTPOT = dataset("HOTPOT")
needs_hotpot = pytest.mark.skipif(
    not HOTPOT or not pathlib.Path(HOTPOT).exists(), reason="SANCHOPANZA_HOTPOT not set"
)
SCRIPT = ROOT / "benchmarks" / "lateral" / "screen" / "confirm.py"


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}


@needs_hotpot
def test_the_harness_reproduces_the_published_screen():
    argv = [sys.executable, str(SCRIPT), "--replay-published", "--hotpot", HOTPOT]
    done = subprocess.run(argv, capture_output=True, text=True, env=_clean_env(), cwd=ROOT)
    assert done.returncode == 0, done.stderr[-2000:]
    report = json.loads(done.stdout)
    assert report["arms"]["SCREEN"]["page_joint"] == 0.96
    assert report["arms"]["TOUR"]["page_joint"] == 0.965
    assert report["verdict"] == "confirmed"


@needs_hotpot
def test_the_fresh_questions_were_never_drawn_before():
    code = (
        "import importlib.util, pathlib, sys\n"
        f"spec = importlib.util.spec_from_file_location('c', r'{SCRIPT}')\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['c'] = m\n"
        "spec.loader.exec_module(m)\n"
        f"h = pathlib.Path(r'{HOTPOT}')\n"
        "fresh = {r['id'] for r in m.fresh(h)}\n"
        "old = {r['id'] for r in m.hier.build(h)} | m.hier.used_ids(h)\n"
        "assert len(fresh) == m.N and not fresh & old\n"
        "print('ok')\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=_clean_env(), cwd=ROOT
    )
    assert done.returncode == 0 and "ok" in done.stdout, done.stderr[-2000:]


def test_live_is_refused_without_a_registered_prereg():
    registered = ROOT / "docs" / "results" / "2026-09-28-lateral-screen-confirm" / "prereg.sha256"
    if registered.exists():
        pytest.skip("the prereg is registered; the refusal is covered by require_prereg")
    argv = [sys.executable, str(SCRIPT), "--live", "--hotpot", HOTPOT or "none"]
    done = subprocess.run(argv, capture_output=True, text=True, env=_clean_env(), cwd=ROOT)
    assert done.returncode != 0


@needs_hotpot
def test_the_live_confirmation_replays_as_published():
    argv = [sys.executable, str(SCRIPT), "--replay-live", "--hotpot", HOTPOT]
    done = subprocess.run(argv, capture_output=True, text=True, env=_clean_env(), cwd=ROOT)
    assert done.returncode == 0, done.stderr[-2000:]
    report = json.loads(done.stdout)
    published = ROOT / "docs" / "results" / "2026-09-28-lateral-screen-confirm" / "analysis.json"
    assert report == json.loads(published.read_text(encoding="utf-8"))
    assert report["verdict"] == "not confirmed" and report["S1"] and not report["S2"]
