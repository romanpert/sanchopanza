"""A label for local sessions that does not ask the shell parser what a command writes.

The sealed label (`lineage or file`) sees file tools only, so every record a shell write gives
counts as noise under it; `+shell` (variants_v62.with_shell_label) is circular for the shell
touch, since both it and the touch ask `shell.written`. Here the truth comes from git instead:
the files of the commits the request made. `+commit` is the sealed label plus `file` for a
record that changed a file the request committed.

Which commits are the request's (review of 2026-10-01: a hash in the output alone let earlier
commits, amends, cherry-picks and a sibling worktree's commits in): a hash printed in the
request's shell output, `[branch abc1234] msg` from `git commit` or `abc1234 subject` from a `git
log --oneline` whose subject, whole, is in one of the request's `git commit` commands; and the
commit is in the HEAD reflog of the worktree the command ran in, as a plain `commit` (not an
amend, cherry-pick, rebase or reset), at a time inside the request's window (its transcript's
first and last stamps, SLACK seconds either side).

Limits, declared: only requests that commit can say anything (the rest keep the sealed label);
a commit may carry files written by earlier requests of the same worktree or by another session
in it (`git add -A`), which reads as related when it was not; a commit made elsewhere (`git -C
other`) or whose reflog expired is not found. Every git failure is counted. Read-only on the
repositories (`GIT_OPTIONAL_LOCKS=0`), local, free.

    python benchmarks/memory_real/commit_label.py [--items CACHE/items-v61-local.jsonl] [--tag x]
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import replay_v6 as rv  # noqa: E402
from score import CACHE, OUT, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402
from variants_v62 import _norm, with_shell_label  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context import shell  # noqa: E402

# `[main 1a2b3c4] msg`, `[detached HEAD 1a2b3c4] msg`, `[main (root-commit) 1a2b3c4] msg`
COMMITTED = re.compile(r"^\[(?:[^\]\n]*\s)?([0-9a-f]{7,40})\]\s", re.M)
# `git log --oneline` after a `git commit -q`
ONELINE = re.compile(r"^([0-9a-f]{7,40}) \S", re.M)
SUBJECT_MIN = 8
SLACK = 120.0
OWN = ("commit", "commit (initial)", "commit (merge)")
GIT_ENV = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
PROJECTS = Path.home() / ".claude" / "projects"
ERRORS: Counter[str] = Counter()


def _git(cwd: str, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", cwd, "-c", "core.quotepath=off", *args],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=20, check=False, env=GIT_ENV)  # fmt: skip
    except (OSError, subprocess.SubprocessError) as error:
        ERRORS[error.__class__.__name__] += 1
        return None
    if done.returncode != 0:
        ERRORS[f"git {args[0]} exit {done.returncode}"] += 1
        return None
    return done.stdout


def folder(path: str) -> str:
    """A folder as the shell named it, as the file system names it: `~`, `$HOME`,
    `%USERPROFILE%`, `$env:USERPROFILE` and a Git Bash `/c/` drive resolved."""
    p = path.strip().strip("'\"").replace("\\", "/")
    home = Path.home().as_posix()
    p = re.sub(r"^(?:~|\$HOME|\$\{HOME\}|%USERPROFILE%|\$env:USERPROFILE)(?=/|$)", home, p,
               flags=re.I)  # fmt: skip
    return re.sub(r"^/([a-zA-Z])/", r"\1:/", p) if os.name == "nt" else p


@functools.cache
def root_of(where: str) -> str | None:
    if not where or not Path(where).is_dir():
        return None
    out = _git(where, "rev-parse", "--show-toplevel")
    return out.strip() if out else None


@functools.cache
def full_sha(root: str, sha: str) -> str | None:
    out = _git(root, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    return out.strip() if out else None


@functools.cache
def reflog(root: str) -> dict[str, tuple[tuple[str, float], ...]]:
    """Per commit, (action, time) of each entry of this worktree's HEAD reflog."""
    out = _git(root, "reflog", "--date=unix", "--format=%H %gd %gs", "HEAD") or ""
    found: dict[str, list[tuple[str, float]]] = {}
    for line in out.splitlines():
        m = re.match(r"^([0-9a-f]{40}) \S*@\{(\d+)\} ([^:]*):", line)
        if m:
            found.setdefault(m.group(1), []).append((m.group(3), float(m.group(2))))
    return {k: tuple(v) for k, v in found.items()}


@functools.cache
def files_of(root: str, sha: str) -> tuple[str, ...] | None:
    out = _git(root, "show", "--no-renames", "--name-only", "--format=", sha)
    return None if out is None else tuple(x for x in out.splitlines() if x.strip())


@functools.cache
def subject_of(root: str, sha: str) -> str:
    return (_git(root, "log", "-1", "--format=%s", sha) or "").strip()


@functools.cache
def _windows(session: str) -> dict[int, tuple[float, float]]:
    """Per request of a local session, from its prompt's stamp to the next request's (the
    last request: to the transcript's last stamp)."""
    path = next(iter(PROJECTS.glob(f"*/{session}.jsonl")), None)
    if path is None:
        return {}
    entries = ep.entries_of(path)
    starts = ep.split_requests(entries).stamps
    last = max((ep._stamp(e) for e in entries if e.get("timestamp")), default=0.0)
    ends = [*starts[1:], last]
    return {
        i: (s, max(s, e)) for i, (s, e) in enumerate(zip(starts, ends, strict=True), start=1) if s
    }


def window_of(item: dict[str, Any]) -> tuple[float, float] | None:
    given = item.get("window")
    if given:
        return float(given[0]), float(given[1])
    return _windows(str(item.get("session") or "")).get(int(item.get("index") or 0))


