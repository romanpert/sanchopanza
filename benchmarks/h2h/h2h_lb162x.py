"""Lot lb162x (docs/results/2026-10-16-lb162x/prereg.md): one driver for the smoke and both paid
phases, the expensive model in clean Claude Code (arm N) where lot lb162 did not run it, Jev's
lb162 answers reused as recorded (no Jev call). In order: the smoke (ONE Opus session on a dev
task outside the 162, 0.80 USD), phase B (Opus 5.5 on all 162 tasks: the primary verdict), phase
A (Sonnet 5.5 on the 102 uncovered). A thin runner over h2h_longdoc.py and h2h_lb162.py: the same
session (Claude Code 2.1.287 pinned, a clean user and CLAUDE_CONFIG_DIR per session, the
document as `document.txt`, LongBench v2's official 0-shot template, the web taken away, the
local hook), the official `extract_answer` grade, and lb162's clock and STOP rules. The money
and each session's health: lb162x_guard.py.

    python benchmarks/h2h/h2h_lb162x.py --dry         # free: lb162x.py --dry plus what is spent
    python benchmarks/h2h/h2h_lb162x.py --preflight   # free: cache, recordings, pinned claude
    powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb162x.py -RunnerArgs "--lot lb162x" `
        -Pin $env:USERPROFILE\\.cache\\sanchopanza\\claude-pin\\2.1.287 -KeysEnv <path> `
        -Log C:\\sp-runs\\lb162x\\driver.log -PidFile C:\\sp-runs\\lb162x\\driver.pids   # PAID
    python benchmarks/h2h/h2h_lb162x.py               # free: rows without text into the results

A live run refuses (exit 3) without the seal, outside a clean checkout detached at the sealed
commit, with lb162's recordings changed or a frozen order that is not their derivation; with a
LIMIT.flag in RUN_DIR (exit 2); and when the next phase may not start by the clock (exit 5). A
phase or the smoke that ended by finishing (or a phase by its ceiling) is skipped on a relaunch;
the first one that pauses stops the lot. Exit codes (EXIT): done 0, ceiling 1 (every phase over,
one at its ceiling), limit 2, preflight 3, jev 4, clock 5, manual 6, error 7, outage 8, smoke 9.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))
import h2h_lb162 as s162  # noqa: E402  (lb162's phase S: the guard, row keys and exit codes)
import h2h_longdoc as ld  # noqa: E402
import lb162  # noqa: E402
import lb162x  # noqa: E402
import lb162x_guard as guard_mod  # noqa: E402

common, gaia, phase_loop = ld.common, ld.gaia, ld.phase

LOT = "lb162x"
BRAZO = "CC"
RUN_DIR = lb162x.RUN_DIR
EXIT = {**s162.EXIT, "error": 7, "outage": 8, "smoke": 9}
Phase = lb162x.Phase
SMOKE = lb162x.SMOKE


def sessions_of(phase: Phase) -> pathlib.Path:
    return ld.PRIVATE / phase.name / "sessions.jsonl"


def reservations_of(phase: Phase) -> pathlib.Path:
    return sessions_of(phase).with_name("reservations.jsonl")


def smoke_task() -> Any:
    """lb162's smoke task: lot L6's, a LongBench dev task outside the 162."""
    task = lb162.l6.b3_tasks(dev=True)[0]
    if task.task_id in set(lb162.frozen_ids()):
        raise SystemExit("the smoke task is one of the 162")
    return task


def tasks_of(phase: Phase) -> list[Any]:
    """The phase's tasks in the frozen order, checked against lb162's recorded rows."""
    if phase.key == SMOKE.key:
        return [smoke_task()]
    ids = lb162x.frozen_order(phase, lb162x.jev_rows())
    by_id = {t.task_id: t for t in lb162.load_tasks()}
    return [by_id[i] for i in ids]


def steps(phase: Phase, tasks: Sequence[Any]) -> list[tuple]:
    return ld.planned(tasks, [phase.model], [BRAZO])


def done_now(phase: Phase, sessions: pathlib.Path | None = None) -> int:
    rows = gaia.read_rows(sessions or sessions_of(phase))
    return sum(1 for r in rows
               if r.get("arm") == phase.arm and not r.get("not_run") and r["run"] > 0)  # fmt: skip


def smoke_cap(spent: float) -> float | None:
    """The smoke's one session: its cap while nothing is spent, then nothing (its ceiling)."""
    return SMOKE.full_cap if spent + SMOKE.full_cap <= SMOKE.ceiling + 1e-9 else None


