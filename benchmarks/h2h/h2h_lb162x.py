"""Lot lb162x (docs/results/2026-10-16-lb162x/prereg.md): one driver for both paid phases, the
expensive model in clean Claude Code (arm N) where lot lb162 did not run it, Jev's lb162 answers
reused as recorded (no Jev call). Phase B first (Opus 5.5 on all 162 tasks: the primary
verdict), then phase A (Sonnet 5.5 on the 102 uncovered). A thin runner over h2h_longdoc.py and
h2h_lb162.py: the same session (Claude Code 2.1.287 pinned, a clean user and CLAUDE_CONFIG_DIR
per session, the document as `document.txt`, LongBench v2's official 0-shot template, the web
taken away, the local hook), the official `extract_answer` grade, and lb162's clock and STOP
rules. Its own: each phase's tasks (benchmarks/jev114/lb162x.py's frozen orders), private
session folder, ceiling and money rule.

    python benchmarks/h2h/h2h_lb162x.py --dry         # free: lb162x.py --dry plus what is spent
    python benchmarks/h2h/h2h_lb162x.py --preflight   # free: cache, recordings, pinned claude
    powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb162x.py -RunnerArgs "--lot lb162x" `
        -Pin $env:USERPROFILE\\.cache\\sanchopanza\\claude-pin\\2.1.287 -KeysEnv <path> `
        -Log C:\\sp-runs\\lb162x\\driver.log -PidFile C:\\sp-runs\\lb162x\\driver.pids   # PAID
    python benchmarks/h2h/h2h_lb162x.py               # free: rows without text into the results

Money: a phase never passes its ceiling (B 45, A 16 USD). Before each session (`Budget`) the spend
so far of that phase (recorded sessions, plus the reserve of any started session with no row)
sets its --max-budget-usd, `lb162x.cap_for`: the phase's full cap (Opus 6.00, Sonnet 3.00) while
it plus one worst turn (8.64, 4.32) fits, else the room left after the worst turn, and a stop
(`ceiling`, final) under the phase's floor (1.00, 0.50). Claude Code stops only between turns,
so a session spends at most its cap plus one turn: the reservation row written before it holds
exactly that. A live run refuses without the seal, with lb162's recordings changed, a frozen
order that is not their derivation, a LIMIT.flag in RUN_DIR, or a phase start before 08:00 or
one whose expected wall time crosses midnight. Stops otherwise as lb162's phase S: the clock
(exit 5), a STOP file (exit 6), a 429 or usage limit (exit 2, LIMIT.flag written). Phase A starts
only after phase B ended by finishing or by its ceiling; a relaunch skips a phase so ended and
resumes the other for free.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
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

common, gaia, phase_loop = ld.common, ld.gaia, ld.phase

LOT = "lb162x"
BRAZO = "CC"
RUN_DIR = lb162x.RUN_DIR
EXIT = s162.EXIT
Phase = lb162x.Phase


def sessions_of(phase: Phase) -> pathlib.Path:
    return ld.PRIVATE / phase.name / "sessions.jsonl"


def reservations_of(phase: Phase) -> pathlib.Path:
    return sessions_of(phase).with_name("reservations.jsonl")


def tasks_of(phase: Phase) -> list[Any]:
    """The phase's tasks in the frozen order, checked against lb162's recorded rows."""
    ids = lb162x.frozen_order(phase, lb162x.jev_rows())
    by_id = {t.task_id: t for t in lb162.load_tasks()}
    return [by_id[i] for i in ids]


def steps(phase: Phase, tasks: Sequence[Any]) -> list[tuple]:
    return ld.planned(tasks, [phase.model], [BRAZO])


# --- money: reservations and the spend so far ---------------------------------------------------


def reserve(path: pathlib.Path, task: str, run: int, arm: str, now: dt.datetime, cap: float,
            worst_turn: float) -> None:  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"task": task, "run": run, "arm": arm, "cap_usd": cap,
            "reserve_usd": round(cap + worst_turn, 4),
            "started": f"{now:%Y-%m-%dT%H:%M:%S}"}  # fmt: skip
    with path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(line) + "\n")


def open_reservations(rows: Sequence[Mapping[str, Any]],
                      path: pathlib.Path) -> list[dict[str, Any]]:  # fmt: skip
    """A not-run row at its own reserve for every started session with no recorded row: asked
    again on a resume, its reserve counted against the ceiling."""
    started: dict[tuple, list[float]] = {}
    for r in lb162.read_jsonl(path) or []:
        started.setdefault((r["task"], r["run"], r["arm"]), []).append(float(r["reserve_usd"]))
    out = []
    for key, reserves in started.items():
        recorded = sum((r["task"], r["run"], r["arm"]) == key for r in rows)
        for usd in reserves[recorded:]:
            out.append({"task": key[0], "task_id": key[0], "run": key[1], "arm": key[2],
                        "not_run": True, "open": True, "list_usd": usd})  # fmt: skip
    return out


def known_rows(sessions: pathlib.Path, reservations: pathlib.Path) -> list[dict[str, Any]]:
    rows = gaia.read_rows(sessions)
    return [*rows, *open_reservations(rows, reservations)]


def spent_now(sessions: pathlib.Path, reservations: pathlib.Path) -> float:
    return sum(float(r["list_usd"]) for r in known_rows(sessions, reservations))


def done_now(phase: Phase, sessions: pathlib.Path | None = None) -> int:
    rows = gaia.read_rows(sessions or sessions_of(phase))
    return sum(1 for r in rows
               if r.get("arm") == phase.arm and not r.get("not_run") and r["run"] > 0)  # fmt: skip


class Budget(s162.Guard):
    """lb162's checks before each session (the clock, the STOP file), then the phase's money
    rule: the session's cap from the spend so far, a stop below the floor, and its reserve row."""

    def __init__(self, phase: Phase, start: dt.datetime, spent: Callable[[], float],
                 clock: Callable[[], dt.datetime] = dt.datetime.now,
                 run_dir: pathlib.Path = RUN_DIR,
                 reservations: pathlib.Path | None = None) -> None:  # fmt: skip
        super().__init__(start, clock=clock, run_dir=run_dir,
                         reservations=reservations or reservations_of(phase))  # fmt: skip
        self.phase, self.spent = phase, spent

    def wrap(self, session: Callable) -> Callable:
        """`session(item, run, arm, cap)` as the phase loop's `(item, run, arm)`."""

        def one(item: tuple, run: int, arm: str) -> dict[str, Any]:
            now = self.clock()
            if stop := self.refusal(now):
                self.kind = stop[0]
                raise s162.ClockStop(stop[1])
            spent = self.spent()
            cap = lb162x.cap_for(spent, self.phase)
            if cap is None:
                self.kind = "ceiling"
                raise s162.ClockStop(
                    f"ceiling: {spent:.2f} USD spent in phase {self.phase.key}, "
                    f"under {self.phase.floor:g} left after one worst turn"
                )
            reserve(self.reservations, item[0], run, arm, now, cap, self.phase.worst_turn)
            return session(item, run, arm, cap)

        return one


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


