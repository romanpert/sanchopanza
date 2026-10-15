"""Lot lb102 (docs/results/2026-10-16-lb102/prereg.md): Sonnet 5.5 in clean Claude Code (arm N,
`SONNET-CC`) on the 102 LongBench v2 tasks Jev 1.14 did not cover at 0.6 in lot lb162. A thin
runner over h2h_longdoc.py and h2h_lb162.py: the same session (Claude Code 2.1.287 pinned, a
clean user and CLAUDE_CONFIG_DIR per session, the document as `document.txt`, LongBench v2's
official 0-shot template, the web taken away, the local hook), the official `extract_answer`
grade, and lb162's clock and STOP rules. Its own: the tasks (benchmarks/jev114/lb102.py's
frozen order), the phase and its private session folder, and the money rule.

    python benchmarks/h2h/h2h_lb102.py --dry         # free: lb102.py --dry plus what is spent
    python benchmarks/h2h/h2h_lb102.py --preflight   # free: cache, pinned claude, hooks, arm
    powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb102.py -RunnerArgs "--phase lb102" `
        -Pin $env:USERPROFILE\\.cache\\sanchopanza\\claude-pin\\2.1.287 `
        -Log C:\\sp-runs\\lb102\\sonnet.log -PidFile C:\\sp-runs\\lb102\\sonnet.pids   # PAID
    python benchmarks/h2h/h2h_lb102.py               # free: rows without text into the results

Money: the phase never passes lb102.CEILING_USD (16). Before each session (`Budget`) the spend so
far (recorded sessions, plus the reserve of any started session with no row) sets its
--max-budget-usd, `lb102.cap_for`: arm N's 3.00 while 3.00 plus one worst turn (4.32) fits under
the ceiling, else the room left after the worst turn, and a stop (`ceiling`, exit 1) when that
is under 0.50. Claude Code stops only between turns, so a session spends at most its cap plus
one turn: the reserve row written before it holds exactly that. A live run refuses without the
seal, a frozen order that is not lb162's derivation, a start before 08:00 or one whose expected
wall time crosses midnight, and a LIMIT.flag in RUN_DIR. Stops otherwise as lb162's phase S:
the clock (exit 5), a STOP file (exit 6), a 429 or usage limit (exit 2, LIMIT.flag written).
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
import h2h_lb162 as s162  # noqa: E402  (lb162's phase S: the guard, rows and exit codes)
import h2h_longdoc as ld  # noqa: E402
import lb102  # noqa: E402
import lb162  # noqa: E402

common, gaia, phase = ld.common, ld.gaia, ld.phase

PHASE = "lb102"
MODEL, BRAZO, ARM = s162.MODEL, s162.BRAZO, s162.ARM
CEILING_USD = lb102.CEILING_USD
SESSIONS = ld.PRIVATE / PHASE / "sessions.jsonl"
RESERVATIONS = SESSIONS.with_name("reservations.jsonl")
RUN_DIR = lb102.RUN_DIR
EXIT = s162.EXIT
# The phase loop's own check (browse/phase.py: spent + this > the ceiling stops): the floor cap
# plus one worst turn, the same line as `lb102.cap_for` returning None.
RESERVE = {MODEL: lb102.LOOP_RESERVE_USD}


def uncovered_tasks() -> list[Any]:
    """The 102 in the frozen order, checked against the derivation from lb162's rows."""
    ids = lb102.frozen_order(lb102.jev_rows())
    by_id = {t.task_id: t for t in lb162.load_tasks()}
    return [by_id[i] for i in ids]


def steps(tasks: Sequence[Any]) -> list[tuple]:
    return ld.planned(tasks, [MODEL], [BRAZO])


# --- money: reservations and the spend so far ---------------------------------------------------


def reserve(path: pathlib.Path, task: str, run: int, arm: str, now: dt.datetime,
            cap: float) -> None:  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"task": task, "run": run, "arm": arm, "cap_usd": cap,
            "reserve_usd": round(cap + lb102.WORST_TURN_USD, 4),
            "started": f"{now:%Y-%m-%dT%H:%M:%S}"}  # fmt: skip
    with path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(line) + "\n")


def open_reservations(rows: Sequence[Mapping[str, Any]],
                      path: pathlib.Path = RESERVATIONS) -> list[dict[str, Any]]:  # fmt: skip
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


def known_rows(sessions: pathlib.Path = SESSIONS,
               reservations: pathlib.Path = RESERVATIONS) -> list[dict[str, Any]]:  # fmt: skip
    rows = gaia.read_rows(sessions)
    return [*rows, *open_reservations(rows, reservations)]


def spent_now(sessions: pathlib.Path = SESSIONS,
              reservations: pathlib.Path = RESERVATIONS) -> float:  # fmt: skip
    return sum(float(r["list_usd"]) for r in known_rows(sessions, reservations))


def done_now() -> int:
    return sum(1 for r in gaia.read_rows(SESSIONS)
               if r.get("arm") == ARM and not r.get("not_run") and r["run"] > 0)  # fmt: skip


