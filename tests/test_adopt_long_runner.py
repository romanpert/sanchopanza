"""The long-chain runner end to end, against a stand-in for `claude` that replays B2's recorded
calls (`tests/fixtures/long_fake`). No model, no API, no Jev, no Docker: the working copy is a
local git repository and Docker's health and labels are stubbed; everything else is the runner
as the launcher starts it (`long_run.main`), with its clean user, caps, rows and stop files.

The four gate chains: `pydantic__pydantic-long40-1` and `conan-io__conan-long40-1` (the long60
chains are not built yet), on Sonnet and Opus, arm N, the first 6 bugs each. Injected: a
compaction, a timeout, a crash, a usage limit, and (in an S arm) a failed MCP server."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
FAKE = ROOT / "tests" / "fixtures" / "long_fake" / "fake_claude.py"
MAIN_VENV = pathlib.Path(r"C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts")
OURS = ("run", "long", "docker_env", "perbug", "long_run", "long_call", "long_guard",
        "long_report", "arm_files", "hook_env", "meter", "carry", "chains", "related", "masking")


def _purge() -> None:
    for name in OURS:
        sys.modules.pop(name, None)


@pytest.fixture
def lr(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):  # type: ignore[no-untyped-def]
    """`long_run` imported fresh from benchmarks/adopt, with Docker and the home folder stubbed."""
    _purge()
    monkeypatch.syspath_prepend(str(ADOPT))
    import long_run

    monkeypatch.setattr(long_run.docker_env, "export", _export)
    monkeypatch.setattr(long_run.docker_env, "health", lambda: "")
    monkeypatch.setattr(long_run.docker_env, "remove_labelled", lambda _v: [])
    monkeypatch.setattr(long_run.carry, "ancestors_memory", lambda _p: [])
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-oauth-token-for-tests")
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-typesafe-key")
    yield long_run
    _purge()


def _export(tag: str, dest: pathlib.Path) -> str:
    dest.mkdir(parents=True)
    (dest / "pkg.py").write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    git = ["git", "-C", str(dest), "-c", "user.name=t", "-c", "user.email=t@t"]
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "start"]):
        subprocess.run([*git, *step], check=True, capture_output=True)
    return subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()  # fmt: skip


def _chain(name: str) -> dict[str, Any]:
    bugs = [{"instance_id": f"{name}.b{i}", "problem_statement": f"Issue {i}: it breaks.",
             "patch": "", "FAIL_TO_PASS": [f"tests/t.py::t{i}"], "PASS_TO_PASS_STAR": []}
            for i in range(1, 9)]  # fmt: skip
    return {"chain": name, "split": "dev", "tag": "fake:tag", "valid": True, "kind": "long",
            "image": "fake", "bugs": bugs}  # fmt: skip


def _setup(lr: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
           arms: tuple[str, ...], chains: tuple[str, ...], models: tuple[str, ...],
           inject: dict[str, Any]) -> list[str]:  # fmt: skip
    profile = lr.Profile("fake", arms, models, dict.fromkeys(models, 1.0),
                         dict.fromkeys(models, 20.0), 200.0, chains, bugs=6, timeout_s=3.0,
                         idle_s=60.0)  # fmt: skip
    monkeypatch.setitem(lr.PROFILES, "fake", profile)
    monkeypatch.setenv("FAKE_CLAUDE_INJECT", json.dumps(inject))
    known = tmp_path / "chains.json"
    known.write_text(json.dumps({n: _chain(n) for n in chains}), encoding="utf-8")
    return ["run", "--profile", "fake", "--root", str(tmp_path / "L"), "--chains-file",
            str(known), "--limit-flag", str(tmp_path / "LIMIT.flag"), "--allow-midnight",
            "--claude", json.dumps([sys.executable, str(FAKE)])]  # fmt: skip


def _row(tmp_path: pathlib.Path, run_name: str, arm: str = "N") -> dict[str, Any]:
    path = tmp_path / "L" / "runs" / run_name / arm / "row.json"
    return json.loads(path.read_text(encoding="utf-8"))


PYD, CONAN = "pydantic__pydantic-long40-1", "conan-io__conan-long40-1"


def test_four_gate_chains_replay_with_every_injection_detected_and_handled(
    lr: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fake counts calls, retries included: its 8th call is request 7 (5 ran twice).
    inject = {f"{PYD}-sonnet-N": {"3": "compact", "5": "timeout", "8": "crash"},
              f"{CONAN}-opus-N": {"2": "429"}}  # fmt: skip
    argv = _setup(lr, tmp_path, monkeypatch, ("N",), (PYD, CONAN), ("sonnet", "opus"), inject)
    code = lr.main(argv)
    assert code == 2  # the usage limit stopped the last chain
    assert (tmp_path / "LIMIT.flag").exists()

    first = _row(tmp_path, f"{PYD}-sonnet")
    calls = {c["request"]: c for c in first["calls"]}
    assert len(calls) == 8 and first["partial"] is False and first["stopped"] == ""
    # compaction: recorded, and its call's cost found in modelUsage though not in the transcript
    assert calls[3]["compactions"] == [{"trigger": "auto", "pre": 160_500, "post": 9_000}]
    assert calls[3]["unlogged_owner_usd"] > 0 and calls[2]["unlogged_owner_usd"] == 0
    # timeout with no tool and no change: killed, retried once, ran
    assert calls[5]["retried"] and calls[5]["status"] == "ran"
    assert (tmp_path / "L" / "runs" / f"{PYD}-sonnet" / "N" / "stream-5-retry.jsonl").exists()
    # crash after a tool and a change: charged its cap, a declared deviation, the chain went on
    assert calls[7]["status"] == "cut (exit 3)" and "deviation" in calls[7]
    assert calls[7]["owner_usd"] == 1.0 and calls[7]["charged_cap"]
    assert calls[8]["status"] == "ran"
    assert first["permission_modes"] == ["default"]
    assert all(c["init"]["version"] == "2.1.287" for c in first["calls"] if c["init"])
    assert (tmp_path / "L" / "runs" / f"{PYD}-sonnet" / "N" / "transcript.jsonl").exists()
    assert first["missing_transcripts"] == []

    # Sonnet at the owner's 3/15 is 1.5x Claude Code's 2/10 on the same tokens
    ran = [c for c in _row(tmp_path, f"{CONAN}-sonnet")["calls"] if c["status"] == "ran"]
    assert len(ran) == 8
    assert sum(c["owner_usd"] for c in ran) == pytest.approx(1.5 * sum(c["cc_usd"] for c in ran))

    assert all(c["status"] == "ran" for c in _row(tmp_path, f"{PYD}-opus")["calls"])
    limited = _row(tmp_path, f"{CONAN}-opus")
    statuses = [c["status"] for c in limited["calls"]]
    assert limited["calls"][1]["limits"] == ["limit"] and limited["stopped"] == "limit"
    assert limited["calls"][1]["status"] == "error result (limit)"
    assert statuses[2:] == ["NOT RUN (limit)"] * 6


def test_the_control_token_is_the_arms_own_and_reaches_every_changes_file(
    lr: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = _setup(lr, tmp_path, monkeypatch, ("N",), (PYD,), ("sonnet",), {})
    assert lr.main(argv) == 0
    row = _row(tmp_path, f"{PYD}-sonnet")
    final = (tmp_path / "L" / "runs" / f"{PYD}-sonnet" / "N" / "final.patch").read_text("utf-8")
    assert final.count(f"+Ref: {row['token']}") == 6
    assert [c["kind"] for c in row["calls"]].count("callback") == 2


def test_a_failed_mcp_server_in_the_s_arm_stops_the_chain_and_writes_stop(
    lr: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not (MAIN_VENV / "sanchopanza.exe").exists():
        pytest.skip("no sanchopanza.exe to install the S arm with")
    monkeypatch.setattr(lr.run, "SANCHO", MAIN_VENV / "sanchopanza.exe")
    monkeypatch.setattr(lr.run, "PYTHON", MAIN_VENV / "python.exe")
    monkeypatch.setattr(lr.run, "KEYS", tmp_path / "keys")
    argv = _setup(lr, tmp_path, monkeypatch, ("S",), (PYD,), ("sonnet",),
                  {f"{PYD}-sonnet-S": {"2": "mcpfail"}})  # fmt: skip
    assert lr.main(argv) == 4
    row = _row(tmp_path, f"{PYD}-sonnet", "S")
    assert row["calls"][0]["status"] == "ran" and not row["calls"][0]["breaks"]
    assert any("failed" in b for b in row["calls"][1]["breaks"])
    assert (tmp_path / "L" / "STOP").exists()
    settings = json.loads((tmp_path / "L" / "w" / f"{PYD}-sonnet-S" / ".claude" /
                           "settings.json").read_text(encoding="utf-8"))  # fmt: skip
    assert settings["env"]["SANCHOPANZA_CANDOR_MODE"] == "observe"
    assert settings["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "193000"


def test_a_stop_file_present_refuses_the_run_before_any_call(
    lr: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = _setup(lr, tmp_path, monkeypatch, ("N",), (PYD,), ("sonnet",), {})
    (tmp_path / "L").mkdir()
    (tmp_path / "L" / "STOP").write_text("by hand", encoding="utf-8")
    assert lr.main(argv) == 1
    assert not (tmp_path / "L" / "runs").exists()


def test_n_early_differs_from_n_by_its_window_alone(
    lr: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = _setup(lr, tmp_path, monkeypatch, ("N", "Ne"), (PYD,), ("sonnet",), {})
    assert lr.main(argv) == 0
    work = tmp_path / "L" / "w"
    early = json.loads((work / f"{PYD}-sonnet-Ne" / ".claude" / "settings.json").read_text("utf-8"))
    assert early == {"env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "193000"}}
    assert not (work / f"{PYD}-sonnet-N" / ".claude").exists()
    streams = [tmp_path / "L" / "runs" / f"{PYD}-sonnet" / a / "stream-1.jsonl" for a in ("N", "Ne")]
    inits = [json.loads(p.read_text("utf-8").splitlines()[0]) for p in streams]
    assert inits[0]["permissionMode"] == inits[1]["permissionMode"] == "default"
    tokens = {_row(tmp_path, f"{PYD}-sonnet", a)["token"] for a in ("N", "Ne")}
    assert len(tokens) == 2  # a token per chain and arm


def test_the_smoke_profile_cannot_raise_its_hard_cap(lr: ModuleType) -> None:
    with pytest.raises(SystemExit, match="at most 8.0"):
        lr.ceiling_of(lr.PROFILES["smoke"], 9.0)
    assert lr.ceiling_of(lr.PROFILES["smoke"], 0.0) == 8.0
    smoke = lr.PROFILES["smoke"]
    assert smoke.bugs == 3 and smoke.models == ("haiku",) and smoke.window == 100_000
    assert smoke.budget == 67_000 and smoke.forced_timeouts == (("N", 2, 90.0),)
    assert smoke.call_cap == {"haiku": 1.0} and smoke.chain_cap == {"haiku": 2.0}


def test_the_command_never_bypasses_permissions_and_is_the_same_in_every_arm(
    lr: ModuleType, tmp_path: pathlib.Path
) -> None:
    mcp = tmp_path / ".mcp.json"
    cmd = lr.long_call.command(("claude",), "claude-sonnet-5-5", "fix", None, 3.0, mcp)
    assert "bypassPermissions" not in cmd and "--dangerously-skip-permissions" not in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "default"
    assert "--allowedTools" in cmd and cmd[cmd.index("--max-budget-usd") + 1] == "3.00"
    for arm in ("N", "Ne", "S"):
        assert lr.arm_spec(arm, lr.PROFILES["dev"]).fresh is False


def test_arm_order_rotates_by_chain_and_keeps_every_arm(lr: ModuleType) -> None:
    orders = {lr.arm_order(f"chain-{i}", ("N", "Ne", "S")) for i in range(12)}
    assert len(orders) > 1 and all(sorted(o) == ["N", "Ne", "S"] for o in orders)
