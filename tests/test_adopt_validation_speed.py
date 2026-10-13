"""Why dvc-long60-1's validation never finished a round, and what changed (2026-10-13).

- One hung test held a whole pytest run to its 3,600 s timeout, and that run came back with no
  results. Validation runs now pass pytest-timeout's `--timeout` per test, only where the image has
  the plugin (dvc has it; conan, pydantic and moto do not, so their runs are unchanged).
- `perbug.check` ran one pytest run per broken test inside an `any`, for every bug: with hundreds
  of tests broken by the fixes that is hundreds of runs per bug. Now it is one run per bug.
- A reserve chain can be validated when it is named (promoted), never by `all`.
No Docker, no network, no model."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
from types import ModuleType
from typing import Any

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"
sys.path.append(str(ADOPT))


def _load(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ADOPT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


docker_env = _load("adopt_docker_env_speed", "docker_env.py")
import perbug  # noqa: E402


def _bug(i: int) -> dict[str, Any]:
    path = f"pkg/m{i}.py"
    patch = (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
             f"@@ -10,3 +10,3 @@\n a\n-b{i}\n+c{i}\n d\n")  # fmt: skip
    return {"instance_id": f"o__r.abc.pr_{i}", "patch": patch, "FAIL_TO_PASS": [f"t.py::f{i}"],
            "PASS_TO_PASS": ["t.py::g1", "t.py::g2", "t.py::g3"], "source": "pr_mirror"}  # fmt: skip


# ---- the per-test timeout ------------------------------------------------------------------------


def test_no_per_test_timeout_unless_asked() -> None:
    assert docker_env.per_test(None) == ""
    assert docker_env.per_test(0) == ""


def test_the_per_test_timeout_is_added_only_where_the_plugin_imports() -> None:
    flag = docker_env.per_test(300)
    assert "import pytest_timeout" in flag and "--timeout=300" in flag
    assert "&&" in flag  # the option only when the import succeeds


def _scripts(monkeypatch, **kwargs: Any) -> list[str]:  # noqa: ANN001
    seen: list[str] = []

    def fake_docker(*args: str, **_k: object) -> subprocess.CompletedProcess:
        seen.append(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout=b"PASSED t.py::a\n", stderr=b"")

    monkeypatch.setattr(docker_env, "docker", fake_docker)
    docker_env.pytest("tag", "", ["t.py::a"], **kwargs)
    return seen


def test_a_validation_run_carries_the_timeout_and_a_grade_run_does_not(monkeypatch) -> None:  # noqa: ANN001
    assert all("--timeout" not in s for s in _scripts(monkeypatch, keep_collecting=True))
    asked = _scripts(monkeypatch, keep_collecting=True, test_timeout=300)
    assert asked and all("--timeout=300" in s for s in asked)
    # before the node list and the report options: one pytest command line
    assert asked[0].index("--timeout=300") < asked[0].index("-rA")


def test_validation_asks_for_the_per_test_timeout(monkeypatch) -> None:  # noqa: ANN001
    kwargs: list[dict[str, Any]] = []

    def fake(tag, patch, nodes, **k):  # noqa: ANN001, ANN202
        kwargs.append(k)
        return {n: "FAILED" for n in nodes}

    monkeypatch.setattr(perbug.docker_env, "pytest", fake)
    monkeypatch.setattr(perbug.masking, "culprits", lambda *a, **k: [])
    perbug.check("tag", [_bug(1), _bug(2)])
    assert kwargs and all(k.get("test_timeout") == docker_env.PER_TEST_TIMEOUT for k in kwargs)


# ---- one run per bug for the tests the fixes break -----------------------------------------------


def test_tests_broken_by_the_fixes_cost_one_run_per_bug(monkeypatch) -> None:  # noqa: ANN001
    bugs = [_bug(i) for i in range(1, 5)]
    broken = ["t.py::g1", "t.py::g2", "t.py::g3"]
    runs: list[list[str]] = []

    def fake(tag, patch, nodes, reverse=False, **_k):  # noqa: ANN001, ANN202
        runs.append(list(nodes))
        if not reverse:  # every bug in: each F2P fails, the P2P pass
            return {n: ("PASSED" if n.startswith("t.py::g") else "FAILED") for n in nodes}
        if patch == perbug.joined(bugs):  # every bug undone: the F2P pass, the P2P break
            return {n: ("FAILED" if n.startswith("t.py::g") else "PASSED") for n in nodes}
        fixed = int(patch.split("+c", 1)[1][0])
        out = {n: "FAILED" for n in nodes}
        out.update({f"t.py::f{fixed}": "PASSED"} if f"t.py::f{fixed}" in nodes else {})
        if nodes == broken:  # only bug 2's fix breaks them
            return {n: ("FAILED" if fixed == 2 else "PASSED") for n in nodes}
        return out

    monkeypatch.setattr(perbug.docker_env, "pytest", fake)
    monkeypatch.setattr(perbug.masking, "culprits", lambda *a, **k: [])
    result = perbug.check("tag", bugs)
    assert sum(1 for r in runs if r == broken) == len(bugs)
    assert result["drop"] == {1: "undoing it breaks a test that passed"}


# ---- a reserve chain only when named -------------------------------------------------------------


def _main(monkeypatch, wanted: str) -> list[str]:  # noqa: ANN001
    # loaded here, not at collection: validate imports adopt's `run`, another suite has its own
    validate = _load("adopt_validate_speed", "validate.py")
    chains = [{"chain": "a-long60-1", "split": "dev", "grader": "per_bug"},
              {"chain": "b-long60-2", "split": "reserve", "grader": "per_bug"}]  # fmt: skip
    isolated: list[str] = []

    def isolate(chain):  # noqa: ANN001, ANN202
        isolated.append(chain["chain"])
        return {"chain": chain["chain"], "valid": True, "history": [], "seconds": 0}

    monkeypatch.setattr(validate.run, "sealed", lambda: False)
    monkeypatch.setattr(validate, "full", lambda: [])
    monkeypatch.setattr(validate.related, "full", lambda: [])
    monkeypatch.setattr(validate.long, "full", lambda: [])
    monkeypatch.setattr(validate.long, "full60", lambda: chains)
    monkeypatch.setattr(validate.long, "resumed", lambda c: c)
    monkeypatch.setattr(validate.perbug, "isolate", isolate)
    monkeypatch.setattr(validate, "save", lambda result: None)
    monkeypatch.setattr(sys, "argv", ["validate.py", wanted])
    validate.main()
    return isolated


def test_a_named_reserve_chain_is_validated(monkeypatch) -> None:  # noqa: ANN001
    assert _main(monkeypatch, "b-long60-2") == ["b-long60-2"]


def test_all_never_takes_a_reserve_chain(monkeypatch) -> None:  # noqa: ANN001
    assert _main(monkeypatch, "all") == ["a-long60-1"]
