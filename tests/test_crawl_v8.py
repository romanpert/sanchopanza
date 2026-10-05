"""Crawl v8 in development, every piece off by default: the echoed wrapper cut from the evaluate's
result (`SANCHOPANZA_CRAWL_ECHO=short`, PostToolUse) and the strategy line only on requests that
gather data (`SANCHOPANZA_CRAWL_LINE_AT=prompt`, UserPromptSubmit). No model, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

from sanchopanza.harness import crawl_hook as crawl

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAYWRIGHT = "mcp__playwright__browser_evaluate"
AGENTS = (
    "async () => {\n  const r = await fetch('/api?page=2');\n  return (await r.json()).length;\n}"
)
RESULT = '{\n  "result": 3,\n  "sanchopanza": "sanchopanza: fetched JSON rows 5, distinct 4."\n}'


def _conf4():
    spec = importlib.util.spec_from_file_location(
        "browse_nav_confirm4_v8", ROOT / "benchmarks/browse/nav_confirm4.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["browse_nav_confirm4_v8"] = module
    spec.loader.exec_module(module)
    return module


def _echoed(function: str, result: str = RESULT) -> str:
    """What Playwright MCP returns for an evaluate: the result, then the code it ran, quoted."""
    quoted = "'" + function.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"
    return (
        f"### Result\n{result}\n### Ran Playwright code\n```js\nawait page.evaluate({quoted});\n```"
        "\n### Page\n- Page URL: https://example.org/list"
    )


def _post(text: str, env: dict, tool: str = PLAYWRIGHT, as_blocks: bool = True) -> dict | None:
    response = [{"type": "text", "text": text}] if as_blocks else text
    event = {"hook_event_name": "PostToolUse", "tool_name": tool,
             "tool_input": {"function": "() => 1"}, "tool_response": response}  # fmt: skip
    return crawl.handle(event, env=env)


ECHO_ON = {"SANCHOPANZA_CRAWL_ECHO": "short"}


def test_the_echoed_wrapper_is_replaced_by_one_line_and_the_result_is_kept():
    text = _echoed(crawl.wrap(AGENTS, 120, notes=2))
    out = _post(text, ECHO_ON)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    new = out["updatedToolOutput"]
    assert isinstance(new, list) and new[0]["type"] == "text"
    body = new[0]["text"]
    assert body.startswith(f"### Result\n{RESULT}\n### Ran Playwright code\n")
    assert body.endswith("### Page\n- Page URL: https://example.org/list")
    assert crawl.MARK not in body and "const sp" not in body
    assert "fetched JSON rows 5, distinct 4." in body


def test_a_plain_string_response_is_rewritten_as_a_string():
    out = _post(_echoed(crawl.wrap(AGENTS, 120, notes=2)), ECHO_ON, as_blocks=False)
    assert crawl.MARK not in out["hookSpecificOutput"]["updatedToolOutput"]


def test_the_wrapper_costs_under_1000_characters_over_the_guard_alone():
    """The measure the echo cut is for: Playwright MCP repeats the code it ran in every result,
    and v7's wrapper made that about 2,900 characters longer than the guard alone."""
    guard_only = len(_echoed(crawl.wrap(AGENTS, 120)))
    v7 = len(_echoed(crawl.wrap(AGENTS, 120, notes=True)))
    v8 = _post(_echoed(crawl.wrap(AGENTS, 120, notes=2)), ECHO_ON)
    after = len(v8["hookSpecificOutput"]["updatedToolOutput"][0]["text"])
    assert v7 - guard_only > 2500, "before: the notes' wrapper, echoed"
    assert after - guard_only < 1000, "after: the echo cut, with v8's larger wrapper"


@pytest.mark.parametrize(
    ("env", "text", "tool"),
    [
        ({}, "WRAPPED", PLAYWRIGHT),  # off by default
        ({"SANCHOPANZA_CRAWL_ECHO": "0"}, "WRAPPED", PLAYWRIGHT),
        (ECHO_ON, "PLAIN", PLAYWRIGHT),  # not our wrapper: no identity rewrite
        (ECHO_ON, "WRAPPED", "mcp__playwright__browser_snapshot"),
        (ECHO_ON, "### Result\n3", PLAYWRIGHT),  # nothing echoed
    ],
)
def test_the_result_is_left_alone(env, text, tool):
    text = {"WRAPPED": _echoed(crawl.wrap(AGENTS, 120, notes=2)), "PLAIN": _echoed(AGENTS)}.get(
        text, text
    )
    assert _post(text, env, tool=tool) is None


