"""`sanchopanza hook`, with every provider answer written down. An instrument of this run.

It runs `sanchopanza.harness.claude_code.main`, the function the `sanchopanza hook` command
calls (`cli._hook`), with one change: the decider built from the environment is wrapped in
`RecordingDecider`, which passes every call through unchanged and appends the answer to
`$RECORD_OUT`. That recording is what lets `tests/test_claude_code_broad.py` replay every
hook-level verdict with no key and no network. Nothing else differs from the command; the
latency sample in `prereg.md` is taken with the installed `sanchopanza.exe hook` itself.
"""

from __future__ import annotations

import os
import sys

from sanchopanza.harness import claude_code
from sanchopanza.providers.recorded import RecordingDecider

_build = claude_code.decider_from_env


def _recording(env: dict[str, str] | None = None):
    decider = _build(env)
    out = os.environ.get("RECORD_OUT")
    return RecordingDecider(decider, out) if out else decider


claude_code.decider_from_env = _recording

if __name__ == "__main__":
    sys.exit(claude_code.main())
