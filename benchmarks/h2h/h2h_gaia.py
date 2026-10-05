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
Code's normal tools, Bash included (GAIA needs computing and reading files); no MCP server, no
user or project settings (`--setting-sources ""`), the scheduling tools off.

Both arms deny the hosts that serve the set: WebFetch through the session's deny rules, and any
tool through a PreToolUse hook that reads the call's whole input (`deny_hook.py`), since Bash
could `curl` them. A session whose tool results say "GAIA" or the task id is marked `leak` and
read by hand. The arms differ only by `settings_for(arm)`; the SP arm is not written yet and
refuses to run (a TODO, not a guess).

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
import importlib.util
import json
import os
import pathlib
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
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
e2e = _load("browse_e2e", ROOT / "benchmarks" / "browse" / "e2e.py")
data = _load("h2h_gaia_data", HERE / "gaia_data.py")
scorer = _load("h2h_gaia_scorer", HERE / "gaia_scorer.py")
reading = _load("h2h_gaia_session", HERE / "gaia_session.py")
deny_hook = _load("h2h_deny_hook", HERE / "deny_hook.py")

PRIVATE = data.CACHE / "h2h"  # rows keep the agents' answers: never in the repository
SESSIONS = PRIVATE / "sessions.jsonl"
HAND = PRIVATE / "hand.jsonl"
REVIEW = PRIVATE / "review.json"
RESULTS = ROOT / "docs" / "results" / "2026-10-05-h2h-gaia"
REPORT = RESULTS / "report.json"  # counts and task ids only

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
    """The session's whole settings file for an arm. The arms differ here and nowhere else."""
    if brazo == "CC":
        return base_settings()
    if brazo == "SP":
        # TODO(h2h): the sanchopanza arm - which `sanchopanza install` profile, its hooks and MCP
        # servers added to base_settings(), its env (Jev key, caps) - is decided with the owner
        # and written here. Until then the arm refuses to run rather than run something guessed.
        raise NotImplementedError("the SP arm is not written yet (settings_for TODO)")
    raise ValueError(f"unknown arm {brazo!r}")


def env_for(brazo: str, deny_log: pathlib.Path) -> dict[str, str]:
    """Both arms: no API credential (the subscription runs it), no Jev key, no PYTHONPATH from
    the launcher. The SP arm will add its own variables here."""
    dropped = ("TYPESAFE_API_KEY", "PYTHONPATH")
    env = {k: v for k, v in e2e.clean_env(dict(os.environ)).items() if k not in dropped}
    return {**env, "H2H_DENY_LOG": str(deny_log)}


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
        "--settings", str(settings), "--setting-sources", "",
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
              work: pathlib.Path, side: pathlib.Path, wall_s: float) -> dict[str, Any]:  # fmt: skip
    model, brazo = split_arm(arm)
    folder = reading.folder_of(work)
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
        "tools": reading.tool_calls(folder),
        **reading.denials(out, side / "denied.jsonl"),
        "leak": bool(leaks), "leak_tools": leaks,
        "answer": LIMIT_MARKER if limited(reply, stderr, is_error) else "",
        "version": reading.version_of(folder), "workdir": str(work), "side": str(side),
    }  # fmt: skip


def one_session(task: Any, run: int, arm: str) -> dict[str, Any]:
    model, brazo = split_arm(arm)
    work = pathlib.Path(tempfile.mkdtemp(prefix="sp-h2h-"))
    side = pathlib.Path(tempfile.mkdtemp(prefix="sp-h2h-side-"))  # out of the agent's sight
    attached = None
    if task.file_path:
        attached = work / neutral_name(task.file_name)
        shutil.copyfile(task.file_path, attached)
    settings = side / "settings.json"
    settings.write_text(json.dumps(settings_for(brazo)), encoding="utf-8")
    mcp = side / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    env = env_for(brazo, side / "denied.jsonl")
    started = time.monotonic()
    argv = argv_for(model, settings, mcp, CAPS[model], prompt(task, attached))
    out, stderr = run_claude(argv, work, side, env)
    return build_row(task, run, arm, out, stderr, work, side, time.monotonic() - started)


