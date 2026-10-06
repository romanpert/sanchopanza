"""Resuming an arm of a long chain where it stopped: the bugs whose calls already ran are never
asked again. Pure decisions over an arm's `row.json` and evidence; `long_run.resume` applies
them. Nothing here calls `claude`, an API or Jev.

- **Which arms resume.** A row that says `"partial": true` (the runner died, or was killed by
  PID, between or during calls) and a row stopped by something that passes (`limit`: the usage
  limit resets; `harness`: a STOP file the owner removes after looking; `ceiling`: it stops again
  at once unless spending is allowed). Never a finished arm, one whose own caps or wall stopped
  it (`cap`, `wall`: its budget is spent), or a set-aside one.
- **Where it resumes.** After the last call in the row; a call the dead runner left half done
  (`stream-<k>.jsonl` with no row) is settled first, as a cut call (pre-mortem 4): charged its
  cap, retried when it used no tool and left the diff as it was, otherwise a declared deviation
  and the next request (development and the gate) or the chain set aside (confirmation).
- **What the next call needs.** The session to `--resume`, the `modelUsage` the session had
  reached (`usage_after`) and the transcript requests already metered (`metered_ids`), both
  stored in every call's row.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import long_guard  # noqa: E402

RESUMES = ("limit", "harness", "ceiling")
NOT_RUN = "NOT RUN"
DIED = "cut (runner died)"
LIMITED = "error result (limit)"


def read_row(evidence: Path) -> dict[str, Any] | None:
    path = evidence / "row.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def may_resume(row: Mapping[str, Any]) -> bool:
    if row.get("partial"):
        return True
    return row.get("stopped") in RESUMES


def kept(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The calls that ran (or were charged), without the NOT RUN rows a stop appended."""
    return [dict(c) for c in row.get("calls", []) if not str(c.get("status", "")).startswith(
        NOT_RUN)]  # fmt: skip


def patch_of(evidence: Path, k: int) -> str:
    path = evidence / f"diff-{k}.patch"
    return path.read_text(encoding="utf-8") if k > 0 and path.exists() else ""


def ask_limited_again(calls: list[dict[str, Any]], evidence: Path,
                      split: str) -> list[dict[str, Any]]:  # fmt: skip
    """The last call, if the usage limit rejected it, is asked again when it did nothing (no
    tool, the diff as before); otherwise it stands as a cut call (pre-mortem 4)."""
    if not calls or calls[-1].get("status") != LIMITED:
        return calls
    last = calls[-1]
    k = int(last["request"])
    tools = int(last.get("tool_uses") or 0)
    decision = long_guard.resume_decision(tools, patch_of(evidence, k - 1), patch_of(evidence, k),
                                          split)  # fmt: skip
    return [*calls[:-1], {**last, "superseded": decision == "retry"}]


def next_request(calls: Sequence[Mapping[str, Any]]) -> int:
    """The first request not yet done: after the last call that counts (a superseded one, a dead
    call retried, is asked again)."""
    done = [int(c["request"]) for c in calls if not c.get("superseded")]
    return max(done, default=0) + 1


def session_of(calls: Sequence[Mapping[str, Any]]) -> str | None:
    return next((str(c["session"]) for c in reversed(calls) if c.get("session")), None)


def usage_of(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The session's `modelUsage` after the last call that recorded it ({} before any)."""
    return next((dict(c["usage_after"]) for c in reversed(calls) if c.get("usage_after")), {})


def seen_of(calls: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    return frozenset(i for c in calls for i in c.get("metered_ids") or [])


def dead_stream(evidence: Path, k: int, calls: Sequence[Mapping[str, Any]]) -> Path | None:
    """The stream of call `k` that a runner started and died in before writing its row: one no
    row names in its `streams`."""
    settled = {name for c in calls for name in c.get("streams") or []}
    if (evidence / f"stream-{k}-dead.jsonl").exists() and f"stream-{k}-dead.jsonl" not in settled:
        return evidence / f"stream-{k}-dead.jsonl"  # renamed, then the runner died again
    for name in (f"stream-{k}-retry.jsonl", f"stream-{k}.jsonl"):
        if (evidence / name).exists() and name not in settled:
            return evidence / name
    return None


def wall_of(stream: Path) -> float:
    """Seconds the dead call ran, as far as its stream shows (creation to last write)."""
    info = stream.stat()
    return round(max(0.0, info.st_mtime - info.st_ctime), 1)


def dead_row(k: int, ask: Mapping[str, Any], facts: Mapping[str, Any], decision: str,
             money: Mapping[str, Any], stream: Path) -> dict[str, Any]:  # fmt: skip
    """The row of a call the runner died in, charged its caps as any cut call."""
    keys = ("session", "subtype", "is_error", "init", "tools", "tool_uses", "compactions",
            "limits", "denials")  # fmt: skip
    return {"request": k, "kind": ask["kind"], "instance_id": ask["instance_id"], "exit": None,
            "wall_s": wall_of(stream), "streams": [stream.name], "status": DIED,
            "decision": decision,
            "superseded": decision == "retry", **{key: facts.get(key) for key in keys},
            **dict(money), "breaks": [],
            **({"deviation": "the runner died mid-call after tools or changes: went on"}
               if decision == "continue" else {})}  # fmt: skip
