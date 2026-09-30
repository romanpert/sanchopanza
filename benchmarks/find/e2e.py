"""find_in_repo end to end: does an agent localise an issue better, or cheaper, with it?

    python benchmarks/find/e2e.py plan                    # the sample and the cost ceiling, free
    python benchmarks/find/e2e.py run --arms N,F          # Claude Code sessions (subscription)
    python benchmarks/find/e2e.py score                   # verdicts, free

The retrieval result (`docs/results/2026-09-29-find/`) measured the tool alone, from the issue
text, before anything is read. It said what it does not show: whether an agent that already
has `Grep`, `Glob` and `Read` does better with it. This runs the agent.

Per instance and arm, a fresh git worktree at the issue's base commit and one headless Claude
Code session (Haiku 4.5, subscription, `--setting-sources project --strict-mcp-config
--permission-mode dontAsk`, read-only tools). The agent reads the issue and ends with the files
it would change, most likely first. Nothing is edited.

- `N`: `Read`, `Grep`, `Glob`.
- `F`: the same, plus `find_in_repo` (`python -m sanchopanza.harness.mcp --tools find`, the
  BM25 shortlist judged by Jev). The tool is offered, never imposed.

The label is SWE-bench's: the files the accepted patch edits. Instances: SWE-bench Verified,
seeded, disjoint from the 117 of the retrieval run and the 48 of its dev sample.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))

import ceiling  # noqa: E402
import swebench  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-09-30-find-e2e"
ROOT = Path.home() / ".cache" / "sanchopanza" / "find-e2e"
PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")
MODEL = "claude-haiku-4-5-20251001"
SEED = 20260930
PER_REPO = 4
SESSION_CAP_USD = 0.30  # --max-budget-usd of each session
CEILING_USD = 7.0  # list price of every session of the run; registered in prereg-find-e2e.md
JEV_CAP_USD = 0.30  # Jev inside the MCP server, summed from the journals between sessions
MAX_TURNS = 25
TOOLS = {"N": ["Read", "Grep", "Glob"],
         "F": ["Read", "Grep", "Glob", "mcp__sanchopanza__find_in_repo"]}  # fmt: skip
PROMPT = (
    "You are in a checkout of {repo}. Here is an issue reported against it:\n\n<issue>\n"
    "{issue}\n</issue>\n\nFind the source files that must change to fix this issue. Do not edit "
    "anything and do not write a patch. When you are sure, end your reply with one line:\n"
    "FILES: <up to five repository-relative paths, most likely first, comma-separated>"
)
_FILES = re.compile(r"^\s*\**FILES\**\s*:\s*(.+)$", re.M | re.I)
_lock = threading.Lock()
_spent = {"usd": 0.0, "jev": 0.0, "reserved": 0.0}


def sample() -> list[dict[str, Any]]:
    """PER_REPO instances per repository, seeded, none from the retrieval run or its dev set."""
    import random
    from collections import defaultdict

    import pyarrow.parquet as pq

    used = {r["instance_id"] for r in swebench.instances()}
    used |= {r["instance_id"] for r in ceiling.dev_instances(set(used))}
    rows = [r for r in pq.read_table(swebench.DATA / "verified.parquet").to_pylist()
            if r["instance_id"] not in used]  # fmt: skip
    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["instance_id"]):
        by_repo[row["repo"]].append(row)
    rng = random.Random(SEED)
    out = []
    for repo in sorted(by_repo):
        out += rng.sample(by_repo[repo], min(PER_REPO, len(by_repo[repo])))
    return sorted(out, key=lambda r: r["instance_id"])


def worktree(row: dict[str, Any], arm: str) -> Path:
    """A fresh detached worktree of the instance's base commit, apart from every other run."""
    clone = swebench.clone_dir(row["repo"])
    target = ROOT / "work" / f"{row['instance_id']}-{arm}"
    if target.exists():
        subprocess.run(["git", "-C", str(clone), "worktree", "remove", "--force", str(target)],
                       capture_output=True)  # fmt: skip
        shutil.rmtree(target, ignore_errors=True)
    subprocess.run(["git", "-C", str(clone), "worktree", "prune"], check=True)
    subprocess.run(["git", "-C", str(clone), "worktree", "add", "-q", "--detach", str(target),
                    row["base_commit"]], check=True)  # fmt: skip
    return target


def mcp_config(art: Path) -> Path:
    config = {"mcpServers": {"sanchopanza": {
        "command": PYTHON, "args": ["-m", "sanchopanza.harness.mcp", "--tools", "find"],
        "env": {"PYTHONPATH": str(REPO / "src"), "SANCHOPANZA_JOURNAL": str(art / "journal.jsonl"),
                "TYPESAFE_API_KEY": os.environ.get("TYPESAFE_API_KEY", "")},
    }}}  # fmt: skip
    path = art / "mcp.json"
    path.write_text(json.dumps(config, indent=1), encoding="utf-8")
    return path


def command(row: dict[str, Any], arm: str, art: Path) -> list[str]:
    prompt = PROMPT.format(repo=row["repo"], issue=row["problem_statement"].strip())
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--max-budget-usd", str(SESSION_CAP_USD),
           "--max-turns", str(MAX_TURNS), "--output-format", "stream-json", "--verbose",
           "--setting-sources", "project", "--strict-mcp-config", "--permission-mode", "dontAsk",
           "--allowedTools", *TOOLS[arm]]  # fmt: skip
    if arm == "F":
        cmd += ["--mcp-config", str(mcp_config(art))]
    return cmd


