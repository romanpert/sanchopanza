"""F2 runner: memory against the handoff ritual (docs/results/2026-10-16-memory-f2/prereg.md).

A triple is one scene (`scenes_handoff.py`) at one repetition, run in three arms, one after the
other, each in its own fresh repository and clean Claude Code user (`carry.clean_config`, the
arm's own CLAUDE_CONFIG_DIR, the subscription's OAuth token only):

- `N0`: session 1 (the scene's `first`), then session 2, a new session, with the `continue` line;
- `H`: session 1; then the same session resumed once (`claude -p --resume <session id>`) with
  HANDOFF_REQUEST; then session 2, a new session, whose prompt is exactly that turn's text;
- `S`: sanchopanza as `sanchopanza install` leaves it in a project today (`carry_s.install`, the
  memory cell's S), session 2 with the same `continue` line as N0.

**What the agent sees is neutral.** Each arm works in `WORK/<run dir>/t<NN>-<x>` (NN the
triple's number, x a letter shuffled per triple by a seeded RNG), its repository in `repo/`
under it; neither path, nor any file the agent can open, names the scene, the arm, the model or
the lot. Streams, `handoff.txt` and the rows (with the folder of each arm) go to the lot's own
folder, `OUT/<run>/`, which the agent never sees. The agent's environment carries no
PYTHONPATH (`handoff_call.agent_env`).

Every session and the handoff turn: the same model, `--max-budget-usd` CALL_CAPS[model],
`--settings "{}"`, `--allowedTools` carry.TOOLS, `stream-json`. After session 1 (and H's
handoff) the work is committed. After session 2: the repository's tests and the scene's checks,
run with the agent's environment (no key, no PYTHONPATH).

NOT RUN rules, stops and caps: prereg, and the functions below (`session_cut`, `handoff_cut`,
`run_plan`).

    python benchmarks/memory_carry/handoff.py --run f2-pilot [--out DIR] [--dry] [--cap USD]
    python benchmarks/memory_carry/handoff.py --preflight [--out DIR]
    python benchmarks/memory_carry/handoff.py --seal          # writes the seal; never run live
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "benchmarks"))

import carry  # noqa: E402
import carry_s  # noqa: E402
import handoff_call as hc  # noqa: E402
import handoff_cost  # noqa: E402
import handoff_seal  # noqa: E402
import meter  # noqa: E402
import winupdate  # noqa: E402
from scenes_handoff import CHECKS, HANDOFF, HANDOFF_PILOT, check_code, names_c_d  # noqa: E402

from sanchopanza import durable  # noqa: E402

ARMS = ("N0", "H", "S")
LETTERS = ("a", "b", "c")
HANDOFF_REQUEST = "Give me a prompt to continue this work in a clean session."
CALL_CAPS = {"sonnet": 0.80, "opus": 1.50}
# One turn past --max-budget-usd (Claude Code checks it between turns): it reads a 200,000-token
# context from the cache, writes 50,000 new tokens to it and answers 20,000, at Claude Code's own
# rates (meter.CLAUDE_CODE_RATES, the dearer cache write). Sonnet 5.5: 0.04 + 0.20 + 0.20 =
# 0.44; Opus 5.5: 0.04 + 0.40 + 0.40 = 0.84. The memory cell's dearest session was 0.115.
WORST_CONTEXT, WORST_WRITE, WORST_OUTPUT = 200_000, 50_000, 20_000
MODEL_IDS = {"sonnet": meter.SONNET_55, "opus": meter.OPUS_55}


def worst_turn(model: str) -> float:
    r = meter.rates_of(meter.CLAUDE_CODE_RATES, MODEL_IDS[model])
    usd = WORST_CONTEXT * r.read + WORST_WRITE * max(r.write_5m, r.write_1h) + \
        WORST_OUTPUT * r.output  # fmt: skip
    return round(usd / 1e6, 4)


WORST_TURN = {m: worst_turn(m) for m in CALL_CAPS}
NIGHT_CAP = 230.0  # USD at list price over every run of the night (handoff_night.py)
RUNS: dict[str, dict[str, Any]] = {
    "f2-pilot": {"model": "sonnet", "scenes": HANDOFF_PILOT, "repeats": [0], "cap": 11.5,
                 "dir": "r1"},
    "f2-sonnet": {"model": "sonnet", "scenes": list(HANDOFF), "repeats": [1, 2, 3, 4],
                  "cap": 109.0, "dir": "r2"},
    "f2-opus": {"model": "opus", "scenes": list(HANDOFF), "repeats": [1, 2], "cap": 106.0,
                "dir": "r3"},
    # W17 (docs/results/2026-10-16-memory-w17/prereg.md): two arms, S at user scope, call caps
    # about 4x (Sonnet) and 2.6x (Opus) F2's dearest session, a stratum of repetitions whose
    # session 2 is BARE_LINE. The lot's 45 USD (LOTS["w17"]["night_cap"]) binds both run caps
    # in a root that holds both; the redo's root (Amendment 1) runs only w17-opus, under its 33.
    "w17-sonnet": {"model": "sonnet", "scenes": list(HANDOFF), "repeats": [1, 2, 3, 4],
                   "bare": [3, 4], "cap": 17.0, "dir": "r1", "lot": "w17", "arms": ("N0", "S"),
                   "scope": "user", "call_caps": {"sonnet": 0.50, "opus": 0.80},
                   "jev_cap": 0.50},
    "w17-opus": {"model": "opus", "scenes": list(HANDOFF), "repeats": [1, 2, 3], "bare": [3],
                 "cap": 33.0, "dir": "r2", "lot": "w17", "arms": ("N0", "S"), "scope": "user",
                 "call_caps": {"sonnet": 0.50, "opus": 0.80}, "jev_cap": 0.50},
}  # fmt: skip
BARE_LINE = "Let's continue."  # W17's stratum: a session 2 line that names nothing
CAP_FILE = "jev-cap.json"  # beside the run's key: the hooks' Jev cap (carry_hook.CAP_FILE)
SESSION_TIMEOUT = 900
HANDOFF_TIMEOUT = 600
CARRIED = 0.5  # the resumed turn's first request holds at least half of session 1's last one
INTERRUPTS = 2  # an arm cut by a crash or reboot runs again whole at most this many times
EXPECTED_ARM_S = {"sonnet": 300, "opus": 420}  # one arm, for the midnight rule
WALL_FACTOR = 1.5
MIDNIGHT_MARGIN_S = 120
OUT = Path(r"C:\sp-runs\memory-f2")  # the lot's own files: rows, ledger, streams, logs
WORK = Path(r"C:\sp-runs\w16")  # where the agent works: no name of the lot, scene or arm
RESULTS = handoff_seal.RESULTS
BROKEN_AFTER = 3  # arms in a row with a session that ended without a result stop the run
EXIT = {"": 0, "cap": 2, "limit": 3, "harness": 4, "manual": 6, "broken": 7, "quiet": 8}
seal, seal_ok = handoff_seal.seal, handoff_seal.seal_ok
# A lot: the runs of one night, its cap over all of them, where its own files and the agents'
# folders go, the run whose automatic gate decides whether the rest run, and whether arms may
# run in the quiet hours (Windows Update restarts this machine between 02:00 and 08:00).
LOTS: dict[str, dict[str, Any]] = {
    "f2": {"sequence": ("f2-pilot", "f2-sonnet", "f2-opus"), "night_cap": NIGHT_CAP, "out": OUT,
           "work": WORK, "gate": "f2-pilot", "quiet": False},
    # W17's Opus redo (prereg, Amendment 1): new roots, so it cannot read, resume from, set
    # aside or charge anything of the interrupted run, left where it was in `W17_INTERRUPTED`.
    "w17": {"sequence": ("w17-sonnet", "w17-opus"), "night_cap": 45.0,
            "out": Path(r"C:\sp-runs\memory-w17-redo"), "work": Path(r"C:\sp-runs\w19"),
            "gate": None, "quiet": True},
}  # fmt: skip
W17_INTERRUPTED = (Path(r"C:\sp-runs\memory-w17"), Path(r"C:\sp-runs\w18"))  # 16 Oct: evidence
QUIET = (dt.time(2, 0), dt.time(8, 0))  # no W17 arm runs, even in part, between these
# ... unless Windows Update is paused at least winupdate.MARGIN past the check and no restart is
# pending (Amendment 1). The keys are the guard-pointers lot's (`long_start.RESTART_KEYS`): that
# module is not imported here (its `carry` is adopt's, not this folder's).
_WINDOWS = r"SOFTWARE\Microsoft\Windows\CurrentVersion"
RESTART_KEYS = (_WINDOWS + r"\WindowsUpdate\Auto Update\RebootRequired",
                _WINDOWS + r"\Component Based Servicing\RebootPending")  # fmt: skip


def restart_pending() -> str:
    """The first of `RESTART_KEYS` present under HKLM ("" when none, or off Windows)."""
    try:
        import winreg
    except ImportError:
        return ""
    for key in RESTART_KEYS:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key))
        except OSError:
            continue
        return key.rsplit("\\", 1)[-1]
    return ""


def interrupted_refusal(*paths: Path) -> str:
    """W17's redo (Amendment 1): why one of `paths` is, or lies under, the interrupted run's root
    or work folder ("" when none does). Those folders are evidence: never resumed, set aside,
    charged or written."""
    for path in paths:
        for old in W17_INTERRUPTED:
            if path.resolve().is_relative_to(old.resolve()):
                return f"{path} is in the interrupted run's {old}; the redo uses its own"
    return ""


def lot_of(run: str) -> str:
    return str(RUNS[run].get("lot", "f2"))


def arms_of(run: str) -> tuple[str, ...]:
    return tuple(RUNS[run].get("arms", ARMS))


def scope_of(run: str | None) -> str:
    """Where arm S's `sanchopanza install` writes: the scene's repository (F2) or the user's
    settings, which under a clean user are the arm's own CLAUDE_CONFIG_DIR (W17)."""
    return str(RUNS[run].get("scope", "project")) if run else "project"


