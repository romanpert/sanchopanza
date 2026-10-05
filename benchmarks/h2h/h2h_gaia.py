"""Head to head on GAIA: Claude Code alone (CC) against Claude Code with sanchopanza (SP).

python benchmarks/h2h/h2h_gaia.py --plan [--models SONNET] [--levels 1]   # free: the run order
python benchmarks/h2h/h2h_gaia.py --preflight                             # free: pin, set, hook
python benchmarks/h2h/h2h_gaia.py --check-models                          # free: ids in the pin
python benchmarks/h2h/h2h_gaia.py --live --models HAIKU --limit 2 --ceiling 2    # PAID
python benchmarks/h2h/h2h_gaia.py --review                                # free: misses to read
python benchmarks/h2h/h2h_gaia.py --verdict TASK ARM RUN yes|no           # a hand grade
python benchmarks/h2h/h2h_gaia.py                                         # free: the report

One headless Claude Code session per task, arm and model, the way people use it: the prompt is
the question, where its attached file is (copied into the session's own folder under a neutral
name, since GAIA names files by task id) and GAIA's own instruction for the final answer. Claude
Code's normal tools, Bash included (GAIA needs computing and reading files); no MCP server, the
scheduling tools off.

Each session is a clean user (`gaia_arms.py`): its own empty CLAUDE_CONFIG_DIR, the
subscription's token, `--setting-sources user`, and its folders under `RUNS` (outside the home
folder, whose `.claude` the upward CLAUDE.md search would load). CC is that and nothing else;
SP adds what `sanchopanza install` writes by default into that user folder (`SP_USER_SETTINGS`,
checked after a real install from a frozen copy of `src`) and the TypeSafe key.

Both arms deny the hosts that serve the set: WebFetch through the session's deny rules, and any
tool through a PreToolUse hook that reads the call's whole input (`deny_hook.py`), since Bash
could `curl` them. A session whose tool results say "GAIA" or the task id is marked `leak` and
read by hand.

Grading is GAIA's own `question_scorer` (`gaia_scorer.py`) on the last FINAL ANSWER; misses it
might have got wrong are listed by `--review` and a hand verdict sits beside the official one.

Money: every session has its model's cap (`CAPS`, passed as --max-budget-usd), the phase stops
before a session whose cap would cross the ceiling (benchmarks/browse/phase.py), and the ceiling
cannot be set above `MAX_CEILING_USD` without editing this file. A 429, "weekly limit" or "hit
your limit" stops the phase at once (STOP-LIMIT) and the session is recorded as not run. Rows
keep answers, so they live in ~/.cache/sanchopanza/gaia/h2h, never in the repository; the
report holds counts and task ids only. Resuming skips what is done. Claude Code is pinned: the
launcher (`launch.ps1`) puts the pinned 2.1.287 first on PATH and starts the runner through WMI
in its own process group (CreateFlags 512); `--live` ignores SIGINT.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase = _load("browse_phase", ROOT / "benchmarks" / "browse" / "phase.py")
data = _load("h2h_gaia_data", HERE / "gaia_data.py")
scorer = _load("h2h_gaia_scorer", HERE / "gaia_scorer.py")
reading = _load("h2h_gaia_session", HERE / "gaia_session.py")
deny_hook = _load("h2h_deny_hook", HERE / "deny_hook.py")
arms = _load("h2h_gaia_arms", HERE / "gaia_arms.py")
stats = _load("h2h_gaia_stats", HERE / "gaia_stats.py")

PRIVATE = data.CACHE / "h2h"  # rows keep the agents' answers: never in the repository
RESULTS = ROOT / "docs" / "results" / "2026-10-05-h2h-gaia"
# Session folders (work, user config, side logs): outside the home folder, never in the repo.
RUNS = pathlib.Path("C:/sp-runs/h2h")
DEV_IDS = HERE / "gaia-dev-ids.txt"  # the dev draw: out of every confirmation
DEV_SEED = 20261005
DEV_SIZE = 20
PHASE_CEILINGS = {"dev": 25.0}  # USD at list; a phase named here cannot be given more

CLAUDE_VERSION = "2.1.287"
PIN = pathlib.Path(
    "C:/Users/roman/AppData/Local/Temp/claude/c--Users-roman-Desktop-proyectos-apps-indagis/"
    "ed2adcce-a92b-4af9-bb31-96872de0c1cd/scratchpad/pin/claude.exe"
)
MODELS = {
    "FABLE": "claude-fable-5-1",
    "OPUS": "claude-opus-5-5",
    "SONNET": "claude-sonnet-5-5",
    "HAIKU": "claude-haiku-4-5-20251001",
}
# Per-session caps, USD at list. Sonnet's is the FRAMES pilot's (its sessions averaged 0.23 and
# none hit 1.50); the others scale it by the model's price, Haiku with a floor.
CAPS = {"FABLE": 6.00, "OPUS": 3.00, "SONNET": 1.50, "HAIKU": 0.75}
ARMS = ("CC", "SP")
DEFAULT_CEILING_USD = 10.0
MAX_CEILING_USD = 150.0  # above this, edit the file: the owner's rule is to ask past 10 USD
TIMEOUT_S = 2400
TOOLS = "Bash Read Grep Glob Write Edit NotebookEdit WebSearch WebFetch Task Agent TodoWrite"
DISALLOWED = "SendMessage ListAgents ScheduleWakeup CronCreate RemoteTrigger"
DENY = tuple(f"WebFetch(domain:{host})" for host in deny_hook.DENIED_HOSTS)
HOOK_TIMEOUT_S = 15
# GAIA's own instruction (Mialon et al., 2023, the leaderboard's system prompt), kept verbatim.
FORMAT = (
    "Finish your answer with the following template: FINAL ANSWER: [YOUR FINAL ANSWER]. "
    "YOUR FINAL ANSWER should be a number OR as few words as possible OR a comma separated list "
    "of numbers and/or strings. If you are asked for a number, don't use comma to write your "
    "number neither use units such as $ or percent sign unless specified otherwise. If you are "
    "asked for a string, don't use articles, neither abbreviations (e.g. for cities), and write "
    "the digits in plain text unless specified otherwise. If you are asked for a comma separated "
    "list, apply the above rules depending of whether the element to be put in the list is a "
    "number or a string."
)
LIMIT_MARKER = "usage limit: hit your limit"


# --- arms ---------------------------------------------------------------------------------------


def split_arm(arm: str) -> tuple[str, str]:
    """An arm label, e.g. SONNET-CC, as (model key, arm)."""
    model, _, brazo = arm.rpartition("-")
    if model not in MODELS or brazo not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    return model, brazo


def hook_command() -> str:
    return f'"{pathlib.Path(sys.executable).as_posix()}" "{(HERE / "deny_hook.py").as_posix()}"'


def base_settings() -> dict[str, Any]:
    """What both arms share: the allow list, the deny rules and the deny hook."""
    hook = {"type": "command", "command": hook_command(), "timeout": HOOK_TIMEOUT_S}
    return {
        "permissions": {"allow": TOOLS.split(), "deny": list(DENY)},
        "hooks": {"PreToolUse": [{"matcher": "", "hooks": [hook]}]},
    }


def settings_for(brazo: str) -> dict[str, Any]:
    """An arm's settings, by source: `flag` is the `--settings` file (the same in both arms),
    `user` what its CLAUDE_CONFIG_DIR/settings.json holds (nothing for CC; for SP exactly what
    `sanchopanza install` writes by default, `gaia_arms.SP_USER_SETTINGS`). The arms differ in
    `user`, the SP skill beside it and `gaia_arms.session_env`, and nowhere else."""
    if brazo == "CC":
        return {"flag": base_settings(), "user": {}}
    if brazo == "SP":
        return {"flag": base_settings(), "user": arms.SP_USER_SETTINGS}
    raise ValueError(f"unknown arm {brazo!r}")


# --- prompt -------------------------------------------------------------------------------------


def neutral_name(file_name: str) -> str:
    """GAIA names an attachment by its task id: the copy is `attachment.<ext>`."""
    ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
    return f"attachment.{ext}" if ext else "attachment"


def prompt(task: Any, attached: pathlib.Path | None) -> str:
    parts = [task.question.strip()]
    if attached is not None:
        parts.append(f"The attached file is at {attached} (in your working directory).")
    parts.append(FORMAT)
    return "\n\n".join(parts)


def argv_for(model: str, settings: pathlib.Path, mcp: pathlib.Path, cap: float, text: str) -> list:
    return [
        shutil.which("claude") or "claude", "-p", "--model", MODELS[model],
        "--settings", str(settings), "--setting-sources", arms.SETTING_SOURCES,
        "--mcp-config", str(mcp), "--strict-mcp-config",
        "--allowedTools", TOOLS, "--disallowedTools", DISALLOWED,
        "--output-format", "json", "--max-budget-usd", f"{cap:g}", "--", text,
    ]  # fmt: skip


# --- one session --------------------------------------------------------------------------------


def run_claude(
    argv: list[str], work: pathlib.Path, side: pathlib.Path, env: dict[str, str]
) -> tuple[dict, str]:
    try:
        done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=TIMEOUT_S)
        stderr = done.stderr.decode("utf-8", errors="replace")
        out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
    except (subprocess.TimeoutExpired, ValueError) as error:
        stderr, out = "", {"is_error": True, "subtype": f"runner: {error.__class__.__name__}"}
    (side / "stderr.txt").write_text(stderr, encoding="utf-8")
    return out, stderr


def limited(reply: str, stderr: str, is_error: bool) -> bool:
    if phase.usage_limited({"answer": reply}) or "weekly limit" in f"{reply} {stderr}".lower():
        return True
    return is_error and bool(re.search(r"\b429\b|rate.?limit", f"{reply} {stderr}", re.I))


def grade_fields(answer: str | None, gold: str) -> dict[str, Any]:
    return {
        "final_answer": answer,
        "ok_oficial": scorer.question_scorer(answer, gold),
        "review": scorer.needs_review(answer, gold),
    }


def build_row(task: Any, run: int, arm: str, out: Mapping[str, Any], stderr: str,
              work: pathlib.Path, side: pathlib.Path, wall_s: float,
              projects: pathlib.Path | None = None) -> dict[str, Any]:  # fmt: skip
    model, brazo = split_arm(arm)
    folder = reading.folder_of(work, projects)
    reply = str(out.get("result") or "")
    answer = scorer.final_answer(reply)
    if answer is None:  # a cap or an error can end the session before its last reply
        texts = [t for t in reading.last_assistant_texts(folder) if scorer.final_answer(t)]
        answer = scorer.final_answer(texts[-1]) if texts else None
    usd = float(out.get("total_cost_usd") or 0.0)
    is_error = bool(out.get("is_error", True))
    leaks = reading.leaks(folder, task.task_id)
    return {
        "task": task.task_id, "task_id": task.task_id, "level": task.level,
        "attachment": task.kind, "video": task.video, "run": run, "arm": arm,
        "brazo": brazo, "model_key": model, "model": MODELS[model],
        **grade_fields(answer, task.gold),
        "success": scorer.question_scorer(answer, task.gold),
        "ok": not is_error, "subtype": out.get("subtype"),
        "list_usd": usd, "cap_usd": CAPS[model],
        "hit_cap": out.get("subtype") == "error_max_budget_usd" or usd >= CAPS[model] * 0.999,
        **reading.usage_summary(out.get("modelUsage") or {}),
        "turns": out.get("num_turns"), "wall_s": round(wall_s, 1),
        "tools": reading.tool_calls(folder), "hooks": reading.hook_runs(folder),
        **reading.journal(side / "journal.jsonl"),
        **reading.denials(out, side / "denied.jsonl"),
        "leak": bool(leaks), "leak_tools": leaks,
        "answer": LIMIT_MARKER if limited(reply, stderr, is_error) else "",
        "version": reading.version_of(folder), "workdir": str(work), "side": str(side),
    }  # fmt: skip


def session_root(phase_name: str, task_id: str, arm: str, run: int) -> pathlib.Path:
    """A neutral folder name: the agent sees its working folder (and an attachment's path in the
    prompt), so neither the task id (searchable) nor the arm may be in it. The dev phase of
    2026-10-05 ran with `<task id>/<arm>-<run>`; the row keeps the folder either way."""
    digest = hashlib.sha256(f"{phase_name}|{task_id}|{arm}|{run}".encode()).hexdigest()[:16]
    return RUNS / phase_name / digest


def one_session(task: Any, run: int, arm: str, ctx: Mapping[str, Any]) -> dict[str, Any]:
    """One clean-user session. `ctx`: the phase's name and, for SP, the frozen src and shim."""
    model, brazo = split_arm(arm)
    root = session_root(ctx["phase"], task.task_id, arm, run)
    if root.exists():  # a session the usage limit stopped, run again from nothing
        shutil.rmtree(root)
    work, config, side = root / "work", root / "config", root / "side"
    for folder in (work, side):
        folder.mkdir(parents=True)
    arms.prepare_config(brazo, config, ctx.get("src"))
    attached = None
    if task.file_path:
        attached = work / neutral_name(task.file_name)
        shutil.copyfile(task.file_path, attached)
    settings = side / "settings.json"
    settings.write_text(json.dumps(settings_for(brazo)["flag"]), encoding="utf-8")
    mcp = side / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    env = arms.session_env(brazo, config, side, ctx.get("shim"))
    started = time.monotonic()
    argv = argv_for(model, settings, mcp, CAPS[model], prompt(task, attached))
    out, stderr = run_claude(argv, work, side, env)
    wall = time.monotonic() - started
    row = build_row(task, run, arm, out, stderr, work, side, wall, config / "projects")
    scrubbed = arms.scrub(root, arms.secrets_of(env))
    shim = reading.shim_runs(side / "shim.log")
    return {
        **row,
        "phase": ctx["phase"],
        "sp_commit": ctx.get("commit", ""),
        "shim_calls": sum(shim.values()),
        "shim_runs": shim,
        "scrubbed_files": scrubbed,
    }