def session_for(phase: Phase, ctx: Mapping[str, Any]) -> Callable:
    def session(item: tuple, run: int, arm: str, cap: float) -> dict[str, Any]:
        row = ld.one_session(item[3], run, arm, ctx, caps={phase.model: cap})
        if phase_loop.usage_limited(row):
            phase_loop._log(
                sessions_of(phase), f"STOP-LIMIT {item[0]} {arm}: 429 or usage limit in the session"
            )
        return row

    return session


def clock_refusal(phase: Phase, now: dt.datetime, todo: int) -> str:
    if now.hour < s162.EARLIEST_HOUR:
        return f"phase {phase.key} refused: {now:%H:%M} is before {s162.EARLIEST_HOUR:02d}:00"
    seconds = todo * phase.wall_mean_s * s162.WALL_FACTOR + s162.MIDNIGHT_MARGIN_S
    if s162.crosses_midnight(now, seconds):
        return (f"phase {phase.key} refused: {todo} sessions (~{seconds / 60:.0f} min with "
                f"margin) started at {now:%H:%M} would cross midnight")  # fmt: skip
    return ""


# --- rows without text --------------------------------------------------------------------------


def public_rows(rows: Sequence[Mapping[str, Any]], phase: Phase) -> list[dict[str, Any]]:
    """lb162's public row (id, letter, grade, cost, time, how it ended) plus the cap it ran with
    and whether most of its cost went to the phase's model."""
    out = []
    for r in phase_loop.counted(list(rows)):
        if r.get("arm") != phase.arm:
            continue
        served = guard_mod.served_by(r)
        out.append({"id": r["task_id"], "letter": r.get("final_answer"),
                    "ok": bool(r.get("ok_oficial")), "usd": round(float(r["list_usd"]), 6),
                    "wall_s": r.get("wall_s"), "turns": r.get("turns"),
                    "hit_cap": bool(r.get("hit_cap")),
                    "no_letter": r.get("final_answer") is None,
                    "is_error": not r.get("ok", False), "subtype": r.get("subtype"),
                    "cap_usd": r.get("cap_usd"),
                    "served_ok": served is None or served == phase.model_id})  # fmt: skip
    return out


