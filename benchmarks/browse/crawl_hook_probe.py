"""Live probe of the packaged crawl hook (`sanchopanza.harness.crawl_hook`) in Claude Code.

python benchmarks/browse/crawl_hook_probe.py      # three Haiku sessions, about 0.15 USD list

Three things the unit tests cannot show, each read from the session's own transcript:

1. `allowed`: with browser_evaluate allowed, the guard's rewrite takes effect although the hook
   returns no `permissionDecision` (the bench guard returned "allow"), and the SessionStart line
   reaches the session.
2. `not-allowed`: with browser_evaluate NOT allowed, the packaged guard does not approve it: the
   call is refused as it would be with no hook at all.
3. `not-allowed-old`: the same with the bench guard (`evaluate_guard.py`, "allow"), to show what
   the packaged one avoids: a hook that approves a call the user's rules would have refused.

The hook runs from this worktree's `src` (PYTHONPATH); main's package has no crawl hook, so a
session that shows the line can only have run this one.

Run 2026-10-02 on Claude Code 2.1.287, 0.10 USD list: `allowed` came back after 15 s as the
guard's error, with the line in the transcript; `not-allowed` was refused ("you haven't granted
it yet"); `not-allowed-old` ran the evaluate the rules refused - the bench guard's "allow" was a
permission escalation, which the packaged guard does not have.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
spec = importlib.util.spec_from_file_location("browse_nav_e2e", HERE / "nav_e2e.py")
nav = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_e2e"] = nav
spec.loader.exec_module(nav)
sys.path.insert(0, str(SRC))

from sanchopanza.harness.crawl_hook import STRATEGY_LINE  # noqa: E402

LIMIT_S = 15
PROMPT = (
    "Open https://example.com in the browser. The page loads a results panel late, so wait for it: "
    "call browser_evaluate once with this function, unchanged: "
    "async () => { while (!document.querySelector('#results')) { await new Promise(r => "
    "setTimeout(r, 200)); } return document.querySelector('#results').textContent; } "
    "Then report exactly what the tool returned, error or value."
)
NO_EVALUATE = (
    "mcp__playwright__browser_navigate mcp__playwright__browser_snapshot "
    "mcp__playwright__browser_wait_for Read Grep Glob"
)


def _hooks(case: str) -> dict:
    python = nav.HOOK_PYTHON.as_posix()
    package = f'"{python}" -m sanchopanza.harness.crawl_hook'
    old = f'"{python}" "{(HERE / "evaluate_guard.py").as_posix()}"'
    guard = old if case.endswith("-old") else package
    entry = [{"type": "command", "command": guard, "timeout": 30}]
    return {
        "SessionStart": [{"matcher": "", "hooks": [
            {"type": "command", "command": package, "timeout": 30}]}],
        "PreToolUse": [{"matcher": r"mcp__.*__browser_evaluate", "hooks": entry}],
    }  # fmt: skip


def _transcript(work: pathlib.Path) -> str:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(work))
    folder = pathlib.Path.home() / ".claude" / "projects" / slug
    texts = (p.read_text(encoding="utf-8", errors="replace") for p in folder.glob("*.jsonl"))
    return "\n".join(texts)


def _evaluate_results(text: str) -> list[str]:
    """What each browser_evaluate call returned, as the transcript holds it."""
    calls: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        try:
            content = (json.loads(line).get("message") or {}).get("content")
        except ValueError:
            continue
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_use" and str(block.get("name")).endswith("evaluate"):
                calls.add(block["id"])
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                out.append(json.dumps(block.get("content"))[:400])
    return out


def run(case: str) -> dict:
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-crawl-probe-{case}-"))
    tools = nav.TOOLS if case == "allowed" else NO_EVALUATE
    settings = {"permissions": {"allow": tools.split()}, "hooks": _hooks(case)}
    (work / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    env = {**nav.base.clean_env(dict(os.environ)), "SANCHOPANZA_EVALUATE_LIMIT_S": str(LIMIT_S),
           "PYTHONPATH": str(SRC)}  # fmt: skip
    env.pop("TYPESAFE_API_KEY", None)
    argv = [shutil.which("claude") or "claude", "-p", "--model", "claude-haiku-4-5",
            "--settings", str(work / "settings.json"), "--setting-sources", "",
            "--mcp-config", str(nav.mcp.mcp_config(work)), "--strict-mcp-config",
            "--allowedTools", tools, "--disallowedTools", nav.DISALLOWED,
            "--output-format", "json", "--max-budget-usd", "0.30", "--", PROMPT]  # fmt: skip
    done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=300)
    out = json.loads(done.stdout.decode("utf-8", "replace") or "{}")
    text = _transcript(work)
    results = _evaluate_results(text)
    return {
        "case": case, "workdir": str(work), "list_usd": out.get("total_cost_usd"),
        "turns": out.get("num_turns"), "version": nav.claude_version(work),
        "line_in_transcript": STRATEGY_LINE[:80] in text,
        "evaluate_results": results,
        "guard_fired": any(f"stopped after {LIMIT_S} s" in r for r in results),
        "result": str(out.get("result"))[:500],
    }  # fmt: skip


def main() -> int:
    cases = sys.argv[1:] or ["allowed", "not-allowed", "not-allowed-old"]
    for case in cases:
        print(json.dumps(run(case), indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
