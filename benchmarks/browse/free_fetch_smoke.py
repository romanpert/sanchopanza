"""Browse, development: a smoke of fetch by passages in real Claude Code sessions (two at most).

python benchmarks/browse/free_fetch_smoke.py --run      # two Sonnet sessions, 1.50 USD cap each
python benchmarks/browse/free_fetch_smoke.py            # the report so far (free)

Two FRAMES tasks the first pilots already ran, the two whose SONNET base sessions fetched the most
pages and answered right; each run once with the pilot's runner (`free_e2e.one_session`, Claude
Code 2.1.287 first on PATH, settings through the session's own `--settings`), plus:

- the `sanchopanza-fetch` MCP server (`python -m sanchopanza fetch-mcp`) in the session's MCP
  config, allowed, with the pilots' WebFetch deny hosts in `SANCHOPANZA_FETCH_DENY_HOSTS`;
- the `fetch_hook` on `PreToolUse` WebFetch: a URL's first WebFetch goes to `fetch_passages`.

It checks the path end to end - the server starts, the hook denies, the agent calls the tool,
the Haiku reader's spend falls - and compares each session with the recorded base sessions of
the same task. Two sessions measure nothing. Rows with answers stay in the private cache.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


frames = _load("browse_free_frames", HERE / "free_frames.py")
offline = _load("browse_free_fetch_offline", HERE / "free_fetch_offline.py")
free = frames.free
PRIVATE = free.CACHE / "frames-fetch-smoke"
SESSIONS = PRIVATE / "sessions.jsonl"
CAP_USD = 1.50
CEILING_USD = 3.00
N_TASKS = 2
SERVER = "sanchopanza-fetch"
PIN = os.environ.get("SANCHOPANZA_CLAUDE_PIN", "")
PYTHON = free.nav.HOOK_PYTHON


def chosen_tasks() -> list[str]:
    """The base sessions' tasks with the most fetched pages, right by the runner's grade."""
    data = json.loads(offline.RECORDS.read_text(encoding="utf-8"))
    rows = [s for s in data["sessions"] if s["src"] in ("P1", "P2") and s["arm"] == "SONNET"]
    graded = {}
    for src in ("frames-pilot", "frames-pilot2"):
        for line in (free.CACHE / src / "sessions.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["arm"] == "SONNET":
                graded[row["task"]] = bool(row.get("success"))
    ranked = sorted((r for r in rows if graded.get(r["task"])), key=lambda r: -r["fetches_ok"])
    return [r["task"] for r in ranked[:N_TASKS]]


def mcp_config_with_fetch(original):
    def config(work: pathlib.Path) -> pathlib.Path:
        path = original(work)
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["mcpServers"][SERVER] = {
            "command": str(PYTHON),
            "args": ["-m", "sanchopanza", "fetch-mcp"],
            "env": {
                "PYTHONPATH": str(free.SRC),
                "SANCHOPANZA_FETCH_DENY_HOSTS": ",".join(frames.DENIED_HOSTS),
            },
        }
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    return config


def hooks() -> dict[str, Any]:
    command = f'"{pathlib.Path(PYTHON).as_posix()}" -m sanchopanza.harness.fetch_hook'
    hook = {"type": "command", "command": command, "timeout": frames.HOOK_TIMEOUT_S}
    return {"PreToolUse": [{"matcher": "WebFetch", "hooks": [hook]}]}


def run() -> None:
    if not PIN or not (pathlib.Path(PIN) / "claude.exe").exists():
        raise SystemExit("set SANCHOPANZA_CLAUDE_PIN to the folder holding the pinned claude.exe")
    if not frames.global_settings_clean():
        raise SystemExit("~/.claude/settings.json carries a sanchopanza hook: not running")
    os.environ["PATH"] = PIN + os.pathsep + os.environ.get("PATH", "")
    free.TOOLS = f"{free.TOOLS} mcp__{SERVER}"
    free.nav.mcp.mcp_config = mcp_config_with_fetch(free.nav.mcp.mcp_config)
    rows_frames = frames.read_frames()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    spent = sum(json.loads(x)["list_usd"] for x in _lines())
    for task in frames.tasks(rows_frames, chosen_tasks()):
        if any(json.loads(x)["task"] == task[0] for x in _lines()):
            continue
        if spent + CAP_USD > CEILING_USD:
            raise SystemExit(f"ceiling: {spent:.2f} spent, a session may cost {CAP_USD}")
        marks = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-fetch-{task[0].lower()}-"))
        row = free.one_session(
            task, 1, "SONNET-FETCH", session_max_usd=CAP_USD, deny=frames.DENY, hooks=hooks(),
            env_extra={"SANCHOPANZA_FETCH_DIR": str(marks),
                       "SANCHOPANZA_FETCH_DENY_HOSTS": ",".join(frames.DENIED_HOSTS)},
        )  # fmt: skip
        found = frames.inspect(row, task[3], CAP_USD, marks)
        row = {**row, **found, "success": found["ok_auto"]}
        with SESSIONS.open("a", encoding="utf-8") as out:
            out.write(json.dumps(row) + "\n")
        spent += row["list_usd"]


def _lines() -> list[str]:
    if not SESSIONS.exists():
        return []
    return [x for x in SESSIONS.read_text(encoding="utf-8").splitlines() if x.strip()]


def report() -> list[dict[str, Any]]:
    base = {}
    for src in ("frames-pilot", "frames-pilot2"):
        for line in (free.CACHE / src / "sessions.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["arm"] == "SONNET":
                base[row["task"]] = row
    out = []
    for line in _lines():
        row = json.loads(line)
        then = base.get(row["task"], {})
        out.append(
            {
                "task": row["task"],
                "right_auto": row["success"],
                "base_right_auto": then.get("success"),
                "list_usd": round(row["list_usd"], 4),
                "base_list_usd": round(then.get("list_usd", 0.0), 4),
                "usd_by_model": row["usd_by_model"],
                "base_usd_by_model": then.get("usd_by_model"),
                "tools": row["tools"],
                "base_tools": then.get("tools"),
                "leak": row.get("leak"),
                "version": row.get("version"),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.run:
        run()
    sys.stdout.write(json.dumps(report(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