def session_for(log_to: pathlib.Path):
    """`one_session` behind phase.run_phase's (task tuple, run, arm) signature."""

    def session(item: tuple, run: int, arm: str) -> dict[str, Any]:
        row = one_session(item[3], run, arm)
        if phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {item[0]} {arm}: 429 or usage limit in the session")
        return row

    return session


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


def ceiling(value: float) -> float:
    if not 0 < value <= MAX_CEILING_USD:
        raise SystemExit(f"--ceiling must be in (0, {MAX_CEILING_USD:g}] USD")
    return value


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
    for brazo in brazos:
        try:
            settings_for(brazo)
        except NotImplementedError as error:
            problems.append(str(error))
    probe = {"tool_input": {"command": "curl https://huggingface.co/datasets/x"}}
    if not deny_hook.denied(probe["tool_input"]):
        problems.append("the deny hook let a denied host through")
    return problems


# --- review and report --------------------------------------------------------------------------


def hand_verdicts(path: pathlib.Path = HAND) -> dict[tuple, bool]:
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
    spent = round(sum(r["list_usd"] for r in rows), 2)
    out: dict[str, Any] = {"sessions": len(rows), "list_usd": spent}
    cells = {}
    for arm in sorted({r["arm"] for r in rows}):
        mine = [r for r in rows if r["arm"] == arm]
        with_hand = [hand.get((r["task"], r["arm"], r["run"]), r["ok_oficial"]) for r in mine]
        cells[arm] = {
            "sessions": len(mine),
            "ok_oficial": sum(bool(r["ok_oficial"]) for r in mine),
            "ok_with_hand": sum(with_hand),
            "by_level": {
                str(lv): f"{sum(r['ok_oficial'] for r in mine if r['level'] == lv)}/"
                f"{sum(r['level'] == lv for r in mine)}"
                for lv in sorted({r["level"] for r in mine})
            },
            "mean_usd": round(statistics.mean(r["list_usd"] for r in mine), 4),
            "median_usd": round(statistics.median(r["list_usd"] for r in mine), 4),
            "median_wall_s": statistics.median(r["wall_s"] for r in mine),
            "hit_cap": sum(bool(r["hit_cap"]) for r in mine),
            "leak": sorted(r["task"] for r in mine if r["leak"]),
            "no_final_answer": sum(r["final_answer"] is None for r in mine),
            "denied": sum(r["denied"] + len(r["hook_denied"]) for r in mine),
        }
    out["by_arm"] = cells
    return out


# --- main ---------------------------------------------------------------------------------------


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--check-models", "--live", "--review"):
        mode.add_argument(flag, action="store_true")
    mode.add_argument("--verdict", nargs=4, metavar=("TASK", "ARM", "RUN", "YES_NO"))
    ap.add_argument("--models", nargs="+", default=["SONNET"], choices=sorted(MODELS))
    ap.add_argument("--brazos", nargs="+", default=["CC"], choices=ARMS)
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="the first N tasks after filtering")
    ap.add_argument("--ceiling", type=float, default=DEFAULT_CEILING_USD)
    return ap.parse_args(argv)


def chosen(args: argparse.Namespace) -> list[Any]:
    tasks = data.select(data.load(), args.levels, args.no_video)
    return tasks[: args.limit] if args.limit else tasks


def main(argv: Sequence[str] | None = None) -> int:
    args = parse(argv)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if args.check_models:
        print(json.dumps(model_ids_in(PIN, list(MODELS.values())), indent=1))
        return 0
    if args.verdict:
        task, arm, run, yes = args.verdict
        with HAND.open("a", encoding="utf-8") as sink:
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
    rows = read_rows(SESSIONS)
    code = 0
    if args.live:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        cap = max(CAPS[m] for m in args.models)
        limits = phase.Limits(session_max_usd=cap, ceiling_usd=ceiling(args.ceiling))
        code, rows = phase.run_phase(steps, rows, limits, session_for(SESSIONS), SESSIONS)
    counted = phase.counted(rows)
    hand = hand_verdicts()
    if args.review:
        pending = to_review(counted, hand)
        REVIEW.write_text(json.dumps(pending, indent=1), encoding="utf-8")
        print(f"{len(pending)} sessions to read by hand: {REVIEW}")
        return 0
    if counted:
        result = report(counted, hand)
        RESULTS.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