def call_cap(run: str | None, model: str) -> float:
    caps = (RUNS[run].get("call_caps") if run else None) or CALL_CAPS
    return float(caps[model])


def line_of(run: str | None, rep: int) -> str:
    """Session 2's line: "bare" (BARE_LINE) in the run's bare repetitions, else "named" (the
    scene's own `continue` line, as F2)."""
    return "bare" if run and rep in RUNS[run].get("bare", ()) else "named"


def work_of(run: str) -> Path:
    return Path(LOTS[lot_of(run)]["work"]) / RUNS[run]["dir"]


# ---- plan ----------------------------------------------------------------------------------------


def build_plan(run: str) -> list[tuple[str, str, str, int]]:
    """(scene, model, arm, repetition) for every arm of every triple (a pair in a two-arm run),
    the arms of a triple one after the other, their order rotated from triple to triple (and
    from repetition to repetition) so each arm runs first, second and third about equally
    often."""
    spec, arms = RUNS[run], arms_of(run)
    out = []
    for rep in spec["repeats"]:
        for i, name in enumerate(spec["scenes"]):
            k = (i + rep) % len(arms)
            out += [(name, spec["model"], arm, rep) for arm in (*arms[k:], *arms[:k])]
    return out


def folder_name(run: str, triple: int, arm: str) -> str:
    """`t<NN>-<x>`: the triple's number and a letter per arm, shuffled per triple with a seed
    of the run and the triple, so the letter says nothing about the arm (a two-arm run takes
    the first two letters of the same shuffle)."""
    letters = list(LETTERS)
    random.Random(f"{run}/{triple}").shuffle(letters)
    arms = arms_of(run) if run in RUNS else ARMS
    return f"t{triple:02d}-{dict(zip(arms, letters[: len(arms)], strict=True))[arm]}"


