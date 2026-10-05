"""What a request changed in the working tree, whatever tool changed it (memory v6).

Records built from the transcript know what the file tools changed. An agent that edits through
the shell (`python - <<E ... s.replace(...)`, `sed -i`: Sonnet 5.5 did in 70-100 % of its
requests in phase B2, 2026-10-01) leaves records that changed nothing, and the touch has nothing
to match. So the memory hook takes a `snapshot` of the git working tree when a request starts
and another when it stops; `changes` gives the files whose content differs and, per file,
prints of the lines the request added (`episodes.line_print`, never the text).

Only git working trees; anything else, or git slower than `SECONDS`, gives None and the
records stay as the transcript makes them. git runs read-only (`GIT_OPTIONAL_LOCKS=0`: it never
takes `index.lock` from under the person's own `git commit`). Untracked files count (a new
module); ignored ones do not, nor files named like secrets (`.env*`, keys, certificates). Files
above `MAX_BYTES` are named without prints; at most `MAX_FILES` dirty files are looked at, and
`changes` stops at its deadline. Which of the changed files a request may claim is the hook's
choice (`memory_hook.finish_tree`: only files the request wrote).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import episodes as ep

SECONDS = 3.0
MAX_FILES = 300
MAX_BYTES = 1_000_000
TOTAL_BYTES = 20_000_000  # read per snapshot; past it a file is compared by size and time only
SECRET_NAME = re.compile(
    r"^\.env|\.(pem|key|p12|pfx|jks|keystore|asc|gpg)$|^id_(rsa|dsa|ecdsa|ed25519)|credential|"
    r"secret|\.netrc$|\.npmrc$|\.pypirc$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The tree at one moment: the repository's root, HEAD, and per dirty or untracked file
    (relative to the root) a content key and its prints."""

    root: str
    head: str
    files: dict[str, str] = field(default_factory=dict)
    prints: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"root": self.root, "head": self.head, "files": self.files,
                "prints": {k: list(v) for k, v in self.prints.items()}}  # fmt: skip

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        return cls(str(data["root"]), str(data.get("head") or ""), dict(data.get("files") or {}),
                   {k: tuple(v) for k, v in (data.get("prints") or {}).items()})  # fmt: skip


