"""Lot lb162x's guard before and after each paid session (benchmarks/h2h/h2h_lb162x.py): the
money (reservations, the spend so far, the session's cap) and the health of what came back
(an outage, a streak of infrastructure errors, a session another model served).

Money. A reservation row (the session's cap plus one worst turn, with an id) is written before
each session, and the session's row carries that id. The spend so far is every recorded row at
its cost, except a row whose cost is unknown (no reply Claude Code could price: the runner's
own subtype, or an error that reports tokens but no cost), which counts at its reservation; plus
every reservation with no row (a session that died) at its reserve. So a phase never passes its
ceiling.

Health. After a session: a reply that names an authentication or model-availability failure
(401, OAuth, "model not available") is an outage at once; a session most of whose cost went to
another model than the phase's is not run; an infrastructure error (an error with no letter,
not a cap stop) or another model's session counts toward a streak, and OUTAGE_STREAK of them in
a row are an outage. An outage marks the streak's rows not run (asked again on a resume, free),
stops the phase (kind `outage`, a pause) and records nothing as a result.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import h2h_lb162 as s162
import h2h_longdoc as ld
import lb162
import lb162x

gaia, phase_loop = ld.gaia, ld.phase

OUTAGE_STREAK = 3
OUTAGE_TEXT = re.compile(
    r"\b401\b|\b403\b|unauthori[sz]ed|authenticat|oauth|invalid api key|api key|"
    r"model\b.{0,60}\bnot (?:available|found|supported)|not_found_error|permission_error",
    re.I,
)


class OutageStop(s162.ClockStop):
    """An outage: the phase loop ends as at its ceiling; `Budget.kind` says `outage`."""


# --- money ----------------------------------------------------------------------------------------


def reserve(path: pathlib.Path, task: str, run: int, arm: str, now: dt.datetime, cap: float,
            worst_turn: float) -> str:  # fmt: skip
    """Write the reservation row; its id, which the session's row carries."""
    rid = uuid.uuid4().hex
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"rid": rid, "task": task, "run": run, "arm": arm, "cap_usd": cap,
            "reserve_usd": round(cap + worst_turn, 4),
            "started": f"{now:%Y-%m-%dT%H:%M:%S}"}  # fmt: skip
    with path.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(line) + "\n")
    return rid


def _key(r: Mapping[str, Any]) -> tuple:
    return r["task"], r["run"], r["arm"]


def open_reservations(rows: Sequence[Mapping[str, Any]],
                      path: pathlib.Path) -> list[dict[str, Any]]:  # fmt: skip
    """A not-run row at its own reserve for every started session with no recorded row: asked
    again on a resume, its reserve counted against the ceiling. Matched by id; a reservation
    without one is matched by key, the earliest left open (a death ends its process, so the
    sessions after it on the same key are the ones that recorded)."""
    found = lb162.read_jsonl(path) or []
    recorded_ids = {r.get("reservation") for r in rows}
    out = [r for r in found if r.get("rid") and r["rid"] not in recorded_ids]
    legacy: dict[tuple, list[float]] = {}
    for r in found:
        if not r.get("rid"):
            legacy.setdefault(_key(r), []).append(float(r["reserve_usd"]))
    unmatched = [r for r in rows if not r.get("reservation")]
    left = []
    for key, reserves in legacy.items():
        recorded = sum(_key(r) == key for r in unmatched)
        left += [(key, usd) for usd in reserves[: len(reserves) - recorded]]
    return [*({"task": r["task"], "task_id": r["task"], "run": r["run"], "arm": r["arm"],
               "not_run": True, "open": True, "list_usd": float(r["reserve_usd"])} for r in out),
            *({"task": k[0], "task_id": k[0], "run": k[1], "arm": k[2], "not_run": True,
               "open": True, "list_usd": usd} for k, usd in left)]  # fmt: skip


def cost_unknown(row: Mapping[str, Any]) -> bool:
    """No cost Claude Code could report: the runner's own subtype (a wall-clock timeout, a reply
    that is not JSON), or an error that used tokens but reports 0 USD. An error with no tokens
    and 0 USD (a refused request) cost nothing."""
    if str(row.get("subtype") or "").startswith("runner:"):
        return True
    if row.get("ok", False) or float(row.get("list_usd") or 0.0) > 0:
        return False
    tokens = row.get("tokens")
    used = sum(v for k, v in tokens.items() if k != "web_searches") if tokens else None
    return used is None or used > 0


def spent_now(sessions: pathlib.Path, reservations: pathlib.Path,
              fallback: float = 0.0) -> float:  # fmt: skip
    """Every recorded row at its cost (an unknown cost at its reservation, or `fallback`), and
    every open reservation at its reserve."""
    rows = gaia.read_rows(sessions)
    held = {r["rid"]: float(r["reserve_usd"]) for r in lb162.read_jsonl(reservations) or []
            if r.get("rid")}  # fmt: skip
    total = 0.0
    for r in rows:
        usd = float(r.get("list_usd") or 0.0)
        if cost_unknown(r):
            usd = max(usd, held.get(r.get("reservation"), fallback))
        total += usd
    return total + sum(float(o["list_usd"]) for o in open_reservations(rows, reservations))


