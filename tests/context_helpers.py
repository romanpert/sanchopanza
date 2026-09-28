"""A hand-written Claude Code transcript and a scripted decider, for the context tests.

No test here calls a paid provider. The transcript is synthetic: one prompt, a Read, a failing
Bash, an Edit, the same Read again, the same Bash passing, and a closing reply, with a
sidechain entry and a meta entry that must be skipped.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from sanchopanza import Decision, truth
from sanchopanza.contract import Question

APP = "def add(a, b):\n    return a - b\n" + "# padding line\n" * 60
FAIL = "Exit code 1\n" + "FAILED tests/test_app.py::test_add - assert -1 == 3\n" * 12
PASS = "1 passed in 0.02s\n" + "collected 1 item\n" * 40


def _assistant(mid: str, block: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {"id": mid, "role": "assistant", "content": [block]},
        **extra,
    }


def _result(tid: str, content: Any, *, error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tid, "content": content}
    if error:
        block["is_error"] = True
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def _use(tid: str, name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": tid, "name": name, "input": arguments}


ENTRIES: list[dict[str, Any]] = [
    {"type": "summary", "summary": "an older session", "leafUuid": "x"},
    {"type": "user", "message": {"role": "user", "content": "Fix the failing test in app.py"}},
    _assistant("m1", {"type": "text", "text": "Reading the file first."}),
    _assistant("m1", _use("t1", "Read", file_path="/p/app.py")),
    _result("t1", APP),
    _assistant("m2", _use("t2", "Bash", command="pytest -q")),
    _result("t2", FAIL, error=True),
    _assistant("side", _use("s1", "Read", file_path="/p/x.py"), isSidechain=True),
    {"type": "user", "isMeta": True, "message": {"role": "user", "content": "Caveat: local"}},
    _assistant("m3", _use("t3", "Edit", file_path="/p/app.py", old_string="-", new_string="+")),
    _result("t3", "The file /p/app.py has been updated."),
    _assistant("m4", _use("t4", "Read", file_path="/p/app.py")),
    _result("t4", [{"type": "text", "text": APP.replace("-", "+")}]),
    _assistant("m5", _use("t5", "Bash", command="pytest -q")),
    _result("t5", PASS),
    _assistant("m6", {"type": "text", "text": "Fixed: add now adds."}),
    {"type": "system", "subtype": "stop_hook_summary", "content": "done"},
]


def write_transcript(path: Path, entries: list[dict[str, Any]] | None = None) -> Path:
    lines = [json.dumps(e) for e in (ENTRIES if entries is None else entries)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class ScriptedDecider:
    """Answers every Truth with `answer(point, key, state)`; None leaves it unanswered."""

    name = "scripted"
    accepts_attachments = False

    def __init__(self, answer: Callable[[str, str, Any], float | None]) -> None:
        self._answer = answer
        self.calls: list[tuple[str, Any, dict[str, Question]]] = []

    async def decide(self, point: str, state: Any, questions: Mapping[str, Question]) -> Decision:
        self.calls.append((point, state, dict(questions)))
        answers = {}
        for key in questions:
            p = self._answer(point, key, state)
            if p is not None:
                answers[key] = truth(p)
        return Decision(point=point, answers=answers, provider=self.name, model="scripted-1")


class BrokenDecider:
    name = "broken"
    accepts_attachments = False

    async def decide(self, point: str, state: Any, questions: Mapping[str, Question]) -> Decision:
        raise RuntimeError("provider down")
