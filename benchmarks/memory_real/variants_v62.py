"""v6.2 candidates after amendment 5 (not confirmed: on the maintainer's sessions, reads through
the shell gave 196 unrelated records of 258). The product's v6.1 touch, with what a shell READ
may give changed (what a shell command writes keeps the edit rule in all of them). Free, local.

    python benchmarks/memory_real/variants_v62.py local dev held1 held2 held3 [--only=a,b]

Reads: `all` (v6.1 as shipped), `none` (m: no shell read gives anything; `none_nogate` the same
without the file-edit gate), `after_edit` (n: a
shell read gives only once the session has written through the shell), `focused` (o: only a
command that reads one named file: `cat`, `sed -n`, `head`, `tail`, `nl`, `Get-Content`).
`local` is local_v6.py's items (PowerShell replayed as PowerShell); the others build_v6.py's.

Besides the sealed label, a reported one: `+shell`, where a record is also related when the
request writes one of its files through the shell (the file-tool label cannot see that).
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

import local_v6 as lv  # noqa: E402
import replay_v6 as rv  # noqa: E402
from score import CACHE, OUT, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402
from variants_v61 import with_cwd  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context import shell  # noqa: E402
from sanchopanza.context import statements as st  # noqa: E402
from sanchopanza.harness import memory_hook as mh  # noqa: E402

READERS = frozenset({"cat", "sed", "head", "tail", "nl", "less", "more", "bat", "type",
                     "get-content", "gc"})  # fmt: skip
_AS_BASH = rv.bash_event
rv.bash_event = lambda item, transcript, touch: {
    **_AS_BASH(item, transcript, touch),
    "tool_name": touch.get("shell", "Bash"),
}


def focused(command: str, powershell: bool) -> bool:
    """One statement that prints code, a reader of one named file (`sed` only with `-n`)."""
    text = command[: shell.SCAN]
    printing = [s for s in st.split(text, "`" if powershell else "\\")
                if not s.piped and not st.silent(st.words(text, s))]  # fmt: skip
    if len(printing) != 1:
        return False
    ws = st.words(text, printing[0])
    name = st.program(ws).removesuffix(".exe")
    if name not in READERS or (name == "sed" and "-n" not in ws):
        return False
    return len(set(shell.PATH.findall(" ".join(ws[1:])))) == 1


@contextlib.contextmanager
def reads(mode: str) -> Iterator[None]:
    """Patch what a shell read may give; the edit rule for shell writes is untouched."""
    original_view, original_touch = mh.bash_view, mh.touch
    current = {"key": ("", "")}
    wrote: set[tuple[str, str]] = set()

    def view(command: Any, response: Any, cwd: str, powershell: bool = False) -> Any:
        raws, seen, base = original_view(command, response, cwd, powershell)
        keep = (mode == "all" or (mode == "after_edit" and current["key"] in wrote)
                or (mode == "focused" and isinstance(command, str)
                    and focused(command, powershell)))  # fmt: skip
        return (raws, seen, base) if keep else ([], seen, base)

    def touch(event: Any) -> Any:
        current["key"] = (str(event.get("session_id")), str(event.get("transcript_path")))
        out = original_touch(event)
        data = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
        if event.get("tool_name") in mh.SHELL_TOOLS and mh.shell_written(data.get("command")):
            wrote.add(current["key"])
        return out

    # v6.1's gate (none of the shell touch once a session edits with a file tool) was removed
    # in v6.2; `_nogate` modes measured it off while it was in the product (see the README).
    gate = getattr(mh, "SHELL_UNTIL_FILE_EDIT", None)
    shell_reads = getattr(mh, "SHELL_READS", True)
    mh.bash_view, rv.mh.touch = view, touch
    if gate is not None:
        mh.SHELL_UNTIL_FILE_EDIT = gate and not mode.endswith("_nogate")
    mh.SHELL_READS = True  # which reads give is the view's choice above
    try:
        yield
    finally:
        mh.bash_view, rv.mh.touch = original_view, original_touch
        mh.SHELL_READS = shell_reads
        if gate is not None:
            mh.SHELL_UNTIL_FILE_EDIT = gate


def _norm(path: str, cwd: str, base: str = "") -> str:
    """A path as the session's records spell it: resolved against the folder the command ran
    in (`cd DIR &&`, as the hook resolves it), then relative to where the session started."""
    path = path.replace("\\", "/")
    base = (base or cwd).replace("\\", "/").rstrip("/")
    if base and not (path.startswith("/") or re.match(r"^[A-Za-z]:", path)):
        path = f"{base}/{path}"
    path = re.sub(r"^/([a-zA-Z])/", r"\1:/", path)
    rel = ep.relative(path, cwd.replace("\\", "/")) if cwd else path
    return rel.replace("\\", "/").lstrip("./").casefold()


def with_shell_label(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Items whose `none` labels become `file` when the request writes, through the shell, a
    file the record changed (reported only; the sealed label sees file tools alone)."""
    out = []
    for it in items:
        cwd = it.get("cwd", "")
        written = {_norm(p, cwd, shell.view(t["command"], "", cwd)[2])
                   for t in it["touches"] if "command" in t
                   for p in mh.shell_written(t["command"])}  # fmt: skip
        labels = dict(it["labels"])
        for record in it["pool"]:
            changed = {_norm(str(c), cwd) for c in (record.changed_raw or record.changed)}
            if labels.get(record.key) == "none" and changed & written:
                labels[record.key] = "file"
        out.append({**it, "labels": labels})
    return out


def row(items: list[dict[str, Any]], shell_label: list[dict[str, Any]], bash: bool) -> Any:
    with tempfile.TemporaryDirectory() as tmp:
        shown, chars, by_tool = rv.touch_replay(items, Path(tmp), bash)
    m, plus = metrics(items, shown), metrics(shell_label, shown)
    via = [(n, k) for n, d in by_tool.items() for k, t in d.items() if t == "Bash"]
    good = sum(items[n]["labels"][k] != "none" for n, k in via)
    good_plus = sum(shell_label[n]["labels"][k] != "none" for n, k in via)
    return {**m, "+shell/all/any": plus["all/any"],
            "chars_per_request": round(sum(chars.values()) / max(1, len(items))),
            "given_by_shell": len(via), "related_given_by_shell": good,
            "related_given_by_shell_+shell": good_plus}  # fmt: skip


def items_of(name: str) -> list[dict[str, Any]]:
    return load(lv.ITEMS) if name == "local" else with_cwd(load(CACHE / f"items-v6-{name}.jsonl"))


def main() -> int:
    only = [a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--only=")]
    modes = only[0] if only else ["all", "none", "after_edit", "focused"]
    results: dict[str, Any] = {}
    for name in [a for a in sys.argv[1:] if not a.startswith("--")]:
        items = items_of(name)
        plus = with_shell_label(items)
        rows = {"v5": row(items, plus, False)}
        for mode in modes:
            with reads(mode):
                rows[mode] = row(items, plus, True)
        results[name] = rows
        for label, r in rows.items():
            a, p = r["all/any"], r["+shell/all/any"]
            print(name, label.ljust(10), f"R {a['recall']} P {a['precision']} N {a['noise']}",
                  f"| +shell P {p['precision']} N {p['noise']}",
                  f"| shell {r['given_by_shell']} ({r['related_given_by_shell']}"
                  f"/{r['related_given_by_shell_+shell']})", flush=True)  # fmt: skip
    suffix = "-".join(a for a in sys.argv[1:] if not a.startswith("--"))
    (OUT / f"variants-v62-{suffix}.json").write_text(json.dumps(results, indent=1),
                                                     encoding="utf-8", newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
