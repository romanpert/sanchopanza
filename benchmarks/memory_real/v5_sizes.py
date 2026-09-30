"""v5, item 2: what the characters of a record are made of (request, report, paths, command
output), over the records of every pool. Free, local; prints numbers only.

    python benchmarks/memory_real/v5_sizes.py --items CACHE/items-v4b.jsonl
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from score import CACHE  # noqa: E402
from variants_v4b import load  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", default=str(CACHE / "items-v4b.jsonl"))
    args = parser.parse_args(argv)
    seen: dict[str, dict[str, int]] = {}
    for item in load(Path(args.items)):
        for e in item["pool"]:
            if e.key in seen:
                continue
            seen[e.key] = {
                "total": len(e.text()), "request": len(e.request), "report": len(e.report),
                "changed": sum(len(p) for p in e.changed), "read": sum(len(p) for p in e.read),
                "facts": sum(len(f) for f in e.facts), "tests": len(e.tests or ""),
            }  # fmt: skip
    rows = list(seen.values())
    total = sum(r["total"] for r in rows)
    median = statistics.median(r['total'] for r in rows)
    print(f"{len(rows)} records, {total} characters, median {median}")
    for part in ("request", "report", "changed", "read", "facts", "tests"):
        values = [r[part] for r in rows]
        print(f"{part:8} share {sum(values) / total:.1%}  median {statistics.median(values):>6}"
              f"  p90 {sorted(values)[int(len(values) * 0.9)]:>6}  max {max(values)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