def export(phase: Phase, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    mine = public_rows(rows, phase)
    lb162.write_jsonl(phase.rows, mine)
    return {"sessions": len(mine), "right": sum(r["ok"] for r in mine),
            "list_usd": round(sum(r["usd"] for r in mine), 4)}  # fmt: skip


def smoke_passed(rows: Sequence[Mapping[str, Any]]) -> bool:
    """A letter, no error, and served by Opus (the grade does not matter)."""
    return any(r["letter"] is not None and not r["is_error"] and r["served_ok"] for r in rows)


# --- the driver ---------------------------------------------------------------------------------


def final_kind(phase: Phase) -> str | None:
    """The recorded stop when it is final (finished, or a phase at its ceiling), else None."""
    kind = (lb162x.stop_of(phase) or {}).get("kind")
    finals = ("done",) if phase.key == SMOKE.key else lb162x.FINAL
    return kind if kind in finals else None


def drive(phases: Sequence[Phase], run_one: Callable[[Phase], str],
          final: Callable[[Phase], str | None] = final_kind,
          ) -> tuple[str, dict[str, str]]:  # fmt: skip
    """Run in order, skipping what is already final; stop at the first pause. The lot's kind is
    the pausing one's, or `done` when everything finished, or `ceiling` when every phase is over
    and one ended at its ceiling (the smoke only passes as `done`)."""
    kinds: dict[str, str] = {}
    for phase in phases:
        kind = final(phase) or run_one(phase)
        kinds[phase.key] = kind
        passes = ("done",) if phase.key == SMOKE.key else lb162x.FINAL
        if kind not in passes:
            return (kind if kind in EXIT else "error"), kinds
    return ("done" if all(k == "done" for k in kinds.values()) else "ceiling"), kinds


def exit_code(kind: str) -> int:
    return EXIT.get(kind, EXIT["error"])


def problems() -> list[str]:
    data = [*lb162.data_problems()]
    if not lb162.longdoc_data.RAW.exists():
        data.append(f"no LongBench cache at {lb162.longdoc_data.RAW}")
    if not data:
        data.extend([*lb162x.docs_problems(), *lb162x.recorded_problems()])
    return common.preflight([BRAZO], ld.flag_settings(), data, None, LOT)


def model_problems(pin_dir: pathlib.Path = s162.PIN_DIR) -> list[str]:
    """Free: both models' ids in the pinned Claude Code build."""
    found = gaia.model_ids_in(pin_dir / "claude.exe", [p.model_id for p in lb162x.ORDER])
    return [f"{m} not in the pinned claude.exe" for m, ok in found.items() if not ok]


def pin_problems() -> list[str]:
    """The claude on PATH is the pinned build the seal hashed."""
    sealed = pathlib.Path.home() / lb162x.PIN_REL
    claude = shutil.which("claude")
    if claude is None or not sealed.is_file():
        return ["no claude on PATH or no pinned build to compare"]
    same = lb162.raw_digest(pathlib.Path(claude)) == lb162.raw_digest(sealed)
    return [] if same else [f"the claude on PATH ({claude}) is not the sealed pinned build"]


def live_args(phase: Phase) -> argparse.Namespace:
    return argparse.Namespace(phase=phase.name, ceiling=phase.ceiling, brazos=[BRAZO],
                              models=[phase.model], s_line=str(gaia.arms.s_line.S_INSTALL),
                              unsealed_ok=False, joint_with=[])  # fmt: skip


def run_phase(phase: Phase, found: Sequence[str]) -> str:  # pragma: no cover - paid sessions
    """One phase (or the smoke) through the phase loop; its stop kind and rows."""
    tasks = tasks_of(phase)
    now = dt.datetime.now()
    if why := clock_refusal(phase, now, len(tasks) - done_now(phase)):
        print(why, file=sys.stderr)
        return "clock"
    sessions, reservations = sessions_of(phase), reservations_of(phase)
    sessions.parent.mkdir(parents=True, exist_ok=True)
    smoke = phase.key == SMOKE.key
    guard = guard_mod.Budget(phase, now, sessions, reservations,
                             cap_rule=smoke_cap if smoke else None)  # fmt: skip
    reserve = SMOKE.full_cap if smoke else phase.loop_reserve
    code, rows = common.run_live(live_args(phase), steps(phase, tasks),
                                 guard_mod.known_rows(sessions, reservations),
                                 lambda ctx: guard.wrap(session_for(phase, ctx)), sessions,
                                 {phase.model: reserve}, {phase.name: phase.ceiling},
                                 found)  # fmt: skip
    kind = s162.stop_kind(code, guard)
    said = export(phase, rows)
    if smoke and kind in ("done", "ceiling"):
        kind = "done" if smoke_passed(public_rows(rows, phase)) else "smoke"
    print(json.dumps({"phase": phase.key, **said, "stop": kind}), file=sys.stderr)
    return kind


def guarded_run(phase: Phase, found: Sequence[str],
                run: Callable[[Phase, Sequence[str]], str] = run_phase,
                run_dir: pathlib.Path = RUN_DIR) -> str:  # fmt: skip
    """`run` with every way out turned into a stop kind: a refusal (SystemExit) is `preflight`,
    any other exception `error`; the stop file and, on a usage limit, LIMIT.flag written."""
    try:
        kind = run(phase, found)
    except SystemExit as why:
        print(f"phase {phase.key} refused: {why}", file=sys.stderr)
        kind = "preflight"
    except Exception as why:  # noqa: BLE001 - every failure must end in a stop kind
        print(f"phase {phase.key} failed: {why.__class__.__name__}: {why}", file=sys.stderr)
        kind = "error"
    if kind == "limit":
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "LIMIT.flag").write_text(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} 429\n",
                                            encoding="utf-8")  # fmt: skip
    lb162.write_jsonl(phase.stop, [{"kind": kind}])
    return kind


