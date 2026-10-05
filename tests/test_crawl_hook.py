"""The crawl hook: the strategy line at SessionStart and the evaluate guard at PreToolUse.
The wrapped code is run in Node to check it behaves; no model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from sanchopanza.harness import crawl_hook as crawl

ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
HUNG = "async () => { while (true) { await new Promise(r => setTimeout(r, 10)); } }"
PLAYWRIGHT = "mcp__playwright__browser_evaluate"


def _lines():
    spec = importlib.util.spec_from_file_location(
        "browse_strategy_lines", ROOT / "benchmarks/browse/strategy_lines.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(function: str, tool: str = PLAYWRIGHT, **extra) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"function": function, **extra}}  # fmt: skip


def test_the_line_is_v5_word_for_word():
    assert crawl.STRATEGY_LINE == _lines().STRATEGY_HINT_V5


def test_v6_is_the_benchmark_line_word_for_word_and_keeps_v5s_frame():
    v6 = crawl.STRATEGY_LINE_V6
    assert v6 == _lines().STRATEGY_HINT_V6
    assert v6 != crawl.STRATEGY_LINE_V5 and v6.isascii()
    head, tail = crawl.STRATEGY_LINE_V5.split(" Make it also return")
    assert v6.startswith(head) and v6.endswith("rather than walking the pages.")
    for clause in (
        "never a URL pattern you guessed",
        "computed by the code and not assumed",
        "not a word or a regex anywhere",
        "by its URL or id, never by its name",
    ):
        assert clause in v6  # fmt: skip


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, "V5"), ("5", "V5"), ("6", "V6"), ("v6", "V6"), (" 6 ", "V6"), ("7", "V5"), ("", "V5")],
)
def test_the_line_version_is_chosen_by_the_environment_and_defaults_to_v5(raw, expected):
    env = {} if raw is None else {"SANCHOPANZA_CRAWL_LINE_VERSION": raw}
    out = crawl.handle({"hook_event_name": "SessionStart", "source": "startup"}, env=env)
    assert out["hookSpecificOutput"]["additionalContext"] == getattr(
        crawl, f"STRATEGY_LINE_{expected}"
    )
    assert crawl.STRATEGY_LINE == crawl.STRATEGY_LINE_V5, "the default stays v5 until confirmed"


def test_switching_the_line_off_wins_over_its_version():
    env = {"SANCHOPANZA_CRAWL_LINE": "0", "SANCHOPANZA_CRAWL_LINE_VERSION": "6"}
    assert crawl.handle({"hook_event_name": "SessionStart"}, env=env) is None


def test_the_hook_process_reads_the_version_from_its_environment():
    event = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})
    done = _hook(event, SANCHOPANZA_CRAWL_LINE_VERSION="6")
    context = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context == crawl.STRATEGY_LINE_V6


def test_session_start_adds_the_line_and_can_be_switched_off():
    out = crawl.handle({"hook_event_name": "SessionStart", "source": "startup"}, env={})
    assert out["hookSpecificOutput"] == {
        "hookEventName": "SessionStart",
        "additionalContext": crawl.STRATEGY_LINE,
    }
    off = {"SANCHOPANZA_CRAWL_LINE": "0"}
    assert crawl.handle({"hook_event_name": "SessionStart"}, env=off) is None


@pytest.mark.parametrize(
    "tool", [PLAYWRIGHT, "mcp__plugin_playwright_playwright__browser_evaluate"]
)
def test_an_evaluate_on_any_server_is_rewritten_and_keeps_its_other_arguments(tool):
    out = crawl.guard(_event("() => 1", tool=tool, element="row", ref="e5"), limit_s=30)
    updated = out["hookSpecificOutput"]["updatedInput"]
    assert updated["element"] == "row" and updated["ref"] == "e5"
    assert "() => 1" in updated["function"] and "30000" in updated["function"]


def test_the_guard_never_approves_a_call():
    out = crawl.guard(_event("() => 1"), limit_s=30)["hookSpecificOutput"]
    assert "permissionDecision" not in out, "the user's permission rules must still apply"


@pytest.mark.parametrize(
    "event",
    [
        _event("() => 1", tool="mcp__playwright__browser_click"),
        _event("() => 1", tool="browser_evaluate"),
        _event("   "),
        {"hook_event_name": "PreToolUse", "tool_name": PLAYWRIGHT, "tool_input": "() => 1"},
        {"hook_event_name": "PostToolUse", "tool_name": PLAYWRIGHT},
    ],
)
def test_everything_else_is_left_alone(event):
    assert crawl.handle(event, env={}) is None


def test_already_wrapped_code_is_never_wrapped_twice():
    once = crawl.guard(_event("() => 1"), 30)["hookSpecificOutput"]["updatedInput"]["function"]
    assert crawl.guard(_event(once), 30) is None


@pytest.mark.parametrize(
    ("raw", "expected"), [("", 120), ("45", 45), ("soon", 120), ("0", 120), ("-3", 120)]
)
def test_the_limit_comes_from_the_environment_and_a_bad_one_falls_back(raw, expected):
    assert crawl.limit_seconds({"SANCHOPANZA_EVALUATE_LIMIT_S": raw}) == expected


def _run(function: str, *args: str) -> dict:
    script = (
        f"const f = {function};\n"
        "const say = (o) => { console.log(JSON.stringify(o)); process.exit(0); };\n"
        f"Promise.resolve(f({', '.join(args)}))"
        ".then(v => say({ok: v}), e => say({err: String(e)}));"
    )  # fmt: skip
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    return json.loads(done.stdout)


@pytest.mark.skipif(NODE is None, reason="needs node")
def test_a_hung_async_loop_becomes_an_error_the_agent_can_read():
    result = _run(crawl.wrap(HUNG, limit_s=1))
    assert "err" in result and "stopped after 1 s" in result["err"]


@pytest.mark.skipif(NODE is None, reason="needs node")
@pytest.mark.parametrize(
    ("function", "args", "value"),
    [
        ("() => 41 + 1", (), 42),
        ("async () => { await new Promise(r => setTimeout(r, 50)); return 'done'; }", (), "done"),
        ("(element) => element * 2", ("21",), 42),
        ("function () { return [1, 2, 3].length; }", (), 3),
        ("() => 42 // the answer", (), 42),
        ("async () => {\n  return 7;\n}\n// trailing note", (), 7),
    ],
)
def test_code_that_returns_in_time_returns_what_it_always_returned(function, args, value):
    assert _run(crawl.wrap(function, limit_s=5), *args) == {"ok": value}


def _hook(stdin: str, **env: str) -> subprocess.CompletedProcess:
    code = "from sanchopanza.harness.crawl_hook import main; raise SystemExit(main())"
    return subprocess.run(
        [sys.executable, "-c", code],
        input=stdin.encode("utf-8"),
        capture_output=True,
        env={**os.environ, **env},
        timeout=60,
    )


def test_the_hook_process_answers_an_evaluate():
    done = _hook(json.dumps(_event("() => 1")), SANCHOPANZA_EVALUATE_LIMIT_S="9")
    assert done.returncode == 0
    out = json.loads(done.stdout)
    assert "9000" in out["hookSpecificOutput"]["updatedInput"]["function"]


@pytest.mark.parametrize("stdin", ["not json", "[1, 2]", ""])
def test_the_hook_process_fails_open(stdin):
    done = _hook(stdin)
    assert done.returncode == 0 and done.stdout == b""


def test_the_hook_imports_nothing_heavy():
    probe = (
        "import sanchopanza.harness.crawl_hook, sys, json\n"
        "sys.stdout.write(json.dumps(sorted(sys.modules)))"
    )
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    loaded = set(json.loads(done.stdout))
    heavy = {"asyncio", "importlib.metadata", "sanchopanza.squire", "sanchopanza.providers"}
    assert not loaded & heavy
