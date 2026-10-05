"""Crawl: a Claude Code hook for agents that gather data across many pages of a site.

Two pieces, both with no model and no decision, because neither needs judgment:

- `SessionStart` adds one line of strategy to the session: extract a multi-page crawl in one
  `browser_evaluate` that fetches each page and parses it with `DOMParser`, rather than walking
  the pages one tool call at a time (`STRATEGY_LINE`, v5 of the line in
  `benchmarks/browse/strategy_lines.py`, where each version's reason is kept).
- `PreToolUse` on any MCP server's `browser_evaluate` races the function against a timer
  (`wrap`). Playwright MCP never stops an evaluate, so a loop that cannot end hangs the session;
  with the guard it becomes an error the agent reads and can fix. A safety property does not
  belong in a clause the model must obey: with the line saying "cap every loop", the cheap model
  still wrote `while (true)` and one such hang decided a registered confirmation.

The guard only rewrites the call's input. It returns no `permissionDecision`, so the user's
permission rules apply to the rewritten call exactly as they did to the original: installing
it never approves an evaluate that would otherwise have been asked about or refused.

What the guard cannot stop: a synchronous loop with no `await` holds the page's only thread and
no timer fires. What it does not do: kill the loop; an abandoned asynchronous loop keeps running
in the page until it navigates or closes.

Measured (`docs/results/2026-10-02-browse-nav/`, sections 14-17): in development the line made
Haiku 14/15 right at 0.066 USD a crawl against 11/15 at 0.265 unaided, and halved Sonnet where it
walked. Two registered confirmations did NOT confirm it: v2 lost answers; v5 kept them (21/24
against 22/24) and one hang charged at the session cap decided the cost. Without that hang it
would have been 0.73 and cheaper on 6 of 8. The guard is the answer to that hang, verified live.

Environment: `SANCHOPANZA_EVALUATE_LIMIT_S` (default 120; a 50-page fetch crawl measured here
takes well under that), `SANCHOPANZA_CRAWL_LINE=0` to keep the guard and drop the line,
`SANCHOPANZA_CRAWL_LINE_VERSION=6` for line v6 (in development; v5 stays the default),
`SANCHOPANZA_CRAWL_NOTES=1` for notes in each evaluate's result (`crawl_notes`, in development).

v8, in development and off by default, from confirmation 4's misses (README 2026-10-03, section
"Confirmation 4"); v7 is unchanged by any of it:

- `SANCHOPANZA_CRAWL_NOTES=2`: v7's notes plus clicks that never changed the page's text and the
  fetched JSON's rows against its distinct rows (`crawl_notes._V2`).
- `SANCHOPANZA_CRAWL_ECHO=short`: a `PostToolUse` hook replaces the wrapper that Playwright MCP
  echoes under `### Ran Playwright code` with one line, through `updatedToolOutput` (Claude Code
  2.1.287 has it, and `updatedMCPToolOutput` for MCP tools only). The result and the notes are
  left as they are. The echo was about 30 % of what Haiku's interactive tasks cost over the bare
  harness.
- `SANCHOPANZA_CRAWL_LINE_AT=prompt`: the line moves from `SessionStart` to `UserPromptSubmit`, and
  is added only to a prompt that asks to gather (`GATHERS`) and does not ask to act (`ACTS`). The
  guard and the notes stay on for every request.

`install --crawl` wires only `SessionStart` and `PreToolUse`. The two events v8 adds are in
`V8_HOOKS`. Whoever turns the echo cut or `LINE_AT=prompt` on must wire them too, or the echo is
left alone and the line is never added.
Standard library only (the echo cut reuses `autopilot`'s response walk); fail open everywhere.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from collections.abc import Mapping
from typing import Any

from .. import _env
from .crawl_notes import wrap_with_notes
from .hookio import stdin_text, stdout_json

PREFIX = "sanchopanza crawl"
EVALUATE = re.compile(r"^mcp__.+__browser_evaluate$")
MARK = "/* sanchopanza evaluate guard */"
DEFAULT_LIMIT_S = 120

STRATEGY_LINE_V5 = (
    "If the request needs data gathered from many pages of a site (counting, summing, comparing "
    "or listing across pagination or infinite scroll), do not open the pages one by one: write "
    "one browser_evaluate that collects them all and computes the answer in code, with a cap on "
    "every loop far above the site's size (a loop that reaches its cap fell short). Inside it "
    "never click or change the page's location, which destroys the call: fetch() each page's URL "
    "and parse it with DOMParser, or fetch the data the page loads; if the pages are drawn by "
    "JavaScript, find that data (a JSON request or a script on the page) first. Make it also "
    "return how many pages and items it read and whether more remained, and check that against "
    "what the site shows before you answer. If the call errors or falls short, fix the code and "
    "run it again rather than walking the pages."
)
# v6 (development, not confirmed): v5 with four clauses for confirmation 3's misses, each an
# extraction the agent never checked - a guessed `?page=N` scheme, a "nothing remained" it never
# computed, a word matched anywhere in a card, products merged by name (README 2026-10-03).
STRATEGY_LINE_V6 = STRATEGY_LINE_V5.replace(
    "Make it also return how many pages and items it read and whether more remained, and check "
    "that against what the site shows before you answer. ",
    "Follow the pages through the site's own links or data, never a URL pattern you guessed. "
    "Make it also return how many pages and items it read and whether more remained, each "
    "computed by the code and not assumed, and before you answer check them against what the "
    "site states (a total, a last page). Match the field the request names, read from its own "
    "element or a parser, not a word or a regex anywhere in an item's text. Count each item once "
    "by its URL or id, never by its name. ",
)
LINES = {"5": STRATEGY_LINE_V5, "6": STRATEGY_LINE_V6}
# v8 (development): the events `install --crawl` does not wire, for whoever turns v8 on.
V8_HOOKS = {"PostToolUse": r"mcp__.*__browser_evaluate", "UserPromptSubmit": ""}
# A request that gathers across pages, and one that acts on a site (confirmation 4's I1, I2).
GATHERS = re.compile(
    r"\b(?:how many|count(?:s|ing)?|totals?|sum|list all|every|across|number of)\b", re.I
)
ACTS = re.compile(
    r"\b(?:log ?in|sign ?in|check ?out|add to (?:the |my )?cart|fill|submit|book|purchase)\b", re.I
)
ECHO = re.compile(r"### Ran Playwright code\n```js\n(.*?)\n```", re.S)
ECHO_LINE = (
    "### Ran Playwright code\nyour function, inside sanchopanza's evaluate guard (not repeated)"
)
DEFAULT_VERSION = "5"
STRATEGY_LINE = LINES[DEFAULT_VERSION]


def wrap(function: str, limit_s: int, notes: bool | int = False) -> str:
    """The same function, raced against a timer. Its arguments pass through untouched.

    The function sits on lines of its own, so a trailing `// comment` in it cannot swallow the
    parenthesis that closes it. With `notes`, the result also carries what the page and the
    network said during the call (`crawl_notes`); `notes=2` is v8's notes, in development."""
    message = (
        f"evaluate stopped after {limit_s} s: the code did not return. Cap its loops, or fetch "
        "the data the page loads instead of waiting on the page."
    )
    if notes:
        return wrap_with_notes(function, limit_s, message, MARK, version=int(notes))
    return (
        f"{MARK} async (...args) => {{ const run = (\n{function}\n); "
        f"let timer; const limit = new Promise((_, reject) => {{ timer = setTimeout("
        f"() => reject(new Error({json.dumps(message)})), {limit_s * 1000}); }}); "
        f"try {{ return await Promise.race("
        f"[Promise.resolve().then(() => run(...args)), limit]); }} "
        f"finally {{ clearTimeout(timer); }} }}"
    )


