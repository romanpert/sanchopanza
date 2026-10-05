"""Does Claude Code 2.1.285 put the find-auto hook's answer in front of the model? Free: a local
fake Messages endpoint plays the model, so nothing is billed and no question reaches Jev.

    python -m benchmarks.adopt_dev.auto_e2e [--sancho <sanchopanza.exe>] [--claude <claude.exe>]

A scratch git repository with a few source files gets `sanchopanza install --scope project
--write --find-auto` from the given sanchopanza (default: this repository's .venv; the probe's
free check passes the sealed runner's own wiring instead, `run.install_sancho`). `claude -p`
runs against the endpoint (ANTHROPIC_BASE_URL on 127.0.0.1, a dummy key, no TypeSafe key: the
hook ranks with free BM25). The endpoint answers the agent's first four requests with one Grep each
and captures the fifth, then ends the turn. Passing means:

1. find_in_repo is in the agent's first request and `find_auto` is not (kept from the model);
2. the server was connected at init;
3. the fifth request carries the hook's header and a `pkg/...` place, and no earlier one does;
4. the journal holds one `find_auto` row with outcome `free` at search 4.

Side requests (title, quota: no Grep among their tools) get a one-word answer. Writes only under
~/.cache/sanchopanza/adopt/auto-e2e/ (or `--out`).
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = Path.home() / ".cache" / "sanchopanza" / "adopt" / "auto-e2e"
CLAUDE = Path.home() / ".cache" / "sanchopanza" / "adopt" / "claude-2.1.285" / "claude.exe"
MODEL = "claude-haiku-4-5-20251001"
FIND = "mcp__sanchopanza__find_in_repo"
AUTO = "mcp__sanchopanza__find_auto"
PATTERNS = ("convert", "returning", "insert_rows", "from_db")
REQUEST = "Database converters (from_db_value) are not called for returning fields on insert."
SOURCE = {
    "pkg/compiler.py": "class SQLInsertCompiler:\n    def execute_sql(self, returning_fields):\n"
    "        rows = fetch_returned_insert_rows(returning_fields)\n        return rows\n",
    "pkg/fields.py": "def from_db_value(value, expression, connection):\n    return value\n",
    "pkg/other.py": "def unrelated():\n    return 1\n",
    "docs/ref.md": "returning fields from_db_value converters insert\n",
}
DROP = ("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDECODE", "CLAUDE_AGENT_SDK", "CLAUDE_PID",
        "SANCHOPANZA_", "SANCHO_", "TYPESAFE_")  # fmt: skip


def sse(events: list[dict[str, Any]]) -> bytes:
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


def message(n: int, block: dict[str, Any], stop: str) -> tuple[list[dict[str, Any]], dict]:
    """The stream events of one assistant message with one content block, and the same message
    whole (for a request that did not ask to stream)."""
    usage = {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0}  # fmt: skip
    head = {"id": f"msg_{n}", "type": "message", "role": "assistant", "model": MODEL,
            "content": [], "stop_reason": None, "stop_sequence": None, "usage": usage}  # fmt: skip
    if block["type"] == "tool_use":
        start = {**block, "input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
    else:
        start = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": block["text"]}
    events = [
        {"type": "message_start", "message": head},
        {"type": "content_block_start", "index": 0, "content_block": start},
        {"type": "content_block_delta", "index": 0, "delta": delta},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
         "usage": {"output_tokens": 5}},
        {"type": "message_stop"},
    ]  # fmt: skip
    return events, {**head, "content": [block], "stop_reason": stop}


class Script:
    """The fake model: four Greps, then the end of the turn; every main request kept."""

    def __init__(self) -> None:
        self.main: list[dict[str, Any]] = []
        self.side = 0
        self.lock = threading.Lock()

    def answer(self, body: dict[str, Any]) -> tuple[list[dict[str, Any]], dict]:
        tools = [t.get("name") for t in body.get("tools") or []]
        with self.lock:
            if "Grep" not in tools:
                self.side += 1
                return message(1000 + self.side, {"type": "text", "text": "ok"}, "end_turn")
            self.main.append(body)
            n = len(self.main)
        if n <= len(PATTERNS):
            block = {"type": "tool_use", "id": f"toolu_{n:02d}", "name": "Grep",
                     "input": {"pattern": PATTERNS[n - 1], "path": "."}}  # fmt: skip
            return message(n, block, "tool_use")
        return message(n, {"type": "text", "text": "done"}, "end_turn")


def endpoint(script: Script) -> http.server.ThreadingHTTPServer:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            size = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(size) or b"{}")
            if "count_tokens" in self.path:
                return self._json({"input_tokens": 10})
            events, whole = script.answer(body)
            if not body.get("stream"):
                return self._json(whole)
            data = sse(events)
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None

        def do_GET(self) -> None:  # noqa: N802
            self._json({"data": [], "has_more": False}, 200)

        def _json(self, value: Any, code: int = 200) -> None:
            data = json.dumps(value).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args: Any) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def scratch(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    work = out / "work"
    for rel, text in SOURCE.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text, encoding="utf-8", newline="\n")
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    return work


def child_env(sancho: Path, claude: Path, out: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(DROP)}
    path = os.pathsep.join([str(claude.parent), str(sancho.parent), env.get("PATH", "")])
    return {**env, "PATH": path, "DISABLE_AUTOUPDATER": "1",
            "SANCHOPANZA_GUARD_DIR": str(out / "guard"),
            "SANCHOPANZA_JOURNAL": str(out / "journal.jsonl"),
            "SANCHOPANZA_LOOP_HOME": str(out / "loop")}  # fmt: skip


Install = Callable[[Path, Path], Path]  # (work, evidence) -> the .mcp.json to pass


def plain_install(sancho: Path, env: dict[str, str]) -> Install:
    """`sanchopanza install --scope project --write --find-auto` as a user runs it."""

    def install(work: Path, evidence: Path) -> Path:
        done = subprocess.run([str(sancho), "install", "--scope", "project", "--write",
                               "--find-auto"], cwd=work, env=env, capture_output=True,
                              text=True)  # fmt: skip
        (evidence / "install.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
        if done.returncode != 0:
            raise RuntimeError(f"install failed: {done.stderr[-400:]}")
        return work / ".mcp.json"

    return install


def text_of(body: dict[str, Any]) -> str:
    return json.dumps(body.get("messages") or [], ensure_ascii=False)


def run(claude: Path, out: Path, install: Install, env: dict[str, str]
        ) -> tuple[list[str], dict[str, Any]]:  # fmt: skip
    """The check. `install` wires the scratch repository (its journal must be
    `out/journal.jsonl`); `env` is Claude Code's environment, without the endpoint."""
    from sanchopanza.harness.find_auto import HEADER

    work = scratch(out)
    mcp = install(work, out)
    script = Script()
    server = endpoint(script)
    env = {**env, "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
           "ANTHROPIC_API_KEY": "dummy"}  # fmt: skip
    cmd = [str(claude), "-p", REQUEST, "--model", MODEL, "--max-budget-usd", "0.05",
           "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
           "--strict-mcp-config", "--mcp-config", str(mcp),
           "--permission-mode", "bypassPermissions"]  # fmt: skip
    problems: list[str] = []
    stream = out / "stream.jsonl"
    with stream.open("wb") as stdout, (out / "stream.err").open("wb") as stderr:
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=stdout, stderr=stderr,
                                stdin=subprocess.DEVNULL)  # fmt: skip
        try:
            proc.wait(timeout=240)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            problems.append("claude -p against the fake endpoint did not exit in 240 s")
    server.shutdown()
    (out / "requests.json").write_text(json.dumps(script.main, indent=1), encoding="utf-8")
    init = next((json.loads(line) for line in stream.read_text("utf-8", "replace").splitlines()
                 if '"subtype":"init"' in line.replace(" ", "")), {})  # fmt: skip
    servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or []}
    if servers.get("sanchopanza") != "connected":
        problems.append(f"find's server at init: {servers}")
    if len(script.main) < 5:
        return [*problems, f"only {len(script.main)} agent requests reached the endpoint"], {}
    first_tools = [t.get("name") for t in script.main[0].get("tools") or []]
    if FIND not in first_tools:
        problems.append("find_in_repo is not in the agent's first request")
    if AUTO in first_tools or any(AUTO in str(t) for t in init.get("tools") or []):
        problems.append("find_auto reached the model's tools")
    carried = [HEADER in text_of(body) for body in script.main]
    if carried[:4] != [False] * 4 or not carried[4]:
        problems.append(f"the header per request: {carried}")
    if carried[4] and "pkg/" not in text_of(script.main[4]).split(HEADER, 1)[1][:600]:
        problems.append("the fifth request has the header but no pkg/ place after it")
    journal = out / "journal.jsonl"
    rows = [json.loads(line) for line in journal.read_text("utf-8").splitlines()
            if '"find_auto"' in line] if journal.exists() else []  # fmt: skip
    outcomes = [(r["data"].get("outcome"), r["data"].get("search")) for r in rows]
    if outcomes != [("free", 4)]:
        problems.append(f"journal find_auto rows: {outcomes}")
    seen = {
        "init_servers": servers,
        "agent_requests": len(script.main),
        "side": script.side,
        "header_per_request": carried,
        "journal": outcomes,
        "auto_in_first_tools": AUTO in first_tools,
        "injected": text_of(script.main[4]).split(HEADER, 1)[-1][:400] if carried[4] else "",
    }
    return problems, seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sancho", default=str(REPO / ".venv" / "Scripts" / "sanchopanza.exe"))
    parser.add_argument("--claude", default=str(CLAUDE))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    sancho, claude, out = Path(args.sancho), Path(args.claude), Path(args.out)
    env = child_env(sancho, claude, out)
    problems, seen = run(claude, out, plain_install(sancho, env), env)
    print(json.dumps(seen, indent=1, ensure_ascii=False))
    for problem in problems:
        print(f"E2E FAILED: {problem}", flush=True)
    if not problems:
        print("E2E OK", flush=True)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
