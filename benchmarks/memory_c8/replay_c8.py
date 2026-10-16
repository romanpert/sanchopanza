"""Memory's C8 figures, free and replayed (docs/results/2026-10-16-memory-c8-replay).

    python benchmarks/memory_c8/replay_c8.py --f2-root <F2 run root> \
        [--items <items-memgate-hook.jsonl>] [--own-rules <rules file>] [--out <json>]

Three parts, each run only when its input is given or found, none calling a model:
- `f2_replay`: F2's S arms, the night's logged decisions replayed through the shipped code;
- `swechat`: SWE-chat's 909 first prompts (lot memgate-hook's items, local cache);
- `own_rules`: standing rules stored from the owner's real sessions, counts only.
Paths come from the arguments or the environment (SANCHOPANZA_F2_ROOT, SANCHOPANZA_C8_ITEMS,
SANCHOPANZA_C8_OWN_RULES); the output names no local path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import f2_replay  # noqa: E402
import own_rules  # noqa: E402
import swechat  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-10-16-memory-c8-replay" / "replay.json"


def _path(given: str | None, env: str, default: Path | None = None) -> Path | None:
    raw = given or os.environ.get(env, "")
    path = Path(raw) if raw else default
    return path if path is not None and path.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--f2-root")
    parser.add_argument("--items")
    parser.add_argument("--own-rules")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    f2 = _path(args.f2_root, "SANCHOPANZA_F2_ROOT")
    items = _path(args.items, "SANCHOPANZA_C8_ITEMS", swechat.ITEMS)
    rules = _path(args.own_rules, "SANCHOPANZA_C8_OWN_RULES")
    result: dict[str, Any] = {
        "live_calls": 0,
        "f2": f2_replay.run(f2) if f2 else "not run: no F2 run root",
        "swechat": swechat.run(items) if items else "not run: no items file",
        "own_rules": own_rules.run(rules) if rules else "not run: no rules file",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=1, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(brief(result), indent=1, ensure_ascii=False))
    return 0


def brief(result: dict[str, Any]) -> dict[str, Any]:
    """The result without F2's per-arm rows."""
    f2 = result["f2"]
    if isinstance(f2, str):
        return result
    runs = {name: run["summary"] for name, run in f2["runs"].items()}
    return {**result, "f2": {**f2, "runs": runs}}


if __name__ == "__main__":
    raise SystemExit(main())