def hashes(output: str) -> list[str]:
    return list(dict.fromkeys(COMMITTED.findall(output or "")))


def _whole_subject(subject: str, commands: list[str]) -> bool:
    """`subject` is a whole first line of a message in a commit command: a quote or a line
    break before and after it (`-m "fix: x"`, a heredoc's first line), not a piece of a longer
    one (`fix: tests` inside `fix: tests for v6`)."""
    if len(subject) < SUBJECT_MIN:
        return False
    pattern = r"(?:^|[\"'\n])" + re.escape(subject) + r"(?=[\"'\n\\]|$)"
    return any(re.search(pattern, c) for c in commands)


def committed(item: dict[str, Any]) -> tuple[set[str], Counter[str]]:
    """(files the request committed, spelt as the labels spell them; counts: `printed`
    distinct hashes considered, `found` accepted, and each reason one was refused)."""
    cwd = str(item.get("cwd") or "")
    window = window_of(item)
    commands = [t["command"] for t in item["touches"] if "git commit" in t.get("command", "")]
    out: set[str] = set()
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    for t in item["touches"]:
        if "command" not in t:
            continue
        output = t.get("output", "")
        strict = hashes(output)
        loose = [s for s in dict.fromkeys(ONELINE.findall(output or "")) if s not in strict]
        if not strict and not (commands and loose):
            continue
        base = folder(shell.view(t["command"], "", cwd)[2] or cwd)
        roots = [r for r in dict.fromkeys([root_of(base), root_of(folder(cwd))]) if r]
        for sha, own in [(s, True) for s in strict] + [(s, False) for s in loose]:
            located = next(((r, f) for r in roots if (f := full_sha(r, sha))), None)
            if located is None:
                counts["refused: not in a repository"] += own  # a log line may be anything
                continue
            root, full = located
            if full in seen:
                continue
            seen.add(full)
            counts["considered"] += 1
            reason = _refused(root, full, own, window, commands)
            files = None if reason else files_of(root, full)
            if reason or files is None:
                counts[reason or "refused: no file list"] += 1
                continue
            counts["found"] += 1
            out |= {_norm(f"{root}/{f}", cwd) for f in files}
    return out, counts


def _refused(root: str, full: str, strict: bool, window: tuple[float, float] | None,
             commands: list[str]) -> str:  # fmt: skip
    if window is None:
        return "refused: no request window"
    entries = reflog(root).get(full, ())
    lo, hi = window[0] - SLACK, window[1] + SLACK
    if not any(action in OWN and lo <= at <= hi for action, at in entries):
        kinds = {a.split(" ", 1)[0] if a.startswith("merge") else a for a, _ in entries}  # no names
        return "refused: not this worktree's commit in the window" + (
            f" ({sorted(kinds)[0]})" if kinds and not kinds & set(OWN) else "")  # fmt: skip
    if not strict and not _whole_subject(subject_of(root, full), commands):
        return "refused: log line whose subject no commit command carries"
    return ""


def with_commit_label(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[bool], Counter[str]]:
    """(items with `+commit` labels, per item whether the request committed something found,
    counts over all items)."""
    out, has, total = [], [], Counter()
    for it in items:
        files, counts = committed(it)
        total.update(counts)
        cwd = str(it.get("cwd") or "")
        labels = dict(it["labels"])
        for record in it["pool"]:
            changed = {_norm(str(c), cwd) for c in (record.changed_raw or record.changed)}
            if labels.get(record.key) == "none" and changed & files:
                labels[record.key] = "file"
        out.append({**it, "labels": labels})
        has.append(counts["found"] > 0)
    return out, has, total


def _sub(items: list[dict[str, Any]], keep: list[bool]) -> list[dict[str, Any]]:
    return [it for it, k in zip(items, keep, strict=True) if k]


def _shown_sub(shown: dict[int, list[str]], keep: list[bool]) -> dict[int, list[str]]:
    kept = [n for n, k in enumerate(keep) if k]
    return {m: shown[n] for m, n in enumerate(kept)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v61-local.jsonl"))
    parser.add_argument("--tag", default="local-v61")
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    plus_commit, has, counts = with_commit_label(items)
    plus_shell = with_shell_label(items)
    shell_and_commit = with_commit_label(plus_shell)[0]
    result: dict[str, Any] = {"requests": len(items), "committing": sum(has),
                              "commits": dict(counts), "git_errors": dict(ERRORS)}  # fmt: skip
    for arm, on in (("v5", False), ("v6.2", True)):
        with tempfile.TemporaryDirectory() as tmp:
            shown, _, by_tool = rv.touch_replay(items, Path(tmp), on)
        via = [(n, k) for n, d in by_tool.items() for k, t in d.items() if t == "Bash"]
        row: dict[str, Any] = {
            "given_by_shell": len(via),
            "given_by_shell (committing)": sum(has[n] for n, _ in via),
        }
        for name, labelled in (
            ("sealed", items),
            ("+commit", plus_commit),
            ("+shell", plus_shell),
            ("+shell+commit", shell_and_commit),
        ):
            row[name] = metrics(labelled, shown)["all/any"]
            row[f"{name} (committing)"] = metrics(_sub(labelled, has),
                                                  _shown_sub(shown, has))["all/any"]  # fmt: skip
            row[f"{name}: related shell gives (committing)"] = sum(
                labelled[n]["labels"][k] != "none" for n, k in via if has[n]
            )
        result[arm] = row
    target = OUT / f"commit-label-{args.tag}.json"
    target.write_text(json.dumps(result, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