def session_for(log_to: pathlib.Path, ctx: Mapping[str, Any]):
    """`one_session` behind phase.run_phase's (task tuple, run, arm) signature."""

    def session(item: tuple, run: int, arm: str) -> dict[str, Any]:
        row = one_session(item[3], run, arm, ctx)
        if phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {item[0]} {arm}: 429 or usage limit in the session")
        return row

    return session


def phase_context(phase_name: str, brazos: Sequence[str]) -> dict[str, Any]:
    """Refuse an unclean user; for SP, freeze `src` at HEAD and write the shim (free)."""
    arms.refuse_unclean(RUNS)
    ctx: dict[str, Any] = {"phase": phase_name}
    if "SP" in brazos:
        frozen = arms.freeze(ROOT, RUNS)
        ctx = {**ctx, "src": frozen / "src", "shim": arms.write_shim(frozen),
               "commit": frozen.name}  # fmt: skip
    return ctx


# --- plan ---------------------------------------------------------------------------------------


def planned(tasks: Sequence[Any], models: Sequence[str], brazos: Sequence[str],
            runs: Sequence[int] = (1,)) -> list[tuple]:  # fmt: skip
    """(index, (task_id, "", "", task), run, arm), arms interleaved within each task so a
    ceiling stop cuts every arm alike."""
    steps = []
    for i, task in enumerate(tasks):
        item = (task.task_id, "", "", task)
        for run in runs:
            for model in models:
                for brazo in brazos:
                    steps.append((i, item, run, f"{model}-{brazo}"))
    return steps


