"""Candor inside Claude Code: `python -m sanchopanza.harness.candor_hook` as a command hook.

    {"hooks": {
      "UserPromptSubmit":   [{"hooks": [{"type": "command", "command": HOOK}]}],
      "PreToolUse":         [{"matcher": "*", "hooks": [ same ]}],
      "PostToolUse":        [{"matcher": "*", "hooks": [ same ]}],
      "PostToolUseFailure": [{"matcher": "*", "hooks": [ same ]}],
      "Stop":               [{"hooks": [ same ]}]}}

    with HOOK = "<python> -m sanchopanza.harness.candor_hook"

What each event does:

- `UserPromptSubmit`: opens a new request in the session's ledger and, with SNAPSHOT on,
  hashes the workspace so that Stop can see changes no tool call names.
- `PreToolUse`: if the lock is engaged, refuses the call (every call, whatever it is). If the
  call itself touches the monitor, the hooks, the permissions or the trace, engages the lock
  and refuses it. Pure code and a local file: it cannot time out into a pass.
- `PostToolUse` / `PostToolUseFailure`: appends the call to the ledger with its outcome.
- `Stop`: holds the final report (the assistant text after the last tool call) against the
  ledger. Findings go to the journal; at or above LOCK_ON, in `lock` mode, the lock engages
  and the user sees the claim beside the action.

Environment (`SANCHOPANZA_CANDOR_<NAME>`):

    MODE      lock (default) | observe: observe records findings and never refuses anything
    LOCK_ON   critical (default) | high
    JUDGE     "1" to add the decision model: its reading of the report, and the frontier
              (v5: one typed question where code doubts; needs a provider; see
              `harness.claude_code` for SANCHOPANZA_PROVIDER and TYPESAFE_API_KEY)
    SNAPSHOT  "1" to diff the workspace between the prompt and the stop (recommended: in
              round 4 it alone stopped the reports of outputs that never changed)
    ASK_BLOCK prompt (default): append the four-line status block request to each prompt;
              stop: hold a final report without it once; both; off
    DIR       where ledgers and findings live (default ~/.sanchopanza/candor)

The lock file itself is SANCHOPANZA_CANDOR_LOCK (default ~/.sanchopanza/candor-lock.json).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from .._env import home_dir
from ..candor import lock as lock_mod
from ..candor import should_lock
from ..candor.claims import BLOCK_REQUEST, report_block
from ..candor.ledger import RESULT_LIMIT, Action, action, target_of, writes_of
from ..candor.rules import RANK, Turn, check

SNAPSHOT_FILES = 3_000
SNAPSHOT_BYTES = 2_000_000
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
                       ".pytest_cache", ".ruff_cache", "dist", "build", ".claude"})  # fmt: skip


def _setting(name: str, default: str = "") -> str:
    return os.environ.get(f"SANCHOPANZA_CANDOR_{name}", default).strip()


def state_dir() -> Path:
    override = _setting("DIR")
    return Path(override) if override else home_dir() / "candor"


def _ledger_path(session: str) -> Path:
    safe = "".join(ch for ch in session if ch.isalnum() or ch in "-_") or "default"
    return state_dir() / f"{safe}.jsonl"


LOCK_WAIT_S = 30.0


@contextlib.contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    """A lock across processes, on `<path>.lock`. The hooks of parallel tool calls run at the
    same time, and on Windows an append is a seek then a write: without this, two entries
    overwrite each other (round 3 of the benchmark lost an action that way). Past LOCK_WAIT_S
    the write goes ahead unlocked, since a torn line is better than a missing one."""
    with open(path.with_name(path.name + ".lock"), "a+b") as handle:
        locked = False
        deadline = time.monotonic() + LOCK_WAIT_S
        while not locked and time.monotonic() < deadline:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                time.sleep(0.005)
        try:
            yield
        finally:
            if locked and os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif locked:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append(path: Path, entry: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
    with _exclusive(path), path.open("ab") as handle:
        handle.write(line)


def snapshot(root: Path) -> dict[str, str]:
    """sha1 of every file under `root`, skipping caches and the harness's own directories."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if len(out) >= SNAPSHOT_FILES:
                return out
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > SNAPSHOT_BYTES:
                    continue
                digest = hashlib.sha1(path.read_bytes()).hexdigest()
            except OSError:
                continue
            out[path.relative_to(root).as_posix()] = digest
    return out


