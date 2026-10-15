"""Phase S of lot lb162 (docs/results/2026-10-15-lb162/prereg.md): Sonnet 5.5 in clean Claude
Code (arm N, `SONNET-CC`) on the LongBench v2 tasks Jev 1.14 covered at 0.6 in phase J
(benchmarks/jev114/lb162.py). A thin runner over h2h_longdoc.py: the same session (clean user,
the document as `document.txt`, LongBench v2's official 0-shot template, the web taken away,
the local hook), the same per-session cap and the official `extract_answer` grade; only the
tasks, the phase, its private session folder and its money and clock rules are its own.

    python benchmarks/h2h/h2h_lb162.py --plan        # free: sessions, bands, cost, wall time
    python benchmarks/h2h/h2h_lb162.py --preflight   # free: cache, pinned claude, hooks, arm
    powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb162.py -RunnerArgs "--phase lb162" `
        -Pin $env:USERPROFILE\\.cache\\sanchopanza\\claude-pin\\2.1.287 -KeysEnv <keys .env path> `
        -Log C:\\sp-runs\\lb162\\sonnet.log -PidFile C:\\sp-runs\\lb162\\sonnet.pids   # PAID
    python benchmarks/h2h/h2h_lb162.py               # free: rows without text into the results

A live run refuses: without lot lb162's seal; before phase J is over; a covered-ids file that
is not the one derived from phase J's rows; a plan whose expected cost alone (SONNET_EST_USD a
session) exceeds the ceiling (a plan above what the ceiling holds starts, and the guard below
stops it, leaving a random subset of the covered tasks: they run in a seeded order); a start
before 08:00 or one whose expected wall time crosses midnight; a LIMIT.flag in RUN_DIR.

Before each session (`Guard`): a stop if it is before 08:00, past the phase's start date or
within MIDNIGHT_MARGIN_S of midnight (kind `clock`, exit 5), or RUN_DIR holds a STOP file
(`manual`, exit 6); then a reservation row (RESERVATIONS) so a session that dies mid-way still
counts its reserve against the ceiling on a resume. The loop (browse/phase.py) stops at the
ceiling: spent + the session cap + one worst turn > 18 USD (`ceiling`, exit 1). A 429 or usage
limit records the session as not run and writes LIMIT.flag (`limit`, exit 2: a pause, not a
result). The stop's kind goes to the results folder (sonnet-stop.json), the kind only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))
import h2h_longdoc as ld  # noqa: E402
import lb162  # noqa: E402

common, gaia, phase = ld.common, ld.gaia, ld.phase

PHASE = "lb162"
MODEL, BRAZO = "SONNET", "CC"
ARM = f"{MODEL}-{BRAZO}"
CEILING_USD = lb162.SONNET_CEILING_USD
SESSIONS = ld.PRIVATE / PHASE / "sessions.jsonl"
RESERVATIONS = SESSIONS.with_name("reservations.jsonl")
RUN_DIR = lb162.RUN_DIR
PIN_DEFAULT = pathlib.Path.home() / ".cache" / "sanchopanza" / "claude-pin" / "2.1.287"
PIN_DIR = pathlib.Path(os.environ.get("SANCHOPANZA_PIN_DIR") or PIN_DEFAULT)
EARLIEST_HOUR = 8  # Windows Update restarts between 02:00 and 08:00
MIDNIGHT_MARGIN_S = 600  # no session starts this close to midnight (the longest took 468 s)
WALL_FACTOR = 1.5  # the start's midnight check takes the mean session time times this
ROW_KEYS = ("letter", "ok", "usd", "wall_s", "turns", "hit_cap", "no_letter", "is_error",
            "subtype")  # fmt: skip
# What the phase loop reserves before each session (browse/phase.py stops when spent + this >
# the ceiling): the session's --max-budget-usd (h2h_longdoc's cap, unchanged) plus one worst turn
# past it, so the phase never spends more than CEILING_USD.
RESERVE = {MODEL: lb162.SONNET_RESERVE_USD}
EXIT = {"done": 0, "ceiling": 1, "limit": 2, "preflight": 3, "jev": 4, "clock": 5, "manual": 6}


# --- the tasks and their rules ------------------------------------------------------------------


def covered_tasks() -> list[Any]:
    """Phase J's covered tasks in the covered-ids file's order, checked against the rows."""
    rows = lb162.read_jsonl(lb162.JEV_ROWS)
    stop = lb162.read_jsonl(lb162.STOP_FILE)
    if why := lb162.phase_j_final(rows, stop[0] if stop else None):
        raise SystemExit(f"phase S refused: {why}")
    ids = gaia.read_ids(lb162.COVERED_FILE)
    if ids != lb162.covered(rows):
        raise SystemExit("phase S refused: covered-ids.txt is not the derivation of phase J")
    by_id = {t.task_id: t for t in lb162.load_tasks()}
    return [by_id[i] for i in ids]


def expected_refusal(todo: int) -> str:
    """Empty unless the expected cost of the sessions left (SONNET_EST_USD each) alone exceeds
    the ceiling. A plan above what the ceiling can hold still starts: the guard before each
    session stops it, and the seeded order leaves a random subset of the covered tasks."""
    need = todo * lb162.SONNET_EST_USD
    if round(need, 6) <= CEILING_USD:
        return ""
    return (f"phase S refused: {todo} sessions x {lb162.SONNET_EST_USD} = {need:.2f} USD expected "
            f"> the {CEILING_USD:g} USD ceiling")  # fmt: skip


def crosses_midnight(start: dt.datetime, seconds: float) -> bool:
    return (start + dt.timedelta(seconds=seconds)).date() != start.date()


def clock_refusal(now: dt.datetime, todo: int) -> str:
    if now.hour < EARLIEST_HOUR:
        return f"phase S refused: {now:%H:%M} is before {EARLIEST_HOUR:02d}:00"
    seconds = todo * lb162.SONNET_WALL_MEAN_S * WALL_FACTOR + MIDNIGHT_MARGIN_S
    if crosses_midnight(now, seconds):
        return (f"phase S refused: {todo} sessions (~{seconds / 60:.0f} min with margin) started "
                f"at {now:%H:%M} would cross midnight")  # fmt: skip
    return ""


class ClockStop(common.JointCeiling):
    """A stop before a session (the clock or the STOP file): the loop ends as at its ceiling;
    `Guard.kind` tells it apart."""


class Guard:
    """Checks before each session, then its reservation row. `kind` names a stop it raised."""

    def __init__(self, start: dt.datetime, clock: Callable[[], dt.datetime] = dt.datetime.now,
                 run_dir: pathlib.Path = RUN_DIR,
                 reservations: pathlib.Path = RESERVATIONS) -> None:  # fmt: skip
        self.start, self.clock = start, clock
        self.run_dir, self.reservations = run_dir, reservations
        self.kind: str | None = None

    def refusal(self, now: dt.datetime) -> tuple[str, str] | None:
        if now.hour < EARLIEST_HOUR or now.date() != self.start.date():
            return "clock", f"STOP clock: {now:%Y-%m-%d %H:%M}, outside the phase's day after 08:00"
        if crosses_midnight(now, MIDNIGHT_MARGIN_S):
            return "clock", f"STOP midnight: {now:%H:%M}, resume after 08:00"
        if (self.run_dir / "STOP").exists():
            return "manual", "STOP file in the run folder"
        return None

    def wrap(self, session: Callable) -> Callable:
        def one(item: tuple, run: int, arm: str) -> dict[str, Any]:
            now = self.clock()
            if stop := self.refusal(now):
                self.kind = stop[0]
                raise ClockStop(stop[1])
            reserve(self.reservations, item[0], run, arm, now)
            return session(item, run, arm)

        return one


def reserve(path: pathlib.Path, task: str, run: int, arm: str, now: dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"task": task, "run": run, "arm": arm, "reserve_usd": lb162.SONNET_RESERVE_USD,
            "started": f"{now:%Y-%m-%dT%H:%M:%S}"}  # fmt: skip
    with path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(line) + "\n")


def open_reservations(rows: Sequence[Mapping[str, Any]],
                      path: pathlib.Path = RESERVATIONS) -> list[dict[str, Any]]:  # fmt: skip
    """A row at the reserve for every started session with no recorded row (one that died
    mid-way, or between its end and its record): not run, so it is asked again, but its
    reserve counts against the ceiling."""
    started = Counter((r["task"], r["run"], r["arm"]) for r in lb162.read_jsonl(path) or [])
    recorded = Counter((r["task"], r["run"], r["arm"]) for r in rows)
    return [{"task": t, "task_id": t, "run": run, "arm": arm, "not_run": True, "open": True,
             "list_usd": lb162.SONNET_RESERVE_USD}
            for (t, run, arm), n in started.items()
            for _ in range(n - recorded[(t, run, arm)])]  # fmt: skip


def steps(tasks: Sequence[Any]) -> list[tuple]:
    return ld.planned(tasks, [MODEL], [BRAZO])


# --- rows without text --------------------------------------------------------------------------


def public_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Counted sessions of the arm: the id, the extracted letter, the grade, cost, time and how
    the session ended (Claude Code's subtype, or the runner's on a wall-clock timeout)."""
    out = []
    for r in phase.counted(list(rows)):
        if r.get("arm") != ARM:
            continue
        out.append({"id": r["task_id"], "letter": r.get("final_answer"),
                    "ok": bool(r.get("ok_oficial")), "usd": round(float(r["list_usd"]), 6),
                    "wall_s": r.get("wall_s"), "turns": r.get("turns"),
                    "hit_cap": bool(r.get("hit_cap")),
                    "no_letter": r.get("final_answer") is None,
                    "is_error": not r.get("ok", False), "subtype": r.get("subtype")})  # fmt: skip
    return out


