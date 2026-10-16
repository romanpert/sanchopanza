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
SP adds what the install line of `s_install.json` writes into that user folder (run for real
from a frozen copy of the line's source, its digest checked against the preflight's proof,
`s_line.py`), the line's env and the TypeSafe key; a paid phase refuses an unsealed line. Both
arms set the permission mode explicitly (`--permission-mode` and `defaultMode`), since a clean
2.1.287 starts a user folder's first session in `auto`, and every session gets a new user
folder, so native memory never passes from one task to another.

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
import asyncio
import hashlib
import importlib.util
import json
import os
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
# USD at list; a phase named here cannot be given more (conf: prereg 2026-10-06)
PHASE_CEILINGS = {"dev": 25.0, "gaia-conf": 40.0}

CLAUDE_VERSION = "2.1.287"
# The pinned claude.exe: in the folder SANCHOPANZA_PIN_DIR names, else under the runs folder.
PIN = pathlib.Path(os.environ.get("SANCHOPANZA_PIN_DIR") or "C:/sp-runs/pin") / "claude.exe"
MODELS = {
    "FABLE": "claude-fable-5-1",
    "OPUS": "claude-opus-5-5",
    "SONNET": "claude-sonnet-5-5",
    "HAIKU": "claude-haiku-4-5-20251001",
}
# Per-session caps, USD at list. Sonnet's is the FRAMES pilot's (its sessions averaged 0.23 and
# none hit 1.50); the others scale it by the model's price, Haiku with a floor.
CAPS = {"FABLE": 6.00, "OPUS": 3.00, "SONNET": 1.50, "HAIKU": 0.75}
# NE: N-early, clean N with only S's auto-compact window (gaia_arms.NE_USER_SETTINGS).
ARMS = ("CC", "SP", "NE")
DEFAULT_CEILING_USD = 10.0
# Above this, edit the file: the owner's rule is to ask past 10 USD (250: conf amendment 2).
MAX_CEILING_USD = 250.0
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
        "permissions": {
            "allow": TOOLS.split(),
            "deny": list(DENY),
            "defaultMode": arms.PERMISSION_MODE,
        },
        "hooks": {"PreToolUse": [{"matcher": "", "hooks": [hook]}]},
    }


def settings_for(brazo: str, base: Mapping[str, Any] | None = None,
                 line: Any = None) -> dict[str, Any]:  # fmt: skip
    """An arm's settings, by source: `flag` is the `--settings` file (the same in both arms: the
    suite's `base`, GAIA's by default), `user` what goes into its CLAUDE_CONFIG_DIR: nothing for
    CC; for SP the install line of `s_install.json` (its flags, run for real per session, and its
    env), never a hand-written settings block. The arms differ in `user`, what that install
    writes beside it (skill, MCP servers) and `gaia_arms.session_env`, and nowhere else."""
    flag = dict(base) if base is not None else base_settings()
    if brazo == "CC":
        return {"flag": flag, "user": {}}
    if brazo == "NE":
        return {"flag": flag, "user": dict(arms.NE_USER_SETTINGS)}
    if brazo == "SP":
        chosen = line if line is not None else arms.s_line.load()
        return {"flag": flag, "user": {"install_flags": list(chosen.flags),
                                       "env": chosen.env_map}}  # fmt: skip
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


