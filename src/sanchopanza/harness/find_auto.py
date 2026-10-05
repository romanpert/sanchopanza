"""The find nudge's substitute mode: run find_in_repo for the agent at the struggle point and put
the likeliest places in front of it, instead of suggesting a call it does not make.

Why: Haiku 4.5 called find_in_repo 0 times in 10 sessions of the need probe (phase D's copy,
2026-10-05) where 7 of 10 took 5 or more searches to the gold file. Offline
(benchmarks/find_auto, f1ef58e, ca6033a), trigger R4 - the 4th search while no source file has
been Read or edited - fires in 24/35 hard sessions and 5/144 easy ones (this module's rule;
f1ef58e's replay said 25 and 7, see `evaluate.replay_untouched`); at that fire, the request plus
the session's search words, ranked by find's source-only `kind=code` (top 60) and judged by Jev as
find_in_repo judges, holds a gold file in the top 5 in 16/24.

How: an `mcp_tool` hook (Claude Code 2.1.285: `{"type": "mcp_tool", "server", "tool", "input"}`,
`${path}` interpolated from the hook input, the tool's text parsed like a command hook's stdout)
calls `find_auto` on the running find server after each search, Read and edit (PostToolUse and
PostToolUseFailure: a grep that finds nothing can be a failure, and it is a search). The server
warmed the index in a background thread at start (`context.repo.warm`), so a fire costs a BM25
query and one Jev tournament, not a 35-second build. The tool is hidden from the model
(`_meta.ui.visibility: ["app"]`): only the hook calls it.

The trigger state and once-per-session marker are the nudge's (`find_nudge.is_search`,
`EDIT_TOOLS`, `claim`), kept per session in `SANCHOPANZA_GUARD_DIR`. What closes the window is the
offline replay's (`benchmarks/find_auto/evaluate.replay_untouched`, which now steps this module's
`step`): a Read of a source file (`context.repo.is_source`), or an edit of an existing non-test,
non-doc file (a Write to a path never Read creates a file and does not close it). Subagents'
calls are not counted (the replay counted the main thread only). At fire time the transcript is
replayed too, so a source Read whose event the hook missed still closes it.

Fails open, and says so in the journal (kind `find_auto`, with the query, the keys shown and the
Jev cost): nothing is added when the index is not built yet (the trigger stays armed for the next
search in the window), when the judge errs or leaves every fragment unanswered, when it keeps
nothing, past the session's Jev ceiling (`SESSION_MAX_USD`, the loop hook's ledger), or on any
error. Without a decider the free BM25 top 5 is shown, as find_in_repo shows it without a key.
`SANCHOPANZA_FIND_AUTO=0` silences it where wired. Opt-in: `sanchopanza install --find-auto`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .. import _env
from .find_nudge import EDIT_TOOLS, SEARCH_TOOLS, SHELL_TOOLS, claim, is_search
from .hookio import safe_name, state_dir, write_private

TOOL = "find_auto"
DESCRIPTION = "Called by sanchopanza's find-auto hook, not by the model."
HIDDEN = {"ui": {"visibility": ["app"]}}  # Claude Code keeps a tool with this from the model
MATCHER = "Bash|Glob|Grep|PowerShell|Read|Edit|Write|MultiEdit|NotebookEdit"
EVENTS = ("PostToolUse", "PostToolUseFailure")
NTH = 4  # R4
K = 5
SHORTLIST = 60
HOOK_TIMEOUT_S = 45
JUDGE_TIMEOUT_S = 30
QUERY_JOURNAL_CHARS = 2_000
HEADER = ("sanchopanza ran find_in_repo for this request; these are the likeliest places "
          "(Read to check):")  # fmt: skip
# What the hook passes: the hook input's fields the trigger reads, never a Write's content.
FIELDS = ("hook_event_name", "session_id", "tool_name", "tool_use_id", "agent_id",
          "transcript_path", "cwd")  # fmt: skip
INPUT_FIELDS = ("file_path", "notebook_path", "command", "pattern", "glob")
HOOK_INPUT = {**{f: f"${{{f}}}" for f in FIELDS},
              **{f: f"${{tool_input.{f}}}" for f in INPUT_FIELDS}}  # fmt: skip
DOC_SUFFIXES = (".md", ".rst", ".txt")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
OPTION = re.compile(r"(?:^|\s)--?[\w-]+(?:=\S+)?")
DRIVE = re.compile(r"^/([a-z])/")
_SHELL_WORDS = (
    "grep egrep rg ag ack find fd ls tree head tail xargs cat sed awk sort uniq wc echo cd type "
    "name iname include exclude path print null testbed dev usr lib python python3 site packages "
    "and the for not with from import def class self return none true false"
)
SHELL_WORDS = frozenset(_SHELL_WORDS.split())
_LOCK = threading.Lock()


def hook() -> dict[str, Any]:
    """The settings hook: the find server's `find_auto`, with the fields above."""
    from .install_defaults import FIND_SERVER

    return {"type": "mcp_tool", "server": FIND_SERVER, "tool": TOOL, "input": dict(HOOK_INPUT),
            "timeout": HOOK_TIMEOUT_S}  # fmt: skip


