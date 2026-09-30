"""Episodes: what each request of a Claude Code session did, recorded verbatim, no model.

The compaction guard (`context.guard`) carries what a summary drops *within* a session. This
module keeps the same kind of record *across* requests and sessions: when a request ends, what
the person asked, what the agent said it did (its final text, verbatim), the files it changed
and read, its last test run, and the lines of one-shot command output the guard's rule would
keep. A later request, in this session after a compaction or in a new session, is given back
the records that bear on it (`harness.memory_hook`).

Why records and not a summary: Claude Code's own summary beat every replacement we built, and
what it lost was always verbatim (docs/results/2026-09-28-context-e2e, -2026-09-29-context-guard).
A record is built by code from the transcript, so it can only say what happened.

Why each record carries a short `page`: the decider judged memories on 900 characters, and on
LongMemEval it lost recall exactly where the evidence was outside what it read (75 % of gold
turns visible, recall 0.73 against BM25's 0.85; docs/results/2026-09-28-memory-gate). A page
is written to hold the request and the outcome whole, so what decides relevance is always seen.

What is live: a request any of whose messages comes after the session's last compaction is still
in the conversation (an automatic compaction always falls in the middle of a request, and the
agent carries on after it), and so is every request of a session never compacted. Only the
others are offered back to the same session. A prompt Claude Code writes again after a boundary
(same `promptId`) is the same request, not a new one.

Pure functions over Claude Code transcript entries; storage is plain JSON files, written
atomically and readable by this user only.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..redact import mask
from ..text import truncate
from . import guard as guard_mod
from .archive import safe_name
from .transcript import _is_boundary, blocks_of, calls, merge_consecutive, message_text

REQUEST_CHARS = 1_000
REPORT_CHARS = 1_200
FACTS_CHARS = 800
PATHS_CHARS = 400  # each of the changed and read lists, in the injected text
PAGE_CHARS = 880  # under `chunks.PAGE_LIMIT` (900): the decider reads the page whole
FILES_MAX = 12
LOAD_LIMIT = 300  # newest records looked at per project
KEEP_DAYS = 30  # records older than this are removed when a project's records are saved
# key -> {"changed", "at"} of every record in a project's folder: the touch reads this one file
# (300 record files took 0.75-3.2 s to load cold on Windows, 2026-10-01).
INDEX = "index.json"
# v4: a record keeps, per file, prints of the lines its request wrote (16+ characters, the last
# WROTE_MAX per file), never shown, so that a later Read or Edit can say whose code it is at.
LINE_MIN = 16
WROTE_MAX = 200
COMMON = re.compile(r"^(import |from \S+ import |#include|using |require\(|package |@\w|"
                    r"export \* from|const \w+ = require\()")  # fmt: skip
_WORDS = re.compile(r"\w+")

# How `guard.trail_of` names its lines.
CHANGED = "changed: "
TESTED = "last test run: "
# Text a hook of ours adds, and messages the harness writes in the person's place.
# Not the person's request: our notes, a background task's notification, and Claude Code's mark of
# an interrupted request (recorded as a request in SWE-chat and scored 0.90 against an unrelated
# record, 2026-10-01).
NOT_ASKED = (guard_mod.HEADER, "[sanchopanza memory", "<task-notification>",
             "[Request interrupted by user")
UNFINISHED = "(the request ended before the agent finished; its last text follows) "
_TAGS = re.compile(r"</?[\w-]+>")
_FENCE = re.compile(r"^(<<<|>>>)", re.M)


def _fenced(label: str, body: str) -> str:
    """`body` between fences it cannot close: a line of its own starting `<<<` or `>>>` (a
    Python prompt, a forged fence) is shifted by one space."""
    safe = _FENCE.sub(r" \1", body)
    return f"<<<{label}\n{safe}\n>>>"


def _paths(label: str, paths: Sequence[str]) -> str:
    return truncate(f"{label}: " + ", ".join(paths), PATHS_CHARS)


@dataclass(frozen=True, slots=True)
class Episode:
    """One request of one session, as it ended."""

    session: str
    index: int  # the request's number in its session, from 1
    request: str
    report: str
    changed: tuple[str, ...] = ()
    read: tuple[str, ...] = ()
    tests: str = ""
    facts: tuple[str, ...] = ()
    tool_calls: int = 0
    at: float = 0.0
    # The changed paths before secret masking, for the index only (never shown): the mask's
    # `sk-...` rule rewrites folder names such as `task-management-service` (review, 2026-10-01).
    changed_raw: tuple[str, ...] = ()
    # Per file, prints of the lines this request wrote (`line_print`); None before v4.
    wrote: tuple[tuple[str, tuple[str, ...]], ...] | None = None

    @property
    def key(self) -> str:
        return f"{self.session}-{self.index:03d}"

    @property
    def title(self) -> str:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.at)) if self.at else "?"
        return f"request {self.index} of session {self.session[:8]} ({when})"

    def page(self) -> str:
        """What the decider reads: the request and the outcome, whole, under `PAGE_CHARS`."""
        files = ", ".join(self.changed[:6]) or "none"
        head = f"Changed: {files}\nRequest: "
        room = PAGE_CHARS - len(head) - len("\nOutcome: ")
        request = truncate(self.request, max(80, room // 2 - 6))
        report = truncate(self.report, max(80, room - len(request) - 6))
        return f"{head}{request}\nOutcome: {report}"[:PAGE_CHARS]

    def prints_for(self, path: str) -> set[str]:
        """Prints of the lines this request wrote in `path` (empty before v4 or elsewhere)."""
        return {p for rel, prints in self.wrote or () if same_path(rel, path) for p in prints}

    def search(self) -> str:
        """What BM25 scores: everything, file paths included."""
        return " ".join([self.request, self.report, *self.changed, *self.read, *self.facts])

    def text(self) -> str:
        """What is injected: the whole record, each section bounded before it is fenced."""
        parts = [f"### Earlier {self.title}", _fenced("request", self.request)]
        if self.changed:
            parts.append(_paths("Changed", self.changed))
        if self.read:
            parts.append(_paths("Read", self.read))
        if self.tests:
            parts.append(f"Last test run: {self.tests}")
        if self.report:
            parts.append("The agent's final report, verbatim:\n" + _fenced("report", self.report))
        if self.facts:
            output = _fenced("output", "\n".join(self.facts))
            parts.append(f"Command output recorded then:\n{output}")
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Episode:
        tuples = ("changed", "read", "facts", "changed_raw")
        data = {**data, "wrote": _prints_from(data.get("wrote"))}
        fields = {k: (tuple(v) if k in tuples else v) for k, v in data.items()
                  if k in cls.__dataclass_fields__}  # fmt: skip
        return cls(**fields)


# ---- from a transcript --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Split:
    """A session's conversational entries grouped by request, oldest first."""

    groups: tuple[tuple[Mapping[str, Any], ...], ...]  # each opens with the person's prompt
    stamps: tuple[float, ...]  # when each request was made (0.0 when the transcript does not say)
    live: frozenset[int]  # requests (numbered from 1) still in the conversation