def refusal(now: dt.datetime, run_dir: pathlib.Path = RUN_DIR) -> tuple[str, str] | None:
    """Before any session: (kind, why) when the lot may not start, else None."""
    try:
        value = lb162x.require_prereg()
        lb162x.jev_rows()  # refuses changed recordings
        if found := [*lb162x.checkout_problems(value), *pin_problems()]:
            return "preflight", "; ".join(found)
    except SystemExit as why:
        return "preflight", str(why)
    if (run_dir / "LIMIT.flag").exists():
        return "limit", "LIMIT.flag in the run folder: the last run met a usage limit"
    first = next((p for p in lb162x.DRIVEN if not final_kind(p)), None)
    if first is None:
        return "done", "every phase is over: nothing to run"
    nxt = lb162x.PHASE_B if first.key == SMOKE.key else first  # the smoke is one session
    if why := clock_refusal(nxt, now, nxt.n - done_now(nxt)):
        return "clock", why
    return None


def live(now: dt.datetime | None = None) -> int:  # pragma: no cover - paid sessions
    if stop := refusal(now or dt.datetime.now()):
        print(stop[1], file=sys.stderr)
        return exit_code(stop[0])
    found = [*model_problems(), *problems()]
    kind, kinds = drive(lb162x.DRIVEN, lambda p: guarded_run(p, found))
    print(json.dumps({"lot": kind, "phases": kinds}), file=sys.stderr)
    return exit_code(kind)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--dry", "--plan", "--preflight", "--live"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--lot", choices=[LOT], default=LOT)
    args = ap.parse_args(argv)
    if args.live:
        return live()
    if args.dry or args.plan:
        print("\n".join(lb162x.dry()))
        task = smoke_task()
        print(f"smoke: {task.task_id} ({task.length}, {task.chars:,d} characters), cap and "
              f"ceiling {SMOKE.full_cap:g} USD, one session")  # fmt: skip
        for p in lb162x.DRIVEN:
            spent = guard_mod.spent_now(sessions_of(p), reservations_of(p))
            print(f"phase {p.key}: spent so far {spent:.2f} USD, {done_now(p)} sessions done, "
                  f"stop {(lb162x.stop_of(p) or {}).get('kind')}")  # fmt: skip
        print(f"seal: {lb162x.seal_state()}")
        return 0
    if args.preflight:
        found = [*s162.pinned_first_on_path(), *model_problems(), *problems(),
                 *lb162x.replay_problems()]  # fmt: skip
        smoke_task()
        print(f"lb162x seal: {lb162x.seal_state()}", file=sys.stderr)
        print("preflight: " + ("; ".join(found) or "ok"), file=sys.stderr)
        return 3 if found else 0
    for p in lb162x.DRIVEN:
        if sessions_of(p).exists():
            print(json.dumps({"phase": p.key, **export(p, gaia.read_rows(sessions_of(p)))}))
        else:
            print(f"no sessions in {sessions_of(p)}: nothing to export", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
