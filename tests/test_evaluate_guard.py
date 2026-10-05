"""The evaluate guard: a PreToolUse hook that puts a time limit on every browser_evaluate.
The wrapped code is run in Node to check it behaves; no model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_evaluate_guard", ROOT / "benchmarks/browse/evaluate_guard.py"
)
guard = importlib.util.module_from_spec(spec)
sys.modules["browse_evaluate_guard"] = guard
spec.loader.exec_module(guard)

NODE = shutil.which("node")
HUNG = "async () => { while (true) { await new Promise(r => setTimeout(r, 10)); } }"


def _event(function: str, tool: str = guard.EVALUATE, **extra) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"function": function, **extra}}  # fmt: skip


def test_an_evaluate_is_rewritten_and_keeps_its_other_arguments():
    out = guard.decide(_event("() => 1", element="row", ref="e5"), limit_s=30)
    updated = out["hookSpecificOutput"]["updatedInput"]
    assert updated["element"] == "row" and updated["ref"] == "e5"
    assert "() => 1" in updated["function"] and "30000" in updated["function"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_other_tools_and_already_wrapped_code_are_left_alone():
    assert guard.decide(_event("() => 1", tool="mcp__playwright__browser_click"), 30) is None
    once = guard.decide(_event("() => 1"), 30)["hookSpecificOutput"]["updatedInput"]["function"]
    assert guard.decide(_event(once), 30) is None, "never wrapped twice"


def _run(function: str, *args: str) -> subprocess.CompletedProcess:
    script = (
        f"const f = {function};\n"
        "const say = (o) => { console.log(JSON.stringify(o)); process.exit(0); };\n"
        f"Promise.resolve(f({', '.join(args)}))"
        ".then(v => say({ok: v}), e => say({err: String(e)}));"
    )  # fmt: skip
    return subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)


@pytest.mark.skipif(NODE is None, reason="needs node")
def test_a_hung_async_loop_becomes_an_error_the_agent_can_read():
    wrapped = guard.wrap(HUNG, limit_s=1)
    result = json.loads(_run(wrapped).stdout)
    assert "err" in result and "stopped after 1 s" in result["err"]


@pytest.mark.skipif(NODE is None, reason="needs node")
@pytest.mark.parametrize(
    ("function", "args", "value"),
    [
        ("() => 41 + 1", (), 42),
        ("async () => { await new Promise(r => setTimeout(r, 50)); return 'done'; }", (), "done"),
        ("(element) => element * 2", ("21",), 42),
        ("function () { return [1, 2, 3].length; }", (), 3),
    ],
)
def test_code_that_returns_in_time_returns_what_it_always_returned(function, args, value):
    result = json.loads(_run(guard.wrap(function, limit_s=5), *args).stdout)
    assert result == {"ok": value}
