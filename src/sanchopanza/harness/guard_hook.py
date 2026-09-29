"""The compaction guard as Claude Code command hooks (`sanchopanza guard-hook`).

One process per event, JSON on stdin (https://code.claude.com/docs/en/hooks). What it does is
in `context.guard`; this module only reads the event and the transcript and writes the answer:

- `PreCompact`: builds the guard from the whole transcript, keeps it for the `SessionStart`
  that follows, and prints the note for the summariser. Claude Code 2.1.282 appends the stdout
  of a successful `PreCompact` hook to the summary prompt as additional instructions, on
  manual and automatic compaction alike.
- `SessionStart` with source `compact`: returns the guard block as `additionalContext`, which
  Claude Code places right after the summary.
- `PostToolUse` on `Bash`: when a command that ran before the last compaction runs again and
  its value lines are not all in the new output, appends them once per command and session
  (`guard.echo`). Agents re-run one-shot tools after a compaction instead of searching an
  archive (39 re-runs, 0 archive searches in docs/results/2026-09-28-context-lean), so the
  earlier values are given back where the agent already looks. Without a compaction in the
  transcript it returns before parsing it.

Environment (every name is `SANCHOPANZA_<NAME>`):

    GUARD_CHOOSER    rule (default, no model) | judge: every output line judged by the decider,
                     the person's requests as the question, no content rule | decider: the rule's
                     lines, one tournament over commands when they do not fit (the first version).
                     judge and decider need a provider (as `sanchopanza hook`) and get at most
                     GUARD_DECIDER_SECONDS (default 20); a judge that fails or times out chooses
                     no line (requests and trail still go), a decider falls back to the rule |
                     keep: the cascade (`context.keep`): every line proposed, the rule's lines
                     free, the decider scoring blocks then lines with the requests in full when
                     the pool does not fit; built at the SessionStart, with the agent's open
                     TodoWrite items as notes, else the previous compaction's summary (the new one
                     is not on disk yet; GUARD_NOTES=0 to leave notes out); the rule on failure
    GUARD_FACTS_CHARS, GUARD_REQUESTS_CHARS   budgets (defaults 3000 and 2500)
    GUARD_WEB        "1" to keep lines of WebFetch, WebSearch and MCP output too (off: a page can
                     be fetched again, and its lines could carry instructions aimed at the model)
    GUARD_ECHO       "0" to turn the re-run echo off
    GUARD_DIR        where a PreCompact leaves its guard for the SessionStart (default
                     ~/.sanchopanza/guard); never the project directory, which the agent searches.
                     Files are private to the user and removed when used or after an hour.
    GUARD_LOG        a JSONL file to append one line per event to (off when unset)

Fail open: any error writes one line to stderr and adds nothing; the native summary stands.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import _env
from ..context import guard as guard_mod
from ..context.transcript import Call, calls, history_from_claude_code, last_compact_summary

PREFIX = "sanchopanza guard"
KEPT_SECONDS = 3_600


def _int(name: str, default: int) -> int:
    try:
        value = int(_env.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _on(name: str, default: str) -> bool:
    return _env.get(name, default).strip() not in ("0", "", "false", "no")


def _dir() -> Path:
    return Path(_env.get("GUARD_DIR", "") or _env.home_dir() / "guard")


def _safe(session: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in session) or "session"


def _log(row: Mapping[str, Any]) -> None:
    path = _env.get("GUARD_LOG", "")
    if not path:
        return
    try:
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": round(time.time(), 3), **row}) + "\n")
    except OSError:
        pass  # a debugging aid never changes what the hook does


def _write_private(path: Path, text: str) -> None:
    """Write `text` readable by this user only (the guard can hold command output)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def _sweep(folder: Path) -> None:
    """Remove kept guards older than `KEPT_SECONDS` (a compaction whose SessionStart never ran)."""
    cutoff = time.time() - KEPT_SECONDS
    for old in folder.glob("*.json"):
        with contextlib.suppress(OSError):
            if old.stat().st_mtime < cutoff:
                old.unlink()


