"""What a session really cost, from Claude Code's result JSON. Written after round 2.

Checked on this run's own files (`t01-orders`, rounds 1 and 2): in `claude -p --resume`, and
in `--resume --fork-session` too, `total_cost_usd` and `modelUsage` are **cumulative over the
whole conversation**, phase A included, while `usage` covers only the API calls of that one
invocation, and **a `/compact` invocation reports `usage` all zero** although its summary call
appears in `modelUsage`. So:

- the cost of one task in one arm is the last call's `total_cost_usd` (phase A, compaction and
  phase B together); summing the three calls counts phase A two or three times;
- the input tokens of one task in one arm are the last call's `modelUsage` input + cache
  creation + cache read; summing `usage` leaves out the native summary call.

Round 1's rows and round 2's first analysis summed the calls. Everything here reads the saved
result JSON files again; nothing is estimated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path.home() / ".cache" / "sanchopanza" / "context-e2e"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    try:
        return json.loads(text.splitlines()[-1]) if text else {}
    except json.JSONDecodeError:
        return {}


def model_input(result: dict[str, Any]) -> int:
    return sum(
        int(v.get(k) or 0)
        for v in (result.get("modelUsage") or {}).values()
        for k in ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
    )


def model_output(result: dict[str, Any]) -> int:
    return sum(int(v.get("outputTokens") or 0) for v in (result.get("modelUsage") or {}).values())


def last_result(folder: Path, names: tuple[str, ...]) -> dict[str, Any]:
    """The last of the named result files that holds a result with a cost."""
    found: dict[str, Any] = {}
    for name in names:
        result = _load(folder / name)
        if result.get("total_cost_usd") is not None:
            found = result
    return found


def split(a: dict[str, Any], compact: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Per-phase figures by difference of the cumulative totals."""

    def usd(r: dict[str, Any]) -> float:
        return float(r.get("total_cost_usd") or 0.0)

    last = b or compact or a
    return {
        "total_usd": round(usd(last), 6),
        "a_usd": round(usd(a), 6),
        "compact_usd": round(usd(compact) - usd(a), 6) if compact else None,
        "b_usd": round(usd(b) - usd(compact or a), 6) if b else None,
        "total_input": model_input(last),
        "a_input": model_input(a),
        "compact_input": model_input(compact) - model_input(a) if compact else None,
        "b_input": model_input(b) - model_input(compact or a) if b else None,
        "total_output": model_output(last),
    }


def round1(task: str, arm: str) -> dict[str, Any]:
    """Arms N/R of round 1 (and N of round 3): phase A shared, compaction on a fork."""
    a = _load(ROOT / "runs" / task / "A" / "result.json")
    folder = ROOT / "runs" / task / arm
    return split(a, _load(folder / "compact.json"), _load(folder / "b.json"))


def round2(task: str) -> dict[str, Any]:
    """Arm A of round 2: one session, no fork."""
    folder = ROOT / "runs-r2" / task / "A"
    return split(_load(folder / "a.json"), _load(folder / "compact.json"), _load(folder / "b.json"))
