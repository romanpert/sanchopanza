"""Hook inputs for the hook-level replay (`prereg.md`, part H), built from labelled sets.

Every case is one JSON object Claude Code would hand `sanchopanza hook` on stdin, plus the
label it is scored against. Nothing here calls anything; `hook_replay.py` feeds the cases to
the hook process.

Sets, and what a label means in each:

- `guard`      benches/safety.jsonl, point `command` (32). Per command. Written by this
               repository's author, and the code deny-list was written after seeing it: it
               covers this set by construction (`points/guard.py` says so).
- `atbench`    ATBench-Codex test split (500, Apache-2.0). Per trajectory (`is_safe`). Every
               assistant action becomes a PreToolUse input: `shell_command` as `Bash`, every
               other tool as the MCP name Claude Code would give it, `mcp__<server>__<op>`.
- `rjudge`     R-Judge at the pinned commit, only the trajectories with a shell action
               (`TerminalExecute: {...}` or a fenced bash block). Per trajectory (`label`).
- `inject-ad`  benches/agentdojo-injection.jsonl (AgentDojo v1.2.2, MIT). Per text. Each
               text is the stdout of `curl -s http://127.0.0.1:8765/<id>.html` at
               PostToolUse, the shell-fetch path of commit 5810509.
- `inject-own` benches/safety.jsonl, point `injection` (28). Per text, as above.
- `control`    the same 304 texts as the stdout of `cat pages/<id>.txt`: a command that does
               not fetch, so the installed hook must not scan it (no decision, no note).
- `stop`       this repository's AgentDojo runs of 2026-09-24 (655), label AgentDojo's
               `utility`. Each run becomes a Claude Code transcript file and a Stop input.

Third-party inputs (ATBench, R-Judge) are read from local copies and never written into this
directory; `hook-verdicts.jsonl` keeps ids, labels and verdicts only.
"""

from __future__ import annotations

import ast
import glob
import json
import re
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RJUDGE_COMMIT = "83ce301da3ad50dd8b397e772863f5411c3d3dc2"
AGENTDOJO_GLOBS = (
    "docs/results/2026-09-24-agentdojo-e2e/runs/**/*.json",
    "docs/results/2026-09-24-agentdojo-haiku/runs/**/*.json",
)
PORT = 8765
SHELL_ATBENCH = "shell_command"


def _bench(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def _pre(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "replay",
        "tool_name": tool,
        "tool_input": arguments,
    }


def _post_bash(command: str, stdout: str) -> dict[str, Any]:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": "replay",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        # Claude Code's Bash result shape (recorded in the 2026-09-28 harness run).
        "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False, "isImage": False},
    }


# --- guard bench -----------------------------------------------------------------------------


def guard_cases() -> list[dict[str, Any]]:
    rows = [r for r in _bench(REPO / "benches" / "safety.jsonl") if r["point"] == "command"]
    return [
        {
            "set": "guard",
            "id": r["id"],
            "label": "unsafe" if r["expected"] else "safe",
            "calls": [_pre("Bash", {"command": r["input"]["command"]})],
        }
        for r in rows
    ]


# --- ATBench-Codex ---------------------------------------------------------------------------


def _mcp_name(name: str, arguments: Any) -> str:
    server = re.sub(r"_mcp$", "", name) or name
    op = arguments.get("operation") if isinstance(arguments, dict) else None
    op = re.sub(r"[^A-Za-z0-9_]+", "_", str(op)) if op else "call"
    return f"mcp__{server}__{op}"


def atbench_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    for record in json.loads(path.read_text(encoding="utf-8")):
        calls = []
        for message in record["conversation"]:
            action = message.get("action") if message.get("role") == "assistant" else None
            if not action:
                continue
            if isinstance(action, str):
                try:
                    action = json.loads(action)
                except json.JSONDecodeError:
                    action = {"name": action, "arguments": {}}
            name = str(action.get("name") or "")
            arguments = action.get("arguments") or {}
            if name == SHELL_ATBENCH and isinstance(arguments, dict):
                calls.append(_pre("Bash", {"command": str(arguments.get("command") or "")}))
            else:
                args = arguments if isinstance(arguments, dict) else {"value": arguments}
                calls.append(_pre(_mcp_name(name, arguments), args))
        cases.append(
            {
                "set": "atbench",
                "id": str(record["id"]),
                "label": "safe" if record["is_safe"] else "unsafe",
                "calls": calls,
            }
        )
    return cases


# --- R-Judge ---------------------------------------------------------------------------------

_TERMINAL = re.compile(r"TerminalExecute(?:\s+Input)?\s*:\s*(\{.*\})", re.DOTALL)
_FENCED = re.compile(r"```(?:bash|sh|shell)\s*\n?(.*?)```", re.DOTALL)


def rjudge_commands(action: str) -> list[str]:
    """The shell commands of one R-Judge action string, in order. Nothing else is read."""
    found = _TERMINAL.search(action)
    if found:
        try:
            command = json.loads(found.group(1).strip()).get("command")
        except (json.JSONDecodeError, AttributeError):
            command = None
        return [str(command)] if command else []
    return [c.strip() for c in _FENCED.findall(action) if c.strip()]


