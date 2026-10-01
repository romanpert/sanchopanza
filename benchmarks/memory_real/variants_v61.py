"""v6.1 variants of the shell touch against v5 (no shell) and v6, replayed through
`memory_hook.touch` on items of build_v6.py (replay_v6.touch_replay). Free, local.

    python benchmarks/memory_real/variants_v61.py dev held1 held2 held3

Variants: `v6.0` (the view as v6 shipped it), `v6.1` (the product's `shell.view`: no output of a
history command, no message bodies), and `v6.1+2` (v6.1, and a shell read needs two of a
record's lines in view). The first version of v6.1 also had each rule alone; see the README.
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

import build_v6  # noqa: E402
import replay_v6 as rv  # noqa: E402
from score import CACHE, OUT, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context import shell  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402


def with_cwd(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Items with the folder their session started in, as the hook keeps it in its state.
    build_v6.py's items had none (found 2026-10-01, after amendment 4): a shell command naming
    a file by its absolute path, without a `cd` first, never matched a record."""
    return [{**it, "cwd": it.get("cwd") or build_v6.cwd_of(it["session"])} for it in items]


def view_v60(
    command: Any, response: Any, cwd: str, powershell: bool = False
) -> tuple[list[str], set[str], str]:
    """shell.view as v6 shipped it (894f650), before v6.1."""
    if not isinstance(command, str) or not command.strip():
        return [], set(), cwd
    out = response.get("stdout") if isinstance(response, dict) else response
    out = out[: shell.SCAN] if isinstance(out, str) else ""
    base = cwd
    moved = shell._CD.match(command)
    if moved:
        folder = moved.group(1).strip("\"'")
        absolute = folder.startswith(("/", "\\")) or bool(re.match(r"^[A-Za-z]:", folder))
        base = folder if absolute or not cwd else f"{cwd.rstrip('/')}/{folder}"
    own = command[: shell.SCAN]
    raws = list(dict.fromkeys([*shell.PATH.findall(own), *shell._GREP_PREFIX.findall(out)]))
    quoted = [q[1:-1] for q in shell._QUOTED.findall(own)]
    text = "\n".join([shell._LINE_PREFIX.sub("", out), *shell._TRIPLE.split(own), *quoted])
    return raws[: shell.PATHS], ep.line_prints(text), base


VIEWS = {"v6.0": view_v60, "v6.1": shell.view}


@contextlib.contextmanager
def variant(view: str, least: int, until_file: bool = False) -> Iterator[None]:
    """Patch the hook's view of a shell call, and with `least` > 1 drop a shell read's record
    with fewer of its written lines in view. With `until_file`, the shell touch gives nothing
    once the session (session id and transcript) has called a file tool."""
    original_view, original_choose, original_touch = mh.bash_view, mh.choose_touched, mh.touch
    in_shell = {"on": False}
    filed: set[tuple[str, str]] = set()

    def choose(matching: Any, tool: str, seen: set[str], *args: Any, **kwargs: Any) -> Any:
        chosen = original_choose(matching, tool, seen, *args, **kwargs)
        if not in_shell["on"] or tool != "Read" or least <= 1:
            return chosen
        return [
            e
            for e in chosen
            if len({p for _, prints in e.wrote or () for p in prints} & seen) >= least
        ]

    def touch(event: Any) -> Any:
        in_shell["on"] = event.get("tool_name") in mh.SHELL_TOOLS
        key = (str(event.get("session_id")), str(event.get("transcript_path")))
        if not in_shell["on"]:
            filed.add(key)
        elif until_file and key in filed:
            in_shell["on"] = False
            return {}
        try:
            return original_touch(event)
        finally:
            in_shell["on"] = False

    mh.bash_view, mh.choose_touched = VIEWS[view], choose
    rv.mh.touch = touch
    try:
        yield
    finally:
        mh.bash_view, mh.choose_touched, rv.mh.touch = (
            original_view,
            original_choose,
            original_touch,
        )


VARIANTS = {"v6.0": ("v6.0", 1, False), "v6.1": ("v6.1", 1, False), "v6.1+2": ("v6.1", 2, False),
            "v6.1-e": ("v6.1", 1, True)}  # fmt: skip


def row(items: list[dict[str, Any]], bash: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        shown, chars, by_tool = rv.touch_replay(items, Path(tmp), bash)
    m = metrics(items, shown)
    via = [(n, k) for n, d in by_tool.items() for k, t in d.items() if t == "Bash"]
    good = sum(items[n]["labels"][k] != "none" for n, k in via)
    return {**m, "chars_per_request": round(sum(chars.values()) / len(items)),
            "given_by_bash": len(via), "related_given_by_bash": good}  # fmt: skip


def main() -> int:
    results: dict[str, Any] = {}
    for name in sys.argv[1:]:
        items = with_cwd(load(CACHE / f"items-v6-{name}.jsonl"))
        rows = {"v5": row(items, False)}
        for label, spec in VARIANTS.items():
            with variant(*spec):
                rows[label] = row(items, True)
        results[name] = rows
        for label, r in rows.items():
            a = r["all/any"]
            print(
                name,
                label.ljust(9),
                f"R {a['recall']} P {a['precision']} N {a['noise']}",
                f"bash {r['given_by_bash']} ({r['related_given_by_bash']})",
                flush=True,
            )
    (OUT / "variants-v61.json").write_text(json.dumps(results, indent=1), encoding="utf-8",
                                           newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
