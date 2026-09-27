"""Passive recorder hook: appends the raw hook input to $RECORDER_OUT. Prints nothing.

An instrument of the e2e run, not part of sanchopanza. It lets the report show exactly what
Claude Code handed each hook, and lets the latency replay feed the same inputs back.
"""

from __future__ import annotations

import json
import os
import sys
import time


def main() -> int:
    raw = sys.stdin.read()
    out = os.environ.get("RECORDER_OUT")
    if not out:
        return 0
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {"unparsed": raw[:2000]}
    with open(out, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"t": time.time(), "input": data}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
