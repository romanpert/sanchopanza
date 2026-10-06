"""The compaction guard as Claude Code command hooks (`sanchopanza guard-hook`).

One process per event, JSON on stdin (https://code.claude.com/docs/en/hooks). What it does is
in `context.guard`; this module only reads the event and the transcript and writes the answer:

- `PreCompact`: builds the guard from the whole transcript, keeps it for the `SessionStart`
  that follows, and prints the note for the summariser. Claude Code 2.1.282 appends the stdout
  of a successful `PreCompact` hook to the summary prompt as additional instructions, on
  manual and automatic compaction alike.
- `SessionStart` with source `compact`: returns the guard block as `additionalContext`, which
  Claude Code places right after the summary.
- Split (`--parts K` on `PreCompact`, `--part i --parts K` on each of K `SessionStart`
  commands, as `sanchopanza install` writes them): `PreCompact` splits the block into at most K
  parts (`context.parts`), each within GUARD_INLINE_CHARS, and keeps one file per part; each
  `SessionStart` command prints its own part, or nothing. Claude Code caps each hook's context
  on its own and joins them, so the whole GUARD_STRUCT_CHARS arrives inline. Without `--part`
  and `--parts` the hook keeps one block within GUARD_INLINE_CHARS, as before.
- `PostToolUse` on `Bash`: when a command that ran before the last compaction runs again and
  its value lines are not all in the new output, appends them once per command and session
  (`guard.echo`). Agents re-run one-shot tools after a compaction instead of searching an
  archive (39 re-runs, 0 archive searches in docs/results/2026-09-28-context-lean), so the
  earlier values are given back where the agent already looks. Without a compaction in the
  transcript it returns before parsing it.

Environment (every name is `SANCHOPANZA_<NAME>`):

    GUARD_CHOOSER    struct (default, no model): whole tool results since the previous compaction,
                     the latest on each file being edited first, then by recency, output that
                     cannot be had again first in each, pointers for re-readable results left out
                     (`context.structural`; measured offline 2026-10-05: Jev's ranking lost to
                     recency, docs/results/2026-10-05-guard-struct); any error there gives the
                     rule's block | rule: value lines of one-shot output by a free rule (the
                     default until 2026-10-05) | judge: every output line judged by the decider,
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
    GUARD_STRUCT_CHARS   struct's budget for whole results (default 44000, about 20k tokens; the
                     replay measured .64-.67 of needed results kept at 44000, .15-.21 at 3000)
    GUARD_POINTER_CHARS  struct's room for pointers (default 1500)
    GUARD_INLINE_CHARS   struct's cap on the whole block, or on each part when split (default
                     9500; 0 for none). Claude Code keeps a hook's additionalContext inline up
                     to 10,000 characters and shows only a 2,000-character preview and a file
                     path past that, so a single block carries about 3,900 to 7,000 characters
                     of results, whatever GUARD_STRUCT_CHARS allows; split, all of it
    GUARD_WEB        "1" to keep lines of WebFetch, WebSearch and MCP output too (off: a page can
                     be fetched again, and its lines could carry instructions aimed at the model)
    GUARD_ECHO       "0" to turn the re-run echo off
    GUARD_DIR        where a PreCompact leaves its guard for the SessionStart (default
                     ~/.sanchopanza/guard); never the project directory, which the agent searches.
                     Files are private to the user and removed when used or after an hour.
    GUARD_LOG        a JSONL file to append one line per event to (off when unset)

Fail open: any error writes one line to stderr and adds nothing; the native summary stands. An
error while splitting gives the rule's block as part 1 and nothing in the others.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import _env
from ..context import guard as guard_mod
from ..context import parts as parts_mod
from ..context.transcript import Call, calls, history_from_claude_code, last_compact_summary
from .hookio import safe_name, state_dir, stdin_text, stdout_json, stdout_text, write_private

PREFIX = "sanchopanza guard"
KEPT_SECONDS = 3_600


def _int(name: str, default: int) -> int:
    try:
        value = int(_env.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _cap(name: str, default: int) -> int:
    """A size where 0 means no cap; anything unreadable or negative is the default."""
    try:
        value = int(_env.get(name, "") or default)
    except ValueError:
        return default
    return value if value >= 0 else default


def _on(name: str, default: str) -> bool:
    return _env.get(name, default).strip() not in ("0", "", "false", "no")


_dir = state_dir
_safe = safe_name


def _log(row: Mapping[str, Any]) -> None:
    path = _env.get("GUARD_LOG", "")
    if not path:
        return
    try:
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": round(time.time(), 3), **row}) + "\n")
    except OSError:
        pass  # a debugging aid never changes what the hook does


_write_private = write_private


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
    return _env.get("GUARD_CHOOSER", "").strip() or "struct"


def _structural(messages: list[dict[str, Any]], since: int, options: Mapping[str, Any]) -> Any:
    """The structural keep, or the rule's guard on any error (the earlier default)."""
    from ..context import structural

    try:
        return structural.build(
            messages,
            since=since,
            facts_chars=_int("GUARD_STRUCT_CHARS", structural.STRUCT_CHARS),
            requests_chars=options["requests_chars"],
            pointer_chars=_int("GUARD_POINTER_CHARS", structural.POINTER_CHARS),
            inline_chars=_cap("GUARD_INLINE_CHARS", structural.INLINE_CHARS),
            web=options["web"],
        )
    except Exception as error:  # noqa: BLE001 - the summariser was promised a block
        _log({"event": "error", "error": f"struct: {error.__class__.__name__}: {error}"})
        rule = guard_mod.build(messages, **options)
        return dataclasses.replace(rule, chooser="struct (error: rule only)")


