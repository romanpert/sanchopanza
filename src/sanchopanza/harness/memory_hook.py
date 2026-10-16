"""Memory between requests and between sessions (`sanchopanza memory-hook`).

Classic command hooks, one process per event (https://code.claude.com/docs/en/hooks); they
fire in `claude -p` as in an interactive session. What a record holds is `context.episodes`.

- `Stop` and `SessionEnd`: every finished request of the session is recorded verbatim, by
  code, in the project's store. Idempotent: a record is rewritten only when it changed.
- `PostToolUse` on `Read|Edit|MultiEdit|Write|NotebookEdit` (**just in time**, code only):
  when the agent opens or changes a file, a record of an earlier request that changed it, once
  per session until the next compaction. Which one (v4): the record whose written lines the
  agent is looking at (a Read's content, an Edit's old_string; each record keeps prints of the
  lines it wrote), and at an edit with none in view the newest. This is where
  memory pays in people's sessions: a prompt often names nothing ("fix it", "push"), but the
  file the agent opens does. It reads one index file (`episodes.INDEX`), not every record.
- `UserPromptSubmit`: first the same recording (a `Stop` that did not run is caught up, for
  this session and for the project's other recent sessions), then, when `MEMORY_PROMPT` says
  so, recall at the prompt. By default that is only at the session's first live request (its
  start, or after a compaction took every earlier request out) and only with a decider: BM25
  proposes `MEMORY_K`, the decider says which are about the same code as the request
  (`points.memory.related_questions`), and records at `MEMORY_KEEP_AT` or above enter. v5:
  there, a record that changed files enters only if the prompt names one of them
  (`named_in`), and the decider is not asked when no candidate can enter; a record that
  changed nothing (a question, an investigation) is judged as before.

Candidates are always the project's records **not in the live context** (`episodes.Split.live`)
and not already given to this session since its last compaction.

Measured on real people's sessions (SWE-chat, 60 groups of one person on one public
repository, 953 development requests, docs/results/2026-10-01-memory-real), the shipped hook
replayed through this code: 94 % of the requests with a related earlier record had one in view,
73 % of what was given was related, and 3.7 % of the requests with nothing related were given
anything (v3, the two newest records per file: 94 %, 60 %, 4.9 %; v2, recall at every prompt
with the decider at 0.2: 25 %, 2.6 %, 39 %).

Nothing already in the conversation is rewritten: records are appended with the prompt or the
tool result, so no cached prefix is invalidated. Records live outside the project
(`MEMORY_STORE`, default `~/.sanchopanza/memory-store/<project>/`), readable by this user only,
and are removed after 30 days: they hold command output. `<project>` is the git repository the
session started in, shared by its worktrees (F1, `memory_store`).

Environment (every name is `SANCHOPANZA_<NAME>`):

    MEMORY_SELECT            decider (default when a provider or a TypeSafe key is set) | bm25
                             (the top MEMORY_BM25_KEEP by score, no model) | off (record only;
                             no touch either)
    MEMORY_PROMPT            first (default with a decider) | every | off (default without one)
    MEMORY_TOUCH             on (default) | off;  MEMORY_TOUCH_K  1
    MEMORY_K, MEMORY_BM25_KEEP   5 and 2
    MEMORY_KEEP_AT           the decider's probability a record needs at a prompt (default 0.8)
    MEMORY_PROMPT_NAMED      on (default) | off: the v5 gate at a first prompt; off is v4.1
    MEMORY_CHARS             cap of the injected text (default 6000)
    MEMORY_DECIDER_SECONDS   the decider's time (default 15); past it, nothing is injected
    MEMORY_STORE             the store's root; MEMORY_STORE_LOG a JSONL file, one line per event
    MEMORY_STORE_KEY         repo (default: the session's git repository) | folder (before F1)
    MEMORY_RULES             on (default) | off: standing rules kept at Stop, given at start
    MEMORY_RULES_AUDIT       off (default) | on: at Stop, hold the request's diff against the
                             rules and send a confident break back once (`memory_rules.audit_on`)
    MEMORY_NATIVE            off (default) | 1: at Stop, the session's records also go into
                             Claude Code's own auto memory (one note, one index line), and a
                             new session is not given again what that note carries
                             (`memory_native`; `install --memory-native`)
    MEMORY_WINDOW            short (default here) | long: the decider reads each candidate
                             record whole (Jev's long-context header only past its short
                             window), within MEMORY_DECIDER_SECONDS less 3 s, and the pages
                             when it cannot (`memory_window`; opt-in here: on records it
                             was worse on noise, docs/results/2026-10-16-memgate-hook; the
                             library gate `memory_gate.gate` defaults to long)

Cost: the touch calls no model; at most one decider call at a session's first prompt (two with
`MEMORY_WINDOW=long` when the long call falls back and the pages are judged after it).
Latency: a touch is a new process, 0.17 s median on the maintainer's Windows laptop.

Fail open: any error writes one line to stderr and injects nothing. A decider that answers no
page injects nothing either.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import _env
from ..context import episodes as ep
from ..context.archive import safe_name
from ..context.transcript import _is_boundary
from . import memory_native, memory_store, memory_tree
from .hookio import stdin_text, stdout_json

# Split out of this module (review of F1); re-exported, and they look this module's names up at
# call time, so `mh.<name> = ...` in tests and benchmarks/memory_real still reaches them.
from .memory_recall import (  # noqa: F401 - re-exported
    BM25_KEEP,
    CHARS,
    CLOSING,
    HEADER,
    KEEP_AT,
    NAMED_STEM,
    K,
    _choose,
    _fold,
    candidates,
    gate_named,
    gate_passes,
    keep_by_decider,
    named_in,
    pool_of,
    recall,
    render,
)
from .memory_store import log as _log
from .memory_touch import (  # noqa: F401 - re-exported
    DENIED,
    PATH_IN_HEADER,
    SHELL_EDIT_RULE,
    SHELL_FIRST_NOTE,
    SHELL_READS,
    SHELL_TOOLS,
    TOUCH_HEADER,
    TOUCH_K,
    TOUCH_LOAD,
    TOUCH_TOOLS,
    _absolute,
    _give,
    _norm,
    _wanted,
    bash_view,
    choose_touched,
    render_touch,
    seen_prints,
    shell_first,
    shell_first_on,
    shell_written,
    touch,
)
from .memory_tree import TREE, finish_tree, with_tree  # noqa: F401 - re-exported

PREFIX = "sanchopanza memory"
CATCH_UP = 3  # the project's other sessions caught up per prompt, most recent first
CATCH_UP_BYTES = 20_000_000
CATCH_UP_SECONDS = 86_400
SHOWN = "shown"  # per-session record of what was given since the last compaction


def _int(name: str, default: int) -> int:
    try:
        value = int(_env.get(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _float(name: str, default: float) -> float:
    try:
        value = float(_env.get(name, "") or default)
    except ValueError:
        return default
    return value if 0.0 <= value <= 1.0 else default


def mode() -> str:
    chosen = _env.get("MEMORY_SELECT", "").strip().lower()
    if chosen in ("decider", "bm25", "off"):
        return chosen
    provider = _env.get("PROVIDER", "").strip()
    has_decider = provider not in ("", "null") or bool(os.environ.get("TYPESAFE_API_KEY"))
    return "decider" if has_decider else "bm25"


def prompt_mode() -> str:
    """When recall runs at a prompt: `first` (no earlier request of the session is in the live
    context: its start, or after a compaction), `every`, or `off`. By default `first` with a
    decider and `off` without one: BM25 alone gave something to 82 % of real session starts that
    had nothing related (SWE-chat, 2026-10-01). The touch runs either way."""
    chosen = str(_env.get("MEMORY_PROMPT", "") or "").strip().lower()
    if mode() == "off":
        return "off"
    if chosen in ("first", "every", "off"):
        return chosen
    return "first" if mode() == "decider" else "off"


def store_for(event: Mapping[str, Any]) -> Path:
    """The project's folder: the git repository the session started in, worked out once per
    session (`memory_store`); else as Claude Code names the project (the transcript's folder),
    else from the working directory."""
    return memory_store.store_for(event)


def session_cwd(entries: Sequence[Mapping[str, Any]], fallback: str = "") -> str:
    """Where the session started: paths in its records are written relative to it."""
    return next((str(e["cwd"]) for e in entries if e.get("cwd")), fallback)


@dataclass(frozen=True, slots=True)
class Recorded:
    """What recording one transcript found."""

    episodes: tuple[ep.Episode, ...]
    live: frozenset[int]
    boundaries: int
    written: tuple[str, ...]
    cwd: str = ""
    requests: int = 0


def record_transcript(
    path: Path, session: str, store: Path, cwd: str = "",
    entries: Sequence[Mapping[str, Any]] | None = None,
) -> Recorded:  # fmt: skip
    entries = ep.entries_of(path) if entries is None else entries
    start = session_cwd(entries, cwd)
    found, live = ep.episodes_of(entries, session=session, cwd=start)
    found = [with_tree(store, e) for e in found]
    boundaries = sum(1 for e in entries if _is_boundary(e))
    written = ep.save(store, found, session=session)
    requests = len(ep.split_requests(entries).groups)
    return Recorded(tuple(found), live, boundaries, tuple(written), start, requests)


def record(event: Mapping[str, Any]) -> Recorded:
    session = str(event.get("session_id") or "session")
    path = Path(str(event["transcript_path"]))
    return record_transcript(path, session, store_for(event), str(event.get("cwd") or ""))


def catch_up(event: Mapping[str, Any]) -> list[str]:
    """Record the project's other recent sessions whose records are older than their transcript
    (a session killed before its Stop or SessionEnd). Best effort; the keys written."""
    current = Path(str(event.get("transcript_path") or ""))
    if not current.name:
        return []
    store = store_for(event)
    cutoff = time.time() - CATCH_UP_SECONDS
    others = []
    for path in current.parent.glob("*.jsonl"):
        with contextlib.suppress(OSError):
            stat = path.stat()
            if path != current and stat.st_mtime >= cutoff and stat.st_size <= CATCH_UP_BYTES:
                others.append((stat.st_mtime, path))
    written: list[str] = []
    for mtime, path in sorted(others, reverse=True)[:CATCH_UP]:
        records = list(store.glob(f"{safe_name(path.stem)}-*.json"))
        if records and max(r.stat().st_mtime for r in records) >= mtime:
            continue
        with contextlib.suppress(Exception):  # someone else's transcript is never our failure
            written.extend(record_transcript(path, path.stem, store).written)
    return written


def tree_at_prompt(
    event: Mapping[str, Any], store: Path, session: str, cwd: str, requests: int
) -> None:
    """A request that ended without its Stop (Esc) is finished first (review of v6, M6); then
    the new request's start snapshot is kept."""
    if not memory_tree.tree_on():
        return
    opened = memory_tree.open_request(store, session)
    if opened is not None and opened == requests and requests > 0:
        entries = ep.entries_of(Path(str(event["transcript_path"])))
        if memory_tree.finish_tree(store, session, entries, opened, note=_log):
            found, _ = ep.episodes_of(entries, session=session, cwd=cwd)
            ep.save(store, [with_tree(store, e) for e in found if e.index == opened])
    memory_tree.start_tree(store, session, cwd, requests + 1, note=_log)


def stop(event: Mapping[str, Any]) -> Recorded:
    """Stop: the record first (a slow tree never costs it), then what the tree says the request
    wrote, merged into its record (review of v6, H1)."""
    path = Path(str(event["transcript_path"]))
    session, store = str(event.get("session_id") or "session"), store_for(event)
    entries = ep.entries_of(path)
    seen = record_transcript(path, session, store, str(event.get("cwd") or ""), entries)
    with contextlib.suppress(Exception):  # the tree is extra; it never costs the record
        if memory_tree.finish_tree(store, session, entries, note=_log):
            last = [e for e in seen.episodes if e.index == seen.requests]
            ep.save(store, [with_tree(store, e) for e in last])
        memory_tree.prune(store)
    return seen


# ---- what this session was already given ------------------------------------------------------


def _shown_path(store: Path, session: str) -> Path:
    return store / SHOWN / f"{safe_name(session)}.json"


def _state(store: Path, session: str) -> dict[str, Any]:
    try:
        data = json.loads(_shown_path(store, session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def shown_since_compaction(store: Path, session: str, boundaries: int) -> frozenset[str]:
    data = _state(store, session)
    if data.get("boundaries") != boundaries:
        return frozenset()  # a compaction since: what was given is no longer verbatim
    return frozenset(str(k) for k in data.get("keys") or [])


def remember_shown(store: Path, session: str, boundaries: int, keys: Sequence[str]) -> None:
    """Add `keys` to what this session was given. The caller holds `ep.locked` on the state."""
    before = shown_since_compaction(store, session, boundaries)
    payload = {**_state(store, session), "boundaries": boundaries,
               "keys": sorted(before | set(keys))}  # fmt: skip
    ep.write_private(_shown_path(store, session), json.dumps(payload))


def note_live(
    store: Path, session: str, boundaries: int, live: frozenset[int] | None, cwd: str = ""
) -> None:
    """What the session had in its live context at its last prompt or compaction, and where it
    started, for the touch, which must not read the whole transcript on every file opened."""
    with ep.locked(_shown_path(store, session)):
        kept = shown_since_compaction(store, session, boundaries)
        payload = {"boundaries": boundaries, "keys": sorted(kept), "cwd": cwd,
                   "live": None if live is None else sorted(live)}  # fmt: skip
        ep.write_private(_shown_path(store, session), json.dumps(payload))


def live_at_last_prompt(store: Path, session: str) -> tuple[int, frozenset[int] | None]:
    data = _state(store, session)
    live = data.get("live")
    return int(data.get("boundaries") or 0), None if live is None else frozenset(live)


def after_compaction(event: Mapping[str, Any]) -> dict[str, Any]:
    """SessionStart after a compaction: what is live changed in the middle of a request, and what
    was given before it is gone with the summary; the touch must know before the next prompt.

    Claude Code writes the `compact_boundary` entry after the SessionStart hooks run (measured
    2026-10-01: summary 57.389, hooks 57.960, boundary 58.021), so the transcript does not show
    this compaction yet. When it does not, the event is taken at its word: one boundary more,
    and only the request in progress (cut by the compaction, H1) still live. The next prompt
    reads the boundary from the transcript and finds the same count."""
    store, session = store_for(event), str(event.get("session_id") or "session")
    before, _ = live_at_last_prompt(store, session)
    seen = record(event)
    boundaries, live = seen.boundaries, seen.live
    if boundaries <= before:
        boundaries = before + 1
        live = frozenset({max(seen.live)}) if seen.live else frozenset()
    note_live(store, session, boundaries, live, seen.cwd)
    _log({"event": "SessionStart", "boundaries": boundaries, "live": sorted(live),
          "boundary_in_transcript": seen.boundaries > before})  # fmt: skip
    return {}


# ---- entry -------------------------------------------------------------------------------------


def rules_at_stop(event: Mapping[str, Any], seen: Recorded,
                  start: Mapping[str, Any] | None) -> dict[str, Any]:  # fmt: skip
    """v7 at Stop: new standing rules from the request, then, only with `MEMORY_RULES_AUDIT=on`,
    its diff held against the rules it did not state; a confident break sends the agent back
    once (`memory_rules`). By default no audit question is asked and no Stop is blocked."""
    from . import memory_rules  # not at import: a touch event must stay light

    if not memory_rules.rules_on() or mode() != "decider" or not seen.episodes:
        return {}
    import asyncio

    from .claude_code import squire_from_env

    store, session = store_for(event), str(event.get("session_id") or "session")
    squire = squire_from_env(redact=True)
    audit = memory_rules.audit_on()
    check = audit and bool(start) and start.get("index") == seen.requests \
        and not event.get("stop_hook_active")  # fmt: skip
    request = next((e.request for e in seen.episodes if e.index == seen.requests), "")
    seconds = _int("MEMORY_RULES_SECONDS", 20)
    deadline = time.monotonic() + seconds

    async def checked() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not check or start is None:
            return [], {}
        return await memory_rules.audit(
            squire, store, session, seen.requests, str(start.get("cwd") or ""),
            str(start.get("head") or ""), wrote_by(store, session, seen.requests),
            request=request, note=_log, deadline=deadline)  # fmt: skip

    async def both() -> tuple[Any, Any]:
        extracted = memory_rules.extract_landed(squire, store, session, seen.cwd,
                                                seen.episodes[-3:], note=_log)  # fmt: skip
        return await asyncio.gather(  # side by side, each with its own deadline
            asyncio.wait_for(extracted, seconds),
            asyncio.wait_for(checked(), seconds), return_exceptions=True)  # fmt: skip

    extracted, audited = asyncio.run(both())
    added = extracted if isinstance(extracted, list) else []
    broken, found = audited if isinstance(audited, tuple) else ([], {})
    for part, value in (("extract", extracted), ("audit", audited)):
        if isinstance(value, BaseException):
            _log({"event": "rules", "part": part, "error": f"{value.__class__.__name__}"})
    _log({"event": "rules", "added": added, "checked": found,
          "broken": [r["text"] for r in broken], "audit": "on" if audit else "off"})  # fmt: skip
    return {"decision": "block", "reason": memory_rules.block_reason(broken)} if broken else {}


def wrote_by(store: Path, session: str, index: int) -> list[str]:
    """The files request `index` wrote (`memory_tree.finish_tree`, relative to where its
    session started): the only ones its audit reads."""
    try:
        data = json.loads(memory_tree.tree_path(store, session, index).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [str(x) for x in data.get("changed") or []] if isinstance(data, dict) else []


# ---- the bridge into Claude Code's own auto memory (`memory_native`, opt-in) ------------------


def native_at_stop(event: Mapping[str, Any], seen: Recorded) -> None:
    """Stop and SessionEnd: the session's note in Claude Code's auto memory. Never costs the
    record: an error is logged and Claude Code's folder is left as it was."""
    session = str(event.get("session_id") or "session")
    try:
        folder = memory_native.native_dir(event)
        if folder is None:
            _log({"event": "native", "native": "auto memory off or unknown folder"})
            return
        _log(memory_native.refresh(folder, seen.episodes, session=session,
                                   store=store_for(event)))  # fmt: skip
    except Exception as error:  # noqa: BLE001 - the bridge is extra
        _log({"event": "native", "error": f"{error.__class__.__name__}: {error}"})


def carried_at_start(event: Mapping[str, Any]) -> None:
    """A new session's start: the records our note carries, which Claude Code loads itself,
    count as given to this session (neither the prompt nor the touch gives them again)."""
    store, session = store_for(event), str(event.get("session_id") or "session")
    try:
        keys = memory_native.carried(event, store, session)
        if keys:
            with ep.locked(_shown_path(store, session)):
                remember_shown(store, session, 0, keys)
        _log({"event": "native", "carried": keys})
    except Exception as error:  # noqa: BLE001 - then the records may come again; never worse
        _log({"event": "native", "error": f"{error.__class__.__name__}: {error}"})


def at_session_start(event: Mapping[str, Any]) -> dict[str, Any]:
    """Any SessionStart: the project's standing rules (v7); after a compaction, also what is
    live (`after_compaction`)."""
    from . import memory_rules

    if event.get("source") == "compact":
        with contextlib.suppress(Exception):  # the rules still come if this fails
            after_compaction(event)
    if event.get("source") in ("startup", "clear") and memory_native.native_on():
        carried_at_start(event)
    text = memory_rules.render(store_for(event)) if memory_rules.rules_on() else ""
    _log({"event": "SessionStart", "source": event.get("source"), "rules_chars": len(text)})
    if not text:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def handle(event: Mapping[str, Any]) -> dict[str, Any]:
    name = event.get("hook_event_name")
    if name in ("Stop", "SessionEnd"):
        session = str(event.get("session_id") or "session")
        start = memory_tree.start_of(store_for(event), session) if name == "Stop" else None
        seen = stop(event) if name == "Stop" else record(event)
        if name == "SessionEnd":
            memory_tree.forget_open(store_for(event), session)
        _log({"event": name, "episodes": len(seen.episodes), "written": list(seen.written)})
        if memory_native.native_on():
            native_at_stop(event, seen)
        return rules_at_stop(event, seen, start) if name == "Stop" else {}
    if name == "UserPromptSubmit":
        import asyncio  # a prompt may ask the decider; the touch never does

        return asyncio.run(recall(event))
    if name == "PostToolUse":
        return touch(event)
    if name == "PreToolUse":
        return shell_first(event)
    if name == "SessionStart":
        return at_session_start(event)
    return {}


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        event = json.loads(stdin_text() or "{}")
        if not isinstance(event, Mapping):
            raise ValueError("the event is not a JSON object")
        payload = handle(event)
        if payload:
            stdout_json(payload)
    except Exception as error:  # noqa: BLE001 - fail open, and say so
        with contextlib.suppress(Exception):
            sys.stderr.write(f"{PREFIX}: added nothing ({error.__class__.__name__}: {error})\n")
        _log({"event": "error", "error": f"{error.__class__.__name__}: {error}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
