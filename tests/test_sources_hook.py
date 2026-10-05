"""The sources hook: one request for sources at the first Stop of a session that used the web,
never twice, never on its own feedback loop, and wired by `install --sources` on Stop alone."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from sanchopanza.harness import sources_hook
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import apply, plan
from sanchopanza.harness.sources_hook import REQUEST, SOURCES_COMMAND, SOURCES_HOOKS


def _transcript(tmp_path: Path, tools: list[str]) -> Path:
    entries = [{"type": "user", "message": {"role": "user", "content": "Which city? ANSWER:"}}]
    for number, tool in enumerate(tools):
        use = {"type": "tool_use", "id": f"t{number}", "name": tool, "input": {"q": "x"}}
        result = {"type": "tool_result", "tool_use_id": f"t{number}", "content": "found"}
        entries.append({"type": "assistant", "message": {"role": "assistant", "content": [use]}})
        entries.append({"type": "user", "message": {"role": "user", "content": [result]}})
    final = {"role": "assistant", "content": [{"type": "text", "text": "ANSWER: Lyon."}]}
    entries.append({"type": "assistant", "message": final})
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def _event(transcript: Path, **extra: object) -> dict[str, object]:
    return {
        "session_id": "abc-123",
        "transcript_path": str(transcript),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        **extra,
    }


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setattr(sources_hook, "state_dir", lambda: state)
    monkeypatch.delenv("SANCHOPANZA_SOURCES", raising=False)
    monkeypatch.delenv("SANCHO_SOURCES", raising=False)
    return state


def test_blocks_once_after_web_calls_then_lets_the_session_stop(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ["WebSearch", "WebFetch"])
    first = sources_hook.handle(_event(transcript), env={})
    assert first == {"decision": "block", "reason": REQUEST}
    assert sources_hook.handle(_event(transcript), env={}) is None


def test_the_mark_is_written_before_blocking(tmp_path: Path, _state: Path) -> None:
    transcript = _transcript(tmp_path, ["mcp__playwright__browser_navigate"])
    assert sources_hook.handle(_event(transcript), env={}) is not None
    assert len(list(_state.glob("*abc-123*"))) == 1


def test_respects_stop_hook_active(tmp_path: Path, _state: Path) -> None:
    transcript = _transcript(tmp_path, ["WebSearch"])
    assert sources_hook.handle(_event(transcript, stop_hook_active=True), env={}) is None
    assert not _state.exists() or not any(_state.iterdir())


def test_subagent_stop_is_left_alone(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ["WebSearch"])
    event = _event(transcript, hook_event_name="SubagentStop")
    assert sources_hook.handle(event, env={}) is None


def test_no_web_calls_no_request(tmp_path: Path, _state: Path) -> None:
    transcript = _transcript(tmp_path, ["Read", "Bash", "Grep", "mcp__memory__search"])
    assert sources_hook.handle(_event(transcript), env={}) is None
    assert not _state.exists() or not any(_state.iterdir())


@pytest.mark.parametrize(
    "tool",
    ["WebSearch", "WebFetch", "mcp__playwright__browser_snapshot", "mcp__fetch__fetch"],
)
def test_every_kind_of_web_call_counts(tmp_path: Path, tool: str) -> None:
    assert sources_hook.handle(_event(_transcript(tmp_path, [tool])), env={}) is not None


def test_env_zero_switches_it_off(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ["WebSearch"])
    assert sources_hook.handle(_event(transcript), env={"SANCHOPANZA_SOURCES": "0"}) is None


def test_the_request_asks_for_conditions_sources_and_the_answer_line() -> None:
    lowered = REQUEST.lower()
    assert "condition" in lowered and "url" in lowered and "exact sentence" in lowered
    assert "ANSWER:" in REQUEST


def _run_main(monkeypatch: pytest.MonkeyPatch, stdin: str) -> tuple[int, str, str]:
    raw = io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8")), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdin", raw)
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    return sources_hook.main([]), out.getvalue(), err.getvalue()


def test_broken_input_lets_it_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    code, out, err = _run_main(monkeypatch, "{not json")
    assert code == 0 and out == "" and err.count("\n") == 1


def test_missing_transcript_lets_it_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event(tmp_path / "missing.jsonl")
    code, out, _ = _run_main(monkeypatch, json.dumps(event))
    assert code == 0 and out == ""


def test_main_prints_the_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event(_transcript(tmp_path, ["WebSearch"]))
    code, out, _ = _run_main(monkeypatch, json.dumps(event))
    assert code == 0 and json.loads(out)["decision"] == "block"


def test_install_sources_wires_stop_only(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "", "hooks": [{"type": "command", "command": "theirs"}]}
    path.write_text(json.dumps({"hooks": {"Stop": [theirs]}}), "utf-8")
    apply(plan(path, HarnessConfig(), sources=True))
    doc = json.loads(path.read_text("utf-8"))
    assert SOURCES_HOOKS == {"Stop": ""}
    ours = [e for e in doc["hooks"]["Stop"] if e["hooks"][0]["command"] == SOURCES_COMMAND]
    assert len(ours) == 1
    assert [e for e in doc["hooks"]["Stop"] if e is not ours[0]][0]["hooks"][0]["command"] == (
        "theirs"
    )
    wired = [k for k, v in doc["hooks"].items() if SOURCES_COMMAND in json.dumps(v)]
    assert wired == ["Stop"]
    again = plan(path, HarnessConfig(), sources=True)
    assert not again.added and not again.removed


def test_install_without_sources_writes_nothing_of_ours(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = plan(path, HarnessConfig())
    assert SOURCES_COMMAND not in json.dumps(settings.merged)
    apply(plan(path, HarnessConfig(), sources=True))
    removal = plan(path, HarnessConfig(), sources=False)
    assert any("(sources)" in line for line in removal.removed)
    apply(removal)
    assert SOURCES_COMMAND not in path.read_text("utf-8")
