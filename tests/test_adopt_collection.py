"""Amendment 5, second part: a test file that cannot be collected stops pytest whole (exit 2,
which xargs turns into 123, read as "tests failed"), so every other node comes out absent and is
counted as not passing. A bug of conan-long40-1 removes `rm`, test_rm.py does not import, and
31 of its 40 bugs validated with no PASS_TO_PASS test passing. Development chains now run pytest
with `--continue-on-collection-errors`; held-out chains keep the sealed command, so phase A's
arms and their rerun are graded the same way. No Docker, no network."""

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


def _purge() -> None:
    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None) or ""
        if not name.startswith("adopt_") and pathlib.Path(where).parent == ADOPT:
            del sys.modules[name]


docker_env = _load("adopt_docker_env_collection", "docker_env.py")
run = _load("adopt_run_collection", "run.py")
validate = _load("adopt_validate_collection", "validate.py")
_purge()

FLAG = "--continue-on-collection-errors"


def _capture(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> list[str]:
    scripts: list[str] = []

    def fake_docker(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
        scripts.append(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout=b"PASSED t.py::a\n", stderr=b"")

    monkeypatch.setattr(module, "docker", fake_docker)
    return scripts


def test_pytest_keeps_the_sealed_command_unless_asked(monkeypatch) -> None:  # noqa: ANN001
    scripts = _capture(monkeypatch, docker_env)
    docker_env.pytest("tag", "", ["t.py::a"])
    docker_env.pytest("tag", "", ["t.py::a"], keep_collecting=True)
    assert FLAG not in scripts[0]
    assert FLAG in scripts[1]


def test_a_development_chain_is_graded_past_a_collection_error(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    asked: list[bool] = []

    def fake_pytest(tag, patch, nodes, **kwargs):  # noqa: ANN001, ANN003, ANN202
        asked.append(kwargs.get("keep_collecting", False))
        return {n: "PASSED" for n in nodes}

    monkeypatch.setattr(run.docker_env, "pytest", fake_pytest)
    monkeypatch.setattr(run, "RUNS", tmp_path)
    bug = {"instance_id": "b", "FAIL_TO_PASS": ["t.py::a"], "PASS_TO_PASS_STAR": []}
    for split in ("dev", "held"):
        (tmp_path / f"c-{split}" / "N").mkdir(parents=True)
        (tmp_path / f"c-{split}" / "N" / "final.patch").write_text("", encoding="utf-8")
        chain = {"chain": f"c-{split}", "split": split, "tag": "t", "bugs": [bug]}
        monkeypatch.setattr(run, "sealed", lambda: True)
        run.grade_chain(chain, "N", 1)
    assert asked == [True, False]


def test_validation_of_a_development_chain_keeps_collecting(monkeypatch) -> None:  # noqa: ANN001
    asked: list[bool] = []

    def fake_pytest(tag, patch, nodes, **kwargs):  # noqa: ANN001, ANN003, ANN202
        asked.append(kwargs.get("keep_collecting", False))
        return dict.fromkeys(nodes, "FAILED") if not kwargs.get("reverse") else dict.fromkeys(
            nodes, "PASSED")  # fmt: skip

    monkeypatch.setattr(validate.docker_env, "pytest", fake_pytest)
    monkeypatch.setattr(validate.docker_env, "bake", lambda *a, **k: None)
    bug = {"instance_id": "b", "patch": "p", "FAIL_TO_PASS": ["t.py::a"], "PASS_TO_PASS": []}
    for split in ("dev", "held"):
        validate.check({"chain": f"c-{split}", "split": split, "image": "i"}, [bug])
    assert asked == [True, True, False, False]


# A listed node id that does not exist ("ERROR: not found") stops pytest before any test runs,
# with or without --continue-on-collection-errors. pydantic's doc tests are named by line range
# (`test_docstrings_examples[pydantic/types.py:2042-2063]`): another bug of the chain in that file
# shifts the range, so every run of the chain's FAIL_TO_PASS with that bug in came out empty, all
# 60 bugs of pydantic-long60-1 read as masked, and bisection (own nodes only, which ran) blamed
# the chain's first two bugs six rounds running.


def _fake_missing(monkeypatch: pytest.MonkeyPatch, missing: set[str]) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_docker(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
        io_dir = next(a for a in args if a.endswith(":/io:ro"))[: -len(":/io:ro")]
        nodes = [n for n in (pathlib.Path(io_dir) / "nodes.txt").read_text().splitlines() if n]
        calls.append(nodes)
        absent = [n for n in nodes if n in missing]
        if absent:
            text = "".join(f"ERROR: not found: /testbed/{n}\n(no match in any of [<Module x>])\n\n"
                           for n in absent) + "no tests ran in 0.10s\n"  # fmt: skip
            return subprocess.CompletedProcess(args, 123, stdout=text.encode(), stderr=b"")
        text = "".join(f"PASSED {n}\n" for n in nodes)
        return subprocess.CompletedProcess(args, 0, stdout=text.encode(), stderr=b"")

    monkeypatch.setattr(docker_env, "docker", fake_docker)
    return calls


DOC = "tests/test_docs.py::test_docstrings_examples[pydantic/types.py:2042-2063]"


def test_a_node_that_does_not_exist_reads_as_not_passing_not_as_an_empty_run(monkeypatch) -> None:  # noqa: ANN001
    calls = _fake_missing(monkeypatch, {DOC})
    out = docker_env.pytest("tag", "", ["t.py::a", DOC, "t.py::b"], keep_collecting=True)
    assert out == {"t.py::a": "PASSED", "t.py::b": "PASSED"}
    assert calls[-1] == ["t.py::a", "t.py::b"]


def test_every_listed_node_missing_is_nothing_passing(monkeypatch) -> None:  # noqa: ANN001
    _fake_missing(monkeypatch, {DOC})
    assert docker_env.pytest("tag", "", [DOC], keep_collecting=True) == {}


def test_held_out_chains_keep_the_sealed_behaviour_on_a_missing_node(monkeypatch) -> None:  # noqa: ANN001
    calls = _fake_missing(monkeypatch, {DOC})
    with pytest.raises(RuntimeError, match="gave no results"):
        docker_env.pytest("tag", "", ["t.py::a", DOC])
    assert len(calls) == 1
