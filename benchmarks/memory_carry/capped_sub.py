"""One `sanchopanza` subcommand with the hook's decider behind a hard dollar cap (W17's lots,
docs/results/2026-10-16-memory-w17/prereg.md).

`carry_hook.py` runs this instead of `python -m sanchopanza <sub>` when the run wrote its Jev cap
beside its key (`carry_hook.CAP_FILE`). It replaces `harness.claude_code.decider_from_env` for this
process only: the decider the environment names, wrapped in `CappedDecider` on the run's
`SpendLedger` (one file shared by every hook process of the run). A call that would not fit is
not made and the squire falls to its default, as with any unavailable decider. Nothing else of
the subcommand changes; without a key (the null decider) nothing is wrapped.

    python capped_sub.py <ledger.jsonl> <cap USD> <subcommand> [args...]
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BATCH = "hooks"


def capped_factory(ledger: Path, cap_usd: float) -> Callable[..., Any]:
    """`decider_from_env` as the harness has it, its decider capped on `ledger`."""
    from sanchopanza.budget import SpendLedger
    from sanchopanza.harness import claude_code
    from sanchopanza.providers.capped import CappedDecider

    real = claude_code.decider_from_env

    def build(env: dict[str, str] | None = None) -> Any:
        inner = real(env)
        if getattr(inner, "name", "null") in ("", "null"):
            return inner
        spend = SpendLedger(ledger, cap_usd=cap_usd)
        return CappedDecider(inner, ledger=spend, batch=BATCH, max_usd=cap_usd)

    return build


def main(argv: list[str]) -> int:
    # The benchmark folder holds modules (rules.py, cell.py...) that must not shadow anything
    # the subcommand imports.
    sys.path[:] = [p for p in sys.path if p and Path(p).resolve() != HERE]
    ledger, cap, rest = Path(argv[0]), float(argv[1]), argv[2:]
    from sanchopanza.harness import claude_code

    claude_code.decider_from_env = capped_factory(ledger, cap)  # type: ignore[assignment]
    from sanchopanza.cli import main as cli

    return cli(rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
