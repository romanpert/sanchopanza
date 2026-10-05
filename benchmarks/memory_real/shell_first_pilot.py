"""Pilot: what an agent does when its first shell write of a file is denied once with the
file's earlier record as the reason (`memory_hook.shell_first`, v6.3 candidate).

Per run: a small git repository in a scratch folder, a memory store holding one earlier request
that changed the file (recorded through the hook's own Stop from a written transcript, as a
real session leaves it), and a live `claude -p` that must edit through the shell (the file tools
are disallowed). The earlier record carries a fact the task can break (the trap); a checker runs
the repository's tests and the trap's own check after the session. Arms: `deny`
(SANCHOPANZA_MEMORY_SHELL_FIRST=deny) and `off` (v6.2: the record arrives after the write).

Caps: `--max-budget-usd` per session (CALL_CAP) and TOTAL_CAP over the pilot, checked before
each session from the sessions' own `total_cost_usd` (list price; the subscription pays).
Sessions run one at a time. `--dry` builds every run and prints the commands, calling nothing.

    python benchmarks/memory_real/shell_first_pilot.py --out DIR [--dry] [--models haiku,sonnet]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
sys.path.insert(0, str(SRC))

from sanchopanza.harness import memory_hook as mh  # noqa: E402

CALL_CAP = 0.50
TOTAL_CAP = 5.00
MODELS = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-5-5"}
PYTHON = sys.executable

SCENARIOS: dict[str, dict[str, Any]] = {
    "hex": {
        "files": {
            "calc/__init__.py": "",
            "calc/parse.py": (
                "def parse_number(text: str) -> int:\n"
                '    """An integer from text; underscores group digits (1_000)."""\n'
                '    cleaned = text.strip().replace("_", "")\n'
                "    return int(cleaned)\n"
            ),
            "tests/test_parse.py": (
                "from calc.parse import parse_number\n\n\n"
                'def test_plain():\n    assert parse_number("42") == 42\n'
            ),
        },
        "earlier_prompt": "Invoices from the Lyon office fail to import: amounts like 1_000 crash.",
        "earlier_file": "calc/parse.py",
        "earlier_old": "    cleaned = text.strip()\n",
        "earlier_new": '    cleaned = text.strip().replace("_", "")\n',
        "earlier_report": (
            "parse_number now strips underscores before int(): the Lyon office exports amounts "
            "as 1_000 and its invoice import depends on this. Keep it when changing the parser."
        ),
        "task": (
            "Make calc.parse.parse_number also accept hexadecimal literals such as 0x1F. Edit "
            "files only with shell commands (sed, python, cat >), the Edit and Write tools are "
            "off. Add a test for hex in tests/test_parse.py and run python -m pytest -q."
        ),
        "check": (
            "from calc.parse import parse_number as p\n"
            "assert p('0x1F') == 31, 'hex'\n"
            "assert p('1_000') == 1000, 'underscores (the trap)'\n"
            "assert p('0x1_F') == 31, 'underscores in hex'\n"
        ),
    },
    "rename": {
        "files": {
            "app/__init__.py": "",
            "app/settings.py": 'SETTINGS = {\n    "retry_limit": 3,\n    "timeout": 10,\n}\n',
            "app/client.py": (
                "from app.settings import SETTINGS\n\n\n"
                'def attempts() -> int:\n    return SETTINGS["retry_limit"]\n'
            ),
            "deploy/check.py": (
                'import sys\nsys.path.insert(0, ".")\nfrom app.settings import SETTINGS\n\n'
                'assert SETTINGS["retry_limit"] > 0\n'
            ),
            "tests/test_client.py": (
                "from app.client import attempts\n\n\n"
                "def test_attempts():\n    assert attempts() == 3\n"
            ),
        },
        "earlier_prompt": "The deploy job must refuse a config with no retries.",
        "earlier_file": "app/settings.py",
        "earlier_old": '    "retry_limit": 3,\n',
        "earlier_new": '    "retry_limit": 3,\n',
        "earlier_report": (
            "Added deploy/check.py, which the deploy job runs: it reads SETTINGS['retry_limit'] "
            "from app/settings.py. Any rename of that key must be made there too, or every "
            "deploy fails."
        ),
        "task": (
            "Rename the settings key retry_limit to max_retries in app/settings.py and wherever "
            "the application code uses it. Edit files only with shell commands (sed, python, "
            "cat >), the Edit and Write tools are off. Run python -m pytest -q at the end."
        ),
        "check": (
            "import subprocess, sys\n"
            "from app.settings import SETTINGS\n"
            "assert 'max_retries' in SETTINGS and 'retry_limit' not in SETTINGS, 'renamed'\n"
            "done = subprocess.run([sys.executable, 'deploy/check.py'], capture_output=True)\n"
            "assert done.returncode == 0, 'deploy check (the trap)'\n"
        ),
    },
}


def project_name(cwd: Path) -> str:
    """The folder Claude Code keeps a project's transcripts in."""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "p", "GIT_AUTHOR_EMAIL": "p@p",
           "GIT_COMMITTER_NAME": "p", "GIT_COMMITTER_EMAIL": "p@p"}  # fmt: skip
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


