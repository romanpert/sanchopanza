"""The free half of pruning: what code can decide about a tool result, code decides.

Each call gets one verdict, in this order; the first rule that applies wins:

1. `recent`: the call or its result is within the last `keep_recent` messages. Kept: it is
   what the model is working on.
2. `already_pruned`: the result is a stub a previous compaction left. Kept as it is.
3. `small`: the result is under `small` characters. Kept: a stub would free almost nothing.
4. Errors: an error whose same tool and input succeeded later is stubbed (`error_retried`);
   any other error is kept (`error`), since what went wrong is what the model must not repeat.
5. `read_superseded`: a `Read` of a file that is read again later over the same range, or
   edited or written later. What it showed is stale or repeated. Stubbed.
6. `command_repeated`: a `Bash` command run again later, character for character. The later
   output is the current one. Stubbed.
7. Everything else is `ask`: the decider judges it.

A stub is reversible (the full text goes to the archive and the stub names the file), which
is why rules 5 and 6 can be this blunt. Nothing here reads the model's text: a rule that
guessed at meaning would be a worse decider, not a rule.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .transcript import Call

Action = Literal["keep", "stub", "ask"]

STUB_PREFIX = "[sanchopanza pruned this "
READ_TOOLS = frozenset({"Read"})
WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
SHELL_TOOLS = frozenset({"Bash"})
# Failures a tool reports in its text without setting is_error. Anchored at the start, so a
# file that merely mentions "error" is not one.
FAILURE = re.compile(
    r"^\s*(?:<tool_use_error>|error\b|Error\b|Exit code [1-9]|fatal:|Traceback \(most recent)",
)


@dataclass(frozen=True, slots=True)
class Verdict:
    action: Action
    reason: str


def failed(call: Call) -> bool:
    """The tool said it failed, by flag or by the way its output starts."""
    return call.is_error or bool(FAILURE.match(call.result))


def _path(call: Call) -> str:
    raw = call.input.get("file_path") or call.input.get("notebook_path") or ""
    return str(raw).replace("\\", "/").strip()


def _range(call: Call) -> tuple[Any, Any]:
    return call.input.get("offset"), call.input.get("limit")


def _covers(later: Call, earlier: Call) -> bool:
    """A later read shows at least what the earlier one showed: whole file, or same range."""
    return _range(later) == (None, None) or _range(later) == _range(earlier)


def _same_call(a: Call, b: Call) -> bool:
    return a.tool == b.tool and json.dumps(a.input, sort_keys=True, default=str) == json.dumps(
        b.input, sort_keys=True, default=str
    )


def _superseded_read(call: Call, later: Sequence[Call]) -> bool:
    path = _path(call)
    if not path:
        return False
    for other in later:
        if _path(other) != path:
            continue
        if other.tool in WRITE_TOOLS and not failed(other):
            return True
        if other.tool in READ_TOOLS and not failed(other) and _covers(other, call):
            return True
    return False


def _repeated_command(call: Call, later: Sequence[Call]) -> bool:
    command = str(call.input.get("command") or "").strip()
    return bool(command) and any(
        o.tool == call.tool and str(o.input.get("command") or "").strip() == command for o in later
    )


def _verdict(call: Call, later: Sequence[Call], recent_from: int, small: int) -> Verdict:
    if call.use_msg >= recent_from or call.result_msg >= recent_from:
        return Verdict("keep", "recent")
    if call.result.startswith(STUB_PREFIX):
        return Verdict("keep", "already_pruned")
    if call.chars < small:
        return Verdict("keep", "small")
    if failed(call):
        retried = any(_same_call(call, o) and not failed(o) for o in later)
        return Verdict("stub", "error_retried") if retried else Verdict("keep", "error")
    if call.tool in READ_TOOLS and _superseded_read(call, later):
        return Verdict("stub", "read_superseded")
    if call.tool in SHELL_TOOLS and _repeated_command(call, later):
        return Verdict("stub", "command_repeated")
    return Verdict("ask", "undecided")


def triage_rules(
    messages: Sequence[Mapping[str, Any]],
    calls: Sequence[Call],
    *,
    keep_recent: int = 6,
    small: int = 400,
) -> dict[str, Verdict]:
    """One verdict per call id. Pure: same messages and calls, same verdicts."""
    if keep_recent < 0 or small < 0:
        raise ValueError("keep_recent and small must be >= 0")
    recent_from = len(messages) - keep_recent
    ordered = sorted(calls, key=lambda c: (c.use_msg, c.result_msg))
    return {
        call.id: _verdict(call, ordered[i + 1 :], recent_from, small)
        for i, call in enumerate(ordered)
    }
