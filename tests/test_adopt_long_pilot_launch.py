"""The pilot's launcher `long-pilot-a-run.cmd`, end to end through `cmd.exe` with the stand-in
`claude`, runner, sanchopanza and preflight; and `pilot_a_compare.py` on synthetic rows. Free: no
model, no API, no Jev, no Docker."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Any

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


# ---- the comparison ------------------------------------------------------------------------------


def _arm(root: pathlib.Path, chain: str, arm: str, calls: list[dict[str, Any]],
         resolved: int | None, **row: Any) -> None:  # fmt: skip
    folder = root / "runs" / f"{chain}-sonnet" / arm
    folder.mkdir(parents=True)
    body = {"chain": chain, "run": f"{chain}-sonnet", "arm": arm, "model": "claude-sonnet-5-5",
            "bugs": 60, "requests_planned": 62, "stopped": "", "calls": calls,
            "owner_usd": round(sum(c["owner_usd"] for c in calls), 6), **row}  # fmt: skip
    (folder / "row.json").write_text(json.dumps(body), encoding="utf-8")
    if resolved is not None:
        grade = {"resolved": resolved, "bugs_total": 60}
        (folder / "grade.json").write_text(json.dumps(grade), encoding="utf-8")


def _call(usd: float, requests: int, peak: int, compactions: int = 0) -> dict[str, Any]:
    return {"status": "ran", "owner_usd": usd, "requests": requests, "peak_context": peak,
            "compactions": [{"pre": 1}] * compactions}  # fmt: skip


def test_the_comparison_is_per_chain_descriptive_and_reads_both_roots(
    tmp_path: pathlib.Path,
) -> None:
    gate, pilot = tmp_path / "L", tmp_path / "L-pilot-a"
    _arm(gate, GATE[0], "N", [_call(10.0, 100, 300_000, 1), _call(14.0, 80, 420_000)], 30)
    _arm(gate, GATE[1], "N", [_call(20.0, 150, 500_000)], None)  # not graded yet
    passages = {"cuts": 40, "r": 0.3, "r_whole": 0.1, "chars_in": 400_000, "chars_out": 100_000}
    _arm(pilot, GATE[0], "A", [_call(9.0, 90, 200_000), _call(9.0, 70, 250_000)], 33,
         passages=passages)  # fmt: skip
    _arm(pilot, GATE[1], "A", [_call(5.0, 30, 90_000)], 0, stopped="rerequest",
         passages={**passages, "r_whole": 0.6})  # fmt: skip
    out = tmp_path / "compare.json"
    done = subprocess.run([sys.executable, str(ADOPT / "pilot_a_compare.py"), "--gate", str(gate),
                           "--pilot", str(pilot), "--pilot10", str(tmp_path / "none"),
                           "--json", str(out)], capture_output=True, text=True)  # fmt: skip
    assert done.returncode == 0, done.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "k=1" in data["declared"] and "no inferential" in data["declared"]
    conan = data["chains"][GATE[0]]
    assert conan["N"]["cost_usd"] == 24.0 and conan["N"]["resolved"] == 30
    assert conan["N"]["cost_per_resolved"] == pytest.approx(0.8) and conan["N"]["f2p"] == 0.5
    assert conan["N"]["requests"] == 180 and conan["N"]["peak_context"] == 420_000
    assert conan["N"]["compactions"] == 1 and conan["N"]["cuts"] is None
    assert conan["A"]["cost_usd"] == 18.0 and conan["A"]["f2p"] == pytest.approx(0.55)
    assert conan["A"]["cuts"] == 40 and conan["A"]["r"] == 0.3 and conan["A"]["r_whole"] == 0.1
    assert conan["A_vs_N"]["cost"] == pytest.approx(0.75)
    assert conan["A_vs_N"]["cost_per_resolved"] == pytest.approx((18 / 33) / 0.8, abs=1e-3)
    pyd = data["chains"][GATE[1]]
    assert pyd["N"]["resolved"] is None and pyd["N"]["cost_per_resolved"] is None
    assert pyd["A"]["stopped"] == "rerequest" and pyd["A"]["cost_per_resolved"] is None
    assert pyd["A_vs_N"]["cost_per_resolved"] is None and "A10" not in pyd
    assert "rerequest" in done.stdout and GATE[0] in done.stdout and "k=1" in done.stdout
