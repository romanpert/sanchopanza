"""Browse, development: Claude Code left to itself on free, complex web tasks it can be graded on.

python benchmarks/browse/free_e2e.py --pilot [--ceiling 8]     # Sonnet, natural tools, no hook
python benchmarks/browse/free_e2e.py                           # free: the report so far

Every phase of this line until now gave the agent a URL, a question shaped for one mechanism and
only the browser. That measures a lever under laboratory conditions; it says little about how a
harness copes with what people actually ask (the owner, 2026-10-03). Here the agent gets only the
question and the tools Claude Code normally has (WebSearch, WebFetch, Playwright MCP, files and
subagents; Bash stays off on this machine), on tasks from two public sets whose answers can be
checked:

- AssistantBench (Yoran et al., 2024), dev split: realistic, time-consuming web tasks. Some
  answers drift with time (opening hours, a streaming catalogue); both arms of a comparison run
  the same day, so drift costs sensitivity, not fairness. Only tasks whose answer is a number or
  a short name are taken.
- BrowseComp (Wei et al., 2025), the public test set: hard-to-find facts with short, stable
  answers. Its problems and answers are encrypted with a canary so they stay out of training
  data; they are decrypted into the local cache only, and nothing here writes an answer to the
  repository - the session files keep the task id and the grade, not the text.

Grading: the reply's ANSWER line, normalised, must contain the gold answer (numbers compared as
numbers within 1 %); every miss is read by hand before it is described.

The pilot calibrates: what a free session costs, how long it takes, whether the browser is used
at all, and how often Sonnet fails. It confirms nothing and compares nothing.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.util
import json
import os
import pathlib
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
CACHE = pathlib.Path.home() / ".cache" / "sanchopanza" / "free"


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nav = _load("browse_nav_e2e", HERE / "nav_e2e.py")
RESULTS = nav.base.ROOT / "docs" / "results" / "2026-10-03-browse-free"
SESSIONS = RESULTS / "free-sessions.jsonl"
REPORT = RESULTS / "free.json"
SEED = 20261003
SESSION_MAX_USD = 1.50
TIMEOUT_S = 1800
TOOLS = "WebSearch WebFetch mcp__playwright Read Grep Glob Write Edit Task Agent TodoWrite"
DISALLOWED = "Bash SendMessage ListAgents"
ANSWER = (
    " Work it out with whatever tools you need. End your reply with one line: "
    "ANSWER: <your answer>."
)
MODELS = {"SONNET": "claude-sonnet-5", "HAIKU": "claude-haiku-4-5"}


def _xor(text_b64: str, password: str) -> str:
    data = base64.b64decode(text_b64)
    key = hashlib.sha256(password.encode()).digest()
    stream = key * (len(data) // len(key)) + key[: len(data) % len(key)]
    return bytes(a ^ b for a, b in zip(data, stream, strict=True)).decode()


def browsecomp(n: int) -> list[dict[str, str]]:
    rows = list(csv.DictReader((CACHE / "browsecomp.csv").open(encoding="utf-8")))
    picked = random.Random(SEED).sample(range(len(rows)), n)
    return [
        {
            "tid": f"BC{i}",
            "question": _xor(rows[i]["problem"], rows[i]["canary"]),
            "gold": _xor(rows[i]["answer"], rows[i]["canary"]),
        }
        for i in picked
    ]


def _short(answer: str) -> bool:
    return "\n" not in answer.strip() and len(answer) <= 60


def assistantbench(n: int) -> list[dict[str, str]]:
    rows = [json.loads(line) for line in (CACHE / "ab_dev.jsonl").open(encoding="utf-8")]
    usable = [r for r in rows if _short(str(r["answer"]))]
    picked = random.Random(SEED).sample(usable, min(n, len(usable)))
    return [
        {"tid": f"AB{r['id'][:8]}", "question": r["task"], "gold": str(r["answer"])} for r in picked
    ]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", text.lower().replace(",", "")).strip()


def graded(reply: str, gold: str) -> bool:
    line = nav.answer_line(reply)
    if not line:
        return False
    got, want = _norm(line), _norm(gold)
    if re.fullmatch(r"-?\d+(\.\d+)?", want):
        numbers = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", got)]
        target = float(want)
        return any(abs(x - target) <= max(abs(target) * 0.01, 1e-9) for x in numbers)
    return want in got


def tool_calls(work: pathlib.Path) -> dict[str, int]:
    folder = pathlib.Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(work))
    counts: dict[str, int] = {}
    for path in folder.rglob("*.jsonl") if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            content = (json.loads(line).get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    counts[block["name"]] = counts.get(block["name"], 0) + 1
    return counts


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    tid, _url, question, gold = task
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-free-{tid.lower()}r{run}-"))
    settings = work / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": TOOLS.split()}}), encoding="utf-8")
    env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(SRC)}
    env.pop("TYPESAFE_API_KEY", None)
    argv = [
        shutil.which("claude") or "claude",
        "-p",
        "--model",
        MODELS[arm.split("-")[0]],
        "--settings",
        str(settings),
        "--setting-sources",
        "",
        "--mcp-config",
        str(nav.mcp.mcp_config(work)),
        "--strict-mcp-config",
        "--allowedTools",
        TOOLS,
        "--disallowedTools",
        DISALLOWED,
        "--output-format",
        "json",
        "--max-budget-usd",
        f"{SESSION_MAX_USD:g}",
        "--",
        question + ANSWER,
    ]
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=TIMEOUT_S)
        out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
    except (subprocess.TimeoutExpired, ValueError) as error:
        out = {"is_error": True, "subtype": f"runner: {error.__class__.__name__}"}
    reply = str(out.get("result") or "")
    return {
        "task": tid,
        "run": run,
        "arm": arm,
        "ok": not out.get("is_error", True),
        "subtype": out.get("subtype"),
        "success": graded(reply, gold),
        "answer": "",
        "answered": bool(nav.answer_line(reply)),
        "list_usd": float(out.get("total_cost_usd") or 0.0),
        "turns": out.get("num_turns"),
        "usd_by_model": {
            m: round(float(u.get("costUSD") or 0), 5)
            for m, u in (out.get("modelUsage") or {}).items()
        },
        "wall_s": round(time.monotonic() - started, 1),
        "tools": tool_calls(work),
        "version": nav.claude_version(work),
        "workdir": str(work),
    }


def tasks(n_bc: int, n_ab: int) -> list[tuple[str, str, str, str]]:
    items = browsecomp(n_bc) + assistantbench(n_ab)
    return [(t["tid"], "", t["question"], t["gold"]) for t in items]


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arm in sorted({r["arm"] for r in rows}):
        mine = [r for r in rows if r["arm"] == arm]
        browsed = [r for r in mine if any(k.startswith("mcp__playwright") for k in r["tools"])]
        out[arm] = {
            "sessions": len(mine),
            "right": sum(r["success"] for r in mine),
            "right_by_set": {
                s: f"{sum(r['success'] for r in mine if r['task'].startswith(s))}/"
                f"{sum(r['task'].startswith(s) for r in mine)}"
                for s in ("BC", "AB")
            },
            "mean_usd": round(statistics.mean(r["list_usd"] for r in mine), 4),
            "max_usd": round(max(r["list_usd"] for r in mine), 4),
            "median_wall_s": statistics.median(r["wall_s"] for r in mine),
            "sessions_that_opened_the_browser": len(browsed),
            "tool_totals": dict(
                sorted(
                    {
                        k: sum(r["tools"].get(k, 0) for r in mine) for r in mine for k in r["tools"]
                    }.items(),
                    key=lambda kv: -kv[1],
                )[:12]
            ),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--arm", default="SONNET")
    ap.add_argument("--ceiling", type=float, default=8.0)
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = nav.done_sessions(SESSIONS)
    code = 0
    if args.pilot:
        limits = nav.phase.Limits(session_max_usd=SESSION_MAX_USD, ceiling_usd=args.ceiling)
        plan = nav.phase.planned(tasks(6, 6), [1], (args.arm,))
        code, rows = nav.phase.run_phase(plan, rows, limits, one_session, SESSIONS)
    counted = nav.phase.counted(rows)
    if counted:
        result = report(counted)
        REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
