"""Browse, development: the `sources` hook, version 2, on twenty harder FRAMES tasks (pilot 2).

python benchmarks/browse/free_frames2.py --plan          # free: ids and arms in run order
python benchmarks/browse/free_frames2.py --preflight     # free: version, both hooks, settings
python benchmarks/browse/free_frames2.py --smoke         # the first task, both -SRC2 arms
python benchmarks/browse/free_frames2.py --live          # the pilot, under its ceiling
python benchmarks/browse/free_frames2.py                 # free: the report so far

The first pilot (`free_frames.py`) found version 1 of the hook did not pay, on tasks the base
already got right in 16 of 20. This one runs version 2 (`sources_v2`: subagents counted, no block
past 60 % of the cap, a block only on a sign of a weak answer, a request that keeps the answer)
on tasks chosen to be harder by their metadata alone, never by any result: FRAMES test rows with
an answer of at most four words and either three or more reasoning types or four or more
Wikipedia links, none of the first pilot's twenty; seeded. Only ids reach the repository
(`frames2-ids.txt`); the rows, which keep the agents' answers, live beside the cached set.

Everything else is the first pilot's: `free_e2e.one_session`, WebFetch denied to the hosts that
serve the set, Claude Code pinned, the hook wired through each -SRC2 session's own `--settings`
(never `~/.claude/settings.json`), the caps (Sonnet 1.50, Sonnet+v2 1.05, Haiku 0.60, Haiku+v2
0.42), interleaved by task. A -SRC2 session also gets `SANCHOPANZA_SOURCES_VERSION=2` and its cap
as `SANCHOPANZA_SOURCES_CAP_USD`. What the hook saw at each stop (web calls, estimated spend,
signs, over the cap or not) is kept in the row from its `checked-*.json`. The ceiling, 32 USD,
counts the smoke too. A 429 or "weekly limit" stops the phase at once.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import random
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


frames = _load("browse_free_frames", HERE / "free_frames.py")
free, phase, calib = frames.free, frames.phase, frames.calib

IDS = frames.RESULTS / "frames2-ids.txt"
REPORT = frames.RESULTS / "frames2.json"
PRIVATE = free.CACHE / "frames-pilot2"  # the rows keep the agents' answers: not in the repo
SESSIONS = PRIVATE / "sessions.jsonl"
SMOKE = PRIVATE / "smoke-sessions.jsonl"
SEED = 20261006
N_TASKS = 20
CEILING_USD = 32.0
SMOKE_CEILING_USD = 3.0
CAPS = {"SONNET": 1.50, "SONNET-SRC2": 1.05, "HAIKU": 0.60, "HAIKU-SRC2": 0.42}
ARMS = tuple(CAPS)
RESERVE_USD = max(CAPS.values())
MIN_TYPES = 3
MIN_LINKS = 4
WEAK_REPLY = "It is likely Lyon, though the sources are unclear.\nANSWER: Lyon"
CLEAN_REPLY = "Found it.\nANSWER: Lyon"


# --- tasks --------------------------------------------------------------------------------------


def eligible(row: Mapping[str, str]) -> bool:
    """Harder by metadata: a short answer and many reasoning types or many linked articles."""
    words = len(str(row.get("Answer") or "").split())
    many = len(frames.types_of(row)) >= MIN_TYPES or frames.links_of(row) >= MIN_LINKS
    return 0 < words <= 4 and many


def sample(
    rows: Sequence[Mapping[str, str]], taken: set[str], n: int = N_TASKS, seed: int = SEED
) -> list[str]:
    """n eligible ids not in `taken`, seeded, drawn from the pool in file order."""
    pool = [frames.tid_of(r) for r in rows if eligible(r) and frames.tid_of(r) not in taken]
    return random.Random(seed).sample(pool, n)


def chosen_ids(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if IDS.exists():
        return [x.strip() for x in IDS.read_text(encoding="utf-8").splitlines() if x.strip()]
    first = set(frames.IDS.read_text(encoding="utf-8").split())
    ids = sample(rows, first)
    IDS.write_text("\n".join(ids) + "\n", encoding="utf-8")
    return ids


def plan(items: Sequence[tuple]) -> list[tuple]:
    streams = [[(t, arm) for t in items] for arm in ARMS]
    return [(i, task, 1, arm) for i, (task, arm) in enumerate(calib.interleave(streams))]


# --- sessions -----------------------------------------------------------------------------------


def env_for(arm: str, sources_dir: pathlib.Path) -> dict[str, str]:
    env = {"SANCHOPANZA_SOURCES_DIR": str(sources_dir)}
    if frames.is_src(arm):
        env |= {"SANCHOPANZA_SOURCES_VERSION": "2", "SANCHOPANZA_SOURCES_CAP_USD": f"{CAPS[arm]:g}"}
    return env


def hook_seen(sources_dir: pathlib.Path) -> dict[str, Any] | None:
    """What the v2 hook saw at the session's last stop it checked, from its own folder."""
    found = sorted(sources_dir.glob("checked-*.json")) if sources_dir.is_dir() else []
    return json.loads(found[-1].read_text(encoding="utf-8")) if found else None


