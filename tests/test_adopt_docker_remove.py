"""`docker_env.remove_labelled` must not end a paid chain over a container already going away."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ADOPT = Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"


def _done(code: int, out: bytes = b"", err: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["docker"], code, out, err)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ADOPT))
    import docker_env

    yield docker_env
    sys.modules.pop("docker_env", None)


def _fake(calls: list[tuple[str, ...]], rm: list[subprocess.CompletedProcess],
          left: list[bytes]):  # fmt: skip
    def docker(*args: str, stdin: bytes | None = None, timeout: int = 3600):
        calls.append(args)
        if args[0] == "ps":
            return _done(0, left.pop(0) if left else b"")
        return rm.pop(0)

    return docker


def test_a_removal_already_in_progress_is_not_fatal(env, monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    busy = b"Error response from daemon: removal of container 585fafc5c66c is already in progress"
    monkeypatch.setattr(env, "docker", _fake(calls, [_done(1, err=busy)], [b"585fafc5c66c\n", b""]))
    monkeypatch.setattr(env, "REMOVE_WAIT_S", 0.0)
    assert env.remove_labelled("x-N") == ["585fafc5c66c"]


def test_a_container_already_gone_is_not_fatal(env, monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    gone = b"Error response from daemon: No such container: 585fafc5c66c"
    monkeypatch.setattr(env, "docker", _fake(calls, [_done(1, err=gone)], [b"585fafc5c66c\n", b""]))
    monkeypatch.setattr(env, "REMOVE_WAIT_S", 0.0)
    assert env.remove_labelled("x-N") == ["585fafc5c66c"]


def test_a_container_that_stays_after_the_wait_still_fails(env, monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    busy = b"Error response from daemon: removal of container abc is already in progress"
    monkeypatch.setattr(env, "docker",
                        _fake(calls, [_done(1, err=busy)], [b"abc\n"] * 10))  # fmt: skip
    monkeypatch.setattr(env, "REMOVE_WAIT_S", 0.0)
    monkeypatch.setattr(env, "REMOVE_CHECKS", 3)
    with pytest.raises(RuntimeError, match="still there"):
        env.remove_labelled("x-N")


def test_another_docker_error_still_fails(env, monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    other = b"Cannot connect to the Docker daemon"
    monkeypatch.setattr(env, "docker", _fake(calls, [_done(1, err=other)], [b"abc\n"]))
    monkeypatch.setattr(env, "REMOVE_WAIT_S", 0.0)
    with pytest.raises(RuntimeError, match="docker rm failed"):
        env.remove_labelled("x-N")