def _summary(guard: guard_mod.Guard, text: str) -> dict[str, Any]:
    return {
        "candidates": guard.candidates,
        "facts": len(guard.facts),
        "requests": len(guard.requests),
        "trail": len(guard.trail),
        "chooser": guard.chooser,
        "block_chars": len(text),
    }


def _chooser() -> str:
    return _env.get("GUARD_CHOOSER", "rule").strip()


def _guard(messages: list[dict[str, Any]], notes: str = "") -> guard_mod.Guard:
    options = {
        "facts_chars": _int("GUARD_FACTS_CHARS", guard_mod.FACTS_CHARS),
        "requests_chars": _int("GUARD_REQUESTS_CHARS", guard_mod.REQUESTS_CHARS),
        "web": _on("GUARD_WEB", "0"),
    }
    chooser = _chooser()
    if chooser not in ("decider", "judge", "keep"):
        return guard_mod.build(messages, **options)
    from .claude_code import squire_from_env

    squire = squire_from_env(redact=True)
    seconds = _int("GUARD_DECIDER_SECONDS", 20)
    if chooser == "keep":
        from ..context import keep as keep_mod

        try:
            return asyncio.run(
                asyncio.wait_for(keep_mod.build(squire, messages, notes=notes, **options), seconds)
            )
        except TimeoutError:
            rule = guard_mod.build(messages, **options)
            return dataclasses.replace(rule, chooser="keep (decider timed out: rule only)")
        except Exception as error:  # noqa: BLE001 - the summariser was promised a block
            _log({"event": "error", "error": f"keep: {error.__class__.__name__}: {error}"})
            rule = guard_mod.build(messages, **options)
            return dataclasses.replace(rule, chooser="keep (error: rule only)")
    make = guard_mod.build_with_judge if chooser == "judge" else guard_mod.build_with_decider
    try:
        return asyncio.run(asyncio.wait_for(make(squire, messages, **options), seconds))
    except TimeoutError:
        if chooser == "judge":  # no hidden rule takes over: requests and trail only
            history = calls(messages)
            requests = guard_mod.requests_of(messages, options["requests_chars"])
            return guard_mod.Guard((), requests, guard_mod.trail_of(history), 0, "judge timed out",
                                   guard_mod.clipped_of(history, web=options["web"]))  # fmt: skip
        rule = guard_mod.build(messages, **options)
        return dataclasses.replace(rule, chooser="rule (decider timed out)")


def pre_compact(event: Mapping[str, Any]) -> str:
    """Build and keep the guard; return the note for the summariser (stdout)."""
    messages, _ = history_from_claude_code(str(event["transcript_path"]))
    if _chooser() == "keep":
        # Built at the SessionStart instead (`session_start`); the rule's guard only says
        # whether there will be anything to attach.
        guard = guard_mod.build(messages, web=_on("GUARD_WEB", "0"))
        _log({"event": "PreCompact", "trigger": event.get("trigger"), "deferred": True})
        return guard_mod.instructions(guard)
    guard = _guard(messages)
    text = guard_mod.block(guard)
    folder = _dir()
    if folder.exists():
        _sweep(folder)
    kept = folder / f"{_safe(str(event.get('session_id', '')))}.json"
    _write_private(kept, json.dumps({"block": text, "at": time.time()}))
    _log({"event": "PreCompact", "trigger": event.get("trigger"), **_summary(guard, text)})
    return guard_mod.instructions(guard)


