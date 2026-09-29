"""The autopilot: sanchopanza keeps the context lean by itself; the agent never asks for it.

Three hook bodies for Claude Code (https://code.claude.com/docs/en/hooks), each acting only on
content being ADDED to the conversation, never on what is already in it:

- **Arrival** (`PostToolUse`): a tool result over `threshold` characters is cut to the parts
  that bear on the current task (`context.arrival`: the multi-level tournament), the full text
  goes to the archive, and the agent receives the kept parts in their original order with
  omission markers and one line naming the archive file. The replacement is
  `hookSpecificOutput.updatedToolOutput`, which Claude Code applies to every tool, built-in or
  MCP, and which "must match the tool's output shape": the hook replaces the one string field
  that holds the text (Read's `file.content`, Bash's `stdout`, WebFetch's `result`, Grep's
  `content`, an MCP text block) inside a copy of the original response, so the shape is the
  tool's own. A value that does not match is ignored by Claude Code, which then uses the
  original: a failure of ours degrades to "nothing cut".
- **Recall on a tool call** (`PostToolUse`, appended): BM25 over the archive and the memory
  files with the latest prompt and what the agent is doing now, one in-context triage of the
  top `k`, and what contributes is appended as `additionalContext` with its file paths.
- **Recall on a prompt** (`UserPromptSubmit`): the same store and shape, with the prompt.

Compaction is the plugin's (`compact_hook.ts`, arm `mask`: free observation masking into the
archive; no decider asked, see `context.compact`).

Fail open everywhere: any error, an unanswered decision, a cut that saves too little or a
session over its ceiling returns the event untouched, with the reason on stderr.

A per-session ledger (`.sanchopanza/autopilot/<session>.json`) holds the dollars and decisions
spent by these hooks across processes (each hook is a fresh process and a fresh squire) and the
archive files already injected in the current context, so the same entry is not proposed again
until a compaction clears the list. `SANCHOPANZA_SESSION_MAX_USD` (default 0.50) is the ceiling.

Environment (every name is `SANCHOPANZA_<NAME>`):

    AUTOPILOT          "1": arrival, recall on prompts and recall on tool calls
    ARRIVAL, RECALL, RECALL_ON_TOOL   "1"/"0": each piece on its own (override AUTOPILOT
                       and RECALL_ON)
    RECALL_ON          where recall runs: both | prompt | tool | off (unset: as AUTOPILOT)
    ARRIVAL_MODE       jev (default: the tournament) | free (`arrival.free_cut`, no decider)
    ARRIVAL_FREE_CHARS  free mode: characters kept at most (default 8000; below 1000, the default)
    ARRIVAL_CHARS      threshold for a cut (default 6000)
    ARRIVAL_ERROR_CHARS  threshold for a result that reads as a failure (default 20000)
    ARRIVAL_MIN_SAVING   a cut that saves less passes whole (default 0.2)
    ARRIVAL_SENTENCES  "0": never cut below the block
    RECALL_K           BM25 candidates judged per recall (default 5)
    RECALL_CAP         characters of injected context per recall (default 6000)
    ARCHIVE            archive root (default <cwd>/.sanchopanza/archive)
    STUB_STYLE         read by `sanchopanza compact`: plain | index | cleared
    SESSION_MAX_USD    ceiling for these hooks per session (default 0.50)
"""

from __future__ import annotations

import contextlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import _env
from ..context import archive as archive_mod

if TYPE_CHECKING:
    from ..squire import Squire

SKIP_KEYS = frozenset({"filePath", "file_path", "url", "query", "type", "codeText"})
ERROR_FIELDS = frozenset({"stderr"})
NOT_CUT = frozenset({"Agent", "Task"})  # a subagent's report is already a compression
LEDGER = "autopilot"
ARRIVAL_MODES = ("jev", "free")
RECALL_PLACES = {
    "both": (True, True),
    "prompt": (True, False),
    "tool": (False, True),
    "off": (False, False),
}  # (on prompts, on tool calls)


def _flag(name: str, default: bool, env: Mapping[str, str] | None) -> bool:
    value = _env.get(name, "", env=env).strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def _number(name: str, default: float, env: Mapping[str, str] | None) -> float:
    try:
        return float(_env.get(name, "", env=env) or default)
    except ValueError:
        return default


