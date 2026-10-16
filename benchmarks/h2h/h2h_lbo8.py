"""Lot lbo8 (docs/results/2026-10-16-lbo8/prereg.md): one driver for the smoke and both paid
phases, lb162x's exact sibling. In order: the smoke (ONE Opus 5.5 session on lb162x's smoke task,
a LongBench dev task outside the 78, 0.80 USD), phase J (Jev 1.14 on the 78 through lb162's
runner, recorded first, live on a miss, this lot's own ledger capped at 0.20 USD:
lbo8.run_phase_j), phase O (Opus 5.5 in clean Claude Code, arm N, on all 78 in the seeded order,
ceiling 30 USD). The session, its grade, the money rule and each session's health are
h2h_lb162x's and lb162x_guard's, reused as they are with this lot's phases and run folder.

    python benchmarks/h2h/h2h_lbo8.py --dry         # free: lbo8.py --dry plus what is spent
    python benchmarks/h2h/h2h_lbo8.py --preflight   # free: cache, pinned claude, launcher, ledger
    powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lbo8.py -RunnerArgs "--lot lbo8" `
        -Pin $env:USERPROFILE\\.cache\\sanchopanza\\claude-pin\\2.1.287 -KeysEnv <path> `
        -Log C:\\sp-runs\\lbo8\\driver.log -PidFile C:\\sp-runs\\lbo8\\driver.pids   # PAID
    python benchmarks/h2h/h2h_lbo8.py               # free: rows without text into the results

A live run refuses (exit 3) without the seal or outside a clean checkout detached at the sealed
commit or with another claude first on PATH; with a LIMIT.flag in the run folder (exit 2); and
when the next phase may not start by the clock (exit 5). A phase or the smoke that ended by
finishing (or a phase by its ceiling) is skipped on a relaunch; the first one that pauses stops
the lot. Exit codes (h2h_lb162x.EXIT): done 0, ceiling 1, limit 2, preflight 3, jev 4 (phase J
paused: 402, Jev's 429, an outage, three failed tasks in a row), clock 5, manual 6, error 7,
outage 8, smoke 9. The run folder (STOP, LIMIT.flag, phase J's ledger) is lbo8.RUN_DIR,
C:/sp-runs/lbo8, or --run-dir.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from collections.abc import Callable, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))
import h2h_lb162x as x  # noqa: E402  (lb162x's driver: session, rows, smoke, drive, exit codes)
import lb162x_guard as guard_mod  # noqa: E402
import lbo8  # noqa: E402

ld, s162, common, gaia = x.ld, x.s162, x.common, x.gaia

LOT = "lbo8"
BRAZO = x.BRAZO
EXIT = x.EXIT
SMOKE, PHASE_J, PHASE_O = lbo8.SMOKE, lbo8.PHASE_J, lbo8.PHASE_O
DRIVEN = lbo8.DRIVEN
CLAUDE_PHASES = (SMOKE, PHASE_O)
LAUNCHER = HERE / "launch.ps1"
# Other lots' run folders: phase J's ledger (and STOP, LIMIT.flag) must never be one of theirs.
OTHER_RUN_DIRS = (pathlib.Path("C:/sp-runs/w17-jev"), lbo8.lb162.RUN_DIR, lbo8.lb162x.RUN_DIR)

sessions_of, reservations_of, done_now = x.sessions_of, x.reservations_of, x.done_now
final_kind, exit_code, export = x.final_kind, x.exit_code, x.export


def smoke_task() -> Any:
    """lb162x's smoke task, refused if it is one of the 78."""
    task = x.smoke_task()
    if task.task_id in set(lbo8.read_ids(lbo8.IDS_FILE)):
        raise SystemExit("the smoke task is one of the 78")
    return task


def tasks_of(phase: Any) -> list[Any]:
    """The smoke's one task, or phase O's 78 in the seeded order."""
    if phase.key == SMOKE.key:
        return [smoke_task()]
    by_id = {t.task_id: t for t in lbo8.load_tasks()}
    return [by_id[i] for i in lbo8.opus_order()]