def test_the_cut_approves_nothing_and_touches_no_other_field():
    out = _post(_echoed(crawl.wrap(AGENTS, 120, notes=True)), ECHO_ON)
    assert set(out["hookSpecificOutput"]) == {"hookEventName", "updatedToolOutput"}
    assert set(out) == {"hookSpecificOutput"}


# --- the line only on requests that gather data ----------------------------------------------

AT_PROMPT = {"SANCHOPANZA_CRAWL_LINE_AT": "prompt", "SANCHOPANZA_CRAWL_LINE_VERSION": "6"}


def _prompt(text: str, env: dict) -> dict | None:
    return crawl.handle({"hook_event_name": "UserPromptSubmit", "prompt": text}, env=env)


def test_every_crawl_of_confirmation_4_gets_the_line_and_no_interactive_task_does():
    conf4 = _conf4()
    for tid, url, question, _ in conf4.TASKS:
        prompt = f"Open {url} in the browser. {question}"  # as nav_e2e sends it
        out = _prompt(prompt, AT_PROMPT)
        if tid.startswith("G"):
            specific = out["hookSpecificOutput"]
            assert specific["hookEventName"] == "UserPromptSubmit", tid
            assert specific["additionalContext"] == crawl.STRATEGY_LINE_V6, tid
        else:
            assert out is None, tid


@pytest.mark.parametrize(
    ("prompt", "line"),
    [
        ("List all the open issues across every page.", True),
        ("What is the total number of products?", True),
        ("Count the rows in this table.", True),
        ("Log in and count the items in my cart.", False),
        ("Add to cart the cheapest product and check out.", False),
        ("Fill the form and submit it.", False),
        ("Book a table for two.", False),
        ("What does this page say about shipping?", False),
        ("Write a summary of this article.", False),
    ],
)
def test_the_line_needs_a_sign_of_gathering_and_none_of_acting(prompt, line):
    assert (_prompt(prompt, AT_PROMPT) is not None) is line


def test_at_prompt_the_session_start_carries_no_line_but_the_guard_stays():
    start = {"hook_event_name": "SessionStart", "source": "startup"}
    assert crawl.handle(start, env=AT_PROMPT) is None
    evaluate = {"hook_event_name": "PreToolUse", "tool_name": PLAYWRIGHT,
                "tool_input": {"function": "() => 1"}}  # fmt: skip
    wrapped = crawl.handle(evaluate, env=AT_PROMPT)["hookSpecificOutput"]["updatedInput"]
    assert wrapped["function"].startswith(crawl.MARK)


def test_by_default_the_line_stays_at_session_start_and_prompts_get_nothing():
    start = {"hook_event_name": "SessionStart", "source": "startup"}
    assert crawl.handle(start, env={})["hookSpecificOutput"]["additionalContext"] == (
        crawl.STRATEGY_LINE_V5
    )
    assert _prompt("How many products are there?", {}) is None
    assert _prompt("How many products are there?", {"SANCHOPANZA_CRAWL_LINE_AT": "session"}) is None


def test_the_line_switched_off_stays_off_at_prompt_too():
    env = {**AT_PROMPT, "SANCHOPANZA_CRAWL_LINE": "0"}
    assert _prompt("How many products are there?", env) is None


def test_the_v8_events_are_named_for_whoever_wires_them():
    assert crawl.V8_HOOKS == {"PostToolUse": r"mcp__.*__browser_evaluate", "UserPromptSubmit": ""}


def test_the_command_line_hook_answers_a_prompt(monkeypatch, capsys):
    import io

    monkeypatch.setenv("SANCHOPANZA_CRAWL_LINE_AT", "prompt")
    monkeypatch.delenv("SANCHOPANZA_CRAWL_LINE_VERSION", raising=False)
    event = {"hook_event_name": "UserPromptSubmit", "prompt": "How many books cost under 20?"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    assert crawl.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["additionalContext"] == crawl.STRATEGY_LINE_V5
