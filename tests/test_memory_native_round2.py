"""The memory bridge, second review (2026-10-16): the reviewer's probes as tests. No test here
calls a paid provider."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from sanchopanza import cli
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_native as mn
from sanchopanza.harness import memory_native_index as mni

from .test_memory_native import (  # noqa: F401 - _clean is the shared autouse fixture
    _clean,
    _step_one,
    _transcript,
    event,
    native,
    record,
)

EMO = "\U0001f600"


# A junction is made with cmd.exe: the test cannot even start elsewhere.
WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")


def _refresh(tmp_path: Path, records: list | None = None, **extra: object) -> dict:
    return mn.refresh(native(tmp_path), records or [record()], session="s1",
                      store=tmp_path / "store", **extra)  # fmt: skip


def _read(tmp_path: Path, path: Path, extra_input: dict | None = None, **extra: object) -> dict:
    return event(tmp_path, "PostToolUse", "s2", tool_name="Read",
                 tool_input={"file_path": str(path), **(extra_input or {})},
                 tool_response={"content": "x"}, **extra)  # fmt: skip


def _after_session_one(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "off")
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    return mh.store_for(event(tmp_path, session="s2"))


def _writable(folder: Path) -> None:
    for path in folder.iterdir():
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


# ---- HIGH ---------------------------------------------------------------------------------------


def test_high1_a_refused_replace_rebuilds_from_the_fresh_index(tmp_path: Path, monkeypatch) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    index = folder / "MEMORY.md"
    index.write_bytes(b"- [A](a.md) - one\n")
    real, calls = os.replace, {"n": 0}

    def busy_then_free(src: str, dst: str) -> None:
        calls["n"] += str(dst).endswith("MEMORY.md")
        if str(dst).endswith("MEMORY.md") and calls["n"] == 1:  # Claude Code holds it, writes
            with open(dst, "ab") as handle:
                handle.write(b"- [New](new.md) - saved by Claude Code\n")
            raise PermissionError(13, "busy")
        real(src, dst)

    monkeypatch.setattr(mni.os, "replace", busy_then_free)
    assert _refresh(tmp_path)["native"] == "written"
    text = index.read_bytes().decode("utf-8")
    assert "saved by Claude Code" in text and "- [A](a.md) - one" in text
    assert sum(1 for n in text.split("\n") if mni.is_ours(n)) == 1


def test_high2_a_subagent_s_read_marks_nothing(tmp_path: Path, monkeypatch) -> None:
    store = _after_session_one(tmp_path, monkeypatch)
    mh.handle(_read(tmp_path, native(tmp_path) / mni.NOTE, agent_id="sub-1"))
    assert mh.shown_since_compaction(store, "s2", 0) == frozenset()


# ---- MEDIUM -------------------------------------------------------------------------------------


@pytest.mark.parametrize("window", [{"limit": 3}, {"offset": 5}, {"offset": 5, "limit": 999}])
def test_medium1_a_partial_read_marks_nothing(tmp_path: Path, monkeypatch, window: dict) -> None:
    store = _after_session_one(tmp_path, monkeypatch)
    mh.handle(_read(tmp_path, native(tmp_path) / mni.NOTE, window))
    assert mh.shown_since_compaction(store, "s2", 0) == frozenset()


def test_medium1_a_read_whose_limit_covers_the_note_counts(tmp_path: Path, monkeypatch) -> None:
    store = _after_session_one(tmp_path, monkeypatch)
    mh.handle(_read(tmp_path, native(tmp_path) / mni.NOTE, {"offset": 1, "limit": 2000}))
    assert mh.shown_since_compaction(store, "s2", 0) == {"s1-001"}


def test_medium2_our_line_never_pushes_a_person_s_line_out_of_what_loads(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    _t, short_line, _k = mn.compose([record(request="tiny")])
    users = [f"- [U{i}](u{i}.md) — " + EMO * 200 for i in range(60)]
    body = "\n".join([users[0], short_line, *users[1:]]) + "\n"
    while mni._units(body.strip()) > 24_990:
        users.pop()
        body = "\n".join([users[0], short_line, *users[1:]]) + "\n"
    body = body[:-1] + "x" * (24_995 - mni._units(body.strip())) + "\n"
    (folder / "MEMORY.md").write_bytes(body.encode("utf-8"))
    before = mni.loaded(body)
    _refresh(tmp_path, [record(request="L" * 400)])
    after = mni.loaded((folder / "MEMORY.md").read_bytes().decode("utf-8"))
    lost = [u.split(" —")[0] for u in users
            if u.split(" —")[0] in before and u.split(" —")[0] not in after]  # fmt: skip
    assert not lost


def test_medium3_a_read_only_index_is_left_alone_and_leaves_no_temporary(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    index = folder / "MEMORY.md"
    index.write_bytes(b"- [A](a.md) - x\n")
    os.chmod(index, stat.S_IREAD)
    try:
        assert _refresh(tmp_path)["native"] == "index read-only"
        assert sorted(p.name for p in folder.iterdir()) == ["MEMORY.md"]
        _transcript(tmp_path, "s1", _step_one())
        mh.handle(event(tmp_path))
        assert sorted(p.name for p in folder.iterdir()) == ["MEMORY.md"]
    finally:
        _writable(folder)


def test_medium3_going_off_with_a_read_only_index_still_installs(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    path = config / "settings.json"
    assert cli.main(["install", "--path", str(path), "--memory-native", "--write"]) == 0
    _refresh(tmp_path)
    index = native(tmp_path) / "MEMORY.md"
    before = index.read_bytes()
    os.chmod(index, stat.S_IREAD)
    try:
        assert cli.main(["install", "--path", str(path), "--write"]) == 0
        assert index.read_bytes() == before and (native(tmp_path) / mni.NOTE).exists()
        assert not [p for p in native(tmp_path).iterdir() if p.name.endswith(".tmp")]
    finally:
        _writable(native(tmp_path))


def test_medium4_memory_formation_with_no_memory_folder_says_so(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from types import SimpleNamespace

    from sanchopanza.context import formation

    monkeypatch.setattr("sanchopanza.harness.memory_gate.memory_dir_for", lambda *a, **k: None)
    monkeypatch.delenv("SANCHOPANZA_MEMORY_DIR", raising=False)

    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("formation ran without a memory folder")

    monkeypatch.setattr(formation, "form", never)
    assert cli._formation_dir() is None
    args = SimpleNamespace(form_memories=True)
    cli._after_compaction(args, None, [], SimpleNamespace(steps=[]), tmp_path / "a" / "archive",
                          "s")  # fmt: skip
    assert "memory formation skipped" in capsys.readouterr().err


def test_medium4_no_memory_after_the_flag_sweeps_our_note(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    path = config / "settings.json"
    assert cli.main(["install", "--path", str(path), "--memory-native", "--write"]) == 0
    _refresh(tmp_path)
    assert cli.main(["install", "--path", str(path), "--no-memory", "--write"]) == 0
    assert not (native(tmp_path) / mni.NOTE).exists()
    assert mni.LINE_HEAD not in (native(tmp_path) / "MEMORY.md").read_text("utf-8")


# ---- LOW ----------------------------------------------------------------------------------------


def test_low_a_a_bom_before_our_line_is_kept_and_our_line_still_ours(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    _refresh(tmp_path)
    index = folder / "MEMORY.md"
    index.write_bytes(b"\xef\xbb\xbf" + index.read_bytes())
    _refresh(tmp_path, [record(request="A new plan entirely about ship_all")])
    text = index.read_bytes().decode("utf-8")
    assert text.startswith("\ufeff") and text.count(mni.LINE_HEAD) == 1
    mn.uninstall(tmp_path / "config")
    assert index.read_bytes().decode("utf-8") == "\ufeff"


def test_low_b_covered_with_an_unreadable_index_keeps_the_note(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    assert _refresh(tmp_path)["native"] == "written"
    index = folder / "MEMORY.md"
    index.write_bytes(index.read_bytes() + "- [Caf\xe9](c.md) — x\n".encode("cp1252"))
    (folder / "plan.md").write_text("ship_all(orders, carrier) carrier client label_for labels "
                                    "step 2 shipping today orders rejects requests app/labels.py",
                                    "utf-8")  # fmt: skip
    _refresh(tmp_path, written=frozenset({"plan.md"}))
    assert (folder / mni.NOTE).exists()


@WINDOWS_ONLY
def test_low_c_a_junction_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "shared"
    target.mkdir()
    folder = native(tmp_path)
    folder.parent.mkdir(parents=True)
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(folder), str(target)],
                          capture_output=True, check=False)  # fmt: skip
    if done.returncode != 0:
        pytest.skip("no junction on this machine")
    assert _refresh(tmp_path)["native"] == "link refused"
    assert list(target.iterdir()) == []


def test_low_c_a_linked_project_folder_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    (target / "memory").mkdir(parents=True)
    project = native(tmp_path).parent
    project.parent.mkdir(parents=True)
    try:
        os.symlink(target, project, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot make a symbolic link")
    assert _refresh(tmp_path)["native"] == "link refused"


def test_low_g_a_record_whose_changed_list_was_cut_is_not_whole() -> None:
    many = tuple(f"app/module_{i:03d}.py" for i in range(40))
    _text, _line, keys = mn.compose([record(changed=many)])
    assert keys == []


@WINDOWS_ONLY
def test_low_c_a_junction_is_seen_without_path_is_junction(tmp_path: Path, monkeypatch) -> None:
    target, junction = tmp_path / "target", tmp_path / "junction"
    target.mkdir()
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                          capture_output=True, check=False)  # fmt: skip
    if done.returncode != 0:
        pytest.skip("no junction on this machine")
    monkeypatch.delattr(Path, "is_junction", raising=False)  # Python 3.11 has none
    assert mni.linked(junction)
    assert not mni.linked(target) and not mni.linked(tmp_path / "missing")


@pytest.mark.parametrize(("text", "window", "whole"), [
    ("a\nb\n", {"limit": 2}, True),
    ("a\nb\n", {"limit": 1}, False),
    ("a\nb", {"limit": 2}, True),
    ("a\nb", {"limit": 1}, False),
    ("a\nb\n", {"offset": -1}, False),
    ("a\nb\n", {"offset": 1}, True),
    ("a\nb\n", {}, True),
])  # fmt: skip
def test_low_whole_read_counts_lines_exactly(text: str, window: dict, whole: bool) -> None:
    assert mn._whole_read(window, text) is whole
