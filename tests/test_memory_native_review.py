"""The memory bridge after its review (2026-10-16): never harm Claude Code's or the person's memory,
and give records again unless the session read the note. No test here calls a paid provider."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from sanchopanza import cli
from sanchopanza.harness import memory_gate as mg
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_native as mn
from sanchopanza.harness import memory_native_index as mni

from .test_memory_native import (  # noqa: F401 - _clean is the shared autouse fixture
    CWD,
    GH_TOKEN,
    _clean,
    _step_one,
    _transcript,
    event,
    native,
    record,
)

USER = "- [Mine](sanchopanza-next.md) — a line the person wrote that links the same name"


def _refresh(tmp_path: Path, records: list | None = None, **extra: object) -> dict:
    return mn.refresh(native(tmp_path), records or [record()], session="s1",
                      store=tmp_path / "store", **extra)  # fmt: skip


def _index(tmp_path: Path) -> str:
    return (native(tmp_path) / "MEMORY.md").read_bytes().decode("utf-8")


def _ours(text: str) -> list[str]:
    return [n for n in text.split("\n") if mni.is_ours(n)]


# ---- H1: only our exact line is ours ------------------------------------------------------------


def test_h1_a_person_s_line_linking_the_same_name_is_never_touched(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    (folder / "MEMORY.md").write_bytes((USER + "\n").encode("utf-8"))
    assert _refresh(tmp_path)["native"] == "written"
    lines = _index(tmp_path).split("\n")
    assert lines[0] == USER and len(_ours(_index(tmp_path))) == 1
    (folder / mni.NOTE).unlink()
    mn.uninstall(tmp_path / "config")
    assert _index(tmp_path) == USER + "\n"


def test_h1_l3_line_separators_and_crlf_are_kept_and_reused(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    original = "- [A](a.md) — one\u2028still one\x85line\r\n- [B](b.md) — two\r\n"
    (folder / "MEMORY.md").write_bytes(original.encode("utf-8"))
    _refresh(tmp_path)
    text = _index(tmp_path)
    assert text.startswith(original) and text.endswith('"\r\n')
    assert text.count("\n") == 3


# ---- H2: a note we did not write is not ours -----------------------------------------------------


def test_h2_a_note_of_that_name_we_did_not_write_is_left_alone(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    (folder / mni.NOTE).write_text("---\nname: sanchopanza-next\n---\nThe person's own.", "utf-8")
    assert _refresh(tmp_path)["native"] == "name taken"
    assert (folder / mni.NOTE).read_text(encoding="utf-8").endswith("The person's own.")
    assert not (folder / "MEMORY.md").exists()
    assert mn.uninstall(tmp_path / "config") == []
    assert (folder / mni.NOTE).exists()


def test_h2_our_note_carries_its_owner_mark() -> None:
    text, _line, _keys = mn.compose([record()])
    assert mni.is_owned_note(text) and "  owner: sanchopanza\n" in text.split("---")[1]


# ---- H3: a writer in the window loses nothing ---------------------------------------------------


def test_h3_a_line_added_while_we_write_is_kept(tmp_path: Path, monkeypatch) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    (folder / "MEMORY.md").write_text("- [A](a.md) — one\n", encoding="utf-8")
    calls = {"n": 0}

    def writer(path: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # Claude Code saves a memory between our read and our swap
            path.write_text(path.read_text("utf-8") + "- [New](new.md) — CC\n", "utf-8")

    monkeypatch.setattr(mni, "before_swap", writer)
    assert _refresh(tmp_path)["native"] == "written"
    text = _index(tmp_path)
    assert "- [New](new.md) — CC" in text and "- [A](a.md) — one" in text
    assert len(_ours(text)) == 1


def test_h3_an_index_that_keeps_changing_is_given_up_on(tmp_path: Path, monkeypatch) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    (folder / "MEMORY.md").write_text("- [A](a.md) — one\n", encoding="utf-8")

    def writer(path: Path) -> None:
        path.write_text(path.read_text("utf-8") + f"- [X](x{time.time_ns()}.md) — x\n", "utf-8")

    monkeypatch.setattr(mni, "before_swap", writer)
    assert _refresh(tmp_path)["native"] == "index busy"
    text = _index(tmp_path)
    assert not _ours(text) and text.count("- [X]") == 2


# ---- H4: only what the note holds whole counts ---------------------------------------------------


def test_h4_the_newest_record_is_kept_whole_and_only_whole_ones_count() -> None:
    old = record(1, request="Old request. " + "x" * 5000, changed=("app/a.py",))
    mid = record(2, request="Middle request.", changed=("app/b.py",))
    new = record(3, request="Newest request: ship_all next.", changed=("app/c.py",))
    text, _line, keys = mn.compose([old, mid, new])
    assert "Newest request: ship_all next." in text and "Middle request." in text
    assert len(text) <= mn.FILE_CHARS
    assert keys == ["s1-002", "s1-003"]


# ---- H5: no dedupe until the session read the note ----------------------------------------------


def _session_two(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "every")
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    mh.handle(event(tmp_path, "SessionStart", "s2", source="startup"))
    out = mh.handle(event(tmp_path, "UserPromptSubmit", "s2",
                          prompt="Let's continue with ship_all in app/labels.py"))  # fmt: skip
    return out["hookSpecificOutput"]["additionalContext"] if out else ""


def test_h5_the_prompt_still_gets_the_record_with_the_bridge_on(tmp_path, monkeypatch) -> None:
    assert "session s1" in _session_two(tmp_path, monkeypatch)


def _read(tmp_path: Path, path: Path) -> dict:
    return event(tmp_path, "PostToolUse", "s2", tool_name="Read",
                 tool_input={"file_path": str(path)}, tool_response={"content": "x"})  # fmt: skip


def test_h5_only_a_read_of_our_note_marks_its_records_given(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "off")
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    store = mh.store_for(event(tmp_path, session="s2"))
    mh.handle(_read(tmp_path, native(tmp_path) / "other.md"))
    assert mh.shown_since_compaction(store, "s2", 0) == frozenset()
    mh.handle(_read(tmp_path, native(tmp_path) / mni.NOTE))
    assert mh.shown_since_compaction(store, "s2", 0) == {"s1-001"}


def test_h5_a_note_changed_since_is_not_counted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    note = native(tmp_path) / mni.NOTE
    note.write_text(note.read_text("utf-8") + "edited", "utf-8")
    store = mh.store_for(event(tmp_path, session="s2"))
    mh.handle(_read(tmp_path, note))
    assert mh.shown_since_compaction(store, "s2", 0) == frozenset()


def test_h5_claude_code_s_own_memory_is_never_a_reason_to_hold_back(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text("ship_all(orders, carrier) carrier client label_for labels "
                                    "step 2 shipping today orders rejects requests app/labels.py",
                                    "utf-8")  # fmt: skip
    assert _refresh(tmp_path, written=frozenset({"plan.md"}))["native"] == "covered"
    assert mn.keys_after_read(_read(tmp_path, folder / "plan.md"), tmp_path / "store", "s2") == []


# ---- M1, M2: the bridge stays off where Claude Code's memory is elsewhere or off ----------------


@pytest.mark.parametrize(("name", "value"), [("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE", "C:/x"),
                                             ("CLAUDE_CODE_SIMPLE", "1"),
                                             ("CLAUDE_CODE_SAFE_MODE", "1"),
                                             ("CLAUDE_CODE_REMOTE", "1")])  # fmt: skip
def test_m1_m2_the_bridge_is_off(tmp_path: Path, monkeypatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    assert mn.native_dir(event(tmp_path)) is None


def test_m2_remote_with_its_memory_folder_writes_there(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "1")
    monkeypatch.setenv("CLAUDE_CODE_REMOTE_MEMORY_DIR", str(tmp_path / "remote"))
    assert mn.native_dir(event(tmp_path)) == tmp_path / "remote" / "projects" / "C--work-repo" \
        / "memory"  # fmt: skip


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_m2_project_settings_are_read_from_the_project_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "sub").mkdir(parents=True)
    _git("init", "-q", cwd=root)
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text('{"autoMemoryEnabled": false}', "utf-8")
    found = mn.native_dir({**event(tmp_path), "cwd": str(root / "sub")})
    assert found is None


# ---- M3, M4: links refused, temporaries cleaned ------------------------------------------------


def test_m3_a_linked_index_is_refused(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    target = tmp_path / "elsewhere.md"
    target.write_text("- [A](a.md) — one\n", encoding="utf-8")
    try:
        os.symlink(target, folder / "MEMORY.md")
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot make a symbolic link")
    assert _refresh(tmp_path)["native"] == "link refused"
    assert target.read_text(encoding="utf-8") == "- [A](a.md) — one\n"


def test_m4_our_stale_temporaries_are_cleaned_and_fresh_ones_kept(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    stale, fresh = folder / ".sanchopanza-old.tmp", folder / ".sanchopanza-new.tmp"
    stale.write_text("x", "utf-8")
    fresh.write_text("x", "utf-8")
    past = time.time() - 3600
    os.utime(stale, (past, past))
    _refresh(tmp_path)
    assert not stale.exists() and fresh.exists()


# ---- M5: coverage needs this session's own write or a changed file's name -----------------------


def test_m5_an_overlapping_memory_the_session_did_not_write_does_not_cover(tmp_path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    (folder / "plan.md").write_text(
        "ship_all orders carrier client label_for labels shipping "
        "today rejects requests session through adding",
        "utf-8",
    )
    assert _refresh(tmp_path)["native"] == "written"
    assert _refresh(tmp_path, written=frozenset({"plan.md"}))["native"] == "covered"


def test_m5_the_session_s_memory_writes_come_from_its_transcript(tmp_path: Path) -> None:
    folder = native(tmp_path)
    use = {
        "type": "tool_use",
        "id": "t9",
        "name": "Write",
        "input": {"file_path": str(folder / "plan.md"), "content": "x"},
    }
    shell = {
        "type": "tool_use",
        "id": "t10",
        "name": "Bash",
        "input": {"command": f'cd "{folder.as_posix()}" && cat > rule.md <<EOF'},
    }
    entries = [{"type": "assistant", "message": {"role": "assistant", "content": [use, shell]}}]
    assert mn.memory_writes(entries, folder) == {"plan.md", "rule.md"}


# ---- M6: going off removes only what is ours ----------------------------------------------------


def test_m6_uninstall_removes_only_our_marked_note_and_exact_line(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    (folder / "MEMORY.md").write_bytes((USER + "\n").encode("utf-8"))
    _refresh(tmp_path)
    removed = mn.uninstall(tmp_path / "config")
    assert len(removed) == 2 and not (folder / mni.NOTE).exists()
    assert _index(tmp_path) == USER + "\n"


def test_m6_no_memory_with_memory_native_is_refused(tmp_path: Path, capsys) -> None:
    path = tmp_path / "settings.json"
    code = cli.main(["install", "--path", str(path), "--no-memory", "--memory-native"])
    assert code == 2 and not path.exists()


def test_m6_install_without_the_flag_takes_our_note_out(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    path = config / "settings.json"
    assert cli.main(["install", "--path", str(path), "--memory-native", "--write"]) == 0
    _refresh(tmp_path)
    assert (native(tmp_path) / mni.NOTE).exists()
    assert cli.main(["install", "--path", str(path), "--write"]) == 0
    assert not (native(tmp_path) / mni.NOTE).exists()
    assert "sanchopanza-next.md" in capsys.readouterr().out


# ---- M7: one folder rule, and the memory gate never reads our note as a memory -------------------


def test_m7_the_memory_gate_uses_the_same_folder_and_skips_our_note(tmp_path: Path) -> None:
    assert mg.memory_dir_for(event(tmp_path)) == native(tmp_path)
    _refresh(tmp_path)
    (native(tmp_path) / "tabs.md").write_text("---\nname: tabs\n---\nTabs.", "utf-8")
    assert [m.file for m in mg.load_memories(native(tmp_path))] == ["tabs.md"]


# ---- M8: after the rules; the index rewritten only when the line changes -----------------------


def test_m8_the_note_comes_after_the_rules_at_stop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    order: list[str] = []
    monkeypatch.setattr(mh, "rules_at_stop", lambda *a: order.append("rules") or {})
    monkeypatch.setattr(mh, "native_at_stop", lambda *a: order.append("native"))
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    assert order == ["rules", "native"]


def test_m8_a_new_note_with_the_same_line_leaves_the_index_as_it_was(tmp_path: Path) -> None:
    _refresh(tmp_path)
    index = native(tmp_path) / "MEMORY.md"
    stamp = index.stat().st_mtime_ns
    later = record(report="A different final report, same request.")
    assert _refresh(tmp_path, [later])["native"] == "written"
    assert index.stat().st_mtime_ns == stamp


# ---- L1, L2 -------------------------------------------------------------------------------------


def test_l1_changed_paths_are_masked() -> None:
    text, _line, _keys = mn.compose([record(changed=(f"app/{GH_TOKEN}.py",))])
    assert GH_TOKEN not in text


def test_l2_what_claude_code_loads_is_measured_in_utf16_units() -> None:
    wide = "- [W](w.md) — " + "\U0001f600" * 12_600 + "\n"  # 25,200 UTF-16 units, 12,614 chars
    _text, line, _keys = mn.compose([record()])
    assert mni.index_with(wide, line) is None
