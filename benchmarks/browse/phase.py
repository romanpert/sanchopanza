"""The loop both end-to-end browse runners share (`e2e.py`, `e2e_mcp.py`).

Every guard is checked before a session starts and counts every session already paid for,
warm-ups included. A runner that resumes warms the prompt cache again with a new uncounted
session, since the cache it wrote before has gone cold; and it logs its own progress beside its
sessions file, so launching a phase needs no shell redirection.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

WARMUP_RUN = -9  # warm-ups are runs -9, -10, ...: excluded from every count (run <= 0)
# The subscription's answer instead of a session (3m: "You've hit your weekly limit").
_USAGE_LIMIT = re.compile(r"hit your (?:\w+ )?limit", re.I)
SHOWN = ("task", "run", "arm", "success", "list_usd", "turns", "jev_usd", "tools")

Task = tuple[str, str, str, list[Any]]
Session = Callable[[Task, int, str], dict[str, Any]]


@dataclass(frozen=True)
class Limits:
    session_max_usd: float
    ceiling_usd: float
    jev_session_max_usd: float = 0.0
    jev_ceiling_usd: float | None = None
    early_stop_usd: float | None = None  # Phase 3's rule: on the first tasks' spend only
    early_tasks: frozenset[str] = field(default_factory=frozenset)


def planned(tasks: list[Task], runs: list[int], arms: tuple[str, ...]) -> list[tuple]:
    """(task index, task, run, arm) in the order the phase runs them."""
    return [(i, task, run, arm) for i, task in enumerate(tasks) for run in runs for arm in arms]


def usage_limited(row: dict[str, Any]) -> bool:
    return bool(_USAGE_LIMIT.search(str(row.get("answer") or "")))


def counted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sessions a phase reports: not the warm-ups, not the ones the usage limit stopped."""
    return [r for r in rows if r["run"] > 0 and not r.get("not_run")]


def next_warmup_run(rows: list[dict[str, Any]]) -> int:
    used = [r["run"] for r in rows if r["run"] <= WARMUP_RUN]
    return min(used) - 1 if used else WARMUP_RUN


def stop_reason(rows: list[dict[str, Any]], limits: Limits, task_index: int) -> str | None:
    spent = sum(r["list_usd"] for r in rows)
    if spent + limits.session_max_usd > limits.ceiling_usd:
        return f"ceiling: {spent:.2f} USD spent"
    jev = sum(r.get("jev_usd", 0.0) for r in rows)
    if limits.jev_ceiling_usd is not None and jev + limits.jev_session_max_usd > (
        limits.jev_ceiling_usd
    ):
        return f"Jev ceiling: {jev:.4f} USD spent"
    if limits.early_stop_usd is not None and task_index >= len(limits.early_tasks):
        early = sum(r["list_usd"] for r in rows if r["task"] in limits.early_tasks)
        if early > limits.early_stop_usd:
            return f"early stop: the first two tasks passed {limits.early_stop_usd:g} USD"
    return None


class PhaseBudget:
    """One ceiling for a whole phase, however many harness clients it runs through, counted from
    each session's own cost. A client's `spent_usd` starts from its cache's total, so two
    clients count a replayed run twice and each holds only itself to the ceiling."""

    def __init__(self, ceiling_usd: float, concurrency: int) -> None:
        self.ceiling_usd = ceiling_usd
        self.spent_usd = 0.0
        self._reserved = 0.0
        # Sessions reserve their cap only once they hold a slot: a phase gathers every session
        # at once, and reserving in the client's queue would refuse most of them.
        self._slots = asyncio.Semaphore(concurrency)

    async def run(self, client: Any, session_max_usd: float, text: str, schema: Any = None) -> Any:
        async with self._slots:
            if self.spent_usd + self._reserved + session_max_usd > self.ceiling_usd:
                raise RuntimeError(
                    f"phase ceiling: {self.spent_usd:.2f} USD spent of {self.ceiling_usd:g}"
                )
            self._reserved += session_max_usd
            try:
                session = await client.run(text, schema=schema)
            finally:
                self._reserved -= session_max_usd
        if not session.cached:
            self.spent_usd += session.list_cost_usd
        return session


def _log(sessions: pathlib.Path, line: str) -> None:
    print(line, file=sys.stderr)
    with sessions.with_suffix(".log").open("a", encoding="utf-8") as log:
        log.write(line + "\n")


def _record(sessions: pathlib.Path, row: dict[str, Any]) -> None:
    with sessions.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(row, ensure_ascii=False) + "\n")
    _log(sessions, json.dumps({k: row[k] for k in SHOWN if k in row}))


def run_phase(
    plan: list[tuple],
    done: list[dict[str, Any]],
    limits: Limits,
    session: Session,
    sessions: pathlib.Path,
    warmup_task: Task | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Run what the plan still lacks; (exit code, every row). The caller's list is not changed."""
    rows = list(done)
    seen = {(r["task"], r["run"], r["arm"]) for r in rows if not r.get("not_run")}
    todo = [p for p in plan if (p[1][0], p[2], p[3]) not in seen]
    if not todo:
        return 0, rows
    steps = [(0, warmup_task, next_warmup_run(rows), "PLAIN")] if warmup_task else []
    for index, task, run, arm in steps + todo:
        reason = stop_reason(rows, limits, index)
        if reason:
            _log(sessions, reason)
            return 1, rows
        row = session(task, run, arm)
        if usage_limited(row):  # NOT RUN: recorded as such, run again on a resume
            row = {**row, "not_run": True}
            rows = [*rows, row]
            _record(sessions, row)
            _log(sessions, "usage limit: the subscription refused the session; stopped")
            return 2, rows
        rows = [*rows, row]
        _record(sessions, row)
    return 0, rows