def child_env() -> dict[str, str]:
    """The subscription, not a key; and none of the coordinating session's own settings."""
    drop = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "CLAUDE_EFFORT", "CLAUDECODE", "SANCHOPANZA_")
    return {k: v for k, v in os.environ.items() if not k.startswith(drop)} | {
        "MAX_THINKING_TOKENS": "0"
    }


def files_claimed(text: str) -> list[str]:
    found = _FILES.findall(text or "")
    if not found:
        return []
    return [p.strip().strip("`'\"").lstrip("./") for p in found[-1].split(",") if p.strip()][:5]


def jev_spent(art: Path) -> float:
    path = art / "journal.jsonl"
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            total += float(json.loads(line).get("cost_usd") or 0.0)
        except (ValueError, AttributeError):
            continue
    return total


def _result(stream: Path) -> dict[str, Any]:
    for line in reversed(stream.read_text(encoding="utf-8").splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            return event
    return {}


def _tool_calls(stream: Path) -> list[str]:
    calls = []
    for line in stream.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append(str(block.get("name")))
    return calls


def one(row: dict[str, Any], arm: str) -> dict[str, Any] | None:
    name = f"{row['instance_id']}-{arm}"
    art = ROOT / "runs" / name
    if (art / "row.json").exists():
        return json.loads((art / "row.json").read_text(encoding="utf-8"))
    stream = art / "stream.jsonl"
    if stream.exists() and float(_result(stream).get("total_cost_usd") or 0.0) > 0:
        sys.stderr.write(f"{name}: ran and was paid, not rerun\n")
        return None
    with _lock:
        over = _spent["usd"] + _spent["reserved"] + SESSION_CAP_USD > CEILING_USD
        if over or _spent["jev"] >= JEV_CAP_USD:
            sys.stderr.write(f"ceiling: skip {name}\n")
            return None
        _spent["reserved"] += SESSION_CAP_USD
    art.mkdir(parents=True, exist_ok=True)
    work = worktree(row, arm)
    started = time.time()
    try:
        with stream.open("w", encoding="utf-8") as out:
            subprocess.run(
                command(row, arm, art),
                cwd=work,
                env=child_env(),
                stdout=out,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                timeout=1200,
            )
    except subprocess.TimeoutExpired:
        pass
    result = _result(stream)
    calls = _tool_calls(stream)
    usage = result.get("usage") or {}
    claimed = files_claimed(str(result.get("result") or ""))
    gold = swebench.gold_files(row["patch"])
    record = {
        "instance": row["instance_id"], "repo": row["repo"], "arm": arm,
        "seconds": round(time.time() - started, 1),
        "cost_usd": float(result.get("total_cost_usd") or 0.0), "jev_usd": jev_spent(art),
        "subtype": result.get("subtype"), "turns": result.get("num_turns"),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "calls": {t: calls.count(t) for t in sorted(set(calls))}, "claimed": claimed,
        "gold": gold, **swebench.hits(claimed, gold),
    }  # fmt: skip
    with _lock:
        _spent["reserved"] -= SESSION_CAP_USD
        _spent["usd"] += record["cost_usd"]
        _spent["jev"] += record["jev_usd"]
    (art / "row.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    sys.stderr.write(f"{name}: {record['cost_usd']:.3f} USD, hit@1={record.get('any@1')}, "
                     f"total {_spent['usd']:.2f} / Jev {_spent['jev']:.4f}\n")  # fmt: skip
    return record


def spent_so_far() -> tuple[float, float]:
    usd = jev = 0.0
    for art in (ROOT / "runs").glob("*"):
        if (art / "stream.jsonl").exists():
            usd += float(_result(art / "stream.jsonl").get("total_cost_usd") or 0.0)
        jev += jev_spent(art)
    return usd, jev


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="e2e.py")
    parser.add_argument("step", choices=["plan", "run", "score"])
    parser.add_argument("--arms", default="N,F")
    parser.add_argument("--only", default="")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args(argv)
    rows = sample()
    if args.only:
        rows = [r for r in rows if r["instance_id"] in args.only.split(",")]
    arms = [a for a in args.arms.split(",") if a in TOOLS]
    if args.step == "plan":
        sys.stdout.write(json.dumps({
            "instances": len(rows), "arms": arms, "sessions": len(rows) * len(arms),
            "ceiling_usd": CEILING_USD, "session_cap_usd": SESSION_CAP_USD,
            "jev_cap_usd": JEV_CAP_USD, "ids": [r["instance_id"] for r in rows],
        }, indent=1) + "\n")  # fmt: skip
        return 0
    if args.step == "score":
        import e2e_score

        sys.stdout.write(json.dumps(e2e_score.summary(ROOT / "runs", OUT), indent=1) + "\n")
        return 0
    if "F" in arms and not os.environ.get("TYPESAFE_API_KEY"):
        parser.error("arm F needs TYPESAFE_API_KEY (the judge)")
    _spent["usd"], _spent["jev"] = spent_so_far()
    jobs = [(r, a) for r in rows for a in arms]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        done = [x for x in pool.map(lambda j: one(*j), jobs) if x]
    sys.stderr.write(f"{len(done)} sessions, {_spent['usd']:.2f} USD list, "
                     f"Jev {_spent['jev']:.4f}\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