# ---- the trigger ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class State:
    searches: int = 0
    words: tuple[str, ...] = ()
    read: frozenset[str] = field(default_factory=frozenset)
    created: frozenset[str] = field(default_factory=frozenset)
    closed: str = ""  # fired, read, edited, judge_failed, nothing_kept, ceiling, touched, error


def search_words(tool: str, arguments: Mapping[str, Any]) -> list[str]:
    """The words an agent searched for: Grep/Glob patterns, a shell search's arguments."""
    if tool in SEARCH_TOOLS:
        text = " ".join(str(arguments.get(k) or "") for k in ("pattern", "glob"))
    elif tool in SHELL_TOOLS:
        text = OPTION.sub(" ", str(arguments.get("command") or ""))
    else:
        return []
    words = [w for w in WORD.findall(text) if w.lower() not in SHELL_WORDS]
    return list(dict.fromkeys(words))


def _canon(path: str) -> str:
    """'/'-separated, lower case, and a Git Bash drive (`/c/Users/...`, which Haiku passes to Read
    on Windows) written as `c:/users/...`."""
    norm = path.replace("\\", "/").removeprefix("./").lower()
    return DRIVE.sub(r"\1:/", norm)


def relative(path: str, root: str) -> str:
    """`path` relative to the project when it is under it, '/'-separated, lower case."""
    norm = _canon(path)
    base = _canon(root).rstrip("/") + "/"
    return norm[len(base) :] if base != "/" and norm.startswith(base) else norm


def _is_test(path: str) -> bool:
    from ..context.repo import is_test

    return is_test(path)


def step(state: State, tool: str, arguments: Mapping[str, Any], *, failed: bool = False,
         root: str = "") -> tuple[State, bool]:  # fmt: skip
    """The next state, and whether this call is at or past the NTH search with the window open
    (no source Read, no edit of an existing non-test, non-doc file)."""
    from ..context.repo import is_source

    if state.closed:
        return state, False
    raw = str(arguments.get("file_path") or arguments.get("notebook_path") or "")
    path = relative(raw, root) if raw else ""
    if tool == "Read" and path:
        if is_source(path):
            return replace(state, closed="read"), False
        return replace(state, read=state.read | {path}), False
    if tool in EDIT_TOOLS:
        if failed or not path:
            return state, False
        if tool == "Write" and path not in state.read:
            return replace(state, created=state.created | {path}), False
        if path not in state.created and not _is_test(path) and not path.endswith(DOC_SUFFIXES):
            return replace(state, closed="edited"), False
        return state, False
    if not is_search(tool, arguments):
        return state, False
    words = tuple(dict.fromkeys([*state.words, *search_words(tool, arguments)]))
    after = replace(state, searches=state.searches + 1, words=words)
    return after, after.searches >= NTH


# ---- the transcript ------------------------------------------------------------------------------


def _entries(path: str) -> Iterator[dict[str, Any]]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        with contextlib.suppress(ValueError):
            entry = json.loads(line)
            if isinstance(entry, dict):
                yield entry


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, Mapping) and b.get("type") == "tool_result" for b in content):
            return ""
        return "\n".join(str(b.get("text") or "") for b in content
                         if isinstance(b, Mapping) and b.get("type") == "text")  # fmt: skip
    return ""


def first_request(path: str) -> str:
    """The session's first prompt: the first user message that is text, not meta, not a tool
    result and not a command's output."""
    for entry in _entries(path):
        if entry.get("type") != "user" or entry.get("isMeta"):
            continue
        said = _text((entry.get("message") or {}).get("content")).strip()
        if said and not said.startswith(("<command-", "<local-command-", "<system-reminder>")):
            return said
    return ""


