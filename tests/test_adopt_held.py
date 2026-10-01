"""What guards the held-out runs of the adoption study before and after the seal: the frozen
commit, model, caps and Claude Code version enforced in code; the cache entries the sealed
summary hashed; no second attempt of a crashed arm; API errors not counted as requests; a
singles harness failure not counted as a loss. No Docker, no network, no model."""

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
    """Drop the bench's modules registered under bare names (`run`, `docker_env`...): other
    benchmarks have modules of the same names and would import these instead."""
    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None) or ""
        if not name.startswith("adopt_") and pathlib.Path(where).parent == ADOPT:
            del sys.modules[name]


run = _load("adopt_run_held", "run.py")
singles_run = _load("adopt_singles_run_held", "singles_run.py")
_purge()


def _ready(monkeypatch: pytest.MonkeyPatch, commit: str = run.HELD_COMMIT) -> None:
    monkeypatch.setattr(run, "sealed", lambda: True)
    monkeypatch.setattr(run, "frozen_stamp", lambda: {"commit": commit})
    monkeypatch.setattr(run, "claude_version", lambda: run.CLAUDE_VERSION)


def test_held_out_settings_are_enforced_in_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _ready(monkeypatch)
    assert run.held_refusal("haiku", 1.5, 6.0) is None
    assert run.held_refusal(None, 1.5, 6.0) is None  # the default model is phase A's
    assert "haiku" in run.held_refusal("sonnet", 1.5, 6.0)
    assert "caps" in run.held_refusal("haiku", 4.5, 6.0)
    assert "caps" in run.held_refusal("haiku", 1.5, 15.0)
    monkeypatch.setattr(run, "claude_version", lambda: "2.2.0")
    assert "Claude Code" in run.held_refusal("haiku", 1.5, 6.0)
    _ready(monkeypatch, commit="94487923")  # another frozen copy
    assert "frozen" in run.held_refusal("haiku", 1.5, 6.0)
    monkeypatch.setattr(run, "sealed", lambda: False)
    assert "sealed" in run.held_refusal("haiku", 1.5, 6.0)


def test_a_cache_entry_the_summary_did_not_hash_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    chain = {"split": "held", "image": "i", "tag": "t", "bugs": [{"patch": "p"}]}
    digest = run.chain_digest(chain)
    monkeypatch.setattr(run, "summary_digest", lambda name: digest)
    assert run.stale_held({"c": chain}, ["c"]) == []
    changed = {**chain, "bugs": [{"patch": "q"}]}
    assert run.stale_held({"c": changed}, ["c"]) == ["c"]
    assert run.stale_held({"c": {**changed, "split": "dev"}}, ["c"]) == []  # dev is not sealed


def test_the_summary_holds_a_digest_for_every_held_out_chain() -> None:
    summary = json.loads((ADOPT / "chains-validated-summary.json").read_text(encoding="utf-8"))
    held = [n for n, c in summary.items() if c["valid"] and "long" not in n]
    assert held and all(len(summary[n].get("sha256") or "") == 64 for n in held)


def test_a_crashed_held_out_arm_is_not_run_again(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    (tmp_path / "runs" / "c" / "N").mkdir(parents=True)  # evidence, no row.json
    chain = {"chain": "c", "split": "held", "tag": "t", "bugs": []}
    with pytest.raises(RuntimeError, match="earlier attempt"):
        run.one_chain(chain, "N", "m", 1.0, tmp_path / "key")


def _stream(path: pathlib.Path, result: dict) -> pathlib.Path:
    rows = [{"type": "system", "subtype": "init", "session_id": "s"}, {"type": "result", **result}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def test_an_api_error_is_not_a_request_that_ran_but_a_cap_is(tmp_path: pathlib.Path) -> None:
    usage_limit = _stream(tmp_path / "a.jsonl", {"subtype": "success", "is_error": True,
                                                  "total_cost_usd": 0.01})  # fmt: skip
    capped = _stream(tmp_path / "b.jsonl", {"subtype": "error_max_budget_usd", "is_error": True,
                                             "total_cost_usd": 1.5})  # fmt: skip
    fine = _stream(tmp_path / "c.jsonl", {"subtype": "success", "is_error": False})
    assert run.facts(usage_limit)["api_error"] is True
    assert run.facts(capped)["api_error"] is False
    assert run.facts(fine)["api_error"] is False


def test_a_singles_harness_failure_writes_no_grade(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(singles_run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(singles_run, "SWE", tmp_path / "swe")
    for arm in singles_run.run.ARMS:
        folder = tmp_path / "runs" / "x__y-1" / arm
        folder.mkdir(parents=True)
        (folder / "final.patch").write_text("", encoding="utf-8")
    monkeypatch.setattr(singles_run.subprocess, "run", lambda *a, **k: None)  # no report.json
    assert singles_run.grade("x__y-1") == {}
    assert not list((tmp_path / "runs").rglob("grade.json"))


def test_a_held_out_single_does_not_start_over_earlier_sessions(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(singles_run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(singles_run.run, "WORK", tmp_path / "work")
    monkeypatch.setattr(singles_run.run, "CLAUDE_PROJECTS", tmp_path / "projects")
    old = singles_run.run.projects_dir(tmp_path / "work" / "x__y-1-N")
    old.mkdir(parents=True)
    (old / "s.jsonl").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="earlier sessions"):
        singles_run.one({"instance_id": "x__y-1"}, "N", "m", 1.0, tmp_path / "k", held=True)
    assert not (tmp_path / "runs" / "x__y-1").exists()


def test_child_sessions_never_update_claude_code() -> None:
    assert run.child_env("t", "b")["DISABLE_AUTOUPDATER"] == "1"
