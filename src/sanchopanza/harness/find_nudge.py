"""The find nudge as a Claude Code command hook (`sanchopanza find-hook`, PostToolUse).

In the alwaysLoad probe (2026-10-03) find_in_repo sat in turn 1 with its schema and Haiku 4.5
called it 0 times in 10 sessions; 37 of its 61 pre-edit searches were shell `find|grep|head -20`
listings, and the "20 files" it saw were head-truncated. In find-e2e, where it was used, two of
six calls came right after a search that listed many files. So the suggestion goes where the need
shows: once per session, after one of the first `MAX_SEARCHES` searches, before any edit, when it
listed `MIN_LISTED` or more files or filled a `head -K` (K >= `MIN_HEAD`) cut, and only when
Claude Code would load find_in_repo (a `.mcp.json` server counts once approved). One line of
`additionalContext`, added to the messages: the tools and the system prompt never change, so no
cached prefix is invalidated. "Once" holds under concurrent hook calls: only the call that creates
the session's `fired` marker (O_CREAT|O_EXCL) nudges.

Wired by `sanchopanza install` with find (matcher `MATCHER`). Environment (`SANCHOPANZA_<NAME>`):

    FIND_NUDGE   "0" turns it off (on by default wherever it is wired)
    GUARD_DIR    the per-session state folder, shared with the compaction guard (`hookio`)
    JOURNAL      each firing is journalled there as kind `find_nudge`

Fail open: any error writes one line to stderr and adds nothing.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .. import _env
from .hookio import safe_name, state_dir, stdin_text, stdout_json, write_private

SEARCH_TOOLS = frozenset({"Grep", "Glob"})
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
MATCHER = "Bash|Glob|Grep|PowerShell"
MIN_LISTED = 15
MIN_HEAD = 10
MAX_SEARCHES = 3
FIND_SERVER = "sanchopanza"
FIND_CALL = "mcp__sanchopanza__find_in_repo"

SHELL_SEARCH = re.compile(
    r"(?:^|[|;&(]|\s)(?:git\s+grep|grep|egrep|rg|ag|ack|find|fd|ls|tree|findstr|select-string"
    r"|sls|get-childitem|gci|dir)(?=\s|$)",
    re.IGNORECASE,
)
HEAD = re.compile(r"\bhead\s+(?:-n\s*|-)(\d+)|\bselect-object\s+-first\s+(\d+)", re.IGNORECASE)
PATH = re.compile(
    r"^(?:[A-Za-z]:)?[\w.~\\/\-]*?[\w\-]\.[A-Za-z0-9]{1,8}(?=$|[:\s]|-\d+-)"
)  # a file path at the start of a line: `./a/b.py:12:...`, `a\b.py-3-...`, `C:\a\b.py`


@dataclass(frozen=True, slots=True)
class State:
    searches: int = 0
    closed: str = ""  # why it will not fire again in this session: fired, edited, searches


@dataclass(frozen=True, slots=True)
class Wide:
    search: int  # which search of the session (1-based)
    listed: int  # distinct files in its result
    cut: str  # "head -20" when a full head listing made it wide, else ""


# ---- reading one result --------------------------------------------------------------------------


def is_search(tool: str, arguments: Mapping[str, Any]) -> bool:
    if tool in SEARCH_TOOLS:
        return True
    command = arguments.get("command")
    return tool in SHELL_TOOLS and isinstance(command, str) and bool(SHELL_SEARCH.search(command))


def _text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        return "\n".join(str(response.get(k) or "") for k in ("stdout", "content", "output"))
    return ""


def _paths(text: str) -> set[str]:
    found = (PATH.match(line.strip()) for line in text.splitlines())
    return {m.group(0).replace("\\", "/").removeprefix("./") for m in found if m}


def listed(tool: str, response: Any) -> int:
    """Distinct files a search result lists."""
    if isinstance(response, Mapping) and tool in SEARCH_TOOLS:
        names = response.get("filenames") or []
        counted = max(int(response.get("numFiles") or 0), len(names))
        return max(counted, len(_paths(str(response.get("content") or ""))))
    return len(_paths(_text(response)))


def head_cut(command: str) -> tuple[int, str] | None:
    """The last `head -K` / `Select-Object -First K` of a command: (K, as written)."""
    matches = list(HEAD.finditer(command))
    if not matches:
        return None
    last = matches[-1]
    return int(last.group(1) or last.group(2)), " ".join(last.group(0).split())


def head_limit(command: str) -> int | None:
    cut = head_cut(command)
    return cut[0] if cut else None


def full_head(arguments: Mapping[str, Any], response: Any) -> str:
    """The cut as written ("head -20") when the command cut its output at K >= MIN_HEAD lines
    and the output filled the cut; "" otherwise."""
    command = arguments.get("command")
    cut = head_cut(command) if isinstance(command, str) else None
    if cut is None or cut[0] < MIN_HEAD:
        return ""
    lines = [line for line in _text(response).splitlines() if line.strip()]
    return cut[1] if len(lines) >= cut[0] else ""


# ---- the session's state -------------------------------------------------------------------------


def step(state: State, event: Mapping[str, Any]) -> tuple[State, Wide | None]:
    """The next state and, when this result is the wide early search, what made it wide."""
    if state.closed:
        return state, None
    tool = str(event.get("tool_name", ""))
    arguments = event.get("tool_input")
    arguments = arguments if isinstance(arguments, Mapping) else {}
    if tool in EDIT_TOOLS:
        return replace(state, closed="edited"), None
    if not is_search(tool, arguments):
        return state, None
    count = state.searches + 1
    after = replace(state, searches=count, closed="searches" if count >= MAX_SEARCHES else "")
    response = event.get("tool_response")
    files = listed(tool, response)
    cut = full_head(arguments, response) if tool in SHELL_TOOLS else ""
    if files >= MIN_LISTED or cut:
        return after, Wide(search=count, listed=files, cut=cut)
    return after, None


def _state_path(event: Mapping[str, Any]) -> Path:
    return state_dir() / f"{safe_name(str(event.get('session_id', '')))}-find-nudge.json"


def load(path: Path) -> State:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return State(searches=int(data.get("searches", 0)), closed=str(data.get("closed", "")))
    except (OSError, ValueError, TypeError, AttributeError):
        return State()


def save(path: Path, state: State) -> None:
    write_private(path, json.dumps({"searches": state.searches, "closed": state.closed}))


def claim(path: Path) -> bool:
    """Create the session's `fired` marker beside its state, exclusively: of two hooks running
    at once, only the one whose create succeeds may nudge."""
    marker = path.with_suffix(".fired")
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    except FileExistsError:
        return False
    return True


# ---- conditions checked only when it would fire --------------------------------------------------


def edited_in(transcript: str) -> bool:
    """An Edit, Write, MultiEdit or NotebookEdit call anywhere in the transcript so far."""
    try:
        text = Path(transcript).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        if not any(f'"{name}"' in line for name in EDIT_TOOLS):
            continue
        with contextlib.suppress(ValueError):
            content = (json.loads(line).get("message") or {}).get("content") or []
            if any(isinstance(b, Mapping) and b.get("type") == "tool_use"
                   and b.get("name") in EDIT_TOOLS for b in content):  # fmt: skip
                return True
    return False


def user_config() -> Path:
    return Path.home() / ".claude.json"


def user_settings() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _json(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, Mapping) else {}


def _names(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return {str(name) for name in value}
    return {str(name) for name in value} if isinstance(value, list) else set()


def _approved(settings: list[Mapping[str, Any]]) -> bool:
    """Whether settings let Claude Code load our `.mcp.json` server: approved by name or all at
    once, and not disabled by name."""
    if any(FIND_SERVER in _names(s.get("disabledMcpjsonServers")) for s in settings):
        return False
    return any(FIND_SERVER in _names(s.get("enabledMcpjsonServers"))
               or s.get("enableAllProjectMcpServers") is True for s in settings)  # fmt: skip


def _project_entry(config: Mapping[str, Any], project: str) -> Mapping[str, Any]:
    projects = config.get("projects")
    if not isinstance(projects, Mapping):
        return {}
    for key in (project, project.replace("\\", "/")):
        entry = projects.get(key)
        if isinstance(entry, Mapping):
            return entry
    return {}


def find_installed(event: Mapping[str, Any]) -> bool:
    """find_in_repo's server as Claude Code would load it: in the user's or the project's (local)
    scope of `~/.claude.json`, or in the project's `.mcp.json` once the settings, or the answer
    to Claude Code's prompt kept in `~/.claude.json`, approve it. Read only when it would fire."""
    from .claude_code import project_dir

    project = project_dir(event)
    config = _json(user_config())
    entry = _project_entry(config, project)
    if FIND_SERVER in _names(config.get("mcpServers")) | _names(entry.get("mcpServers")):
        return True
    if FIND_SERVER not in _names(_json(Path(project) / ".mcp.json").get("mcpServers")):
        return False
    folder = Path(project) / ".claude"
    files = (folder / "settings.json", folder / "settings.local.json", user_settings())
    return _approved([entry, *(_json(path) for path in files)])