def limit_seconds(env: Mapping[str, str] | None = None) -> int:
    raw = _env.get("EVALUATE_LIMIT_S", "", env)
    try:
        value = int(raw) if raw else DEFAULT_LIMIT_S
    except ValueError:
        return DEFAULT_LIMIT_S
    return value if value > 0 else DEFAULT_LIMIT_S


def notes_on(env: Mapping[str, str] | None = None) -> int:
    """`SANCHOPANZA_CRAWL_NOTES=1` turns the result notes on (in development; off by default),
    `2` turns on v8's: 0, 1 or 2."""
    raw = _env.get("CRAWL_NOTES", "", env).strip().lower()
    if raw == "2":
        return 2
    return 1 if raw in {"1", "true", "yes", "on"} else 0


def guard(
    event: Mapping[str, Any], limit_s: int, notes: bool | int = False
) -> dict[str, Any] | None:
    """`PreToolUse`: the evaluate with its function wrapped, or None to leave the call alone."""
    if not EVALUATE.match(str(event.get("tool_name") or "")):
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, Mapping):
        return None
    function = str(tool_input.get("function") or "")
    if not function.strip() or function.lstrip().startswith(MARK):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {**tool_input, "function": wrap(function, limit_s, notes)},
        }
    }


def strategy(
    env: Mapping[str, str] | None = None, event: str = "SessionStart"
) -> dict[str, Any] | None:
    """The line, unless switched off: at `SessionStart`, or at `UserPromptSubmit` (v8)."""
    if _env.get("CRAWL_LINE", "1", env).strip().lower() in {"0", "false", "no", "off"}:
        return None
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": line_for(env)}}