def known_rows(sessions: pathlib.Path, reservations: pathlib.Path) -> list[dict[str, Any]]:
    rows = gaia.read_rows(sessions)
    return [*rows, *open_reservations(rows, reservations)]


# --- health ---------------------------------------------------------------------------------------


def served_by(row: Mapping[str, Any]) -> str | None:
    """The model most of the session's cost went to (None with no cost by model)."""
    by_model = {m: float(u or 0.0) for m, u in (row.get("usd_by_model") or {}).items()}
    if not by_model or max(by_model.values()) <= 0:
        return None
    return max(by_model, key=by_model.__getitem__)


def reply_text(row: Mapping[str, Any]) -> str:
    """What the session said about itself: its subtype and Claude Code's stderr."""
    side = pathlib.Path(str(row.get("side") or "")) / "stderr.txt"
    text = side.read_text(encoding="utf-8", errors="replace") if row.get("side") and \
        side.is_file() else ""  # fmt: skip
    return f"{row.get('subtype') or ''}\n{text}"


def trouble(row: Mapping[str, Any], model_id: str) -> tuple[str, str] | None:
    """("outage", why) at once, ("infra", why) toward the streak, or None for a measurement."""
    if phase_loop.usage_limited(row):
        return None  # the loop's own stop (a 429 or usage limit)
    no_letter = row.get("final_answer") is None
    if no_letter and OUTAGE_TEXT.search(reply_text(row)):
        return "outage", f"authentication or model failure ({row.get('subtype')})"
    served = served_by(row)
    if served is not None and served != model_id:
        return "infra", f"served by {served}"
    if no_letter and not row.get("hit_cap") and not row.get("ok", False):
        return "infra", f"infrastructure error ({row.get('subtype')})"
    return None


def void(sessions: pathlib.Path, rids: Sequence[str], why: str) -> None:
    """Mark the rows of reservations `rids` not run (rewritten in place, atomically)."""
    if not rids or not sessions.exists():
        return
    out = []
    for line in sessions.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("reservation") in rids and not row.get("not_run"):
            row = {**row, "not_run": True, "invalid": why}
        out.append(json.dumps(row, ensure_ascii=False))
    tmp = sessions.with_suffix(".tmp")
    tmp.write_text("".join(x + "\n" for x in out), encoding="utf-8")
    os.replace(tmp, sessions)


class Budget(s162.Guard):
    """lb162's checks before each session (the clock, the STOP file), then the phase's money
    rule (the session's cap from the spend so far, a stop below the floor, its reservation row),
    then the session's health after it (an outage, a streak, another model)."""

    def __init__(self, phase: Any, start: dt.datetime, sessions: pathlib.Path,
                 reservations: pathlib.Path,
                 cap_rule: Callable[[float], float | None] | None = None,
                 clock: Callable[[], dt.datetime] = dt.datetime.now,
                 run_dir: pathlib.Path = lb162x.RUN_DIR) -> None:  # fmt: skip
        super().__init__(start, clock=clock, run_dir=run_dir, reservations=reservations)
        self.phase, self.sessions = phase, sessions
        self.cap_rule = cap_rule or (lambda spent: lb162x.cap_for(spent, phase))
        self.streak: list[str] = []

    def spent(self) -> float:
        return spent_now(self.sessions, self.reservations,
                         self.phase.full_cap + self.phase.worst_turn)  # fmt: skip

    def wrap(self, session: Callable) -> Callable:
        """`session(item, run, arm, cap)` as the phase loop's `(item, run, arm)`."""

        def one(item: tuple, run: int, arm: str) -> dict[str, Any]:
            now = self.clock()
            if stop := self.refusal(now):
                self.kind = stop[0]
                raise s162.ClockStop(stop[1])
            spent = self.spent()
            cap = self.cap_rule(spent)
            if cap is None:
                self.kind = "ceiling"
                raise s162.ClockStop(
                    f"ceiling: {spent:.2f} USD spent in phase {self.phase.key}, "
                    f"under {self.phase.floor:g} left after one worst turn"
                )
            rid = reserve(self.reservations, item[0], run, arm, now, cap, self.phase.worst_turn)
            row = {**session(item, run, arm, cap), "reservation": rid}
            return self.checked(row, rid)

        return one

    def checked(self, row: dict[str, Any], rid: str) -> dict[str, Any]:
        found = trouble(row, self.phase.model_id)
        if found is None:
            self.streak = []
            return row
        kind, why = found
        if kind == "outage" or len(self.streak) + 1 >= OUTAGE_STREAK:
            void(self.sessions, self.streak, f"outage: {why}")
            phase_loop._record(self.sessions, {**row, "not_run": True, "invalid": f"outage: {why}"})
            self.kind = "outage"
            raise OutageStop(f"STOP outage in phase {self.phase.key}: {why}")
        self.streak.append(rid)
        return {**row, "not_run": True, "invalid": why} if why.startswith("served by") else row
