"""With the v4 touch, what recall at a session's first request adds at each cut. Free: cached
decider answers and the touch replayed through the hook's code.

    python benchmarks/memory_real/prompt_cut_v4.py [--split dev]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_v4 import touch_replay  # noqa: E402
from score import OUT, decider_pass, metrics  # noqa: E402
from variants_v4 import load  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=("dev", "held"))
    args = parser.parse_args(argv)
    items = load(args.split)
    with tempfile.TemporaryDirectory() as tmp:
        touch, _ = touch_replay(items, Path(tmp))
    rows = {"touch only": metrics(items, touch)}
    for cut in (0.7, 0.8, 0.9):
        prompt = asyncio.run(decider_pass(items, 0.0001, cut, 0, True))
        both = {n: list(dict.fromkeys([*touch[n], *prompt[n]])) for n in touch}
        rows[f"touch + first request at {cut}"] = metrics(items, both)
    for name, m in rows.items():
        print(name.ljust(30), " | ".join(
            f"{k}: R {m[k]['recall']} P {m[k]['precision']} N {m[k]['noise']}"
            for k in ("all/any", "all/lineage", "first/any")))
    target = OUT / f"prompt-cut-v4-{args.split}.json"
    target.write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