def line_at_prompt(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_CRAWL_LINE_AT=prompt` (v8, development): the line on gathering prompts only."""
    return _env.get("CRAWL_LINE_AT", "", env).strip().lower() == "prompt"


def gathers(prompt: str) -> bool:
    """A request to gather data across pages, with no sign of acting on the site."""
    return bool(GATHERS.search(prompt)) and not ACTS.search(prompt)


def echo_cut_on(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_CRAWL_ECHO=short` (v8, development): cut the echoed wrapper."""
    return _env.get("CRAWL_ECHO", "", env).strip().lower() == "short"


def cut_echo(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """`PostToolUse` on an evaluate: the result with the echoed wrapper replaced by one line, or
    None when no echo of our wrapper is in it (never an identity rewrite, which would race other
    hooks' rewrites of the same result)."""
    from .autopilot import replaced, text_field

    if not EVALUATE.match(str(event.get("tool_name") or "")):
        return None
    response = event.get("tool_response")
    found = text_field(response)
    if found is None:
        return None
    path, text = found
    new = ECHO.sub(lambda m: ECHO_LINE if MARK in m.group(1) else m.group(0), text)
    if new == text:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": replaced(response, path, new),
        }
    }


def line_for(env: Mapping[str, str] | None = None) -> str:
    """The line `SANCHOPANZA_CRAWL_LINE_VERSION` names (5 or 6); v5, the default, for anything
    else, so a typo cannot switch the line off."""
    version = _env.get("CRAWL_LINE_VERSION", DEFAULT_VERSION, env).strip().lstrip("vV")
    return LINES.get(version, LINES[DEFAULT_VERSION])


def handle(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict | None:
    name = event.get("hook_event_name")
    if name == "SessionStart":
        return None if line_at_prompt(env) else strategy(env)
    if name == "PreToolUse":
        return guard(event, limit_seconds(env), notes_on(env))
    if name == "UserPromptSubmit" and line_at_prompt(env):
        prompt = event.get("prompt")
        return strategy(env, name) if isinstance(prompt, str) and gathers(prompt) else None
    if name == "PostToolUse" and echo_cut_on(env):
        return cut_echo(event)
    return None


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        event = json.loads(stdin_text() or "{}")
        if not isinstance(event, Mapping):
            raise ValueError("the event is not a JSON object")
        payload = handle(event)
        if payload is not None:
            stdout_json(payload)
    except Exception as error:  # noqa: BLE001 - fail open, and say so
        with contextlib.suppress(Exception):
            name = error.__class__.__name__
            sys.stderr.write(f"{PREFIX}: left the call alone ({name}: {error})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
