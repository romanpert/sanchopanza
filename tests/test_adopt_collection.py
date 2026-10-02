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
