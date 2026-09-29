"""`run.py dry`: everything but the model, for every arm and model. Free, no key.

1. Builds each arm's files (settings, plugin, MCP config) and prints the exact commands.
2. K and L: runs the arm's compaction command (the wrapper and `sanchopanza compact`) on a
   synthetic conversation, as the plugin would, and checks the exit code and the stub style.
3. L: the settings `install --autopilot --lean` wrote (lean variables, no decider), one
   PostToolUse with a 20,000-character build log through the hook wrapper (arrival cut applied
   and logged), and the archive MCP server started, its tools listed and `search_archive` asked.
4. A: its settings and commands (no key: the hooks fail open).
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import arms
import evidence

DRY = arms.ROOT / "dry"
LOG_LINE = "CHECK BR-7777 failed: expected 0.4242 got 0.4011"


def synthetic(n: int = 16, log_at: int = 1) -> list[dict[str, Any]]:
    """A task prompt and `n` acting turns; turn `log_at` is a 20,000-character build log."""
    msgs: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": "do the task"}]}]
    for i in range(n):
        if i == log_at:
            use = {"type": "tool_use", "id": f"tu{i}", "name": "Bash", "input": {"command": "python tools/build_report.py"}}
            lines = [f"[10:{j % 60:02d}] compile pkg/m{j % 24}.py ok cache hit {j * 7919:08x}" for j in range(300)]
            text = "\n".join([*lines[:150], LOG_LINE, *lines[150:]])
        else:
            use = {"type": "tool_use", "id": f"tu{i}", "name": "Read", "input": {"file_path": f"pkg/m{i}.py"}}
            text = "\n".join(f"def f{i}_{j}(x):\n    return x * {j}  # helper {i}" for j in range(40))
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": f"step {i}"}, use]})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"tu{i}", "content": text}]})
    msgs.append({"role": "assistant", "content": [{"type": "text", "text": "done"}]})
    return msgs


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return json.dumps(content)


def results(messages: list[dict[str, Any]]) -> list[str]:
    return [_text(b.get("content")) for m in messages for b in m.get("content", [])
            if isinstance(b, dict) and b.get("type") == "tool_result"]  # fmt: skip


def compaction_check(cfg: arms.ArmConfig, work: Path, ev: Path) -> dict[str, Any]:
    command = cfg.env["SANCHOPANZA_COMPACT_COMMAND"].split()
    out = work / ".sanchopanza" / "compact-dry.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(cfg.env)
    if cfg.settings is not None:
        env = {**env, **json.loads(cfg.settings.read_text("utf-8")).get("env", {})}
    proc = subprocess.run([*command, "--session", "dry", "--out", str(out)], cwd=work, env=env,
                          input=json.dumps({"messages": synthetic()}), capture_output=True,
                          text=True, encoding="utf-8", timeout=180)  # fmt: skip
    data = json.loads(out.read_text("utf-8")) if out.exists() else {}
    texts = results(data.get("messages") or [])
    report = data.get("report") or {}
    style = arms.STYLE[cfg.arm]
    cleared = sum(t == evidence.CLEARED for t in texts)
    stubs = [t for t in texts if t.startswith(evidence.STUB_PREFIX)]
    archive = work / ".sanchopanza" / "archive"
    archived = [p for p in archive.rglob("*") if p.is_file()] if archive.exists() else []
    kept_recent = all(not (t == evidence.CLEARED or t.startswith(evidence.STUB_PREFIX)) for t in texts[-arms.MASK_TURNS:])
    if style == "cleared":
        ok = cleared >= 6 and not stubs and not archived
    else:
        ok = len(stubs) >= 6 and all(" Holds: " in s for s in stubs) and bool(archived) and not cleared
    wrapper = [json.loads(x) for x in evidence.tr._lines(ev / "wrapper.jsonl")]
    return {
        "exit": proc.returncode, "stub_style_reported": report.get("stub_style"),
        "reduction": report.get("reduction"), "cleared": cleared, "sancho_stubs": len(stubs),
        "log_stub": next((evidence.neutral(s)[:300] for s in stubs if "Bash" in s), None),
        "failing_id_in_index": any("BR-7777" in s for s in stubs), "archived_files": len(archived),
        "last_10_kept": kept_recent, "wrapper_lines": len(wrapper),
        "stderr": evidence.neutral(proc.stderr[-300:]),
        "passed": proc.returncode == 0 and report.get("stub_style") == style and ok and kept_recent and bool(wrapper),
    }  # fmt: skip


LEAN_EXPECTED = {"SANCHOPANZA_STUB_STYLE": "index", "SANCHOPANZA_ARRIVAL_MODE": "free",
                 "SANCHOPANZA_RECALL_ON": "off"}  # fmt: skip


def lean_settings_check(cfg: arms.ArmConfig) -> dict[str, Any]:
    data = json.loads(cfg.settings.read_text("utf-8"))
    env = data.get("env", {})
    installed = cfg.notes.get("installed_env", {})
    commands = [h.get("command", "") for entries in data.get("hooks", {}).values()
                for e in entries for h in e.get("hooks", [])]  # fmt: skip
    ok_env = all(installed.get(k) == v for k, v in LEAN_EXPECTED.items())
    return {
        "lean_env": {k: installed.get(k) for k in LEAN_EXPECTED}, "lean_env_ok": ok_env,
        "no_decider": "SANCHOPANZA_PROVIDER" not in env and not any(k.startswith("TYPESAFE") for k in env),
        "hook_events": sorted(data.get("hooks", {})),
        "hooks_to_wrapper": bool(commands) and all("hook_wrapper.py" in c for c in commands),
        "marketplace_keys": [k for k in ("extraKnownMarketplaces", "enabledPlugins") if k in data],
        "compact_at_percent": env.get("SANCHOPANZA_COMPACT_AT_PERCENT"),
        "mcp_source": cfg.notes.get("mcp_source"), "installed_mcp_entry": cfg.notes.get("installed_entry"),
        "passed": ok_env and bool(commands) and all("hook_wrapper.py" in c for c in commands),
    }  # fmt: skip


def hook_check(cfg: arms.ArmConfig, work: Path, ev: Path) -> dict[str, Any]:
    env = {**cfg.env, **json.loads(cfg.settings.read_text("utf-8")).get("env", {})}
    big = "\n".join([f"[10:{i % 60:02d}] compile pkg/m{i % 24}.py ok ({i / 1000:.3f}s) cache hit {i * 7919:08x}" for i in range(299)] + [LOG_LINE])
    events = [
        {"hook_event_name": "PostToolUse", "session_id": "dry", "cwd": str(work), "transcript_path": "",
         "tool_name": "Bash", "tool_input": {"command": "python tools/build_report.py"},
         "tool_response": {"stdout": big, "stderr": "", "interrupted": False}},
        {"hook_event_name": "UserPromptSubmit", "session_id": "dry", "cwd": str(work), "prompt": "set the token"},
    ]  # fmt: skip
    command = arms.hook_command(ev, ev / "no-key").split()
    for event in events:
        subprocess.run(command, input=json.dumps(event), text=True, capture_output=True, env=env,
                       cwd=work, timeout=180)  # fmt: skip
    stats = evidence.hook_stats(ev)
    return {**stats, "passed": stats["events"] == 2 and stats["arrival_cuts"] == 1 and stats["nonzero_exits"] == 0}


def mcp_check(cfg: arms.ArmConfig, work: Path) -> dict[str, Any]:
    """Start the archive server from the session's MCP config; list tools; one search."""
    name, entry = next(iter(json.loads(cfg.mcp_config.read_text("utf-8"))["mcpServers"].items()))
    proc = subprocess.Popen([entry["command"], *entry.get("args", [])], cwd=work, env=cfg.env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8")  # fmt: skip
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(x) for x in proc.stdout], daemon=True).start()

    def call(i: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
        proc.stdin.flush()
        while True:
            msg = json.loads(lines.get(timeout=60))
            if msg.get("id") == i:
                return msg

    try:
        call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "dry", "version": "0"}})  # fmt: skip
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        tools = [t["name"] for t in call(2, "tools/list", {})["result"]["tools"]]
        found = call(3, "tools/call", {"name": "search_archive", "arguments": {"query": "CHECK failed BR-7777", "k": 3}})
        text = json.dumps(found.get("result"))
        out = {"server": name, "tools": tools, "search_hit_has_failing_line": "BR-7777" in text,
               "search_chars": len(text)}  # fmt: skip
    except (queue.Empty, KeyError, json.JSONDecodeError, OSError) as error:
        out = {"server": name, "error": f"{error.__class__.__name__}: {error}"}
    finally:
        proc.kill()
    return {**out, "passed": "search_archive" in out.get("tools", [])}