def steps(phase: Any, tasks: Sequence[Any]) -> list[tuple]:
    return ld.planned(tasks, [phase.model], [BRAZO])


def clock_refusal(phase: Any, now: dt.datetime, todo: int) -> str:
    """lb162x's rule (no start before 08:00, none whose sessions would cross midnight); phase J
    takes its own allowance (lbo8.J_WALL_S)."""
    if phase.key != PHASE_J.key:
        return x.clock_refusal(phase, now, todo)
    if now.hour < s162.EARLIEST_HOUR:
        return f"phase J refused: {now:%H:%M} is before {s162.EARLIEST_HOUR:02d}:00"
    if s162.crosses_midnight(now, lbo8.J_WALL_S + s162.MIDNIGHT_MARGIN_S):
        return f"phase J refused: started at {now:%H:%M} it could cross midnight"
    return ""


def ledger_problems(run_dir: pathlib.Path) -> list[str]:
    """Phase J's ledger is this lot's own: its run folder is no other lot's."""
    mine = run_dir.resolve()
    return [f"the run folder {run_dir} is another lot's (phase J's ledger must be lbo8's own)"
            for other in OTHER_RUN_DIRS if mine == other.resolve()]  # fmt: skip


def launcher_problems(path: pathlib.Path = LAUNCHER) -> list[str]:
    """launch.ps1's -Runner list must take this runner."""
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return [] if "'h2h_lbo8.py'" in text else [f"{path.name} does not accept -Runner h2h_lbo8.py"]


def model_problems(pin_dir: pathlib.Path = s162.PIN_DIR) -> list[str]:
    """Free: Opus 5.5's id in the pinned Claude Code build."""
    found = gaia.model_ids_in(pin_dir / "claude.exe", [PHASE_O.model_id])
    return [f"{m} not in the pinned claude.exe" for m, ok in found.items() if not ok]


def data_problems() -> list[str]:
    try:
        tasks = lbo8.load_tasks()
    except (SystemExit, FileNotFoundError) as error:
        return [f"lbo8 data: {error}"]
    missing = [t.task_id for t in tasks if not pathlib.Path(t.doc_path).is_file()]
    return [f"lbo8 data: {len(missing)} documents missing: lbo8.py --prepare"] if missing else []


def problems(run_dir: pathlib.Path) -> list[str]:
    data = [*data_problems(), *ledger_problems(run_dir)]
    if not lbo8.longdoc_data.RAW.exists():
        data.append(f"no LongBench cache at {lbo8.longdoc_data.RAW}")
    if not data:
        data.extend(lbo8.docs_problems())
    return common.preflight([BRAZO], ld.flag_settings(), data, None, LOT)


# --- the phases ---------------------------------------------------------------------------------


def run_claude(phase: Any, found: Sequence[str], run_dir: pathlib.Path) -> str:  # pragma: no cover
    """The smoke or phase O through the phase loop (h2h_lb162x.run_phase with this lot's tasks
    and run folder); its stop kind and rows."""
    tasks = tasks_of(phase)
    now = dt.datetime.now()
    if why := clock_refusal(phase, now, len(tasks) - done_now(phase)):
        print(why, file=sys.stderr)
        return "clock"
    sessions, reservations = sessions_of(phase), reservations_of(phase)
    sessions.parent.mkdir(parents=True, exist_ok=True)
    smoke = phase.key == SMOKE.key
    guard = guard_mod.Budget(phase, now, sessions, reservations,
                             cap_rule=x.smoke_cap if smoke else None, run_dir=run_dir)  # fmt: skip
    reserve = SMOKE.full_cap if smoke else phase.loop_reserve
    code, rows = common.run_live(x.live_args(phase), steps(phase, tasks),
                                 guard_mod.known_rows(sessions, reservations),
                                 lambda ctx: guard.wrap(x.session_for(phase, ctx)), sessions,
                                 {phase.model: reserve}, {phase.name: phase.ceiling},
                                 found)  # fmt: skip
    kind = s162.stop_kind(code, guard)
    said = export(phase, rows)
    if smoke:
        kind = x.settle_smoke(kind, sessions)
    print(json.dumps({"phase": phase.key, **said, "stop": kind}), file=sys.stderr)
    return kind


