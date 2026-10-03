"""Free checks before the alwaysLoad probe spends anything. No question reaches Jev or Claude.

    python -m benchmarks.adopt_dev.probe_alwaysload check

1. the confirmation's seal holds, the plan has no held-out single and the seeded draw still gives
   the new development singles;
2. Claude Code 2.1.285 is first on PATH; ADOPT_SANCHO is the frozen 1ea9302 copy with jev and mcp;
3. the S arms' hooks build JevDecider (`run.decider_probe`: building it sends no question);
4. `run.install_sancho` in a scratch repository writes find's server with `"alwaysLoad": true`,
   and a `claude -p` of the S arm against a local fake endpoint (ANTHROPIC_BASE_URL on 127.0.0.1,
   a dummy key, ENABLE_TOOL_SEARCH=true so tool search is on as with the real API) shows, in its
   first request, find_in_repo with its schema and no `defer_loading` while other tools are
   deferred, and the server connected in the init line. The endpoint answers 400: nothing billed.
"""

from __future__ import annotations

import http.server
import json
import subprocess
import threading
from pathlib import Path
from typing import Any

from .common import (
    CLAUDE_VERSION,
    FIND_TOOL,
    FROZEN_COMMIT,
    MODEL,
    OUT,
    docker_env,
    plan_refusal,
    read_json,
    run,
)

CHECK = OUT / "check"


def capture_server(sink: list[dict[str, Any]]) -> http.server.HTTPServer:
    """A local endpoint that keeps each request's tools (name, defer_loading) and answers 400."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            size = int(self.headers.get("content-length", 0))
            try:
                body = json.loads(self.rfile.read(size))
                tools = [{"name": t.get("name"), "defer_loading": t.get("defer_loading"),
                          "has_schema": "input_schema" in t}
                         for t in body.get("tools", [])]  # fmt: skip
                sink.append({"path": self.path, "model": body.get("model"), "tools": tools})
            except ValueError as exc:
                sink.append({"path": self.path, "error": str(exc)})
            error = {"type": "invalid_request_error", "message": "capture"}
            answer = json.dumps({"type": "error", "error": error}).encode()
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


def scratch_repo() -> tuple[Path, Path]:
    work, evidence = CHECK / "work", CHECK / "evidence"
    for path in (work, evidence):
        docker_env.remove_tree(path)
        path.mkdir(parents=True)
    (work / "README.md").write_text("scratch\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    return work, evidence


def first_main_request(sink: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The agent's first request: the one that offers Bash (not a title or quota call)."""
    return next((r for r in sink if any(t["name"] == "Bash" for t in r.get("tools", []))), None)


def captured_request() -> tuple[list[str], dict[str, Any]]:
    problems: list[str] = []
    work, evidence = scratch_repo()
    mcp = run.install_sancho(work, evidence, CHECK / "no.key")  # no key: the server needs none
    server_entry = read_json(mcp)["mcpServers"].get("sanchopanza", {})
    if server_entry.get("alwaysLoad") is not True:
        problems.append(f"the wired .mcp.json has no alwaysLoad: {server_entry}")
    sink: list[dict[str, Any]] = []
    server = capture_server(sink)
    env = {**run.child_env("", ""), "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
           "ANTHROPIC_API_KEY": "dummy", "ENABLE_TOOL_SEARCH": "true"}  # fmt: skip
    cmd = run.command(MODEL, "Say hi.", None, mcp)
    out = CHECK / "stream.jsonl"
    with out.open("wb") as stdout, (CHECK / "stream.err").open("wb") as stderr:
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=stdout, stderr=stderr,
                                stdin=subprocess.DEVNULL)  # fmt: skip
        try:
            proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            problems.append("claude -p against the capture did not exit in 180 s")
    server.shutdown()
    (CHECK / "captured.json").write_text(json.dumps(sink, indent=1), encoding="utf-8")
    init = next((json.loads(line) for line in out.read_text("utf-8", "replace").splitlines()
                 if '"subtype":"init"' in line.replace(" ", "")), {})  # fmt: skip
    servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or []}
    if servers.get("sanchopanza") != "connected":
        problems.append(f"find's server at init: {servers}")
    first = first_main_request(sink)
    if first is None:
        return [*problems, f"no agent request captured ({len(sink)} requests)"], {}
    tools = {t["name"]: t for t in first["tools"]}
    find = tools.get(FIND_TOOL)
    deferred = sorted(n for n, t in tools.items() if t.get("defer_loading"))
    if find is None or find.get("defer_loading") or not find.get("has_schema"):
        problems.append(f"find in turn 1: {find}")
    if "ToolSearch" not in tools or not deferred:
        problems.append("tool search was not on in the capture: the check proves nothing")
    seen = {"model": first.get("model"), "find": find, "deferred": deferred,
            "init_servers": servers, "tools": sorted(tools)}  # fmt: skip
    return problems, seen


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
    turn1 = {k: v for k, v in seen.items() if k != "tools"}
    print(json.dumps({"claude": found, "frozen": stamp, "decider": decider, "turn1": turn1},
                     indent=1))  # fmt: skip
    for problem in problems:
        print(f"CHECK FAILED: {problem}", flush=True)
    if not problems:
        print("CHECK OK", flush=True)
    return 1 if problems else 0
