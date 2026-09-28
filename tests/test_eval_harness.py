"""The private evaluation harness: a clear exit when it is not installed, the module when it is."""

import sys
import types

import pytest

from sanchopanza.eval import harness


def test_a_missing_harness_exits_saying_what_replays_without_it(monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_EVAL_HARNESS", "no_such_harness_module_xyz")
    with pytest.raises(SystemExit) as stop:
        harness.load()
    assert "not distributed" in str(stop.value) and "replay" in str(stop.value)


def test_an_installed_harness_is_returned(monkeypatch):
    fake = types.ModuleType("fake_eval_harness")
    monkeypatch.setitem(sys.modules, "fake_eval_harness", fake)
    monkeypatch.setenv("SANCHOPANZA_EVAL_HARNESS", "fake_eval_harness")
    assert harness.load() is fake
