"""`_atomic_write` on a busy file (Windows): it waits for the file instead of leaving debris.

2026-10-06, h2h: an install hit a `settings.json` another process held open; `os.replace` failed,
the cleanup's `os.unlink` failed too, and a `.settings.json.*.tmp` stayed in the config folder
(the h2h runner removed it by hand, e173100). A busy file on Windows is a `PermissionError` that
clears within moments, so both steps are retried a few times before giving up.
"""

from __future__ import annotations

import os

import pytest

from sanchopanza.harness import install


def _flaky(real, fails: int):
    calls = {"n": 0}

    def call(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= fails:
            raise PermissionError(32, "The process cannot access the file")
        return real(*args, **kwargs)

    return call, calls


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(install, "BUSY_WAIT_S", 0.0)


def test_a_replace_that_meets_a_busy_file_is_retried(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    replace, calls = _flaky(os.replace, fails=2)
    monkeypatch.setattr(install.os, "replace", replace)
    install._atomic_write(target, b'{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
    assert calls["n"] == 3
    assert not list(tmp_path.glob(".settings.json.*.tmp"))


def test_a_file_busy_past_every_try_raises_and_leaves_no_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    replace, _ = _flaky(os.replace, fails=100)
    unlink, unlinks = _flaky(os.unlink, fails=2)
    monkeypatch.setattr(install.os, "replace", replace)
    monkeypatch.setattr(install.os, "unlink", unlink)
    with pytest.raises(PermissionError):
        install._atomic_write(target, b'{"a": 1}')
    assert target.read_text(encoding="utf-8") == "{}"
    assert unlinks["n"] == 3
    assert not list(tmp_path.glob(".settings.json.*.tmp"))


def test_an_error_that_is_not_a_busy_file_is_not_retried(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    calls = {"n": 0}

    def broken(*args, **kwargs):
        calls["n"] += 1
        raise IsADirectoryError(21, "Is a directory")

    monkeypatch.setattr(install.os, "replace", broken)
    with pytest.raises(IsADirectoryError):
        install._atomic_write(target, b"{}")
    assert calls["n"] == 1
    assert not list(tmp_path.glob(".settings.json.*.tmp"))
