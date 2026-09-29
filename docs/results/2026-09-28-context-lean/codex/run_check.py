"""ONE end-to-end check of the sanchopanza archive inside OpenAI's Codex CLI.

Nothing here spends unless `--i-am-authorised` is passed. Without it the script writes the
isolated Codex home and the task folder, checks login and hook trust, and prints the commands;
that is free.

    python run_check.py                       # free: prepare, check login and trust, print
    python run_check.py --i-am-authorised     # ONE session, two turns, on the ChatGPT login

Everything runs in an isolated CODEX_HOME (never `~/.codex`), on a ChatGPT login only (an API
key login is refused, and OPENAI_API_KEY / CODEX_API_KEY are removed from the environment).
The hooks are not force-trusted: the owner reviews and trusts them once in the Codex TUI
(`/hooks`), which is the path a real user takes, and the check refuses to run until they are.

1. `codex exec --json` turn 1: run `build_log.py` once (a ~10 KB log, one needed line).
2. `codex exec resume <thread> --json` turn 2: asks for that line's value.

Then it reads the two JSONL streams, the hook journal, the archive and the session rollout and
writes `results/check-<time>.json`: hooks fired, archive written (and whether Codex had cut the
output before the hook), additionalContext recorded in the rollout, `search_archive` called or
not, whether the tool was re-run, the answer, and usage totals.

Caps: one session; turn 2 is skipped if turn 1 used more than `--max-input-tokens`; each turn
is killed after `--timeout` seconds. Model: `gpt-6-luna` by default ("Fast and affordable
model for easier tasks" in codex-rs/models-manager/models.json), reasoning effort low.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from make_task import make  # noqa: E402

from sanchopanza.harness import codex  # noqa: E402

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_WORK = Path(tempfile.gettempdir()) / "sanchopanza-codex-check"
INSTALL = (
    "codex is not on PATH. For this check only, without a global install:\n"
    "  npm install --prefix <dir> @openai/codex   and pass --codex <dir>/node_modules/.bin/codex\n"
    "or globally, if you prefer: npm i -g @openai/codex"
)
# Codex's sandboxed PowerShell has no `python` on PATH (found in the first check): full path.
TURN_1 = (
    "Run `.\\build_log.cmd` exactly once in this folder. Then answer in one sentence: did "
    "the build succeed, and about how many lines did it print? Do not quote any line of the log."
)
TURN_2 = (
    "What was the exact value of RELEASE_TOKEN in the log that build_log.py printed in the "
    "previous turn? Do not run build_log.py again: it prints a new token on every run. Reply "
    "with the value only."
)
STRIPPED_ENV = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")
HOOK_EVENTS = ("post_tool_use", "session_start")


# --- setup ----------------------------------------------------------------------------------


def codex_env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV}
    return {**env, "CODEX_HOME": str(home)}


def desired_files(task: Path, args: argparse.Namespace) -> dict[str, str]:
    """config.toml and hooks.json from `harness.codex`: the text a project's `.codex/` gets."""
    extra = {"model": json.dumps(args.model), "model_reasoning_effort": json.dumps(args.effort)}
    if args.compact_at:
        extra = {**extra, "model_auto_compact_token_limit": str(int(args.compact_at))}
    return {
        "config.toml": codex.config_toml(
            archive=task / ".sanchopanza" / "archive",
            tool_output_token_limit=args.tool_output_token_limit,
            extra=extra,
        ),
        "hooks.json": codex.hooks_json(),
    }


