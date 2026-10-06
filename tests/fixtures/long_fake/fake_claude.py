"""A stand-in for `claude -p` that replays recorded calls, for `long_run.py`'s dry runs. Free.

    python fake_claude.py --version
    python fake_claude.py -p <prompt> --model M --permission-mode P --mcp-config F [--resume S]

Each call replays one recorded call of B2's arm N (`b2-n-calls.json`: per request its usage and
the tools it called) as stream-json on stdout and appends the same requests to the session's
transcript under CLAUDE_CONFIG_DIR, as Claude Code does. It does the work the prompt asks in the
working copy: `changes/<n>.md` with the token given in the first prompt, a line in a module, and
a callback's `changes/recall-<k>.md`. `modelUsage` in the result is the session's running total.

FAKE_CLAUDE_INJECT (JSON): {"<config folder name>": {"<call>": kind}}, the call counted per
configuration, retries included. Kinds:
- `429`: a rejected rate-limit event and a result with api_error_status 429;
- `timeout`: the init, then silence (the runner kills it);
- `crash`: the init and one tool call that changes a file, then exit 3 with no result;
- `compact`: a compaction boundary, and its call's tokens in modelUsage only (as headless
  Claude Code leaves the compaction call out of the transcript);
- `mcpfail`: the init lists every MCP server of --mcp-config as `failed`.

A `429` call is rejected before any work. With `--debug-file=<path>` it writes Claude Code's
`autocompact: tokens=... effectiveWindow=...` line per request: the window is the settings
`env` block's CLAUDE_CODE_AUTO_COMPACT_WINDOW, else FAKE_SERVER_WINDOW (default 1,000,000), which
it also caches in `<config>/.claude.json` as the server would (`autoCompactWindowsCache`).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
VERSION = "2.1.287"
OUTPUT_RESERVE = 20_000
S_PREFIX = 1_000  # what an S install adds to the first request's prefix (pre-mortem 9: 200-6,000)
COMPACTION = {"input_tokens": 3, "output_tokens": 9_000, "cache_read_input_tokens": 160_000,
              "cache_creation_input_tokens": 0}  # fmt: skip


def option(argv: list[str], name: str) -> str | None:
    if name in argv:
        return argv[argv.index(name) + 1]
    joined = next((a for a in argv if a.startswith(f"{name}=")), None)
    return joined.split("=", 1)[1] if joined else None


def window(model: str, config: Path) -> int:
    """The window this session runs under, as Claude Code resolves it (env first)."""
    settings = Path(".claude", "settings.json")
    env = json.loads(settings.read_text("utf-8")).get("env", {}) if settings.exists() else {}
    if env.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"):
        return int(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"])
    server = int(os.environ.get("FAKE_SERVER_WINDOW") or 1_000_000)
    cached = {"autoCompactWindowsCache": {model: server}}
    (config / ".claude.json").write_text(json.dumps(cached), encoding="utf-8")
    return server


def debug_lines(path: str | None, usages: list[dict[str, Any]], effective: int) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as out:
        for u in usages:
            tokens = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                      "cache_creation_input_tokens"))
            out.write(f"2026-10-06T00:00:00Z [DEBUG] autocompact: tokens={tokens} level=ok "
                      f"effectiveWindow={effective}\n")
            out.write("2026-10-06T00:00:00Z [DEBUG] [api] request sent\n")


def prompt_of(argv: list[str]) -> str:
    after = option(argv, "-p")
    return after if after is not None and not after.startswith("--") else sys.stdin.read()


def emit(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def state_file(config: Path) -> Path:
    return config / "fake-state.json"


def load_state(config: Path) -> dict[str, Any]:
    path = state_file(config)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "calls": 0, "token": "", "usage": {}}  # fmt: skip


def injection(config: Path, call: int) -> str:
    plan = json.loads(os.environ.get("FAKE_CLAUDE_INJECT") or "{}")
    return str((plan.get(config.parent.name) or {}).get(str(call)) or "")


def init_event(session: str, argv: list[str], kind: str) -> dict[str, Any]:
    mcp = option(argv, "--mcp-config")
    names = list(json.loads(Path(mcp).read_text(encoding="utf-8")).get("mcpServers", {})) \
        if mcp and Path(mcp).exists() else []  # fmt: skip
    status = "failed" if kind == "mcpfail" else "connected"
    return {"type": "system", "subtype": "init", "session_id": session, "cwd": os.getcwd(),
            "model": option(argv, "--model"), "permissionMode": option(argv, "--permission-mode"),
            "claude_code_version": VERSION, "apiKeySource": "none", "tools": ["Bash", "Read"],
            "mcp_servers": [{"name": n, "status": status} for n in names], "plugins": [],
            "skills": [], "agents": []}  # fmt: skip


def project_dir(config: Path) -> Path:
    folder = config / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def do_work(prompt: str, token: str) -> str:
    """What the prompt asks, done in the working copy; returns the token it now knows."""
    found = re.search(r"Ref: ([0-9a-f]{8})", prompt)
    token = found.group(1) if found else token
    bug = re.search(r"Bug (\d+) of this session", prompt)
    recall = re.search(r"changes/recall-(\d+)\.md", prompt)
    Path("changes").mkdir(exist_ok=True)
    if bug:
        n = bug.group(1)
        Path("changes", f"{n}.md").write_text(f"Ref: {token}\nFixed.\n", encoding="utf-8")
        with Path("fake_module.py").open("a", encoding="utf-8") as module:
            module.write(f"FIX_{n} = True\n")
    elif recall:
        Path("changes", f"recall-{recall.group(1)}.md").write_text(
            "bug 1: fake_module.py\n", encoding="utf-8")  # fmt: skip
    return token


def replay(call: int, session: str, model: str, transcript: Path,
           installed: bool = False) -> list[dict[str, Any]]:  # fmt: skip
    """The recorded requests of one call, as stream events and transcript lines. With an install
    (MCP servers in --mcp-config) the first request writes S_PREFIX more (skill, schemas, hooks)."""
    recorded = json.loads((HERE / "b2-n-calls.json").read_text(encoding="utf-8"))["calls"]
    requests = recorded[(call - 1) % len(recorded)]["requests"]
    if installed and call == 1 and requests:
        first = dict(requests[0]["usage"])
        written = int(first.get("cache_creation_input_tokens") or 0)
        first["cache_creation_input_tokens"] = written + S_PREFIX
        requests = [{**requests[0], "usage": first}, *requests[1:]]
    usages = []
    with transcript.open("a", encoding="utf-8") as out:
        for i, req in enumerate(requests):
            content = [{"type": "tool_use", "id": f"t{call}-{i}-{j}", "name": name, "input": {}}
                       for j, name in enumerate(req["tools"])] or [{"type": "text", "text": "ok"}]
            message = {"id": f"msg-{session[:8]}-{call}-{i}", "model": model,
                       "content": content, "usage": req["usage"]}  # fmt: skip
            event = {"type": "assistant", "session_id": session, "message": message}
            emit(event)
            out.write(json.dumps(event) + "\n")
            usages.append(req["usage"])
    return usages


def add_usage(total: dict[str, Any], model: str, usages: list[dict[str, Any]]) -> dict[str, Any]:
    keys = {"inputTokens": "input_tokens", "outputTokens": "output_tokens",
            "cacheReadInputTokens": "cache_read_input_tokens",
            "cacheCreationInputTokens": "cache_creation_input_tokens"}  # fmt: skip
    mine = dict(total.get(model) or dict.fromkeys(keys, 0))
    for u in usages:
        mine = {k: mine.get(k, 0) + int(u.get(v) or 0) for k, v in keys.items()}
    return {**total, model: mine}


def run_call(argv: list[str]) -> int:
    config = Path(os.environ["CLAUDE_CONFIG_DIR"])
    state = load_state(config)
    call = state["calls"] + 1
    kind = injection(config, call)
    session = option(argv, "--resume") or str(uuid.uuid4())
    model = option(argv, "--model") or "claude-sonnet-5-5"
    state_file(config).write_text(json.dumps({**state, "calls": call}), encoding="utf-8")
    emit(init_event(session, argv, kind))
    if kind == "timeout":
        time.sleep(600)
        return 0
    if kind == "429":
        return finish(config, session, call, kind, state["usage"], state["token"])
    if kind == "crash":
        emit({"type": "assistant", "session_id": session, "message": {
            "id": f"msg-crash-{call}", "model": model, "content": [
                {"type": "tool_use", "id": "c1", "name": "Bash", "input": {}}]}})  # fmt: skip
        Path("crash_note.txt").write_text("half done\n", encoding="utf-8")
        return 3
    token = do_work(prompt_of(argv), state["token"])
    transcript = project_dir(config) / f"{session}.jsonl"
    mcp = option(argv, "--mcp-config")
    installed = bool(mcp and json.loads(Path(mcp).read_text(encoding="utf-8")).get("mcpServers"))
    usages = replay(call, session, model, transcript, installed)
    debug_lines(option(argv, "--debug-file"), usages, window(model, config) - OUTPUT_RESERVE)
    if kind == "compact":
        emit({"type": "system", "subtype": "compact_boundary", "session_id": session,
              "compact_metadata": {"trigger": "auto", "pre_tokens": 160_500,
                                   "post_tokens": 9_000}})  # fmt: skip
        usages = [*usages, COMPACTION]
    total = add_usage(state["usage"], model, usages)
    return finish(config, session, call, kind, total, token)


def finish(config: Path, session: str, call: int, kind: str, total: dict[str, Any],
           token: str) -> int:  # fmt: skip
    limited = kind == "429"
    if limited:
        emit({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}})
    emit({"type": "result", "subtype": "success", "session_id": session, "is_error": limited,
          **({"api_error_status": 429} if limited else {}), "num_turns": 3,
          "total_cost_usd": 0.0, "modelUsage": total, "permission_denials": []})  # fmt: skip
    state = {"calls": call, "token": token, "usage": total}
    state_file(config).write_text(json.dumps(state), encoding="utf-8")
    return 1 if limited else 0


def main(argv: list[str]) -> int:
    if "--version" in argv:
        print(f"{VERSION} (Claude Code)")
        return 0
    return run_call(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
