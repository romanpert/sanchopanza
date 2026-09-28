"""The autopilot's hook bodies: shapes Claude Code accepts, archive, recall, ledger, fail-open.

Every decider is scripted; no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sanchopanza import Squire
from sanchopanza.context import archive as archive_mod
from sanchopanza.harness import autopilot, claude_code
from sanchopanza.harness import memory_gate as mg
from sanchopanza.harness.generic import HarnessConfig
from tests.context_helpers import BrokenDecider, ScriptedDecider, write_transcript

CODE = "".join(
    f"def function_{i}(x):\n    value = x * {i}\n    return value + {i}\n\n" for i in range(120)
)
ON = autopilot.Config(arrival=True, recall=True, recall_on_tool=True)


def _keep(marker: str, high: float = 0.9):
    def answer(point, key, state):
        if point in ("triage_pages",):
            parts = re.split(r"(?m)^(P\d\d)\| ", state["pages"])
            text = dict(zip(parts[1::2], parts[2::2], strict=True)).get(key, "")
            return high if marker in text else 0.02
        if point == "recall":
            return 0.9
        return None

    return answer


def _event(tmp_path: Path, **extra):
    transcript = write_transcript(tmp_path / "session.jsonl")
    return {
        "hook_event_name": "PostToolUse",
        "session_id": "s-1",
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
        "tool_name": "Read",
        "tool_use_id": "toolu_9",
        "tool_input": {"file_path": str(tmp_path / "app.py")},
        "tool_response": {
            "type": "text",
            "file": {
                "filePath": str(tmp_path / "app.py"),
                "content": CODE,
                "numLines": 480,
                "startLine": 1,
                "totalLines": 480,
            },
        },
        **extra,
    }


# --- the response's text field ----------------------------------------------------------------


def test_text_field_finds_the_content_of_each_tool_shape():
    assert autopilot.text_field({"file": {"content": "x" * 9, "filePath": "y" * 50}})[0] == (
        "file",
        "content",
    )
    assert autopilot.text_field({"stdout": "a" * 9, "stderr": "b"})[0] == ("stdout",)
    assert autopilot.text_field({"result": "r" * 9, "url": "u" * 90, "code": 200})[0] == ("result",)
    assert autopilot.text_field([{"type": "text", "text": "t" * 9}])[0] == (0, "text")
    assert autopilot.text_field("plain") == ((), "plain")
    assert autopilot.text_field({"code": 200}) is None


def test_replaced_changes_one_field_and_nothing_else():
    original = {"stdout": "long", "stderr": "", "interrupted": False, "isImage": False}
    out = autopilot.replaced(original, ("stdout",), "short")
    assert out == {**original, "stdout": "short"}
    assert original["stdout"] == "long"  # not mutated
    blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert autopilot.replaced(blocks, (1, "text"), "c")[1] == {"type": "text", "text": "c"}


# --- PostToolUse ------------------------------------------------------------------------------


async def test_a_long_read_is_cut_archived_and_keeps_its_shape(tmp_path):
    squire = Squire(ScriptedDecider(_keep("function_7(")))
    config = autopilot.Config(arrival=True)
    out = await autopilot.post_tool_use(_event(tmp_path), squire, config)
    specific = out["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    updated = specific["updatedToolOutput"]
    assert set(updated) == {"type", "file"}
    assert set(updated["file"]) == {"filePath", "content", "numLines", "startLine", "totalLines"}
    content = updated["file"]["content"]
    assert content.startswith("[sanchopanza cut this Read result on arrival")
    assert "def function_7(x):" in content and "def function_60(" not in content
    path = Path(re.search(r"Full text: (.+?) \(Read it", content).group(1))
    assert path.read_text(encoding="utf-8") == CODE
    assert (tmp_path / ".sanchopanza" / ".gitignore").read_text() == "*\n"
    assert json.loads(path.with_name(path.stem + ".meta.json").read_text())["by"] == "arrival"


async def test_the_decider_sees_the_task_from_the_transcript(tmp_path):
    decider = ScriptedDecider(_keep("function_7("))
    await autopilot.post_tool_use(_event(tmp_path), Squire(decider), autopilot.Config(arrival=True))
    purpose = decider.calls[0][1]["purpose"]
    assert "Fix the failing test in app.py" in purpose
    assert "app.py" in purpose


async def test_an_outage_leaves_the_result_untouched(tmp_path, capsys):
    out = await autopilot.post_tool_use(
        _event(tmp_path), Squire(BrokenDecider()), autopilot.Config(arrival=True)
    )
    assert out == {}
    assert "passed whole" in capsys.readouterr().err
    assert not any((tmp_path / ".sanchopanza" / "archive").glob("*/*.txt"))


async def test_a_short_result_and_a_subagent_report_are_never_touched(tmp_path):
    decider = ScriptedDecider(lambda *a: 0.01)
    short = _event(tmp_path, tool_response={"stdout": "ok", "stderr": ""}, tool_name="Bash")
    report = _event(tmp_path, tool_name="Agent", tool_response={"content": CODE})
    for event in (short, report):
        out = await autopilot.post_tool_use(event, Squire(decider), autopilot.Config(arrival=True))
        assert out == {}
    assert decider.calls == []


async def test_stderr_needs_the_error_threshold(tmp_path):
    event = _event(
        tmp_path,
        tool_name="Bash",
        tool_input={"command": "make"},
        tool_response={"stdout": "", "stderr": CODE[:9_000], "interrupted": False},
    )
    decider = ScriptedDecider(lambda *a: 0.01)
    out = await autopilot.post_tool_use(event, Squire(decider), autopilot.Config(arrival=True))
    assert out == {} and decider.calls == []


async def test_the_tool_input_is_never_changed(tmp_path):
    event = _event(tmp_path)
    out = await autopilot.post_tool_use(
        event, Squire(ScriptedDecider(_keep("function_7("))), autopilot.Config(arrival=True)
    )
    assert "updatedInput" not in out["hookSpecificOutput"]
    assert event["tool_input"] == {"file_path": str(tmp_path / "app.py")}


async def test_the_session_ceiling_passes_everything_through(tmp_path, capsys):
    root = archive_mod.root_for(tmp_path)
    autopilot.write_ledger(root, "s-1", {"usd": 1.0, "decisions": 9, "injected": []})
    decider = ScriptedDecider(_keep("function_7("))
    out = await autopilot.post_tool_use(_event(tmp_path), Squire(decider), ON)
    assert out == {} and decider.calls == []
    assert "ceiling" in capsys.readouterr().err


async def test_the_ledger_accumulates_across_processes(tmp_path):
    for _ in range(2):
        squire = Squire(ScriptedDecider(_keep("function_7(")))
        await autopilot.post_tool_use(_event(tmp_path), squire, autopilot.Config(arrival=True))
    ledger = autopilot.read_ledger(archive_mod.root_for(tmp_path), "s-1")
    assert ledger["decisions"] >= 2


# --- recall -----------------------------------------------------------------------------------


def _archive_entry(tmp_path: Path, name: str, text: str, about: str) -> Path:
    directory = archive_mod.session_dir(archive_mod.root_for(tmp_path), "old-session")
    return archive_mod.write_entry(directory, name, text, {"tool": "Bash", "about": about})


def _memory(tmp_path: Path, name: str, body: str) -> Path:
    project = tmp_path / "project"
    (project / "memory").mkdir(parents=True, exist_ok=True)
    path = project / "memory" / f"{name}.md"
    path.write_text(f"---\nname: {name}\ndescription: {name} notes\n---\n{body}\n", "utf-8")
    return project


async def test_prompt_recall_joins_memory_files_and_the_archive(tmp_path):
    project = _memory(tmp_path, "deploy", "Deploy with the blue pipeline, never on Fridays.")
    _archive_entry(tmp_path, "c1", "pytest output: test_parser_unicode FAILED", "pytest -q")
    _archive_entry(tmp_path, "c2", "npm install finished", "npm install")
    event = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s-1",
        "cwd": str(tmp_path),
        "transcript_path": str(project / "s-1.jsonl"),
        "prompt": "why does test_parser_unicode fail after the deploy pipeline change",
    }

    def answer(point, key, state):
        if point == "recall":
            return 0.9
        return 0.9 if point == "triage_pages" else None

    out = await autopilot.user_prompt(event, Squire(ScriptedDecider(answer)), ON)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "deploy.md" in context and "c1.txt" in context
    assert "c2.txt" not in context  # BM25 never proposed it: no shared word
    ledger = autopilot.read_ledger(archive_mod.root_for(tmp_path), "s-1")
    assert any(item.endswith("c1.txt") for item in ledger["injected"])


async def test_tool_recall_appends_and_does_not_repeat(tmp_path):
    saved = _archive_entry(tmp_path, "c1", "function_7 was renamed to compute_total", "git log")
    event = _event(
        tmp_path,
        tool_response={"stdout": "ok", "stderr": ""},
        tool_name="Bash",
        tool_input={"command": "grep -n function_7 app.py"},
    )
    decider = ScriptedDecider(lambda point, key, state: 0.9 if point == "triage_pages" else None)
    first = await autopilot.post_tool_use(event, Squire(decider), ON)
    assert str(saved) in first["hookSpecificOutput"]["additionalContext"]
    assert "updatedToolOutput" not in first["hookSpecificOutput"]
    second = await autopilot.post_tool_use(event, Squire(decider), ON)
    assert second == {}  # already injected in this context


async def test_a_compaction_lets_recalled_entries_come_back(tmp_path):
    root = archive_mod.root_for(tmp_path)
    autopilot.write_ledger(root, "s-1", {"usd": 0.0, "decisions": 0, "injected": ["x"]})
    autopilot.clear_injected(root, "s-1")
    assert autopilot.read_ledger(root, "s-1")["injected"] == []


async def test_recall_with_nothing_answered_injects_nothing(tmp_path):
    _archive_entry(tmp_path, "c1", "function_7 was renamed", "git log")
    event = _event(
        tmp_path,
        tool_response={"stdout": "ok"},
        tool_name="Bash",
        tool_input={"command": "grep function_7"},
    )
    out = await autopilot.post_tool_use(event, Squire(BrokenDecider()), ON)
    assert out == {}


def test_bm25_candidates_are_top_k_with_a_shared_word():
    store = [
        mg.Memory(file=f"f{i}", name="", description="", body=body)
        for i, body in enumerate(["alpha beta", "gamma", "alpha alpha gamma", "delta"])
    ]
    assert mg.bm25_candidates("alpha", store, k=5) == [2, 0]
    assert mg.bm25_candidates("alpha", store, k=1) == [2]
    assert mg.bm25_candidates("zeta", store) == []


# --- the command-line hook ----------------------------------------------------------------------


def test_the_fast_path_skips_what_the_autopilot_cannot_act_on(tmp_path):
    config = HarnessConfig()
    short = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_response": {"stdout": "ok"},
    }
    long = {**short, "tool_response": {"stdout": "x" * 7_000}}
    prompt = {"hook_event_name": "UserPromptSubmit", "prompt": "hello there"}
    assert not claude_code.needs_decision(short, config, ON)
    assert claude_code.needs_decision(long, config, ON)
    assert claude_code.needs_decision(prompt, config, ON)
    assert not claude_code.needs_decision(prompt, config, autopilot.Config())
    assert not claude_code.needs_decision(long, config, autopilot.Config())


def test_config_from_env_turns_the_pieces_on_and_off():
    assert autopilot.config_from_env({}).any is False
    on = autopilot.config_from_env({"SANCHOPANZA_AUTOPILOT": "1"})
    assert on.arrival and on.recall and on.recall_on_tool
    partial = autopilot.config_from_env(
        {
            "SANCHOPANZA_AUTOPILOT": "1",
            "SANCHOPANZA_RECALL_ON_TOOL": "0",
            "SANCHOPANZA_ARRIVAL_CHARS": "9000",
        }
    )
    assert partial.arrival and not partial.recall_on_tool and partial.threshold == 9_000


def test_merge_outputs_joins_contexts_and_keeps_the_rewrite():
    scan = {
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "a"},
        "systemMessage": "warned",
    }
    cut = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": {"x": 1},
            "additionalContext": "b",
        }
    }
    out = claude_code.merge_outputs(scan, cut)
    assert out["hookSpecificOutput"]["additionalContext"] == "a\n\nb"
    assert out["hookSpecificOutput"]["updatedToolOutput"] == {"x": 1}
    assert out["systemMessage"] == "warned"
    assert claude_code.merge_outputs({}, cut) == cut


async def test_handle_routes_a_prompt_to_recall_only_when_on(tmp_path, monkeypatch):
    monkeypatch.delenv("SANCHOPANZA_AUTOPILOT", raising=False)
    guardian = claude_code.Guardian(Squire(BrokenDecider()), HarnessConfig())
    event = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "anything at all",
        "cwd": str(tmp_path),
    }
    assert await claude_code.handle(event, guardian) == {}


# --- the process boundary ---------------------------------------------------------------------


def _hook(event: dict, **env: str):
    import os
    import subprocess
    import sys

    probe = (
        "from sanchopanza.cli import main\nimport sys, json\ncode = main(['hook'])\n"
        "sys.stderr.write('MODULES=' + json.dumps(sorted(sys.modules)))\n"
    )
    full = {**os.environ, "SANCHOPANZA_PROVIDER": "null", "SANCHOPANZA_JOURNAL": os.devnull, **env}
    full.pop("TYPESAFE_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-c", probe],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=full,
        timeout=120,
    )


def test_a_short_result_never_loads_the_squire_with_the_autopilot_on(tmp_path):
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "cwd": str(tmp_path),
        "tool_input": {"command": "ls"},
        "tool_response": {"stdout": "a\nb", "stderr": ""},
    }
    run = _hook(event, SANCHOPANZA_AUTOPILOT="1")
    modules = set(json.loads(run.stderr.rsplit("MODULES=", 1)[1]))
    assert "sanchopanza.squire" not in modules and "asyncio" not in modules
    assert run.stdout == ""


def test_a_long_result_with_no_decider_passes_whole_and_says_why(tmp_path):
    event = _event(tmp_path)
    run = _hook(event, SANCHOPANZA_AUTOPILOT="1")
    assert run.returncode == 0
    assert run.stdout == ""  # the null decider answers nothing: nothing replaced
    assert "passed whole" in run.stderr