def ceiling(value: float, phase_name: str = "") -> float:
    top = min(MAX_CEILING_USD, PHASE_CEILINGS.get(phase_name, MAX_CEILING_USD))
    if not 0 < value <= top:
        raise SystemExit(f"--ceiling must be in (0, {top:g}] USD for phase {phase_name!r}")
    return value


def draw(tasks: Sequence[Any], size: int = DEV_SIZE, seed: int = DEV_SEED) -> list[str]:
    """The dev tasks: `size` ids drawn with `seed` from the non-video ones, in draw order."""
    pool = sorted(t.task_id for t in tasks if not t.video)
    return random.Random(seed).sample(pool, size)


def read_ids(path: pathlib.Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [x.strip() for x in lines if x.strip() and not x.startswith("#")]


# --- checks -------------------------------------------------------------------------------------


def model_ids_in(binary: pathlib.Path, ids: Sequence[str]) -> dict[str, bool]:
    """Free: each id as a quoted string inside the pinned Claude Code build."""
    blob = binary.read_bytes() if binary.exists() else b""
    return {m: f'"{m}"'.encode() in blob for m in ids}


def preflight(brazos: Sequence[str]) -> list[str]:
    problems: list[str] = []
    claude = shutil.which("claude") or "claude"
    try:
        version = subprocess.run([claude, "--version"], capture_output=True, timeout=60)
        if CLAUDE_VERSION not in version.stdout.decode("utf-8", errors="replace"):
            problems.append(f"claude on PATH ({claude}) is not {CLAUDE_VERSION}: use launch.ps1")
    except (OSError, subprocess.TimeoutExpired) as error:
        problems.append(f"claude did not run: {error.__class__.__name__}")
    if not data.TASKS.exists():
        problems.append("no GAIA tasks in the cache: gaia_data.py --fetch")
    try:
        ctx = phase_context("preflight", brazos)
        for brazo in brazos:
            config = RUNS / "preflight" / brazo / "config"
            if config.exists():
                shutil.rmtree(config)
            arms.prepare_config(brazo, config, ctx.get("src"))
    except (SystemExit, RuntimeError, OSError, subprocess.SubprocessError) as error:
        problems.append(f"arms: {error}")
    probe = {"tool_input": {"command": "curl https://huggingface.co/datasets/x"}}
    if not deny_hook.denied(probe["tool_input"]):
        problems.append("the deny hook let a denied host through")
    return problems


# --- review and report --------------------------------------------------------------------------


def paths(phase_name: str) -> dict[str, pathlib.Path]:
    """A phase's private rows (answers: never in the repository) and its public report."""
    own = PRIVATE / phase_name
    return {
        "sessions": own / "sessions.jsonl",
        "hand": own / "hand.jsonl",
        "review": own / "review.json",
        "report": RESULTS / f"report-{phase_name}.json",
    }


def hand_verdicts(path: pathlib.Path) -> dict[tuple, bool]:
    rows = read_rows(path)
    return {(r["task"], r["arm"], r["run"]): bool(r["ok"]) for r in rows}


def read_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def to_review(rows: Sequence[Mapping[str, Any]], hand: Mapping[tuple, bool]) -> list[dict]:
    """Officially wrong sessions a person should read, not yet given a hand verdict."""
    return [
        {"task": r["task"], "arm": r["arm"], "run": r["run"], "why": r["review"]}
        for r in rows
        if r.get("review") and (r["task"], r["arm"], r["run"]) not in hand
    ]


def report(rows: Sequence[Mapping[str, Any]], hand: Mapping[tuple, bool]) -> dict[str, Any]:
    """Counts, costs and task ids only, per arm, and the paired comparison per model."""
    spent = round(sum(r["list_usd"] for r in rows), 2)
    out: dict[str, Any] = {"sessions": len(rows), "list_usd": spent}
    out["by_arm"] = {arm: stats.arm_cell([r for r in rows if r["arm"] == arm], hand)
                     for arm in sorted({r["arm"] for r in rows})}  # fmt: skip
    out["paired"] = {m: stats.paired(rows, hand, f"{m}-SP", f"{m}-CC")
                     for m in sorted({r["model_key"] for r in rows})}  # fmt: skip
    return out


# --- main ---------------------------------------------------------------------------------------


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--check-models", "--live", "--review", "--draw-dev"):
        mode.add_argument(flag, action="store_true")
    mode.add_argument("--verdict", nargs=4, metavar=("TASK", "ARM", "RUN", "YES_NO"))
    ap.add_argument("--phase", default="dev", help="rows, folders and report are per phase")
    ap.add_argument("--models", nargs="+", default=["SONNET"], choices=sorted(MODELS))
    ap.add_argument("--brazos", nargs="+", default=["CC", "SP"], choices=ARMS)
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--ids", default=None, help="a file of task ids: only these, in its order")
    ap.add_argument("--exclude", default=None, help="a file of task ids to leave out")
    ap.add_argument("--limit", type=int, default=0, help="the first N tasks after filtering")
    ap.add_argument("--ceiling", type=float, default=DEFAULT_CEILING_USD)
    return ap.parse_args(argv)


def chosen(args: argparse.Namespace) -> list[Any]:
    tasks = data.select(data.load(), args.levels, args.no_video)
    if args.exclude:
        out = set(read_ids(pathlib.Path(args.exclude)))
        tasks = [t for t in tasks if t.task_id not in out]
    if args.ids:
        order = read_ids(pathlib.Path(args.ids))
        by_id = {t.task_id: t for t in tasks}
        tasks = [by_id[i] for i in order if i in by_id]
    return tasks[: args.limit] if args.limit else tasks


def write_dev_ids() -> list[str]:
    ids = draw(data.load())
    head = (f"# {DEV_SIZE} of the non-video GAIA validation tasks: random.Random({DEV_SEED})"
            ".sample of the sorted ids. Out of every confirmation.\n")  # fmt: skip
    DEV_IDS.write_text(head + "\n".join(ids) + "\n", encoding="utf-8")
    return ids


def main(argv: Sequence[str] | None = None) -> int:
    args = parse(argv)
    files = paths(args.phase)
    files["sessions"].parent.mkdir(parents=True, exist_ok=True)
    if args.check_models:
        print(json.dumps(model_ids_in(PIN, list(MODELS.values())), indent=1))
        return 0
    if args.draw_dev:
        print(f"{len(write_dev_ids())} ids written to {DEV_IDS}")
        return 0
    if args.verdict:
        task, arm, run, yes = args.verdict
        with files["hand"].open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"task": task, "arm": arm, "run": int(run),
                                   "ok": yes.lower() in ("yes", "y", "si")}) + "\n")  # fmt: skip
        return 0
    steps = planned(chosen(args), args.models, args.brazos)
    if args.plan:
        for i, item, run, arm in steps:
            print(i, item[0], arm, run, CAPS[split_arm(arm)[0]])
        print(f"{len(steps)} sessions; caps sum {sum(CAPS[split_arm(s[3])[0]] for s in steps):g}")
        return 0
    if args.preflight or args.live:
        problems = preflight(args.brazos)
        if problems:
            print("preflight: " + "; ".join(problems), file=sys.stderr)
            return 3
        if args.preflight:
            print("preflight: ok", file=sys.stderr)
            return 0
    rows = read_rows(files["sessions"])
    code = 0
    if args.live:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        cap = max(CAPS[m] for m in args.models)
        limits = phase.Limits(session_max_usd=cap, ceiling_usd=ceiling(args.ceiling, args.phase))
        session = session_for(files["sessions"], phase_context(args.phase, args.brazos))
        code, rows = phase.run_phase(steps, rows, limits, session, files["sessions"])
    counted = phase.counted(rows)
    hand = hand_verdicts(files["hand"])
    if args.review:
        pending = to_review(counted, hand)
        files["review"].write_text(json.dumps(pending, indent=1), encoding="utf-8")
        print(f"{len(pending)} sessions to read by hand: {files['review']}")
        return 0
    if counted:
        result = report(counted, hand)
        RESULTS.mkdir(parents=True, exist_ok=True)
        files["report"].write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
