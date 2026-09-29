"""OpenAI Codex CLI: archive every tool result on arrival and point the model at it.

Codex (openai/codex, read at 33a0f766) runs command hooks from `hooks.json` or `[hooks]` in
`config.toml`, at `~/.codex/` or `<repo>/.codex/`. Two of them are enough here:

- `PostToolUse`: the full tool response is written to `.sanchopanza/archive/<session>/` and,
  when it is large, one line of `additionalContext` says where it is and what it holds
  (`index_of`). Codex records that line as a developer message after the tool output.
- `SessionStart`: when the archive already holds something, a short note says so and names
  the `search_archive` tool (`sanchopanza archive-mcp`, registered as an MCP server).

What Codex does not allow, and so this module does not try: replacing a built-in tool's
output (`updatedMCPToolOutput` is rejected; `continue: false` replaces it but halts the
turn), editing earlier history, or reading what was cut before the hook ran. The response a
`Bash` hook receives is already truncated to `tool_output_token_limit`, so the archive holds
what the model saw, and its use is recall after compaction or in a later session. See
`docs/results/2026-09-28-context-lean/codex/README.md` for the citations.

Every hook body fails open: any error prints `{}` and exits 0, so the tool is never failed.

    python -m sanchopanza.harness.codex post-tool-use     # hook body, JSON on stdin
    python -m sanchopanza.harness.codex session-start     # hook body, JSON on stdin
    python -m sanchopanza.harness.codex config [DIR]      # print .codex/hooks.json and config.toml
"""

from __future__ import annotations

import contextlib
import inspect
import json
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..context import archive as archive_mod

LARGE = 6_000  # characters from which the hook tells the model where the full text is
ARCHIVE_MIN = 500  # shorter results are not archived: they would only dilute search_archive
INDEX_LIMIT = 240
JOURNAL = "codex-hooks.jsonl"  # beside the archive, in the git-ignored .sanchopanza folder
SERVER = "sanchopanza_archive"
SEARCH_TOOL = "search_archive"
FIND_TOOL = "find_in_repo"
MARK = "sanchopanza archive:"  # the check looks for this in the rollout to prove delivery
HOOK_TIMEOUT_SEC = 30
SEARCH_OUTPUT_TOKENS = 2_000


# --- reading the event ----------------------------------------------------------------------


def _text_of(response: Any) -> str:
    """The text of a Codex tool response: a string for Bash and apply_patch, a serialized
    `CallToolResult` (`content: [{type, text}]`) for MCP tools, anything else as JSON."""
    from .generic import text_of

    text = text_of(response)
    if text or response in (None, ""):
        return text
    return json.dumps(response, ensure_ascii=False)


def _about(tool_input: Any) -> str:
    if not isinstance(tool_input, Mapping):
        return ""
    for key in ("command", "file_path", "path", "query", "url", "pattern"):
        value = tool_input.get(key)
        if value:
            return (value if isinstance(value, str) else json.dumps(value))[:160]
    return ""


def _root(event: Mapping[str, Any]) -> Path:
    from .. import _env

    cwd = str(event.get("cwd") or "") or None
    return archive_mod.root_for(cwd, override=_env.get("ARCHIVE") or None)


def _index(text: str) -> str:
    """Distinctive tokens of `text`, or "" when no index function is available."""
    finder: Callable[..., str] | None = None
    for module in ("sanchopanza.context.index", "sanchopanza.context.compact"):
        with contextlib.suppress(ImportError, AttributeError):
            finder = __import__(module, fromlist=["index_of"]).index_of
            break
    if finder is None:
        return ""
    if _takes_limit(finder):
        return str(finder(text, limit=INDEX_LIMIT))
    return str(finder(text))[:INDEX_LIMIT]


def _takes_limit(finder: Callable[..., str]) -> bool:
    """Whether `finder` accepts `limit=`: checked on the signature, so a TypeError raised from
    inside the index is not mistaken for an older signature and swallowed."""
    try:
        params = inspect.signature(finder).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "limit" or p.kind is p.VAR_KEYWORD for p in params)


