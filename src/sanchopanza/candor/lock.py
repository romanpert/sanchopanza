"""The sticky lock: once engaged, every tool call is refused until a human releases it.

Pure code and a local file, no model and no network, so the check that stops an agent cannot
be talked out of its answer or time out into a pass. It **fails closed**: a lock file that
exists but cannot be read counts as engaged. Everything else in sanchopanza fails open; this
is the one place where the failure the operator sees (a stopped agent) is the cheap one.

The agent cannot release it: while it is engaged the PreToolUse hook refuses every call, the
release command included, and the ledger classifies any touch of the lock file as `tamper`.
A human releases it from their own terminal with `python -m sanchopanza.candor release`.

Evidence behind the shape (docs/results/2026-09-29-candor/README.md): human approvers pass
93-97 % of permission prompts and catch fewer of them as a session goes on, so a lock that
fires often is a lock that gets rubber-stamped. The release records who and why, and the
screen shows the claim beside the action, not a yes/no.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._env import home_dir
from .rules import Finding

LOCK_NAME = "candor-lock.json"
LOCKS_DIR = "candor-locks"
SCOPES = ("session", "project", "machine")


def scope() -> str:
    """SANCHOPANZA_CANDOR_LOCK_SCOPE: `session` (default), `project` or `machine`.

    One file for the whole machine held every other candor session on it, in other projects,
    from their first call, until a person looked (the Indagis scene, 2026-09-30). A flagged
    session is what needs a person; other work is not evidence against it. `project` is for
    an orchestrator that starts sessions on its own, where a new session must not walk past
    the hold; `machine` keeps the old behaviour. Anything else reads as `session`."""
    chosen = os.environ.get("SANCHOPANZA_CANDOR_LOCK_SCOPE", "session").strip().lower()
    return chosen if chosen in SCOPES else "session"


def project_root(cwd: str | os.PathLike[str] | None) -> Path:
    """The git root above `cwd`, or `cwd` itself: worktrees of one repository stay apart,
    since each has its own root."""
    start = Path(cwd or os.getcwd()).resolve()
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return start


def _safe(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum() or ch in "-_")[:80]


def default_path(session: str = "", cwd: str | os.PathLike[str] | None = None) -> Path:
    """Where the lock for this session lives. SANCHOPANZA_CANDOR_LOCK, a file, wins over the
    scope. A session with no id falls back to its project, never to the machine."""
    override = os.environ.get("SANCHOPANZA_CANDOR_LOCK")
    if override:
        return Path(override)
    chosen = scope()
    if chosen == "machine":
        return home_dir() / LOCK_NAME
    if chosen == "session" and _safe(session):
        return home_dir() / LOCKS_DIR / f"session-{_safe(session)}.json"
    root = str(project_root(cwd)).lower() if os.name == "nt" else str(project_root(cwd))
    digest = hashlib.sha1(root.encode("utf-8")).hexdigest()[:16]
    return home_dir() / LOCKS_DIR / f"project-{digest}.json"


def engaged_paths() -> list[Path]:
    """Every lock file that is engaged on this machine, for the person's `status` and
    `release`: the explicit file, the machine file and each scoped one."""
    override = os.environ.get("SANCHOPANZA_CANDOR_LOCK")
    candidates = [Path(override)] if override else []
    candidates.append(home_dir() / LOCK_NAME)
    folder = home_dir() / LOCKS_DIR
    if folder.is_dir():
        candidates.extend(sorted(folder.glob("*.json")))
    seen: list[Path] = []
    for path in candidates:
        if path not in seen and read(path).engaged:
            seen.append(path)
    return seen


@dataclass(frozen=True, slots=True)
class LockState:
    engaged: bool
    reason: str = ""
    findings: tuple[dict[str, Any], ...] = ()
    session: str = ""
    since: float = 0.0


def read(path: Path | None = None) -> LockState:
    """The lock as it stands. Unreadable counts as engaged: fail closed."""
    path = path or default_path()
    if not path.exists():
        return LockState(False)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return LockState(True, reason="lock file unreadable: treated as engaged")
    if not isinstance(data, dict) or not data.get("engaged"):
        return LockState(False)
    return LockState(
        True,
        reason=str(data.get("reason") or ""),
        findings=tuple(data.get("findings") or ()),
        session=str(data.get("session") or ""),
        since=float(data.get("since") or 0.0),
    )


def engage(
    findings: Sequence[Finding], *, session: str = "", path: Path | None = None
) -> LockState:
    """Engage the lock with what triggered it. An engaged lock keeps its first reason."""
    path = path or default_path()
    current = read(path)
    if current.engaged:
        return current
    worst = findings[0] if findings else None
    reason = f"{worst.rule}: {worst.detail}" if worst else "engaged"
    state = {
        "engaged": True,
        "reason": reason,
        "findings": [f.to_dict() for f in findings],
        "session": session,
        "since": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)
    return read(path)


def release(*, by: str, why: str, path: Path | None = None) -> LockState:
    """Release the lock, keeping a line of who released it and why beside it."""
    path = path or default_path()
    before = read(path)
    if not by.strip() or not why.strip():
        raise ValueError("a release needs who releases it and why")
    history = path.with_name(path.stem + "-releases.jsonl")
    entry = {"at": time.time(), "by": by, "why": why, "reason": before.reason,
             "findings": list(before.findings)}  # fmt: skip
    history.parent.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if path.exists():
        path.unlink()
    return read(path)


def refusal(state: LockState) -> str:
    """What the agent is told while the lock is engaged. Short on purpose: an agent that learns
    exactly which check fired learns what to avoid next time (arXiv 2508.19461)."""
    return (
        "sanchopanza: this session is on hold for human review. Every tool call is refused until "
        "a person releases it. Stop here and tell the user plainly what you did and what you "
        "reported, so they can compare the two."
    )


def summary(state: LockState) -> str:
    """What the human sees: each finding with the claim beside the action, not a yes/no."""
    if not state.engaged:
        return "no lock engaged"
    lines = [f"LOCK ENGAGED ({state.reason})"]
    for f in state.findings:
        lines.append(f"- [{f.get('severity')}] {f.get('rule')}: {f.get('detail')}")
        if f.get("claim"):
            lines.append(f"    said: {str(f['claim'])[:200]}")
        if f.get("action"):
            lines.append(f"    did:  {str(f['action'])[:200]}")
    return "\n".join(lines)