FREE_CHARS_DEFAULT = 8_000
FREE_CHARS_MIN = 1_000


def _free_chars(env: Mapping[str, str] | None) -> int:
    """`ARRIVAL_FREE_CHARS`, or the default when it is below `FREE_CHARS_MIN` or not a finite
    number: a bad value must not cut every result on arrival down to nothing."""
    value = _number("ARRIVAL_FREE_CHARS", FREE_CHARS_DEFAULT, env)
    if not math.isfinite(value) or value < FREE_CHARS_MIN:
        say(
            f"SANCHOPANZA_ARRIVAL_FREE_CHARS={value!r} is below {FREE_CHARS_MIN}: "
            f"using the default {FREE_CHARS_DEFAULT}"
        )
        return FREE_CHARS_DEFAULT
    return int(value)


@dataclass(frozen=True, slots=True)
class Config:
    arrival: bool = False
    recall: bool = False
    recall_on_tool: bool = False
    threshold: int = 6_000
    error_threshold: int = 20_000
    min_saving: float = 0.2
    sentences: bool = True
    arrival_mode: str = "jev"
    free_target: int = 8_000
    k: int = 5
    cap: int = 6_000
    archive: str = ""
    session_max_usd: float = 0.50

    @property
    def any(self) -> bool:
        return self.arrival or self.recall or self.recall_on_tool


def _choice(name: str, choices: Sequence[str], env: Mapping[str, str] | None) -> str | None:
    """The variable's value if it is one of `choices`; None when unset or unknown (said so)."""
    value = _env.get(name, "", env=env).strip().lower()
    if value and value not in choices:
        say(f"SANCHOPANZA_{name}={value!r} is not one of {tuple(choices)}: ignored")
    return value if value in choices else None


def config_from_env(env: Mapping[str, str] | None = None) -> Config:
    on = _flag("AUTOPILOT", False, env)
    place = _choice("RECALL_ON", tuple(RECALL_PLACES), env)
    on_prompt, on_tool = RECALL_PLACES[place] if place else (on, on)
    return Config(
        arrival=_flag("ARRIVAL", on, env),
        recall=_flag("RECALL", on_prompt, env),
        recall_on_tool=_flag("RECALL_ON_TOOL", on_tool, env),
        arrival_mode=_choice("ARRIVAL_MODE", ARRIVAL_MODES, env) or "jev",
        free_target=_free_chars(env),
        threshold=int(_number("ARRIVAL_CHARS", 6_000, env)),
        error_threshold=int(_number("ARRIVAL_ERROR_CHARS", 20_000, env)),
        min_saving=_number("ARRIVAL_MIN_SAVING", 0.2, env),
        sentences=_flag("ARRIVAL_SENTENCES", True, env),
        k=int(_number("RECALL_K", 5, env)),
        cap=int(_number("RECALL_CAP", 6_000, env)),
        archive=_env.get("ARCHIVE", "", env=env),
        session_max_usd=_number("SESSION_MAX_USD", 0.50, env),
    )


# --- the text field of a tool response ------------------------------------------------------

Path_ = tuple[Any, ...]


