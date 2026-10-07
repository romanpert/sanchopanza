"""The launchers `long-smoke-run.cmd` and `long-gate-run.cmd`, end to end through `cmd.exe`, with a
stand-in `claude` (`tests/fixtures/long_fake`), a stand-in runner for Docker (`dry_runner.py`)
and a stand-in `python -m sanchopanza jev-preflight`. Free: no model, no API, no Jev, no Docker.

`dry_environment` builds what a dry launch needs and is used by the dry run in STATUS-launch.md.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
FAKE = ROOT / "tests" / "fixtures" / "long_fake"
MAIN_VENV = pathlib.Path(r"C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts")
# The sealed S (cb0062e, frozen by benchmarks/adopt/freeze.py) when it is here; else main's venv.
SEALED = (pathlib.Path.home() / ".cache" / "sanchopanza" / "adopt" / "frozen"
          / "cb0062e36340-jev-mcp" / "Scripts" / "sanchopanza.exe")  # fmt: skip
SANCHO = SEALED if SEALED.exists() else MAIN_VENV / "sanchopanza.exe"
GATE = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")
SMOKE = "pydantic__pydantic-long60-1"

pytestmark = pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")


def _digest(chain: dict[str, Any]) -> str:
    """`run.chain_digest`, run in a child: importing benchmarks/adopt here would leave its plain
    module names (`run`) in sys.modules for other benchmarks' tests."""
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import run; "
            "print(run.chain_digest(json.loads(sys.stdin.read())))")
    done = subprocess.run([sys.executable, "-c", code, str(ADOPT)], input=json.dumps(chain),
                          capture_output=True, text=True, check=True)  # fmt: skip
    return done.stdout.strip()


def _chain(name: str) -> dict[str, Any]:
    bugs = [{"instance_id": f"{name}.b{i}", "problem_statement": f"Issue {i}: it breaks.",
             "patch": "", "FAIL_TO_PASS": [f"tests/t.py::t{i}"], "PASS_TO_PASS_STAR": []}
            for i in range(1, 7)]  # fmt: skip
    return {"chain": name, "split": "gate", "tag": "fake:tag", "valid": True, "kind": "long",
            "image": "fake", "bugs": bugs}  # fmt: skip


