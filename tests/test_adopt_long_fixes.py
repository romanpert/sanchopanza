"""The eight problems the long-session pre-mortem found in the existing runner (a-h), one test
each, every one written to fail before its fix. No Docker, no network, no `claude`."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
sys.path.append(str(ADOPT))


def _load(name: str, file: pathlib.Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("adopt_run_fixes", ADOPT / "run.py")
docker_env = run.docker_env
hook_env = _load("adopt_hook_env_fixes", ADOPT / "hook_env.py")
meter = _load("bench_meter_fixes", ROOT / "benchmarks" / "meter.py")


def _stream(session: str, cost: float) -> bytes:
    events = [{"type": "system", "subtype": "init", "session_id": session},
              {"type": "result", "subtype": "success", "session_id": session,
               "total_cost_usd": cost, "num_turns": 1, "usage": {}}]  # fmt: skip
    return "".join(json.dumps(e) + "\n" for e in events).encode()


def _isolate(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    monkeypatch.setattr(run.docker_env, "export", lambda tag, work: "base")
    monkeypatch.setattr(run.docker_env, "agent_diff", lambda work, base: "")
    monkeypatch.setattr(run, "reserve", lambda *_a: True)
    monkeypatch.setattr(run, "settle", lambda *_a: None)
    monkeypatch.setattr(run, "claude_version", lambda: "x")


# ---- a: the grade's primary unit is the bug's own FAIL_TO_PASS --------------------------------


def test_a_one_regression_shared_by_every_bug_does_not_unresolve_them_all(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # B2's Sm: one wrong exception class broke a test in every bug's PASS_TO_PASS*: 0/40 strict.
    bugs = [{"instance_id": f"b{i}", "FAIL_TO_PASS": [f"t{i}"], "PASS_TO_PASS_STAR": ["docs"]}
            for i in range(3)]  # fmt: skip
    outcome = {"t0": "PASSED", "t1": "PASSED", "t2": "FAILED", "docs": "FAILED"}
    grade = _grade(tmp_path, monkeypatch, bugs, outcome)
    assert grade["resolved_f2p"] == 2 and grade["resolved_strict"] == 0
    assert grade["primary"] == "resolved_f2p"
    assert [b["p2p_broken"] for b in grade["bugs"]] == [1, 1, 1]
    assert grade["regressions"] == ["docs"]  # the guard, counted once per test


def _grade(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, bugs: list[dict[str, Any]],
           outcome: dict[str, str]) -> dict[str, Any]:  # fmt: skip
    monkeypatch.setattr(run, "RUNS", tmp_path)
    (tmp_path / "c" / "N").mkdir(parents=True)
    (tmp_path / "c" / "N" / "final.patch").write_text("", encoding="utf-8")
    monkeypatch.setattr(run.docker_env, "pytest", lambda *_a, **_k: outcome)
    return run.grade_chain({"chain": "c", "split": "dev", "tag": "t", "bugs": bugs}, "N")


# ---- b: a git failure while taking the agent's diff is an error, not an empty diff ------------


def test_b_agent_diff_retries_git_and_raises_instead_of_returning_nothing(monkeypatch) -> None:  # noqa: ANN001
    calls: list[list[str]] = []

    def denied(cmd, **_k):  # noqa: ANN001, ANN003, ANN202
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 128, b"", b"error: open(x): Permission denied")

    monkeypatch.setattr(docker_env.subprocess, "run", denied)
    monkeypatch.setattr(docker_env.time, "sleep", lambda _s: None)
    with pytest.raises(RuntimeError, match="Permission denied"):
        docker_env.agent_diff(pathlib.Path("w"), "base")
    assert len(calls) >= 2  # tried again before giving up


def test_b_agent_diff_keeps_crlf_bytes_as_git_wrote_them(monkeypatch) -> None:  # noqa: ANN001
    body = b"diff --git a/x b/x\n+line\r\n"

    def ok(cmd, **_k):  # noqa: ANN001, ANN003, ANN202
        return subprocess.CompletedProcess(cmd, 0, body if "diff" in cmd else b"", b"")

    monkeypatch.setattr(docker_env.subprocess, "run", ok)
    assert docker_env.agent_diff(pathlib.Path("w"), "base") == body.decode()


# ---- c: the arm's row is written after every call, not only at the chain's end ----------------


def test_c_a_runner_crash_after_the_first_call_keeps_that_call_in_row_json(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(tmp_path, monkeypatch)
    count = {"n": 0}

    def fake(cmd, **kw):  # noqa: ANN001, ANN003, ANN202
        count["n"] += 1
        if count["n"] == 2:
            raise RuntimeError("the runner died here")
        kw["stdout"].write(_stream("s1", 0.25))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run.subprocess, "run", fake)
    bugs = [{"instance_id": f"r.b{k}", "problem_statement": "p"} for k in range(3)]
    with pytest.raises(RuntimeError, match="died"):
        run.one_chain({"chain": "c", "split": "dev", "tag": "t", "bugs": bugs}, "N", "m", 9.0,
                      tmp_path / "key")  # fmt: skip
    row = json.loads((tmp_path / "runs" / "c" / "N" / "row.json").read_text(encoding="utf-8"))
    assert [c["request"] for c in row["calls"]] == [1] and row["partial"] is True


# ---- d: transcripts are read from the configuration the session used ---------------------------


def test_d_transcripts_come_from_claude_config_dir_when_the_session_used_one(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(tmp_path, monkeypatch)
    config = tmp_path / "cfg"
    saved = config / "projects" / "C--w-c-N" / "s1.jsonl"
    saved.parent.mkdir(parents=True)
    saved.write_text('{"type": "user"}\n', encoding="utf-8")
    monkeypatch.setattr(run, "child_env", lambda *_a: {"CLAUDE_CONFIG_DIR": str(config)})

    def fake(cmd, **kw):  # noqa: ANN001, ANN003, ANN202
        kw["stdout"].write(_stream("s1", 0.1))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run.subprocess, "run", fake)
    bugs = [{"instance_id": "r.b0", "problem_statement": "p"}]
    run.one_chain({"chain": "c", "split": "dev", "tag": "t", "bugs": bugs}, "N", "m", 9.0,
                  tmp_path / "key")  # fmt: skip
    assert (tmp_path / "runs" / "c" / "N" / "transcript.jsonl").exists()


# ---- e: the gate's chain caps fit its ceiling, checked before anything runs --------------------


def test_e_the_gate_caps_fit_the_ceiling_and_the_old_opus_cap_is_refused_at_plan_time() -> None:
    guard = _load("adopt_long_guard_fixes", ADOPT / "long_guard.py")
    blocks = [("c1", "sonnet", 38.0), ("c2", "sonnet", 38.0), ("c1", "opus", 64.0),
              ("c2", "opus", 64.0)]  # fmt: skip
    assert "204" in guard.plan_refusal(blocks, 175.0)
    long_run = _load("adopt_long_run_fixes", ADOPT / "long_run.py")
    gate = [(c, m, long_run.GATE_CHAIN_CAP[m]) for m in ("sonnet", "opus") for c in ("c1", "c2")]
    assert guard.plan_refusal(gate, long_run.GATE_CEILING) == ""
    assert sum(cap for *_x, cap in gate) <= long_run.GATE_CEILING


# ---- f: the hooks' Jev ceiling is the chain's, not a per-call 0.10 -----------------------------


def test_f_the_runner_sets_the_hooks_jev_ceiling_for_a_resumed_chain(tmp_path) -> None:  # noqa: ANN001
    env = hook_env.environment(tmp_path, tmp_path / "k", base={"ADOPT_JEV_MAX_USD": "0.50"})
    assert env["SANCHOPANZA_SESSION_MAX_USD"] == "0.50"
    plain = hook_env.environment(tmp_path, tmp_path / "k", base={})
    assert plain["SANCHOPANZA_SESSION_MAX_USD"] == "0.10"  # phase A and B as they ran


# ---- h: caps are set in the owner's prices and passed in Claude Code's ------------------------


def test_h_a_sonnet_cap_of_4_5_owner_usd_is_passed_as_3_in_claude_codes_price() -> None:
    assert meter.claude_code_cap(4.5, "claude-sonnet-5-5") == pytest.approx(3.0)
    # Opus: Claude Code reads cache at 0.2 against the owner's 0.5: the safe side is the lowest.
    assert meter.claude_code_cap(8.0, "claude-opus-5-5") == pytest.approx(3.2)
    assert meter.claude_code_cap(1.0, "claude-haiku-4-5-20251001") == pytest.approx(1.0)


def test_h_claude_codes_reported_cost_is_two_thirds_of_the_owners_on_sonnet() -> None:
    usage = {"inputTokens": 10, "outputTokens": 1000, "cacheReadInputTokens": 100_000,
             "cacheCreationInputTokens": 5_000}  # fmt: skip
    cc = meter.model_usage_cost({"claude-sonnet-5-5": usage}, meter.CLAUDE_CODE_RATES)
    owner = meter.model_usage_cost({"claude-sonnet-5-5": usage}, meter.OWNER_RATES)
    assert cc == pytest.approx(owner * 2 / 3)
