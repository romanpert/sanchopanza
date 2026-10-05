"""Pure reading of one recorded Claude Code session: its main-thread tool calls with their results,
how far it searched before reaching a gold file, and offline replays of find-nudge triggers.

The search test (`is_search`), the "wide result" test (`listed`, `full_head`) and the live rule
(`step`) are imported from `sanchopanza.harness.find_nudge`, so the replay of the current rule is
the hook's own code. No model, no Jev, no Docker.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sanchopanza.harness.find_nudge import (
    EDIT_TOOLS,
    MIN_LISTED,
    SEARCH_TOOLS,
    SHELL_TOOLS,
    State,
    full_head,
    is_search,
    listed,
    step,
)

FIND_TOOL = "mcp__sanchopanza__find_in_repo"
VIEW_TOOLS = SHELL_TOOLS | {"Grep"}
# A line of a shell result that says nothing was found (or the command failed), not a match.
NOTHING = re.compile(
    r"no such file|cannot access|not found|permission denied|is not recognized|cannot find path"
    r"|^exit code \d+|^error: exit code|^(?:find|grep|ls|rg|ag|fd|tree):\s|^no (?:files|matches)"
    r" found|^\(no output\)|^\(eval\):",
    re.IGNORECASE,
)
LISTING_VERB = re.compile(r"\b(?:find|fd|ls|tree|dir|get-childitem|gci)\b", re.IGNORECASE)
CONTENT_IN_PIPE = re.compile(r"-exec\s+grep|xargs\s+(?:-\S+\s+)*(?:grep|rg)", re.IGNORECASE)
DOC_SUFFIXES = (".md", ".rst", ".txt")


@dataclass(frozen=True, slots=True)
class Call:
    name: str
    input: Mapping[str, Any]
    result: Any = None
    error: bool = False


@dataclass(frozen=True, slots=True)
class Fire:
    call: int  # 1-based index of the tool call after which the nudge would be added
    search: int  # which search of the session it was
    kind: str  # "listing", "content" or "empty"


# ---- parsing -------------------------------------------------------------------------------------


def jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def _block_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text") or "") for b in content if isinstance(b, Mapping))
    return ""


class _Collector:
    """Tool uses in order (deduplicated by id) and their results by id."""

    def __init__(self) -> None:
        self.order: list[tuple[str, str, Mapping[str, Any]]] = []
        self.seen: set[str] = set()
        self.results: dict[str, tuple[Any, bool]] = {}

    def assistant(self, content: list[Any]) -> None:
        for b in content:
            if not isinstance(b, Mapping) or b.get("type") != "tool_use":
                continue
            if b.get("id") not in self.seen:
                self.seen.add(str(b.get("id")))
                given = b.get("input")
                self.order.append((str(b.get("id")), str(b.get("name")),
                                   given if isinstance(given, Mapping) else {}))  # fmt: skip

    def user(self, content: list[Any], structured: Any) -> None:
        blocks = [b for b in content if isinstance(b, Mapping) and b.get("type") == "tool_result"]
        for b in blocks:
            result = structured if len(blocks) == 1 and structured is not None else None
            self.results[str(b.get("tool_use_id"))] = (
                result if result is not None else _block_text(b.get("content")),
                bool(b.get("is_error")),
            )

    def calls(self) -> list[Call]:
        return [Call(name, given, *self.results.get(uid, (None, False)))
                for uid, name, given in self.order]  # fmt: skip


def stream_calls(path: Path) -> tuple[dict[str, Any], list[Call]]:
    """`claude -p --output-format stream-json` output: init facts and main-thread calls."""
    meta: dict[str, Any] = {}
    got = _Collector()
    for e in jsonl(path):
        kind = e.get("type")
        if kind == "system" and e.get("subtype") == "init" and not meta:
            meta = {"model": e.get("model"), "version": e.get("claude_code_version"),
                    "tools": e.get("tools") or []}  # fmt: skip
        if e.get("parent_tool_use_id"):
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        if kind == "assistant":
            got.assistant(content)
        elif kind == "user":
            got.user(content, e.get("tool_use_result"))
    return meta, got.calls()


def _prompt_text(e: Mapping[str, Any]) -> str | None:
    """The text a person typed, or None for tool results, meta entries and harness messages."""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isCompactSummary"):
        return None
    content = (e.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, Mapping) and b.get("type") == "tool_result" for b in content):
            return None
        content = _block_text(content)
    if not isinstance(content, str):
        return None
    text = re.sub(r"<(system-reminder|local-command-\w+|command-\w+|task-notification|bash-\w+)"
                  r"[^>]*>.*?</\1>", "", content, flags=re.S).strip()  # fmt: skip
    if not text or text.startswith("[Request interrupted"):
        return None
    return text


def transcript_turns(path: Path) -> list[dict[str, Any]]:
    """A Claude Code transcript as turns: each typed request and the main-thread calls until the
    next one. Text is returned for the caller to classify, never stored by this module."""
    turns: list[dict[str, Any]] = []
    got: _Collector | None = None
    model = None
    for e in jsonl(path):
        if e.get("isSidechain"):
            continue
        prompt = _prompt_text(e)
        if prompt is not None:
            if got is not None:
                turns[-1]["calls"] = got.calls()
            got = _Collector()
            turns.append({"prompt": prompt, "calls": [], "cwd": e.get("cwd")})
            continue
        if got is None:
            continue
        message = e.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if e.get("type") == "assistant":
            model = model or message.get("model")
            got.assistant(content)
        elif e.get("type") == "user":
            got.user(content, e.get("toolUseResult"))
    if got is not None:
        turns[-1]["calls"] = got.calls()
    for turn in turns:
        turn["model"] = model
    return turns


# ---- reading results -----------------------------------------------------------------------------


def result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, Mapping):
        parts = [str(result.get(k) or "") for k in ("stdout", "content", "output")]
        return "\n".join([*parts, *map(str, result.get("filenames") or [])])
    return _block_text(result)


def is_empty(call: Call) -> bool:
    """A search that returned nothing useful: no file and no matching line (an error, a failed
    grep, "No files found", or only error lines on the shell)."""
    result = call.result
    if call.name in SEARCH_TOOLS and isinstance(result, Mapping):
        files = int(result.get("numFiles") or 0) or len(result.get("filenames") or [])
        return files == 0 and not str(result.get("content") or "").strip()
    lines = [line for line in result_text(result).splitlines()
             if line.strip() and not NOTHING.search(line.strip())]  # fmt: skip
    return not lines


def is_listing(call: Call) -> bool:
    """A listing of file names (Glob, or a shell find/ls/tree whose first stage lists names and
    whose pipe never greps file contents), as opposed to a search of contents."""
    if call.name == "Glob":
        return True
    command = call.input.get("command")
    if call.name not in SHELL_TOOLS or not isinstance(command, str):
        return False
    first = re.split(r"\|", command, maxsplit=1)[0]
    return bool(LISTING_VERB.search(first)) and not CONTENT_IN_PIPE.search(command)


def norm(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./").lower()


def is_test(path: str) -> bool:
    parts = norm(path).split("/")
    base = parts[-1]
    return (any(p in ("test", "tests", "testing", "__tests__") for p in parts[:-1])
            or base.startswith("test") or base == "conftest.py"
            or any(m in base for m in ("_test.", ".test.", ".spec.", "_tests.")))  # fmt: skip


def source_edits(calls: list[Call]) -> list[int]:
    """0-based indices of successful edits of an existing non-test, non-doc file. A Write to a
    path the session never Read creates a file (Claude Code refuses to overwrite an unread one);
    a file the session created stays new."""
    read: set[str] = set()
    created: set[str] = set()
    out: list[int] = []
    for i, call in enumerate(calls):
        path = norm(str(call.input.get("file_path") or call.input.get("notebook_path") or ""))
        if call.name == "Read" and path:
            read.add(path)
        if call.name not in EDIT_TOOLS or not path or call.error:
            continue
        if call.name == "Write" and path not in read:
            created.add(path)
            continue
        if path not in created and not is_test(path) and not path.endswith(DOC_SUFFIXES):
            out.append(i)
    return out


# ---- reaching the gold ---------------------------------------------------------------------------


def is_gold(path: str, gold: Iterable[str]) -> bool:
    tail = norm(path)
    return any(tail == norm(g) or tail.endswith("/" + norm(g)) for g in gold)


def names_gold(call: Call, gold: Iterable[str]) -> bool:
    """A shell command or Grep whose arguments name a gold file (its last two path parts)."""
    if call.name not in VIEW_TOOLS:
        return False
    text = norm(json.dumps(dict(call.input)).replace("\\\\", "/"))
    return any("/".join(norm(g).split("/")[-2:]) in text for g in gold)


def reach(calls: list[Call], gold: list[str]) -> dict[str, Any]:
    """Searches (and find calls) before the first Read of a gold file (`read_*`, the dev log's
    measure), and before the first view of one (a Read, or a shell command or Grep that names it;
    `view_*`). None: never."""
    out: dict[str, Any] = {"read_at": None, "read_searches": None, "view_at": None,
                           "view_searches": None, "finds_before": None}  # fmt: skip
    searches = finds = 0
    for n, call in enumerate(calls, start=1):
        path = str(call.input.get("file_path", ""))
        is_read = call.name == "Read" and is_gold(path, gold)
        if out["view_at"] is None and (is_read or names_gold(call, gold)):
            out.update(view_at=n, view_searches=searches)
        if is_read:
            out.update(read_at=n, read_searches=searches, finds_before=finds)
            break
        searches += is_search(call.name, call.input)
        finds += call.name == FIND_TOOL
    out["searches_total"] = sum(is_search(c.name, c.input) for c in calls)
    out["finds_total"] = sum(c.name == FIND_TOOL for c in calls)
    return out


# ---- replays -------------------------------------------------------------------------------------


def _fire(n: int, search: int, call: Call, kind: str | None = None) -> Fire:
    return Fire(n, search, kind or ("listing" if is_listing(call) else "content"))


def replay_live(calls: list[Call]) -> Fire | None:
    """The hook as shipped (`find_nudge.step`): wide result within the first 3 searches, any
    edit closes."""
    state = State()
    for n, call in enumerate(calls, start=1):
        event = {"tool_name": call.name, "tool_input": dict(call.input),
                 "tool_response": call.result}  # fmt: skip
        state, wide = step(state, event)
        if wide is not None:
            return _fire(n, wide.search, call)
        if state.closed:
            return None
    return None


def _closers(calls: list[Call], closer: str) -> set[int]:
    if closer == "source":
        return set(source_edits(calls))
    return {i for i, c in enumerate(calls) if c.name in EDIT_TOOLS}


def is_wide(call: Call) -> bool:
    if listed(call.name, call.result) >= MIN_LISTED:
        return True
    return call.name in SHELL_TOOLS and bool(full_head(call.input, call.result))


def replay_wide(calls: list[Call], max_searches: int, closer: str, listings: bool = True
                ) -> Fire | None:  # fmt: skip
    """A wide result within the first `max_searches` searches, before the window closes (`any`
    edit, or an edit of an existing non-test `source` file); `listings=False` ignores name
    listings."""
    closes, count = _closers(calls, closer), 0
    for i, call in enumerate(calls):
        if i in closes:
            return None
        if not is_search(call.name, call.input):
            continue
        count += 1
        if count > max_searches:
            return None
        if is_wide(call) and (listings or not is_listing(call)):
            return _fire(i + 1, count, call)
    return None


def replay_empty(calls: list[Call], nth: int = 2, closer: str = "source",
                 within: int | None = None) -> Fire | None:  # fmt: skip
    """The struggle rule: the `nth` empty search before the window closes (and, with `within`,
    among the session's first `within` searches)."""
    closes, count, empty = _closers(calls, closer), 0, 0
    for i, call in enumerate(calls):
        if i in closes:
            return None
        if not is_search(call.name, call.input):
            continue
        count += 1
        if within is not None and count > within:
            return None
        empty += is_empty(call)
        if empty == nth:
            return _fire(i + 1, count, call, "empty")
    return None


def replay_count(calls: list[Call], nth: int, closer: str = "source") -> Fire | None:
    """The `nth` search of any kind before the window closes (a plain persistence signal)."""
    closes, count = _closers(calls, closer), 0
    for i, call in enumerate(calls):
        if i in closes:
            return None
        if is_search(call.name, call.input):
            count += 1
            if count == nth:
                return _fire(i + 1, count, call)
    return None


RULES = {
    "live: wide in first 3, any edit closes": lambda c: replay_live(c),
    "wide in first 3, source edit closes": lambda c: replay_wide(c, 3, "source"),
    "wide in first 6, any edit closes": lambda c: replay_wide(c, 6, "any"),
    "wide in first 6, source edit closes": lambda c: replay_wide(c, 6, "source"),
    "wide in first 3, source closes, no listings": lambda c: replay_wide(c, 3, "source", False),
    "wide in first 6, source closes, no listings": lambda c: replay_wide(c, 6, "source", False),
    "2nd empty search, any edit closes": lambda c: replay_empty(c, 2, "any"),
    "NEW 2nd empty search, source edit closes": lambda c: replay_empty(c, 2, "source"),
    "2nd empty in first 8 searches, source edit closes": lambda c: replay_empty(c, 2, "source", 8),
    "3rd empty search, source edit closes": lambda c: replay_empty(c, 3, "source"),
    "5th search, source edit closes": lambda c: replay_count(c, 5, "source"),
}
