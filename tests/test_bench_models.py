"""The benchmarks that pinned jev-1.13.0 by hand follow SANCHOPANZA_JEV_MODEL, and another
version's recordings go to their own directory. No call is made: only paths and names."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

import pytest

from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(relative: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks" / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SANCHOPANZA_JEV_MODEL", "SANCHO_JEV_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "not-used")


def test_fifth_batch_stays_on_1_13_and_its_files_by_default() -> None:
    fb = load("fifth_batch.py", "_fb_default")
    assert fb.MODEL == "jev-1.13.0"
    assert fb.RECORDING == ROOT / "fixtures" / "fifth-batch" / "recording.jsonl"
    assert fb.ANALYSIS == fb.OUT / "analysis.json"


def test_fifth_batch_follows_the_environment_into_its_own_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.14.0")
    fb = load("fifth_batch.py", "_fb_114")
    assert fb.MODEL == "jev-1.14.0"
    assert fb.RECORDING == ROOT / "fixtures" / "fifth-batch" / "jev114" / "recording.jsonl"
    assert fb.ANALYSIS == fb.OUT / "jev114" / "analysis.json"


def test_context_run_pins_its_model_unless_told(monkeypatch: pytest.MonkeyPatch) -> None:
    run = load("context/run.py", "_context_run")
    assert run.jev_model() == run.PINNED_MODEL == "jev-1.13.0"
    replay = run.decider_for("replay", "", "sanchopanza")
    assert isinstance(replay, RecordedDecider)
    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.14.0")
    assert run.jev_model() == "jev-1.14.0"
    live = run.decider_for("live", "", "sanchopanza")
    assert isinstance(live, RecordingDecider)
    assert live._path == run.RECORDINGS / "jev114" / "sanchopanza.jsonl"
    assert live._inner.model == "jev-1.14.0"


def test_memory_gate_estimates_with_the_model_it_would_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks" / "memory_gate"))
    run = load("memory_gate/run.py", "_memory_gate_run")
    assert run._model() == "jev-1.13.0"
    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.14.0")
    assert run._model() == "jev-1.14.0"
