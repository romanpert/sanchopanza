"""The rename from `sancho` to `sanchopanza` does not break a setup made before it.

Every `SANCHOPANZA_*` variable falls back to its old `SANCHO_*` spelling, the new one wins
when both are set, old directories are used only when the new ones do not exist, and
`sanchopanza install` migrates old variables in a settings file instead of doubling them.
"""

from __future__ import annotations

from sanchopanza import _env
from sanchopanza.harness import HarnessConfig
from sanchopanza.harness.claude_code import config_from_env
from sanchopanza.harness.install import merge


def test_the_new_name_is_read():
    assert _env.get("PROVIDER", env={"SANCHOPANZA_PROVIDER": "jev"}) == "jev"


def test_the_old_name_is_still_read():
    assert _env.get("PROVIDER", env={"SANCHO_PROVIDER": "null"}) == "null"


def test_the_new_name_wins_over_the_old():
    env = {"SANCHO_PROVIDER": "null", "SANCHOPANZA_PROVIDER": "jev"}
    assert _env.get("PROVIDER", env=env) == "jev"


def test_neither_name_gives_the_default():
    assert _env.get("PROVIDER", "x", env={}) == "x"


def test_prefixed_variables_merge_both_spellings():
    env = {"SANCHO_T_ACT": "0.1", "SANCHO_T_INJECTION": "0.2", "SANCHOPANZA_T_ACT": "0.9"}
    assert _env.with_prefix("T_", env) == {"ACT": "0.9", "INJECTION": "0.2"}


def test_a_hook_configured_with_old_names_still_scans():
    config = config_from_env({"SANCHO_SCAN_CONTENT": "1", "SANCHO_CONTENT_TOOLS": "Read"})
    assert config.scan_content is True and config.content_tools == frozenset({"Read"})


def test_directories_prefer_the_new_one(tmp_path, monkeypatch):
    monkeypatch.setattr(_env.Path, "home", lambda: tmp_path)
    assert _env.home_dir() == tmp_path / ".sanchopanza"
    (tmp_path / ".sancho").mkdir()
    assert _env.home_dir() == tmp_path / ".sancho"
    (tmp_path / ".sanchopanza").mkdir()
    assert _env.home_dir() == tmp_path / ".sanchopanza"
    assert _env.cache_dir() == tmp_path / ".cache" / "sanchopanza"
    (tmp_path / ".cache" / "sancho").mkdir(parents=True)
    assert _env.cache_dir() == tmp_path / ".cache" / "sancho"


def test_install_migrates_old_variables_and_keeps_other_keys():
    current = {"env": {"SANCHO_PROVIDER": "null", "SANCHO_SCAN_CONTENT": "1", "OTHER": "x"}}
    merged, _ = merge(current, HarnessConfig(scan_content=True), provider="jev")
    assert merged["env"] == {
        "OTHER": "x",
        "SANCHOPANZA_PROVIDER": "jev",
        "SANCHOPANZA_SCAN_CONTENT": "1",
    }


def test_install_without_scanning_removes_old_scan_variables():
    current = {"env": {"SANCHO_SCAN_CONTENT": "1", "SANCHO_CHECK_DONE": "1"}}
    merged, _ = merge(current, HarnessConfig())
    assert merged["env"] == {}