def export(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    mine = public_rows(rows)
    lb162.write_jsonl(lb162.SONNET_ROWS, mine)
    return {"sessions": len(mine), "right": sum(r["ok"] for r in mine),
            "list_usd": round(sum(r["usd"] for r in mine), 4)}  # fmt: skip


def stop_kind(code: int, guard: Guard) -> str:
    if code == 1 and guard.kind:
        return guard.kind
    return {v: k for k, v in EXIT.items() if k not in ("clock", "manual")}.get(code, "error")


# --- plan, preflight, live ----------------------------------------------------------------------


def known_rows() -> list[dict[str, Any]]:
    """The recorded sessions plus the open reservations (at the reserve, not run)."""
    rows = gaia.read_rows(SESSIONS)
    return [*rows, *open_reservations(rows)]


def spent_now() -> tuple[float, int]:
    rows = known_rows()
    done = [r for r in rows if r.get("arm") == ARM and not r.get("not_run") and r["run"] > 0]
    return sum(float(r["list_usd"]) for r in rows), len(done)


def plan_lines(tasks: Sequence[Any] | None) -> list[str]:
    if tasks is None:
        expected = lb162.plan(lb162.load_tasks(), None)["phase_s"]
        return [f"phase J not over: about {expected['sessions']} sessions expected, est "
                f"{expected['est_usd']} USD; reserve {expected['reserve_per_session_usd']} USD "
                f"a session; the guard stops after about "
                f"{expected['sessions_before_guard_at_mean']} at the mean cost, "
                f"{expected['sessions_guaranteed_at_worst']} at worst"]  # fmt: skip
    spent, done = spent_now()
    todo = len(tasks) - done
    bands = lb162.plan(tasks, [t.task_id for t in tasks])
    return [
        *(f"{i} {item[0]} {arm} {run} {ld.CAPS[MODEL]}" for i, item, run, arm in steps(tasks)),
        f"{len(tasks)} sessions ({done} done, {todo} to run); by length {bands['by_length']}; "
        f"by difficulty {bands['by_difficulty']}",
        f"cost: est {todo * lb162.SONNET_EST_USD:.2f} USD to run, {spent:.2f} spent; ceiling "
        f"{CEILING_USD:g}; " + (expected_refusal(todo) or "expected within the ceiling")
        + f"; reserve {lb162.SONNET_RESERVE_USD} a session; the guard stops after "
        f"~{lb162.sessions_before_guard(lb162.SONNET_EST_USD)} sessions at the mean cost, "
        f"{lb162.guaranteed_sessions()} at worst",
        f"wall: ~{todo * lb162.SONNET_WALL_MEAN_S / 60:.0f} min at the mean, "
        f"~{todo * lb162.SONNET_WALL_MEDIAN_S / 60:.0f} at the median; "
        + (clock_refusal(dt.datetime.now(), todo) or "the clock allows a start now"),
    ]  # fmt: skip


def pinned_first_on_path(pin_dir: pathlib.Path = PIN_DIR) -> list[str]:
    """What launch.ps1 does for its process: the pinned claude first on PATH."""
    if not (pin_dir / "claude.exe").is_file():
        return [f"no pinned claude.exe in {pin_dir}"]
    os.environ["PATH"] = f"{pin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    return []


def problems() -> list[str]:
    data = [*lb162.data_problems()]
    if not lb162.longdoc_data.RAW.exists():
        data.append(f"no LongBench cache at {lb162.longdoc_data.RAW}")
    if not data:
        data.extend(lb162.docs_problems())
    return common.preflight([BRAZO], ld.flag_settings(), data, None, PHASE)


def live_args() -> argparse.Namespace:
    return argparse.Namespace(phase=PHASE, ceiling=CEILING_USD, brazos=[BRAZO], models=[MODEL],
                              s_line=str(gaia.arms.s_line.S_INSTALL), unsealed_ok=False,
                              joint_with=[])  # fmt: skip


def live() -> int:  # pragma: no cover - paid sessions
    lb162.require_prereg()
    tasks = covered_tasks()
    spent, done = spent_now()
    todo = len(tasks) - done
    now = dt.datetime.now()
    if why := expected_refusal(todo) or clock_refusal(now, todo):
        raise SystemExit(why)
    if (RUN_DIR / "LIMIT.flag").exists():
        raise SystemExit("LIMIT.flag in the run folder: the last run met a usage limit")
    SESSIONS.parent.mkdir(parents=True, exist_ok=True)
    guard = Guard(now)
    code, rows = common.run_live(live_args(), steps(tasks), known_rows(),
                                 lambda ctx: guard.wrap(ld.session_for(SESSIONS, ctx)), SESSIONS,
                                 RESERVE, {PHASE: CEILING_USD}, problems())  # fmt: skip
    kind = stop_kind(code, guard)
    if kind == "limit":
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "LIMIT.flag").write_text(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} 429\n",
                                            encoding="utf-8")  # fmt: skip
    lb162.write_jsonl(lb162.SONNET_STOP, [{"kind": kind}])
    print(json.dumps(export(rows) | {"stop": kind}), file=sys.stderr)
    return EXIT.get(kind, 7)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--plan", "--preflight", "--live"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--phase", choices=[PHASE], default=PHASE)
    args = ap.parse_args(argv)
    if args.live:
        return live()
    if args.plan:
        try:
            tasks = covered_tasks()
        except SystemExit as why:
            print(why, file=sys.stderr)
            tasks = None
        print("\n".join(plan_lines(tasks)))
        return 0
    if args.preflight:
        found = [*pinned_first_on_path(), *problems()]
        print(f"lb162 seal: {lb162.seal_state()}", file=sys.stderr)
        print("preflight: " + ("; ".join(found) or "ok"), file=sys.stderr)
        return 3 if found else 0
    if not SESSIONS.exists():
        print(f"no sessions in {SESSIONS}: nothing to export", file=sys.stderr)
        return 0
    print(json.dumps(export(gaia.read_rows(SESSIONS))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
