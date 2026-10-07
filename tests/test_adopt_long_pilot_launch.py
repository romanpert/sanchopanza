"""The pilot's launcher `long-pilot-a-run.cmd`, end to end through `cmd.exe` with the stand-in
`claude`, runner, sanchopanza and preflight (the comparison: test_adopt_long_compare.py). Free: no
model, no API, no Jev, no Docker."""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

from tests.test_adopt_long_launch import dry_environment, launch

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
FAKE = ROOT / "tests" / "fixtures" / "long_fake"
GATE = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")
CMD = "long-pilot-a-run.cmd"

pytestmark = pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")


def pilot_environment(base: pathlib.Path, **extra: str) -> dict[str, str]:
    """`dry_environment` with the frozen copy replaced by a stand-in that has `passages-hook`."""
    env = dry_environment(base, GATE)
    exe = base / "frozen" / "Scripts" / "sanchopanza.cmd"
    exe.parent.mkdir(parents=True)
    exe.write_text(f'@"{sys.executable}" "{FAKE / "fake_sancho.py"}" %*\r\n', encoding="utf-8",
                   newline="")  # fmt: skip
    config = json.loads((base / "dry.json").read_text(encoding="utf-8"))
    (base / "dry.json").write_text(json.dumps({**config, "sancho": str(exe)}), encoding="utf-8")
    return {**env, "FAKE_DECIDER_PROBE": "JevDecider", **extra}


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_the_pilot_launcher_runs_arm_a_on_both_chains_and_reports_the_journal(
    tmp_path: pathlib.Path,
) -> None:
    env = pilot_environment(tmp_path, FAKE_PASSAGES=json.dumps({"cuts": 1, "targeted": 1}))
    code = launch(CMD, ["0000000", "A", "dry"], env)
    root = tmp_path / "L"
    assert code == 0, _text(root / "launch.log")
    log = _text(root / "launch.log")
    assert "4.50 USD per call" in log and "38.00 per chain and arm, arms A" in log
    assert "caps held 76.00 USD" in log and "ceiling 80.00 (hard, in code)" in log
    assert "A runs " in log and "sanchopanza.cmd" in log
    assert "exit 0 (ok)" in _text(root / "preflight.txt")
    assert "start" in _text(root / "launch.status") and "pilot-a A commit 0000000" in _text(
        root / "launch.status")  # fmt: skip
    report = json.loads(_text(root / "report.json"))
    for chain in GATE:
        line = report["arms"][f"{chain}/claude-sonnet-5-5/A"]
        assert line["passages"]["cuts"] > 0 and line["passages"]["r"] == 1.0
        assert line["stopped"] == "" and "give_ups" in line and "f2p_rate" in line
    assert "cuts" in _text(root / "grade.log")
    assert not list((root / "runs").glob("*/N"))  # the pilot runs A only


def test_the_pilot_launcher_refuses_a_copy_without_passages_hook(tmp_path: pathlib.Path) -> None:
    env = pilot_environment(tmp_path, FAKE_NO_PASSAGES="1")
    assert launch(CMD, ["0000000", "A", "dry"], env) == 1
    root = tmp_path / "L"
    assert "refused" in _text(root / "launch.log") and "passages-hook" in _text(root / "launch.log")
    assert not (root / "runs").exists() and not (root / "preflight.txt").exists()


def test_the_pilot_launcher_stops_on_the_preflight_before_any_call(tmp_path: pathlib.Path) -> None:
    env = pilot_environment(tmp_path, FAKE_PREFLIGHT_EXIT="13")
    assert launch(CMD, ["0000000", "A10", "dry"], env) == 13
    root = tmp_path / "L"
    assert "exit 13 (unreachable)" in _text(root / "preflight.txt")
    assert "arms A10" in _text(root / "launch.log") and not (root / "runs").exists()


@pytest.mark.parametrize("args", [[], ["0000000", "S"], ["0000000", "N"]])
def test_the_pilot_launcher_needs_a_commit_and_arm_a_or_a10(
    tmp_path: pathlib.Path, args: list[str]
) -> None:
    env = pilot_environment(tmp_path)
    assert launch(CMD, args, env) == 1


def test_the_pilot_launcher_is_lf_and_pins_claude_code_and_its_root() -> None:
    raw = (ROOT / CMD).read_bytes()
    assert b"\r\n" not in raw
    text = raw.decode("utf-8")
    assert r"claude-pin\2.1.287" in text and "DISABLE_AUTOUPDATER=1" in text
    assert r"C:\sp-runs\L-pilot-a" in text and r"C:\sp-runs\L-pilot-a10" in text
    assert "long_launch.py pilot-a --commit" in text
