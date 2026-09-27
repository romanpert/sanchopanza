"""The money guards shared by every lateral run of 2026-09-28.

Two totals, both hard: Jev at most `JEV_TOTAL_USD` across every `fixtures/lateral-*.jsonl`
recording, and the Claude Code CLI at most `CLI_TOTAL_USD` at list price across every
`fixtures/cli/lateral-*.jsonl` session cache. A live run declares the most it can spend
(its own caps) and is refused before its first call if that could carry a total past its bar.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
JEV_TOTAL_USD = 1.00
CLI_TOTAL_USD = 5.00


def jev_spent() -> float:
    total = 0.0
    for path in sorted(FIXTURES.glob("lateral-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                total += float(json.loads(line).get("cost_usd") or 0.0)
    return total


def cli_spent() -> float:
    total = 0.0
    for path in sorted((FIXTURES / "cli").glob("lateral-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.replace(chr(0), "").strip()
            if line:
                total += float(json.loads(line)["session"].get("list_cost_usd") or 0.0)
    return total


def require_jev_room(most: float) -> None:
    spent = jev_spent()
    if spent + most > JEV_TOTAL_USD + 1e-9:
        raise SystemExit(
            f"Jev: {spent:.4f} USD already recorded + up to {most:.2f} here would pass "
            f"{JEV_TOTAL_USD:.2f}: nothing spent"
        )


def require_cli_room(most: float) -> None:
    spent = cli_spent()
    if spent + most > CLI_TOTAL_USD + 1e-9:
        raise SystemExit(
            f"CLI: {spent:.4f} USD already spent + up to {most:.2f} here would pass "
            f"{CLI_TOTAL_USD:.2f}: nothing spent"
        )


def write_hash(target: pathlib.Path, value: str) -> None:
    """Register a hash once; a different one already there is refused, never overwritten."""
    if target.exists() and target.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit(f"{target.name} already holds a different hash: nothing written")
    target.write_text(value + "\n", encoding="utf-8")
