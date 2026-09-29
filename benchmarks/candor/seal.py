"""Seal a candor pre-registration: hash the document and the code it names, before any data.

    python benchmarks/candor/seal.py prereg-3

Writes `<name>.manifest.json` (path -> sha256, LF line endings, the document first) and
`<name>.sha256`, the sha256 of the lines `"<path> <hash>\\n"` in manifest order. That is how
prereg-2 was sealed, and `tests/test_candor_bench.py` checks it the same way.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "results" / "2026-09-29-candor"
CODE = sorted(
    [
        *(p for p in (REPO / "benchmarks" / "candor").glob("*.py")),
        *(REPO / "src" / "sanchopanza" / "candor").glob("*.py"),
        REPO / "src" / "sanchopanza" / "harness" / "candor_hook.py",
    ]
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main(argv: list[str]) -> int:
    name = argv[0] if argv else "prereg-3"
    doc = OUT / f"{name}.md"
    manifest = {doc.relative_to(REPO).as_posix(): digest(doc)}
    manifest |= {p.relative_to(REPO).as_posix(): digest(p) for p in CODE}
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    (OUT / f"{name}.manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (OUT / f"{name}.sha256").write_text(combined.hexdigest() + "\n", encoding="utf-8")
    print(f"{name}: {len(manifest)} files, {combined.hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
