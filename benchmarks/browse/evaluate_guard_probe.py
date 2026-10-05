"""One live probe: does Claude Code apply a PreToolUse updatedInput to a Playwright MCP evaluate?

python benchmarks/browse/evaluate_guard_probe.py     # one Haiku session, about 0.04 USD list

Run 2026-10-02 on Claude Code 2.1.287: the evaluate came back after 15 s as the guard's error and
the agent reported it. A first wording that called the loop infinite outright was refused by the
model and tested nothing; this one asks it to wait for an element that never appears.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("browse_nav_e2e", HERE / "nav_e2e.py")
nav = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_e2e"] = nav
spec.loader.exec_module(nav)

LIMIT_S = 15
PROMPT = (
    "Open https://example.com in the browser. The page loads a results panel late, so wait for it: "
    "call browser_evaluate once with this function, unchanged: "
    "async () => { while (!document.querySelector('#results')) { await new Promise(r => "
    "setTimeout(r, 200)); } return document.querySelector('#results').textContent; } "
    "Then report exactly what the tool returned, error or value."
)


def main() -> int:
    work = pathlib.Path(tempfile.mkdtemp(prefix="sp-guard-probe-"))
    hook = f'"{nav.HOOK_PYTHON.as_posix()}" "{(HERE / "evaluate_guard.py").as_posix()}"'
    settings = {
        "permissions": {"allow": nav.TOOLS.split()},
        "hooks": {"PreToolUse": [{"matcher": "mcp__playwright__browser_evaluate",
                                  "hooks": [{"type": "command", "command": hook, "timeout": 30}]}]},
    }  # fmt: skip
    (work / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    env = {**nav.base.clean_env(dict(os.environ)), "SANCHOPANZA_EVALUATE_LIMIT_S": str(LIMIT_S)}
    env.pop("TYPESAFE_API_KEY", None)
    argv = [shutil.which("claude") or "claude", "-p", "--model", "claude-haiku-4-5",
            "--settings", str(work / "settings.json"), "--setting-sources", "",
            "--mcp-config", str(nav.mcp.mcp_config(work)), "--strict-mcp-config",
            "--allowedTools", nav.TOOLS, "--disallowedTools", nav.DISALLOWED,
            "--output-format", "json", "--max-budget-usd", "0.30", "--", PROMPT]  # fmt: skip
    done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=300)
    out = json.loads(done.stdout.decode("utf-8", "replace") or "{}")
    print(json.dumps({"workdir": str(work), "list_usd": out.get("total_cost_usd"),
                      "turns": out.get("num_turns"), "result": str(out.get("result"))[:800],
                      "version": nav.claude_version(work)}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
