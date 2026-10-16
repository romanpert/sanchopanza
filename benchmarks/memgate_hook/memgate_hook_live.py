"""Lot memgate-hook: what a live call must meet before the key is read, and the time zone a
replay must share with the run of record. `git` and the clock are passed in, so the rules are
tested without either."""

from __future__ import annotations

import datetime
import fnmatch
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


# What a run writes in the lot's folder: the only paths that may differ from HEAD there.
RUN_FILES = ("*-answers-*", "*-scored*", "*-zone.json", "summary.json")
SEAL_FILES = ("prereg.sha256", "prereg.manifest.json")  # all the sealing commit may change


def _run_file(path: str, rel: str) -> bool:
    folder, _, base = path.rpartition("/")
    return folder == rel and any(fnmatch.fnmatchcase(base, p) for p in RUN_FILES)


def changed_paths(git: Git) -> list[str]:
    """Every path that differs from HEAD (staged, unstaged or untracked, files not folders)."""
    lines = git("status", "--porcelain", "--untracked-files=all").splitlines()
    return [line[3:].split(" -> ")[-1].strip().strip('"') for line in lines if line.strip()]


def heads(git: Git) -> dict[str, Any]:
    """HEAD and its parents (the sealing commit and the commit it sealed)."""
    ids = git("rev-list", "--parents", "-n", "1", "HEAD").split()
    return {"head": ids[0] if ids else "", "parents": ids[1:]}


def live_refusal(name: str, *, repo: pathlib.Path, out: pathlib.Path,
                 now: datetime.datetime, git: Git) -> str:  # fmt: skip
    """Why a live `name` ("smoke" or "run") must not start, or "":
    - not inside the update window;
    - HEAD is the commit that wrote this lot's seal, with a single parent, and it changed only
      `prereg.sha256` and `prereg.manifest.json` (the seal of what its parent holds);
    - nothing differs from HEAD but the run's own new files in `out` (answers, scored rows,
      the zone file, the summary): prereg.md and the seal files included;
    - for the run, the smoke is scored."""
    start, end = UPDATE_WINDOW
    if start <= now.hour < end:
        return f"it is {now:%H:%M}, inside the {start:02d}:00-{end:02d}:00 update window"
    rel = out.relative_to(repo).as_posix()
    sealed = git("log", "-1", "--format=%H", "--", f"{rel}/prereg.sha256").strip()
    if not sealed:
        return "the seal (prereg.sha256) is not committed"
    found = heads(git)
    if found["head"] != sealed:
        return f"HEAD {found['head'][:8]} is not the commit that wrote the seal, {sealed[:8]}"
    if len(found["parents"]) != 1:
        return f"the sealing commit has {len(found['parents'])} parents, not one"
    touched = set(git("diff", "--name-only", "HEAD^", "HEAD").split())
    if not touched <= {f"{rel}/{f}" for f in SEAL_FILES}:
        return f"the sealing commit changed {len(touched)} paths, not only the seal's two"
    dirty = [p for p in changed_paths(git) if not _run_file(p, rel)]
    if dirty:
        return f"{len(dirty)} paths differ from the sealed commit: {', '.join(dirty[:3])}"
    if name == "run" and not (out / "smoke-scored.jsonl").exists():
        return "the smoke is not scored (smoke-scored.jsonl): run --smoke --live first"
    return ""


def prereg_changed(repo: pathlib.Path, out: pathlib.Path, git: Git) -> bool:
    """prereg.md differs from HEAD: a re-seal must seal a committed prereg, not a draft."""
    rel = out.relative_to(repo).as_posix()
    return f"{rel}/prereg.md" in changed_paths(git)


def time_zone() -> dict[str, Any]:
    """What `Episode.title` depends on: the zone's names and offsets (not today's offset)."""
    offset = datetime.datetime.now().astimezone().utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    return {"tzname": list(time.tzname), "timezone_s": time.timezone, "altzone_s": time.altzone,
            "utc_offset_min_now": minutes}  # fmt: skip


def offsets(zone: Mapping[str, Any]) -> dict[str, Any]:
    """The zone's UTC offsets only, for the summary (Windows' zone names come back localised)."""
    return {k: zone.get(k) for k in ("timezone_s", "altzone_s", "utc_offset_min_now")}


def zone_mismatch(saved: Mapping[str, Any], current: Mapping[str, Any]) -> str:
    """Why a replay under `current` would not rebuild the run's requests, or ""."""
    keys = ("tzname", "timezone_s", "altzone_s")
    if all(saved.get(k) == current.get(k) for k in keys):
        return ""
    return (f"the run was in {saved.get('tzname')} ({saved.get('timezone_s')} s), this "
            f"process is in {current.get('tzname')} ({current.get('timezone_s')} s): the "
            "records' titles, and so L's recording keys, would differ")  # fmt: skip