def transcript_state(path: str, root: str) -> State:
    """The trigger replayed over the transcript's main-thread calls (a result marked is_error is
    a failure; a call whose result is not written yet counts as done)."""
    calls: list[tuple[str, str, Mapping[str, Any]]] = []
    failed: set[str] = set()
    for entry in _entries(path):
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, Mapping):
                continue
            if b.get("type") == "tool_use" and entry.get("type") == "assistant":
                arguments = b.get("input") if isinstance(b.get("input"), Mapping) else {}
                calls.append((str(b.get("id")), str(b.get("name")), arguments))
            elif b.get("type") == "tool_result" and b.get("is_error"):
                failed.add(str(b.get("tool_use_id")))
    state = State()
    for call_id, name, arguments in calls:
        state, _ = step(state, name, arguments, failed=call_id in failed, root=root)
    return state


# ---- the session's state -------------------------------------------------------------------------


def _state_path(session: str) -> Path:
    return state_dir() / f"{safe_name(session)}-find-auto.json"


def load(path: Path) -> State:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return State(searches=int(data.get("searches", 0)), words=tuple(data.get("words", [])),
                     read=frozenset(data.get("read", [])),
                     created=frozenset(data.get("created", [])),
                     closed=str(data.get("closed", "")))  # fmt: skip
    except (OSError, ValueError, TypeError, AttributeError):
        return State()


def save(path: Path, state: State) -> None:
    write_private(path, json.dumps({"searches": state.searches, "words": list(state.words),
                                    "read": sorted(state.read), "created": sorted(state.created),
                                    "closed": state.closed}))  # fmt: skip


# ---- what it shows -------------------------------------------------------------------------------


def best_line(text: str, query: str) -> str:
    words = {w.lower() for w in WORD.findall(query)}
    body = [x.strip() for x in text.splitlines() if x.strip()]
    best = max(body, key=lambda x: len(words & {w.lower() for w in WORD.findall(x)}), default="")
    return best[:100]


def render(candidates: Sequence[Any], query: str) -> str:
    """The header and one `- path:lines  <the line with most query words>` per place."""
    return "\n".join([HEADER, *(f"- {c.key}  {best_line(c.text, query)}" for c in candidates)])


def query_of(request: str, words: Sequence[str]) -> str:
    """The offline Q3: the request, then the session's search words so far."""
    joined = " ".join(words)
    return f"{request}\n{joined}" if request and joined else (request or joined)


# ---- the fire ------------------------------------------------------------------------------------


def _ceiling() -> float:
    try:
        return float(_env.get("SESSION_MAX_USD", "0.50") or 0.50)
    except ValueError:
        return 0.50


def squire_from_env_capped(remaining_usd: float) -> Any:
    """find_in_repo's judge from the environment (None without a decider), its dollar cap
    lowered to what is left of the session's ceiling."""
    from .mcp import _squire_if_keyed

    squire = _squire_if_keyed()
    if squire is None:
        return None
    cap = min(squire.thresholds.max_usd, remaining_usd)
    return squire.fork(thresholds=replace(squire.thresholds, max_usd=cap))


async def rank(query: str, root: Path, squire: Any) -> tuple[str, list[Any]]:
    """(outcome, places): `fired`/`free` with the top K, or why nothing is shown."""
    from ..context.repo import PURPOSE, ready_index
    from ..select import select

    ready = ready_index(root)
    if ready is None:
        return "not_ready", []
    candidates, index = ready
    try:
        picks = await asyncio.wait_for(
            select(
                query,
                candidates,
                squire=squire,
                purpose=PURPOSE.format(query=query),
                shortlist_k=SHORTLIST,
                keep=K,
                index=index,
            ),  # fmt: skip
            timeout=JUDGE_TIMEOUT_S,
        )
    except TimeoutError:
        return "judge_failed", []
    if squire is None:
        return ("free", [p.candidate for p in picks]) if picks else ("nothing_kept", [])
    if not picks:
        return "nothing_kept", []
    if all(p.p is None for p in picks):  # an error, or nothing answered: the free order
        return "judge_failed", []
    return "fired", [p.candidate for p in picks]


