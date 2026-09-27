"""The opt-in Stop hook: a calibrated "is it done?" before Claude Code is allowed to stop.

Measured on 655 AgentDojo trajectories labelled by the benchmark's own environment check
(`docs/results/2026-09-25-completion/`): the agent's own word is right 52 % of the time, the
completion question 94 %. The hook blocks a stop only below the derived cut, never twice in a
row (`stop_hook_active`), and on any failure lets the stop through.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sanchopanza import Squire
from sanchopanza.contract import Answer, Decision
from sanchopanza.harness.claude_code import handle, transcript_task_and_record
from sanchopanza.harness.generic import Guardian, HarnessConfig
from sanchopanza.harness.install import matchers


def _transcript(tmp_path: Path) -> Path:
    lines = [
        {"type": "user", "message": {"role": "user", "content": "old request, finished"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "done with that"}],
            },
        },
        {
            "type": "user",
            "message": {"role": "user", "content": "Invite Dora and tell her the date"},
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Inviting Dora."},
                    {"type": "tool_use", "id": "t1", "name": "invite", "input": {"who": "Dora"}},
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "invited"}],
            },
        },
        {
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "All done."}]},
        },
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return path


class Fixed:
    name = "fixed"

    def __init__(self, p):
        self.p = p
        self.states = []

    async def decide(self, point, state, questions):
        self.states.append(state)
        answers = (
            {} if self.p is None else {"done": Answer("truth", abs(2 * self.p - 1), truth=self.p)}
        )
        return Decision(point, answers, "fixed", "m")


def _run(tmp_path, p, *, active=False, check=True):
    decider = Fixed(p)
    guardian = Guardian(Squire(decider), HarnessConfig(check_done=check))
    data = {
        "hook_event_name": "Stop",
        "transcript_path": str(_transcript(tmp_path)),
        "stop_hook_active": active,
    }
    return asyncio.run(handle(data, guardian)), decider


def test_the_task_is_the_last_real_prompt_and_the_record_what_followed(tmp_path):
    task, record = transcript_task_and_record(_transcript(tmp_path))
    assert task == "Invite Dora and tell her the date"
    assert "AGENT ACTION: invite" in record and "TOOL RESULT: invited" in record
    assert "old request" not in record


def test_blocks_when_confidently_not_done(tmp_path):
    out, decider = _run(tmp_path, 0.1)
    assert out["decision"] == "block"
    assert "Invite Dora" in decider.states[0]["task"]


def test_lets_the_stop_through_when_done_or_unsure_of_nothing(tmp_path):
    assert _run(tmp_path, 0.9)[0] == {}
    assert _run(tmp_path, None)[0] == {}  # no data: the harness's own rule


def test_never_blocks_twice_in_a_row(tmp_path):
    out, decider = _run(tmp_path, 0.1, active=True)
    assert out == {} and decider.states == []


def test_off_unless_asked(tmp_path):
    out, decider = _run(tmp_path, 0.1, check=False)
    assert out == {} and decider.states == []


def test_a_missing_transcript_lets_the_stop_through(tmp_path):
    guardian = Guardian(Squire(Fixed(0.1)), HarnessConfig(check_done=True))
    data = {"hook_event_name": "Stop", "transcript_path": str(tmp_path / "none.jsonl")}
    assert asyncio.run(handle(data, guardian)) == {}


def test_install_wires_stop_only_when_asked():
    assert matchers(HarnessConfig())["Stop"] == ""
    assert matchers(HarnessConfig(check_done=True))["Stop"] == "*"


def test_install_check_done_writes_the_stop_hook_and_its_env(tmp_path, capsys):
    from sanchopanza import cli

    settings = tmp_path / "settings.json"
    assert cli.main(["install", "--check-done", "--path", str(settings), "--write"]) == 0
    written = json.loads(settings.read_text(encoding="utf-8"))
    assert written["hooks"]["Stop"][0]["hooks"][0]["command"] == "sanchopanza hook"
    assert written["env"]["SANCHO_CHECK_DONE"] == "1"
    # and running it again without the flag removes both
    assert cli.main(["install", "--path", str(settings), "--write"]) == 0
    again = json.loads(settings.read_text(encoding="utf-8"))
    assert not again["hooks"].get("Stop") and "SANCHO_CHECK_DONE" not in again.get("env", {})
