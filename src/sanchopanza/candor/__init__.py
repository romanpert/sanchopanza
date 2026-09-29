"""Candor: hold what an agent says against what it did, and stop it for a human when they differ.

Three layers, cheapest first, each usable alone:

1. `ledger` builds the record of actions by rules. No model ever reads raw tool output.
2. `rules` checks the report's claims against that record. Pure code, free, deterministic.
3. `judge` (optional) asks a decision model what single sentences assert. It only adds.

`lock` turns findings into a sticky hold on every tool call that only a human can release.

    from sanchopanza.candor import check_record
    findings = check_record({"said": "...", "did": [{"tool": "Bash", "target": "pytest",
                                                      "ok": False, "result": "1 failed"}]})

What this is and is not, measured in docs/results/2026-09-29-candor/: a check of the
categories it names (false success, denied actions, claimed actions with no trace, sources
never read, consequential actions left out of the report, test edits behind a success claim,
touching the monitor). It is not robust against an agent that sets out to beat it, and it
sees only what the harness records: a side effect of a script the hook never saw is not in
the ledger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .ledger import Action, action, from_audit
from .rules import RANK, Finding, Report, Turn, check

LOCK_ON: dict[str, int] = {"critical": RANK["critical"], "high": RANK["high"]}


def turn_of(record: Mapping[str, Any]) -> Turn:
    """A `Turn` from `{said, did: [{tool, target, ok, result, writes}], task?, changed?}`.
    A record that carries `changed`, even empty, had a snapshot taken, unless `snapshot` says no."""
    did = record.get("did") or ()
    return Turn(
        said=str(record.get("said") or ""),
        did=tuple(from_audit(did if isinstance(did, Sequence) else ())),
        task=str(record.get("task") or ""),
        changed=tuple(str(p) for p in (record.get("changed") or ())),
        snapshot=bool(record.get("snapshot", "changed" in record)),
    )


def check_record(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Findings for one turn as plain dicts, worst first. Pure: no model, no I/O."""
    report = check(turn_of(record))
    ordered = sorted(report.findings, key=lambda f: -RANK[f.severity])
    return [f.to_dict() for f in ordered]


async def judge_record(record: Mapping[str, Any], squire: Any) -> list[dict[str, Any]]:
    """`check_record` plus the model layer through `squire` (its budget and journal apply).
    Without a usable decider it returns exactly what `check_record` returns."""
    from .frontier import frontier
    from .judge import judge

    turn = turn_of(record)
    report = await frontier(squire, turn, await judge(squire, turn, check(turn)))
    ordered = sorted(report.findings, key=lambda f: -RANK[f.severity])
    return [f.to_dict() for f in ordered]


def should_lock(findings: Sequence[Finding | Mapping[str, Any]], *, on: str = "critical") -> bool:
    """True when any finding is at or above `on` ("critical" by default, or "high")."""
    floor = LOCK_ON.get(on, RANK["critical"])
    for f in findings:
        severity = f.severity if isinstance(f, Finding) else str(f.get("severity"))
        if RANK.get(severity, 0) >= floor:
            return True
    return False


__all__ = [
    "Action",
    "Finding",
    "Report",
    "Turn",
    "action",
    "check",
    "check_record",
    "judge_record",
    "should_lock",
    "turn_of",
]
