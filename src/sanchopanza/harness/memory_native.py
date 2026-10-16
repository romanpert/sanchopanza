"""The memory bridge: a session's record written into Claude Code's own auto memory (opt-in).

Claude Code 2.1.287 keeps auto memory per project in `<config>/projects/<slug>/memory/`: one fact
per `*.md` file with a front matter (`name`, `description`, `metadata.type`) and an index,
`MEMORY.md`, one line per memory (`- [Title](file.md) — hook`). At every session start it puts
the index into the first user message, as an attachment of the `instructions` kind headed
"Contents of ...MEMORY.md (user's auto-memory, persists across conversations)", after the system
prompt and with the CLAUDE.md files; a memory file is read only when the model chooses to `Read`
it. So what is in the index rides in the context Claude Code already builds at start (cached with
the rest of that message), at no hook's cost. Verified (2026-10-16) in:

- the pinned binary's JS: `MEMORY.md`, 200 lines and 25,000 characters loaded (`_hn`: the rest
  is cut with a warning); the folder `projects/<Vx(root)>/memory/` under
  `CLAUDE_CODE_REMOTE_MEMORY_DIR` or the config folder, where `Vx` turns every non-alphanumeric
  character into "-" (past 200 characters it appends a hash), and `root` is the canonical git
  root of the project root (a worktree's is the main checkout's); `autoMemoryDirectory`
  (settings) and `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` replace the folder;
  `autoMemoryEnabled: false` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY` turn it off;
- F2's transcripts (`docs/results/2026-10-16-memory-f2`): the index arrives as above, the
  `init` event names the same folder, and Sonnet 5.5 read the memory file the index pointed to
  in every session 2 that had one (4 of 4 in N0, kept all in all 4).

What this module does, at a memory `Stop` when `SANCHOPANZA_MEMORY_NATIVE=1`
(`sanchopanza install --memory-native`):

- **One note of ours.** `sanchopanza-next.md` holds the session's last records (the person's
  requests and the agent's final reports, verbatim and masked by `redact.mask_strict`, bounded to
  FILE_CHARS), and the index gets exactly one line pointing to it. Nothing else in the folder is
  touched: no line of the index but ours is changed, moved or removed, and no file but ours is
  written or deleted. Idempotent; atomic writes; the index is left alone when it is full (our line
  would land past what Claude Code loads), and so is the note.
- **Only a session that changed files** refreshes the note: a question-only session leaves the
  last plan where it is.
- **Claude Code first.** When Claude Code saved a memory of its own during this session that
  restates at least COVER_SHARE of the session's request words, the plan is carried natively; our
  note is not written, and an older note of ours is taken out (it would be stale).
- **Less injected.** The keys of the records native memory carries (in our note, or in Claude
  Code's own memory of the plan) are kept with each carrying file's digest (`native.json` in the
  store). At the next session's start, while every such file is unchanged and its index line is
  within what Claude Code loads, those records count as already given to that session: neither
  the prompt recall nor the file touch injects them again (`memory_hook.carried_at_start`).

The index and the SessionStart text both land in the first user message, which Claude Code
writes to the cache afresh every session: moving text from a hook into native memory saves no
cache cost by itself. What saves is not giving twice what native memory already holds. What the
bridge adds is that the plan reaches the next session through Claude Code's own mechanism: any
harness that reads it gets it, it survives sanchopanza being off, and it composes with the
memory Claude Code saves itself (Opus 5.5 did after every F2 session 1).

Fails open: any error writes one log line and leaves Claude Code's folder as it was.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env
from ..context import episodes as ep
from ..redact import mask_strict
from ..text import truncate
from . import memory_store

NOTE = "sanchopanza-next.md"
OWN_PREFIX = "sanchopanza-"
INDEX = "MEMORY.md"
INDEX_LINES = 200  # Claude Code 2.1.287 loads the index's first 200 lines ...
INDEX_BYTES = 25_000  # ... and at most 25,000 characters of them
SLUG_MAX = 200  # past this Claude Code appends a hash we do not reproduce
LINE_CHARS = 150  # Claude Code asks for index lines "under ~150 characters"
FILE_CHARS = 2_600
RECORDS = 3  # the session's last records in the note
REQUEST_CHARS = 1_000  # shared by the records in the note
REPORT_CHARS = 600
COVER_SHARE = 0.5
COVER_SLACK_S = 5.0
COVER_READ = 20_000
STATE = "native.json"
TITLE = "Where the last session left off"
DESCRIPTION = ("Where the last session in this project left off (the person's requests, the "
               "agent's final reports, files changed), recorded by sanchopanza")  # fmt: skip
_WORD = re.compile(r"[a-z][a-z0-9_]{4,}")
_SPACE = re.compile(r"\s+")


def native_on() -> bool:
    return str(_env.get("MEMORY_NATIVE", "") or "").strip().lower() in ("1", "on", "true", "yes")


def project_key(path: str) -> str:
    """Claude Code's folder name for a project path (`Vx` without its hash)."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def config_dir(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> Path:
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
    return Path.home() / ".claude"


