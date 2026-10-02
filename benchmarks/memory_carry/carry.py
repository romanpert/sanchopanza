"""Carry pilot: does a fact the person said in an earlier session survive into a new one?

Per scene (`scenes.py`) and arm, a fresh git repository; session 1 (`claude -p`, the scene's
`first` prompt: a small task with the fact said in passing), a commit, then session 2, a NEW
session (no --resume) with the scene's `second` prompt, which tempts breaking the fact. After it:
the repository's tests, the scene's `task` check and its `fact` check.

Arms: `N`, Claude Code as it ships, its own auto memory on (it is by default, keyed by the git
repository, so session 2 loads what session 1 saved); `M`, the same plus sanchopanza's memory
hooks as `sanchopanza install --memory` writes them (`install.MEMORY_HOOKS`), with the decider
when TYPESAFE_API_KEY is set. Both arms get the same tools, model, prompts and caps.

Caps: `--max-budget-usd` per session (CALL_CAP) and TOTAL_CAP over the run, checked before each
pair from the sessions' own `total_cost_usd` (list price; the subscription pays). Sessions run
one at a time; a usage limit stops the run. `--dry` builds every repository and prints what it
would run, calling nothing.

    python benchmarks/memory_carry/carry.py --out DIR [--dry] [--models sonnet] [--repeats 1]
        [--scenes pilot|held|all|a,b] [--total-cap USD]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SRC))

from scenes import SCENES as PILOT  # noqa: E402
from scenes_held import HELD  # noqa: E402

from sanchopanza.harness.install import MEMORY_HOOKS  # noqa: E402

CALL_CAP = 0.60
TOTAL_CAP = 9.00  # default; --total-cap raises it for a run the owner approved
SCENES = {**PILOT, **HELD}
SETS = {"pilot": list(PILOT), "held": list(HELD), "all": list(SCENES)}
MODELS = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-5-5"}
PYTHON = sys.executable
TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep"]
PROJECTS = Path.home() / ".claude" / "projects"


def project_name(cwd: Path) -> str:
    """The folder Claude Code keeps a project's transcripts and auto memory in."""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))


def git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.org",
           "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.org"}  # fmt: skip
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


def build(run: Path, scene: dict[str, Any]) -> Path:
    repo = run / "repo"
    for rel, text in scene["files"].items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "start")
    return repo


def settings(run: Path, arm: str, keyfile: Path) -> str:
    if arm == "N":
        return "{}"
    launcher = (HERE / "carry_hook.py").as_posix()
    hook = {"type": "command", "command": f'"{Path(PYTHON).as_posix()}" "{launcher}" '
            f'"{run.as_posix()}" "{keyfile.as_posix()}"'}  # fmt: skip
    return json.dumps({"hooks": {event: [{"matcher": matcher, "hooks": [hook]}]
                                 for event, matcher in MEMORY_HOOKS.items()}})  # fmt: skip


def environment() -> dict[str, str]:
    """The agent's environment, the same in both arms: no API key (the subscription pays), no
    TypeSafe key (only the M arm's hook reads it, from a file), Claude Code's own memory on."""
    drop = ("ANTHROPIC_API_KEY", "TYPESAFE_", "SANCHOPANZA_", "CLAUDE_CODE_DISABLE_AUTO_MEMORY")
    return {k: v for k, v in os.environ.items() if not k.startswith(drop)}


def keyfile_from_indagis(out: Path) -> Path:
    """The TypeSafe key for the M arm's hook, from the owner's Indagis .env; never printed, and
    removed when the run ends."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    env_file = Path(r"C:\Users\roman\Desktop\proyectos\apps\indagis\.env")
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise SystemExit("no TypeSafe key: the M arm would run without its decider")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "typesafe.key"
    path.write_text(key, encoding="utf-8")
    return path


def session(run: Path, repo: Path, prompt: str, model: str, arm: str, tag: str,
            keyfile: Path, dry: bool) -> dict[str, Any]:  # fmt: skip
    cmd = ["claude", "-p", prompt, "--model", MODELS[model], "--output-format", "stream-json",
           "--verbose", "--max-budget-usd", f"{CALL_CAP:.2f}",
           "--settings", settings(run, arm, keyfile), "--allowedTools", *TOOLS]  # fmt: skip
    if dry:
        return {"dry": True}
    started = time.time()
    with (run / f"{tag}.jsonl").open("w", encoding="utf-8") as out:
        done = subprocess.run(cmd, cwd=repo, env=environment(), stdout=out,
                              stderr=subprocess.PIPE, text=True, timeout=900,
                              check=False)  # fmt: skip
    seen = read_stream(run / f"{tag}.jsonl")
    return {"returncode": done.returncode, "stderr": done.stderr[-300:],
            "seconds": round(time.time() - started, 1), **seen}  # fmt: skip


def read_stream(path: Path) -> dict[str, Any]:
    cost, turns, final, limit, tools = 0.0, 0, "", False, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            cost = float(event.get("total_cost_usd") or 0.0)
            turns, final = event.get("num_turns") or 0, str(event.get("result") or "")
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        tools += sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use") \
            if isinstance(content, list) else 0
        limit = limit or "usage limit" in line.lower() or '"status":429' in line
    return {"cost": cost, "turns": turns, "tools": tools, "final": final[-500:],
            "limit_hit": limit}  # fmt: skip


def passes(repo: Path, code: str) -> bool | None:
    if not code:
        return None
    done = subprocess.run([PYTHON, "-c", code], cwd=repo, capture_output=True, timeout=120)
    return done.returncode == 0


def check(repo: Path, scene: dict[str, Any]) -> dict[str, Any]:
    tests = subprocess.run([PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo,
                           capture_output=True, text=True, timeout=300)  # fmt: skip
    return {"tests_pass": tests.returncode == 0, "task_pass": passes(repo, scene["task"]),
            "fact_kept": passes(repo, scene["fact"])}  # fmt: skip


def native_memory(repo: Path) -> list[str]:
    """Files Claude Code's own auto memory holds for this repository."""
    wanted = project_name(repo).casefold()
    folders = [d for d in PROJECTS.glob("*/memory") if d.parent.name.casefold() == wanted]
    return sorted(str(p.relative_to(PROJECTS)) for d in folders for p in d.rglob("*")
                  if p.is_file())  # fmt: skip