def _journal(root: Path, record: Mapping[str, Any]) -> None:
    """One line per hook run, for the end-to-end check. Never raises."""
    with contextlib.suppress(Exception):
        path = root.parent / JOURNAL
        archive_mod.keep_out_of_git(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({**dict(record), "at": time.time()}, ensure_ascii=False))
            handle.write("\n")


# --- the hook bodies ------------------------------------------------------------------------


def _is_own_tool(tool: str) -> bool:
    return SEARCH_TOOL in tool


def context_line(tool: str, chars: int, path: Path, index: str) -> str:
    holds = f" Holds: {index}." if index else ""
    return (
        f"{MARK} the full {tool} output ({chars:,} characters) is saved verbatim at {path}."
        f"{holds} Read that file or call {SEARCH_TOOL}(query) to get it back instead of "
        "re-running the tool."
    )


def post_tool_use(event: Mapping[str, Any], *, large: int = LARGE) -> dict[str, Any]:
    """Archive the response; for a large one, return one line of `additionalContext`."""
    if event.get("hook_event_name") not in (None, "PostToolUse"):
        return {}
    tool = str(event.get("tool_name") or "tool")
    if _is_own_tool(tool):
        return {}
    text = _text_of(event.get("tool_response"))
    root = _root(event)
    session = str(event.get("session_id") or "session")
    if len(text) < ARCHIVE_MIN:
        # journaled anyway: whether Codex ran the hook at all must be visible (first check)
        _journal(root, {"event": "PostToolUse", "tool": tool, "chars": len(text), "archived": None,
                        "session": session})  # fmt: skip
        return {}
    tool_input = event.get("tool_input")
    meta = {
        "tool": tool,
        "about": _about(tool_input),
        "id": str(event.get("tool_use_id") or ""),
        "turn": str(event.get("turn_id") or ""),
        "by": "codex",
    }
    name = f"codex-{event.get('tool_use_id') or int(time.time() * 1000)}"
    path = archive_mod.write_entry(archive_mod.session_dir(root, session), name, text, meta)
    context = context_line(tool, len(text), path, _index(text)) if len(text) >= large else ""
    _journal(
        root,
        {
            "event": "PostToolUse",
            "tool": tool,
            "chars": len(text),
            "archived": str(path),
            "context": context,
            "session": session,
            "transcript": event.get("transcript_path"),
        },
    )
    if not context:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}


def session_start(event: Mapping[str, Any]) -> dict[str, Any]:
    """A short note, only when the archive already holds something."""
    if event.get("hook_event_name") not in (None, "SessionStart"):
        return {}
    root = _root(event)
    if not root.is_dir():
        return {}
    count = sum(1 for _ in root.glob("*/*.txt"))
    if count == 0:
        return {}
    note = (
        f"{MARK} {count} earlier tool output(s) are archived verbatim under {root}. "
        f"When you need something a tool printed before (a value, a line, an error), call "
        f"{SEARCH_TOOL}(query, k) or read the file it names, instead of re-running the tool."
    )
    _journal(
        root,
        {
            "event": "SessionStart",
            "source": event.get("source"),
            "entries": count,
            "session": str(event.get("session_id") or ""),
            "transcript": event.get("transcript_path"),
        },
    )
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}}


HANDLERS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "post-tool-use": post_tool_use,
    "session-start": session_start,
}


def run_hook(kind: str, raw: str) -> str:
    """The hook's stdout for `raw` stdin. Fail-open: any problem is `{}`."""
    try:
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, Mapping):
            return "{}"
        return json.dumps(HANDLERS[kind](event))  # ASCII: safe on any console code page
    except Exception as error:  # noqa: BLE001 - a hook must never fail the tool
        _report(error)
        return "{}"


ERROR_MESSAGE_MAX = 200


def _report(error: BaseException) -> None:
    """One stderr line naming the failure: its class and a short, one-line message. Never the
    event, the tool output or the environment. Never raises."""
    with contextlib.suppress(Exception):
        message = " ".join(str(error).split())[:ERROR_MESSAGE_MAX]
        sys.stderr.write(f"sanchopanza codex hook: {type(error).__name__}: {message}\n")