class Budget(s162.Guard):
    """lb162's checks before each session (the clock, the STOP file), then the money rule: the
    session's cap from the spend so far, a stop below the floor, and its reserve row."""

    def __init__(self, start: dt.datetime, spent: Callable[[], float] = spent_now,
                 clock: Callable[[], dt.datetime] = dt.datetime.now,
                 run_dir: pathlib.Path = RUN_DIR,
                 reservations: pathlib.Path = RESERVATIONS) -> None:  # fmt: skip
        super().__init__(start, clock=clock, run_dir=run_dir, reservations=reservations)
        self.spent = spent

    def wrap(self, session: Callable) -> Callable:
        """`session(item, run, arm, cap)` as the phase loop's `(item, run, arm)`."""

        def one(item: tuple, run: int, arm: str) -> dict[str, Any]:
            now = self.clock()
            if stop := self.refusal(now):
                self.kind = stop[0]
                raise s162.ClockStop(stop[1])
            spent = self.spent()
            cap = lb102.cap_for(spent)
            if cap is None:
                self.kind = "ceiling"
                floor = lb102.CAP_FLOOR_USD
                raise s162.ClockStop(
                    f"ceiling: {spent:.2f} USD spent, under {floor:g} left after one worst turn"
                )
            reserve(self.reservations, item[0], run, arm, now, cap)
            return session(item, run, arm, cap)

        return one


def session_for(ctx: Mapping[str, Any]) -> Callable:
    def session(item: tuple, run: int, arm: str, cap: float) -> dict[str, Any]:
        row = ld.one_session(item[3], run, arm, ctx, caps={MODEL: cap})
        if phase.usage_limited(row):
            phase._log(SESSIONS, f"STOP-LIMIT {item[0]} {arm}: 429 or usage limit in the session")
        return row

    return session


def clock_refusal(now: dt.datetime, todo: int) -> str:
    if now.hour < s162.EARLIEST_HOUR:
        return f"lb102 refused: {now:%H:%M} is before {s162.EARLIEST_HOUR:02d}:00"
    seconds = todo * lb102.WALL_MEAN_S * s162.WALL_FACTOR + s162.MIDNIGHT_MARGIN_S
    if s162.crosses_midnight(now, seconds):
        return (f"lb102 refused: {todo} sessions (~{seconds / 60:.0f} min with margin) started "
                f"at {now:%H:%M} would cross midnight")  # fmt: skip
    return ""


# --- rows without text --------------------------------------------------------------------------


def public_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """lb162's public row (id, letter, grade, cost, time, how it ended) plus the cap it ran with."""
    mine = [r for r in phase.counted(list(rows)) if r.get("arm") == ARM]
    return [{**pub, "cap_usd": raw.get("cap_usd")}
            for raw, pub in zip(mine, s162.public_rows(rows), strict=True)]  # fmt: skip


def export(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    mine = public_rows(rows)
    lb162.write_jsonl(lb102.SONNET_ROWS, mine)
    return {"sessions": len(mine), "right": sum(r["ok"] for r in mine),
            "list_usd": round(sum(r["usd"] for r in mine), 4)}  # fmt: skip


# --- preflight, live, main ----------------------------------------------------------------------


def problems() -> list[str]:
    data = [*lb162.data_problems()]
    if not lb162.longdoc_data.RAW.exists():
        data.append(f"no LongBench cache at {lb162.longdoc_data.RAW}")
    if not data:
        data.extend([*lb102.docs_problems(), *lb102.check_derivation(lb102.jev_rows())])
    return common.preflight([BRAZO], ld.flag_settings(), data, None, PHASE)


def live_args() -> argparse.Namespace:
    return argparse.Namespace(phase=PHASE, ceiling=CEILING_USD, brazos=[BRAZO], models=[MODEL],
                              s_line=str(gaia.arms.s_line.S_INSTALL), unsealed_ok=False,
                              joint_with=[])  # fmt: skip


def live() -> int:  # pragma: no cover - paid sessions
    lb102.require_prereg()
    tasks = uncovered_tasks()
    todo = len(tasks) - done_now()
    now = dt.datetime.now()
    if why := clock_refusal(now, todo):
        raise SystemExit(why)
    if (RUN_DIR / "LIMIT.flag").exists():
        raise SystemExit("LIMIT.flag in the run folder: the last run met a usage limit")
    SESSIONS.parent.mkdir(parents=True, exist_ok=True)
    guard = Budget(now)
    code, rows = common.run_live(live_args(), steps(tasks), known_rows(),
                                 lambda ctx: guard.wrap(session_for(ctx)), SESSIONS, RESERVE,
                                 {PHASE: CEILING_USD}, problems())  # fmt: skip
    kind = s162.stop_kind(code, guard)
    if kind == "limit":
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "LIMIT.flag").write_text(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} 429\n",
                                            encoding="utf-8")  # fmt: skip
    lb162.write_jsonl(lb102.SONNET_STOP, [{"kind": kind}])
    print(json.dumps(export(rows) | {"stop": kind}), file=sys.stderr)
    return EXIT.get(kind, 7)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    for flag in ("--dry", "--preflight", "--live"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--phase", choices=[PHASE], default=PHASE)
    args = ap.parse_args(argv)
    if args.live:
        return live()
    if args.dry:
        print("\n".join(lb102.dry()))
        print(f"spent so far {spent_now():.2f} USD, {done_now()} sessions done; seal: "
              f"{lb102.seal_state()}")  # fmt: skip
        return 0
    if args.preflight:
        found = [*s162.pinned_first_on_path(), *problems()]
        print(f"lb102 seal: {lb102.seal_state()}", file=sys.stderr)
        print("preflight: " + ("; ".join(found) or "ok"), file=sys.stderr)
        return 3 if found else 0
    if not SESSIONS.exists():
        print(f"no sessions in {SESSIONS}: nothing to export", file=sys.stderr)
        return 0
    print(json.dumps(export(gaia.read_rows(SESSIONS))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
