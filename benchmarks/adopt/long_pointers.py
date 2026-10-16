"""The guard-pointers lot's arms and the invariants a call of theirs must keep
(docs/results/2026-10-16-guard-pointers/prereg.md). Read by `long_run.py`; free: nothing here
calls `claude`, an API or Jev.

Arms, both `sanchopanza install --scope project --write` as a user runs it, with no decider key
(the hooks build the null decider; no Jev, no preflight):
- **P**, the default install: after a compaction the guard attaches the requests, the files changed
  and pointers to earlier output, one-shot output archived beside the project
  (`SANCHOPANZA_GUARD_CHOOSER` unset, so `pointers`).
- **F**, the same install with `--guard-full`: the whole earlier results in 6 parts (`struct`).

What stops the run (STOP file), checked on every call of P or F:
- a compaction whose guard did not run, or ran another chooser than its arm's (`guard_breaks`,
  from the guard's own log, `<evidence>/guard.jsonl`, which `hook_env` turns on for these arms);
- a compaction far from where the install's budget puts it, or a context past its window
  (`window_breaks`): the window never took;
- any decision asked of a provider other than the null decider (`keyless_breaks`): a paid call.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

GUARD_ARMS = {"P": ("pointers", ()), "F": ("struct", ("--guard-full",))}
DEFAULT_BUDGET = 160_000  # install_defaults.DEFAULT_BUDGET: what the default install writes
GUARD_LOG = "guard.jsonl"
LOT_ENV = ("ADOPT_GUARD_LOT", "1")  # hook_env.GUARD_LOT_VAR


def install_flags(arm: str, budget: int = DEFAULT_BUDGET) -> tuple[str, ...]:
    """`install` flags of the arm: none for P (the default), `--guard-full` for F; a budget only
    when a profile asks for another than the default (the smoke's, so Haiku compacts early)."""
    _chooser, flags = GUARD_ARMS[arm]
    return (*flags, *(("--context-budget", str(budget)) if budget != DEFAULT_BUDGET else ()))


def bounds(budget: int) -> tuple[tuple[int, int], int]:
    """(where a compaction's `pre` must lie, the most context a call may reach) for a budget.
    Claude Code compacts at the budget (window - 33k); seen on Sonnet at 160k: 159,643-162,755
    (2026-10-13/15); at 67k: 66,253-73,752. A request adds up to ~12k between two checks."""
    return (int(0.75 * budget), budget + 25_000), budget + 33_000 + 10_000


def window_breaks(row: Mapping[str, Any], budget: int = DEFAULT_BUDGET) -> list[str]:
    (low, high), peak_max = bounds(budget)
    out = [
        f"{row.get('arm', '?')} compacted at {c.get('pre')} tokens, outside {low}-{high}"
        for c in row.get("compactions") or []
        if not low <= int(c.get("pre") or 0) <= high
    ]
    peak = int(row.get("peak_context") or 0)
    return [*out, *([f"{row.get('arm', '?')} reached {peak} tokens of context, past {peak_max}"]
                    if peak > peak_max else [])]  # fmt: skip


def guard_rows(evidence: Path, skip: int = 0) -> list[dict[str, Any]]:
    """The guard's log from line `skip` on (`SANCHOPANZA_GUARD_LOG`)."""
    path = evidence / GUARD_LOG
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[skip:]:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def guard_facts(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per PreCompact of the call: chooser, block size, outputs archived, parts."""
    keep = ("chooser", "block_chars", "archived", "parts", "part_chars", "candidates", "trigger")
    return [{k: r.get(k) for k in keep if k in r} for r in rows if r.get("event") == "PreCompact"]


def guard_breaks(arm: str, row: Mapping[str, Any]) -> list[str]:
    """A compaction without its arm's guard: not the registered treatment."""
    compactions = len(row.get("compactions") or [])
    built = row.get("guard") or []
    want = GUARD_ARMS[arm][0]
    out = [f"{arm}: {compactions} compaction(s) and {len(built)} guard block(s) built"
           ] if compactions > len(built) else []  # fmt: skip
    return [
        *out,
        *(
            f"{arm}: the guard ran chooser {g.get('chooser')!r}, not {want!r}"
            for g in built
            if not str(g.get("chooser") or "").startswith(want)
        ),
    ]


def keyless_breaks(decisions: Sequence[Mapping[str, Any]]) -> list[str]:
    """A decision a provider answered in a keyless arm: a paid call nobody approved."""
    paid = [d for d in decisions if d.get("provider") not in (None, "null")]
    return [f"{len(paid)} decision(s) asked of {sorted({str(d.get('provider')) for d in paid})} "
            "in a keyless arm"] if paid else []  # fmt: skip


def deferred_servers(mcp: Path) -> tuple[str, ...]:
    """Servers of an .mcp.json without `alwaysLoad`: Claude Code defers them (`Expect.deferred`)."""
    servers = json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers", {})
    return tuple(name for name, spec in servers.items() if not spec.get("alwaysLoad"))