def public_rows(rows: Sequence[Mapping[str, Any]], arm: str) -> list[dict[str, Any]]:
    """lb162's public row (id, letter, grade, cost, time, how it ended) plus the cap it ran with."""
    out = []
    for r in phase_loop.counted(list(rows)):
        if r.get("arm") != arm:
            continue
        out.append({"id": r["task_id"], "letter": r.get("final_answer"),
                    "ok": bool(r.get("ok_oficial")), "usd": round(float(r["list_usd"]), 6),
                    "wall_s": r.get("wall_s"), "turns": r.get("turns"),
                    "hit_cap": bool(r.get("hit_cap")),
                    "no_letter": r.get("final_answer") is None,
                    "is_error": not r.get("ok", False), "subtype": r.get("subtype"),
                    "cap_usd": r.get("cap_usd")})  # fmt: skip
    return out


def export(phase: Phase, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    mine = public_rows(rows, phase.arm)
    lb162.write_jsonl(phase.rows, mine)
    return {"sessions": len(mine), "right": sum(r["ok"] for r in mine),
            "list_usd": round(sum(r["usd"] for r in mine), 4)}  # fmt: skip


# --- the driver ---------------------------------------------------------------------------------


def final_kind(phase: Phase) -> str | None:
    """The phase's recorded stop when it is final (finished or at its ceiling), else None."""
    kind = (lb162x.stop_of(phase) or {}).get("kind")
    return kind if kind in lb162x.FINAL else None


def drive(
    phases: Sequence[Phase],
    run_one: Callable[[Phase], str],
    final: Callable[[Phase], str | None] = final_kind,
) -> tuple[str, dict[str, str]]:
    """Run the phases in order, skipping one already final; stop at the first that pauses. The
    lot's kind is the pausing phase's kind, or `done` when every phase finished, or `ceiling`
    when every phase is over and one ended at its ceiling."""
    kinds: dict[str, str] = {}
    for phase in phases:
        kind = final(phase) or run_one(phase)
        kinds[phase.key] = kind
        if kind not in lb162x.FINAL:
            return kind, kinds
    return ("done" if all(k == "done" for k in kinds.values()) else "ceiling"), kinds


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


def live_args(phase: Phase) -> argparse.Namespace:
    return argparse.Namespace(phase=phase.name, ceiling=phase.ceiling, brazos=[BRAZO],
                              models=[phase.model], s_line=str(gaia.arms.s_line.S_INSTALL),
                              unsealed_ok=False, joint_with=[])  # fmt: skip


def run_phase(phase: Phase, found: Sequence[str]) -> str:  # pragma: no cover - paid sessions
    """One phase through the phase loop; its stop kind (and stop file, LIMIT.flag, rows)."""
    tasks = tasks_of(phase)
    now = dt.datetime.now()
    sessions, reservations = sessions_of(phase), reservations_of(phase)
    if why := clock_refusal(phase, now, len(tasks) - done_now(phase)):
        print(why, file=sys.stderr)
        kind = "clock"
    else:
        sessions.parent.mkdir(parents=True, exist_ok=True)
        guard = Budget(phase, now, lambda: spent_now(sessions, reservations))
        code, rows = common.run_live(live_args(phase), steps(phase, tasks),
                                     known_rows(sessions, reservations),
                                     lambda ctx: guard.wrap(session_for(phase, ctx)), sessions,
                                     {phase.model: phase.loop_reserve},
                                     {phase.name: phase.ceiling}, found)  # fmt: skip
        kind = s162.stop_kind(code, guard)
        print(json.dumps({"phase": phase.key, **export(phase, rows), "stop": kind}),
              file=sys.stderr)  # fmt: skip
    if kind == "limit":
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "LIMIT.flag").write_text(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} 429\n",
                                            encoding="utf-8")  # fmt: skip
    lb162.write_jsonl(phase.stop, [{"kind": kind}])
    return kind


