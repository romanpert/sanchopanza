"""The memory bridge: a session's records written into Claude Code's own auto memory (opt-in).

Claude Code 2.1.287 keeps auto memory per project in `<config>/projects/<slug>/memory/`: one fact
per `*.md` file with a front matter (`name`, `description`, `metadata.type`) and an index,
`MEMORY.md`, one line per memory (`- [Title](file.md) — hook`). At every session start it puts
the index into the first user message, as an attachment of the `instructions` kind headed
"Contents of ...MEMORY.md (user's auto-memory, persists across conversations)", with the
CLAUDE.md files; a memory file reaches the model only when the model chooses to `Read` it.
Verified (2026-10-16) in:

- the pinned binary's JS: `MEMORY.md`, 200 lines and 25,000 UTF-16 units loaded (`_hn`); the
  folder `projects/<Vx(root)>/memory/` under `CLAUDE_CODE_REMOTE_MEMORY_DIR` or the config folder,
  where `Vx` turns every non-alphanumeric character into "-" (past 200 characters it appends a
  hash) and `root` is the canonical git root of the project root (a worktree's is the main
  checkout's); `autoMemoryDirectory` (settings) and `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` move
  the folder; `autoMemoryEnabled: false` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY` turn it off;
- F2's transcripts (`docs/results/2026-10-16-memory-f2`): the index arrives as above, the `init`
  event names the same folder (72 of 72 arms), and Sonnet 5.5 read the memory file the index
  pointed to in every session 2 that had one (4 of 4 in N0, kept all in all 4).

The index and the hooks' SessionStart text both land in the first user message, which Claude Code
writes to the cache afresh every session: moving text from a hook into native memory saves no
cache cost by itself. What the bridge adds is that the plan reaches the next session through
Claude Code's own mechanism: any harness that reads it gets it, it survives sanchopanza being
off, and it composes with the memory Claude Code saves itself.

At a memory `Stop` with `SANCHOPANZA_MEMORY_NATIVE=1` (`sanchopanza install --memory-native`):

- **One note and one line of ours** (`memory_native_index`): `sanchopanza-next.md`, marked as
  ours in its front matter, holds the session's last records, newest first in the budget (the
  person's requests and the agent's final reports, verbatim, masked by `redact.mask_strict`,
  within FILE_CHARS), and the index gets our one exact line. Nothing else is ever changed.
- **Off** wherever Claude Code's memory is elsewhere or off: an `autoMemoryDirectory` or the
  cowork override in effect, `autoMemoryEnabled: false` at any scope read from the project root,
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY`, `CLAUDE_CODE_SIMPLE`, `CLAUDE_CODE_SAFE_MODE`, or
  `CLAUDE_CODE_REMOTE` without `CLAUDE_CODE_REMOTE_MEMORY_DIR`.
- **Only a session that changed files** refreshes the note.
- **Claude Code first.** When this session wrote a memory of its own (its transcript shows the
  write, or the memory names a file the session changed) that restates at least COVER_SHARE of
  the session's request words, our note is not written and an older one of ours is taken out.
- **Given again unless read.** The records still come at the next session's prompt and touch as
  without the bridge. Only after that session `Read` our unchanged note do the records it holds
  whole count as given (`keys_after_read`), so a later touch does not repeat them.

Fails open: any error writes one log line and leaves Claude Code's folder as it was.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env
from ..context import episodes as ep
from ..redact import mask_strict
from ..text import truncate
from . import memory_native_index as mni
from . import memory_store

NOTE, INDEX = mni.NOTE, mni.INDEX
OWN_PREFIX = "sanchopanza-"
SLUG_MAX = 200  # past this Claude Code appends a hash we do not reproduce
LINE_CHARS = 150  # Claude Code asks for index lines "under ~150 characters"
FILE_CHARS = 3_200  # room for one stored record whole (episodes caps 1,000 + 1,200)
RECORDS = 3
REQUEST_CHARS = 1_100
REPORT_CHARS = 1_300
COVER_SHARE = 0.5
COVER_SLACK_S = 5.0
COVER_READ = 20_000
STATE = "native.json"
DESCRIPTION = ("Where the last session in this project left off (the person's requests, the "
               "agent's final reports, files changed), recorded by sanchopanza")  # fmt: skip
OFF_ENV = ("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "CLAUDE_CODE_SIMPLE", "CLAUDE_CODE_SAFE_MODE")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_WORD = re.compile(r"[a-z][a-z0-9_]{4,}")
_SPACE = re.compile(r"\s+")
_MD = re.compile(r"[\w.-]+\.md\b")


def native_on() -> bool:
    return str(_env.get("MEMORY_NATIVE", "") or "").strip().lower() in ("1", "on", "true", "yes")


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def config_dir(event: Mapping[str, Any], env: Mapping[str, str] | None = None,
               home: Path | None = None) -> Path:  # fmt: skip
    """`CLAUDE_CONFIG_DIR`, else the folder above the transcript's `projects/`, else ~/.claude."""
    env = os.environ if env is None else env
    named = str(env.get("CLAUDE_CONFIG_DIR") or "").strip()
    if named:
        return Path(named).expanduser()
    transcript = str(event.get("transcript_path") or "")
    if transcript:
        project = Path(transcript).parent
        if project.parent.name.casefold() == "projects":
            return project.parent.parent
    return (home if home is not None else Path.home()) / ".claude"