def write_home(home: Path, files: dict[str, str]) -> list[str]:
    """Write what is missing; never overwrite. Codex appends the hooks' trust to config.toml
    and a changed hooks.json loses it, so a difference is reported, not fixed."""
    home.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    for name, text in files.items():
        path = home / name
        if name == "hooks.json" and _toml_hooks(home):
            continue  # declared in config.toml instead: both at once load twice (0.158.0)
        if not path.exists():
            path.write_text(text, encoding="utf-8")
        elif name == "hooks.json" and path.read_text(encoding="utf-8") != text:
            problems = [
                *problems,
                f"{path} differs from what harness.codex generates now; "
                "delete it (and its [hooks.state] in config.toml) and re-trust",
            ]
        elif name == "config.toml" and not _contains(
            tomllib.loads(path.read_text("utf-8")), tomllib.loads(text)
        ):
            problems = [
                *problems,
                f"{path} was written with other options; delete it to "
                "regenerate (you will have to trust the hooks again)",
            ]
    return problems


def _contains(actual: Any, wanted: Any) -> bool:
    """Every key and value of `wanted` is in `actual` (Codex may add hooks.state and reformat)."""
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and all(
            k in actual and _contains(actual[k], v) for k, v in wanted.items()
        )
    return actual == wanted


def _toml_hooks(home: Path) -> bool:
    """Whether config.toml declares hook events itself (`[[hooks.<Event>]]`)."""
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    names = {"post_tool_use": "PostToolUse", "session_start": "SessionStart"}
    return any(names[event] in config.get("hooks", {}) for event in HOOK_EVENTS)


def trusted_hooks(home: Path) -> list[str]:
    """Hook events of ours (from hooks.json or config.toml) with a trusted hash in hooks.state."""
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    state = config.get("hooks", {}).get("state", {})
    return [
        event
        for event in HOOK_EVENTS
        if any(
            ("hooks.json" in key or "config.toml" in key)
            and f":{event}:" in key
            and value.get("trusted_hash")
            for key, value in state.items()
            if isinstance(value, dict)
        )
    ]


def exec_command(exe: str, task: Path, prompt: str, thread: str | None) -> list[str]:
    # --no-daemon: on Windows the shared app-server's socket path under %TEMP% exceeds SUN_LEN
    # and Codex refuses to start (found by the owner on 0.158.0)
    # `exec resume` takes neither --sandbox nor --cd (0.158.0): the sandbox goes as a config
    # override for both turns, and the folder only on the first (the thread keeps it).
    head = [exe, "--no-daemon", "exec", *(["resume", thread] if thread else [])]
    where = [] if thread else ["--cd", str(task)]
    sandbox = os.environ.get("CHECK_SANDBOX", "read-only")  # third check: the venv fails inside it
    return [
        *head,
        "--json",
        "--skip-git-repo-check",
        "-c",
        f'sandbox_mode="{sandbox}"',
        *where,
        prompt,
    ]