def entries_of(path: Path | str) -> list[Mapping[str, Any]]:
    """The JSONL entries, split on "\\n" only: `str.splitlines` also splits on U+2028, which
    Node's JSON writer leaves unescaped inside strings, and silently drops the entry."""
    out: list[Mapping[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").split("\n"):
        try:
            entry = json.loads(line)
        except ValueError:
            continue  # a line cut by a crash is not a reason to lose the session
        if isinstance(entry, Mapping):
            out.append(entry)
    return out


def _conversational(entry: Mapping[str, Any]) -> bool:
    if entry.get("type") not in ("user", "assistant") or entry.get("isSidechain"):
        return False
    if entry.get("isMeta") or entry.get("isCompactSummary") or entry.get("isApiErrorMessage"):
        return False
    message = entry.get("message")
    if not isinstance(message, Mapping) or message.get("role") not in ("user", "assistant"):
        return False
    return message.get("model") != "<synthetic>"  # "No response requested.", limit notices


def is_request(message: Mapping[str, Any]) -> bool:
    """A message the person wrote: text or an image, no tool result, and not ours."""
    if message.get("role") != "user":
        return False
    blocks = blocks_of(message)
    kinds = {b.get("type") for b in blocks if isinstance(b, Mapping)}
    if "tool_result" in kinds or not ({"text", "image"} & kinds):
        return False
    return not message_text(message).lstrip().startswith(NOT_ASKED)


def _stamp(entry: Mapping[str, Any]) -> float:
    try:
        text = str(entry.get("timestamp") or "").replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp() if text else 0.0
    except ValueError:
        return 0.0


def _identity(entry: Mapping[str, Any], position: int, request: bool) -> str:
    """The same prompt or message when Claude Code writes it again after a boundary: a
    request by its `promptId`, anything else by time and content. Only a request: in
    `claude -p` every tool result carries its request's `promptId` too. An entry without a
    time is never taken for another."""
    if request and entry.get("promptId"):
        return f"prompt:{entry['promptId']}"
    if not entry.get("timestamp"):
        return f"at:{position}"
    return json.dumps([entry["timestamp"], entry.get("message")], sort_keys=True, default=str)


def split_requests(entries: Iterable[Mapping[str, Any]]) -> Split:
    groups: list[list[Mapping[str, Any]]] = []
    stamps: list[float] = []
    last_at: list[int] = []  # position of each group's latest entry
    opened: dict[str, int] = {}  # prompt identity -> group
    seen: set[str] = set()
    boundary = -1
    current = -1
    for position, entry in enumerate(entries):
        if _is_boundary(entry):
            boundary = position
            continue
        if not _conversational(entry):
            continue
        message = entry["message"]
        request = is_request(message)
        identity = _identity(entry, position, request)
        if request:
            if identity in opened:  # written again after a boundary: the same request
                current = opened[identity]
            else:
                opened[identity] = current = len(groups)
                groups.append([message])
                stamps.append(_stamp(entry))
                last_at.append(position)
        elif current >= 0 and identity not in seen:
            groups[current].append(message)
        if current >= 0:
            last_at[current] = position
        seen.add(identity)
    live = frozenset(i + 1 for i, at in enumerate(last_at) if at > boundary)
    return Split(tuple(tuple(g) for g in groups), tuple(stamps), live)


def relative(path: str, cwd: str) -> str:
    """`path` relative to `cwd` when it lies under it, forward slashes either way."""
    return _relative(path, cwd)


def line_print(line: str) -> str:
    """One line's print: its words only, joined by single spaces, hashed (the text is not kept).
    Quotes, commas, brackets and spacing, which formatters rewrite after an edit, do not count."""
    return hashlib.sha1(" ".join(_WORDS.findall(line)).encode("utf-8")).hexdigest()[:12]


def _counts(raw: str) -> str:
    """The line collapsed, or "" when it cannot tell code apart: shorter than LINE_MIN, no word,
    an import or a decorator (in every file of a project), or a line holding a secret (the
    mask changes it: its print could be checked against a dictionary offline)."""
    line = " ".join(raw.split())
    if len(line) < LINE_MIN or not any(c.isalnum() for c in line) or COMMON.match(line):
        return ""
    return line if mask(line) == line else ""


def _ordered_prints(text: Any) -> list[str]:
    if not isinstance(text, str):
        return []
    return list(dict.fromkeys(line_print(x) for raw in text.split("\n") if (x := _counts(raw))))


def line_prints(text: Any) -> set[str]:
    """Prints of the lines of `text` that can tell code apart (see `_counts`)."""
    return set(_ordered_prints(text))


_NUMBERED = re.compile(r"^\s*\d+[\u2192\t]", re.M)


def _wrote(history: Sequence[Any], cwd: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Per file, prints of the lines the request's successful edits left added, in the order
    written: a line the request later took out goes again, and a Write over a file the request
    had read counts only the lines that read did not show (review of v4, 2026-10-01). The last
    WROTE_MAX lines per file are kept."""
    per: dict[str, list[str]] = {}
    last_read: dict[str, str] = {}
    for call in history:
        data = call.input if isinstance(call.input, Mapping) else {}
        path = data.get("file_path")
        if not isinstance(path, str) or call.is_error:
            continue
        rel = _relative(path, cwd)
        if call.tool == "Read":
            last_read[rel] = _NUMBERED.sub("", call.result)
            continue
        if call.tool == "Edit":
            pairs = [(data.get("old_string"), data.get("new_string"))]
        elif call.tool == "MultiEdit":
            pairs = [(e.get("old_string"), e.get("new_string"))
                     for e in data.get("edits") or [] if isinstance(e, Mapping)]  # fmt: skip
        elif call.tool == "Write":
            pairs = [(last_read.get(rel, ""), data.get("content"))]
        else:
            continue
        for old, new in pairs:
            before, after = set(_ordered_prints(old)), _ordered_prints(new)
            kept = [p for p in per.get(rel, []) if p not in before - set(after)]
            per[rel] = kept + [p for p in after if p not in before and p not in kept]
    return tuple((rel, tuple(prints[-WROTE_MAX:])) for rel, prints in per.items() if prints)


def _prints_from(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    """Stored prints back, or None (treated as a record saved before v4) when malformed."""
    if not isinstance(value, list | tuple):
        return None
    out = []
    for pair in value:
        if not (isinstance(pair, list | tuple) and len(pair) == 2 and isinstance(pair[0], str)
                and isinstance(pair[1], list | tuple)
                and all(isinstance(p, str) for p in pair[1])):  # fmt: skip
            return None
        out.append((pair[0], tuple(pair[1])))
    return tuple(out)


def same_path(a: str, b: str) -> bool:
    fold = os.name == "nt" or sys.platform == "darwin"
    x, y = a.replace("\\", "/"), b.replace("\\", "/")
    return x.casefold() == y.casefold() if fold else x == y


def _relative(path: str, cwd: str) -> str:
    clean = path.replace("\\", "/")
    base = cwd.replace("\\", "/").rstrip("/") + "/"
    return clean[len(base) :] if cwd and clean.lower().startswith(base.lower()) else clean


def _finished(messages: Sequence[Mapping[str, Any]]) -> bool:
    """The last message is the agent's, and it asks for no tool: the agent said it was done."""
    last = messages[-1]
    kinds = {b.get("type") for b in blocks_of(last) if isinstance(b, Mapping)}
    return last.get("role") == "assistant" and "tool_use" not in kinds


def _report(messages: Sequence[Mapping[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant" and (text := message_text(message)):
            prefix = "" if _finished(messages) else UNFINISHED
            return mask(prefix + truncate(text, REPORT_CHARS))
    return ""


def _request(first: Mapping[str, Any]) -> str:
    """The prompt verbatim and masked; a slash command keeps its name and arguments."""
    kept = guard_mod.requests_of([first], REQUEST_CHARS)
    if kept and kept[0].strip():
        return kept[0]
    bare = " ".join(_TAGS.sub(" ", message_text(first)).split())
    return mask(truncate(bare, REQUEST_CHARS)) or "(an image, no text)"


def episode_of(
    group: Sequence[Mapping[str, Any]], *, session: str, index: int, cwd: str = "",
    at: float = 0.0,
) -> Episode | None:  # fmt: skip
    """The record of one request, or None while the agent has said nothing yet."""
    messages = merge_consecutive(group)
    report = _report(messages)
    if not report:
        return None
    history = calls(messages)
    request = _request(group[0])
    trail = guard_mod.trail_of(history)
    raw = [_relative(t.removeprefix(CHANGED), cwd) for t in trail if t.startswith(CHANGED)]
    changed = [mask(path) for path in raw]
    tests = next((t.removeprefix(TESTED) for t in trail if t.startswith(TESTED)), "")
    read: list[str] = []
    for call in history:
        path = call.input.get("file_path")
        if call.tool != "Read" or not isinstance(path, str):
            continue
        if (rel := mask(_relative(path, cwd))) not in read:
            read.append(rel)
    found = guard_mod.candidates(history, guard_mod.focus_of([request]))
    chosen = guard_mod.choose(found, FACTS_CHARS)
    return Episode(
        session=session, index=index, request=request, report=report,
        changed=tuple(changed[:FILES_MAX]), changed_raw=tuple(raw[:FILES_MAX]),
        wrote=_wrote(history, cwd),
        read=tuple(p for p in read if p not in changed)[:FILES_MAX], tests=tests,
        facts=tuple(f"{f.source}: {f.line}" for f in chosen), tool_calls=len(history), at=at,
    )  # fmt: skip


def episodes_of(
    entries: Sequence[Mapping[str, Any]], *, session: str, cwd: str = ""
) -> tuple[list[Episode], frozenset[int]]:
    """Every finished request of a transcript, and the requests still in its conversation."""
    split = split_requests(entries)
    numbered = enumerate(zip(split.groups, split.stamps, strict=True), start=1)
    made = (episode_of(g, session=session, index=i, cwd=cwd, at=at) for i, (g, at) in numbered)
    return [e for e in made if e is not None], split.live


# ---- storage -------------------------------------------------------------------------------------


def write_private(path: Path, text: str) -> None:
    """Write `text` atomically (a reader never sees half a file), readable by this user only."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temp, 0o600)
        _replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _replace(temp: str, path: Path, tries: int = 25) -> None:
    """`os.replace`, again while Windows refuses it because another hook has `path` open for
    reading (PermissionError); a reader holds it for milliseconds."""
    for attempt in range(tries):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.01)


LOCK_WAIT_S = 2.0
LOCK_STALE_S = 10.0


@contextlib.contextmanager
def locked(path: Path) -> Iterator[None]:
    """`path`.lock held while the block runs: two sessions' hooks (a Stop and another session's
    catch-up, or parallel tool calls) must not both read-modify-write one file. Created
    exclusively; a lock older than LOCK_STALE_S is a crashed holder's and is taken over. Past
    LOCK_WAIT_S the block runs anyway: a hook must never hang the session."""
    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    deadline = time.monotonic() + LOCK_WAIT_S
    held = False
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            held = True
            break
        except (FileExistsError, PermissionError):  # Windows: a lock being deleted says denied
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > LOCK_STALE_S:
                    lock.unlink()
                    continue
            if time.monotonic() > deadline:
                break
            time.sleep(0.01)
        except OSError:
            break
    try:
        yield
    finally:
        if held:
            with contextlib.suppress(OSError):
                lock.unlink()


def save(
    folder: Path, episodes: Iterable[Episode], *, keep_days: int = KEEP_DAYS,
    session: str | None = None,
) -> list[str]:  # fmt: skip
    """Write each record whose file is missing or differs (the keys written), and remove the
    project's records older than `keep_days`: they hold command output. With `session`, the
    whole recording of that session: its stored records the recording no longer makes (an
    older split of the same transcript) are removed. The index follows."""
    episodes = list(episodes)
    written: list[str] = []
    for episode in episodes:
        path = folder / f"{safe_name(episode.key)}.json"
        text = json.dumps(episode.to_dict(), ensure_ascii=False)
        try:
            if path.exists() and path.read_text(encoding="utf-8") == text:
                continue
        except OSError:
            pass
        write_private(path, text)
        written.append(episode.key)
    gone: list[str] = []
    if session is not None and episodes:  # an empty reading never wipes a session
        made = {f"{safe_name(e.key)}.json" for e in episodes}
        for path in folder.glob(f"{safe_name(session)}-*.json"):
            if path.name not in made and path.stem[len(safe_name(session)) + 1:].isdigit():
                with contextlib.suppress(OSError):
                    path.unlink()
                    gone.append(f"{session}-{path.stem.rsplit('-', 1)[1]}")
    if written and keep_days > 0:
        prune(folder, time.time() - keep_days * 86_400)
    if written or gone or not (folder / INDEX).exists():
        by_key = {e.key: e for e in episodes}
        _update_index(folder, [by_key[k] for k in written if k in by_key], keep_days, gone)
    return written


def _entry(episode: Episode) -> dict[str, Any]:
    return {"changed": list(episode.changed_raw or episode.changed), "at": episode.at}


def _read_index(folder: Path) -> dict[str, dict[str, Any]] | None:
    try:
        data = json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): v for k, v in data.items()
            if isinstance(v, dict) and isinstance(v.get("changed", []), list)}  # fmt: skip


def _update_index(
    folder: Path, episodes: Sequence[Episode], keep_days: int, gone: Sequence[str] = ()
) -> None:
    with locked(folder / INDEX):
        index = _read_index(folder)
        if index is None:
            index = {e.key: _entry(e) for e in load(folder, limit=0)}
        cutoff = time.time() - keep_days * 86_400 if keep_days > 0 else float("-inf")
        fresh = {**index, **{e.key: _entry(e) for e in episodes}}
        kept = {k: v for k, v in fresh.items() if k not in set(gone) and (
            float(v.get("at") or 0.0) >= cutoff or not float(v.get("at") or 0.0))}  # fmt: skip
        write_private(folder / INDEX, json.dumps(kept, ensure_ascii=False))


def index_of(folder: Path) -> dict[str, dict[str, Any]]:
    """The project's index, rebuilt from all its records when missing or unreadable."""
    index = _read_index(folder)
    if index is not None:
        return index
    if not folder.is_dir():
        return {}
    with locked(folder / INDEX):
        index = _read_index(folder)  # another hook may have rebuilt it meanwhile
        if index is not None:
            return index
        rebuilt = {e.key: _entry(e) for e in load(folder, limit=0)}
        with contextlib.suppress(OSError):  # read-only store: the index is only a speed-up
            write_private(folder / INDEX, json.dumps(rebuilt, ensure_ascii=False))
    return rebuilt


def load_keys(folder: Path, keys: Iterable[str]) -> list[Episode]:
    """These records only, oldest first; a key whose file is gone is skipped."""
    out = []
    for key in keys:
        try:
            data = json.loads((folder / f"{safe_name(key)}.json").read_text(encoding="utf-8"))
            out.append(Episode.from_dict(data))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(out, key=lambda e: (e.at, e.session, e.index))


def _is_record(path: Path) -> bool:
    return path.name != INDEX and not path.name.startswith(".tmp-")


def prune(folder: Path, before: float) -> None:
    for path in folder.glob("*.json"):
        if path.name == INDEX:
            continue
        try:
            if path.stat().st_mtime < before:
                path.unlink()
        except OSError:
            continue


def load(folder: Path, *, limit: int = LOAD_LIMIT) -> list[Episode]:
    """The newest `limit` records of a project (by file time, before any is parsed; 0 for all),
    oldest first. Unreadable files and a writer's temporary files are skipped."""
    if not folder.is_dir():
        return []
    stamped: list[tuple[float, Path]] = []
    for path in folder.glob("*.json"):
        if not _is_record(path):
            continue
        try:
            stamped.append((path.stat().st_mtime, path))
        except OSError:
            continue
    out: list[Episode] = []
    for _, path in sorted(stamped)[-limit if limit > 0 else None:]:
        try:
            out.append(Episode.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return sorted(out, key=lambda e: (e.at, e.session, e.index))
