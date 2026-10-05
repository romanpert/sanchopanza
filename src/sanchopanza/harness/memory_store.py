"""Which store a session's memory lives in (F1 fix 2, "K1 read + K4 write").

**K1, the session's store.** Named after the git repository the session started in: its common
git dir (`git rev-parse --git-common-dir`), so sibling worktrees of one repository, and any
subfolder of it, share one store. The name is the folder name Claude Code would give the main
checkout (`memory_gate.project_key` of the repository's top folder), so a session started at the
top of a main checkout keeps the store it always had. Worked out once per session, at its first
hook event, and kept in `<root>/.keys/<session>.json`: the touch runs on every file the agent
opens and must not call git. Outside git, on a git error or timeout, with git older than 2.31
(no `--path-format`), or with `SANCHOPANZA_MEMORY_STORE_KEY=folder`, the store is the folder key
as before (the transcript's folder, else the cwd's `project_key`); why is logged.

**Migration.** When a session's store differs from its folder key, the store under the folder key
(where earlier versions wrote) is merged into it the first time a session uses it: rules by text
(the newest copy kept, newest first, `memory_rules.KEEP_MAX`), the `asked` and `audited` marks,
the records the new store lacks, and the session's own `shown` and `tree` files (a session that
was running at the upgrade). Only when the folder key is the cwd's own or one of its parents' up
to the checkout's top: a session launched in A that moved into B and was cleared keeps A's folder
key, and A's store must not be merged into B's (review of F1, H1). The old store is left as it
was. The merge runs again only when the old store changed since (an older install still writing).

**K4, where a request's rules are written.** At Stop, each request's rules go to the store of the
repository its changes landed in (the files it wrote, as its record keeps them): the session's
store when it wrote nothing, wrote only inside the checkout it started in, or wrote outside git.
On the maintainer's sessions, 33 of 52 writing sessions in one folder wrote into another
repository. A request's store is fixed the first time it is decided (kept in the session's key
file), so a request is never asked twice nor written into two stores (review of F1, M4). At most
LANDING_DIRS git calls per Stop.

Fails open everywhere: an error leaves the folder key, and the request as it was.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import _env
from ..context import episodes as ep
from ..context.archive import safe_name

KEYS = ".keys"  # never a project's name: `project_key` and Claude Code turn "." into "-"
ADOPTED = "adopted.json"
GIT_SECONDS = 2.0
LANDING_DIRS = 4  # git calls a Stop may make to find where a request's files landed
LANDED_MAX = 200  # requests whose store a session's key file remembers
OLD_GIT = "git older than 2.31 (no --path-format): the folder key is used"


@dataclass(frozen=True, slots=True)
class Repo:
    common: str  # the common git dir, absolute: shared by every worktree of the repository
    top: str  # the checkout's top folder (this worktree's)


def log(row: Mapping[str, Any]) -> None:
    """One JSON line in `MEMORY_STORE_LOG`, when set (the memory hook's log)."""
    path = _env.get("MEMORY_STORE_LOG", "")
    if not path:
        return
    # a debugging aid never changes what the hook does
    with contextlib.suppress(OSError), Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": round(time.time(), 3), **row}) + "\n")


def key_mode() -> str:
    """`repo` (default) or `folder` (the key before F1)."""
    chosen = str(_env.get("MEMORY_STORE_KEY", "") or "repo").strip().lower()
    return "folder" if chosen == "folder" else "repo"


def store_root() -> Path:
    return Path(_env.get("MEMORY_STORE", "") or _env.home_dir() / "memory-store")


def lookup(path: str) -> tuple[Repo | None, str]:
    """(the repository `path` lies in, "") from one git call, or (None, why)."""
    if not path:
        return None, "no folder"
    try:
        done = subprocess.run(
            ["git", "-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir",
             "--show-toplevel"],
            capture_output=True, timeout=GIT_SECONDS, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        return None, f"git timed out after {GIT_SECONDS} s"
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return None, f"git did not run ({error.__class__.__name__})"
    lines = done.stdout.decode("utf-8", errors="replace").splitlines()
    if done.returncode != 0:
        said = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return None, (said[0] if said else f"git exited {done.returncode}")[:200]
    if lines and lines[0].strip().startswith("--path-format"):  # echoed: an unknown option
        return None, OLD_GIT
    if len(lines) < 2 or not lines[0].strip():
        return None, "git said no repository"
    return Repo(common=lines[0].strip(), top=lines[1].strip()), ""


def git_repo(path: str) -> Repo | None:
    return lookup(path)[0]


def repo_name(repo: Repo) -> str:
    """The store's name: Claude Code's folder name for the main checkout (the folder holding a
    `.git` common dir), else for the common dir itself (a bare repository's worktrees)."""
    from .memory_gate import project_key  # not at import: only when a session's key is made

    common = repo.common.replace("\\", "/").rstrip("/")
    head, _, last = common.rpartition("/")
    return project_key(head if last.casefold() == ".git" and head else common)


def folder_key(event: Mapping[str, Any]) -> str:
    """The key before F1: the transcript's folder, else the cwd's `project_key`."""
    transcript = str(event.get("transcript_path") or "")
    if transcript:
        return Path(transcript).parent.name
    from .memory_gate import project_key

    return project_key(str(event.get("cwd", "")))


def _fold(text: str) -> str:
    clean = text.replace("\\", "/").rstrip("/")
    return clean.casefold() if os.name == "nt" or sys.platform == "darwin" else clean


def _key_path(root: Path, session: str) -> Path:
    return root / KEYS / f"{safe_name(session)}.json"


def session_key(root: Path, session: str) -> dict[str, Any] | None:
    """What `store_for` kept for `session` (name, top, cwd, landed), or None."""
    try:
        data = json.loads(_key_path(root, session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def own_folder_key(old: str, cwd: str, top: str) -> bool:
    """`old` is the folder key of `cwd` or of a folder above it up to the checkout's `top`."""
    from .memory_gate import project_key

    here, limit = cwd.replace("\\", "/").rstrip("/"), _fold(top)
    inside = _fold(here) == limit or _fold(here).startswith(limit + "/")
    for _ in range(64):
        if _fold(project_key(here)) == _fold(old):
            return True
        parent = os.path.dirname(here)
        if not inside or _fold(here) == limit or not parent or parent == here:
            return False
        here = parent
    return False


def _make_key(root: Path, session: str, cwd: str, old: str) -> dict[str, Any]:
    repo, why = lookup(cwd)
    name = repo_name(repo) if repo else ""
    data = {"name": name, "top": repo.top if repo else "", "cwd": cwd, "old": old,
            **({"why": why} if why else {})}  # fmt: skip
    with contextlib.suppress(OSError):
        ep.write_private(_key_path(root, session), json.dumps(data))
        _prune_keys(root)
    if why:
        log({"event": "store", "session": session, "key": "folder", "why": why})
    if name and _fold(name) != _fold(old):
        if own_folder_key(old, cwd, data["top"]):
            with contextlib.suppress(Exception):  # the old store is extra; never costs the key
                adopt(root / old, root / name, session)
        else:
            log({"event": "store", "session": session, "adopt": "skipped", "old": old,
                 "new": name, "why": "the folder key is not this checkout's"})  # fmt: skip
    return data


def _prune_keys(root: Path) -> None:
    cutoff = time.time() - ep.KEEP_DAYS * 86_400
    for path in (root / KEYS).glob("*.json"):
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < cutoff:
                path.unlink()


def store_for(event: Mapping[str, Any]) -> Path:
    """The session's store: K1 when the event has a session and a cwd, else the folder key."""
    root = store_root()
    old = folder_key(event) or "project"
    session, cwd = str(event.get("session_id") or ""), str(event.get("cwd") or "")
    if key_mode() == "folder" or not session or not cwd:
        return root / old
    data = session_key(root, session)
    if data is None:
        data = _make_key(root, session, cwd, old)
    name = str(data.get("name") or "")
    return root / (name or old)


# ---- migration -------------------------------------------------------------------------------


def _stamp(store: Path) -> list[int]:
    out = []
    for name in ("rules.json", ep.INDEX):
        try:
            stat = (store / name).stat()
            out.extend([stat.st_mtime_ns, stat.st_size])
        except OSError:
            out.extend([0, 0])
    return out


def _adopted(new: Path) -> dict[str, Any]:
    try:
        done = json.loads((new / ADOPTED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return done if isinstance(done, dict) else {}


def adopt(old: Path, new: Path, session: str) -> None:
    """Merge the store under the folder key into the session's store (see the module's doc).
    Every step is a merge, so two first sessions at once (or a stale lock, which `ep.locked`
    runs past) at worst merge twice."""
    if not old.is_dir():
        return
    from . import memory_rules

    with ep.locked(new / ADOPTED):
        stamp = _stamp(old)
        if _adopted(new).get(old.name) != stamp:
            theirs = memory_rules.load(old)
            if any(theirs.values()):
                memory_rules.merge(new, theirs)
            have = {p.stem for p in new.glob("*.json")}
            missing = [e for e in ep.load(old, limit=0) if safe_name(e.key) not in have]
            if missing:
                ep.save(new, missing)
            # read again just before writing: another session's marks are kept
            ep.write_private(new / ADOPTED, json.dumps({**_adopted(new), old.name: stamp}))
    _session_files(old, new, session)


def _session_files(old: Path, new: Path, session: str) -> None:
    """A session running at the upgrade keeps what it was given and its open snapshot."""
    from . import memory_tree

    name = safe_name(session)
    found = [old / "shown" / f"{name}.json", *(old / memory_tree.TREE).glob(f"{name}.json"),
             *(old / memory_tree.TREE).glob(f"{name}-*.json")]  # fmt: skip
    for path in found:
        target = new / path.relative_to(old)
        with contextlib.suppress(OSError):
            if path.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(path, target)


# ---- K4: where a request's changes landed ------------------------------------------------------


def _absolute(path: str) -> str | None:
    """An absolute path as written (a Git Bash `/c/x` as `c:/x`), or None for a relative one."""
    from .memory_tree import _absolute as is_absolute
    from .memory_tree import _bash_drive

    clean = _bash_drive(path.strip()).replace("\\", "/")
    return clean if clean and is_absolute(clean) else None


def _existing(path: str) -> str:
    """The nearest folder of `path` that exists (git -C needs one)."""
    current = Path(path).parent
    for _ in range(12):
        if current.is_dir() or current.parent == current:
            return str(current)
        current = current.parent
    return str(current)


class _Finder:
    """Repository names by folder, at most LANDING_DIRS git calls."""

    def __init__(self, root: Path) -> None:
        self.root, self.calls = root, 0
        self.seen: dict[str, str | None] = {}

    def name(self, path: str) -> str | None:
        folder = _existing(path)
        if _fold(folder) not in self.seen:
            if self.calls >= LANDING_DIRS:
                return None
            self.calls += 1
            repo = git_repo(folder)
            self.seen[_fold(folder)] = repo_name(repo) if repo else None
        return self.seen[_fold(folder)]


def _target(episode: ep.Episode, start: Path, top: str, finder: _Finder) -> Path:
    """The store of the repository most of the request's written files are in; the session's
    store on a tie, when it wrote nothing, or wrote only outside git."""
    counts: Counter[str] = Counter()
    names = {_fold(start.name): start.name}
    inside = _fold(top) + "/" if top else ""
    for raw in episode.changed_raw or episode.changed:
        full = _absolute(str(raw))
        if full is None or (inside and _fold(full).startswith(inside)):
            counts[_fold(start.name)] += 1  # relative to the start, or inside its checkout
            continue
        name = finder.name(full)
        if name:
            names.setdefault(_fold(name), name)
            counts[_fold(name)] += 1
    if not counts:
        return start
    best = max(counts.values())
    if counts.get(_fold(start.name)) == best:
        return start
    return finder.root / names[sorted(n for n, c in counts.items() if c == best)[0]]


def landing(start: Path, session: str, cwd: str,
            episodes: Sequence[ep.Episode]) -> dict[Path, list[ep.Episode]]:  # fmt: skip
    """The episodes grouped by the store their rules go to (K4), the session's store `start`
    first. A request's store is the one decided the first time (kept in the key file); without
    a key file (the folder key chosen, no session id) everything goes to `start`."""
    root = start.parent
    known = session_key(root, session) if key_mode() == "repo" else None
    if not episodes or known is None:
        return {start: list(episodes)} if episodes else {}
    landed = dict(known.get("landed") or {})
    top = str(known.get("top") or "") or cwd  # outside git: the folder it started in
    finder = _Finder(root)
    out: dict[Path, list[ep.Episode]] = {}
    fresh: dict[str, str] = {}
    for episode in episodes:
        name = landed.get(episode.key)
        target = root / name if name else _target(episode, start, top, finder)
        if not name:
            fresh[episode.key] = target.name
        out[target] = [*out.get(target, []), episode]
    if fresh:
        kept = list({**landed, **fresh}.items())[-LANDED_MAX:]
        with contextlib.suppress(OSError):
            ep.write_private(_key_path(root, session), json.dumps({**known, "landed": dict(kept)}))
    ordered = {start: out.pop(start)} if start in out else {}
    return {**ordered, **out}