def one(model: arms.Model, arm: str) -> dict[str, Any]:
    ev, work = DRY / model.key / arm / "ev", DRY / model.key / arm / "work"
    for path in (ev, work):
        shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    out: dict[str, Any] = {"model": model.key, "arm": arm}
    try:
        cfg = arms.config(arm, model.key, ev, work)
    except (RuntimeError, SystemExit, OSError, ValueError) as error:
        return {**out, "error": evidence.neutral(str(error))[:600], "passed": False}
    out["command_a"] = arms.argv("<PROMPT_A>", model, arms.config("phaseA", model.key, ev, work))
    out["command_b"] = arms.argv("<PROMPT_B>", model, cfg, resume="<A-session-id>")
    out["env_set"] = {k: v for k, v in cfg.env.items() if k.startswith(("CLAUDE", "SANCHOPANZA_"))}
    checks = {}
    if arm in ("K", "L"):
        checks["compaction"] = compaction_check(cfg, work, ev)
    if arm == "L":
        checks["settings"] = lean_settings_check(cfg)
        checks["hooks"] = hook_check(cfg, work, ev)
        checks["mcp"] = mcp_check(cfg, work)
    out["checks"] = checks
    out["passed"] = all(c.get("passed") for c in checks.values())
    return out


def main() -> int:
    results_all = []
    for model in arms.MODELS.values():
        for arm in (*model.arms, "A"):
            results_all.append(one(model, arm))
    version = arms.claude_version()
    print(json.dumps(evidence.scrub({"claude_version": version, "arms": results_all}), indent=1))
    bad = [(r["model"], r["arm"]) for r in results_all if not r["passed"]]
    print(f"dry: {'FAILED ' + str(bad) if bad else 'all arms passed'}")
    print("not checked here (needs a session): the plugin's `loaded` marker, mid-turn firing")
    return 1 if bad else 0