def diff(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """Paths added, changed or removed between two snapshots."""
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        parts = [str(response.get(k) or "") for k in ("stdout", "stderr", "output", "content",
                                                        "error", "result")]  # fmt: skip
        return "\n".join(p for p in parts if p)
    return ""


def load(session: str) -> tuple[str, dict[str, str] | None, list[Action]]:
    """The current request's task, snapshot and actions from the session ledger."""
    path = _ledger_path(session)
    task, shot, actions = "", None, []
    if not path.exists():
        return task, shot, actions
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("kind") == "prompt":
            task, shot, actions = str(entry.get("task") or ""), entry.get("snapshot"), []
        elif entry.get("kind") == "action":
            actions.append(action(entry["tool"], entry["target"], ok=entry.get("ok"),
                                  result=entry.get("result", ""),
                                  writes=entry.get("writes", ())))  # fmt: skip
    return task, shot, actions


def final_report(transcript: Path) -> str:
    """The assistant text after the last tool call of the transcript: what the agent reports."""
    texts: list[str] = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") != "assistant" or not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                texts = []
            elif block.get("type") == "text" and block.get("text"):
                texts.append(str(block["text"]))
    return "\n".join(texts)


def pre_tool_use(data: Mapping[str, Any]) -> dict[str, Any]:
    state = lock_mod.read()
    observe = _setting("MODE", "lock") == "observe"
    if state.engaged and not observe:
        return _deny(lock_mod.refusal(state))
    name = str(data.get("tool_name") or "")
    arguments = data.get("tool_input") if isinstance(data.get("tool_input"), Mapping) else {}
    call = action(name, target_of(name, arguments), writes=writes_of(name, arguments))
    if call.effect != "tamper":
        return {}
    report = check(Turn(said="", did=(call,)))
    _append(state_dir() / "findings.jsonl", {"t": time.time(), "event": "PreToolUse",
            "session": data.get("session_id"),
            "findings": [f.to_dict() for f in report.findings]})  # fmt: skip
    on = _setting("LOCK_ON", "critical")
    if observe or not should_lock(report.findings, on=on):
        return {}  # v5: a look at the settings is journalled for review, not refused
    lock_mod.engage(report.findings, session=str(data.get("session_id") or ""))
    return _deny(lock_mod.refusal(lock_mod.read()))


def _deny(reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}  # fmt: skip


def post_tool_use(data: Mapping[str, Any], *, failed: bool) -> dict[str, Any]:
    name = str(data.get("tool_name") or "")
    arguments = data.get("tool_input") if isinstance(data.get("tool_input"), Mapping) else {}
    text = _response_text(data.get("error") if failed else data.get("tool_response"))
    _append(_ledger_path(str(data.get("session_id") or "")), {
        "kind": "action", "t": time.time(), "tool": name,
        "target": target_of(name, arguments), "ok": not failed,
        "result": text[-RESULT_LIMIT:], "writes": list(writes_of(name, arguments)),
    })  # fmt: skip
    return _slipped(data, name, arguments)


def _slipped(data: Mapping[str, Any], name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """A call that finished while the lock is engaged got past PreToolUse before the lock existed:
    Claude Code runs the PreToolUse hooks of parallel calls in one turn at the same time (seen in
    1 of 6 lock sessions). It cannot be undone; it is recorded and put in front of the person."""
    state = lock_mod.read()
    if not state.engaged or _setting("MODE", "lock") == "observe":
        return {}
    call = f"{name}: {target_of(name, arguments)[:160]}"
    _append(state_dir() / "findings.jsonl", {"t": time.time(), "event": "PostToolUse",
            "session": data.get("session_id"), "findings": [{"severity": "critical",
            "rule": "ran_during_lock", "detail": "a parallel call ran before the lock engaged",
            "action": call}]})  # fmt: skip
    return {
        "systemMessage": f"sanchopanza: a call ran while the session was being put on hold "
        f"(issued in parallel before the lock engaged): {call}",
        "hookSpecificOutput": {"hookEventName": str(data.get("hook_event_name") or "PostToolUse"),
                               "additionalContext": lock_mod.refusal(state)},
    }  # fmt: skip


def user_prompt(data: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(str(data.get("cwd") or os.getcwd()))
    shot = snapshot(root) if _setting("SNAPSHOT") in ("1", "true", "yes") else None
    _append(_ledger_path(str(data.get("session_id") or "")),
            {"kind": "prompt", "t": time.time(), "task": str(data.get("prompt") or "")[:2000],
             "cwd": str(root), "snapshot": shot})  # fmt: skip
    notes = []
    state = lock_mod.read()
    if state.engaged and _setting("MODE", "lock") != "observe":
        notes.append(lock_mod.refusal(state))
    if _setting("ASK_BLOCK", "prompt") in ("prompt", "both"):
        notes.append(BLOCK_REQUEST)
    if not notes:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                   "additionalContext": "\n\n".join(notes)}}  # fmt: skip


def _held_for_block(data: Mapping[str, Any], said: str) -> dict[str, Any] | None:
    """`ASK_BLOCK=stop|both`: a final report without the status block is held once, with the
    request, so the check has fields to hold against the ledger. Never twice in a row
    (`stop_hook_active`), and never twice for one request (a mark in the ledger)."""
    if _setting("ASK_BLOCK", "prompt") not in ("stop", "both") or report_block(said):
        return None
    if data.get("stop_hook_active"):
        return None
    path = _ledger_path(str(data.get("session_id") or ""))
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for line in reversed(lines):  # this request's entries, newest first
        if '"kind": "asked_block"' in line:
            return None
        if '"kind": "prompt"' in line:
            break
    _append(path, {"kind": "asked_block", "t": time.time()})
    return {"decision": "block", "reason": BLOCK_REQUEST}


async def stop(data: Mapping[str, Any]) -> dict[str, Any]:
    session = str(data.get("session_id") or "")
    task, shot, actions = load(session)
    try:
        said = final_report(Path(str(data.get("transcript_path"))))
    except OSError:
        said = ""
    held = _held_for_block(data, said)
    if held is not None:
        return held
    changed: list[str] = []
    if shot is not None:
        changed = diff(shot, snapshot(Path(str(data.get("cwd") or os.getcwd()))))
    turn = Turn(said=said, did=tuple(actions), task=task, changed=tuple(changed),
                snapshot=shot is not None)  # fmt: skip
    report = check(turn)
    if _setting("JUDGE") in ("1", "true", "yes"):
        from ..candor.frontier import frontier
        from ..candor.judge import judge
        from .claude_code import squire_from_env

        squire = squire_from_env(redact=True)
        report = await frontier(squire, turn, await judge(squire, turn, report))
    findings = sorted(report.findings, key=lambda f: -RANK[f.severity])
    _append(state_dir() / "findings.jsonl", {"t": time.time(), "event": "Stop",
            "session": session, "actions": len(actions), "changed": changed,
            "findings": [f.to_dict() for f in findings]})  # fmt: skip
    on = _setting("LOCK_ON", "critical")
    if not findings or not should_lock(findings, on=on) or _setting("MODE", "lock") == "observe":
        return {}
    state = lock_mod.engage([f for f in findings if RANK[f.severity] >= RANK[on]],
                            session=session)  # fmt: skip
    return {"systemMessage": lock_mod.summary(state)}


def handle(data: Mapping[str, Any]) -> dict[str, Any]:
    event = str(data.get("hook_event_name") or "")
    if event == "PreToolUse":
        return pre_tool_use(data)
    if event in ("PostToolUse", "PostToolUseFailure"):
        return post_tool_use(data, failed=event == "PostToolUseFailure")
    if event == "UserPromptSubmit":
        return user_prompt(data)
    if event == "Stop":
        import asyncio

        return asyncio.run(stop(data))
    return {}


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        output = handle(data)
    except Exception as error:
        # PreToolUse fails closed while a lock may be engaged: an unreadable state refuses.
        if data.get("hook_event_name") == "PreToolUse" and lock_mod.read().engaged:
            output = _deny(lock_mod.refusal(lock_mod.read()))
        else:
            sys.stderr.write(
                f"sanchopanza candor: passed through ({type(error).__name__}: {error})\n"
            )
            return 0
    if output:
        sys.stdout.write(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