def calls_of(arm: str) -> int:
    return 3 if arm == "H" else 2


def reserve_of(model: str, arm: str, run: str | None = None) -> float:
    """What the next arm may spend at most: each call at its cap plus one worst turn past it,
    and S's Jev reserve per session."""
    jev = 2 * carry_s.JEV_RESERVE if arm == "S" else 0.0
    return calls_of(arm) * (call_cap(run, model) + WORST_TURN[model]) + jev


# ---- a claude call and its NOT RUN rules ---------------------------------------------------------


def command(prompt: str, model: str, resume: str | None = None,
            cap: float | None = None) -> list[str]:  # fmt: skip
    """The memory cell's command shape; a prompt that begins with "-" (a handoff can start with a
    list item) goes last, after "--", so it is never read as an option. `cap`: the run's
    `--max-budget-usd` (F2's CALL_CAPS when not given)."""
    if prompt.startswith("-"):
        base = command("x", model, resume, cap)
        return [*base[:2], *base[3:], "--", prompt]
    head = ["claude", "-p", prompt, *(["--resume", resume] if resume else [])]
    usd = CALL_CAPS[model] if cap is None else cap
    return [*head, "--model", carry.MODELS[model], "--output-format", "stream-json", "--verbose",
            "--max-budget-usd", f"{usd:.2f}", "--settings", "{}",
            "--allowedTools", *carry.TOOLS]  # fmt: skip


def pinned(result: dict[str, Any], model: str) -> bool:
    init = result.get("init") or {}
    return init.get("version") == carry.PIN and init.get("model") == carry.MODELS[model]


def session_cut(result: dict[str, Any], model: str) -> str:
    """Why a session is NOT RUN ("" when it ran)."""
    if result.get("timeout"):
        return "timeout"
    if not carry.session_ran(result):
        return f"{result['tag']} ended without a result (exit {result.get('returncode')})"
    if not pinned(result, model):
        init = result.get("init") or {}
        return f"{result['tag']} ran {init.get('model')} on {init.get('version')}"
    return ""


def handoff_cut(turn: dict[str, Any], model: str) -> str:
    """Why H's handoff turn is NOT RUN ("" when its text can be pasted)."""
    if turn.get("timeout"):
        return "handoff: timeout"
    if turn.get("returncode") != 0 or turn.get("subtype") != "success":
        return f"handoff: exit {turn.get('returncode')}, {turn.get('subtype') or 'no result'}"
    if not pinned(turn, model):
        init = turn.get("init") or {}
        return f"handoff: ran {init.get('model')} on {init.get('version')}"
    text = str(turn.get("text") or "")
    if not text.strip():
        return "handoff: no text"
    if not turn.get("cost_reported") or float(turn.get("cost") or 0.0) <= 0.0:
        return "handoff: no cost reported"
    if turn.get("context_carried") is False:
        return "handoff: the resumed turn did not carry session 1's context"
    if len(subprocess.list2cmdline(command(text, model))) >= hc.WIN_CMDLINE:
        return f"handoff: session 2's command line would pass {hc.WIN_CMDLINE} characters"
    return ""


def carried(first: dict[str, Any], turn: dict[str, Any]) -> bool | None:
    """The resumed turn's first request holds at least CARRIED of session 1's last request (a
    fresh session would hold only the system prompt and the request). Half, not all: on resume
    Claude Code may drop earlier thinking blocks from the context."""
    before, after = first.get("last_prompt"), turn.get("first_prompt")
    if not before or not after:
        return None
    return after >= CARRIED * before


