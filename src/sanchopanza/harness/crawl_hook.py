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

v8.1, in development and off by default, from v8's round (README 2026-10-03, "v8 development"):

- `SANCHOPANZA_CRAWL_NOTES_AT=front`: the `PostToolUse` hook moves the notes from the end of the
  evaluate's result to its head. In G1 a note sat at character 64,295 of 64,577; Claude Code
  persisted the result and showed the agent a 2 KB preview, so the note was never read.
- `SANCHOPANZA_CRAWL_SHOT=snapshot-first`: the first `browser_take_screenshot` of a session is
  denied with a short reason that names `browser_snapshot`; every later one passes, so a task
  that must see the page still can. On I2 Haiku's cost followed that choice: 26-37 turns down
  the screenshot path, 19-20 down the snapshot path. One mark per `session_id` in
  `SANCHOPANZA_CRAWL_DIR` (default `~/.sanchopanza/crawl`). `V81_HOOKS` widens the `PreToolUse`
  matcher to take the screenshot tool beside the evaluate.

v10, in development and off by default, from the h2h confirmations of 2026-10-06 (the line spoke
in 59 sessions with no browser tool, twice on a local file):

- `SANCHOPANZA_CRAWL_LINE_AT=browser`: the line comes with the result of the session's first
  `browser_navigate` or `browser_evaluate` (`BROWSING`), once per session (a mark in
  `SANCHOPANZA_CRAWL_DIR`), and only when the request gathers, read from the session's
  transcript (`first_prompt`; unreadable: the line comes, since there is a browser). Nothing at
  `SessionStart` or `UserPromptSubmit`. `V10_HOOKS` widens `PostToolUse` to the navigate.

