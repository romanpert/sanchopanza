"""v2 as it shipped (every prompt, the decider at 0.2), from the cached answers. Free.

Declared correction (2026-10-01): `score.py --select decider` takes the cut from
`memory_hook.KEEP_AT`, which v3 raised to 0.7, so the held-out "v2" pass of amendment 1 ran at
0.7 on every prompt. The decider's probabilities do not depend on the cut and are cached, so v2
at its own cut is recomputed here without a new call; score.py (sealed) is left as it was.

    python benchmarks/memory_real/v2_at_its_cut.py --split held
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score import OUT, decider_pass, load_items, metrics  # noqa: E402

V2_KEEP_AT = 0.2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="held", choices=("dev", "held"))
    args = parser.parse_args(argv)
    items = load_items(args.split)
    # cap 0.0001: every answer must come from the cache; a missing one stops the run
    shown = asyncio.run(decider_pass(items, 0.0001, V2_KEEP_AT))
    m = metrics(items, shown)
    for k in ("all/any", "all/lineage", "first/any"):
        print(k, m[k])
    (OUT / f"v2-at-0.2-{args.split}.json").write_text(json.dumps(m, indent=1),
                                                     encoding="utf-8", newline="\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