def _options() -> dict[str, Any]:
    return {
        "facts_chars": _int("GUARD_FACTS_CHARS", guard_mod.FACTS_CHARS),
        "requests_chars": _int("GUARD_REQUESTS_CHARS", guard_mod.REQUESTS_CHARS),
        "web": _on("GUARD_WEB", "0"),
    }


def _guard(messages: list[dict[str, Any]], notes: str = "", since: int = 0) -> guard_mod.Guard:
    options = _options()
    chooser = _chooser()
    if chooser == "struct":
        return _structural(messages, since, options)
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


def _split(messages: list[dict[str, Any]], since: int, parts: int) -> parts_mod.Split:
    """The block in at most `parts` parts (struct); another chooser's block, or the rule's on any
    error while splitting, is part 1 alone."""
    from ..context import structural

    if _chooser() == "struct":
        options = _options()
        try:
            return parts_mod.split(
                messages,
                since=since,
                facts_chars=_int("GUARD_STRUCT_CHARS", structural.STRUCT_CHARS),
                requests_chars=options["requests_chars"],
                pointer_chars=_int("GUARD_POINTER_CHARS", structural.POINTER_CHARS),
                inline_chars=_cap("GUARD_INLINE_CHARS", structural.INLINE_CHARS),
                parts=parts,
                web=options["web"],
            )
        except Exception as error:  # noqa: BLE001 - the summariser was promised a block
            _log({"event": "error", "error": f"parts: {error.__class__.__name__}: {error}"})
            guard = dataclasses.replace(guard_mod.build(messages, **options),
                                        chooser="struct (error: rule only)")  # fmt: skip
    else:
        guard = _guard(messages, since=since)
    text = guard_mod.block(guard)
    return parts_mod.Split((text,) if text else (), guard)


def _part_path(session: str, part: int) -> Path:
    return _dir() / f"{_safe(session)}.part{part}.json"


def _pre_compact_parts(event: Mapping[str, Any], parts: int) -> str:
    """Split the block, keep one file per part (1 to `parts`, empty past the last), return the
    note. Each part's `SessionStart` command reads and removes its own file: no shared state."""
    messages, boundary = history_from_claude_code(str(event["transcript_path"]))
    split = _split(messages, boundary, parts)
    folder = _dir()
    name = _safe(str(event.get("session_id", "")))
    if folder.exists():
        _sweep(folder)
        for old in [folder / f"{name}.json", *folder.glob(f"{name}.part*.json")]:
            with contextlib.suppress(OSError):
                old.unlink()
    now, count = time.time(), len(split.texts)
    for part in range(1, parts + 1):
        text = split.texts[part - 1] if part <= count else ""
        kept = {"part": part, "of": count, "text": text, "at": now}
        _write_private(folder / f"{name}.part{part}.json", json.dumps(kept))
    _log({"event": "PreCompact", "trigger": event.get("trigger"), "parts": count,
          "part_chars": [len(t) for t in split.texts],
          **_summary(split.guard, "\n".join(split.texts))})  # fmt: skip
    return guard_mod.instructions(split.guard)


def pre_compact(event: Mapping[str, Any], parts: int = 0) -> str:
    """Build and keep the guard, split in `parts` parts when above 1; return the note for the
    summariser (stdout)."""
    if parts > 1 and _chooser() != "keep":
        return _pre_compact_parts(event, parts)
    messages, boundary = history_from_claude_code(str(event["transcript_path"]))
    if _chooser() == "keep":
        # Built at the SessionStart instead (`session_start`); the rule's guard only says
        # whether there will be anything to attach.
        guard = guard_mod.build(messages, web=_on("GUARD_WEB", "0"))
        _log({"event": "PreCompact", "trigger": event.get("trigger"), "deferred": True})
        return guard_mod.instructions(guard)
    guard = _guard(messages, since=boundary)
    text = guard_mod.block(guard)
    folder = _dir()
    if folder.exists():
        _sweep(folder)
    kept = folder / f"{_safe(str(event.get('session_id', '')))}.json"
    _write_private(kept, json.dumps({"block": text, "at": time.time()}))
    _log({"event": "PreCompact", "trigger": event.get("trigger"), **_summary(guard, text)})
    return guard_mod.instructions(guard)


