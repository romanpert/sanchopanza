"""Free checks before the nudge probe spends anything. No question reaches Jev or Claude.

    python -m benchmarks.adopt_dev.probe_nudge check

1. the confirmation's seal holds; the plan is the behaviour set's ten, none held out, used or in
   phase D;
2. Claude Code 2.1.285 is first on PATH; ADOPT_SANCHO is the frozen 4ee2901 copy with jev and mcp;
3. the S arms' hooks build JevDecider (`run.decider_probe`: building it sends no question);
4. `run.install_sancho` in a scratch repository wires find (alwaysLoad) and its nudge
   (`find-hook` on PostToolUse); a `claude -p` of the S arm against a local endpoint that answers
   400 (nothing billed, tool search on) shows in its first request find_in_repo not deferred, with
   the new description, a description on every parameter and `kind` as an enum, and the server's
   instructions at the session's start (2.1.285 puts them in the first user message);
5. the frozen `find-hook`, fed a 20-file Grep result in that scratch repository, answers with the
   nudge line, and a second time with nothing.
"""

from __future__ import annotations

import http.server
import json
import subprocess
import threading
from typing import Any

from sanchopanza.harness.mcp import FIND_DESCRIPTION, FIND_INSTRUCTIONS

from .check_alwaysload import CHECK, first_main_request, scratch_repo
from .common import (
    CLAUDE_VERSION,
    FIND_TOOL,
    FROZEN_COMMIT,
    FROZEN_EXE,
    MODEL,
    plan_refusal,
    read_json,
    run,
)

MARK = FIND_INSTRUCTIONS[:60]  # enough to find the instructions however they are wrapped


def _system_text(body: dict[str, Any]) -> str:
    system = body.get("system")
    if isinstance(system, list):
        return "\n".join(str(b.get("text", "")) for b in system if isinstance(b, dict))
    return str(system or "")