def note(wide: Wide) -> str:
    what = f"filled its {wide.cut}" if wide.cut else f"listed {wide.listed} files"
    return (f"sanchopanza: that search {what} and nothing is edited yet. If the request describes "
            f"behaviour rather than naming the code, {FIND_CALL}(query=\"<the symptom in the "
            "user's words>\") ranks the fragments that bear on it; then Read the lines it "
            "points to.")  # fmt: skip


def _journal(event: Mapping[str, Any], wide: Wide) -> None:
    from ..journal import JsonlJournal

    path = _env.get("JOURNAL") or _env.home_dir() / "journal.jsonl"
    JsonlJournal(path).record("find_nudge", {
        "session": event.get("session_id"), "tool": event.get("tool_name"),
        "search": wide.search, "listed": wide.listed,
        "head": head_limit(wide.cut) if wide.cut else None})  # fmt: skip


# ---- the hook ------------------------------------------------------------------------------------


def handle(event: Mapping[str, Any]) -> dict[str, Any] | None:
    if event.get("hook_event_name") != "PostToolUse":
        return None
    if _env.get("FIND_NUDGE", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    tool = str(event.get("tool_name", ""))
    if tool not in SEARCH_TOOLS | SHELL_TOOLS | EDIT_TOOLS:
        return None
    path = _state_path(event)
    state = load(path)
    if state.closed:
        return None
    after, wide = step(state, event)
    if wide is not None and edited_in(str(event.get("transcript_path") or "")):
        after, wide = replace(after, closed="edited"), None
    if wide is not None and not find_installed(event):
        wide = None
    if wide is not None:
        after = replace(after, closed="fired")
        if not claim(path):  # another call of this session nudged already
            wide = None
    if after != state:
        save(path, after)
    if wide is None:
        return None
    _journal(event, wide)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note(wide)}}


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
            sys.stderr.write(
                f"sanchopanza find nudge: added nothing ({error.__class__.__name__})\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
