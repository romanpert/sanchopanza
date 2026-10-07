"""The passages hook (`harness.passages_hook`) on events shaped as Claude Code sends them.

No paid provider: the null squire ranks by BM25, a scripted decider stands in for Jev, and a
broken one for an outage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sanchopanza import Squire
from sanchopanza.journal import MemoryJournal
from tests.context_helpers import BrokenDecider, ScriptedDecider
from tests.test_passages_cut import check_line_numbers, module_source, pytest_log

HEADER = re.compile(r"^\[sanchopanza [^\n]*\]\n", re.M)


@pytest.fixture(autouse=True)
def _archive(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / ".sanchopanza" / "archive"))
    for name in ("PASSAGES_FRACTION", "PASSAGES_TOKENS", "SESSION_MAX_USD"):
        monkeypatch.delenv(f"SANCHOPANZA_{name}", raising=False)


def _transcript(tmp_path: Path, prompt: str, step: str = "", extra: list | None = None) -> Path:
    path = tmp_path / "project" / "sess.jsonl"
    (tmp_path / "project" / "sess" / "tool-results").mkdir(parents=True, exist_ok=True)
    entries = [{"type": "user", "message": {"role": "user", "content": prompt}}]
    if step:
        entries.append({"type": "assistant", "message": {
            "id": "m1", "role": "assistant", "content": [{"type": "text", "text": step}]}})
    entries += extra or []
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def _bash(tmp_path, transcript, command, stdout, use_id="toolu_b1", **response):
    return {
        "hook_event_name": "PostToolUse", "session_id": "sess", "cwd": str(tmp_path),
        "transcript_path": str(transcript), "tool_name": "Bash", "tool_use_id": use_id,
        "tool_input": {"command": command, "description": "Run the tests"},
        "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False, **response},
    }


def _read(tmp_path, transcript, path, content, use_id="toolu_r1", **tool_input):
    return {
        "hook_event_name": "PostToolUse", "session_id": "sess", "cwd": str(tmp_path),
        "transcript_path": str(transcript), "tool_name": "Read", "tool_use_id": use_id,
        "tool_input": {"file_path": str(path), **tool_input},
        "tool_response": {"type": "text", "file": {
            "filePath": str(path), "content": content, "numLines": content.count("\n"),
            "startLine": int(tool_input.get("offset") or 1), "totalLines": content.count("\n")}},
    }


def _squire(decider=None) -> Squire:
    return Squire(decider, journal=MemoryJournal())


def _events(squire: Squire, kind: str) -> list[dict]:
    return [e["data"] for e in squire.journal.events if e["kind"] == kind]


async def test_a_small_output_passes_untouched_and_is_not_journaled(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    squire = _squire()
    event = _bash(tmp_path, _transcript(tmp_path, "run the tests"), "pytest -q", "1 passed\n")
    assert await ph.post_tool_use(event, squire) == {}
    assert not _events(squire, "passages")


async def test_a_large_pytest_log_keeps_failures_and_the_summary(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    squire = _squire()
    log = pytest_log()
    transcript = _transcript(tmp_path, "make the test suite pass", "Running the tests to see "
                             "why test_add fails.")
    out = await ph.post_tool_use(_bash(tmp_path, transcript, "python -m pytest -v", log), squire)
    shown = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    for line in ("FAILED tests/test_app.py::test_add - assert -1 == 3",
                 "E       assert -1 == 3", "Traceback (most recent call last):",
                 "ValueError: invalid literal for int() with base 10: 'x'",
                 "=" * 24 + " 2 failed, 300 passed in 3.21s " + "=" * 25):
        assert line in shown
    assert len(shown) < 0.5 * len(log)
    body = HEADER.sub("", shown, count=1)
    check_line_numbers(log, body)
    [record] = _events(squire, "passages")
    assert record["acted"] is True and record["tool"] == "Bash" and record["kind"] == "test"
    assert record["chars_in"] == len(log) and record["chars_out"] == len(body)
    assert record["injected_chars"] == len(shown) and record["ranked_by"] == "bm25"
    archived = list((tmp_path / ".sanchopanza" / "archive" / "sess").glob("passages-*.txt"))
    assert [p.read_text(encoding="utf-8") for p in archived] == [log]
    assert str(archived[0]) in shown, "the reply names the whole text"


async def test_a_large_read_of_python_keeps_line_numbers_and_the_function(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    source = module_source()
    target = tmp_path / "settings.py"
    transcript = _transcript(tmp_path, "The config parser ignores the defaults.",
                             "Let me look at parse_config and load_defaults.")
    out = await ph.post_tool_use(_read(tmp_path, transcript, target, source), _squire())
    content = out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]
    assert "def parse_config(path):" in content and "def helper_70(" not in content
    shown, original = content.splitlines(), source.splitlines()
    assert len(shown) == len(original), "lines left out become blank: the numbering holds"
    assert all(not x or x.startswith("[sanchopanza") or x == original[i]
               for i, x in enumerate(shown))  # fmt: skip
    assert "offset" in content and "limit" in content, "how to get the omitted lines back"
    assert "unchanged" in content, "a plain Read again answers that the file is unchanged"


async def test_reads_the_agent_narrowed_or_that_recover_the_archive_pass(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    source = module_source()
    transcript = _transcript(tmp_path, "fix parse_config")
    narrowed = _read(tmp_path, transcript, tmp_path / "s.py", source, offset=10, limit=900)
    assert await ph.post_tool_use(narrowed, _squire()) == {}
    archive = tmp_path / ".sanchopanza" / "archive" / "sess" / "passages-toolu_x.txt"
    archive.parent.mkdir(parents=True)
    archive.write_text(source, encoding="utf-8")
    assert await ph.post_tool_use(_read(tmp_path, transcript, archive, source), _squire()) == {}
    saved = tmp_path / "project" / "sess" / "tool-results" / "b9.txt"
    saved.write_text(source, encoding="utf-8")
    assert await ph.post_tool_use(_read(tmp_path, transcript, saved, source), _squire()) == {}


async def test_git_diff_and_a_file_the_agent_edited_pass_and_are_journaled(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    squire = _squire()
    diff = "".join(f"diff --git a/f{i}.py b/f{i}.py\n+line {i}\n-old {i}\n\n" for i in range(400))
    transcript = _transcript(tmp_path, "review the change")
    assert await ph.post_tool_use(_bash(tmp_path, transcript, "git diff HEAD~1", diff),
                                  squire) == {}  # fmt: skip
    target = tmp_path / "settings.py"
    edit = [{"type": "assistant", "message": {"id": "m2", "role": "assistant", "content": [
        {"type": "tool_use", "id": "e1", "name": "Edit",
         "input": {"file_path": str(target), "old_string": "a", "new_string": "b"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "e1", "content": "updated"}]}}]
    edited = _transcript(tmp_path, "fix parse_config", extra=edit)
    assert await ph.post_tool_use(_read(tmp_path, edited, target, module_source()), squire) == {}
    reasons = [r["reason"] for r in _events(squire, "passages")]
    assert all(r["acted"] is False for r in _events(squire, "passages"))
    assert any("diff" in r for r in reasons) and any("edited" in r for r in reasons)


async def test_a_file_the_agent_says_it_will_edit_passes(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    target = tmp_path / "settings.py"
    transcript = _transcript(tmp_path, "the parser is wrong",
                             "I'll edit settings.py to fix parse_config.")
    assert await ph.post_tool_use(_read(tmp_path, transcript, target, module_source()),
                                  _squire()) == {}  # fmt: skip


async def test_a_saved_bash_output_is_ranked_whole_and_previewed(tmp_path):
    from sanchopanza.harness import browse_hook
    from sanchopanza.harness import passages_hook as ph

    log = pytest_log(3000)
    assert len(log) > 30000
    transcript = _transcript(tmp_path, "make the suite pass", "Why does test_parse fail?")
    saved = tmp_path / "project" / "sess" / "tool-results" / "b1.txt"
    saved.write_text(log, encoding="utf-8")
    event = _bash(tmp_path, transcript, "pytest -v", log[:30000],
                  persistedOutputPath=str(saved), persistedOutputSize=len(log))
    squire = _squire()
    out = await ph.post_tool_use(event, squire)
    shown = out["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert len(shown) <= browse_hook.PREVIEW_CHARS
    assert "FAILED tests/test_app.py::test_parse - ValueError: invalid literal" in shown
    cut_files = list((tmp_path / ".sanchopanza" / "archive" / "sess").glob("*-cut.txt"))
    assert cut_files and "ValueError: invalid literal" in cut_files[0].read_text(encoding="utf-8")
    assert str(cut_files[0]) in shown
    [record] = _events(squire, "passages")
    assert record["persisted"] is True and record["chars_in"] == len(log)


async def test_a_saved_output_it_cannot_read_passes(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    log = pytest_log(3000)
    transcript = _transcript(tmp_path, "run tests")
    event = _bash(tmp_path, transcript, "pytest -v", log[:30000],
                  persistedOutputPath=str(tmp_path / "elsewhere.txt"))
    assert await ph.post_tool_use(event, _squire()) == {}


async def test_a_decider_ranks_the_blocks(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    def answer(point, key, state):
        parts = re.split(r"(?m)^(P\d\d)\| ", state["pages"])
        text = dict(zip(parts[1::2], parts[2::2], strict=True)).get(key, "")
        return 0.95 if "helper_17" in text else 0.05

    decider = ScriptedDecider(answer)
    squire = _squire(decider)
    transcript = _transcript(tmp_path, "something vague", "Reading the module.")
    out = await ph.post_tool_use(_read(tmp_path, transcript, tmp_path / "m.py", module_source()),
                                 squire)  # fmt: skip
    content = out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]
    assert "def helper_17(value):" in content and decider.calls
    assert _events(squire, "passages")[0]["ranked_by"] == "scripted"


async def test_a_failing_decider_leaves_the_output_whole(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    squire = _squire(BrokenDecider())
    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    event = _read(tmp_path, transcript, tmp_path / "m.py", module_source())
    assert await ph.post_tool_use(event, squire) == {}
    [record] = _events(squire, "passages")
    assert record["acted"] is False and "decider" in record["reason"]


async def test_no_provider_ranks_by_bm25(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    squire = _squire()
    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    out = await ph.post_tool_use(_read(tmp_path, transcript, tmp_path / "m.py",
                                       module_source()), squire)  # fmt: skip
    assert "def parse_config" in out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]


async def test_a_rerun_of_a_cut_command_is_journaled_and_passes_whole(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    log = pytest_log()
    transcript = _transcript(tmp_path, "make the suite pass", "Running the tests.")
    squire = _squire()
    first = await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", log), squire)
    assert first
    other = _bash(tmp_path, transcript, "ls", "a\n", use_id="toolu_b2")
    assert await ph.post_tool_use(other, squire) == {}
    again = _bash(tmp_path, transcript, "pytest  -v", log, use_id="toolu_b3")
    assert await ph.post_tool_use(again, squire) == {}, "a re-request is never cut again"
    [rerun] = _events(squire, "passages_rerequest")
    assert rerun["cut"] == "toolu_b1" and rerun["tool_use_id"] == "toolu_b3"
    assert rerun["after_calls"] == 2 and rerun["kind"] == "whole"


async def test_a_targeted_read_of_the_file_after_a_cut_counts_as_targeted(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    source = module_source()
    target = tmp_path / "m.py"
    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    squire = _squire()
    assert await ph.post_tool_use(_read(tmp_path, transcript, target, source), squire)
    narrowed = _read(tmp_path, transcript, target, source[:2000], use_id="toolu_r2",
                     offset=300, limit=40)
    assert await ph.post_tool_use(narrowed, squire) == {}
    [again] = _events(squire, "passages_rerequest")
    assert again["kind"] == "targeted" and again["after_calls"] == 1


async def test_a_call_past_the_window_is_not_a_rerequest(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    log = pytest_log()
    transcript = _transcript(tmp_path, "make the suite pass", "Running the tests.")
    squire = _squire()
    await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", log), squire)
    for i in range(ph.REREQUEST_WINDOW):
        await ph.post_tool_use(_bash(tmp_path, transcript, f"echo {i}", "x\n", use_id=f"t{i}"),
                               squire)  # fmt: skip
    await ph.post_tool_use(_bash(tmp_path, transcript, "pytest -v", log, use_id="late"), squire)
    assert not _events(squire, "passages_rerequest")


async def test_the_fraction_comes_from_the_environment(tmp_path, monkeypatch):
    from sanchopanza.harness import passages_hook as ph

    source = module_source(120)
    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    sizes = {}
    for fraction in ("0.25", "0.10"):
        monkeypatch.setenv("SANCHOPANZA_PASSAGES_FRACTION", fraction)
        # another file each time: the same one again would be a re-request, never cut twice
        out = await ph.post_tool_use(_read(tmp_path, transcript, tmp_path / f"m{fraction}.py",
                                           source, use_id=f"r{fraction}"), _squire())  # fmt: skip
        sizes[fraction] = len(out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"])
    assert sizes["0.10"] < sizes["0.25"]


async def test_a_browser_snapshot_on_bash_is_left_to_the_browse_hook(tmp_path):
    from sanchopanza.harness import passages_hook as ph
    from tests.test_browse import _big_snapshot

    page = "### Snapshot\n```yaml\n" + _big_snapshot(200) + "```\n"
    transcript = _transcript(tmp_path, "find the price")
    assert await ph.post_tool_use(_bash(tmp_path, transcript, "playwright-cli snapshot", page),
                                  _squire()) == {}  # fmt: skip


def test_main_reads_stdin_and_fails_open(tmp_path, monkeypatch, capsys):
    import io

    from sanchopanza.harness import passages_hook as ph

    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"not json")))
    assert ph.main() == 0
    assert capsys.readouterr().out == ""


async def test_a_subagent_call_is_ranked_for_the_subagent_task(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    transcript = _transcript(tmp_path, "look at helper_50 please")
    own = tmp_path / "project" / "sess" / "subagents" / "agent-a1.jsonl"
    own.parent.mkdir(parents=True)
    ask = {"type": "user", "isSidechain": True,
           "message": {"role": "user", "content": "Find what helper_66 returns"}}
    own.write_text(json.dumps(ask) + "\n", encoding="utf-8")
    event = {**_read(tmp_path, transcript, tmp_path / "m.py", module_source()), "agent_id": "a1"}
    squire = _squire()
    out = await ph.post_tool_use(event, squire)
    content = out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"]
    assert "def helper_66(value):" in content and "def helper_50(value):" not in content
    assert _events(squire, "passages")[0]["subagent"] is True


def test_wants_skips_small_calls_unless_a_cut_is_being_watched(tmp_path):
    """The cheap check `main` runs before importing asyncio or building a squire."""
    import asyncio

    from sanchopanza.harness import passages_hook as ph

    transcript = _transcript(tmp_path, "make the suite pass", "Running the tests.")
    small = _bash(tmp_path, transcript, "ls", "a\n", use_id="s1")
    assert not ph.wants(small)
    assert not ph.wants({**small, "tool_name": "Grep"})
    big = _bash(tmp_path, transcript, "pytest -v", pytest_log())
    assert ph.wants(big)
    assert ph.wants({**small, "tool_response": {"stdout": "x", "persistedOutputPath": "p"}})
    asyncio.run(ph.post_tool_use(big, _squire()))
    assert ph.wants(small), "after a cut, every call counts toward the re-request window"


async def test_a_shell_look_at_a_cut_file_counts_as_a_rerequest(tmp_path):
    from sanchopanza.harness import passages_hook as ph

    target = tmp_path / "settings.py"
    transcript = _transcript(tmp_path, "fix parse_config", "Reading settings.")
    squire = _squire()
    assert await ph.post_tool_use(_read(tmp_path, transcript, target, module_source()), squire)
    await ph.post_tool_use(_bash(tmp_path, transcript, "sed -n '300,340p' settings.py", "x\n",
                                 use_id="b1"), squire)  # fmt: skip
    await ph.post_tool_use(_bash(tmp_path, transcript, f"cat {target}", "x\n", use_id="b2"),
                           squire)  # fmt: skip
    kinds = [(e["tool_use_id"], e["kind"]) for e in _events(squire, "passages_rerequest")]
    assert kinds == [("b1", "targeted"), ("b2", "whole")]
