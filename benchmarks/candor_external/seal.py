"""Seal a pre-registration of candor on external data, as `benchmarks/candor/seal.py` does.

    python benchmarks/candor_external/seal.py prereg-errata

The manifest holds this folder's document first, then this folder's code, the candor bench code
it imports, and the candor rules. The `.sha256` is over the lines `"<path> <hash>\\n"`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "benchmarks" / "candor"))

from seal import digest  # noqa: E402

OUT = REPO / "docs" / "results" / "2026-09-29-candor-external"
CODE = sorted(
    [
        *HERE.glob("*.py"),
        *(REPO / "benchmarks" / "candor").glob("*.py"),
        *(REPO / "src" / "sanchopanza" / "candor").glob("*.py"),
    ]
)


def main(argv: list[str]) -> int:
    name = argv[0]
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
