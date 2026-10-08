"""A pytest run that hangs is a run with no results, and its container is removed.

dvc-long60-1's validation (2026-10-08) stopped after 2 h 23 min: while `masking.culprits` searched
for a culprit, one `docker run` of a bug's FAIL_TO_PASS passed its 3,600 s timeout.
`subprocess.TimeoutExpired` escaped `passes_with`, which reads only a RuntimeError as "does not
pass", and the killed `docker` client left the container running (still there 5 h later). Now the
run is named, a timeout removes that container, and the run comes back with no results (exit 124):
`pytest` raises its RuntimeError, so the masking questions read "does not pass" and a chain's own
checks stop with the reason. No Docker, no network."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
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


docker_env = _load("adopt_docker_env_timeout", "docker_env.py")
masking = _load("adopt_masking_timeout", "masking.py")


def _hanging(calls: list[tuple[str, ...]]):  # noqa: ANN202
    def fake_docker(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(args)
        if args[0] == "run":
            raise subprocess.TimeoutExpired(["docker", *args], kwargs.get("timeout", 0))
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    return fake_docker


def _name_of(run_args: tuple[str, ...]) -> str:
    return run_args[run_args.index("--name") + 1]


def test_a_hung_run_removes_its_container_and_has_no_results(monkeypatch) -> None:  # noqa: ANN001
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(docker_env, "docker", _hanging(calls))
    with pytest.raises(RuntimeError, match="timed out"):
        docker_env.pytest("tag", "", ["t.py::test_a"])
    run = next(c for c in calls if c[0] == "run")
    assert ("rm", "-f", _name_of(run)) in calls


def test_each_run_has_its_own_container_name(monkeypatch) -> None:  # noqa: ANN001
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(docker_env, "docker", _hanging(calls))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            docker_env.pytest("tag", "", ["t.py::test_a"])
    names = [_name_of(c) for c in calls if c[0] == "run"]
    assert len(names) == 2 and names[0] != names[1]


def test_a_hung_run_reads_as_not_passing_in_the_culprit_search(monkeypatch) -> None:  # noqa: ANN001
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(masking.docker_env, "docker", _hanging(calls))
    bugs = [{"FAIL_TO_PASS": ["t.py::test_a"], "patch": "p0\n"},
            {"FAIL_TO_PASS": ["t.py::test_b"], "patch": "p1\n"}]  # fmt: skip
    assert masking.passes_with("tag", bugs, 0, [1]) is False
    assert masking.fails_with("tag", bugs, 0, [1]) is False