def _journal(data: Mapping[str, Any]) -> None:
    from ..journal import JsonlJournal

    path = _env.get("JOURNAL") or _env.home_dir() / "journal.jsonl"
    with contextlib.suppress(OSError):
        JsonlJournal(path).record("find_auto", dict(data))


def _charge(session: str, squire: Any) -> None:
    from .autopilot import _charged, read_ledger, write_ledger
    from .loop_hook import _ledger_root

    if squire is None or not getattr(squire.meter, "decisions", 0):
        return
    root = _ledger_root()
    write_ledger(root, session, _charged(read_ledger(root, session), squire))


def _spent(session: str) -> float:
    from .autopilot import read_ledger
    from .loop_hook import _ledger_root

    return float(read_ledger(_ledger_root(), session).get("usd", 0.0))


def _advance(values: Mapping[str, str], root: Path) -> tuple[State, bool]:
    """Step the session's state under the lock; True when this call should try to fire."""
    tool, event = values.get("tool_name", ""), values.get("hook_event_name", "")
    arguments = {k: values[k] for k in INPUT_FIELDS if values.get(k)}
    path = _state_path(values["session_id"])
    with _LOCK:
        state = load(path)
        after, due = step(state, tool, arguments, failed=event == "PostToolUseFailure",
                          root=str(root))  # fmt: skip
        if due:
            replayed = transcript_state(values.get("transcript_path", ""), str(root))
            if replayed.closed:
                after, due = replace(after, closed="touched"), False
                _journal({**_basics(values, after), "outcome": "touched"})
        if after != state:
            save(path, after)
    return after, due


def _close(session: str, why: str) -> None:
    path = _state_path(session)
    with _LOCK:
        save(path, replace(load(path), closed=why))


def _basics(values: Mapping[str, str], state: State) -> dict[str, Any]:
    return {"session": values.get("session_id"), "event": values.get("hook_event_name"),
            "tool": values.get("tool_name"), "tool_use_id": values.get("tool_use_id"),
            "search": state.searches}  # fmt: skip


async def respond(values: Mapping[str, str], root: Path, *,
                  squire_for: Callable[[float], Any] = squire_from_env_capped) -> str:  # fmt: skip
    """The tool's answer: hook output JSON with additionalContext, or `{}`."""
    try:
        return await _respond(values, root, squire_for)
    except Exception as error:  # noqa: BLE001 - fail open, and say so
        _journal({"session": values.get("session_id"), "outcome": "error",
                  "error": error.__class__.__name__})  # fmt: skip
        return "{}"


async def _respond(values: Mapping[str, str], root: Path,
                   squire_for: Callable[[float], Any]) -> str:  # fmt: skip
    event = values.get("hook_event_name", "")
    if event not in EVENTS or not values.get("session_id") or values.get("agent_id"):
        return "{}"
    if _env.get("FIND_AUTO", "1").strip().lower() in ("0", "false", "no", "off"):
        return "{}"
    state, due = _advance(values, root)
    if not due:
        return "{}"
    session, started = values["session_id"], time.monotonic()
    request = first_request(values.get("transcript_path", ""))
    query = query_of(request, state.words)
    basics = {**_basics(values, state), "query": query[:QUERY_JOURNAL_CHARS],
              "words": list(state.words)}  # fmt: skip
    remaining = _ceiling() - _spent(session)
    if remaining <= 0:
        _close(session, "ceiling")
        _journal({**basics, "outcome": "ceiling"})
        return "{}"
    from ..context.repo import ready_index

    if ready_index(root) is None or not query.strip():
        _journal({**basics, "outcome": "not_ready" if query.strip() else "no_query"})
        return "{}"  # stays armed: the next search in the window tries again
    if not claim(_state_path(session)):
        return "{}"  # another call of this session fired already
    squire = squire_for(remaining)
    outcome, shown = await rank(query, root, squire)
    _close(session, "fired" if shown else outcome)
    _charge(session, squire)
    cost = float(getattr(getattr(squire, "meter", None), "cost_usd", 0.0) or 0.0)
    _journal(
        {
            **basics,
            "outcome": outcome,
            "keys": [c.key for c in shown],
            "jev_usd": round(cost, 6),
            "seconds": round(time.monotonic() - started, 2),
        }
    )
    if not shown:
        return "{}"
    note = render(shown, query)
    return json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                              "additionalContext": note}})  # fmt: skip