def given(run: Path) -> list[str]:
    """Records sanchopanza's memory gave in session 2 (from its hook log)."""
    path = run / "hook-log.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [f"{r.get('event')}:{','.join(r['shown'])}" for r in rows if r.get("shown")]


def pair(out: Path, name: str, model: str, arm: str, rep: int, keyfile: Path,
         dry: bool) -> dict[str, Any]:  # fmt: skip
    run = out / f"{name}-{model}-{arm}-{rep}"
    scene = SCENES[name]
    repo = build(run, scene)
    first = session(run, repo, scene["first"], model, arm, "session-1", keyfile, dry)
    row: dict[str, Any] = {"scene": name, "model": model, "arm": arm, "repeat": rep}
    if dry:
        return {**row, "dry": True, "repo": str(repo)}
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "wip")
    after_first = native_memory(repo)
    second = {} if first["limit_hit"] else session(run, repo, scene["second"], model, arm,
                                                   "session-2", keyfile, dry)  # fmt: skip
    return {**row, "first": first, "second": second, "native_after_1": after_first,
            "given": given(run), **(check(repo, scene) if second else {}),
            "cost": first["cost"] + float(second.get("cost") or 0.0),
            "limit_hit": first["limit_hit"] or bool(second.get("limit_hit"))}  # fmt: skip


def earlier(out: Path) -> list[dict[str, Any]]:
    path = out / "carry.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--models", default="sonnet")
    parser.add_argument("--scenes", default="pilot", help="pilot, held, all or names")
    parser.add_argument("--total-cap", type=float, default=TOTAL_CAP)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--continue", dest="carry_on", action="store_true",
                        help="keep the rows of carry.json; a pair cut by the runner runs again")
    args = parser.parse_args(argv)
    out = Path(args.out)
    plan = [(name, model, arm, rep) for rep in range(args.repeats)
            for model in args.models.split(",")
            for name in SETS.get(args.scenes, args.scenes.split(","))
            for arm in ("N", "M")]  # fmt: skip
    keyfile = out / "typesafe.key" if args.dry else keyfile_from_indagis(out)
    try:
        run_plan(out, plan, keyfile, args.dry, args.total_cap, args.carry_on)
    finally:
        keyfile.unlink(missing_ok=True)
    return 0


def run_plan(out: Path, plan: list[tuple[str, str, str, int]], keyfile: Path, dry: bool,
             total_cap: float, carry_on: bool = False) -> None:  # fmt: skip
    rows = earlier(out) if carry_on else []
    done = {(r["scene"], r["model"], r["arm"], r["repeat"]) for r in rows}
    spent = sum(float(r.get("cost") or 0.0) for r in rows)
    for name, model, arm, rep in plan:
        if (name, model, arm, rep) in done:
            continue
        cut = out / f"{name}-{model}-{arm}-{rep}"
        if cut.exists():  # a pair the runner itself cut (no row): it runs again, whole
            shutil.rmtree(cut)
        if spent + 2 * CALL_CAP > total_cap:
            print(f"stop: {spent:.2f} USD spent, the next pair could pass {total_cap}", flush=True)
            break
        row = pair(out, name, model, arm, rep, keyfile, dry)
        spent += float(row.get("cost") or 0.0)
        rows.append(row)
        keys = ("scene", "model", "arm", "tests_pass", "task_pass", "fact_kept", "cost",
                "given", "native_after_1")
        brief = {k: row.get(k) for k in keys}
        print(json.dumps(brief), f"spent {spent:.2f}", flush=True)
        (out / "carry.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        if row.get("limit_hit"):
            print("stop: the subscription's usage limit", flush=True)
            break


if __name__ == "__main__":
    raise SystemExit(main())
