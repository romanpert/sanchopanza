"""How a request reaches `claude -p`: a prompt too long for Windows' command line goes through
stdin (pydantic-2's second issue, 34,215 characters, failed CreateProcess in phase A), and a call
that cannot be started is NOT RUN (harness) with the arm's row written, never a crash."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from types import ModuleType

import pytest

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"
sys.path.append(str(ADOPT))


def _load(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ADOPT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _purge() -> None:
    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None) or ""
        if not name.startswith("adopt_") and pathlib.Path(where).parent == ADOPT:
            del sys.modules[name]


run = _load("adopt_run_launch", "run.py")
_purge()


def test_a_short_prompt_stays_an_argument_as_before() -> None:
    cmd = run.command("m", "fix it", None, None)
    assert cmd[:3] == ["claude", "-p", "fix it"] and run.stdin_for("fix it") is None


def test_a_prompt_too_long_for_the_command_line_goes_through_stdin() -> None:
    long = "x" * (run.ARGV_PROMPT_MAX + 1)
    cmd = run.command("m", long, "sess", None)
    assert long not in cmd and cmd[:2] == ["claude", "-p"] and "--resume" in cmd
    assert run.stdin_for(long) == long.encode("utf-8")
    assert sum(len(a) for a in cmd) < 8000  # what is left fits any Windows command line


def test_a_call_that_cannot_start_is_not_run_and_the_row_is_written(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    monkeypatch.setattr(run.docker_env, "export", lambda tag, work: "base")
    monkeypatch.setattr(run.docker_env, "agent_diff", lambda work, base: "")
    monkeypatch.setattr(run, "reserve", lambda *_a: True)
    monkeypatch.setattr(run, "settle", lambda *_a: None)
    monkeypatch.setattr(run, "claude_version", lambda: "x")

    def refuse(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise FileNotFoundError(206, "The filename or extension is too long")

    monkeypatch.setattr(run.subprocess, "run", refuse)
    bugs = [{"instance_id": f"r.b{k}", "problem_statement": "p"} for k in range(3)]
    chain = {"chain": "c", "split": "held", "tag": "t", "bugs": bugs}
    run.one_chain(chain, "N", "m", 10.0, tmp_path / "key")
    row = json.loads((tmp_path / "runs" / "c" / "N" / "row.json").read_text(encoding="utf-8"))
    assert [c["status"] for c in row["calls"]] == ["NOT RUN (harness)"] * 3
    assert "too long" in row["calls"][0]["stderr"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