def _settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _setting(config: Path, cwd: str, key: str, scopes: Sequence[str]) -> Any:
    """The first scope that sets `key` (local, project, user: Claude Code's order)."""
    paths = {"user": config / "settings.json"}
    if cwd:
        paths = {**paths, "local": Path(cwd) / ".claude" / "settings.local.json",
                 "project": Path(cwd) / ".claude" / "settings.json"}  # fmt: skip
    for scope in scopes:
        if scope in paths:
            value = _settings(paths[scope]).get(key)
            if value is not None:
                return value
    return None


def slug_of(event: Mapping[str, Any]) -> str:
    """The canonical git root's folder name (the main checkout's, as `memory_store` names a
    store), else the working directory's."""
    cwd, session = str(event.get("cwd") or ""), str(event.get("session_id") or "")
    if memory_store.key_mode() == "repo" and session and cwd:
        root = memory_store.store_root()
        data = memory_store.session_key(root, session)
        if data is None:
            memory_store.store_for(event)
            data = memory_store.session_key(root, session)
        if data and data.get("name"):
            return str(data["name"])
    if cwd and Path(cwd).is_dir():
        repo = memory_store.git_repo(cwd)
        if repo is not None:
            return memory_store.repo_name(repo)
    return project_key(cwd) if cwd else ""


