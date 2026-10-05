"""Browse, sealed confirmation of fetch v2 on free FRAMES tasks, Haiku and Sonnet (fetch1).

python benchmarks/browse/free_fetch_confirm.py --plan         # free: ids and arms in run order
python benchmarks/browse/free_fetch_confirm.py --preflight    # free: version, settings, seal
python benchmarks/browse/free_fetch_confirm.py --check-load   # free: the tool is not deferred
python benchmarks/browse/free_fetch_confirm.py --record-hash  # seal prereg-fetch1.md
python benchmarks/browse/free_fetch_confirm.py --live         # 240 sessions, under 55 USD
python benchmarks/browse/free_fetch_confirm.py                # free: the runner's report so far

The registration is `prereg-fetch1.md` in the results folder; `--live` refuses to spend while it
and `prereg-fetch1.sha256` disagree. The grades, the blind sheet and the verdicts are in
`free_fetch_confirm_hand.py`.

The fetch pilots' runner (`free_fetch2_pilot.session_for`: the question and the ANSWER line,
Claude Code 2.1.287 with its normal tools, Bash denied, WebFetch denied to the hosts that serve
the set) with four arms, interleaved by task: HAIKU and HAIKU-FETCH2 (cap 0.60 USD), SONNET and
SONNET-FETCH2 (cap 1.50). A -FETCH2 arm adds the `sanchopanza-fetch` server at version 2
(`SANCHOPANZA_FETCH_VERSION=2`, registered with `alwaysLoad`) and `fetch_hook` on `PreToolUse`
WebFetch, the hook `sanchopanza install --fetch` writes; no page budget
(`SANCHOPANZA_FETCH_MAX_PAGES` unset). Server and hook go through the session's own MCP config and
`--settings`, never `~/.claude/settings.json`.

Tasks: sixty FRAMES test rows chosen by metadata alone with the fetch pilots' filters (an answer
of at most four words, three or more Wikipedia links), none of any earlier pilot or smoke, seeded.
Only ids reach the repository (`fetch-confirm-ids.txt`). A hard ceiling of 55 USD in code; a 429
or "weekly limit" stops the run (`phase.run_phase`), and a resume runs only what is missing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p2 = _load("browse_free_fetch2_pilot", HERE / "free_fetch2_pilot.py")
pilot, frames, free, phase = p2.pilot, p2.frames, p2.free, p2.phase

PREREG = frames.RESULTS / "prereg-fetch1.md"
IDS = frames.RESULTS / "fetch-confirm-ids.txt"
REPORT = frames.RESULTS / "fetch-confirm.json"
PRIVATE = free.CACHE / "frames-fetch-confirm"  # the rows keep the agents' answers: not in the repo
SESSIONS = PRIVATE / "sessions.jsonl"
SEED = 20261012
N_TASKS = 60
PAIRS = (("HAIKU", "HAIKU-FETCH2"), ("SONNET", "SONNET-FETCH2"))
ARMS = tuple(arm for pair in PAIRS for arm in pair)
CAPS = {"HAIKU": 0.60, "HAIKU-FETCH2": 0.60, "SONNET": 1.50, "SONNET-FETCH2": 1.50}
CEILING_USD = 55.0  # about 38-45 USD expected (prereg-fetch1.md)
PRIOR_IDS = ("frames-ids.txt", "frames2-ids.txt", "fetch-pilot-ids.txt", "fetch2-pilot-ids.txt")
# Every private sessions file of the earlier FRAMES runs, smokes included: none may share a task.
PRIOR_SESSIONS = (
    "frames-pilot", "frames-pilot2", "frames-fetch-smoke", "frames-fetch-pilot",
    "frames-fetch2-pilot",
)  # fmt: skip


# --- tasks --------------------------------------------------------------------------------------


def taken_ids() -> set[str]:
    return {t for name in PRIOR_IDS for t in (frames.RESULTS / name).read_text().split()}


def private_session_ids() -> set[str] | None:
    """Task ids of every earlier FRAMES session file on this machine; None when none is here."""
    paths = [p for name in PRIOR_SESSIONS for p in (free.CACHE / name).glob("*sessions.jsonl")]
    if not paths:
        return None
    return {r["task"] for p in paths for r in free.nav.done_sessions(p)}


def chosen_ids(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if IDS.exists():
        return [x.strip() for x in IDS.read_text(encoding="utf-8").splitlines() if x.strip()]
    ids = pilot.sample(rows, taken_ids(), n=N_TASKS, seed=SEED)
    IDS.write_text("\n".join(ids) + "\n", encoding="utf-8")
    return ids


def plan(items: Sequence[tuple]) -> list[tuple]:
    """Every task in the four arms, interleaved by task (a ceiling stop cuts them alike)."""
    return pilot.plan(items, ARMS)


# --- sessions -----------------------------------------------------------------------------------


def is_fetch(arm: str) -> bool:
    return arm.endswith("-FETCH2")


def fetch_env(marks: pathlib.Path) -> dict[str, str]:
    return {
        "SANCHOPANZA_FETCH_DIR": str(marks),
        "SANCHOPANZA_FETCH_DENY_HOSTS": ",".join(frames.DENIED_HOSTS),
        "SANCHOPANZA_FETCH_VERSION": "2",
    }


def arm_options(arm: str, marks: pathlib.Path) -> dict[str, Any]:
    """Nothing beyond Claude Code for a base arm; for -FETCH2 the server at version 2 (loaded up
    front) and the WebFetch hook of `install --fetch`, no page budget."""
    if not is_fetch(arm):
        return {"hooks": None, "env_extra": None, "mcp_servers": None}
    return {"hooks": pilot.hooks(), "env_extra": fetch_env(marks),
            "mcp_servers": {pilot.SERVER: p2.server_entry()}}  # fmt: skip


def session_for(log_to: pathlib.Path):
    return p2.session_for(log_to, caps=CAPS, options=arm_options)


# --- registration and free checks ---------------------------------------------------------------


def digest(path: pathlib.Path | None = None) -> str:
    return free.nav.base.digest(path or PREREG)


def registered() -> bool:
    sealed = PREREG.with_suffix(".sha256")
    return sealed.exists() and PREREG.exists() and sealed.read_text().strip() == digest()


def preflight(env: Mapping[str, str] | None = None) -> list[str]:
    """The fetch pilots' checks (pinned Claude Code, the set on disk, no sanchopanza hook in the
    global settings, claude on PATH), plus: no fetch setting in the run's own environment (the
    page budget must stay off), sixty new tasks, and the registration as sealed."""
    env = os.environ if env is None else env
    problems = list(pilot.preflight())
    stray = sorted(k for k in env if k.startswith("SANCHOPANZA_FETCH"))
    if stray:
        problems.append(f"fetch settings in the run's environment: {', '.join(stray)}")
    if IDS.exists():
        ids = IDS.read_text(encoding="utf-8").split()
        earlier = taken_ids() | (private_session_ids() or set())
        if len(ids) != N_TASKS or len(set(ids)) != N_TASKS or set(ids) & earlier:
            problems.append("the task ids are not sixty new tasks")
    else:
        problems.append(f"no {IDS.name}: run --plan first")
    if not registered():
        problems.append(f"{PREREG.name} is not registered as it stands")
    return problems


def check_load() -> dict[str, Any]:
    """Free, both -FETCH2 arms: the first request offers fetch_passages with its schema, not
    behind ToolSearch, on this run's options."""
    out = {}
    for arm in ("HAIKU-FETCH2", "SONNET-FETCH2"):
        marks = pathlib.Path(tempfile.mkdtemp(prefix="sp-fetchc-check-"))
        out[arm] = p2.check_load(arm, arm_options(arm, marks))
    return out


