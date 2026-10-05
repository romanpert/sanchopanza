"""Crawl v8.1 in development, both pieces off by default: the notes moved to the head of the
evaluate's result (`SANCHOPANZA_CRAWL_NOTES_AT=front`, PostToolUse) and the session's first
screenshot denied in favour of a snapshot (`SANCHOPANZA_CRAWL_SHOT=snapshot-first`,
PreToolUse). No model, no money."""

from __future__ import annotations

import json
import re

import pytest

from sanchopanza.harness import crawl_hook as crawl
from sanchopanza.harness.install import CRAWL_COMMAND, CRAWL_HOOKS, _merge_crawl, _merge_owned

EVALUATE = "mcp__playwright__browser_evaluate"
SHOT = "mcp__playwright__browser_take_screenshot"
NOTE = "sanchopanza: this call fetched nothing, so it read only the open page, which says: " + (
    '"total":194. If the request covers more than this page, fetch the rest before answering.'
)
IN_JSON = json.dumps(NOTE)[1:-1]  # as the note sits inside the pretty-printed value
FRONT = {"SANCHOPANZA_CRAWL_NOTES_AT": "front"}
BOTH = {**FRONT, "SANCHOPANZA_CRAWL_ECHO": "short"}


def _big_result(note: str = NOTE, items: int = 400) -> str:
    """What the wrapper returns through Playwright MCP: `{result, sanchopanza}`, pretty-printed,
    with a value large enough (G1 r1 of v8: 64,577 characters) for Claude Code to persist it."""
    value = {"result": {"products": [{"id": i, "title": f"Product {i}", "description": "x" * 120}
                                     for i in range(items)]},
             "sanchopanza": note}  # fmt: skip
    return json.dumps(value, indent=2)


def _evaluate_result(result: str, wrapped: bool = True) -> str:
    function = crawl.wrap("async () => 1", 120, notes=2) if wrapped else "async () => 1"
    quoted = json.dumps(function).replace('"', "'")
    return (
        f"### Result\n{result}\n### Ran Playwright code\n```js\nawait page.evaluate({quoted});\n```"
        "\n### Page\n- Page URL: https://dummyjson.com/products"
    )


def _post(text: str, env: dict, as_blocks: bool = True) -> dict | None:
    response = [{"type": "text", "text": text}] if as_blocks else text
    event = {"hook_event_name": "PostToolUse", "tool_name": EVALUATE,
             "tool_input": {"function": "() => 1"}, "tool_response": response}  # fmt: skip
    return crawl.handle(event, env=env)


def _body(out: dict) -> str:
    new = out["hookSpecificOutput"]["updatedToolOutput"]
    return new[0]["text"] if isinstance(new, list) else new


# --- a) the notes at the head of the result ---------------------------------------------------


@pytest.mark.parametrize("env", [FRONT, BOTH])
def test_a_note_at_the_end_of_a_result_over_50000_characters_comes_first(env):
    text = _evaluate_result(_big_result())
    assert len(text) > 50_000 and text.index(IN_JSON) > 50_000
    body = _body(_post(text, env))
    assert body.index(NOTE) < 500
    assert body.startswith(crawl.NOTES_HEAD)
    assert body.count(NOTE) == 1 and IN_JSON not in body, "moved, not copied"
    result = body.split("### Result\n", 1)[1].split("\n### Ran Playwright code", 1)[0]
    assert json.loads(result) == {"result": json.loads(_big_result())["result"]}


def test_with_the_echo_cut_too_the_wrapper_is_gone_and_the_page_line_kept():
    body = _body(_post(_evaluate_result(_big_result()), BOTH))
    assert crawl.MARK not in body and crawl.ECHO_LINE in body
    assert body.endswith("### Page\n- Page URL: https://dummyjson.com/products")


def test_a_note_in_an_error_message_comes_first_too():
    text = "### Error\nError: page.evaluate: TypeError: x is not a function | " + NOTE.replace(
        "this call fetched nothing", "3 of 40 fetches answered 429"
    )
    body = _body(_post(text, FRONT))
    assert body.startswith(crawl.NOTES_HEAD + "\nsanchopanza: 3 of 40 fetches answered 429")
    assert body.endswith("### Error\nError: page.evaluate: TypeError: x is not a function")


def test_a_plain_string_response_is_rewritten_as_a_string():
    out = _post(_evaluate_result(_big_result()), FRONT, as_blocks=False)
    assert isinstance(out["hookSpecificOutput"]["updatedToolOutput"], str)
    assert _body(out).index(NOTE) < 500


def test_a_note_with_quotes_and_escapes_survives_the_move():
    note = 'sanchopanza: 2 fetched pages had exactly the text of an earlier URL (a "b" \\ c).'
    body = _body(_post(_evaluate_result(_big_result(note=note, items=3)), FRONT))
    assert body.startswith(f"{crawl.NOTES_HEAD}\n{note}\n### Result\n")