def session_start(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """After a compaction, the guard block as `additionalContext`."""
    if event.get("source") != "compact":
        return None
    if _chooser() == "keep":
        path = str(event["transcript_path"])
        messages, _ = history_from_claude_code(path)
        notes, origin = "", "off"
        if _on("GUARD_NOTES", "1"):  # the summary on disk is the previous compaction's
            from ..context.keep import pending_tasks

            tasks = pending_tasks(calls(messages))
            notes = tasks or last_compact_summary(path)
            origin = "tasks" if tasks else "previous summary" if notes else "none"
        guard = _guard(messages, notes=notes)
        text = guard_mod.block(guard)
        _log({"event": "SessionStart", "origin": "built", "notes_chars": len(notes),
              "notes_origin": origin, **_summary(guard, text)})  # fmt: skip
        if not text:
            return None
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    kept = _dir() / f"{_safe(str(event.get('session_id', '')))}.json"
    text, origin = "", "kept"
    try:
        data = json.loads(kept.read_text(encoding="utf-8"))
        kept.unlink(missing_ok=True)
        if time.time() - float(data.get("at", 0)) > KEPT_SECONDS:
            raise ValueError("the kept guard is stale")
        text = str(data.get("block") or "")
    except (OSError, ValueError, TypeError):
        origin = "rebuilt"
        messages, _ = history_from_claude_code(str(event["transcript_path"]))
        text = guard_mod.block(_guard(messages))
    _log({"event": "SessionStart", "origin": origin, "block_chars": len(text)})
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        return "\n".join(str(response.get(k) or "") for k in ("stdout", "stderr", "output"))
    return ""


def post_tool_use(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """A command that ran before the last compaction runs again: add what it printed then."""
    if event.get("tool_name") != "Bash" or not _on("GUARD_ECHO", "1"):
        return None
    arguments = event.get("tool_input")
    if not isinstance(arguments, Mapping) or not isinstance(arguments.get("command"), str):
        return None
    path = Path(str(event["transcript_path"]))
    if b"compact_boundary" not in path.read_bytes():
        return None  # no compaction: nothing was dropped, and nothing is parsed
    now = Call(id="now", tool="Bash", input=dict(arguments))
    if guard_mod.is_test_run(now):
        return None
    messages, boundary = history_from_claude_code(path)
    before = [c for c in calls(messages[:boundary]) if guard_mod.at_risk(c)]
    earlier = next((c for c in reversed(before) if guard_mod.same_command(c, now)), None)
    if earlier is None:
        return None
    seen_path = _dir() / f"{_safe(str(event.get('session_id', '')))}-echoed.json"
    try:
        seen = set(json.loads(seen_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        seen = set()
    key = guard_mod._key(earlier)
    if key in seen:
        return None
    note = guard_mod.echo(earlier, _response_text(event.get("tool_response")))
    if not note:
        return None
    _write_private(seen_path, json.dumps(sorted(seen | {key})))
    _log({"event": "PostToolUse", "echo": True, "command": guard_mod.source_of(earlier)})
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}


def handle(event: Mapping[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """(plain stdout, JSON stdout) for one event; at most one of them is non-empty."""
    name = event.get("hook_event_name")
    if name == "PreCompact":
        return pre_compact(event), None
    if name == "SessionStart":
        return "", session_start(event)
    if name == "PostToolUse":
        return "", post_tool_use(event)
    return "", None


def _stdin() -> str:
    buffer = getattr(sys.stdin, "buffer", None)
    return buffer.read().decode("utf-8", "replace") if buffer is not None else sys.stdin.read()


def _stdout(text: str) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        event = json.loads(_stdin() or "{}")
        if not isinstance(event, Mapping):
            raise ValueError("the event is not a JSON object")
        text, payload = handle(event)
        if payload is not None:
            _stdout(json.dumps(payload))  # ASCII-escaped: safe on any console code page
        elif text:
            _stdout(text)
    except Exception as error:  # noqa: BLE001 - fail open, and say so
        with contextlib.suppress(Exception):
            sys.stderr.write(f"{PREFIX}: added nothing ({error.__class__.__name__}: {error})\n")
        _log({"event": "error", "error": f"{error.__class__.__name__}: {error}"})
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