def earlier_transcript(s: dict[str, Any], cwd: Path) -> list[dict[str, Any]]:
    path = f"{cwd.as_posix()}/{s['earlier_file']}"
    stamp = "2026-09-29T10:00:00Z"
    use_read = {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": path}}
    use_edit = {"type": "tool_use", "id": "t2", "name": "Edit",
                "input": {"file_path": path, "old_string": s["earlier_old"],
                          "new_string": s["earlier_new"]}}  # fmt: skip

    def result(n: str, text: str) -> dict[str, Any]:
        return {"type": "user", "timestamp": stamp, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": n, "content": text}]}}  # fmt: skip

    def assistant(block: dict[str, Any]) -> dict[str, Any]:
        return {"type": "assistant", "timestamp": stamp,
                "message": {"role": "assistant", "content": [block]}}  # fmt: skip

    return [
        {"type": "user", "cwd": str(cwd), "timestamp": stamp,
         "message": {"role": "user", "content": s["earlier_prompt"]}},
        assistant(use_read), result("t1", s["files"][s["earlier_file"]]),
        assistant(use_edit), result("t2", "The file has been updated."),
        assistant({"type": "text", "text": s["earlier_report"]}),
    ]  # fmt: skip


def build(run: Path, s: dict[str, Any]) -> Path:
    """The repository and its memory store; the repository's path."""
    repo = run / "repo"
    for rel, text in s["files"].items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "start")
    old = run / "fake-projects" / project_name(repo) / "earlier.jsonl"
    old.parent.mkdir(parents=True)
    old.write_text("".join(json.dumps(e) + "\n" for e in earlier_transcript(s, repo)), "utf-8")
    os.environ["SANCHOPANZA_MEMORY_STORE"] = str(run / "store")
    os.environ["SANCHOPANZA_MEMORY_TREE"] = "off"
    mh.handle({"hook_event_name": "Stop", "session_id": "earlier",
               "transcript_path": str(old), "cwd": str(repo)})  # fmt: skip
    for name in {project_name(repo), project_name(repo)[:1].lower() + project_name(repo)[1:]}:
        target = run / "store" / name
        if not target.exists():
            source = run / "store" / project_name(repo)
            target.mkdir(parents=True)
            for f in source.iterdir():
                if f.is_file():
                    (target / f.name).write_bytes(f.read_bytes())
    return repo


def settings(run: Path) -> str:
    hook = {"type": "command", "command": f'"{Path(PYTHON).as_posix()}" -m '
            "sanchopanza.harness.memory_hook"}  # fmt: skip
    events = {
        "UserPromptSubmit": "",
        "Stop": "",
        "SessionEnd": "",
        "PreToolUse": "Bash|PowerShell",
        "PostToolUse": "Read|Edit|MultiEdit|Write|NotebookEdit|Bash|PowerShell",
    }
    return json.dumps({"hooks": {e: [{"matcher": m, "hooks": [hook]}] for e, m in events.items()}})


def session(run: Path, repo: Path, s: dict[str, Any], model: str, arm: str,
            dry: bool) -> dict[str, Any]:  # fmt: skip
    env = {**os.environ, "PYTHONPATH": str(SRC), "SANCHOPANZA_MEMORY_STORE": str(run / "store"),
           "SANCHOPANZA_MEMORY_STORE_LOG": str(run / "hook-log.jsonl"),
           "SANCHOPANZA_MEMORY_SHELL_FIRST": arm, "SANCHOPANZA_MEMORY_SELECT": "bm25",
           "SANCHOPANZA_MEMORY_PROMPT": "off"}  # fmt: skip
    for name in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY", "SANCHOPANZA_PROVIDER"):
        env.pop(name, None)
    cmd = ["claude", "-p", s["task"], "--model", MODELS[model], "--output-format", "stream-json",
           "--verbose", "--max-budget-usd", f"{CALL_CAP:.2f}", "--settings", settings(run),
           "--allowedTools", "Bash", "Read", "Glob", "Grep",
           "--disallowedTools", "Edit", "Write", "MultiEdit", "NotebookEdit"]  # fmt: skip
    if dry:
        return {"dry": True, "cmd": cmd[:6]}
    started = time.time()
    with (run / "stream.jsonl").open("w", encoding="utf-8") as out:
        done = subprocess.run(cmd, cwd=repo, env=env, stdout=out, stderr=subprocess.PIPE,
                              text=True, timeout=900, check=False)  # fmt: skip
    return {"returncode": done.returncode, "stderr": done.stderr[-500:],
            "seconds": round(time.time() - started, 1)}  # fmt: skip


def read_stream(run: Path) -> dict[str, Any]:
    cost, turns, final, denied, bash_after, limit = 0.0, 0, "", 0, 0, False
    commands: list[str] = []
    for line in (run / "stream.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "result":
            cost, turns, final = e.get("total_cost_usd") or 0.0, e.get("num_turns") or 0, str(
                e.get("result") or "")  # fmt: skip
        blocks = (e.get("message") or {}).get("content") or []
        for b in blocks if isinstance(blocks, list) else []:
            if b.get("type") == "tool_use" and b.get("name") == "Bash":
                commands.append(str((b.get("input") or {}).get("command"))[:300])
                bash_after += denied > 0
            if b.get("type") == "tool_result" and "sanchopanza memory] Not run yet" in str(
                    b.get("content")):  # fmt: skip
                denied += 1
        limit = limit or "usage limit" in line.lower() or '"status":429' in line
    return {"cost": cost, "turns": turns, "denied": denied, "bash_after_deny": bash_after,
            "final": final[-600:], "limit_hit": limit, "commands": len(commands)}  # fmt: skip


def check(repo: Path, s: dict[str, Any]) -> dict[str, Any]:
    tests = subprocess.run([PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo,
                           capture_output=True, text=True, timeout=300)  # fmt: skip
    trap = subprocess.run([PYTHON, "-c", s["check"]], cwd=repo, capture_output=True, text=True,
                          timeout=120)  # fmt: skip
    return {
        "tests_pass": tests.returncode == 0,
        "check_pass": trap.returncode == 0,
        "check_error": trap.stderr.strip().splitlines()[-1:] if trap.returncode else [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--models", default="haiku,sonnet")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    spent = 0.0
    rows: list[dict[str, Any]] = []
    plan = [(sc, m, arm, r) for r in range(args.repeats) for m in args.models.split(",")
            for sc in SCENARIOS for arm in ("deny", "off")]  # fmt: skip
    for sc, model, arm, rep in plan:
        if spent + CALL_CAP > TOTAL_CAP:
            print(f"stop: {spent:.2f} USD spent, the next session could pass {TOTAL_CAP}")
            break
        run = out / f"{sc}-{model}-{arm}-{rep}"
        repo = build(run, SCENARIOS[sc])
        meta = session(run, repo, SCENARIOS[sc], model, arm, args.dry)
        row = {"scenario": sc, "model": model, "arm": arm, "repeat": rep, **meta}
        if not args.dry:
            row = {**row, **read_stream(run), **check(repo, SCENARIOS[sc])}
            spent += float(row["cost"] or 0.0)
            if row["limit_hit"]:
                print("stop: the subscription's usage limit", flush=True)
                rows.append(row)
                break
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k not in ("final", "stderr")}),
              f"spent {spent:.2f}", flush=True)  # fmt: skip
    (out / "pilot.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
