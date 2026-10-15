"""Phase S of lot lb162 (docs/results/2026-10-15-lb162/prereg.md): Sonnet 5.5 in clean Claude
Code (arm N, `SONNET-CC`) on the LongBench v2 tasks Jev 1.14 covered at 0.6 in phase J
(benchmarks/jev114/lb162.py). A thin runner over h2h_longdoc.py: the same session (clean user,
the document as `document.txt`, LongBench v2's official 0-shot template, the web taken away,
the local hook), the same per-session cap and the official `extract_answer` grade; only the
tasks, the phase, its private session folder and its money and clock rules are its own.

    python benchmarks/h2h/h2h_lb162.py --plan        # free: sessions, bands, cost, wall time
    python benchmarks/h2h/h2h_lb162.py --preflight   # free: cache, pinned claude, hooks, arm
    powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb162.py -RunnerArgs "--phase lb162" `
        -Pin $env:USERPROFILE\\.cache\\sanchopanza\\claude-pin\\2.1.287 `
        -Log C:\\sp-runs\\lb162\\sonnet.log -PidFile C:\\sp-runs\\lb162\\sonnet.pids   # PAID
    python benchmarks/h2h/h2h_lb162.py               # free: rows without text into the results

A live run refuses: without lot lb162's seal; before phase J is over; a covered-ids file that
is not the one derived from phase J's rows; a plan whose expected cost (SONNET_EST_USD a
session) does not fit under the ceiling with room for one session's cap and one worst turn;
a start before 08:00 or one whose expected wall time crosses midnight. While it runs, it stops
before a session within MIDNIGHT_MARGIN_S of midnight, when RUN_DIR holds a STOP file, at the
ceiling (spent + the session cap + one worst turn > 18 USD, browse/phase.py) and on a 429 or
usage limit (the session recorded as not run, LIMIT.flag written in RUN_DIR: a pause, not a
result).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
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
RUN_DIR = lb162.RUN_DIR
PIN_DEFAULT = pathlib.Path.home() / ".cache" / "sanchopanza" / "claude-pin" / "2.1.287"
PIN_DIR = pathlib.Path(os.environ.get("SANCHOPANZA_PIN_DIR") or PIN_DEFAULT)
EARLIEST_HOUR = 8  # Windows Update restarts between 02:00 and 08:00
MIDNIGHT_MARGIN_S = 600  # no session starts this close to midnight (the longest took 468 s)
WALL_FACTOR = 1.5  # the start's midnight check takes the mean session time times this
ROW_KEYS = ("letter", "ok", "usd", "wall_s", "turns", "hit_cap", "no_letter")
# What the phase loop reserves before each session (browse/phase.py stops when spent + this >
# the ceiling): the session's --max-budget-usd (h2h_longdoc's cap, unchanged) plus one worst turn
# past it, so the phase never spends more than CEILING_USD.
RESERVE = {MODEL: lb162.SONNET_CAP_USD + lb162.WORST_TURN_USD}


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


def fit_refusal(spent: float, todo: int) -> str:
    """Empty when `todo` sessions at SONNET_EST_USD fit under the ceiling after `spent`, with room
    for one session's cap and one worst turn past it."""
    need = spent + todo * lb162.SONNET_EST_USD + lb162.SONNET_CAP_USD + lb162.WORST_TURN_USD
    if round(need, 6) <= CEILING_USD:
        return ""
    return (f"phase S does not fit: {spent:.2f} spent + {todo} x {lb162.SONNET_EST_USD} + cap "
            f"{lb162.SONNET_CAP_USD} + worst turn {lb162.WORST_TURN_USD} = {need:.2f} > "
            f"{CEILING_USD:g} USD")  # fmt: skip


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
    """A stop before a session (midnight or the STOP file): the loop ends as at its ceiling."""


def guarded(session: Callable, clock: Callable[[], dt.datetime] = dt.datetime.now,
            run_dir: pathlib.Path = RUN_DIR) -> Callable:  # fmt: skip
    def one(item: tuple, run: int, arm: str) -> dict[str, Any]:
        now = clock()
        if crosses_midnight(now, MIDNIGHT_MARGIN_S):
            raise ClockStop(f"STOP midnight: {now:%H:%M}, resume after 08:00")
        if (run_dir / "STOP").exists():
            raise ClockStop(f"STOP file in {run_dir}")
        return session(item, run, arm)

    return one


def steps(tasks: Sequence[Any]) -> list[tuple]:
    return ld.planned(tasks, [MODEL], [BRAZO])


# --- rows without text --------------------------------------------------------------------------


def public_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Counted sessions of the arm: the id, the extracted letter, the grade, cost and time."""
    out = []
    for r in phase.counted(list(rows)):
        if r.get("arm") != ARM:
            continue
        out.append({"id": r["task_id"], "letter": r.get("final_answer"),
                    "ok": bool(r.get("ok_oficial")), "usd": round(float(r["list_usd"]), 6),
                    "wall_s": r.get("wall_s"), "turns": r.get("turns"),
                    "hit_cap": bool(r.get("hit_cap")),
                    "no_letter": r.get("final_answer") is None})  # fmt: skip
    return out


def export(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    mine = public_rows(rows)
    lb162.write_jsonl(lb162.SONNET_ROWS, mine)
    return {"sessions": len(mine), "right": sum(r["ok"] for r in mine),
            "list_usd": round(sum(r["usd"] for r in mine), 4)}  # fmt: skip


# --- plan, preflight, live ----------------------------------------------------------------------


def spent_now() -> tuple[float, int]:
    rows = gaia.read_rows(SESSIONS)
    done = [r for r in rows if r.get("arm") == ARM and not r.get("not_run") and r["run"] > 0]
    return sum(float(r["list_usd"]) for r in rows), len(done)


def plan_lines(tasks: Sequence[Any] | None) -> list[str]:
    if tasks is None:
        expected = lb162.plan(lb162.load_tasks(), None)["phase_s"]
        return [f"phase J not over: about {expected['sessions']} sessions expected, at most "
                f"{lb162.max_covered()} fit; est {expected['est_usd']} USD"]  # fmt: skip
    spent, done = spent_now()
    todo = len(tasks) - done
    bands = lb162.plan(tasks, [t.task_id for t in tasks])
    return [
        *(f"{i} {item[0]} {arm} {run} {ld.CAPS[MODEL]}" for i, item, run, arm in steps(tasks)),
        f"{len(tasks)} sessions ({done} done, {todo} to run); by length {bands['by_length']}; "
        f"by difficulty {bands['by_difficulty']}",
        f"cost: est {todo * lb162.SONNET_EST_USD:.2f} USD to run, {spent:.2f} spent; ceiling "
        f"{CEILING_USD:g}; " + (fit_refusal(spent, todo) or "fits"),
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
    if why := fit_refusal(spent, todo) or clock_refusal(dt.datetime.now(), todo):
        raise SystemExit(why)
    if (RUN_DIR / "LIMIT.flag").exists():
        raise SystemExit(f"{RUN_DIR / 'LIMIT.flag'} exists: the last run met a usage limit")
    SESSIONS.parent.mkdir(parents=True, exist_ok=True)
    code, rows = common.run_live(live_args(), steps(tasks), gaia.read_rows(SESSIONS),
                                 lambda ctx: guarded(ld.session_for(SESSIONS, ctx)), SESSIONS,
                                 RESERVE, {PHASE: CEILING_USD}, problems())  # fmt: skip
    if code == 2:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "LIMIT.flag").write_text(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} 429\n",
                                            encoding="utf-8")  # fmt: skip
    print(json.dumps(export(rows)), file=sys.stderr)
    return code


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