def argv_for(model: str, settings: pathlib.Path, mcp: pathlib.Path, cap: float, text: str,
             tools: str = TOOLS, disallowed: str = DISALLOWED) -> list:  # fmt: skip
    return [
        shutil.which("claude") or "claude", "-p", "--model", MODELS[model],
        "--settings", str(settings), "--setting-sources", arms.SETTING_SOURCES,
        "--permission-mode", arms.PERMISSION_MODE,
        "--mcp-config", str(mcp), "--strict-mcp-config",
        "--allowedTools", tools, "--disallowedTools", disallowed,
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
        "components": reading.components(folder),
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


def clean_session(ctx: Mapping[str, Any], root: pathlib.Path, arm: str, text: str, *,
                  flag_settings: Mapping[str, Any], make_row: Any,
                  mcp_servers: Mapping[str, Any] | None = None,
                  copies: Sequence[tuple[pathlib.Path, str]] = (),
                  tools: str = TOOLS, disallowed: str = DISALLOWED,
                  caps: Mapping[str, float] | None = None) -> dict[str, Any]:  # fmt: skip
    """One clean-user session of any suite, from nothing: the user folder (S: the line's
    install, checked against the preflight's digest), `copies` into the working folder, the
    suite's MCP servers plus S's, then `make_row(out, stderr, work, side, wall, projects)`;
    secrets scrubbed and the shim's log counted. `ctx`: phase, and for SP the frozen src, shim,
    line and digest."""
    model, brazo = split_arm(arm)
    if root.exists():  # a session the usage limit stopped, run again from nothing
        shutil.rmtree(root)
    work, config, side = root / "work", root / "config", root / "side"
    if config.exists():  # a new CLAUDE_CONFIG_DIR per session: no native memory carried over
        raise RuntimeError(f"{config} survived the reset: refusing to reuse a user folder")
    for folder in (work, side):
        folder.mkdir(parents=True)
    line = ctx.get("line")
    installed = arms.prepare_config(brazo, config, ctx.get("src"),
                                    line.flags if line is not None else (),
                                    ctx.get("s_digest"))  # fmt: skip
    for source, name in copies:
        shutil.copyfile(source, work / name)
    servers = dict(mcp_servers or {})
    allowed = tools
    own_raw = arms.s_line.registered(installed, ctx.get("s_hints", ())) if installed else {}
    if own_raw:
        own = arms.s_line.session_mcp(own_raw, ctx["src"], side / "home")
        clash = sorted(set(own) & set(servers))
        if clash:
            raise RuntimeError(f"the S install's MCP servers clash with the suite's: {clash}")
        servers = {**servers, **own}
        allowed = " ".join([tools, *(f"mcp__{name}" for name in sorted(own))])
    settings = side / "settings.json"
    settings.write_text(json.dumps(flag_settings), encoding="utf-8")
    mcp = side / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    env = arms.session_env(brazo, config, side, ctx.get("shim"),
                           line_env=line.env_map if line is not None else None)  # fmt: skip
    cap = (caps or CAPS)[model]
    started = time.monotonic()
    argv = argv_for(model, settings, mcp, cap, text, tools=allowed, disallowed=disallowed)
    out, stderr = run_claude(argv, work, side, env)
    wall = time.monotonic() - started
    row = make_row(out, stderr, work, side, wall, config / "projects")
    scrubbed = arms.scrub(root, arms.secrets_of(env))
    shim = reading.shim_runs(side / "shim.log")
    return {
        **row,
        "phase": ctx["phase"],
        "sp_commit": ctx.get("commit", ""),
        "s_digest": installed.digest if installed is not None else "",
        "shim_calls": sum(shim.values()),
        "shim_runs": shim,
        "scrubbed_files": scrubbed,
    }


def one_session(task: Any, run: int, arm: str, ctx: Mapping[str, Any]) -> dict[str, Any]:
    """One GAIA session: the question, its attachment under a neutral name, GAIA's format."""
    root = session_root(ctx["phase"], task.task_id, arm, run)
    copies, attached = [], None
    if task.file_path:
        name = neutral_name(task.file_name)
        copies, attached = [(pathlib.Path(task.file_path), name)], root / "work" / name

    def make_row(out, stderr, work, side, wall, projects):  # noqa: ANN001, ANN202
        return build_row(task, run, arm, out, stderr, work, side, wall, projects)

    return clean_session(ctx, root, arm, prompt(task, attached),
                         flag_settings=settings_for(split_arm(arm)[1])["flag"],
                         make_row=make_row, copies=copies)  # fmt: skip


# Jev refusing the account, not one question: no credit (402) or a bad key (401, 403). From then
# on S fails open on every point and the session measures S without its decider.
JEV_ACCOUNT_ERROR = re.compile(r"jev did not answer: HTTP 40[123](?!\d)")


class JevStop(RuntimeError):
    """Jev refused the account in a session: the phase stops (exit 4) until it is recharged."""


def jev_guard(session: Any, log_to: pathlib.Path) -> Any:
    """`session`, stopping the phase after one whose Jev refused the account (the journal's
    failed decisions by kind, `jev_error_kinds`, from `gaia_session.journal`). That paid row is
    recorded `invalid` and `not_run` (a resume runs it again after the recharge); the next
    session is never started."""

    def guarded(item: tuple, run: int, arm: str) -> dict[str, Any]:
        row = session(item, run, arm)
        kinds = row.get("jev_error_kinds") or {}
        bad = sorted(e for e in kinds if JEV_ACCOUNT_ERROR.search(e))
        if bad:
            phase._record(log_to, {**row, "invalid": f"jev account: {bad[0]}", "not_run": True})
            raise JevStop(f"STOP-JEV {item[0]} {arm}: {bad[0]}; recharge TypeSafe and resume")
        return row

    return guarded


def run_stoppable(steps: list, rows: list, limits: Any, session: Any,
                  sessions: pathlib.Path) -> tuple[int, list]:  # fmt: skip
    """phase.run_phase, ended by a JevStop with exit 4 and the rows on disk."""
    try:
        return phase.run_phase(steps, rows, limits, session, sessions)
    except JevStop as stop:
        phase._log(sessions, str(stop))
        return 4, read_rows(sessions)


def session_for(log_to: pathlib.Path, ctx: Mapping[str, Any]):
    """`one_session` behind phase.run_phase's (task tuple, run, arm) signature."""

    def session(item: tuple, run: int, arm: str) -> dict[str, Any]:
        row = one_session(item[3], run, arm, ctx)
        if phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {item[0]} {arm}: 429 or usage limit in the session")
        return row

    return jev_guard(session, log_to)


_VERIFIED: dict[tuple, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}


def verified_line(line: Any, src: pathlib.Path, scratch: pathlib.Path) -> tuple:
    """`s_line.verify` once per process for a (frozen copy, line): the digest, the problems and
    the printed MCP servers the line asked for."""
    key = (str(src), line.flags, line.env)
    if key not in _VERIFIED:
        if scratch.exists():
            shutil.rmtree(scratch)
        full, problems, hints = arms.s_line.verify(line, src, scratch)
        _VERIFIED[key] = (full.digest, tuple(problems), hints)
    digest, problems, hints = _VERIFIED[key]
    return digest, list(problems), hints


def verify_scratch(commit: str, phase_name: str) -> pathlib.Path:
    """Where a phase proves the line: one folder per phase, so suites started side by side do
    not delete each other's proof (two runners shared one on 2026-10-05: WinError 32)."""
    return RUNS / "verify" / f"{commit}-{phase_name}"


def phase_context(phase_name: str, brazos: Sequence[str], line: Any = None) -> dict[str, Any]:
    """Refuse an unclean user; for SP, freeze the line's source at its commit, write the shim
    and prove the line installs whole (free). Any problem with the line stops the phase."""
    arms.refuse_unclean(RUNS)
    ctx: dict[str, Any] = {"phase": phase_name}
    if "SP" not in brazos:
        return ctx
    chosen = line if line is not None else arms.s_line.load()
    source = arms.s_line.source_root(chosen, ROOT)
    frozen = arms.freeze(source, RUNS, chosen.commit)
    scratch = verify_scratch(frozen.name, phase_name)
    digest, problems, hints = verified_line(chosen, frozen / "src", scratch)
    if problems:
        raise SystemExit("the S install line does not install whole: " + "; ".join(problems))
    return {**ctx, "src": frozen / "src", "shim": arms.write_shim(frozen), "commit": frozen.name,
            "line": chosen, "s_digest": digest, "s_hints": hints}  # fmt: skip


def arms_preflight(brazos: Sequence[str], line: Any = None, phase_name: str = "") -> list[str]:
    """Both arms' user folders made as a session makes them; S's line proved flag by flag. In
    folders of the phase's own (`preflight-<phase>`): suites started together shared one and
    stopped each other (WinError 32, 2026-10-06)."""
    name = f"preflight-{phase_name}" if phase_name else "preflight"
    try:
        ctx = phase_context(name, brazos, line)
        for brazo in brazos:
            config = RUNS / name / brazo / "config"
            if config.parent.exists():
                shutil.rmtree(config.parent)
            chosen = ctx.get("line")
            arms.prepare_config(brazo, config, ctx.get("src"),
                                chosen.flags if chosen is not None else (),
                                ctx.get("s_digest"))  # fmt: skip
    except (SystemExit, RuntimeError, OSError, subprocess.SubprocessError) as error:
        return [f"arms: {error}"]
    return []


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


def isolation_problems(flag_settings: Mapping[str, Any], argv: Sequence[str]) -> list[str]:
    """The two things a clean Claude Code 2.1.287 does not fix by itself: the permission mode
    (`auto` in a user folder's first session, `default` after) set explicitly, the same in both
    arms, by flag and in the settings; and a user folder of its own per session (native memory
    lives there), never one another task used."""
    problems = []
    mode = (flag_settings.get("permissions") or {}).get("defaultMode")
    if mode != arms.PERMISSION_MODE:
        problems.append(f"settings defaultMode is {mode!r}, not {arms.PERMISSION_MODE!r}")
    flag = list(argv)
    if "--permission-mode" not in flag or flag[flag.index("--permission-mode") + 1] != (
        arms.PERMISSION_MODE
    ):
        problems.append("the claude command line does not set --permission-mode")
    roots = {session_root("preflight", t, a, r) for t in ("t1", "t2") for a in ("SONNET-CC",
             "SONNET-SP") for r in (1, 2)}  # fmt: skip
    if len(roots) != 8:
        problems.append("two sessions would share a user folder")
    return problems


def claude_problems() -> list[str]:
    """The claude on PATH must be the pinned build."""
    claude = shutil.which("claude") or "claude"
    try:
        version = subprocess.run([claude, "--version"], capture_output=True, timeout=60)
        if CLAUDE_VERSION not in version.stdout.decode("utf-8", errors="replace"):
            return [f"claude on PATH ({claude}) is not {CLAUDE_VERSION}: use launch.ps1"]
    except (OSError, subprocess.TimeoutExpired) as error:
        return [f"claude did not run: {error.__class__.__name__}"]
    return []


def _ask_jev(key: str) -> None:
    """One real decision, a few micro-USD: a one-sentence state and one Truth question."""
    from sanchopanza.contract import Truth
    from sanchopanza.providers.jev import JevDecider

    async def once() -> None:
        decider = JevDecider(key)
        try:
            decision = await decider.decide(
                "preflight", {"text": "The sky is blue."}, {"q": Truth("Is `text` a sentence?")}
            )
        finally:
            await decider.aclose()
        if "q" not in decision.answers:
            raise RuntimeError("jev answered without the question asked")

    asyncio.run(once())


def jev_problems(brazos: Sequence[str], probe: Any = None) -> list[str]:
    """Paid, a few micro-USD, and only when S runs: one real Jev decision with the key S gets.
    With no balance TypeSafe answers HTTP 402 and S fails open in silence (2026-10-05: four GAIA
    S sessions measured S without its decider), so a run with S does not start unless Jev
    answers. The refusal never carries the key."""
    if "SP" not in brazos:
        return []
    try:
        key = arms.secret(arms.JEV_KEY)
    except SystemExit as error:
        return [f"jev: {error}"]
    try:
        (probe or _ask_jev)(key)
    except Exception as error:  # noqa: BLE001 - any failure stops the run, named, key removed
        return ["jev: " + str(error).replace(key, "<key>")]
    return []


def preflight(brazos: Sequence[str], line: Any = None, phase_name: str = "") -> list[str]:
    """Free except, when S runs, one real Jev decision (`jev_problems`). `line` is the S line the
    run will use (`--s-line`); None proves `s_install.json`."""
    problems = claude_problems()
    if not data.TASKS.exists():
        problems.append("no GAIA tasks in the cache: gaia_data.py --fetch")
    problems.extend(arms_preflight(brazos, line, phase_name))
    problems.extend(jev_problems(brazos))
    probe_argv = argv_for("SONNET", RUNS / "s.json", RUNS / "m.json", 1.0, "q")
    for brazo in brazos:
        problems.extend(isolation_problems(settings_for(brazo)["flag"], probe_argv))
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
        "review": own / "review-blind.jsonl",
        "review_key": own / "review-key.jsonl",
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


def blind_review(rows: Sequence[Mapping[str, Any]], hand: Mapping[tuple, bool],
                 sheet: pathlib.Path, key: pathlib.Path) -> int:  # fmt: skip
    """The sessions of `to_review` for a blind hand read: question, gold, final answer and the
    scorer's doubt under an opaque id, no arm (`stats.blind_sheet`). Private, never printed."""
    by_id = {t.task_id: t for t in data.load()}
    by_key = {(r["task"], r["arm"], r["run"]): r for r in rows}
    items = [{**{k: p[k] for k in ("task", "arm", "run")},
              "question": by_id[p["task"]].question, "gold": by_id[p["task"]].gold,
              "answer": by_key[(p["task"], p["arm"], p["run"])].get("final_answer"),
              "why": p["why"]} for p in to_review(rows, hand)]  # fmt: skip
    return stats.blind_sheet(items, sheet, key)


def refuse_open_verdict(phase_name: str) -> None:
    """A confirmation phase takes hand verdicts only through the blind sheet (`--apply-blind`):
    `--verdict` names the arm, and a hand verdict overrides the scorer (prereg 2026-10-06)."""
    if phase_name.endswith("-conf"):
        raise SystemExit(f"phase {phase_name!r} takes blind verdicts only: --review, then "
                         "--apply-blind")


def apply_blind(answers: pathlib.Path, key: pathlib.Path, hand: pathlib.Path) -> int:
    """A blind reader's {"id", "ok"} verdicts appended to the hand verdicts through the key."""
    verdicts = stats.blind_verdicts(answers, key)
    with hand.open("a", encoding="utf-8") as sink:
        for v in verdicts:
            sink.write(json.dumps(v) + "\n")
    return len(verdicts)


def report(rows: Sequence[Mapping[str, Any]], hand: Mapping[tuple, bool]) -> dict[str, Any]:
    """Counts, costs and task ids only, per arm, and the paired comparison per model."""
    spent = round(sum(r["list_usd"] for r in rows), 2)
    out: dict[str, Any] = {"sessions": len(rows), "list_usd": spent}
    out["by_arm"] = {arm: stats.arm_cell([r for r in rows if r["arm"] == arm], hand)
                     for arm in sorted({r["arm"] for r in rows})}  # fmt: skip
    # A task with a session marked `leak` in either arm leaves the paired analysis in both arms,
    # by rule and without reading the arm (prereg 2026-10-06); all tasks stay as a sensitivity.
    leaked = sorted({r["task"] for r in rows if r.get("leak")})
    clean = [r for r in rows if r["task"] not in set(leaked)]
    models = sorted({r["model_key"] for r in rows})
    out["dropped_for_leak"] = leaked
    out["paired"] = {m: stats.paired(clean, hand, f"{m}-SP", f"{m}-CC") for m in models}
    out["verdict"] = {m: stats.verdict(pair) for m, pair in out["paired"].items()}
    out["paired_all_tasks"] = {m: stats.paired(rows, hand, f"{m}-SP", f"{m}-CC") for m in models}
    return out


# --- main ---------------------------------------------------------------------------------------


def parse(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--check-models", "--live", "--review", "--draw-dev"):
        mode.add_argument(flag, action="store_true")
    mode.add_argument("--verdict", nargs=4, metavar=("TASK", "ARM", "RUN", "YES_NO"))
    mode.add_argument("--apply-blind", metavar="VERDICTS_JSONL",
                      help="a blind reader's {id, ok} lines, mapped back through the key")
    ap.add_argument("--phase", default="dev", help="rows, folders and report are per phase")
    ap.add_argument("--models", nargs="+", default=["SONNET"], choices=sorted(MODELS))
    ap.add_argument("--brazos", nargs="+", default=["CC", "SP"], choices=ARMS)
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--ids", default=None, help="a file of task ids: only these, in its order")
    ap.add_argument("--exclude", default=None, help="a file of task ids to leave out")
    ap.add_argument("--limit", type=int, default=0, help="the first N tasks after filtering")
    ap.add_argument("--ceiling", type=float, default=DEFAULT_CEILING_USD)
    add_line_args(ap)
    return ap.parse_args(argv)


def add_line_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--s-line",
        default=str(arms.s_line.S_INSTALL),
        help="the S arm's install line (flags and env), sealed by the owner",
    )
    ap.add_argument(
        "--unsealed-ok",
        action="store_true",
        help="let --live run S from an unsealed line (smokes only)",
    )


def live_line(args: argparse.Namespace) -> Any:
    """The S line a paid phase runs: refused unsealed unless --unsealed-ok."""
    line = arms.s_line.load(pathlib.Path(args.s_line))
    if "SP" in args.brazos:
        arms.s_line.require_sealed(line, args.unsealed_ok)
    return line


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
        refuse_open_verdict(args.phase)
        task, arm, run, yes = args.verdict
        with files["hand"].open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"task": task, "arm": arm, "run": int(run),
                                   "ok": yes.lower() in ("yes", "y", "si")}) + "\n")  # fmt: skip
        return 0
    if args.apply_blind:
        n = apply_blind(pathlib.Path(args.apply_blind), files["review_key"], files["hand"])
        print(f"{n} blind verdicts added to {files['hand']}")
        return 0
    steps = planned(chosen(args), args.models, args.brazos)
    if args.plan:
        for i, item, run, arm in steps:
            print(i, item[0], arm, run, CAPS[split_arm(arm)[0]])
        print(f"{len(steps)} sessions; caps sum {sum(CAPS[split_arm(s[3])[0]] for s in steps):g}")
        return 0
    if args.preflight or args.live:
        line = arms.s_line.load(pathlib.Path(args.s_line))
        problems = preflight(args.brazos, line, args.phase)
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
        ctx = phase_context(args.phase, args.brazos, live_line(args))
        session = session_for(files["sessions"], ctx)
        code, rows = run_stoppable(steps, rows, limits, session, files["sessions"])
    counted = phase.counted(rows)
    hand = hand_verdicts(files["hand"])
    if args.review:
        n = blind_review(counted, hand, files["review"], files["review_key"])
        print(f"{n} sessions to read blind: {files['review']} (the key stays unopened)")
        return 0
    if counted:
        result = report(counted, hand)
        RESULTS.mkdir(parents=True, exist_ok=True)
        files["report"].write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