@pytest.mark.parametrize(
    ("env", "text"),
    [
        ({}, "NOTED"),  # off by default
        ({"SANCHOPANZA_CRAWL_NOTES_AT": "end"}, "NOTED"),
        (FRONT, "### Result\n3\n### Page\n- Page URL: https://x.org"),  # no note
        (FRONT, '### Result\n{\n  "sanchopanza": "mine"\n}'),  # the agent's own key
    ],
)
def test_the_result_is_left_alone(env, text):
    text = _evaluate_result(_big_result(items=3), wrapped=False) if text == "NOTED" else text
    assert _post(text, env) is None


def test_off_by_default_the_echo_cut_alone_leaves_the_note_where_it_was():
    text = _evaluate_result(_big_result())
    body = _body(_post(text, {"SANCHOPANZA_CRAWL_ECHO": "short"}))
    assert body.index(IN_JSON) > 50_000 and NOTE not in body


# --- b) the session's first screenshot: a snapshot first --------------------------------------

SHOT_ON = {"SANCHOPANZA_CRAWL_SHOT": "snapshot-first"}


def _shot(env: dict, session: str = "s1", tool: str = SHOT) -> dict | None:
    event = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": session,
             "tool_input": {"type": "png"}}  # fmt: skip
    return crawl.handle(event, env=env)


@pytest.fixture
def shot_env(tmp_path):
    return {**SHOT_ON, "SANCHOPANZA_CRAWL_DIR": str(tmp_path)}


def test_the_first_screenshot_is_denied_with_a_short_neutral_reason_and_the_second_passes(
    shot_env,
):
    first = _shot(shot_env)["hookSpecificOutput"]
    assert first == {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                     "permissionDecisionReason": crawl.SHOT_REASON}  # fmt: skip
    assert "browser_snapshot" in crawl.SHOT_REASON and len(crawl.SHOT_REASON) < 240
    assert re.search(r"take_screenshot again", crawl.SHOT_REASON)
    assert _shot(shot_env) is None
    assert _shot(shot_env) is None


def test_each_session_has_its_own_first_screenshot(shot_env):
    assert _shot(shot_env, "a") is not None
    assert _shot(shot_env, "b") is not None
    assert _shot(shot_env, "a") is None


@pytest.mark.parametrize(
    ("env_extra", "session", "tool"),
    [
        ({"SANCHOPANZA_CRAWL_SHOT": ""}, "s1", SHOT),  # off by default
        ({"SANCHOPANZA_CRAWL_SHOT": "0"}, "s1", SHOT),
        ({}, "", SHOT),  # no session to remember it by: fail open
        ({}, "s1", "mcp__playwright__browser_snapshot"),
        ({}, "s1", "mcp__playwright__browser_click"),
    ],
)
def test_the_call_is_left_alone(shot_env, env_extra, session, tool):
    assert _shot({**shot_env, **env_extra}, session, tool) is None


def test_any_mcp_servers_screenshot_tool_counts(shot_env):
    assert _shot(shot_env, tool="mcp__browser__browser_take_screenshot") is not None


def test_an_unwritable_state_dir_lets_the_screenshot_through(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    env = {**SHOT_ON, "SANCHOPANZA_CRAWL_DIR": str(blocker / "under")}
    assert _shot(env) is None


def test_with_the_shot_switch_on_the_evaluate_is_still_guarded(shot_env):
    event = {"hook_event_name": "PreToolUse", "tool_name": EVALUATE, "session_id": "s1",
             "tool_input": {"function": "() => 1"}}  # fmt: skip
    wrapped = crawl.handle(event, env=shot_env)["hookSpecificOutput"]["updatedInput"]
    assert wrapped["function"].startswith(crawl.MARK)


def test_v81_hooks_put_the_screenshot_beside_the_evaluate_in_one_pre_tool_use_entry():
    matcher = crawl.V81_HOOKS["PreToolUse"]
    for tool in (EVALUATE, SHOT, "mcp__x__browser_take_screenshot"):
        assert re.fullmatch(matcher, tool), tool
    for tool in ("mcp__playwright__browser_snapshot", "mcp__playwright__browser_click"):
        assert not re.fullmatch(matcher, tool), tool
    settings, _a, _r = _merge_crawl({}, True, command="cmd")
    settings, _a, _r = _merge_owned(settings, True, crawl.V8_HOOKS, "cmd", CRAWL_COMMAND, "crawl")
    settings, _a, _r = _merge_owned(settings, True, crawl.V81_HOOKS, "cmd", CRAWL_COMMAND, "c")
    pre = settings["hooks"]["PreToolUse"]
    assert [e["matcher"] for e in pre] == [matcher]
    assert settings["hooks"]["SessionStart"][0]["matcher"] == CRAWL_HOOKS["SessionStart"]