def _leaves(value: Any, path: Path_ = (), depth: int = 0) -> list[tuple[Path_, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if depth >= 4:
        return []
    if isinstance(value, Mapping):
        out: list[tuple[Path_, str]] = []
        for key, item in value.items():
            if key not in SKIP_KEYS:
                out.extend(_leaves(item, (*path, key), depth + 1))
        return out
    if isinstance(value, list):
        return [
            leaf for i, item in enumerate(value) for leaf in _leaves(item, (*path, i), depth + 1)
        ]
    return []


def text_field(response: Any) -> tuple[Path_, str] | None:
    """The path and text of the longest string in the response: where its content is."""
    leaves = _leaves(response)
    return max(leaves, key=lambda leaf: len(leaf[1])) if leaves else None


def replaced(response: Any, path: Path_, text: str) -> Any:
    """A copy of `response` with the string at `path` replaced. Nothing else changes."""
    if not path:
        return text
    head, rest = path[0], path[1:]
    if isinstance(response, Mapping):
        return {**response, head: replaced(response[head], rest, text)}
    items = list(response)
    return [*items[:head], replaced(items[head], rest, text), *items[head + 1 :]]


def _line_offset(tool: str, response: Any) -> int:
    if tool == "Read" and isinstance(response, Mapping):
        file = response.get("file")
        if isinstance(file, Mapping) and isinstance(file.get("startLine"), int):
            return max(0, file["startLine"] - 1)
    return 0


# --- the session ledger ---------------------------------------------------------------------


def _ledger_path(root: Path, session: str) -> Path:
    return root.parent / LEDGER / f"{archive_mod.safe_name(session or 'session')}.json"


def read_ledger(root: Path, session: str) -> dict[str, Any]:
    try:
        value = json.loads(_ledger_path(root, session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"usd": 0.0, "decisions": 0, "injected": []}
    return value if isinstance(value, dict) else {"usd": 0.0, "decisions": 0, "injected": []}


def write_ledger(root: Path, session: str, ledger: Mapping[str, Any]) -> None:
    path = _ledger_path(root, session)
    archive_mod.keep_out_of_git(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(ledger)), encoding="utf-8")


def clear_injected(root: Path, session: str) -> None:
    """After a compaction what was injected is gone from the context: it may come back."""
    ledger = read_ledger(root, session)
    if ledger.get("injected"):
        write_ledger(root, session, {**ledger, "injected": []})


def _charged(ledger: Mapping[str, Any], squire: Squire, injected: Sequence[str] = ()) -> dict:
    return {
        **ledger,
        "usd": float(ledger.get("usd", 0.0)) + squire.meter.cost_usd,
        "decisions": int(ledger.get("decisions", 0)) + squire.meter.decisions,
        "injected": sorted({*ledger.get("injected", []), *injected}),
    }


# --- context of the event -------------------------------------------------------------------


def _messages(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    from ..context.transcript import messages_from_claude_code

    path = str(event.get("transcript_path") or "")
    if not path:
        return []
    try:
        return messages_from_claude_code(path)
    except (OSError, ValueError):
        return []


def _root(event: Mapping[str, Any], config: Config) -> Path:
    return archive_mod.root_for(str(event.get("cwd") or "") or None, override=config.archive)


def _session(event: Mapping[str, Any]) -> str:
    return str(event.get("session_id") or "session")


def say(text: str) -> None:
    with contextlib.suppress(Exception):
        sys.stderr.write(f"sanchopanza autopilot: {text}\n")


def wants(event: Mapping[str, Any], config: Config) -> bool:
    """Pure code, before any import that costs: can this event lead to a decision?"""
    from .generic import text_of

    kind = str(event.get("hook_event_name", ""))
    if kind == "UserPromptSubmit":
        return config.recall and bool(str(event.get("prompt") or "").strip())
    if kind != "PostToolUse":
        return False
    if config.recall_on_tool and any(_root(event, config).glob("*/*.txt")):
        return True
    if not config.arrival or str(event.get("tool_name", "")) in NOT_CUT:
        return False
    return len(text_of(event.get("tool_response"))) >= config.threshold


# --- arrival --------------------------------------------------------------------------------


async def _arrive(
    event: Mapping[str, Any], squire: Squire, config: Config, messages: Sequence[Any]
) -> tuple[Any, str | None]:
    """(updated response or None, archive path or None)."""
    from ..context import arrival

    tool = str(event.get("tool_name", ""))
    if tool in NOT_CUT:
        return None, None
    response = event.get("tool_response")
    found = text_field(response)
    if found is None:
        return None, None
    path, text = found
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    in_errors = bool(path) and path[-1] in ERROR_FIELDS
    settings = arrival.Settings(
        threshold=config.error_threshold if in_errors else config.threshold,
        error_threshold=config.error_threshold,
        min_saving=config.min_saving,
        sentences=config.sentences,
        target=config.free_target,
    )
    if arrival.gate(text, settings):
        return None, None
    purpose = arrival.purpose_of(messages, tool, tool_input)
    if config.arrival_mode == "free":
        offset = _line_offset(tool, response)
        result = arrival.free_cut(text, purpose, settings, line_offset=offset)
    else:
        result = await arrival.cut(
            squire,
            text,
            tool=tool,
            tool_input=tool_input,
            purpose=purpose,
            settings=settings,
            line_offset=_line_offset(tool, response),
        )
    record = {"tool": tool, "mode": config.arrival_mode, "reason": result.reason, **result.report}
    squire.journal.record("arrival", record)
    if result.text is None:
        say(f"{tool} result passed whole: {result.reason}")
        return None, None
    name = f"arrival-{event.get('tool_use_id') or tool}"
    meta = {"tool": tool, "about": arrival._call_summary(tool, tool_input)[:160], "by": "arrival"}
    saved = archive_mod.write_entry(
        archive_mod.session_dir(_root(event, config), _session(event)), name, text, meta
    )
    omitted = int(result.report.get("omitted", 0))
    head = arrival.header(tool, len(result.text), len(text), omitted, saved)
    return replaced(response, path, head + result.text), str(saved)


# --- recall ---------------------------------------------------------------------------------


def _store(event: Mapping[str, Any], config: Config, query: str) -> tuple[list, str]:
    from . import memory_gate as mg

    directory = mg.memory_dir_for(event)
    memories = mg.load_memories(directory) if directory is not None else ()
    entries = archive_mod.load_entries(_root(event, config))
    return list(mg.store_of(memories, entries, query)), str(directory or "")


def tool_query(messages: Sequence[Any], event: Mapping[str, Any]) -> str:
    from ..context.arrival import purpose_of

    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    return purpose_of(messages, str(event.get("tool_name", "")), tool_input)


async def _recall(
    event: Mapping[str, Any],
    squire: Squire,
    config: Config,
    query: str,
    exclude: Sequence[str],
    *,
    ask_recall: bool,
) -> tuple[str, tuple[str, ...]]:
    from . import memory_gate as mg

    store, directory = _store(event, config, query)
    if not store:
        return "", ()
    result = await mg.recall(
        squire,
        query,
        store,
        k=config.k,
        directory=directory,
        cap=config.cap,
        ask_recall=ask_recall,
        exclude=exclude,
    )
    squire.journal.record("recall", {"reason": result.reason, **dict(result.report)})
    if not result.context:
        say(f"recall: {result.reason}")
    return result.context, result.injected


# --- hook entries ---------------------------------------------------------------------------


def _over_ceiling(ledger: Mapping[str, Any], config: Config) -> bool:
    return float(ledger.get("usd", 0.0)) >= config.session_max_usd


async def post_tool_use(event: Mapping[str, Any], squire: Squire, config: Config) -> dict:
    """Arrival cut and recall for one tool result. Never raises; `{}` means untouched."""
    root, session = _root(event, config), _session(event)
    ledger = read_ledger(root, session)
    if _over_ceiling(ledger, config):
        say(f"session ceiling {config.session_max_usd} USD reached: passing through")
        return {}
    updated, saved, context, injected = None, None, "", ()
    try:
        messages = _messages(event)
        if config.arrival:
            updated, saved = await _arrive(event, squire, config, messages)
        if config.recall_on_tool:
            exclude = [*ledger.get("injected", []), *([saved] if saved else [])]
            context, injected = await _recall(
                event, squire, config, tool_query(messages, event), exclude, ask_recall=False
            )
    except Exception as error:  # fail open at the hook boundary
        say(f"failed open: {error.__class__.__name__}: {error}")
    with contextlib.suppress(OSError):
        write_ledger(root, session, _charged(ledger, squire, injected))
    out: dict[str, Any] = {"hookEventName": "PostToolUse"}
    if updated is not None:
        out["updatedToolOutput"] = updated
    if context:
        out["additionalContext"] = context
    return {"hookSpecificOutput": out} if len(out) > 1 else {}


async def user_prompt(event: Mapping[str, Any], squire: Squire, config: Config) -> dict:
    """Recall over memory files and the archive for one prompt. Never raises."""
    from . import memory_gate as mg

    root, session = _root(event, config), _session(event)
    ledger = read_ledger(root, session)
    if _over_ceiling(ledger, config):
        say(f"session ceiling {config.session_max_usd} USD reached: no recall")
        return {}
    context, injected = "", ()
    try:
        prompt = str(event.get("prompt") or "")
        context, injected = await _recall(
            event, squire, config, prompt, ledger.get("injected", []), ask_recall=True
        )
    except Exception as error:
        say(f"recall failed open: {error.__class__.__name__}: {error}")
    with contextlib.suppress(OSError):
        write_ledger(root, session, _charged(ledger, squire, injected))
    return mg.hook_output(context) if context else {}