def _context(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def _kept_single(session: str) -> str | None:
    """A single block kept by a `PreCompact` without `--parts`, read and left in place (the other
    parts' commands look at it too); None when there is none or it is stale."""
    try:
        data = json.loads((_dir() / f"{_safe(session)}.json").read_text(encoding="utf-8"))
        if time.time() - float(data.get("at", 0)) > KEPT_SECONDS:
            return None
        return str(data.get("block") or "")
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _session_start_part(event: Mapping[str, Any], part: int, parts: int) -> dict[str, Any] | None:
    """Part `part` of the split block: its kept file, else a single kept block (part 1 only),
    else the same split rebuilt from the transcript (pure, so every part rebuilds the same)."""
    session = str(event.get("session_id", ""))
    kept = _part_path(session, part)
    origin = "kept"
    try:
        data = json.loads(kept.read_text(encoding="utf-8"))
        kept.unlink(missing_ok=True)
        if time.time() - float(data.get("at", 0)) > KEPT_SECONDS:
            raise ValueError("the kept part is stale")
        text, of = str(data.get("text") or ""), data.get("of")
    except (OSError, ValueError, TypeError, AttributeError):
        single = _kept_single(session)
        if single is not None:
            origin, text, of = "kept single", single if part == 1 else "", 1
        else:
            origin = "rebuilt"
            messages, boundary = history_from_claude_code(str(event["transcript_path"]))
            texts = _split(messages, boundary, max(parts, part)).texts
            text, of = (texts[part - 1] if part <= len(texts) else ""), len(texts)
    _log({"event": "SessionStart", "origin": origin, "part": part, "of": of,
          "block_chars": len(text)})  # fmt: skip
    return _context(text)


def session_start(event: Mapping[str, Any], part: int = 0, parts: int = 0) -> dict[str, Any] | None:
    """After a compaction, the guard block, or part `part` of it, as `additionalContext`."""
    if event.get("source") != "compact":
        return None
    if part > 1 and _chooser() == "keep":
        return None  # keep builds one block at the SessionStart: part 1 carries it
    if part > 0 and _chooser() != "keep":
        return _session_start_part(event, part, parts or parts_mod.PARTS)
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
        return _context(text)
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
        messages, boundary = history_from_claude_code(str(event["transcript_path"]))
        text = guard_mod.block(_guard(messages, since=boundary))
    _log({"event": "SessionStart", "origin": origin, "block_chars": len(text)})
    return _context(text)


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


def handle(
    event: Mapping[str, Any], part: int = 0, parts: int = 0
) -> tuple[str, dict[str, Any] | None]:
    """(plain stdout, JSON stdout) for one event; at most one of them is non-empty. `part` and
    `parts` are the command's `--part` and `--parts` (0 when absent)."""
    name = event.get("hook_event_name")
    if name == "PreCompact":
        return pre_compact(event, parts), None
    if name == "SessionStart":
        return "", session_start(event, part, parts)
    if name == "PostToolUse":
        return "", post_tool_use(event)
    return "", None


def _arguments(argv: list[str] | None) -> tuple[int, int]:
    """(--part, --parts) from `argv`; 0 for an absent, unreadable or negative one."""
    found = {"--part": 0, "--parts": 0}
    words = list(argv or [])
    for at, flag in enumerate(words):
        value = words[at + 1] if at + 1 < len(words) else ""
        if flag in found:
            with contextlib.suppress(ValueError):
                found[flag] = max(0, int(value))
    return found["--part"], found["--parts"]


def main(argv: list[str] | None = None, *, part: int = 0, parts: int = 0) -> int:
    """One event from stdin. `argv` may carry `--part i` and `--parts K` (the keywords win)."""
    try:
        read_part, read_parts = _arguments(argv)
        part, parts = part or read_part, parts or read_parts
        event = json.loads(stdin_text() or "{}")
        if not isinstance(event, Mapping):
            raise ValueError("the event is not a JSON object")
        text, payload = handle(event, part, parts)
        if payload is not None:
            stdout_json(payload)
        elif text:
            stdout_text(text)
    except Exception as error:  # noqa: BLE001 - fail open, and say so
        with contextlib.suppress(Exception):
            sys.stderr.write(f"{PREFIX}: added nothing ({error.__class__.__name__}: {error})\n")
        _log({"event": "error", "error": f"{error.__class__.__name__}: {error}"})
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