def run_jev(found: Sequence[str], run_dir: pathlib.Path,
            now: Callable[[], dt.datetime] = dt.datetime.now,
            run: Callable[[pathlib.Path], str] = lbo8.run_phase_j) -> str:  # fmt: skip
    """Phase J: refused with any preflight problem (SystemExit, kind `preflight`), stopped by
    the clock or a STOP file, else lbo8.run_phase_j."""
    if found:
        raise SystemExit("preflight: " + "; ".join(found))
    if why := clock_refusal(PHASE_J, now(), PHASE_J.n):
        print(why, file=sys.stderr)
        return "clock"
    if (run_dir / "STOP").exists():
        return "manual"
    return run(run_dir)


def run_any(phase: Any, found: Sequence[str], run_dir: pathlib.Path) -> str:  # pragma: no cover
    if phase.key == PHASE_J.key:
        return run_jev(found, run_dir)
    return run_claude(phase, found, run_dir)


def refusal(now: dt.datetime, run_dir: pathlib.Path = lbo8.RUN_DIR,
            git: Any = None) -> tuple[str, str] | None:  # fmt: skip
    """Before any session or call: (kind, why) when the lot may not start, else None."""
    try:
        value = lbo8.require_prereg()
        if found := [*lbo8.checkout_problems(value, git), *x.pin_problems(),
                     *ledger_problems(run_dir)]:  # fmt: skip
            return "preflight", "; ".join(found)
    except SystemExit as why:
        return "preflight", str(why)
    if (run_dir / "LIMIT.flag").exists():
        return "limit", "LIMIT.flag in the run folder: the last run met a usage limit"
    first = next((p for p in DRIVEN if not final_kind(p)), None)
    if first is None:
        return "done", "every phase is over: nothing to run"
    # The smoke is one session and phase J a few minutes: the clock is phase O's, from now.
    if why := clock_refusal(PHASE_O, now, PHASE_O.n - done_now(PHASE_O)):
        return "clock", why
    return None


def live(run_dir: pathlib.Path, now: dt.datetime | None = None) -> int:  # pragma: no cover - paid
    if stop := refusal(now or dt.datetime.now(), run_dir):
        print(stop[1], file=sys.stderr)
        return exit_code(stop[0])
    found = [*model_problems(), *problems(run_dir), *launcher_problems()]
    kind, kinds = x.drive(DRIVEN, lambda p: x.guarded_run(
        p, found, lambda ph, f: run_any(ph, f, run_dir), run_dir), final_kind)  # fmt: skip
    print(json.dumps({"lot": kind, "phases": kinds}), file=sys.stderr)
    return exit_code(kind)


def retry_smoke(now: dt.datetime | None = None) -> list[str]:
    """`--retry-smoke`: a smoke that failed after spending is moved aside (never deleted), so
    the next launch runs it again under a new 0.80 USD ceiling. Refused when it passed."""
    if final_kind(SMOKE) == "done":
        raise SystemExit("the smoke passed: nothing to retry")
    stamp = f"{now or dt.datetime.now():%Y%m%dT%H%M%S}"
    moved = []
    for path in (sessions_of(SMOKE), reservations_of(SMOKE)):
        if path.exists():
            aside = path.with_name(f"{path.stem}.failed-{stamp}{path.suffix}")
            path.rename(aside)
            moved.append(aside.name)
    return moved


# --- free modes ---------------------------------------------------------------------------------


