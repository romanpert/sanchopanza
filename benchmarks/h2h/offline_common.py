"""What the two offline suites (BrowseComp-Plus, long documents) share on top of the GAIA runner:
the tools, the settings both arms get, the row fields every session has, and the phase loop.

Both suites take the web away from both arms (WebSearch and WebFetch disallowed, and
`local_hook.py` denies a shell's network and any path outside the session's folder), so the
evidence is the suite's own: a retrieval server or a file in the working folder. Everything else
is GAIA's runner (`h2h_gaia.py`): clean users, the S line, caps, the ceiling, STOP-LIMIT, resume.

Dev phases run a seeded draw of `DEV_SIZE` ids written to the suite's `*-dev-ids.txt`; every
other phase leaves those ids out (`leave_out_dev`). Two suites run side by side can share one
ceiling: with `--joint-with` the other suites' session files count against `--ceiling`, and so
does one session in flight per suite (`joint_guard`).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import signal
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
if "h2h_gaia_runner_shared" not in sys.modules:
    import importlib.util

    _spec = importlib.util.spec_from_file_location("h2h_gaia_runner_shared", HERE / "h2h_gaia.py")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["h2h_gaia_runner_shared"] = _module
    _spec.loader.exec_module(_module)
gaia = sys.modules["h2h_gaia_runner_shared"]
phase, arms, reading, stats = gaia.phase, gaia.arms, gaia.reading, gaia.stats

TOOLS = "Bash Read Grep Glob Write Edit NotebookEdit Task Agent TodoWrite"
DISALLOWED = f"{gaia.DISALLOWED} WebSearch WebFetch"
DEV_SEED = 20261005
DEV_SIZE = 10


# --- the dev draw ---------------------------------------------------------------------------------


def draw_dev(pool: Sequence[str], size: int = DEV_SIZE, seed: int = DEV_SEED) -> list[str]:
    return random.Random(seed).sample(sorted(pool), size)


def write_ids(path: pathlib.Path, ids: Sequence[str], head: str) -> None:
    path.write_text(f"# {head}\n" + "\n".join(ids) + "\n", encoding="utf-8")


def leave_out_dev(ids: Sequence[str], chosen_from: pathlib.Path | None,
                  dev_file: pathlib.Path) -> list[str]:  # fmt: skip
    """`ids` without the dev phase's, unless they were chosen from the dev file itself."""
    if chosen_from is not None and chosen_from.resolve() == dev_file.resolve():
        return list(ids)
    dev = set(gaia.read_ids(dev_file))
    return [i for i in ids if i not in dev]


# --- one ceiling for suites run side by side ------------------------------------------------------


class JointCeiling(RuntimeError):
    """Raised before a session the shared ceiling cannot hold."""


def joint_guard(session: Callable, own: pathlib.Path, others: Sequence[pathlib.Path],
                cap: float, ceiling: float) -> Callable:  # fmt: skip
    """`session`, refused when what every suite has spent (their session files) plus one session
    in flight per suite at `cap` could pass `ceiling`."""

    def guarded(item: tuple, run: int, arm: str) -> dict[str, Any]:
        spent = sum(float(r.get("list_usd") or 0.0)
                    for path in (own, *others) for r in gaia.read_rows(path))  # fmt: skip
        reserved = cap * (1 + len(others))
        if spent + reserved > ceiling:
            raise JointCeiling(f"STOP joint ceiling: {spent:.2f} USD spent by the suites + "
                               f"{reserved:.2f} in flight > {ceiling:g}")  # fmt: skip
        return session(item, run, arm)

    return guarded


def run_guarded(steps: list, rows: list, limits: Any, session: Callable,
                sessions: pathlib.Path) -> tuple[int, list]:  # fmt: skip
    """GAIA's phase loop; a joint-ceiling stop ends it like its own ceiling (exit 1)."""
    try:
        return phase.run_phase(steps, rows, limits, session, sessions)
    except JointCeiling as stop:
        phase._log(sessions, str(stop))
        return 1, gaia.read_rows(sessions)


def add_joint_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--joint-with",
        nargs="+",
        default=[],
        metavar="SESSIONS_JSONL",
        help="other suites' session files that share --ceiling with this one",
    )


def hook_command() -> str:
    return f'"{pathlib.Path(sys.executable).as_posix()}" "{(HERE / "local_hook.py").as_posix()}"'


def base_settings(extra_allow: Sequence[str] = ()) -> dict[str, Any]:
    """Both arms: the allow list (plus the suite's MCP tools), the web denied, the local hook,
    and the permission mode set explicitly."""
    hook = {"type": "command", "command": hook_command(), "timeout": gaia.HOOK_TIMEOUT_S}
    return {
        "permissions": {
            "allow": [*TOOLS.split(), *extra_allow],
            "deny": ["WebSearch", "WebFetch"],
            "defaultMode": arms.PERMISSION_MODE,
        },  # fmt: skip
        "hooks": {"PreToolUse": [{"matcher": "", "hooks": [hook]}]},
    }


