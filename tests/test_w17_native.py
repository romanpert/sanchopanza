"""W17's draft runner and F2 replay (benchmarks/w17_native). No test here calls a paid provider
or Claude Code."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "w17_native"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"w17_{name}", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


run = _load("run")
replay = _load("replay_f2")


def test_the_plan_runs_every_arm_of_every_triple_in_rotated_order() -> None:
    plan = run.build_plan("w17-sonnet")
    assert len(plan) == 12 * 4 * 3
    triples = [plan[i : i + 3] for i in range(0, len(plan), 3)]
    assert all(sorted(a for _, _, a, _ in t) == ["N0", "S", "SN"] for t in triples)
    firsts = {t[0][2] for t in triples}
    assert firsts == {"N0", "S", "SN"}
    names = {run.folder_name("w17-sonnet", i, a) for i in range(48) for a in run.ARMS}
    assert len(names) == 144


def test_the_estimate_fits_under_the_cap_and_the_cap_under_the_worst_case() -> None:
    found = run.estimate("w17-sonnet")
    assert found["expected_usd"] + max(run.reserve_of(a) for a in run.ARMS) <= found["cap_usd"]
    assert found["cap_usd"] < found["worst_usd"]


def test_the_user_scope_install_differs_only_by_the_bridge(tmp_path: Path) -> None:
    for native in (False, True):
        work = tmp_path / str(native)
        config = work / "claude-config"
        config.mkdir(parents=True)
        got = run.install_user(work, config, work / "typesafe.key", native, run.carry.environment())
        assert got["native_env"] is native and got["memory_hooks"] == 5
        text = (config / "settings.json").read_text(encoding="utf-8")
        assert "carry_hook.py" in text and '"sanchopanza ' not in text


def test_only_a_dry_run_is_wired_before_the_seal() -> None:
    with pytest.raises(SystemExit):
        run.main(["--run", "w17-pilot"])


def test_the_replay_reads_what_s_gave_session_two() -> None:
    rows = [
        {"at": 1.0, "event": "SessionStart", "rules_chars": 900},
        {"at": 10.0, "event": "SessionStart", "rules_chars": 1000},
        {"at": 11.0, "event": "UserPromptSubmit", "shown": ["s1-001"], "chars": 2000},
        {"at": 12.0, "event": "PostToolUse", "shown": "['s1-002']", "chars": 300},
        {"at": 13.0, "event": "PostToolUse", "shown": [], "chars": 0},
    ]
    got = replay.injected(rows, 10.0)
    assert got == {"rules_chars": 1000, "prompt_chars": 2000, "prompt_keys": ["s1-001"],
                   "touch_chars": 300, "touch_keys": ["s1-002"]}  # fmt: skip
    assert replay.restated("The carrier rejects requests", "the carrier rejects requests")
    assert not replay.restated("The carrier rejects requests", json.dumps({"x": 1}))