def session_for(log_to: pathlib.Path):
    def session(task: tuple, run: int, arm: str) -> dict[str, Any]:
        sources_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-frames2-{task[0].lower()}-"))
        row = free.one_session(
            task, run, arm, session_max_usd=CAPS[arm], deny=frames.DENY,
            hooks=frames.hooks_for(arm), env_extra=env_for(arm, sources_dir),
        )  # fmt: skip
        found = frames.inspect(row, task[3], CAPS[arm], sources_dir)
        out = {**row, **found, "success_reply": row["success"], "success": found["ok_auto"],
               "hook_seen": hook_seen(sources_dir)}  # fmt: skip
        if found["limit"] or phase.usage_limited(row):
            phase._log(log_to, f"STOP-LIMIT {task[0]} {arm}: 429 or weekly limit in the session")
            out = {**out, "answer": free.LIMIT_MARKER}
        return out

    return session


# --- checks -------------------------------------------------------------------------------------


def hook_v2_checks() -> dict[str, list[str]]:
    """The v2 hook as a -SRC2 session runs it: a weak reply blocked once, a clean one let go."""
    env = {"SANCHOPANZA_SOURCES_VERSION": "2", "SANCHOPANZA_SOURCES_CAP_USD": "1.05"}
    return {
        "weak": frames.hook_twice(env, WEAK_REPLY),
        "clean": frames.hook_twice(env, CLEAN_REPLY),
    }


def preflight() -> list[str]:
    problems = frames.preflight()
    try:
        outs = hook_v2_checks()
        weak_ok = json.loads(outs["weak"][0] or "{}").get("decision") == "block"
        if not weak_ok or outs["weak"][1] or any(outs["clean"]):
            problems.append(f"the v2 hook should block a weak reply once, not a clean one: {outs}")
    except (OSError, ValueError) as error:
        problems.append(f"the v2 hook did not run: {error.__class__.__name__}")
    return problems


def spent(path: pathlib.Path) -> float:
    return sum(float(r["list_usd"]) for r in free.nav.done_sessions(path))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--smoke", "--live"):
        mode.add_argument(flag, action="store_true")
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    rows_all = frames.read_frames()
    steps = plan(frames.tasks(rows_all, chosen_ids(rows_all)))
    if args.plan:
        for i, task, _run, arm in steps:
            print(i, task[0], arm, CAPS[arm])
        return 0
    if args.preflight or args.smoke or args.live:
        problems = preflight()
        if problems:
            print("preflight: " + "; ".join(problems), file=sys.stderr)
            return 3
        if args.preflight:
            print("preflight: ok", file=sys.stderr)
            return 0
    sessions = SMOKE if args.smoke else SESSIONS
    rows = free.nav.done_sessions(sessions)
    code = 0
    if args.smoke:
        first = steps[0][1]
        smoke = [(0, first, 1, "SONNET-SRC2"), (0, first, 1, "HAIKU-SRC2")]
        limits = phase.Limits(session_max_usd=RESERVE_USD, ceiling_usd=SMOKE_CEILING_USD)
        code, rows = phase.run_phase(smoke, rows, limits, session_for(sessions), sessions)
    elif args.live:
        ceiling = CEILING_USD - spent(SMOKE)  # one ceiling for the smoke and the pilot
        limits = phase.Limits(session_max_usd=RESERVE_USD, ceiling_usd=ceiling)
        code, rows = phase.run_phase(steps, rows, limits, session_for(sessions), sessions)
    counted = phase.counted(rows)
    if counted:
        result = frames.report(counted, ARMS)
        if not args.smoke:
            REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
