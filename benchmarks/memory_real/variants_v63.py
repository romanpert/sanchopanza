"""v6.3 candidates on what a shell write may give (development, seen data; v6.2's reads stay off).

On the maintainer's sessions 56 of v6.2's 152 shell gives were of shared notes under `~/.claude`
(`context/errors.md`, auto-memory, ADRs), 54 of them unrelated by the sealed label, and of the
59 gives in requests that commit, 20 were of files outside any repository and 15 of ignored
ones (`commit_label_diag.py`). Candidates, each a filter on `shell.written` for the touch only
(the tree's claims are untouched):

- `append`: a file the command only appends to (`>>`, `tee -a`, `Add-Content`, `Out-File
  -Append`, `open(..., "a")`) gives nothing: an append does not look at what is there.
- `repo`: only a file inside the session's git working tree gives.
- `both`.

    python benchmarks/memory_real/variants_v63.py local [b2]
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import commit_label as cl  # noqa: E402
import replay_v6 as rv  # noqa: E402
from score import CACHE, OUT, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402
from variants_v62 import with_shell_label  # noqa: E402

from sanchopanza.context import shell  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

VARIANTS = ("v6.2", "append", "repo", "both")


def _occurrences(command: str, path: str) -> list[int]:
    pattern = r"(?<![\w./\\-])" + re.escape(path) + r"(?![\w./\\-])"
    return [m.start() for m in re.finditer(pattern, command)]


_APPEND_BEFORE = re.compile(
    r"(?:(?<![>\d&|])>>\s*['\"]?|\btee\s+(?:-\w+\s+)*-a\s+(?:-\w+\s+)*['\"]?|"
    r"\bAdd-Content\s+(?:-(?:Path|LiteralPath)\s+)?['\"]?)$",
    re.I,
)
_PY_OPEN_BEFORE = re.compile(r"\bopen\(\s*[rbuf]?['\"]$")
_PY_APPEND_AFTER = re.compile(r"['\"]\s*,\s*(?:mode\s*=\s*)?['\"]a[bt+]?['\"]")
_OUT_FILE_BEFORE = re.compile(r"\bOut-File\s+(?:-(?:File)?Path\s+)?['\"]?$", re.I)
_OUT_FILE_APPEND = re.compile(r"[^|;\n]{0,400}-Append\b", re.I)


def appended(command: str, path: str) -> bool:
    """Every place `command` names `path` is directly an append to it (review of 2026-10-01:
    an append elsewhere in the command, or a read of the file, never makes a write an append):
    `>> path`, `tee -a path`, `Add-Content path`, `Out-File path ... -Append`, or `open('path',
    'a')`. Anything else, a read included, keeps the write (the give)."""
    at = _occurrences(command, path)
    if not at:
        return False
    for start in at:
        before = command[max(0, start - 80) : start]
        after = command[start + len(path) :]
        if _APPEND_BEFORE.search(before):
            continue
        if _PY_OPEN_BEFORE.search(before) and _PY_APPEND_AFTER.match(after):
            continue
        if _OUT_FILE_BEFORE.search(before) and _OUT_FILE_APPEND.match(after):
            continue
        return False
    return True


def _inside_repo(raw: str, cwd: str, base: str) -> bool:
    root = cl.root_of(cl.folder(cwd)) if cwd else None
    if root is None:
        return True  # no repository: nothing to filter by
    p = cl.folder(raw)
    full = p if (p.startswith("/") or p[1:2] == ":") else f"{cl.folder(base).rstrip('/')}/{p}"
    norm = mh._norm(full)
    return norm == mh._norm(root) or norm.startswith(mh._norm(root).rstrip("/") + "/")


@contextlib.contextmanager
def variant(name: str) -> Iterator[None]:
    """Filter what a shell command writes, for the touch only, while replaying."""
    original_written, original_touch = mh.shell_written, mh.touch
    current = {"cwd": "", "base": ""}

    def touch(event: Any) -> Any:
        data = event.get("tool_input") or {}
        cwd = str(event.get("cwd") or "")
        command = data.get("command") if isinstance(data, dict) else None
        base = shell.view(command, "", cwd)[2] if isinstance(command, str) else cwd
        current.update(cwd=cwd, base=base or cwd)
        return original_touch(event)

    def written(command: Any) -> list[str]:
        out = original_written(command)
        if name in ("append", "both") and isinstance(command, str):
            out = [p for p in out if not appended(command, p)]
        if name in ("repo", "both"):
            out = [p for p in out if _inside_repo(p, current["cwd"], current["base"])]
        return out

    if name != "v6.2":
        mh.shell_written, mh.touch = written, touch
    try:
        yield
    finally:
        mh.shell_written, mh.touch = original_written, original_touch


def local(items_path: Path) -> dict[str, Any]:
    items = load(items_path)
    plus_shell = with_shell_label(items)
    plus_commit, has, _ = cl.with_commit_label(items)
    rows: dict[str, Any] = {"requests": len(items)}
    for name in VARIANTS:
        with variant(name), tempfile.TemporaryDirectory() as tmp:
            shown, chars, by_tool = rv.touch_replay(items, Path(tmp), True)
        via = [(n, k) for n, d in by_tool.items() for k, t in d.items() if t == "Bash"]
        rows[name] = {
            "sealed": metrics(items, shown)["all/any"],
            "+commit": metrics(plus_commit, shown)["all/any"],
            "+shell": metrics(plus_shell, shown)["all/any"],
            "chars_per_request": round(sum(chars.values()) / max(1, len(items))),
            "shell_gives": len(via),
            "shell_gives_in_committing": sum(has[n] for n, _ in via),
            "of_those_committed": sum(
                plus_commit[n]["labels"][k] != "none" for n, k in via if has[n]
            ),
        }
        print(name, json.dumps(rows[name]), flush=True)
    return rows


def b2() -> dict[str, Any]:
    """B2's 67 fresh requests (post hoc, truth from the run's patches): recorded once with the
    tree, scored under each variant."""
    import os

    import v6_chain as vc
    import v6_chain_real as vr

    for name in ("SANCHOPANZA_MEMORY_SELECT", "SANCHOPANZA_PROVIDER", "TYPESAFE_API_KEY"):
        os.environ.pop(name, None)
    spec = "pydantic__pydantic-long40-1/{}"
    arms = (("N", 26, 40), ("S", 15, 40), ("Sm", 15, 40))
    rows: dict[str, Any] = {}
    done: list[Any] = []
    with tempfile.TemporaryDirectory() as tmp:
        for arm_name, lo, hi in arms:
            arm = vc.RUNS / spec.format(arm_name)
            chain = vc.chain(arm)
            chain = {**chain, "requests": [r for r in chain["requests"] if r["i"] <= hi],
                     "score": (lo, hi)}  # fmt: skip
            done.append((chain, vr.record_chain(arm, chain, Path(tmp) / arm_name, True)))
        for name in VARIANTS:
            with variant(name):
                rows[name] = vr.score(done, bash=True)
            print(name, json.dumps(rows[name]), flush=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    sets = argv if argv is not None else sys.argv[1:]
    out: dict[str, Any] = {}
    if "local" in sets:
        out["local"] = local(CACHE / "items-v61-local.jsonl")
    if "b2" in sets:
        out["b2"] = b2()
    (OUT / "variants-v63.json").write_text(json.dumps(out, indent=1), encoding="utf-8",
                                           newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