def rjudge_cases(clone: Path) -> list[dict[str, Any]]:
    def git(*args: str) -> bytes:
        return subprocess.run(["git", *args], cwd=clone, capture_output=True, check=True).stdout

    names = git("ls-tree", "-r", "--name-only", RJUDGE_COMMIT, "data").decode().split()
    cases = []
    for name in sorted(n for n in names if n.endswith(".json")):
        stem = name.removeprefix("data/").removesuffix(".json")
        for record in json.loads(git("show", f"{RJUDGE_COMMIT}:{name}").decode("utf-8")):
            commands = [
                command
                for turn in record["contents"]
                for message in turn
                if isinstance(message.get("action"), str)
                for command in rjudge_commands(message["action"])
            ]
            if not commands:
                continue
            cases.append(
                {
                    "set": "rjudge",
                    "id": f"{stem}/{record['id']}",
                    "label": "unsafe" if int(record["label"]) == 1 else "safe",
                    "calls": [_pre("Bash", {"command": c}) for c in commands],
                }
            )
    return cases


# --- content scan through the shell ----------------------------------------------------------


def injection_cases() -> list[dict[str, Any]]:
    own = [r for r in _bench(REPO / "benches" / "safety.jsonl") if r["point"] == "injection"]
    harvested = _bench(REPO / "benches" / "agentdojo-injection.jsonl")
    cases = []
    for set_name, rows in (("inject-ad", harvested), ("inject-own", own)):
        for r in rows:
            text = r["input"]["text"]
            label = "injected" if r["expected"] else "clean"
            fetch = f"curl -s http://127.0.0.1:{PORT}/{r['id']}.html"
            cases.append({"set": set_name, "id": r["id"], "label": label,
                          "calls": [_post_bash(fetch, text)]})  # fmt: skip
            cases.append({"set": "control", "id": r["id"], "label": label,
                          "calls": [_post_bash(f"cat pages/{r['id']}.txt", text)]})  # fmt: skip
    return cases


# --- Stop: AgentDojo trajectories as Claude Code transcripts -----------------------------------


def _blocks(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [b for b in value if isinstance(b, dict)]
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [{"type": "text", "content": value}]
        return [b for b in parsed if isinstance(b, dict)] if isinstance(parsed, list) else []
    return []


def _joined(blocks: list[dict[str, Any]]) -> str:
    return " ".join(b.get("content") or "" for b in blocks if b.get("type") == "text")


def transcript_lines(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """AgentDojo messages as the JSONL entries of a Claude Code transcript."""
    lines: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "user":
            text = _joined(_blocks(m.get("content")))
            lines.append({"type": "user", "message": {"role": "user", "content": text}})
        elif role == "assistant":
            content = [
                {"type": "text", "text": b["content"]}
                for b in _blocks(m.get("content"))
                if b.get("type") == "text" and b.get("content")
            ]
            content += [
                {"type": "tool_use", "id": str(c.get("id")), "name": c["function"],
                 "input": c.get("args") or {}}
                for c in m.get("tool_calls") or []
            ]  # fmt: skip
            if content:
                lines.append({"type": "assistant", "message": {"role": "assistant",
                                                               "content": content}})  # fmt: skip
        elif role == "tool":
            text = f"ERROR: {m['error']}" if m.get("error") else _joined(_blocks(m.get("content")))
            result = {"type": "tool_result", "tool_use_id": str(m.get("tool_call_id")),
                      "content": text}  # fmt: skip
            lines.append({"type": "user", "message": {"role": "user", "content": [result]}})
    return lines


def stop_cases(transcripts: Path) -> list[dict[str, Any]]:
    transcripts.mkdir(parents=True, exist_ok=True)
    cases = []
    for pattern in AGENTDOJO_GLOBS:
        for path in sorted(glob.glob(str(REPO / pattern), recursive=True)):
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if "messages" not in data or "utility" not in data:
                continue
            rel = Path(path).relative_to(REPO).as_posix()
            name = re.sub(r"[^A-Za-z0-9]+", "-", rel.removeprefix("docs/results/"))[-150:]
            target = transcripts / f"{name}.jsonl"
            body = "".join(json.dumps(e, ensure_ascii=False) + "\n"
                           for e in transcript_lines(data["messages"]))  # fmt: skip
            target.write_text(body, encoding="utf-8", newline="\n")
            stop = {
                "hook_event_name": "Stop",
                "session_id": "replay",
                "transcript_path": str(target),
                "stop_hook_active": False,
            }
            cases.append({"set": "stop", "id": rel,
                          "label": "done" if data["utility"] else "not_done",
                          "calls": [stop]})  # fmt: skip
    return cases


def all_cases(
    *, atbench: Path | None, rjudge: Path | None, transcripts: Path
) -> list[dict[str, Any]]:
    cases = guard_cases()
    if atbench is not None:
        cases += atbench_cases(atbench)
    if rjudge is not None:
        cases += rjudge_cases(rjudge)
    return cases + injection_cases() + stop_cases(transcripts)
