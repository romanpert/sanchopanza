# ruff: noqa: E501, F811
"""The guard's pointer block (`context.pointers`), the default chooser since 2026-10-16.

After a compaction: the person's requests verbatim, the files changed, and pointers to the tool
output since the previous compaction instead of the output itself; output that cannot be had
again is archived whole beside the project and its pointer names the file to Read. The
whole-results block (`struct`) stays one setting away.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sanchopanza.context import guard, pointers, structural
from sanchopanza.context.transcript import Call
from sanchopanza.harness import guard_hook

from .test_context_guard import _run, env, write_session  # noqa: F401

TOKEN = "RT-6Z4FRFLG7W"


def _call(cid: str, tool: str, result: str = "ok", *, msg: int = 0, **arguments: Any) -> Call:
    return Call(id=cid, tool=tool, input=arguments, result=result, use_msg=msg)


def _history() -> list[Call]:
    body = "\n".join(f"{n:6d}\tline {n}" for n in range(1, 300))
    return [
        _call("issue", "Bash", f"release token: {TOKEN}\nexpires in 1h", command="./issue_token"),
        _call("read", "Read", body, file_path="/w/pkg/pricing.py"),
        _call(
            "edit", "Edit", "updated", file_path="/w/pkg/pricing.py", old_string="1", new_string="2"
        ),
        _call("grep", "Grep", "pkg/b.py:3: def f", pattern="def f", path="/w/pkg"),
    ]


def test_the_block_points_and_repeats_no_output(tmp_path: Path) -> None:
    g, entries = pointers.build_from_calls(_history(), ["Fix pricing; keep the token."],
                                           archive=tmp_path / "s1")  # fmt: skip
    text = guard.block(g)
    assert g.chooser == "pointers" and g.kind == "pointers" and g.facts == ()
    assert TOKEN not in text and "line 12" not in text  # no output body in the block
    assert guard.ARCHIVED_HEADING in text and "Fix pricing; keep the token." in text
    assert "changed: /w/pkg/pricing.py" in text
    assert "Grep 'def f' in /w/pkg" in text  # can be had again: named, not archived
    [entry] = entries  # only the one-shot output is archived
    assert entry.path.parent == (tmp_path / "s1").absolute()
    assert f"$ ./issue_token -> Read {entry.path}" in text
    assert TOKEN in entry.text
    assert guard.instructions(g) == guard.INSTRUCTIONS_POINTERS


def test_written_entries_hold_the_output_whole_and_masked(tmp_path: Path) -> None:
    secret = "sk-ant-api03-" + "A1b2C3d4" * 6
    history = [_call("env", "Bash", f"KEY={secret}\nTOKEN={TOKEN}", command="./show")]
    _, entries = pointers.build_from_calls(history, [], archive=tmp_path / "s")
    pointers.write(entries)
    written = entries[0].path.read_text("utf-8")
    assert TOKEN in written and "A1b2C3d4" not in written
    assert (tmp_path / ".gitignore").exists() is False  # only a .sanchopanza folder ignores itself


def test_without_an_archive_one_shot_output_gets_no_pointer() -> None:
    g, entries = pointers.build_from_calls(_history(), [], archive=None)
    assert entries == () and not any("issue_token" in p for p in g.pointers)
    assert any("Read /w/pkg/pricing.py" in p or "Edit /w/pkg/pricing.py" in p for p in g.pointers)


def test_the_block_stays_within_one_hooks_inline_limit(tmp_path: Path) -> None:
    history = [_call(f"b{n}", "Bash", f"value {n}", command=f"./probe --n {n} " + "x" * 80)
               for n in range(400)]  # fmt: skip
    requests = ["r" * 1_200, "s" * 1_200]
    g, entries = pointers.build_from_calls(history, requests, archive=tmp_path / "s",
                                           pointer_chars=100_000)  # fmt: skip
    assert structural.width(guard.block(g)) <= structural.INLINE_CHARS
    assert len(entries) == len(g.pointers) > 0  # every archived entry is named in the block


def test_the_block_is_far_smaller_than_the_whole_results_block(tmp_path: Path) -> None:
    history = [
        _call(f"r{n}", "Read", "x = 1\n" * 2_000, file_path=f"/w/pkg/m{n}.py") for n in range(12)
    ]
    g, _ = pointers.build_from_calls(history, ["do it"], archive=tmp_path / "s")
    whole = structural.build_from_calls(history, ["do it"], inline_chars=0)
    assert len(guard.block(g)) * 10 < len(guard.block(whole))


# ---- the hook --------------------------------------------------------------------------------------


def test_pointers_is_the_default_chooser_and_struct_one_setting_away(env, monkeypatch) -> None:
    assert guard_hook._chooser() == "pointers"
    monkeypatch.setenv("SANCHOPANZA_GUARD_CHOOSER", "struct")
    assert guard_hook._chooser() == "struct"


def test_the_default_hook_archives_beside_the_project_and_attaches_pointers(
    env, monkeypatch
) -> None:
    monkeypatch.delenv("SANCHOPANZA_ARCHIVE", raising=False)
    project = env / "proj"
    project.mkdir()
    path = write_session(env / "s.jsonl", compacted=False)
    event = {"session_id": "p1", "transcript_path": str(path), "cwd": str(project)}
    note = _run({"hook_event_name": "PreCompact", "trigger": "auto", **event}, monkeypatch)
    assert note == guard.INSTRUCTIONS_POINTERS
    out = json.loads(
        _run({"hook_event_name": "SessionStart", "source": "compact", **event}, monkeypatch)
    )
    context = out["hookSpecificOutput"]["additionalContext"]
    archived = sorted((project / ".sanchopanza" / "archive" / "p1").glob("guard-*.txt"))
    assert archived and all(str(p.absolute()) in context for p in archived)
    assert any(TOKEN in p.read_text("utf-8") for p in archived)
    assert TOKEN not in context  # the value is one Read away, not re-sent
    assert (project / ".sanchopanza" / ".gitignore").read_text("utf-8") == "*\n"
    log = [json.loads(x) for x in (env / "log.jsonl").read_text("utf-8").splitlines()]
    assert log[0]["chooser"] == "pointers" and log[0]["archived"] == len(archived)


def test_a_rebuilt_block_archives_again(env, monkeypatch) -> None:
    path = write_session(env / "s.jsonl", compacted=True)
    out = json.loads(_run({"hook_event_name": "SessionStart", "source": "compact", "session_id": "p2",
                           "transcript_path": str(path), "cwd": str(env)}, monkeypatch))  # fmt: skip
    context = out["hookSpecificOutput"]["additionalContext"]
    archived = list((env / "archive" / "p2").glob("guard-*.txt"))
    assert archived and str(archived[0].absolute()) in context


def test_an_archive_that_cannot_be_written_gives_the_rule_block(env, monkeypatch) -> None:
    def refuse(_: Any) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(pointers, "write", refuse)
    path = write_session(env / "s.jsonl", compacted=False)
    event = {"session_id": "p3", "transcript_path": str(path), "cwd": str(env)}
    _run({"hook_event_name": "PreCompact", "trigger": "auto", **event}, monkeypatch)
    out = json.loads(
        _run({"hook_event_name": "SessionStart", "source": "compact", **event}, monkeypatch)
    )
    context = out["hookSpecificOutput"]["additionalContext"]
    assert TOKEN in context  # the rule's value lines: nothing at risk is lost
    log = [json.loads(x) for x in (env / "log.jsonl").read_text("utf-8").splitlines()]
    assert log[0]["event"] == "error" and "read-only" in log[0]["error"]
    assert log[1]["chooser"].startswith("pointers (archive failed")


def test_a_split_install_still_gets_the_pointer_block_in_part_one(env, monkeypatch) -> None:
    path = write_session(env / "s.jsonl", compacted=False)
    event = {"session_id": "p4", "transcript_path": str(path), "cwd": str(env)}
    assert guard_hook.pre_compact({"hook_event_name": "PreCompact", **event}, 6)  # an older install
    one = guard_hook.session_start({"source": "compact", **event}, part=1, parts=6)
    two = guard_hook.session_start({"source": "compact", **event}, part=2, parts=6)
    assert guard.ARCHIVED_HEADING in one["hookSpecificOutput"]["additionalContext"]
    assert two is None