def _run(cwd: str, *args: str, data: bytes | None = None) -> bytes | None:
    """git, read-only, its output as bytes (None when it fails)."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    done = subprocess.run(["git", "-C", cwd, "-c", "core.quotepath=off", *args],
                          capture_output=True, timeout=SECONDS, check=False, env=env,
                          input=data)  # fmt: skip
    return done.stdout if done.returncode == 0 else None


def _text(raw: bytes | None) -> str | None:
    return None if raw is None else raw.decode("utf-8", errors="surrogateescape")


def _git(cwd: str, *args: str) -> str | None:
    return _text(_run(cwd, *args))


def _fold(path: str) -> str:
    clean = path.replace("\\", "/")
    return clean.casefold() if os.name == "nt" or sys.platform == "darwin" else clean


def _secret(rel: str) -> bool:
    return bool(SECRET_NAME.search(rel.replace("\\", "/").rsplit("/", 1)[-1]))


def _read(path: Path, budget: list[int]) -> tuple[bytes | None, str]:
    """(the content, or None when too large or past the budget; a content key either way)."""
    try:
        stat = path.stat()
        if stat.st_size > MAX_BYTES or stat.st_size > budget[0]:
            return None, f"stat:{stat.st_size}:{stat.st_mtime_ns}"
        data = path.read_bytes()
    except OSError:
        return None, "unreadable"
    budget[0] -= len(data)
    return data, hashlib.sha1(data).hexdigest()


def _prints(data: bytes | None) -> tuple[str, ...]:
    if not data:
        return ()
    return tuple(ep._ordered_prints(data.decode("utf-8", errors="replace")))


def _status(item: str) -> str | None:
    """The path of one `git status --porcelain=v2` entry (ordinary, unmerged, untracked)."""
    if item.startswith("1 "):
        parts = item.split(" ", 8)
        return parts[8] if len(parts) == 9 else None
    if item.startswith("u "):
        parts = item.split(" ", 10)
        return parts[10] if len(parts) == 11 else None
    return item[2:] if item.startswith("? ") else None


def snapshot(cwd: str) -> Snapshot | None:
    """The tree of the repository holding `cwd`, or None (not git, git missing or too slow)."""
    return probe(cwd)[0]


def _failure(error: Exception, step: str) -> str:
    if isinstance(error, subprocess.TimeoutExpired):
        return f"git timed out after {SECONDS} s ({step})"
    if isinstance(error, FileNotFoundError):
        return f"git not found ({step})"
    return f"{error.__class__.__name__} ({step})"


def probe(cwd: str) -> tuple[Snapshot | None, str]:
    """`snapshot`, and when there is none why not (v6.3: two B2 passes lost a snapshot and left
    no trace; the hook logs this reason). The reason is "" when there is a snapshot."""
    step = "rev-parse"
    try:
        root = (_git(cwd, "rev-parse", "--show-toplevel") or "").strip()
        if not root:
            return None, "not a git working tree"
        step = "status"
        status = _git(root, "status", "--porcelain=v2", "-z", "--branch", "-uall",
                      "--no-renames")  # fmt: skip
    except (OSError, subprocess.SubprocessError) as error:
        return None, _failure(error, step)
    if status is None:
        return None, "git status failed"
    return _parse(root, status), ""


def _parse(root: str, status: str) -> Snapshot:
    head = ""
    files: dict[str, str] = {}
    prints: dict[str, tuple[str, ...]] = {}
    budget = [TOTAL_BYTES]
    for item in status.split("\0"):
        if item.startswith("# branch.oid "):
            oid = item.removeprefix("# branch.oid ").strip()
            head = "" if oid == "(initial)" else oid
            continue
        rel = _status(item)
        if rel is None or _secret(rel) or len(files) >= MAX_FILES:
            continue
        data, files[rel] = _read(Path(root) / rel, budget)
        prints[rel] = _prints(data)
    return Snapshot(root, head, files, prints)


def _committed(root: str, head: str, rels: list[str]) -> dict[str, tuple[str, ...]]:
    """Prints of each file as committed at `head`, through one `git cat-file --batch`."""
    if not head or not rels:
        return {}
    query = "".join(f"{head}:{rel}\n" for rel in rels).encode("utf-8", errors="surrogateescape")
    try:
        out = _run(root, "cat-file", "--batch", data=query)
    except (OSError, subprocess.SubprocessError):
        return {}
    found: dict[str, tuple[str, ...]] = {}
    at = 0
    for rel in rels:
        if out is None or at >= len(out):
            break
        end = out.index(b"\n", at)
        header = out[at:end].split()
        at = end + 1
        if len(header) == 3 and header[1] == b"blob":
            size = int(header[2])
            body = out[at:at + size]
            at += size + 1
            found[rel] = _prints(body) if size <= MAX_BYTES else ()
    return found


def changes(
    before: Snapshot | None, after: Snapshot | None, only: Iterable[str] | None = None,
    deadline: float | None = None,
) -> list[tuple[str, tuple[str, ...]]]:  # fmt: skip
    """Files whose content differs between the snapshots (relative to the root), each with the
    prints of the lines `after` has that `before` did not, in file order, the last
    `episodes.WROTE_MAX` kept. With `only`, those paths alone are looked at; past `deadline`
    (a `time.monotonic()` value) what was found so far."""
    if before is None or after is None or before.root != after.root:
        return []
    wanted = None if only is None else {_fold(x) for x in only}
    paths = set(before.files) | set(after.files)
    moved: set[str] = set()
    if before.head != after.head and before.head and after.head:
        try:
            names = _git(after.root, "diff", "--name-only", "-z", before.head, after.head) or ""
        except (OSError, subprocess.SubprocessError):
            names = ""
        moved = {p for p in names.split("\0") if p and (wanted is None or _fold(p) in wanted)}
        moved = set(sorted(moved)[:MAX_FILES])
        paths |= moved
    if wanted is not None:
        paths = {p for p in paths if _fold(p) in wanted}
    changed = [rel for rel in sorted(paths) if not _secret(rel) and (
        rel in moved or before.files.get(rel) != after.files.get(rel))]  # fmt: skip
    old_head = _committed(after.root, before.head, [r for r in changed if r not in before.files])
    new_head = _committed(after.root, after.head, [r for r in changed if r not in after.files])
    out = []
    for rel in changed:
        if deadline is not None and time.monotonic() > deadline:
            break
        old = set(before.prints.get(rel, ()) if rel in before.files else old_head.get(rel, ()))
        new = after.prints.get(rel, ()) if rel in after.files else new_head.get(rel, ())
        out.append((rel, tuple(p for p in new if p not in old)[-ep.WROTE_MAX:]))
    return out
