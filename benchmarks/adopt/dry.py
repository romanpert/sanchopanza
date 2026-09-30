"""Everything but the model, free: export a chain, wire S, run `runtests` the way the agent would
(through Git Bash, from the working copy), fire each wrapped hook once, list the MCP tool.

    python benchmarks/adopt/dry.py <chain>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402
import run  # noqa: E402

BASH = r"C:\Program Files\Git\bin\bash.exe"


def main(name: str) -> int:
    chain = run.chains()[name]
    root = run.ROOT / "dry"
    docker_env.remove_tree(root)
    work, evidence = root / "work", root / "evidence"
    evidence.mkdir(parents=True)
    base = docker_env.export(chain["tag"], work)
    keyfile = root / "no.key"  # no key: the hooks must still run, on code alone
    mcp = run.install_sancho(work, evidence, keyfile)
    env = run.child_env(chain["tag"], base)
    print("installed:", sorted(p.name for p in (work / ".claude").iterdir()), mcp.name)
    # an edit, then runtests from Git Bash as the agent would call it
    target = next(p for p in sorted(work.rglob("*.py")) if "test" not in p.name)
    target.write_text(target.read_text(encoding="utf-8") + "\n# dry\n", encoding="utf-8")
    test_file = chain["bugs"][0]["FAIL_TO_PASS"][0].split("::")[0]
    done = subprocess.run([BASH, "-lc", f"runtests -q -x {test_file} 2>&1 | tail -3"], cwd=work,
                          env=env, capture_output=True, text=True, timeout=900)  # fmt: skip
    print("runtests:", done.returncode, done.stdout.strip()[-300:], done.stderr.strip()[-300:])
    # each wrapped hook once
    settings = json.loads((work / ".claude" / "settings.json").read_text(encoding="utf-8"))
    events = {"PreToolUse": {"tool_name": "Bash", "tool_input": {"command": "ls"}},
              "PreCompact": {"trigger": "auto"}, "SessionStart": {"source": "compact"}}
    for event, extra in events.items():
        for entry in settings["hooks"].get(event, []):
            for hook in entry["hooks"]:
                payload = json.dumps({"hook_event_name": event, "session_id": "dry",
                                      "cwd": str(work), "transcript_path": "", **extra})
                out = subprocess.run(hook["command"], shell=True, input=payload, cwd=work, env=env,
                                     capture_output=True, text=True, timeout=120)  # fmt: skip
                print(f"hook {event}: exit {out.returncode} {out.stdout[:120]!r}")
    print((evidence / "hooks.jsonl").read_text(encoding="utf-8")[-600:])
    # the MCP server answers tools/list
    server = json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["sanchopanza"]
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "dry", "version": "0"}}}
    listed = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    lines = "\n".join(json.dumps(m) for m in (init, note, listed)) + "\n"
    out = subprocess.run([server["command"], *server["args"]], input=lines, cwd=work, env=env,
                         capture_output=True, text=True, timeout=120)  # fmt: skip
    answers = [json.loads(line) for line in out.stdout.splitlines() if line.startswith("{")]
    print("mcp tools:", [t["name"] for a in answers if a.get("id") == 2
                         for t in a["result"]["tools"]])  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