def common_row(task_id: str, run: int, arm: str, out: Mapping[str, Any], stderr: str,
               work: pathlib.Path, side: pathlib.Path, wall_s: float,
               projects: pathlib.Path | None, leak_word: str,
               caps: Mapping[str, float]) -> dict[str, Any]:  # fmt: skip
    """The fields every session row has, whatever the suite grades."""
    model, brazo = gaia.split_arm(arm)
    folder = reading.folder_of(work, projects)
    reply = str(out.get("result") or "")
    usd = float(out.get("total_cost_usd") or 0.0)
    is_error = bool(out.get("is_error", True))
    leaks = reading.leaks(folder, "", leak_word)
    return {
        "task": task_id, "task_id": task_id, "run": run, "arm": arm, "brazo": brazo,
        "model_key": model, "model": gaia.MODELS[model],
        "ok": not is_error, "subtype": out.get("subtype"),
        "list_usd": usd, "cap_usd": caps[model],
        "hit_cap": out.get("subtype") == "error_max_budget_usd" or usd >= caps[model] * 0.999,
        **reading.usage_summary(out.get("modelUsage") or {}),
        "turns": out.get("num_turns"), "wall_s": round(wall_s, 1),
        "tools": reading.tool_calls(folder), "hooks": reading.hook_runs(folder),
        **reading.journal(side / "journal.jsonl"),
        **reading.denials(out, side / "denied.jsonl"),
        "leak": bool(leaks), "leak_tools": leaks,
        "answer": gaia.LIMIT_MARKER if gaia.limited(reply, stderr, is_error) else "",
        "version": reading.version_of(folder), "workdir": str(work), "side": str(side),
    }  # fmt: skip


def reply_text(out: Mapping[str, Any], folder: pathlib.Path,
               has_answer: Callable[[str], bool]) -> str:  # fmt: skip
    """The final reply, or, when a cap or an error ended the session first, the main agent's
    last text that holds an answer."""
    reply = str(out.get("result") or "")
    if has_answer(reply):
        return reply
    texts = [t for t in reading.last_assistant_texts(folder) if has_answer(t)]
    return texts[-1] if texts else reply


def local_hook_problems() -> list[str]:
    """The local hook, probed in process: the network and a foreign path denied, the folder not."""
    hook = gaia._load("h2h_local_hook", HERE / "local_hook.py")
    cwd = "C:/sp-runs/h2h/probe/work"
    cases = [
        ("Bash", {"command": "curl -s https://example.com"}, True),
        ("Read", {"file_path": "C:/Users/someone/.cache/x.jsonl"}, True),
        ("Bash", {"command": "cat ../../side/mcp.json"}, True),
        ("Read", {"file_path": "C:/sp-runs/h2h/probe/work/document.txt"}, False),
        ("Grep", {"pattern": "revenue", "path": "document.txt"}, False),
        ("mcp__bcp__search", {"query": "x"}, False),
        ("mcp__sanchopanza-fetch__fetch_passages", {"url": "https://example.com"}, True),
        ("mcp__sanchopanza-knowledge__search", {"query": "x"}, True),
        (
            "mcp__sanchopanza-knowledge__read",
            {"url_or_path": "document.txt", "purpose": "x"},
            False,
        ),
        (
            "mcp__sanchopanza-knowledge__read",
            {"url_or_path": "C:/Users/x/a.txt", "purpose": "x"},
            True,
        ),
        ("mcp__sanchopanza-knowledge__pick", {"purpose": "x", "sources": ["*.txt"]}, False),
        ("mcp__sanchopanza-knowledge__pick", {"purpose": "x", "sources": ["../../side"]}, True),
    ]
    return [f"local hook: {tool} {args} not {'denied' if want else 'allowed'}"
            for tool, args, want in cases if hook.denied(tool, args, cwd) is not want]  # fmt: skip


def preflight(brazos: Sequence[str], flag_settings: Mapping[str, Any],
              data_problems: Sequence[str], line: Any = None,
              phase_name: str = "") -> list[str]:  # fmt: skip
    """Free: the pinned claude, the suite's data, both arms' user folders and S's line (`line`,
    the run's `--s-line`; None proves `s_install.json`), the permission mode and the user folder
    per session, the local hook."""
    problems = [
        *gaia.claude_problems(),
        *data_problems,
        *gaia.arms_preflight(brazos, line, phase_name),
    ]
    probe = gaia.argv_for("SONNET", gaia.RUNS / "s.json", gaia.RUNS / "m.json", 1.0, "q",
                          tools=TOOLS, disallowed=DISALLOWED)  # fmt: skip
    return [*problems, *gaia.isolation_problems(flag_settings, probe), *local_hook_problems()]


def run_live(args: Any, steps: list, rows: list, make_session: Callable,
             sessions: pathlib.Path, caps: Mapping[str, float],
             ceilings: Mapping[str, float],
             problems: Sequence[str]) -> tuple[int, list]:  # fmt: skip
    """The paid loop, GAIA's: preflight problems stop it; SIGINT ignored, the S line sealed,
    caps, the ceiling bounded in code, STOP-LIMIT and resume."""
    if problems:
        print("preflight: " + "; ".join(problems), file=sys.stderr)
        return 3, rows
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    top = min(gaia.MAX_CEILING_USD, ceilings.get(args.phase, gaia.MAX_CEILING_USD))
    if not 0 < args.ceiling <= top:
        raise SystemExit(f"--ceiling must be in (0, {top:g}] USD for phase {args.phase!r}")
    ctx = gaia.phase_context(args.phase, args.brazos, gaia.live_line(args))
    cap = max(caps[m] for m in args.models)
    limits = phase.Limits(session_max_usd=cap, ceiling_usd=args.ceiling)
    session = make_session(ctx)
    others = [pathlib.Path(p) for p in getattr(args, "joint_with", None) or []]
    if others:
        session = joint_guard(session, sessions, others, cap, args.ceiling)
    return run_guarded(steps, rows, limits, session, sessions)


def write_report(result: Mapping[str, Any], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