def capture_server(sink: list[dict[str, Any]]) -> http.server.HTTPServer:
    """A local endpoint that keeps each request's tools (with find's description and schema) and
    system text, and answers 400."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            size = int(self.headers.get("content-length", 0))
            try:
                body = json.loads(self.rfile.read(size))
                tools = [{"name": t.get("name"), "defer_loading": t.get("defer_loading"),
                          "has_schema": "input_schema" in t,
                          **({"description": t.get("description"),
                              "input_schema": t.get("input_schema")}
                             if t.get("name") == FIND_TOOL else {})}
                         for t in body.get("tools", [])]  # fmt: skip
                where = [k for k, v in body.items() if k != "messages" and MARK in json.dumps(v)]
                where += [f"messages[{i}]" for i, m in enumerate(body.get("messages") or [])
                          if MARK in json.dumps(m)]  # fmt: skip
                sink.append({"path": self.path, "model": body.get("model"), "tools": tools,
                             "system": _system_text(body), "instructions_in": where})  # fmt: skip
            except ValueError as exc:
                sink.append({"path": self.path, "error": str(exc)})
            answer = json.dumps({"type": "error", "error": {
                "type": "invalid_request_error", "message": "capture"}}).encode()  # fmt: skip
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

        def log_message(self, *_args: Any) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def wiring_problems(work: Any, mcp: Any) -> list[str]:
    problems = []
    if read_json(mcp)["mcpServers"].get("sanchopanza", {}).get("alwaysLoad") is not True:
        problems.append("the wired .mcp.json has no alwaysLoad")
    post = read_json(work / ".claude" / "settings.json")["hooks"].get("PostToolUse", [])
    if not any("find-hook" in h.get("command", "") for e in post for h in e.get("hooks", [])):
        problems.append("the install wired no find-hook on PostToolUse")
    return problems


def turn1_problems(first: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    problems = []
    tools = {t["name"]: t for t in first["tools"]}
    find = tools.get(FIND_TOOL) or {}
    props = (find.get("input_schema") or {}).get("properties", {})
    if not find or find.get("defer_loading") or not find.get("has_schema"):
        problems.append(f"find in turn 1: {find.get('name')} deferred {find.get('defer_loading')}")
    if find.get("description") != FIND_DESCRIPTION:
        problems.append(
            f"find's description in turn 1 is not the new one: {find.get('description')}"
        )
    if set(props) != {"query", "k", "kind"} or not all(
        p.get("description") for p in props.values()
    ):
        problems.append(f"find's parameters lack descriptions: {props}")
    if "enum" not in props.get("kind", {}):
        problems.append("find's kind is not an enum")
    # Claude Code 2.1.285 sends MCP server instructions in the first user message, not the
    # system prompt: fixed at session start either way, so inside the cached prefix.
    where = first.get("instructions_in", [])
    if not set(where) & {"system", "messages[0]"}:
        problems.append(f"the server's instructions are not at the session's start: {where}")
    if "ToolSearch" not in tools:
        problems.append("tool search was not on in the capture: the check proves nothing")
    seen = {"find_description": find.get("description"), "find_properties": props,
            "instructions_in": where,
            "deferred": sorted(n for n, t in tools.items() if t.get("defer_loading"))}  # fmt: skip
    return problems, seen


def nudge_problems(work: Any, evidence: Any) -> tuple[list[str], str]:
    files = [f"pkg/m{i}.py" for i in range(20)]
    event = {"hook_event_name": "PostToolUse", "session_id": "check-nudge", "cwd": str(work),
             "transcript_path": str(evidence / "none.jsonl"), "tool_name": "Grep",
             "tool_input": {"pattern": "x"},
             "tool_response": {"mode": "files_with_matches", "filenames": files,
                               "numFiles": 20}}  # fmt: skip
    env = {**run.child_env("", ""), "CLAUDE_PROJECT_DIR": str(work),
           "SANCHOPANZA_GUARD_DIR": str(evidence / "guard"),
           "SANCHOPANZA_JOURNAL": str(evidence / "journal.jsonl")}  # fmt: skip
    outs = [subprocess.run([str(FROZEN_EXE), "find-hook"], input=json.dumps(event).encode(),
                           capture_output=True, env=env, timeout=60).stdout.decode()
            for _ in range(2)]  # fmt: skip
    first = json.loads(outs[0] or "{}").get("hookSpecificOutput", {}).get("additionalContext", "")
    problems = []
    if "find_in_repo" not in first:
        problems.append(f"the frozen find-hook gave no nudge: {outs[0][:200]!r}")
    if outs[1].strip():
        problems.append("the frozen find-hook nudged twice in one session")
    return problems, first


def captured_request() -> tuple[list[str], dict[str, Any]]:
    work, evidence = scratch_repo()
    mcp = run.install_sancho(work, evidence, CHECK / "no.key")  # no key: the server needs none
    problems = wiring_problems(work, mcp)
    sink: list[dict[str, Any]] = []
    server = capture_server(sink)
    env = {**run.child_env("", ""), "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
           "ANTHROPIC_API_KEY": "dummy", "ENABLE_TOOL_SEARCH": "true"}  # fmt: skip
    out = CHECK / "stream.jsonl"
    with out.open("wb") as stdout, (CHECK / "stream.err").open("wb") as stderr:
        proc = subprocess.Popen(run.command(MODEL, "Say hi.", None, mcp), cwd=work, env=env,
                                stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL)  # fmt: skip
        try:
            proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            problems.append("claude -p against the capture did not exit in 180 s")
    server.shutdown()
    (CHECK / "captured.json").write_text(json.dumps(sink, indent=1), encoding="utf-8")
    first = first_main_request(sink)
    if first is None:
        return [*problems, f"no agent request captured ({len(sink)} requests)"], {}
    more, seen = turn1_problems(first)
    nudged, line = nudge_problems(work, evidence)
    return [*problems, *more, *nudged], {**seen, "nudge_line": line}


def check() -> int:
    import confirm  # benchmarks/adopt is on the path (common.py)

    problems: list[str] = []
    if not confirm.seal_holds():
        problems.append("the confirmation's seal does not hold")
    if why := plan_refusal():
        problems.append(why)
    if (found := run.claude_version()) != CLAUDE_VERSION:
        problems.append(f"Claude Code {found or 'none'} first on PATH, not {CLAUDE_VERSION}")
    stamp = run.frozen_stamp() or {}
    if stamp.get("commit") != FROZEN_COMMIT or not {"jev", "mcp"} <= set(stamp.get("extras", [])):
        problems.append(f"frozen copy: {stamp}")
    keyfile = run.keyfile_from_indagis()
    try:
        decider = run.decider_probe(keyfile)
    finally:
        keyfile.unlink(missing_ok=True)
    if decider != run.HELD_DECIDER:
        problems.append(f"the S hooks would build {decider}")
    CHECK.mkdir(parents=True, exist_ok=True)
    capture_problems, seen = captured_request()
    problems += capture_problems
    print(json.dumps({"claude": found, "frozen": stamp, "decider": decider, "turn1": seen},
                     indent=1))  # fmt: skip
    for problem in problems:
        print(f"CHECK FAILED: {problem}", flush=True)
    if not problems:
        print("CHECK OK", flush=True)
    return 1 if problems else 0
