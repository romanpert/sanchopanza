"""The memory bridge (`harness.memory_native`): a session's record written into Claude Code's own
auto memory, in its format and folder, so Claude Code loads it itself at the next start.
No test here calls a paid provider."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.context import episodes as ep
from sanchopanza.harness import memory_hook as mh
from sanchopanza.harness import memory_native as mn
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import plan

CWD = "C:/work/repo"
SLUG = "C--work-repo"
GH_TOKEN = "ghp_" + "b" * 30
PLAN = (
    "We're adding shipping labels in two steps. Step 1, today: label_for(order) in "
    "app/labels.py. Step 2, next session: ship_all(orders, carrier) through the carrier "
    "client. Only do step 1 now. The carrier rejects requests with more than 50 labels."
)
REPORT = "Step 1 is done: label_for is in app/labels.py with tests. ship_all is not started."


@pytest.fixture(autouse=True)
def _clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
        "CLAUDE_CODE_REMOTE_MEMORY_DIR",
        "CLAUDE_COWORK_MEMORY_PATH_OVERRIDE",
        "SANCHOPANZA_MEMORY_NATIVE",
        "SANCHO_MEMORY_NATIVE",
        "SANCHOPANZA_MEMORY_SELECT",
        "SANCHOPANZA_PROVIDER",
        "TYPESAFE_API_KEY",
        "SANCHOPANZA_MEMORY_TREE",
        "SANCHOPANZA_MEMORY_PROMPT_NAMED",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_KEY", "folder")  # no git calls by default


def record(
    index: int = 1,
    session: str = "s1",
    request: str = PLAN,
    report: str = REPORT,
    changed: tuple[str, ...] = ("app/labels.py", "tests/test_labels.py"),
    at: float | None = None,
) -> ep.Episode:
    return ep.Episode(
        session=session,
        index=index,
        request=request,
        report=report,
        changed=changed,
        changed_raw=changed,
        at=time.time() - 60 if at is None else at,
    )


def native(tmp_path: Path) -> Path:
    return tmp_path / "config" / "projects" / SLUG / "memory"


def event(tmp_path: Path, name: str = "Stop", session: str = "s1", **extra: Any) -> dict[str, Any]:
    transcript = tmp_path / "config" / "projects" / SLUG / f"{session}.jsonl"
    return {
        "hook_event_name": name,
        "session_id": session,
        "cwd": CWD,
        "transcript_path": str(transcript),
        **extra,
    }


# ---- where Claude Code keeps auto memory ---------------------------------------------------------


def test_the_folder_follows_the_transcript_s_config_folder(tmp_path: Path) -> None:
    assert mn.native_dir(event(tmp_path)) == native(tmp_path)


def test_claude_config_dir_wins_and_the_slug_is_claude_code_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "other"))
    found = mn.native_dir({"session_id": "s", "cwd": "C:\\Users\\r\\a.b"})
    assert found == tmp_path / "other" / "projects" / "C--Users-r-a-b" / "memory"


def test_without_any_hint_it_is_the_home_claude_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    found = mn.native_dir({"session_id": "s", "cwd": CWD})
    assert found == tmp_path / ".claude" / "projects" / SLUG / "memory"


def test_auto_memory_turned_off_means_no_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "1")
    assert mn.native_dir(event(tmp_path)) is None
    monkeypatch.delenv("CLAUDE_CODE_DISABLE_AUTO_MEMORY")
    settings = tmp_path / "config" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"autoMemoryEnabled": False}), encoding="utf-8")
    assert mn.native_dir(event(tmp_path)) is None


def test_an_auto_memory_directory_in_user_settings_is_followed(tmp_path: Path) -> None:
    settings = tmp_path / "config" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"autoMemoryDirectory": str(tmp_path / "mine")}), "utf-8")
    assert mn.native_dir(event(tmp_path)) == tmp_path / "mine"


def test_a_slug_past_claude_code_s_200_characters_is_not_guessed(tmp_path: Path) -> None:
    deep = "C:/" + "/".join(["folder"] * 40)
    assert mn.native_dir({**event(tmp_path), "cwd": deep}) is None


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_a_worktree_shares_the_main_checkout_s_memory_as_claude_code_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_KEY", "repo")
    main = tmp_path / "main"
    main.mkdir()
    _git("init", "-q", "-b", "main", cwd=main)
    (main / "a.txt").write_text("a", encoding="utf-8")
    _git("add", "-A", cwd=main)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "a", cwd=main)
    _git("worktree", "add", "-q", "-b", "side", str(tmp_path / "wt"), cwd=main)
    found = mn.native_dir(
        {
            "session_id": "w1",
            "cwd": str(tmp_path / "wt"),
            "transcript_path": str(tmp_path / "config" / "projects" / "x" / "w1.jsonl"),
        }
    )
    slug = mn.project_key(str(main.resolve()).replace("\\", "/"))
    assert found is not None and found.parent.name.casefold() == slug.casefold()


# ---- what is written ----------------------------------------------------------------------------


def test_the_note_is_in_claude_code_s_memory_format_and_bounded() -> None:
    long = record(request=PLAN + " " + "x" * 9000, report=REPORT + f" token={GH_TOKEN}")
    text, line = mn.compose([long])
    head = text.split("---")[1]
    assert "name: sanchopanza-next" in head and "description:" in head
    assert "metadata:\n  type: project" in head
    assert "ship_all" in text and GH_TOKEN not in text
    assert len(text) <= mn.FILE_CHARS
    assert line.startswith("- [") and f"]({mn.NOTE})" in line
    assert "\n" not in line and len(line) <= mn.LINE_CHARS


def test_refresh_writes_the_note_and_one_index_line_and_keeps_every_user_line(
    tmp_path: Path,
) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    users = "- [Prefers tabs](tabs.md) — user style\n- [Deploy](deploy.md) — how to ship\n"
    (folder / "MEMORY.md").write_text(users, encoding="utf-8")
    (folder / "tabs.md").write_text("---\nname: tabs\n---\nTabs.", encoding="utf-8")
    row = mn.refresh(folder, [record()], session="s1", store=tmp_path / "store")
    assert row["native"] == "written"
    index = (folder / "MEMORY.md").read_text(encoding="utf-8")
    assert index.startswith(users) and index.count(f"]({mn.NOTE})") == 1
    assert (folder / "tabs.md").read_text(encoding="utf-8") == "---\nname: tabs\n---\nTabs."
    assert "ship_all" in (folder / mn.NOTE).read_text(encoding="utf-8")
    assert not [p for p in folder.iterdir() if p.name.startswith(".")]  # no temporary left


def test_refresh_is_idempotent_and_replaces_only_its_own_line(tmp_path: Path) -> None:
    folder = native(tmp_path)
    store = tmp_path / "store"
    mn.refresh(folder, [record()], session="s1", store=store)
    stamp = (folder / mn.NOTE).stat().st_mtime_ns
    assert mn.refresh(folder, [record()], session="s1", store=store)["native"] == "unchanged"
    assert (folder / mn.NOTE).stat().st_mtime_ns == stamp
    index = folder / "MEMORY.md"
    index.write_text(
        index.read_text(encoding="utf-8") + "- [Later](later.md) — added by CC\n", encoding="utf-8"
    )
    later = record(
        2, request="Now add invoices in app/invoices.py, step 1 of 2.", changed=("app/invoices.py",)
    )
    mn.refresh(folder, [record(), later], session="s1", store=store)
    lines = index.read_text(encoding="utf-8").splitlines()
    ours = [n for n in lines if f"]({mn.NOTE})" in n]
    assert len(ours) == 1 and lines[-1] == "- [Later](later.md) — added by CC"
    assert "invoices" in (folder / mn.NOTE).read_text(encoding="utf-8")


def test_a_full_index_is_left_alone_and_no_note_is_written(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    full = "".join(f"- [m{i}](m{i}.md) — x\n" for i in range(mn.INDEX_LINES))
    (folder / "MEMORY.md").write_text(full, encoding="utf-8")
    row = mn.refresh(folder, [record()], session="s1", store=tmp_path / "store")
    assert row["native"] == "index full"
    assert (folder / "MEMORY.md").read_text(encoding="utf-8") == full
    assert not (folder / mn.NOTE).exists()
    wide = "- [w](w.md) — " + "y" * (mn.INDEX_BYTES - 20) + "\n"
    (folder / "MEMORY.md").write_text(wide, encoding="utf-8")
    assert (
        mn.refresh(folder, [record()], session="s1", store=tmp_path / "store")["native"]
        == "index full"
    )


def test_a_session_that_changed_no_file_leaves_the_note_as_it_was(tmp_path: Path) -> None:
    folder = native(tmp_path)
    store = tmp_path / "store"
    mn.refresh(folder, [record()], session="s1", store=store)
    before = (folder / mn.NOTE).read_text(encoding="utf-8")
    question = record(1, session="s2", request="What does label_for return?", changed=())
    assert mn.refresh(folder, [question], session="s2", store=store)["native"] == "no change"
    assert (folder / mn.NOTE).read_text(encoding="utf-8") == before


def test_claude_code_s_own_memory_of_the_plan_this_session_takes_over(tmp_path: Path) -> None:
    folder = native(tmp_path)
    store = tmp_path / "store"
    mn.refresh(folder, [record(session="s0")], session="s0", store=store)  # an older note
    own = folder / "labels-step2.md"
    own.write_text(
        "---\nname: labels-step2\nmetadata:\n  type: project\n---\nStep 2 next "
        "session: ship_all(orders, carrier) through the carrier client; labels "
        "come from label_for(order) in app/labels.py; carrier rejects more than "
        "50 labels per request; shipping labels step 1 done today.",
        "utf-8",
    )
    index = folder / "MEMORY.md"
    index.write_text(
        index.read_text(encoding="utf-8") + "- [Labels](labels-step2.md) — s2\n", encoding="utf-8"
    )
    row = mn.refresh(folder, [record(at=time.time() - 30)], session="s1", store=store)
    assert row["native"] == "covered" and row["covered_by"] == ["labels-step2.md"]
    assert not (folder / mn.NOTE).exists()
    assert index.read_text(encoding="utf-8") == "- [Labels](labels-step2.md) — s2\n"
    assert own.exists()


def test_the_record_claude_code_saved_itself_is_not_given_again_while_unchanged(
    tmp_path: Path,
) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    store = tmp_path / "store"
    own = folder / "labels-step2.md"
    own.write_text(
        "Step 2 next session: ship_all(orders, carrier) through the carrier client; "
        "label_for(order) in app/labels.py; carrier rejects more than 50 labels; shipping "
        "labels step 1 done today.",
        "utf-8",
    )
    (folder / "MEMORY.md").write_text("- [Labels](labels-step2.md) — step 2\n", "utf-8")
    assert mn.refresh(folder, [record()], session="s1", store=store)["native"] == "covered"
    assert mn.carried(event(tmp_path, session="s2"), store, "s2") == ["s1-001"]
    assert mn.carried(event(tmp_path, session="s1"), store, "s1") == []  # its own session
    own.write_text("Rewritten: nothing about step 2.", "utf-8")
    assert mn.carried(event(tmp_path, session="s2"), store, "s2") == []


def test_an_older_or_unrelated_memory_of_claude_code_does_not_cover(tmp_path: Path) -> None:
    folder = native(tmp_path)
    folder.mkdir(parents=True)
    old = folder / "labels-old.md"
    old.write_text("ship_all(orders, carrier) carrier client label_for labels step 2", "utf-8")
    past = time.time() - 3600
    os.utime(old, (past, past))
    (folder / "tabs.md").write_text("---\nname: tabs\n---\nThe user prefers tabs.", "utf-8")
    row = mn.refresh(folder, [record(at=time.time() - 60)], session="s1", store=tmp_path / "s")
    assert row["native"] == "written"


# ---- the hook -----------------------------------------------------------------------------------


def _say(text: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def _transcript(tmp_path: Path, session: str, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "config" / "projects" / SLUG / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def _step_one() -> list[dict[str, Any]]:
    use = {
        "type": "tool_use",
        "id": "t1",
        "name": "Write",
        "input": {"file_path": f"{CWD}/app/labels.py", "content": "def label_for(o): ..."},
    }
    result = {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
    return [
        {
            "type": "user",
            "cwd": CWD,
            "timestamp": "2026-10-16T10:00:00Z",
            "message": {"role": "user", "content": PLAN},
        },
        {"type": "assistant", "message": {"role": "assistant", "content": [use]}},
        {"type": "user", "message": {"role": "user", "content": [result]}},
        _say(REPORT),
    ]


def test_the_bridge_is_opt_in(tmp_path: Path) -> None:
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    assert not (native(tmp_path) / mn.NOTE).exists()


def test_at_stop_the_hook_writes_the_note_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    _transcript(tmp_path, "s1", _step_one())
    assert mh.handle(event(tmp_path)) == {}
    note = (native(tmp_path) / mn.NOTE).read_text(encoding="utf-8")
    assert "ship_all" in note and "app/labels.py" in note


def _next_session_gets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "every")  # bm25 recall at the prompt
    mh.handle(event(tmp_path, "SessionStart", "s2", source="startup"))
    out = mh.handle(
        event(
            tmp_path,
            "UserPromptSubmit",
            "s2",
            prompt="Let's continue with ship_all in app/labels.py",
        )
    )
    return out["hookSpecificOutput"]["additionalContext"] if out else ""


def test_without_the_bridge_the_next_session_is_given_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    assert "session s1" in _next_session_gets(tmp_path, monkeypatch)


def test_with_the_bridge_the_record_claude_code_loads_is_not_given_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    assert _next_session_gets(tmp_path, monkeypatch) == ""


def test_a_note_dropped_from_the_index_is_not_counted_as_carried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    (native(tmp_path) / "MEMORY.md").write_text("- [Other](other.md) — rewritten by CC\n", "utf-8")
    assert "session s1" in _next_session_gets(tmp_path, monkeypatch)


def test_a_note_edited_since_it_was_written_is_not_counted_as_carried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_NATIVE", "1")
    _transcript(tmp_path, "s1", _step_one())
    mh.handle(event(tmp_path))
    (native(tmp_path) / mn.NOTE).write_text("---\nname: sanchopanza-next\n---\nemptied", "utf-8")
    assert "session s1" in _next_session_gets(tmp_path, monkeypatch)


# ---- install ------------------------------------------------------------------------------------


def test_install_memory_native_owns_its_variable(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    on = plan(path, HarnessConfig(), memory=True, memory_native=True)
    assert on.merged["env"]["SANCHOPANZA_MEMORY_NATIVE"] == "1"
    assert "env: SANCHOPANZA_MEMORY_NATIVE=1" in on.added
    path.write_text(json.dumps(on.merged), encoding="utf-8")
    off = plan(path, HarnessConfig(), memory=True)
    assert "SANCHOPANZA_MEMORY_NATIVE" not in off.merged.get("env", {})
    assert "env: SANCHOPANZA_MEMORY_NATIVE" in off.removed
    without_memory = plan(path, HarnessConfig(), memory=False, memory_native=True)
    assert "SANCHOPANZA_MEMORY_NATIVE" not in without_memory.merged.get("env", {})