# ---- one arm -------------------------------------------------------------------------------------


def decoys(name: str) -> list[str]:
    """carry.DECOYS rules of other scenes for S's store, never one the scene names `near`."""
    near = set(HANDOFF[name]["near"])
    pool = sorted(k for k in carry.DECOY_POOL if k not in near)
    start = sum(map(ord, name)) % len(pool)
    return [carry.DECOY_POOL[k] for k in (pool[start:] + pool[:start])[: carry.DECOYS]]


def seed(work: Path, repo: Path, name: str) -> None:
    """The decoys in S's store, as earlier sessions of this project left them (carry.seed)."""
    rules = [{"text": text, "p": 0.9, "session": f"earlier-{i}", "index": 1,
              "at": 1_790_000_000.0 + i * 3600, "files": carry.said_while(text)}
             for i, text in enumerate(decoys(name))]  # fmt: skip
    payload = json.dumps({"rules": rules[::-1], "asked": [], "audited": []})
    key = carry.project_name(repo)
    for folder in {key, key[:1].lower() + key[1:], key[:1].upper() + key[1:]}:
        (work / "store" / folder).mkdir(parents=True, exist_ok=True)
        (work / "store" / folder / "rules.json").write_text(payload, encoding="utf-8")


def steps_of(arm: str, line: str = "named") -> list[str]:
    resume = f"handoff: claude -p --resume <session 1 id> {HANDOFF_REQUEST!r}"
    second = "handoff.txt" if arm == "H" else "continue" if line == "named" else "bare"
    return ["session 1: first", *([resume] if arm == "H" else []), f"session 2: {second}"]


def second_prompt(scene: dict[str, Any], line: str) -> str:
    return BARE_LINE if line == "bare" else str(scene["continue"])


def arm_run(out: Path, work: Path, name: str, model: str, arm: str, rep: int, keyfile: Path,
            dry: bool, clean: bool = True, run: str | None = None) -> dict[str, Any]:  # fmt: skip
    """One arm: the agent works in `work` (neutral), its records go to `out/arms/<work name>`.
    `run` gives the arm its scope, session 2's line and its call cap (F2's when None)."""
    rec = out / "arms" / work.name
    scene = HANDOFF[name]
    scope, line = scope_of(run), line_of(run, rep)
    cap = call_cap(run, model) if run else None  # F2: its own CALL_CAPS, as sealed
    work.mkdir(parents=True, exist_ok=True)
    rec.mkdir(parents=True, exist_ok=True)
    prepare = (lambda repo: carry_s.install(work, repo, keyfile, carry.environment())) \
        if arm == "S" and scope == "project" else None  # fmt: skip
    repo = carry.build(work, {"files": scene["files"]}, prepare)
    config = carry.clean_config(work) if clean else None
    if arm == "S" and scope == "user":
        carry_s.install_user(work, config or carry.clean_config(work), keyfile,
                             carry.environment())  # fmt: skip
    if arm == "S":
        seed(work, repo, name)
        for kept in ("install.txt", "install"):  # the install's output and copies: records
            if (work / kept).exists():
                os.replace(work / kept, rec / kept)
    row: dict[str, Any] = {"scene": name, "model": model, "arm": arm, "repeat": rep,
                           "folder": str(work), "planned": steps_of(arm, line), "line": line,
                           "scope": scope, "call_cap": call_cap(run, model)}  # fmt: skip
    if dry:
        return {**row, "dry": True, "repo": str(repo)}
    secrets = [s for s in (carry.clean_token() if clean else "", key_of(keyfile)) if s]
    try:
        done = sessions_of(work, rec, repo, scene, model, arm, config,
                           second_prompt(scene, line), cap, scope)  # fmt: skip
    finally:
        found = [carry.scrub(folder, s) for folder in (work, rec) for s in secrets]
    scrubbed = [f for got in found for f in got[0]]
    in_git = [f for got in found for f in got[1]]
    flags = {**({"token_scrubbed": scrubbed} if scrubbed else {}),
             **({"token_in_git": in_git} if in_git else {})}  # fmt: skip
    full: dict[str, Any] = {**row, **done, **flags}
    for secret in secrets:  # the OAuth token and the TypeSafe key never land in a row
        full = carry.redact(full, secret)
    if run and arm == "S" and isinstance(full.get("kept_all"), bool):
        from handoff_analyze import own_sendbacks  # the row keeps what the analysis reads

        full = {**full, "sendbacks_other_rule": own_sendbacks(full, None)}
    return full


def key_of(keyfile: Path) -> str:
    """The TypeSafe key the harness wrote for S's hooks, to scrub it (never printed)."""
    return keyfile.read_text(encoding="utf-8").strip() if keyfile.is_file() else ""


