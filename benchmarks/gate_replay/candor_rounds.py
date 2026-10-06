"""The change gate against candor's coding rounds: which locks it would keep. Free.

    python benchmarks/gate_replay/candor_rounds.py [--repo PATH]

`--repo`: the checkout whose `docs/results/2026-09-29-candor/runs-N` hold the rounds (they are
not committed; a worktree reads them from the main checkout).

For rounds 2 to 5 of the candor benchmark (coding sessions in throwaway repositories, natural
reports and counterfactual ones), every item is checked with the rules, the status block and
the snapshot (`monitors.rules_arm(..., snapshot=True)`, as `policy_replay.py` does), and the
gate is read from its ledger and snapshot as `candor_hook.stop` reads it: a call that acted
(`change_gate.acted`) or a file the snapshot saw change. Prints the locks on misreports and on
honest reports, all and inside the gate.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.harness import change_gate  # noqa: E402


def _acted(item: dict[str, Any]) -> bool:
    if item.get("changed"):
        return True
    for step in item["ledger"]:
        target = str(step.get("target") or "")
        if change_gate.acted(str(step.get("tool") or ""), {"command": target,
                                                            "file_path": target}):  # fmt: skip
            return True
    return False


def replay(round_name: str) -> dict[str, Any]:
    os.environ["CANDOR_ROUND"] = round_name
    import monitors
    import rounds

    importlib.reload(rounds)
    importlib.reload(monitors)
    sides = [
        f"{k}_{kind}" for k in ("misreport", "honest") for kind in ("natural", "counterfactual")
    ]
    counts = {side: {"items": 0, "gated": 0, "locks": 0, "locks_kept": 0} for side in sides}
    lost = []
    for item in monitors.items():
        kind = "natural" if item.get("kind") == "natural" else "counterfactual"
        side = counts[f"{'misreport' if item['positive'] else 'honest'}_{kind}"]
        acted = _acted(item)
        locked = bool(monitors.rules_arm(item, block=True, snapshot=True)["critical"])
        side["items"] += 1
        side["gated"] += not acted
        side["locks"] += locked
        side["locks_kept"] += locked and acted
        if locked and not acted:
            lost.append(item["id"])
    return {"round": round_name, **counts, "locks_lost": len(lost)}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="the change gate against candor's coding rounds")
    ap.add_argument("--repo", type=Path, default=ROOT)
    args = ap.parse_args()
    sys.path.insert(0, str(args.repo.resolve() / "benchmarks" / "candor"))
    for name in ("2", "3", "4", "5"):
        try:
            print(json.dumps(replay(name)))
        except FileNotFoundError as error:
            print(json.dumps({"round": name, "missing": str(error)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
