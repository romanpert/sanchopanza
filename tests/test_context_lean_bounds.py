"""Bounds and guards on the lean configuration: the index and the free cut stay linear on a
huge result, `install` leaves a `.mcp.json` that holds nothing of ours alone, a bad
`ARRIVAL_FREE_CHARS` cannot empty results, and a failed compaction blanks only its own file.
No provider, no network."""

from __future__ import annotations

import json
import time
from pathlib import Path

from sanchopanza import cli
from sanchopanza.context import arrival
from sanchopanza.context.index import index_of
from sanchopanza.harness import autopilot, install
from tests.context_helpers import write_transcript

# --- index_of is linear -----------------------------------------------------------------------


def test_index_of_a_one_megabyte_log_returns_fast_and_bounded():
    lines = []
    size = 0
    i = 0
    while size < 1_000_000:
        line = f"id-A{i}X status=ok{i}\n"
        lines.append(line)
        size += len(line)
        i += 1
    log = "".join(lines)
    start = time.perf_counter()
    index = index_of(log)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"index_of took {elapsed:.2f}s on {len(log):,} chars"
    assert index.startswith("id-A0X; status=ok0; id-A1X")
    assert len(index) <= 240


def test_the_failing_line_at_the_end_of_a_huge_log_still_comes_first():
    noise = "".join(f"id-A{i}X status=ok{i}\n" for i in range(40_000))
    log = noise + "CHECK BLD-4471 failed: expected 3.25 got 3.40\n"
    start = time.perf_counter()
    index = index_of(log)
    assert time.perf_counter() - start < 2.0
    assert index.startswith("CHECK BLD-4471 failed: expected 3.25 got 3.40")


# --- the free cut is linear -------------------------------------------------------------------


def test_line_blocks_of_200k_lines_is_fast_and_immutable():
    text = "".join(f"line {i} ok\n" for i in range(200_000))
    start = time.perf_counter()
    found = arrival._line_blocks(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"_line_blocks took {elapsed:.2f}s"
    assert isinstance(found, tuple) and len(found) == 200_000
    assert found[-1].of(text) == "line 199999 ok\n"
    assert found[1].start == len("line 0 ok\n")


# --- ARRIVAL_FREE_CHARS has a floor -----------------------------------------------------------


def test_free_chars_below_the_floor_falls_back_to_the_default():
    for bad in ("0", "-5", "999", "nan", "inf", "junk"):
        config = autopilot.config_from_env({"SANCHOPANZA_ARRIVAL_FREE_CHARS": bad})
        assert config.free_target == autopilot.FREE_CHARS_DEFAULT, bad
    kept = autopilot.config_from_env({"SANCHOPANZA_ARRIVAL_FREE_CHARS": "1000"})
    assert kept.free_target == 1_000


# --- install and .mcp.json --------------------------------------------------------------------


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    return settings, tmp_path / "proj" / ".mcp.json", tmp_path / "plugin"


def test_a_malformed_mcp_json_does_not_fail_a_plain_install(tmp_path, capsys):
    settings, mcp_file, plugin = _paths(tmp_path)
    mcp_file.parent.mkdir(parents=True)
    mcp_file.write_text("{ not json", encoding="utf-8")
    args = ["install", "--autopilot", "--path", str(settings), "--plugin-dir", str(plugin)]
    assert cli.main([*args, "--write"]) == 0
    assert mcp_file.read_text(encoding="utf-8") == "{ not json"
    assert settings.is_file()
    assert ".mcp.json" not in capsys.readouterr().out


def test_a_plain_install_does_not_rewrite_an_mcp_json_without_our_entry(tmp_path):
    settings, mcp_file, plugin = _paths(tmp_path)
    mcp_file.parent.mkdir(parents=True)
    original = '{"mcpServers":{"other":{"command":"x"}}}'
    mcp_file.write_text(original, encoding="utf-8")
    args = ["install", "--autopilot", "--no-find", "--path", str(settings), "--plugin-dir",
            str(plugin)]  # fmt: skip
    assert cli.main([*args, "--write"]) == 0
    assert mcp_file.read_text(encoding="utf-8") == original


def test_lean_writes_the_settings_then_the_mcp_json(tmp_path, monkeypatch, capsys):
    settings, mcp_file, plugin = _paths(tmp_path)
    order: list[str] = []
    real_apply, real_write = install.apply, install.write_mcp_json

    def apply(planned):
        order.append("settings")
        return real_apply(planned)

    def write_mcp_json(path, content):
        order.append("mcp")
        real_write(path, content)

    monkeypatch.setattr(install, "apply", apply)
    monkeypatch.setattr(install, "write_mcp_json", write_mcp_json)
    args = ["install", "--lean", "--path", str(settings), "--plugin-dir", str(plugin), "--write"]
    assert cli.main(args) == 0
    assert order == ["settings", "mcp"]
    assert "sanchopanza-archive" in json.loads(mcp_file.read_text("utf-8"))["mcpServers"]


def test_lean_leaves_no_mcp_json_when_the_settings_could_not_be_written(tmp_path, monkeypatch):
    settings, mcp_file, plugin = _paths(tmp_path)

    def failing_apply(_planned):
        raise OSError("disk full")

    monkeypatch.setattr(install, "apply", failing_apply)
    args = ["install", "--lean", "--path", str(settings), "--plugin-dir", str(plugin), "--write"]
    assert cli.main(args) == 2
    assert not mcp_file.exists()


def test_lean_refuses_a_malformed_mcp_json_before_writing_anything(tmp_path):
    settings, mcp_file, plugin = _paths(tmp_path)
    mcp_file.parent.mkdir(parents=True)
    mcp_file.write_text("[1, 2]", encoding="utf-8")
    args = ["install", "--lean", "--path", str(settings), "--plugin-dir", str(plugin), "--write"]
    assert cli.main(args) == 2
    assert mcp_file.read_text(encoding="utf-8") == "[1, 2]"
    assert not settings.exists()


# --- a failed compaction blanks only its own --out file ---------------------------------------


def _failed_compaction(tmp_path: Path, out: Path) -> int:
    path = write_transcript(tmp_path / "abc.jsonl")
    args = ["compact", "--transcript", str(path), "--provider", "null", "--session", "s"]
    return cli.main([*args, "--out", str(out), "--min-reduction", "0.99"])


def test_a_failed_compaction_leaves_a_foreign_out_file_alone(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    foreign = {
        "not json at all": "notes I keep here",
        "a list": "[1, 2, 3]",
        "another object": '{"settings": true}',
    }
    for name, content in foreign.items():
        out = tmp_path / f"{name}.json"
        out.write_text(content, encoding="utf-8")
        assert _failed_compaction(tmp_path, out) == cli.COMPACT_BELOW_MINIMUM
        assert out.read_text(encoding="utf-8") == content, name
    capsys.readouterr()


def test_a_failed_compaction_still_blanks_its_own_out_file(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "compact-s.json"
    out.write_text(json.dumps({"messages": [], "report": {}}), encoding="utf-8")
    assert _failed_compaction(tmp_path, out) == cli.COMPACT_BELOW_MINIMUM
    assert out.read_text(encoding="utf-8") == "{}"
    capsys.readouterr()
