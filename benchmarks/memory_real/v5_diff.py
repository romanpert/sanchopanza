"""Which first requests v5 and v4.1 treat differently, through the hook, from cached answers
only. Prints ids, labels, probabilities and whether the prompt names the file; no text. Free.

    python benchmarks/memory_real/v5_diff.py --items CACHE/items-v4b.jsonl
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import replay_v5  # noqa: E402
from score import CACHE  # noqa: E402
from variants_v4b import load  # noqa: E402

from sanchopanza.harness import memory_hook as mh  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v4b.jsonl"))
    args = parser.parse_args(argv)
    items = load(Path(args.items))
    arms = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, gate in (("v4.1", "off"), ("v5", "on")):
            os.environ["SANCHOPANZA_MEMORY_PROMPT_NAMED"] = gate
            arms[name] = replay_v5.prompt_replay(items, Path(tmp) / name)
    for n, item in enumerate(items):
        a, b = set(arms["v4.1"][n]), set(arms["v5"][n])
        if a == b:
            continue
        prompt = replay_v5.first_prompt(item["session"], item["request"])
        for key in sorted(a ^ b):
            e = next(x for x in item["pool"] if x.key == key)
            print(f"item {n} {key}: {'v4.1 only' if key in a else 'v5 only'}, label "
                  f"{item['labels'][key]}, changed {len(e.changed)} files, named "
                  f"{mh.named_in(prompt, e)}, prompt {len(prompt)} chars, "
                  f"request label hits {sum(v != 'none' for v in item['labels'].values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
