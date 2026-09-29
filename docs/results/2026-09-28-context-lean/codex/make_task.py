"""Write the tiny task folder the Codex check runs in. Free: no model, no network.

    python make_task.py DIR

The folder holds one script, `build_log.py`, that prints a ~10 KB build log (exit 0) with
exactly one line the follow-up question needs: `RELEASE_TOKEN=RT-<8 hex>`. The token is new
on every run, so an agent that re-runs the tool instead of recalling the first output gives a
different value and the check sees it. `task.json` records the log's exact size so the check
can tell whether Codex cut the output before the hook saw it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LINES_BEFORE = 115
LINES_AFTER = 115
NEEDLE_KEY = "RELEASE_TOKEN"
TOKEN_CHARS = len("RT-") + 8

SCRIPT = f'''"""Prints a build log. One line matters; the token changes every run."""
import secrets

before = {LINES_BEFORE}
after = {LINES_AFTER}


def at(hour, i):
    return f"2026-09-28T{{hour}}:{{i // 60:02d}}:{{i % 60:02d}}"


lines = [at(10, i) + f" INFO compile unit {{i:03d}} ok" for i in range(before)]
lines.append("{NEEDLE_KEY}=RT-" + secrets.token_hex(4))
lines += [at(11, i) + f" INFO link step {{i:03d}} ok" for i in range(after)]
lines.append("BUILD OK")
print("\\n".join(lines))
'''


def expected_chars() -> int:
    """Characters `build_log.py` prints, newline included, whatever the token."""
    before = [
        f"2026-09-28T10:{i // 60:02d}:{i % 60:02d} INFO compile unit {i:03d} ok"
        for i in range(LINES_BEFORE)
    ]
    after = [
        f"2026-09-28T11:{i // 60:02d}:{i % 60:02d} INFO link step {i:03d} ok"
        for i in range(LINES_AFTER)
    ]
    needle = f"{NEEDLE_KEY}=" + "x" * TOKEN_CHARS
    return len("\n".join([*before, needle, *after, "BUILD OK"])) + 1


def make(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "build_log.py").write_text(SCRIPT, encoding="utf-8")
    # Codex's sandboxed PowerShell has no `python` on PATH and mangles a quoted interpreter
    # path (first two checks): a launcher the model runs as `.\build_log.cmd`.
    launcher = f'@"{Path(sys.executable)}" "%~dp0build_log.py"\r\n'
    (directory / "build_log.cmd").write_text(launcher, encoding="utf-8")
    manifest = {
        "script": "build_log.py",
        "needle_key": NEEDLE_KEY,
        "needle_pattern": NEEDLE_KEY + r"=(RT-[0-9a-f]{8})",
        "expected_chars": expected_chars(),
        "expected_chars_crlf": expected_chars() + LINES_BEFORE + LINES_AFTER + 2,
        "lines": LINES_BEFORE + LINES_AFTER + 2,
    }
    (directory / "task.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stderr.write("usage: python make_task.py DIR\n")
        raise SystemExit(2)
    sys.stdout.write(json.dumps(make(Path(sys.argv[1])), indent=2) + "\n")