def plan_lines(run_dir: pathlib.Path, now: dt.datetime) -> list[str]:
    """What the lot would run, spend and take, and what is spent so far."""
    o = PHASE_O
    latest = dt.datetime.combine(now.date(), dt.time(23, 59, 59)) - dt.timedelta(
        seconds=o.n * o.wall_mean_s * s162.WALL_FACTOR + s162.MIDNIGHT_MARGIN_S
    )
    lines = [
        f"order: {' -> '.join(p.key for p in DRIVEN)} (smoke, phase J, phase O); "
        f"{1 + o.n} Opus sessions and {lbo8.N_TASKS} Jev tasks; lot ceiling "
        f"{lbo8.LOT_CEILING_USD:.2f} USD (smoke {SMOKE.ceiling:g} + J {lbo8.JEV_CAP_USD:g} + "
        f"O {o.ceiling:g}); expected ~{lbo8.N_TASKS * lbo8.OPUS_EST_USD + 0.2 + 0.07:.1f} USD",
        f"phase O order (seed {lbo8.ORDER_SEED}): first {lbo8.opus_order()[:3]}",
        f"wall: phase O ~{o.n * o.wall_mean_s / 60:.0f} min at {o.wall_mean_s:g} s a session, "
        f"clock allowance {o.n * o.wall_mean_s * s162.WALL_FACTOR / 60 + 10:.0f} min: start "
        f"after 08:00 and by {latest:%H:%M}; phase J allowance {lbo8.J_WALL_S / 60:.0f} min",
        f"run folder {run_dir}; phase J ledger {lbo8.jev_ledger(run_dir)} batch {lbo8.BATCH}: "
        f"{lbo8.batch_spent(run_dir):.4f} USD spent of {lbo8.JEV_CAP_USD:g}",
    ]
    for p in CLAUDE_PHASES:
        spent = guard_mod.spent_now(sessions_of(p), reservations_of(p))
        lines.append(
            f"phase {p.key} ({p.name}): spent so far {spent:.2f} USD, "
            f"{done_now(p)} sessions done, stop {(lbo8.stop_of(p) or {}).get('kind')}"
        )
    lines.append(f"phase J: stop {(lbo8.stop_of(PHASE_J) or {}).get('kind')}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--dry", "--plan", "--preflight", "--live", "--retry-smoke"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--lot", choices=[LOT], default=LOT)
    ap.add_argument("--run-dir", type=pathlib.Path, default=lbo8.RUN_DIR)
    args = ap.parse_args(argv)
    if args.live:
        return live(args.run_dir)
    if args.retry_smoke:
        print(f"smoke moved aside: {retry_smoke() or 'nothing to move'}; the next launch runs it")
        return 0
    if args.dry or args.plan:
        print("\n".join(lbo8.dry(with_power=False)))
        task = smoke_task()
        print(f"smoke: {task.task_id} ({task.length}, {task.chars:,d} characters), cap and "
              f"ceiling {SMOKE.full_cap:g} USD, one session")  # fmt: skip
        print("\n".join(plan_lines(args.run_dir, dt.datetime.now())))
        print(f"seal: {lbo8.seal_state()}")
        return 0
    if args.preflight:
        found = [*s162.pinned_first_on_path(), *model_problems(), *problems(args.run_dir),
                 *launcher_problems()]  # fmt: skip
        smoke_task()
        todo = lbo8.unrecorded(lbo8.load_tasks())
        if why := lbo8.jev_plan_refusal(lbo8.batch_spent(args.run_dir), todo):
            found.append(why)
        print(f"phase J: {len(todo)} of {lbo8.N_TASKS} tasks unrecorded (asked live); ledger "
              f"{lbo8.jev_ledger(args.run_dir)}", file=sys.stderr)  # fmt: skip
        print(f"lbo8 seal: {lbo8.seal_state()}", file=sys.stderr)
        print("preflight: " + ("; ".join(found) or "ok"), file=sys.stderr)
        return 3 if found else 0
    for p in CLAUDE_PHASES:
        if sessions_of(p).exists():
            print(json.dumps({"phase": p.key, **export(p, gaia.read_rows(sessions_of(p)))}))
        else:
            print(f"no sessions in {sessions_of(p)}: nothing to export", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
