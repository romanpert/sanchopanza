"""The guard hook as the run's sessions call it: the logged, keyed wrapper around
`sanchopanza.harness.guard_hook.main`.

    python guard_wrapper.py <evidence dir> <chooser: rule|decider|keep> [keyfile]

Sets, for this process only: where the PreCompact leaves its guard (`<ev>/kept`, outside the
work copy the agent searches), the event log (`<ev>/guard-log.jsonl`), the chooser, and, for the
decider, the provider and the key read from `keyfile` (the session never carries it) with a
journal in the evidence folder. Every raw event is appended to `<ev>/guard-events.jsonl` with
its stdout, so what Claude Code received is on disk.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))


def main() -> int:
    ev = Path(sys.argv[1])
    chooser = sys.argv[2]
    raw = sys.stdin.read()
    os.environ["SANCHOPANZA_GUARD_DIR"] = str(ev / "kept")
    os.environ["SANCHOPANZA_GUARD_LOG"] = str(ev / "guard-log.jsonl")
    os.environ["SANCHOPANZA_GUARD_CHOOSER"] = chooser
    if chooser in ("decider", "keep"):
        keyfile = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        key = keyfile.read_text("utf-8").strip() if keyfile and keyfile.exists() else ""
        if key:
            os.environ["TYPESAFE_API_KEY"] = key
        os.environ["SANCHOPANZA_PROVIDER"] = "jev"
        os.environ["SANCHOPANZA_JOURNAL"] = str(ev / "journal.jsonl")
        os.environ.setdefault("SANCHOPANZA_T_MAX_USD", "0.01")  # amendment A3: per hook call
    from sanchopanza.harness import guard_hook

    out = io.StringIO()
    real_stdin, real_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(raw), out
    started = time.time()
    try:
        code = guard_hook.main()
    finally:
        sys.stdin, sys.stdout = real_stdin, real_stdout
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        event = {"unreadable": raw[:200]}
    row = {"at": round(started, 3), "seconds": round(time.time() - started, 3),
           "event": event.get("hook_event_name"), "source": event.get("source"),
           "trigger": event.get("trigger"), "tool": event.get("tool_name"),
           "stdout_chars": len(out.getvalue()), "stdout": out.getvalue()[:6000]}  # fmt: skip
    sys.stdout.write(out.getvalue())  # what Claude Code needs goes out first
    try:
        with (ev / "guard-events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as error:
        sys.stderr.write(f"guard_wrapper: event log not written: {error}\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