def sessions_of(work: Path, rec: Path, repo: Path, scene: dict[str, Any], model: str, arm: str,
                config: Path | None, line_text: str | None = None, cap: float | None = None,
                scope: str = "project") -> dict[str, Any]:  # fmt: skip
    projects = config / "projects" if config else carry.PROJECTS
    ran: list[dict[str, Any]] = []
    turn: dict[str, Any] = {}
    first = one(work, rec, repo, scene["first"], model, arm, "session-1", config, projects, cap,
                scope)  # fmt: skip
    ran.append(first)
    cut = session_cut(first, model) or first.get("harness_cut", "")
    if not cut and not first.get("limit_hit") and arm == "H":
        turn = handoff_step(rec, repo, first, model, config)
        cut = "" if turn.get("limit_hit") else handoff_cut(turn, model)
    limit = first.get("limit_hit") or turn.get("limit_hit")
    pasted: bool | None = None
    if not cut and not limit:
        carry.commit_wip(repo)
        prompt = turn["text"] if arm == "H" else (line_text or scene["continue"])
        second = one(work, rec, repo, prompt, model, arm, "session-2", config, projects, cap,
                     scope)  # fmt: skip
        ran.append(second)
        limit = second.get("limit_hit")
        cut = session_cut(second, model) or second.get("harness_cut", "")
        if arm == "H":
            got = hc.first_prompt_in_transcript(config, (second.get("init") or {}).get(
                "session_id"))  # fmt: skip
            pasted = None if got is None else got == prompt
            if pasted is False and not cut:  # session 2 did not get the handoff as written
                cut = "handoff: session 2's first prompt differs from handoff.txt"
    jev = carry_s.jev(work) if arm == "S" else {}
    if arm == "S" and not cut and not limit:
        broken = carry_s.pair_breaks(jev)
        cut = f"harness: {'; '.join(broken)}" if broken else ""
    calls = [*ran, *([turn] if turn else [])]
    row = {"sessions": [brief(s) for s in ran], "handoff": handoff_facts(turn, scene),
           "given": carry.given(work), "native_after_1": first.get("native", []), **jev,
           "cost": round(sum(float(s.get("cost") or 0.0) for s in calls), 6),
           "tokens": {k: sum(s["tokens"][k] for s in calls if s.get("tokens"))
                      for k in ("input", "output", "cache_read", "cache_write")},
           "subagents": sum(int(s.get("subagents") or 0) for s in calls),
           "crossed_midnight": crossed(ran), "limit_hit": bool(limit),
           **({"pasted_verbatim": pasted} if arm == "H" else {}),
           **({"hook_starts": hook_starts(work)} if arm == "S" else {})}  # fmt: skip
    if cut or limit:
        return {**row, "cut": cut or "usage limit"}
    return {**row, **checks(repo, scene)}


def hook_starts(work: Path) -> int:
    """How many SessionStart events S's memory hook answered (carry_hook's own log)."""
    path = work / "hooks.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if path.exists() else []  # fmt: skip
    return sum(1 for r in rows if r.get("sub") == "memory-hook" and
               r.get("event") == "SessionStart")  # fmt: skip


def one(work: Path, rec: Path, repo: Path, prompt: str, model: str, arm: str, tag: str,
        config: Path | None, projects: Path, cap: float | None = None,
        scope: str = "project") -> dict[str, Any]:  # fmt: skip
    """One session. At user scope no MCP server is installed (`install` only prints the line
    that would register find_in_repo), so S's check asks for the memory hook at the session's
    start instead of a connected server."""
    since = carry_s.hook_rows(work)
    cmd = command(prompt, model) if cap is None else command(prompt, model, cap=cap)
    result = charged(hc.call(rec, repo, cmd, tag, config, SESSION_TIMEOUT), model, cap)
    auto = (result.get("init") or {}).get("memory_auto")
    server = carry_s.SERVER if scope == "project" else None
    broken = carry_s.session_breaks(work, result, since, server=server) \
        if arm == "S" and carry.session_ran(result) else []  # fmt: skip
    return {
        **result,
        "native": carry.native_memory(repo, projects, auto),
        **({"harness_cut": f"harness: {tag}: {'; '.join(broken)}"} if broken else {}),
    }


def charge_of(model: str, cap: float | None) -> float:
    """What a call that reported no cost may have spent: its cap and one worst turn past it."""
    return (CALL_CAPS[model] if cap is None else cap) + WORST_TURN[model]


def charged(result: dict[str, Any], model: str, cap: float | None) -> dict[str, Any]:
    """A session whose stream reported no cost (no `result` event: a timeout, a crash, a
    killed process) is charged `charge_of`, so every cap holds in code; flagged in its row."""
    if result.get("cost_reported"):
        return result
    return {**result, "cost": charge_of(model, cap), "cost_charged": True}