# --- configuration --------------------------------------------------------------------------


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def hook_command(kind: str, python: str | None = None) -> str:
    exe = python or sys.executable
    return f'"{exe}" -m sanchopanza.harness.codex {kind}'


def hooks_json(python: str | None = None) -> str:
    """`.codex/hooks.json`: PostToolUse on every tool, SessionStart on every source."""

    def handler(kind: str, status: str) -> dict[str, Any]:
        command = hook_command(kind, python)
        return {
            "type": "command",
            "command": command,
            "commandWindows": command,
            "timeout": HOOK_TIMEOUT_SEC,
            "statusMessage": status,
        }

    document = {
        "description": "sanchopanza: archive tool output, point the model at it",
        "hooks": {
            "PostToolUse": [{"hooks": [handler("post-tool-use", "archiving tool output")]}],
            "SessionStart": [{"hooks": [handler("session-start", "checking the archive")]}],
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def config_toml(
    *,
    python: str | None = None,
    archive: str | Path | None = None,
    tool_output_token_limit: int | None = None,
    search_output_tokens: int = SEARCH_OUTPUT_TOKENS,
    extra: Mapping[str, str] | None = None,
    find: bool = False,
) -> str:
    """The `config.toml` fragment: the archive MCP server and, if given, the output cap.

    `search_archive` is read-only BM25 over local files, so it is approved without a prompt
    (otherwise `codex exec`, which cannot ask, may decline it)."""
    exe = python or sys.executable
    args = ["-m", "sanchopanza", "archive-mcp"]
    if archive:
        args = [*args, "--archive", str(archive)]
    lines = [f"{key} = {value}" for key, value in (extra or {}).items()]
    if tool_output_token_limit is not None:
        lines = [*lines, f"tool_output_token_limit = {int(tool_output_token_limit)}"]
    lines = [
        *lines,
        "",
        f"[mcp_servers.{SERVER}]",
        f"command = {_toml_str(exe)}",
        "args = [" + ", ".join(_toml_str(a) for a in args) + "]",
        "startup_timeout_sec = 30",
        *(['env = { SANCHOPANZA_FIND = "1" }'] if find else []),
        "",
        f"[mcp_servers.{SERVER}.tools.{SEARCH_TOOL}]",
        'approval_mode = "approve"',
        f"output_token_limit = {int(search_output_tokens)}",
    ]
    if find:  # `find_in_repo` reads the repository and writes nothing: approved like the search
        lines = [
            *lines,
            "",
            f"[mcp_servers.{SERVER}.tools.{FIND_TOOL}]",
            'approval_mode = "approve"',
            f"output_token_limit = {int(search_output_tokens)}",
        ]
    return "\n".join(lines).lstrip("\n") + "\n"


def project_files(
    project: str | Path | None = None,
    *,
    python: str | None = None,
    archive: str | Path | None = None,
    tool_output_token_limit: int | None = None,
    find: bool = False,
) -> dict[str, str]:
    """{relative path: text} for a project's `.codex/` folder. Nothing is written: the
    caller decides, and Codex loads project config only for a trusted project."""
    del project  # the paths are relative; kept for symmetry with other installers
    return {
        ".codex/hooks.json": hooks_json(python),
        ".codex/config.toml": config_toml(
            python=python,
            archive=archive,
            tool_output_token_limit=tool_output_token_limit,
            find=find,
        ),
    }


# --- entry point ----------------------------------------------------------------------------

USAGE = (
    "usage: python -m sanchopanza.harness.codex post-tool-use|session-start|config [DIR] [--find]"
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    kind = args[0] if args else ""
    if kind in HANDLERS:
        try:
            raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - fail open on an unreadable stdin
            raw = ""
        sys.stdout.write(run_hook(kind, raw) + "\n")
        return 0
    if kind == "config":
        find = "--find" in args
        rest = [a for a in args[1:] if a != "--find"]
        for path, text in project_files(rest[0] if rest else None, find=find).items():
            sys.stdout.write(f"# --- {path}\n{text}\n")
        return 0
    sys.stderr.write(USAGE + "\n")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
