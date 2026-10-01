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


# ---- amendment 2: an arm an error result stopped is set aside and run whole -------------------


def _isolate(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    monkeypatch.setattr(run, "CLAUDE_PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(run.docker_env, "export", lambda tag, work: "base")

    def no_call(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("claude -p must not be called")

    monkeypatch.setattr(run.subprocess, "run", no_call)


def test_the_projects_folder_is_the_one_claude_code_names_for_the_working_copy() -> None:
    work = pathlib.Path(r"C:\Users\roman\.cache\sanchopanza\adopt\work\pydantic__pydantic-2-Sm")
    assert run.projects_dir(work).name == (
        "C--Users-roman--cache-sanchopanza-adopt-work-pydantic--pydantic-2-Sm"
    )


def test_continue_refuses_a_held_out_arm_an_error_result_stopped(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _isolate(tmp_path, monkeypatch)
    evidence = tmp_path / "runs" / "c" / "N"
    evidence.mkdir(parents=True)
    calls = [{"request": 1, "status": "NOT RUN (error result)", "session": "dead"},
             {"request": 2, "status": "NOT RUN (harness)"}]  # fmt: skip
    (evidence / "row.json").write_text(json.dumps({"session": "dead", "base": "b",
                                                   "calls": calls}), encoding="utf-8")  # fmt: skip
    chain = {"chain": "c", "split": "held", "tag": "t", "bugs": [{}, {}]}
    with pytest.raises(RuntimeError, match="set the attempt aside"):
        run.one_chain(chain, "N", "m", 10.0, tmp_path / "key", carry_on=True)


def test_a_held_out_arm_does_not_start_over_sessions_of_an_earlier_attempt(
    tmp_path, monkeypatch
) -> None:  # noqa: ANN001
    _isolate(tmp_path, monkeypatch)
    # pydantic-2 Sm, phase A: memory caught up the crashed attempt's session from this folder.
    old = run.projects_dir(tmp_path / "work" / "c-Sm")
    old.mkdir(parents=True)
    (old / "6a5b1218.jsonl").write_text("{}", encoding="utf-8")
    chain = {"chain": "c", "split": "held", "tag": "t", "bugs": [{}]}
    with pytest.raises(RuntimeError, match="earlier sessions"):
        run.one_chain(chain, "Sm", "m", 10.0, tmp_path / "key")
    assert not (tmp_path / "runs" / "c" / "Sm").exists()  # refused before any evidence


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