# --- report (the runner's provisional grades; the real ones are blind, by hand) -----------------


def report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "sessions": len(rows),
        "list_usd": round(sum(r["list_usd"] for r in rows), 2),
        "grades": "ok_auto (provisional)",
        "by_arm": {},
    }
    for arm in ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        if mine:
            out["by_arm"][arm] = pilot.cell(mine, "ok_auto")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--check-load", "--record-hash", "--live"):
        mode.add_argument(flag, action="store_true")
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if args.record_hash:
        PREREG.with_suffix(".sha256").write_text(digest() + "\n", encoding="utf-8")
        print(f"registered {PREREG.name}: {digest()}")
        return 0
    rows_all = frames.read_frames()
    items = frames.tasks(rows_all, chosen_ids(rows_all))
    if args.plan:
        for i, task, _run, arm in plan(items):
            print(i, task[0], arm, CAPS[arm])
        return 0
    if args.check_load:
        found = check_load()
        print(json.dumps(found, indent=1))
        return 0 if all(x["always_loaded"] for x in found.values()) else 1
    if args.preflight or args.live:
        problems = preflight()
        if problems:
            print("preflight: " + "; ".join(problems), file=sys.stderr)
            return 3
        if args.preflight:
            print("preflight: ok", file=sys.stderr)
            return 0
    code = 0
    rows = free.nav.done_sessions(SESSIONS)
    if args.live:
        limits = phase.Limits(session_max_usd=max(CAPS.values()), ceiling_usd=CEILING_USD)
        code, rows = phase.run_phase(plan(items), rows, limits, session_for(SESSIONS), SESSIONS)
    counted = phase.counted(rows)
    if counted:
        result = report(counted)
        REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