def login_status(exe: str, home: Path) -> str:
    done = subprocess.run(
        [exe, "login", "status"],
        env=codex_env(home),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return (done.stdout + done.stderr).strip()


# --- reading what happened ------------------------------------------------------------------


def events(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            out = [*out, value]
    return out


def summary_of(stream: list[dict[str, Any]]) -> dict[str, Any]:
    done = [
        e["item"]
        for e in stream
        if e.get("type") == "item.completed" and isinstance(e.get("item"), dict)
    ]
    usage = [e["usage"] for e in stream if e.get("type") == "turn.completed" and "usage" in e]
    messages = [i.get("text", "") for i in done if i.get("type") == "agent_message"]
    commands = [i for i in done if i.get("type") == "command_execution"]
    logs = [c for c in commands if "build_log" in str(c.get("command"))]
    return {
        "thread_id": next(
            (e.get("thread_id") for e in stream if e.get("type") == "thread.started"), None
        ),
        "usage": usage[-1] if usage else None,
        "failed": [e for e in stream if e.get("type") in ("turn.failed", "error")],
        "final_message": messages[-1] if messages else "",
        "commands": [
            {
                "command": c.get("command"),
                "exit": c.get("exit_code"),
                "chars": len(c.get("aggregated_output") or ""),
            }
            for c in commands
        ],
        "log_runs": len(logs),
        "mcp_calls": [
            {
                "server": m.get("server"),
                "tool": m.get("tool"),
                "arguments": m.get("arguments"),
                "status": m.get("status"),
            }
            for m in done
            if m.get("type") == "mcp_tool_call"
        ],
        "first_log_output": (logs[0].get("aggregated_output") or "") if logs else "",
    }


def walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for inner in value.values():
            yield from walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from walk(inner)


def rollout_facts(paths: list[str]) -> dict[str, Any]:
    """From the session rollout: our additionalContext recorded, last request size, limits."""
    seen, last_usage, rate_limits, read = False, None, None, []
    for raw in dict.fromkeys(p for p in paths if p):
        path = Path(raw)
        if not path.exists():
            continue
        read = [*read, str(path)]
        seen = seen or codex.MARK in path.read_text(encoding="utf-8", errors="replace")
        for node in (n for record in events(path) for n in walk(record)):
            if isinstance(node.get("last_token_usage"), dict):
                last_usage = node["last_token_usage"]
            if node.get("rate_limits"):
                rate_limits = node["rate_limits"]
    return {
        "rollouts_read": read,
        "additional_context_in_rollout": seen,
        "last_request_usage": last_usage,
        "rate_limits": rate_limits,
    }


def archive_facts(task: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    pattern = re.compile(manifest["needle_pattern"])
    entries = []
    for path in sorted((task / ".sanchopanza" / "archive").glob("*/*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = [
            *entries,
            {"path": str(path), "chars": len(text), "tokens": pattern.findall(text)},
        ]
    journal = events(task / ".sanchopanza" / codex.JOURNAL)
    sizes = (manifest["expected_chars"], manifest["expected_chars_crlf"])
    return {
        "entries": entries,
        "post_tool_use_fired": sum(r.get("event") == "PostToolUse" for r in journal),
        "session_start_fired": sum(r.get("event") == "SessionStart" for r in journal),
        "context_emitted": [r.get("context") for r in journal if r.get("context")],
        "log_archived_whole": any(
            abs(e["chars"] - s) <= 2 for e in entries if e["tokens"] for s in sizes
        ),
        "archived_tokens": sorted({t for e in entries for t in e["tokens"]}),
        "transcripts": [r.get("transcript") for r in journal if r.get("transcript")],
    }


def verdict(t1: dict, t2: dict | None, arch: dict, roll: dict, manifest: dict) -> dict:
    first = re.findall(manifest["needle_pattern"], t1.get("first_log_output", ""))
    truth = first[0] if first else (arch["archived_tokens"] or [""])[0]
    answer = (t2 or {}).get("final_message", "").strip()
    calls = [*t1.get("mcp_calls", []), *(t2 or {}).get("mcp_calls", [])]
    return {
        "true_token": truth,
        "answer": answer,
        "answer_correct": bool(truth) and truth in answer,
        "hooks_fired": arch["post_tool_use_fired"] > 0,
        "session_start_note": arch["session_start_fired"] > 0,
        "archive_holds_true_token": bool(truth) and truth in arch["archived_tokens"],
        "log_archived_whole": arch["log_archived_whole"],
        "additional_context_emitted": bool(arch["context_emitted"]),
        "additional_context_in_rollout": roll["additional_context_in_rollout"],
        "search_archive_called": any(codex.SEARCH_TOOL in str(c.get("tool")) for c in calls),
        "tool_rerun": t1.get("log_runs", 0) + (t2 or {}).get("log_runs", 0) > 1,
        "usage_turn_1": t1.get("usage"),
        "usage_after_turn_2": (t2 or {}).get("usage"),
    }


# --- running --------------------------------------------------------------------------------


def run_turn(cmd: list[str], env: dict[str, str], out: Path, timeout: int) -> int:
    with out.open("w", encoding="utf-8") as handle:
        try:
            done = subprocess.run(
                cmd,
                env=env,
                stdout=handle,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return -1
    out.with_suffix(".stderr.txt").write_text(done.stderr or "", encoding="utf-8")
    return done.returncode


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ONE Codex check of the sanchopanza archive")
    parser.add_argument(
        "--i-am-authorised",
        action="store_true",
        help="run the ONE Codex session (uses ChatGPT plan usage)",
    )
    parser.add_argument("--codex", default=None, help="codex executable (default: on PATH)")
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="low")
    parser.add_argument(
        "--tool-output-token-limit",
        type=int,
        default=None,
        help="default: the model's own (10,000 tokens); a 10 KB log fits",
    )
    parser.add_argument(
        "--compact-at",
        type=int,
        default=None,
        help="model_auto_compact_token_limit, to force compaction before turn 2",
    )
    parser.add_argument(
        "--max-input-tokens",
        type=int,
        default=400_000,
        help="skip turn 2 when turn 1 already used more input tokens",
    )
    parser.add_argument("--timeout", type=int, default=300, help="seconds per turn")
    return parser.parse_args(argv)


def preflight(args: argparse.Namespace, home: Path, task: Path, exe: str | None) -> int:
    """0 when everything is in place; otherwise the reason is printed and a code returned."""
    problems = write_home(home, desired_files(task, args))
    print(f"CODEX_HOME={home}\ntask={task}")
    print("turn 1:", " ".join(exec_command(exe or "codex", task, TURN_1, None)))
    print("turn 2:", " ".join(exec_command(exe or "codex", task, TURN_2, "<thread_id>")))
    for problem in problems:
        print("config:", problem)
    if problems:
        return 5
    if not exe:
        print(INSTALL)
        return 2
    version = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False)
    print("codex:", version.stdout.strip())
    status = login_status(exe, home)
    print("login:", status or "(no output)")
    if "ChatGPT" not in status:
        print(f"Log in with ChatGPT into this home only:  CODEX_HOME={home} {exe} login")
        return 3
    trusted = trusted_hooks(home)
    if set(trusted) != set(HOOK_EVENTS):
        print(
            f"Hooks not trusted yet ({trusted or 'none'}). Open `CODEX_HOME={home} {exe}` in "
            f"{task}, review the two sanchopanza hooks under /hooks, trust them, quit "
            "without sending a prompt."
        )
        return 6
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    work = args.work.resolve()
    home, task = work / "codex-home", work / "task"
    manifest = make(task)
    exe = args.codex or shutil.which("codex")
    code = preflight(args, home, task, exe)
    if code or not args.i_am_authorised:
        print("Nothing run." + ("" if code else " Pass --i-am-authorised to run the ONE session."))
        return code or 4

    env, stamp = codex_env(home), time.strftime("%Y%m%d-%H%M%S")
    t1_path, t2_path = work / f"turn1-{stamp}.jsonl", work / f"turn2-{stamp}.jsonl"
    code1 = run_turn(exec_command(exe, task, TURN_1, None), env, t1_path, args.timeout)
    t1, t2, code2 = summary_of(events(t1_path)), None, None
    used = int((t1.get("usage") or {}).get("input_tokens") or 0)
    if code1 == 0 and t1["thread_id"] and used <= args.max_input_tokens:
        code2 = run_turn(
            exec_command(exe, task, TURN_2, t1["thread_id"]), env, t2_path, args.timeout
        )
        t2 = summary_of(events(t2_path))
    arch = archive_facts(task, manifest)
    roll = rollout_facts(arch["transcripts"])
    result = {
        "model": args.model,
        "effort": args.effort,
        "compact_at": args.compact_at,
        "tool_output_token_limit": args.tool_output_token_limit,
        "exit_codes": [code1, code2],
        "turn_1": {k: v for k, v in t1.items() if k != "first_log_output"},
        "turn_2": {k: v for k, v in t2.items() if k != "first_log_output"} if t2 else None,
        "archive": arch,
        "rollout": roll,
        "verdict": verdict(t1, t2, arch, roll, manifest),
    }
    out = HERE / "results" / f"check-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["verdict"], indent=2))
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