def _settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _repo_facts(event: Mapping[str, Any]) -> tuple[str, str]:
    """(slug, project root): the canonical git root's folder name and this checkout's top, from
    the session's store key when it exists, else one git call, else the working directory."""
    from .memory_gate import project_key  # not at import: the touch stays light

    cwd, session = str(event.get("cwd") or ""), str(event.get("session_id") or "")
    if memory_store.key_mode() == "repo" and session:
        data = memory_store.session_key(memory_store.store_root(), session)
        if data and data.get("name"):
            return str(data["name"]), str(data.get("top") or cwd)
    if cwd and Path(cwd).is_dir():
        repo = memory_store.git_repo(cwd)
        if repo is not None:
            return memory_store.repo_name(repo), repo.top
    return (project_key(cwd) if cwd else ""), cwd


def _scopes(config: Path, root: str) -> list[dict[str, Any]]:
    """The settings Claude Code reads for auto memory that we can read: local, project, user."""
    paths = [config / "settings.json"]
    if root:
        paths = [Path(root) / ".claude" / "settings.local.json",
                 Path(root) / ".claude" / "settings.json", *paths]  # fmt: skip
    return [_settings(p) for p in paths]


def auto_memory_dir(event: Mapping[str, Any], env: Mapping[str, str] | None = None,
                    home: Path | None = None,
                    facts: tuple[str, str] | None = None) -> Path | None:  # fmt: skip
    """Where Claude Code keeps this session's auto memory (to read it), or None when it is off
    or the folder cannot be known."""
    env = os.environ if env is None else env
    if _truthy(env.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY")):
        return None
    config = config_dir(event, env, home)
    slug, root = facts or _repo_facts(event)
    scopes = _scopes(config, root)
    if any(s.get("autoMemoryEnabled") is False for s in scopes):
        return None
    override = str(env.get("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE") or "").strip() or next(
        (str(s["autoMemoryDirectory"]) for s in scopes if s.get("autoMemoryDirectory")), ""
    )
    if override.strip():
        return Path(override.strip()).expanduser()
    if not slug or len(slug) > SLUG_MAX:
        return None
    base = str(env.get("CLAUDE_CODE_REMOTE_MEMORY_DIR") or "").strip()
    return (Path(base) if base else config) / "projects" / slug / "memory"


def native_dir(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> Path | None:
    """The folder the bridge writes in, or None wherever it stays off (see the module's doc)."""
    env = os.environ if env is None else env
    if any(_truthy(env.get(name)) for name in OFF_ENV):
        return None
    if str(env.get("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE") or "").strip():
        return None
    if _truthy(env.get("CLAUDE_CODE_REMOTE")) and not env.get("CLAUDE_CODE_REMOTE_MEMORY_DIR"):
        return None
    facts = _repo_facts(event)
    _slug, root = facts
    if any(s.get("autoMemoryDirectory") for s in _scopes(config_dir(event, env), root)):
        return None
    return auto_memory_dir(event, env, facts=facts)


# ---- the note ----------------------------------------------------------------------------------


def _block(record: ep.Episode) -> tuple[str, bool]:
    """One record's part of the note, and whether its request and report are in it whole."""
    request, report = mask_strict(record.request).strip(), mask_strict(record.report).strip()
    whole = len(request) <= REQUEST_CHARS and len(report) <= REPORT_CHARS
    parts = [f"## Request {record.index} (the person's words)\n{truncate(request, REQUEST_CHARS)}"]
    if report:
        parts.append(f"## Outcome (the agent's final report)\n{truncate(report, REPORT_CHARS)}")
    if record.changed:
        parts.append(truncate(mask_strict("Changed: " + ", ".join(record.changed)), 300))
    return "\n\n".join(parts), whole


def _line(record: ep.Episode) -> str:
    hook = _SPACE.sub(" ", mask_strict(record.request)).strip().replace('"', "'")
    room = LINE_CHARS - len(mni.LINE_HEAD) - 2
    hook = hook if len(hook) <= room else hook[: room - 3].rstrip() + "..."
    return f'{mni.LINE_HEAD}"{hook}"'


def compose(records: Sequence[ep.Episode]) -> tuple[str, str, list[str]]:
    """(the note's text, its index line, the keys of the records it holds whole). The newest
    record first in the budget; older ones are dropped whole when they do not fit."""
    chosen = list(records)[-RECORDS:]
    latest = chosen[-1]
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(latest.at)) if latest.at else "?"
    head = (f"{mni.NOTE_HEAD}description: {DESCRIPTION}\nmetadata:\n  type: project\n"
            f"{mni.OWNER}\n---\n\nRecorded by sanchopanza from the transcript of session "
            f"{mask_strict(latest.session[:8])} ({when}), not written by the agent: the person's "
            "requests and the agent's final reports, verbatim. If the person asks to continue, "
            "this is the work in progress; check the repository before relying on it.")  # fmt: skip
    room = FILE_CHARS - len(head) - 3
    kept: list[tuple[str, str, bool]] = []
    for record in reversed(chosen):
        block, whole = _block(record)
        if len(block) + 2 > room:
            if kept:
                break
            block, whole = block[: max(0, room - 8)] + " [...]", False
        kept.insert(0, (record.key, block, whole))
        room -= len(block) + 2
    text = "\n\n".join([head, *(b for _, b, _ in kept)]) + "\n"
    planned = next((r for r in reversed(chosen) if r.changed), latest)
    return text, _line(planned), [k for k, _, whole in kept if whole]


# ---- Claude Code's own memory of the plan ------------------------------------------------------


def _folded(path: str) -> str:
    clean = path.replace("\\", "/").rstrip("/")
    return clean.casefold() if os.name == "nt" or clean[1:3] == ":/" else clean


def memory_writes(entries: Iterable[Mapping[str, Any]], folder: Path) -> set[str]:
    """Names of the files in `folder` this transcript's tool calls wrote: a file tool's path in
    it, or a shell command that names the folder (a Git Bash `/c/...` form too) and a `.md`."""
    target = _folded(str(folder))
    forms = {target}
    if len(target) > 2 and target[1] == ":":
        forms.add(f"/{target[0]}{target[2:]}")
    found: set[str] = set()
    for entry in entries:
        content = (entry.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            data = block.get("input") if isinstance(block.get("input"), Mapping) else {}
            raw = str(data.get("file_path") or data.get("notebook_path") or "")
            if block.get("name") in WRITE_TOOLS and raw:
                if _folded(str(Path(raw).parent)) == target:
                    found.add(Path(raw).name)
                continue
            command = _folded(str(data.get("command") or ""))
            if command and any(form in command for form in forms):
                found |= {m for m in _MD.findall(command) if m not in (INDEX.casefold(), NOTE)}
    return {n for n in found if n not in (INDEX, NOTE)}


def covering(folder: Path, records: Sequence[ep.Episode], since: float,
             written: frozenset[str] = frozenset()) -> list[str]:  # fmt: skip
    """Claude Code's memory files written since `since` that restate at least COVER_SHARE of the
    records' request words and that this session wrote or that name a file it changed."""
    words = set(_WORD.findall(" ".join(r.request for r in records).lower()))
    names = {Path(str(p)).name.casefold() for r in records for p in r.changed_raw or r.changed}
    if not words or not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.md")):
        if path.name == INDEX or path.name.startswith(OWN_PREFIX) or path.is_symlink():
            continue
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < since:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")[:COVER_READ].lower()
            restates = len(words & set(_WORD.findall(text))) / len(words) >= COVER_SHARE
            ours = path.name.casefold() in {w.casefold() for w in written}
            if restates and (ours or any(n in text for n in names)):
                found.append(path.name)
    return found


# ---- refresh -----------------------------------------------------------------------------------


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _state(store: Path) -> dict[str, Any]:
    try:
        data = json.loads((store / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def refresh(folder: Path, records: Sequence[ep.Episode], *, session: str, store: Path,
            written: frozenset[str] = frozenset()) -> dict[str, Any]:  # fmt: skip
    """Write or refresh our note and its index line for `session`'s records; the log row."""
    row: dict[str, Any] = {"event": "native", "dir": str(folder)}
    records = [r for r in records if r.session == session]
    if not any(r.changed for r in records):
        return {**row, "native": "no change"}
    note, index = folder / NOTE, folder / INDEX
    if any(mni.linked(p) for p in (folder, index, note)):
        return {**row, "native": "link refused"}
    if folder.is_dir():
        mni.clean_temps(folder)
    before = mni.read_text(note)
    if before is None or (before and not mni.is_owned_note(before)):
        return {**row, "native": "name taken"}
    since = min((r.at for r in records if r.at), default=time.time()) - COVER_SLACK_S
    covered = covering(folder, records, since, written)
    with ep.locked(store / STATE):
        if covered:
            status = mni.swap_index(index, mni.index_without) if index.exists() else "unchanged"
            if before:
                note.unlink()
            state = {"session": session, "keys": [], "carrier": "claude-code",
                     "files": covered, "at": time.time()}  # fmt: skip
            ep.write_private(store / STATE, json.dumps(state))
            return {**row, "native": "covered", "covered_by": covered, "index": status}
        text, line, keys = compose(records)
        current = mni.read_text(index)
        if current is None:
            return {**row, "native": "index unreadable"}
        if mni.index_with(current, line) is None:
            return {**row, "native": "index full"}
        if before != text:  # the note first: the line never points at nothing
            mni.write(note, text)
        status = mni.swap_index(index, lambda t: mni.index_with(t, line))
        if status in ("busy", "full", "unreadable"):
            if not before:
                note.unlink(missing_ok=True)
            return {**row, "native": f"index {status}"}
        ep.write_private(store / STATE, json.dumps({
            "session": session, "keys": keys, "carrier": "sanchopanza", "dir": str(folder),
            "files": {NOTE: _digest(text)}, "at": time.time()}))  # fmt: skip
    changed = before != text or status == "written"
    return {**row, "native": "written" if changed else "unchanged", "keys": keys,
            "chars": len(text), "line_chars": len(line)}  # fmt: skip


def keys_after_read(event: Mapping[str, Any], store: Path, session: str) -> list[str]:
    """The records another session's note holds whole, when this event is `session` reading
    that note, unchanged since it was written. Else none."""
    if event.get("tool_name") != "Read":
        return []
    data = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    state = _state(store)
    if state.get("carrier") != "sanchopanza" or state.get("session") in (None, session):
        return []
    folder = native_dir(event)
    if folder is None or _folded(str(folder)) != _folded(str(state.get("dir") or "")):
        return []
    if _folded(os.path.abspath(str(data.get("file_path") or ""))) != _folded(str(folder / NOTE)):
        return []
    text = mni.read_text(folder / NOTE)
    files = state.get("files") if isinstance(state.get("files"), dict) else {}
    if not text or not mni.is_owned_note(text) or _digest(text) != files.get(NOTE):
        return []
    return [str(k) for k in state.get("keys") or []]


# ---- going off ---------------------------------------------------------------------------------


def install_config(settings_path: Path, project: bool) -> Path:
    """The Claude Code configuration folder an install at `settings_path` serves."""
    if not project:
        return settings_path.parent
    named = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return Path(named).expanduser() if named else Path.home() / ".claude"


def uninstall(config: Path) -> list[str]:
    """Our marked notes and our exact index lines out of every project's auto memory under
    `config`; what was removed. Nothing else is touched."""
    removed: list[str] = []
    for folder in sorted((config / "projects").glob("*/memory")):
        note, index = folder / NOTE, folder / INDEX
        if any(mni.linked(p) for p in (folder, note, index)):
            continue
        text = mni.read_text(index)
        mine = bool(text) and any(mni.is_ours(n) for n in (text or "").split("\n"))
        if mine and mni.swap_index(index, mni.index_without) == "written":
            removed.append(f"{index}: our line")
        body = mni.read_text(note)
        if body and mni.is_owned_note(body):
            with contextlib.suppress(OSError):
                note.unlink()
                removed.append(str(note))
    return removed
