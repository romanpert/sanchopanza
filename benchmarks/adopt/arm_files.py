"""What an arm's session leaves on disk, and where: its row (written after every call), its
transcripts (from the configuration the session used) and the `env` block of its project
settings. Shared by `run.py` and `long_run.py`.

- **The row after every call** (long-session pre-mortem, c): written only at the chain's end, a
  crash at bug 55 of 60 lost the 54 calls before it. A row written mid-chain says
  `"partial": true`; `run.one_chain` refuses to read one as done.
- **Transcripts from CLAUDE_CONFIG_DIR** (d): a clean user's sessions live in
  `<config>/projects`, not `~/.claude/projects`; copying from the latter gave empty series.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

HOME_PROJECTS = Path.home() / ".claude" / "projects"


def projects_root(env: Mapping[str, str], default: Path = HOME_PROJECTS) -> Path:
    """Where Claude Code keeps the sessions it starts with `env`."""
    config = env.get("CLAUDE_CONFIG_DIR", "")
    return Path(config) / "projects" if config else default


def copy_transcripts(sessions: Iterable[str], evidence: Path, root: Path) -> list[str]:
    """Each session's transcript into the evidence (`transcript.jsonl`, or `-<n>` when the arm
    had several sessions); returns the sessions none was found for."""
    ordered = list(dict.fromkeys(s for s in sessions if s))
    missing = []
    for n, one in enumerate(ordered, start=1):
        found = next(root.glob(f"*/{one}.jsonl"), None)
        if found is None:
            missing.append(one)
            continue
        suffix = "" if len(ordered) == 1 else f"-{n}"
        shutil.copy(found, evidence / f"transcript{suffix}.jsonl")
    return missing


def write_row(evidence: Path, row: Mapping[str, Any]) -> None:
    """`row.json`, replaced whole: written beside and renamed, so a crash mid-write never leaves
    half a row."""
    path = evidence / "row.json"
    temporary = evidence / "row.json.tmp"
    temporary.write_text(json.dumps(dict(row), indent=1), encoding="utf-8")
    os.replace(temporary, path)


def partial_row(base: Mapping[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    """The row as it stands mid-chain."""
    return {**base, "calls": list(calls), "partial": True}


def write_env_settings(work: Path, env: Iterable[tuple[str, str]]) -> Path:
    """`env` merged into `<work>/.claude/settings.json` (created when absent): the only thing an
    arm like N-early adds to N. Variables already there keep their place; ours win."""
    settings = work / ".claude" / "settings.json"
    current = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    merged = {**current, "env": {**(current.get("env") or {}), **dict(env)}}
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(merged, indent=2), encoding="utf-8", newline="\n")
    return settings


def guard_parts(work: Path) -> str:
    """What the S install's compaction guard is, from its project settings: the SessionStart
    (compact) parts it delivers and the chooser its `env` sets (none: the install's default)."""
    settings = work / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    starts = [h.get("command", "") for e in data.get("hooks", {}).get("SessionStart", [])
              if e.get("matcher") == "compact" for h in e.get("hooks", [])]  # fmt: skip
    parts = sum(1 for c in starts if "guard-hook" in c and "--part " in c)
    chooser = (data.get("env") or {}).get("SANCHOPANZA_GUARD_CHOOSER") or "the install's default"
    return f"guard: {parts} SessionStart(compact) parts, chooser {chooser}"
