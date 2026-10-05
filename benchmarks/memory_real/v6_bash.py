"""v6: how often real sessions read or change files through Bash, where the memory hook (file
tools only) sees nothing. Counts only, from the cached SWE-chat transcripts (or --root). Free.

    python benchmarks/memory_real/v6_bash.py [--root DIR]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402

from sanchopanza.context import episodes as ep  # noqa: E402
from sanchopanza.context.transcript import blocks_of  # noqa: E402

FILE_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
# A shell command that writes a file: in-place editors, redirections into a path with an
# extension, heredocs into python or a file, patch tools.
WRITES = re.compile(
    r"\bsed\s+(-\w*i|--in-place)|\bperl\s+-\w*i|\bawk\s+-i\s+inplace|"
    r"(?<![<>&2])>>?\s*['\"]?[\w./-]+\.\w{1,6}\b|\btee\s+(-a\s+)?[\w./-]+\.\w|"
    r"\bpython[\d.]*\s+-\s*<<|open\([^)]*['\"][wa]b?['\"]|write_text\(|"
    r"\bgit\s+apply\b|\bpatch\s+-p|\bcat\s*>\s*\S"
)
READS = re.compile(r"\b(cat|head|tail|less|more|bat|nl)\s+[^|;&]*[\w-]+\.\w{1,6}\b|"
                   r"\bsed\s+-n\s|\bgrep\s+-\w*n|\brg\s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(build.CACHE / "transcripts"))
    args = parser.parse_args(argv)
    n: Counter[str] = Counter()
    for path in sorted(Path(args.root).rglob("*.jsonl")):
        entries = ep.entries_of(path)
        if not entries:
            continue
        n["sessions"] += 1
        for group in ep.split_requests(entries).groups:
            tools: Counter[str] = Counter()
            writes = reads = 0
            for message in group:
                for b in blocks_of(message):
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    tools[str(b.get("name"))] += 1
                    if b.get("name") == "Bash":
                        command = str((b.get("input") or {}).get("command") or "")
                        writes += bool(WRITES.search(command))
                        reads += bool(READS.search(command))
            if not tools:
                continue
            n["requests with tools"] += 1
            by_tool = bool(FILE_TOOLS & set(tools))
            n["change by file tool"] += by_tool
            n["change by Bash"] += writes > 0
            n["change by Bash only"] += writes > 0 and not by_tool
            n["read by Read tool"] += tools["Read"] > 0
            n["read by Bash"] += reads > 0
            n["read by Bash only"] += reads > 0 and tools["Read"] == 0
    total = n["requests with tools"]
    print(f"{n['sessions']} sessions, {total} requests with a tool call")
    for key in ("change by file tool", "change by Bash", "change by Bash only", "read by Read tool",
                "read by Bash", "read by Bash only"):
        print(f"  {key:22} {n[key]:6}  {n[key] / total:6.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
