"""Lot memgate-hook: what a live call must meet before the key is read, and the time zone a
replay must share with the run of record. `git` and the clock are passed in, so the rules are
tested without either."""

from __future__ import annotations

import datetime
import hashlib
import pathlib
import re
import subprocess
import time
from collections.abc import Callable, Mapping
from typing import Any

UPDATE_WINDOW = (2, 8)  # Windows Update may restart the machine from 02:00 to 08:00
# The launcher's two local values, read as their placeholders by the seal (benchmarks/
# paid_once.py's rule): the owner fills them in the copy under C:\sp-runs without breaking it,
# and no local path goes into anything tracked.
LOCAL_VALUES = {"PY": "<PYTHON>", "SANCHOPANZA_KEYS_ENV": "<KEYS_ENV_PATH>"}
_LOCAL = re.compile(r'^(set "(PY|SANCHOPANZA_KEYS_ENV)=)[^"\n]*(")', re.MULTILINE)


def launcher_digest(path: pathlib.Path) -> str:
    """sha256 of the launcher (LF line ends) with `set "PY=..."` and `set
    "SANCHOPANZA_KEYS_ENV=..."` as their placeholders; any other change moves it."""
    text = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    normal = _LOCAL.sub(lambda m: f"{m.group(1)}{LOCAL_VALUES[m.group(2)]}{m.group(3)}", text)
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()


Git = Callable[..., str]


def git_in(repo: pathlib.Path) -> Git:
    def run(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              check=True)  # fmt: skip
        return done.stdout

    return run


def live_refusal(name: str, *, repo: pathlib.Path, out: pathlib.Path,
                 now: datetime.datetime, git: Git) -> str:  # fmt: skip
    """Why a live `name` ("smoke" or "run") must not start, or "": not inside the update
    window; HEAD is the commit that wrote this lot's seal; nothing changed outside `out` (the
    lot's own folder, where answers and rows are written); for the run, the smoke is scored."""
    start, end = UPDATE_WINDOW
    if start <= now.hour < end:
        return f"it is {now:%H:%M}, inside the {start:02d}:00-{end:02d}:00 update window"
    rel = out.relative_to(repo).as_posix()
    sealed = git("log", "-1", "--format=%H", "--", f"{rel}/prereg.sha256").strip()
    if not sealed:
        return "the seal (prereg.sha256) is not committed"
    head = git("rev-parse", "HEAD").strip()
    if head != sealed:
        return f"HEAD {head[:8]} is not the commit that wrote the seal, {sealed[:8]}"
    dirty = [line for line in git("status", "--porcelain").splitlines()
             if line.strip() and not line[3:].strip().strip('"').startswith(rel)]  # fmt: skip
    if dirty:
        return f"{len(dirty)} paths changed outside {rel}: the tree is not the sealed one"
    if name == "run" and not (out / "smoke-scored.jsonl").exists():
        return "the smoke is not scored (smoke-scored.jsonl): run --smoke --live first"
    return ""


def time_zone() -> dict[str, Any]:
    """What `Episode.title` depends on: the zone's names and offsets (not today's offset)."""
    offset = datetime.datetime.now().astimezone().utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    return {"tzname": list(time.tzname), "timezone_s": time.timezone, "altzone_s": time.altzone,
            "utc_offset_min_now": minutes}  # fmt: skip


def zone_mismatch(saved: Mapping[str, Any], current: Mapping[str, Any]) -> str:
    """Why a replay under `current` would not rebuild the run's requests, or ""."""
    keys = ("tzname", "timezone_s", "altzone_s")
    if all(saved.get(k) == current.get(k) for k in keys):
        return ""
    return (f"the run was in {saved.get('tzname')} ({saved.get('timezone_s')} s), this "
            f"process is in {current.get('tzname')} ({current.get('timezone_s')} s): the "
            "records' titles, and so L's recording keys, would differ")  # fmt: skip