def live() -> int:  # pragma: no cover - paid sessions
    lb162x.require_prereg()
    lb162x.jev_rows()  # refuses changed recordings
    if (RUN_DIR / "LIMIT.flag").exists():
        raise SystemExit("LIMIT.flag in the run folder: the last run met a usage limit")
    first = next((p for p in lb162x.ORDER if not final_kind(p)), None)
    if first is None:
        raise SystemExit("both phases are over: nothing to run")
    if why := clock_refusal(first, dt.datetime.now(), first.n - done_now(first)):
        raise SystemExit(why)
    found = [*model_problems(), *problems()]
    kind, kinds = drive(lb162x.ORDER, lambda p: run_phase(p, found))
    print(json.dumps({"lot": kind, "phases": kinds}), file=sys.stderr)
    return EXIT.get(kind, 7)


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
        for p in lb162x.ORDER:
            print(f"phase {p.key}: spent so far "
                  f"{spent_now(sessions_of(p), reservations_of(p)):.2f} USD, {done_now(p)} "
                  f"sessions done, stop {(lb162x.stop_of(p) or {}).get('kind')}")  # fmt: skip
        print(f"seal: {lb162x.seal_state()}")
        return 0
    if args.preflight:
        found = [*s162.pinned_first_on_path(), *model_problems(), *problems(),
                 *lb162x.replay_problems()]  # fmt: skip
        print(f"lb162x seal: {lb162x.seal_state()}", file=sys.stderr)
        print("preflight: " + ("; ".join(found) or "ok"), file=sys.stderr)
        return 3 if found else 0
    for p in lb162x.ORDER:
        if sessions_of(p).exists():
            print(json.dumps({"phase": p.key, **export(p, gaia.read_rows(sessions_of(p)))}))
        else:
            print(f"no sessions in {sessions_of(p)}: nothing to export", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
