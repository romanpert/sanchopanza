"""v5, item 5: how large real sessions' context gets and how often they compact. Numbers only,
read locally from transcripts (SWE-chat cache, or a folder of Claude Code projects). Free.

    python benchmarks/memory_real/v5_context.py [--root DIR]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score import CACHE  # noqa: E402

BUCKETS = (50_000, 100_000, 150_000, 200_000, 300_000, 500_000)


def session(path: Path) -> dict[str, Any] | None:
    peak = compactions = requests = 0
    models: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
            compactions += 1
        message = e.get("message") if isinstance(e.get("message"), dict) else {}
        if e.get("type") == "user" and isinstance(message.get("content"), str):
            requests += 1
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
        if e.get("type") == "assistant" and usage:
            models.add(str(message.get("model") or ""))
            size = sum(int(usage.get(k) or 0) for k in (
                "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            peak = max(peak, size)
    if not peak:
        return None
    return {"peak": peak, "compactions": compactions, "requests": requests,
            "one_m": any("1m" in m for m in models)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(CACHE / "transcripts"))
    args = parser.parse_args(argv)
    rows = [r for p in Path(args.root).rglob("*.jsonl") if (r := session(p))]
    if not rows:
        raise SystemExit("no session with usage found")
    peaks = sorted(r["peak"] for r in rows)
    print(f"{len(rows)} sessions; peak context median {statistics.median(peaks):,.0f}, "
          f"p90 {peaks[int(len(peaks) * 0.9)]:,}, max {peaks[-1]:,}")
    for b in BUCKETS:
        print(f"  peak >= {b:>7,}: {sum(p >= b for p in peaks) / len(peaks):6.1%}")
    compacted = [r for r in rows if r["compactions"]]
    print(f"sessions with a compaction: {len(compacted)} ({len(compacted) / len(rows):.1%}); "
          f"compactions {sum(r['compactions'] for r in rows)}")
    print(f"requests per session median {statistics.median(r['requests'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