def handoff_step(rec: Path, repo: Path, first: dict[str, Any], model: str,
                 config: Path | None) -> dict[str, Any]:  # fmt: skip
    """H's ritual: session 1 resumed once with HANDOFF_REQUEST; its text kept in handoff.txt."""
    sid = (first.get("init") or {}).get("session_id")
    if not sid:
        return {"returncode": None, "subtype": "", "text": "", "tag": "handoff",
                "error": "session 1 reported no session id"}  # fmt: skip
    turn = hc.call(rec, repo, command(HANDOFF_REQUEST, model, resume=str(sid)), "handoff",
                   config, HANDOFF_TIMEOUT)  # fmt: skip
    total = float(turn.get("cost") or 0.0)
    own, source = handoff_cost.turn_own(total, float(first.get("cost") or 0.0),
                                        turn.get("tokens"), model)  # fmt: skip
    turn = {**turn, "resumed": str(sid), "context_carried": carried(first, turn),
            "same_session": (turn.get("init") or {}).get("session_id") == sid,
            "cost": own, "cost_reported_total": total, "cost_source": source}  # fmt: skip
    (rec / "handoff.txt").write_text(str(turn.get("text") or ""), encoding="utf-8", newline="")
    return turn


def handoff_facts(turn: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    if not turn:
        return {}
    text = str(turn.get("text") or "")
    keys = (
        "returncode",
        "subtype",
        "cost",
        "cost_reported",
        "cost_reported_total",
        "cost_source",
        "context_carried",
        "same_session",
        "first_prompt",
        "tokens",
        "seconds",
        "tools",
        "error",
        "init",
    )
    return {**{k: turn.get(k) for k in keys if k in turn}, "chars": len(text),
            "names": names_c_d(text, scene)}  # fmt: skip


def brief(s: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "tag",
        "returncode",
        "subtype",
        "timeout",
        "cost",
        "turns",
        "tools",
        "seconds",
        "started",
        "init",
        "tokens",
        "subagents",
        "limit_hit",
        "native",
        "harness_cut",
        "cost_charged",
        "first_prompt",
        "last_prompt",
        "is_error",
        "api_error_status",
        "touched",
    )
    return {k: s.get(k) for k in keys if k in s}


def crossed(ran: list[dict[str, Any]]) -> bool:
    if len(ran) < 2:
        return False
    start = dt.datetime.fromtimestamp(ran[0]["started"]).date()
    end = dt.datetime.fromtimestamp(ran[-1]["started"] + ran[-1]["seconds"]).date()
    return start != end


def passes(repo: Path, code: str) -> bool:
    try:
        done = subprocess.run([carry.PYTHON, "-c", code], cwd=repo, capture_output=True,
                              timeout=120, env=hc.agent_env(None))  # fmt: skip
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def checks(repo: Path, scene: dict[str, Any]) -> dict[str, Any]:
    """The repository's tests and the scene's checks, with the agent's environment."""
    try:
        tests = subprocess.run([carry.PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               cwd=repo, capture_output=True, text=True, timeout=300,
                               env=hc.agent_env(None)).returncode  # fmt: skip
    except subprocess.TimeoutExpired:
        tests = -1
    found = {name: passes(repo, check_code(scene, name)) for name in CHECKS}
    return {"tests_pass": tests == 0, **{f"{k}_pass": v for k, v in found.items()},
            "kept_all": bool(found["task"] and found["fact"] and found["decision"])}  # fmt: skip


# ---- a run ---------------------------------------------------------------------------------------


def rows_of(out: Path) -> list[dict[str, Any]]:
    path = out / "f2.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def write_rows(out: Path, rows: list[dict[str, Any]]) -> None:
    """Synced before the rename: an unclean shutdown must not leave the rows zero-filled."""
    durable.replace_text(out / "f2.json", json.dumps(rows, indent=1), temp=out / "f2.json.tmp")


def ledger(out: Path) -> float:
    path = out / "ledger.jsonl"
    if not path.exists():
        return 0.0
    return sum(float(json.loads(x).get("usd") or 0.0)
               for x in path.read_text(encoding="utf-8").splitlines() if x.strip())  # fmt: skip


def book(out: Path, kind: str, usd: float, what: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    durable.append_text(out / "ledger.jsonl",
                        json.dumps({"kind": kind, "usd": round(usd, 6), "what": what,
                                    "at": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")  # fmt: skip


def lost_cost(work: Path, rec: Path, charge: float = 0.0) -> float:
    """What an interrupted arm had spent: its streams' own results and its decisions; a stream
    that reported no cost (the call was cut) counts `charge` (its cap and one worst turn)."""
    streams = [f for f in sorted(rec.glob("*.jsonl")) if f.name.startswith(("session-", "handoff"))]
    claude = sum(carry.read_stream(f)["cost"] if hc.stream_extra(f)["cost_reported"] else charge
                 for f in streams)  # fmt: skip
    return claude + (carry_s.jev(work)["jev_usd"] if work.exists() else 0.0)


def interrupts(out: Path) -> dict[str, int]:
    path = out / "interrupts.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def stop_file(out: Path, extra: Path | None) -> bool:
    return any((d / "STOP").exists() for d in (out, extra) if d is not None)


def aside(path: Path, why: str) -> None:
    """A folder kept, renamed out of the plan's way."""
    if path.exists():
        os.replace(path, path.with_name(f"{path.name}.{why}-{time.strftime('%Y%m%dT%H%M%S')}"))


def wait_for_day(seconds: float, clock: Callable[[], dt.datetime], sleep: Callable[[float], Any],
                 stopped: Callable[[], bool]) -> bool:  # fmt: skip
    """Waits while `seconds` from now would reach the next day; False if a STOP came first."""
    while True:
        now = clock()
        end = now + dt.timedelta(seconds=seconds * WALL_FACTOR + MIDNIGHT_MARGIN_S)
        if end.date() == now.date():
            return True
        if stopped():
            return False
        print(f"midnight rule: waiting at {now:%H:%M:%S}", flush=True)
        sleep(60)


def in_quiet_hours(seconds: float, now: dt.datetime) -> bool:
    """Whether an arm expected to take `seconds` (times WALL_FACTOR, plus the margin) from `now`
    would run, even in part, between QUIET's two times."""
    end = now + dt.timedelta(seconds=seconds * WALL_FACTOR + MIDNIGHT_MARGIN_S)
    start, stop = QUIET
    t = now
    while t <= end:  # minute steps: an arm takes minutes, the window hours
        if start <= t.time() < stop:
            return True
        t += dt.timedelta(minutes=1)
    return start <= end.time() < stop


def resume_interrupted(out: Path, work: Path, seen: dict[str, int],
                       charge: float = 0.0) -> tuple[dict[str, int], bool]:  # fmt: skip
    """An arm folder without a row: its spend counted (a cut call at `charge`), the folders set
    aside; True when it may run again (at most INTERRUPTS times)."""
    rec = out / "arms" / work.name
    lost = lost_cost(work, rec, charge)
    book(out, "interrupted", lost, work.name)
    seen = {**seen, work.name: seen.get(work.name, 0) + 1}
    durable.replace_text(out / "interrupts.json", json.dumps(seen))
    aside(work, "interrupted")
    aside(rec, "interrupted")
    print(f"interrupted arm {work.name}: its {lost:.3f} USD counted", flush=True)
    return seen, seen[work.name] <= INTERRUPTS


def run_plan(out: Path, run: str, keyfile: Path, dry: bool, cap: float, night: Path | None,
             clock: Callable[[], dt.datetime] = dt.datetime.now,
             sleep: Callable[[float], Any] = time.sleep,
             arm_fn: Callable[..., dict[str, Any]] = arm_run,
             work_root: Path | None = None,
             lifted: Callable[[], str] = winupdate.quiet_lifted,
             restart: Callable[[], str] = restart_pending) -> str:  # fmt: skip
    """Runs what is left of `run`; returns why it stopped ("cap", "limit", "harness", "manual",
    "broken", "quiet") or "" at its end. LIMIT.flag goes to `night` (the root) or else `out`.
    A lot with quiet hours starts no arm that would run into them ("quiet", resumable), unless
    `lifted` gives a reason (W17 Amendment 1: Windows Update paused well past the check) and
    `restart` finds no restart pending; the log records each lift before that arm."""
    work_root = work_root or work_of(run)
    plan, arms = build_plan(run), arms_of(run)
    quiet = bool(LOTS[lot_of(run)]["quiet"])
    extra = {} if lot_of(run) == "f2" else {"run": run}  # F2's arms take no run: as sealed
    pairs = lot_of(run) != "f2"
    rows = [] if dry else rows_of(out)
    done = {(r["scene"], r["model"], r["arm"], r["repeat"]) for r in rows}
    seen, failed = interrupts(out), 0
    for index, (name, model, arm, rep) in enumerate(plan):
        if (name, model, arm, rep) in done:
            continue
        work = work_root / folder_name(run, index // len(arms), arm)
        cap_of = call_cap(run, model)
        base = {"scene": name, "model": model, "arm": arm, "repeat": rep, "folder": str(work)}
        if not dry and stop_file(out, night):
            print("stop: a STOP file", flush=True)
            return "manual"
        if not dry and (work.exists() or (out / "arms" / work.name).exists()):
            seen, again = resume_interrupted(out, work, seen, charge_of(model, cap_of))
            if not again:
                rows.append({**base, "cut": f"interrupted {seen[work.name]} times", "cost": 0.0})
                write_rows(out, rows)
                continue
        spent = 0.0 if dry else ledger(out)
        first_of_triple = index % len(arms) == 0
        need = reserve_of(model, arm, run)
        if pairs and first_of_triple:  # W17: a pair starts only if both its arms fit (no orphan)
            need = sum(reserve_of(model, a, run) for a in arms)
        if spent + need > cap:
            print(f"stop: {spent:.2f} USD spent, the next arm could pass {cap}", flush=True)
            return "cap"
        expected = EXPECTED_ARM_S[model] * (len(arms) if first_of_triple else 1)
        if not dry and not wait_for_day(expected, clock, sleep, lambda: stop_file(out, night)):
            return "manual"
        if not dry and quiet and in_quiet_hours(expected, clock()):
            why = lifted()
            pending = restart() if why else ""
            if not why or pending:
                held = f" (not lifted: Windows has a restart pending, {pending})" if pending else ""
                print(f"stop: quiet hours {QUIET[0]:%H:%M}-{QUIET[1]:%H:%M}; run it again after"
                      + held, flush=True)  # fmt: skip
                return "quiet"
            print(f"quiet hours lifted for {work.name}: {why} (amendment 1)", flush=True)
        try:
            row = arm_fn(out, work, name, model, arm, rep, keyfile, dry, **extra)
        except Exception as error:  # never ends the night: the arm is NOT RUN, its spend counted
            if dry:
                raise
            row = {**base, "cut": f"harness exception: {type(error).__name__}",
                   "error": str(error)[-300:],
                   "cost": lost_cost(work, out / "arms" / work.name,
                                     charge_of(model, cap_of))}  # fmt: skip
        if dry:
            print(json.dumps({k: row[k] for k in ("scene", "model", "arm", "repeat", "folder",
                                                  "planned")}))  # fmt: skip
            continue
        usd = float(row.get("cost") or 0.0) + float(row.get("jev_usd") or 0.0)
        book(out, "arm", usd, work.name)
        if row.get("limit_hit"):  # a pause: no row; the folders kept aside, the arm runs again
            aside(work, "limit")
            aside(out / "arms" / work.name, "limit")
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            (night or out).joinpath("LIMIT.flag").write_text(f"{stamp} {run} {work.name}\n",
                                                             encoding="utf-8")  # fmt: skip
            print("stop: the subscription's usage limit (LIMIT.flag)", flush=True)
            return "limit"
        rows.append(row)
        write_rows(out, rows)
        brief_row = {k: row.get(k) for k in ("scene", "arm", "repeat", "kept_all", "task_pass",
                                             "fact_pass", "decision_pass", "intact_pass", "cut",
                                             "cost")}  # fmt: skip
        print(json.dumps(brief_row), f"spent {ledger(out):.2f}", flush=True)
        failed = failed + 1 if "without a result" in str(row.get("cut") or "") else 0
        if failed >= BROKEN_AFTER:
            print(f"stop: {failed} arms in a row ended without a result", flush=True)
            return "broken"
        if str(row.get("cut") or "").startswith("harness:"):
            print(f"stop: {row['cut']}", flush=True)
            return "harness"
    return ""


def complete(out: Path, run: str) -> bool:
    have = {(r["scene"], r["model"], r["arm"], r["repeat"]) for r in rows_of(out)}
    return all(p in have for p in build_plan(run))


def execute(run: str, out: Path, cap: float, dry: bool = False, night: Path | None = None,
            work_root: Path | None = None) -> str:  # fmt: skip
    """A whole run: refusals, the key and Jev's preflight, then the plan. A W17 run also writes
    its Jev cap beside the key (`carry_hook.CAP_FILE`): every hook's decider then goes through
    `CappedDecider` on that run's own ledger (`capped_sub.py`)."""
    work_root = work_root or (out / "work" if dry else work_of(run))
    lot = lot_of(run)
    if lot == "w17" and (why := interrupted_refusal(out, work_root)):  # before any write there
        print(f"refused: {why}; nothing run", flush=True)
        raise SystemExit(handoff_seal.SEALED_CHECKOUT_REFUSED)
    keyfile = work_root / "typesafe.key"
    keyfile.unlink(missing_ok=True)  # one left by a crash is never reused
    if not dry:
        handoff_seal.require_sealed_checkout(*([] if lot == "f2" else [lot]))
        carry.refuse_unclean(out)
        carry.refuse_unclean(work_root)
        carry.record_claude(out, False, True)
        if (night or out).joinpath("LIMIT.flag").exists():
            raise SystemExit("LIMIT.flag: a usage limit paused the night")
        if complete(out, run):
            return ""
    plan = build_plan(run)
    try:
        if not dry:
            keyfile = carry.keyfile_from_harness_env(work_root)
            if "jev_cap" in RUNS[run]:
                (work_root / CAP_FILE).write_text(json.dumps({"cap_usd": RUNS[run]["jev_cap"]}),
                                                  encoding="utf-8")  # fmt: skip
            book(out, "preflight", carry.jev_first(out, plan, keyfile), "jev-preflight")
        return run_plan(out, run, keyfile, dry, cap, night, work_root=work_root)
    finally:
        keyfile.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    carry.ignore_interrupts()
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=sorted(RUNS))
    parser.add_argument("--out")
    parser.add_argument("--cap", type=float)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--seal", action="store_true")
    parser.add_argument("--lot", choices=sorted(LOTS), default="f2")
    args = parser.parse_args(argv)
    if args.seal:
        results, fixed = handoff_seal.LOTS[args.lot]
        print(seal(handoff_seal.REPO, results, fixed))
        return 0
    if args.preflight:
        import handoff_preflight

        root = Path(args.out) if args.out else Path(LOTS[args.lot]["out"])
        return handoff_preflight.main(root, args.lot)
    if not args.run:
        parser.error("--run, --preflight or --seal")
    out = Path(args.out) if args.out else Path(LOTS[lot_of(args.run)]["out"]) / args.run
    cap = min(args.cap if args.cap is not None else RUNS[args.run]["cap"], RUNS[args.run]["cap"])
    return EXIT[execute(args.run, out, cap, args.dry)]


if __name__ == "__main__":
    raise SystemExit(main())