def dry_environment(base: pathlib.Path, chains: tuple[str, ...]) -> dict[str, str]:
    """Chains, manifests, a `claude` on PATH that is the stand-in, the dry config; returns the
    environment variables the launcher reads in `dry` mode (and fakes for every secret)."""
    base.mkdir(parents=True, exist_ok=True)
    known = {n: _chain(n) for n in chains}
    (base / "chains.json").write_text(json.dumps(known), encoding="utf-8")
    manifests = base / "long60"
    manifests.mkdir(exist_ok=True)
    for name, chain in known.items():
        body = {"chain": name, "valid": True, "sha256": _digest(chain)}
        (manifests / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")
    pin = base / "pin"
    pin.mkdir(exist_ok=True)
    (pin / "claude.cmd").write_text(f'@"{sys.executable}" "{FAKE / "fake_claude.py"}" %*\r\n',
                                    encoding="utf-8", newline="")  # fmt: skip
    secrets = {"CLAUDE_CODE_OAUTH_TOKEN": "fake-oauth-token", "TYPESAFE_API_KEY": "fake-key"}
    config = {"root": str(base / "L"), "runner": str(FAKE / "dry_runner.py"),
              "claude": [sys.executable, str(FAKE / "fake_claude.py")],
              "chains_file": str(base / "chains.json"), "manifests": str(manifests),
              "limit_flag": str(base / "LIMIT.flag"), "allow_midnight": True,
              "sancho": str(SANCHO), "preflight_python": sys.executable,
              "preflight_pythonpath": str(FAKE / "preflight"), "env": secrets}  # fmt: skip
    (base / "dry.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
    return {"LL_ROOT": str(base / "L"), "LL_PIN": str(pin), "LL_MANIFESTS": str(manifests),
            "LL_DRY_CONFIG": str(base / "dry.json"), **secrets}  # fmt: skip


def launch(cmd: str, args: list[str], env: dict[str, str], timeout: float = 600.0) -> int:
    full = {**os.environ, **env}
    for name in ("PYTHONPATH", "CLAUDE_CONFIG_DIR"):
        full.pop(name, None)
    done = subprocess.run(["cmd.exe", "/c", str(ROOT / cmd), *args], env=full, timeout=timeout,
                          capture_output=True, text=True)  # fmt: skip
    return done.returncode


def _row(root: pathlib.Path, run_name: str, arm: str) -> dict[str, Any]:
    return json.loads((root / "runs" / run_name / arm / "row.json").read_text(encoding="utf-8"))


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_gate_launcher_runs_n_on_both_models_records_windows_and_resumes(
    tmp_path: pathlib.Path,
) -> None:
    env = dry_environment(tmp_path, GATE)
    root = tmp_path / "L"
    # the usage limit at Opus' third call on pydantic: the launch stops there
    inject = {f"{GATE[1]}-opus-N": {"3": "429"}}
    code = launch("long-gate-run.cmd", ["dry"], {**env, "FAKE_CLAUDE_INJECT": json.dumps(inject),
                                                 "FAKE_SERVER_WINDOW": "1000000"})  # fmt: skip
    assert code == 2, _text(root / "launch.log")
    assert (tmp_path / "LIMIT.flag").exists()
    log = _text(root / "launch.log")
    assert "sonnet (claude-sonnet-5-5): 4.50 USD per call (--max-budget-usd at most 3.00" in log
    assert "opus (claude-opus-5-5): 8.00 USD per call (--max-budget-usd at most 3.20" in log
    assert "caps held 226.00 USD" in log and "ceiling 230.00" in log
    assert "expected total" in log and "jev preflight" not in log  # no S arm, no preflight
    pids = json.loads(_text(root / "launch.json"))
    assert pids[0]["launcher"]["pid"] and pids[0]["runner_sonnet"]["pid"]
    assert pids[0]["runner_sonnet_exit"] == 0 and pids[0]["runner_opus_exit"] == 2
    windows = json.loads(_text(root / "windows.json"))
    assert windows["claude-sonnet-5-5"]["N"]["effective_reported"] == 980_000
    assert windows["claude-sonnet-5-5"]["N"]["value"] == 1_000_000
    assert windows["claude-opus-5-5"]["N"]["source"].startswith("clientdata")
    limited = _row(root, f"{GATE[1]}-opus", "N")
    assert limited["stopped"] == "limit"
    done_before = [c for c in limited["calls"] if c["status"] == "ran"]

    # the limit passes: the same launcher again resumes Opus' pydantic arm, nothing re-run
    (tmp_path / "LIMIT.flag").unlink()
    code = launch("long-gate-run.cmd", ["dry"], env)
    assert code == 0, _text(root / "launch.log")
    resumed = _row(root, f"{GATE[1]}-opus", "N")
    assert resumed["stopped"] == "" and resumed["partial"] is False
    requests = [c["request"] for c in resumed["calls"] if c["status"] == "ran"]
    assert requests[: len(done_before)] == [c["request"] for c in done_before]
    assert requests == list(range(1, resumed["requests_planned"] + 1))  # each asked once
    # the call the limit rejected did nothing: kept (its cost counts), marked, asked again
    rejected = [c for c in resumed["calls"] if c["status"] == "error result (limit)"]
    assert [c["request"] for c in rejected] == [3] and rejected[0]["superseded"]
    assert "resumed at request 3" in _text(root / "runner-opus.log")
    assert "done (to its end); never run twice" in _text(root / "runner-sonnet.log")
    report = json.loads(_text(root / "report.json"))
    assert set(report["gate"]) == {"sonnet", "opus"}
    line = report["arms"][f"{GATE[0]}/claude-sonnet-5-5/N"]
    assert line["window"]["source"].startswith("session debug line")
    assert "give_ups" in line and line["give_ups"]["give_ups"] >= 0


def test_gate_launcher_refuses_without_a_chain_manifest(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, GATE)
    (pathlib.Path(env["LL_MANIFESTS"]) / f"{GATE[0]}.json").unlink()
    assert launch("long-gate-run.cmd", ["dry"], env) == 1
    status = _text(tmp_path / "L" / "launch.status")
    assert f"no manifest {env['LL_MANIFESTS']}\\{GATE[0]}.json" in status
    assert not (tmp_path / "L" / "runs").exists()


def test_gate_launcher_refuses_a_claude_that_is_not_the_pin(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, GATE)
    (pathlib.Path(env["LL_PIN"]) / "claude.cmd").write_text("@echo 2.1.290 (Claude Code)\r\n",
                                                              encoding="utf-8", newline="")
    assert launch("long-gate-run.cmd", ["dry"], env) == 3
    assert "not 2.1.287" in _text(tmp_path / "L" / "launch.status")


@pytest.mark.skipif(not (MAIN_VENV / "sanchopanza.exe").exists(), reason="no sanchopanza.exe")
def test_smoke_launcher_preflight_failure_stops_before_any_call(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, (SMOKE,))
    code = launch("long-smoke-run.cmd", ["0000000", "dry"], {**env, "FAKE_PREFLIGHT_EXIT": "10"})
    assert code == 10
    root = tmp_path / "L"
    assert "exit 10 (no_funds)" in _text(root / "preflight.txt")
    assert not (root / "runs").exists() and not (root / "runner-haiku.log").exists()


@pytest.mark.skipif(not (MAIN_VENV / "sanchopanza.exe").exists(), reason="no sanchopanza.exe")
def test_smoke_launcher_runs_three_arms_on_three_bugs_and_resumes_a_dead_runner(
    tmp_path: pathlib.Path,
) -> None:
    env = dry_environment(tmp_path, (SMOKE,))
    code = launch("long-smoke-run.cmd", ["0000000", "dry"], env)
    root = tmp_path / "L"
    assert code == 0, _text(root / "launch.log")
    log = _text(root / "launch.log")
    assert "haiku (claude-haiku-4-5-20251001): 1.00 USD per call" in log
    assert "2.00 per chain and arm, arms N, Ne, S" in log
    assert "caps held 6.00 USD" in log and "ceiling 8.00 (hard, in code)" in log
    assert "3 bugs + 2 callbacks" in log
    assert "exit 0 (ok)" in _text(root / "preflight.txt")
    name = f"{SMOKE}-haiku"
    rows = {a: _row(root, name, a) for a in ("N", "Ne", "S")}
    assert all(len(r["calls"]) == 5 for r in rows.values())  # 3 bugs and 2 callbacks
    assert rows["Ne"]["window"]["configured"] == 100_000 == rows["S"]["window"]["configured"]
    assert rows["N"]["window"]["configured"] is None
    assert rows["S"]["calls"][0]["init"]["mcp"]  # S's servers were installed and listed
    assert all(c["metered_ids"] and c["usage_after"] for r in rows.values() for c in r["calls"])
    assert "gate:" in _text(root / "grade.log")  # graded (stand-in pytest), give-ups apart
    assert f"S runs {SANCHO}" in log
    if SANCHO == SEALED:  # the sealed install's guard: struct over 6 parts, no chooser of ours
        assert "guard: 6 SessionStart(compact) parts, chooser the install's default" in _text(
            root / "runner-haiku.log")


def test_the_launchers_are_lf_and_name_the_caps_the_code_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = set(sys.modules)
    monkeypatch.syspath_prepend(str(ADOPT))
    import long_run

    for name in ("long-smoke-run.cmd", "long-gate-run.cmd"):
        raw = (ROOT / name).read_bytes()
        assert b"\r\n" not in raw
    gate, smoke = long_run.PROFILES["gate"], long_run.PROFILES["smoke"]
    assert gate.arms == ("N",) and gate.chains == GATE and gate.models == ("sonnet", "opus")
    assert dict(gate.call_cap) == {"sonnet": 4.5, "opus": 8.0}
    assert dict(gate.chain_cap) == {"sonnet": 38.0, "opus": 75.0} and gate.ceiling == 230.0
    assert smoke.chains == (SMOKE,) and smoke.bugs == 3 and smoke.arms == ("N", "Ne", "S")
    assert shutil.which("cmd.exe")
    for name in set(sys.modules) - before:
        sys.modules.pop(name, None)
