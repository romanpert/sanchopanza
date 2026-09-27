"""The cascade confirmation on ATBench-Codex, pinned. No network.

`docs/results/2026-09-27-cascade-frontier/README.md` reports it. The registrations must be the
hashed ones, and the published reports must say what the README says. A replay from the CLI
cache needs the local ATBench-Codex `test.json` in SANCHO_CODEX (not redistributed), or skips.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "results" / "2026-09-27-cascade-frontier"
CODEX = os.environ.get("SANCHO_CODEX", "")


@pytest.mark.parametrize("name", ["prereg-confirm", "prereg-confirm-cli", "prereg-confirm-rest"])
def test_every_registration_is_the_hashed_one(name):
    raw = (OUT / f"{name}.md").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == (OUT / f"{name}.sha256").read_text().strip()


def _core(block):
    p = block["primary"]
    return (
        block["answered"],
        block["cancelled"],
        block["jev_acc"],
        p["cascade_acc"],
        p["opus_acc"],
        p["cost_ratio"],
        p["escalated"],
        block["verdict"],
    )


HELD = (239, 3, 0.7908, 0.8033, 0.7992, 0.3882, 91, "confirmed")
OTHER = (248, 10, 0.7742, 0.7782, 0.7581, 0.3829, 92, "confirmed")
ALL = (487, 13, 0.7823, 0.7906, 0.7782, 0.3854, 183, "confirmed")


def test_the_published_reports():
    held = json.loads((OUT / "confirm-cli-analysis.json").read_text(encoding="utf-8"))
    rest = json.loads((OUT / "confirm-rest-analysis.json").read_text(encoding="utf-8"))
    assert _core(held) == HELD
    assert _core(rest["other_half"]) == OTHER
    assert _core(rest["all_500"]) == ALL
    assert held["primary"]["tau"] == 0.45
    for block in (held, rest["other_half"], rest["all_500"]):
        assert block["C1"] and block["C2"] and block["C3"]


@pytest.mark.skipif(not CODEX or not pathlib.Path(CODEX).exists(), reason="SANCHO_CODEX not set")
def test_both_runs_replay_from_the_cache_without_spending():
    script = str(ROOT / "benchmarks/cascade/confirm_cli.py")
    for extra in (["--rest"], []):
        out = subprocess.run(
            [sys.executable, script, *extra, "--codex", CODEX],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=600,
        )
        assert out.returncode == 0, out.stderr
        assert "spawned 0, spent 0.00" in out.stderr
        report = json.loads(out.stdout)
        if extra:
            assert _core(report["other_half"]) == OTHER
            assert _core(report["all_500"]) == ALL
        else:
            assert _core(report) == HELD