def native_dir(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> Path | None:
    """Claude Code's auto-memory folder for the session that sent `event`, or None when auto
    memory is off or the folder cannot be known."""
    env = os.environ if env is None else env
    if _truthy(env.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY")):
        return None
    config, cwd = config_dir(event, env), str(event.get("cwd") or "")
    if _setting(config, cwd, "autoMemoryEnabled", ("local", "project", "user")) is False:
        return None
    override = str(env.get("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE") or "").strip() or \
        _setting(config, cwd, "autoMemoryDirectory", ("local", "user"))  # fmt: skip
    if isinstance(override, str) and override.strip():
        return Path(override.strip()).expanduser()
    slug = slug_of(event)
    if not slug or len(slug) > SLUG_MAX:
        return None
    base = str(env.get("CLAUDE_CODE_REMOTE_MEMORY_DIR") or "").strip()
    return (Path(base) if base else config) / "projects" / slug / "memory"


# ---- the note ----------------------------------------------------------------------------------


def _flat(text: str) -> str:
    return _SPACE.sub(" ", mask_strict(text)).strip()


def compose(records: Sequence[ep.Episode]) -> tuple[str, str]:
    """(the note's text, its index line) for the session's last records, oldest first."""
    chosen = list(records)[-RECORDS:]
    latest = chosen[-1]
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(latest.at)) if latest.at else "?"
    share = len(chosen)
    parts = [f"---\nname: {NOTE[:-3]}\ndescription: {DESCRIPTION}\nmetadata:\n  type: project\n---",
             f"Recorded by sanchopanza from the transcript of session {latest.session[:8]} "
             f"({when}), not written by the agent: the person's requests and the agent's final "
             "reports, verbatim. If the person asks to continue, this is the work in progress; "
             "check the repository before relying on it."]  # fmt: skip
    for record in chosen:
        request = truncate(mask_strict(record.request).strip(), max(250, REQUEST_CHARS // share))
        report = truncate(mask_strict(record.report).strip(), max(160, REPORT_CHARS // share))
        block = [f"## Request {record.index} (the person's words)\n{request}"]
        if report:
            block.append(f"## Outcome (the agent's final report)\n{report}")
        if record.changed:
            block.append(truncate("Changed: " + ", ".join(record.changed), 300))
        parts.append("\n\n".join(block))
    text = "\n\n".join(parts) + "\n"
    if len(text) > FILE_CHARS:
        text = text[: FILE_CHARS - 7] + " [...]\n"
    planned = next((r for r in reversed(chosen) if r.changed), latest)
    head = f"- [{TITLE}]({NOTE}) — read before continuing: "
    hook = _flat(planned.request)
    room = LINE_CHARS - len(head) - 2
    hook = hook if len(hook) <= room else hook[: room - 3].rstrip() + "..."
    return text, f'{head}"{hook}"'


# ---- the index ---------------------------------------------------------------------------------


def _ours(line: str) -> bool:
    return f"]({NOTE})" in line


def _loaded(text: str) -> str:
    """What Claude Code loads of an index (`_hn`): 200 lines, then 25,000 characters."""
    kept = "\n".join(text.strip().split("\n")[:INDEX_LINES])
    if len(kept) > INDEX_BYTES:
        cut = kept.rfind("\n", 0, INDEX_BYTES)
        kept = kept[: cut if cut > 0 else INDEX_BYTES]
    return kept


def index_with(text: str, line: str) -> str | None:
    """The index with our one line (replacing ours in place, else appended), or None when it
    would land past what Claude Code loads."""
    lines = text.splitlines(keepends=True)
    mine = [i for i, n in enumerate(lines) if _ours(n)]
    if mine:
        first = mine[0]
        ending = lines[first][len(lines[first].rstrip("\r\n")) :]
        kept = [n for i, n in enumerate(lines) if i not in mine[1:]]
        new = "".join([*kept[:first], line + ending, *kept[first + 1 :]])
    else:
        new = (text if not text or text.endswith("\n") else text + "\n") + line + "\n"
    return new if any(_ours(n) for n in _loaded(new).split("\n")) else None


def index_without(text: str) -> str:
    return "".join(n for n in text.splitlines(keepends=True) if not _ours(n))


# ---- files -------------------------------------------------------------------------------------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_index(path: Path) -> str | None:
    """The index as written, "" when absent, None when it is not UTF-8 (never rewritten)."""
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError):
        return None


def _atomic(path: Path, text: str, tries: int = 25) -> None:
    """Write through a temporary file beside `path`; again while Windows says it is busy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".sanchopanza-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        for attempt in range(tries):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == tries - 1:
                    raise
                time.sleep(0.01)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _state(store: Path) -> dict[str, Any]:
    try:
        data = json.loads((store / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def covering(folder: Path, records: Sequence[ep.Episode], since: float) -> list[str]:
    """Claude Code's own memory files written since `since` that restate at least COVER_SHARE
    of the records' request words (words of five letters or more)."""
    words = set(_WORD.findall(" ".join(r.request for r in records).lower()))
    if not words or not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.md")):
        if path.name == INDEX or path.name.startswith(OWN_PREFIX):
            continue
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < since:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")[:COVER_READ].lower()
            if len(words & set(_WORD.findall(text))) / len(words) >= COVER_SHARE:
                found.append(path.name)
    return found


def _drop(folder: Path, index: str) -> bool:
    """Our note and our index line out (the line first); True when anything was removed."""
    removed = False
    without = index_without(index)
    if without != index:
        _atomic(folder / INDEX, without)
        removed = True
    if (folder / NOTE).exists():
        (folder / NOTE).unlink()
        removed = True
    return removed


def refresh(folder: Path, records: Sequence[ep.Episode], *, session: str,
            store: Path) -> dict[str, Any]:  # fmt: skip
    """Write or refresh our note and its index line for `session`'s records; the log row."""
    row: dict[str, Any] = {"event": "native", "dir": str(folder)}
    records = [r for r in records if r.session == session]
    if not any(r.changed for r in records):
        return {**row, "native": "no change"}
    since = min((r.at for r in records if r.at), default=time.time()) - COVER_SLACK_S
    keys = [r.key for r in records[-RECORDS:]]
    with ep.locked(store / STATE):
        index = _read_index(folder / INDEX)
        if index is None:
            return {**row, "native": "index unreadable"}
        covered = covering(folder, records, since)
        if covered:
            removed = _drop(folder, index)
            files = {n: _digest(_read(folder / n)) for n in covered}
            state = {"session": session, "keys": keys, "carrier": "claude-code",
                     "dir": str(folder), "files": files, "at": time.time()}  # fmt: skip
            ep.write_private(store / STATE, json.dumps(state))
            return {**row, "native": "covered", "covered_by": covered, "removed": removed,
                    "keys": keys}  # fmt: skip
        text, line = compose(records)
        new_index = index_with(index, line)
        if new_index is None:
            return {**row, "native": "index full"}
        written = False
        if _read(folder / NOTE) != text:  # the note first: the line never points at nothing
            _atomic(folder / NOTE, text)
            written = True
        if new_index != index:
            _atomic(folder / INDEX, new_index)
            written = True
        ep.write_private(store / STATE, json.dumps({
            "session": session, "keys": keys, "carrier": "sanchopanza", "dir": str(folder),
            "files": {NOTE: _digest(text)}, "at": time.time()}))  # fmt: skip
    return {**row, "native": "written" if written else "unchanged", "keys": keys,
            "chars": len(text), "line_chars": len(line)}  # fmt: skip


def carried(event: Mapping[str, Any], store: Path, session: str) -> list[str]:
    """The record keys native memory carries into `session`: another session's Stop found them
    in our note or in Claude Code's own memory of the plan, every such file is unchanged since,
    and Claude Code loads its index line. Else none."""
    state = _state(store)
    files = state.get("files")
    if state.get("session") in (None, session) or not isinstance(files, dict) or not files:
        return []
    folder = native_dir(event)
    if folder is None or os.path.normcase(str(folder)) != os.path.normcase(str(state.get("dir"))):
        return []
    loaded = _loaded(_read_index(folder / INDEX) or "")
    for name, digest in files.items():
        text = _read(folder / str(name))
        if not text or _digest(text) != digest or f"]({name})" not in loaded:
            return []
    return [str(k) for k in state.get("keys") or []]