Standard library only (the echo cut reuses `autopilot`'s response walk); fail open everywhere.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
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
# v8.1 (development): one PreToolUse entry for the evaluate guard and the screenshot rule.
V81_HOOKS = {"PreToolUse": r"mcp__.*__browser_(evaluate|take_screenshot)"}
SHOT = re.compile(r"^mcp__.+__browser_take_screenshot$")
# v10 (development): the line on the session's first browsing call, a sign there is a browser.
BROWSING = re.compile(r"^mcp__.+__browser_(navigate|evaluate)$")
V10_HOOKS = {"PostToolUse": r"mcp__.*__browser_(evaluate|navigate)"}
SHOT_REASON = (
    "browser_snapshot gives the page text and element refs for clicks at a fraction of the "
    "tokens; call browser_take_screenshot again if you need to see the visual layout."
)
# The notes as the wrapper leaves them: the last key of the value it returns (`{result,
# sanchopanza}`, pretty-printed by Playwright MCP), or the tail of an error message.
NOTES_KEY = re.compile(r',\s*"sanchopanza":\s*("sanchopanza: (?:[^"\\]|\\.)*")(\s*\})')
NOTES_ERROR = re.compile(r" \| (sanchopanza: [^\n]*)")
# v9: a function that returned nothing comes back as the note alone, `{"sanchopanza": ...}`, with
# no comma before the key (v9's round, H8 run 1 of HAIKU-V9); the value it stands for is undefined.
NOTES_LONE = re.compile(r'\{\s*"sanchopanza":\s*("sanchopanza: (?:[^"\\]|\\.)*")\s*\}')
NOTES_HEAD = "### sanchopanza note"
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
    `2` turns on v8's and `3` v9's (in development): 0, 1, 2 or 3."""
    raw = _env.get("CRAWL_NOTES", "", env).strip().lower()
    if raw in {"2", "3"}:
        return int(raw)
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


def line_at_browser(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_CRAWL_LINE_AT=browser` (v10, development): the line where there is a browser."""
    return _env.get("CRAWL_LINE_AT", "", env).strip().lower() == "browser"


def first_prompt(transcript: str) -> str | None:
    """The session's first request as typed, from its transcript; None if it cannot be read."""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as stream:
            for raw in stream:
                with contextlib.suppress(ValueError):
                    record = json.loads(raw)
                    content = (record.get("message") or {}).get("content")
                    if record.get("type") != "user":
                        continue
                    if isinstance(content, str):
                        return content
                    texts = [b.get("text", "") for b in content or [] if isinstance(b, Mapping)
                             and b.get("type") == "text"]  # fmt: skip
                    if texts and not any(isinstance(b, Mapping) and b.get("type") == "tool_result"
                                         for b in content):  # fmt: skip
                        return "\n".join(texts)
    except (OSError, TypeError, AttributeError):
        return None
    return None


def browser_line(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> str | None:
    """v10: the line on the session's first browsing call when its request gathers, else None.
    The mark is written before the line is given, so no session gets it twice; with no session
    to remember it by, or a mark that cannot be written, no line."""
    from ..context.archive import safe_name
    from ..context.episodes import write_private

    session = str(event.get("session_id") or "")
    if not session or not BROWSING.match(str(event.get("tool_name") or "")):
        return None
    if _env.get("CRAWL_LINE", "1", env).strip().lower() in {"0", "false", "no", "off"}:
        return None
    mark = state_dir(env) / f"line-{safe_name(session)}.json"
    try:
        if mark.exists():
            return None
        write_private(mark, json.dumps({"at": time.time()}))
    except OSError:
        return None
    prompt = first_prompt(str(event.get("transcript_path") or ""))
    return line_for(env) if prompt is None or gathers(prompt) else None


def gathers(prompt: str) -> bool:
    """A request to gather data across pages, with no sign of acting on the site."""
    return bool(GATHERS.search(prompt)) and not ACTS.search(prompt)


def echo_cut_on(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_CRAWL_ECHO=short` (v8, development): cut the echoed wrapper."""
    return _env.get("CRAWL_ECHO", "", env).strip().lower() == "short"


def notes_first_on(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_CRAWL_NOTES_AT=front` (v8.1, development): the notes at the result's head."""
    return _env.get("CRAWL_NOTES_AT", "", env).strip().lower() == "front"


def cut_text(text: str) -> str:
    """The text with each echo of our wrapper replaced by one line."""
    return ECHO.sub(lambda m: ECHO_LINE if MARK in m.group(1) else m.group(0), text)


def notes_first(text: str, lone: bool = False) -> str:
    """The text with the wrapper's notes moved to its head, under `NOTES_HEAD`: from the last
    key of the returned value, else from the tail of an error message, else (with `lone`, v9)
    from a value that is the note alone, left as `undefined`. Unchanged with none."""
    keyed = list(NOTES_KEY.finditer(text))
    alone = NOTES_LONE.search(text) if lone and not keyed else None
    if keyed:
        last = keyed[-1]
        note = json.loads(last.group(1))
        rest = text[: last.start()] + last.group(2) + text[last.end() :]
    elif alone:
        note = json.loads(alone.group(1))
        rest = text[: alone.start()] + "undefined" + text[alone.end() :]
    else:
        found = NOTES_ERROR.search(text)
        if not found:
            return text
        note = found.group(1)
        rest = text[: found.start()] + text[found.end() :]
    return f"{NOTES_HEAD}\n{note}\n{rest}"


def rewrite_result(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict | None:
    """`PostToolUse` on an evaluate: the result with the echoed wrapper cut (`ECHO=short`) and
    the notes moved to its head (`NOTES_AT=front`), or None when neither changes it (never an
    identity rewrite, which would race other hooks' rewrites of the same result)."""
    from .autopilot import replaced, text_field

    if not EVALUATE.match(str(event.get("tool_name") or "")):
        return None
    response = event.get("tool_response")
    found = text_field(response)
    if found is None:
        return None
    path, text = found
    new = cut_text(text) if echo_cut_on(env) else text
    new = notes_first(new, lone=notes_on(env) >= 3) if notes_first_on(env) else new
    if new == text:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": replaced(response, path, new),
        }
    }


def shot_first_on(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_CRAWL_SHOT=snapshot-first` (v8.1, development)."""
    return _env.get("CRAWL_SHOT", "", env).strip().lower() == "snapshot-first"


def state_dir(env: Mapping[str, str] | None = None) -> Path:
    override = _env.get("CRAWL_DIR", "", env).strip()
    return Path(override) if override else _env.home_dir() / "crawl"


def first_shot(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict | None:
    """`PreToolUse` on a screenshot: deny the session's first one with `SHOT_REASON`, let every
    later one pass. The mark is written before the denial, so no session is denied twice; with
    no session to remember it by, or a mark that cannot be written, the call passes."""
    from ..context.archive import safe_name
    from ..context.episodes import write_private

    session = str(event.get("session_id") or "")
    if not session or not SHOT.match(str(event.get("tool_name") or "")):
        return None
    mark = state_dir(env) / f"shot-{safe_name(session)}.json"
    try:
        if mark.exists():
            return None
        write_private(mark, json.dumps({"denied_at": time.time()}))
    except OSError:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": SHOT_REASON,
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
        return None if line_at_prompt(env) or line_at_browser(env) else strategy(env)
    if name == "PreToolUse":
        if shot_first_on(env) and SHOT.match(str(event.get("tool_name") or "")):
            return first_shot(event, env)
        return guard(event, limit_seconds(env), notes_on(env))
    if name == "UserPromptSubmit" and line_at_prompt(env):
        prompt = event.get("prompt")
        return strategy(env, name) if isinstance(prompt, str) and gathers(prompt) else None
    if name == "PostToolUse":
        rewritten = rewrite_result(event, env) if echo_cut_on(env) or notes_first_on(env) else None
        line = browser_line(event, env) if line_at_browser(env) else None
        if line is None:
            return rewritten
        spec = (rewritten or {}).get("hookSpecificOutput") or {"hookEventName": "PostToolUse"}
        return {"hookSpecificOutput": {**spec, "additionalContext": line}}
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
