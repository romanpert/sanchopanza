"""Seal a pre-registration: hash the document and the code it names, before any data.

    python benchmarks/candor/seal.py prereg-3
    python benchmarks/candor/seal.py prereg --out docs/results/2026-09-29-find \
        --code "benchmarks/find/*.py" "src/sanchopanza/select.py" "src/sanchopanza/context/*.py"

Writes `<name>.manifest.json` (path -> sha256, LF line endings, the document first) and
`<name>.sha256`, the sha256 of the lines `"<path> <hash>\\n"` in manifest order. That is how
prereg-2 was sealed, and `tests/test_candor_bench.py` checks it the same way. Without `--out`
and `--code` it seals a candor round: the candor results folder, the bench and the rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "results" / "2026-09-29-candor"
CANDOR_CODE = (
    "benchmarks/candor/*.py",
    "src/sanchopanza/candor/*.py",
    "src/sanchopanza/harness/candor_hook.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def seal(name: str, out: Path, patterns: tuple[str, ...]) -> str:
    doc = out / f"{name}.md"
    code = sorted({p for pattern in patterns for p in REPO.glob(pattern) if p.is_file()})
    manifest = {doc.relative_to(REPO).as_posix(): digest(doc)}
    manifest |= {p.relative_to(REPO).as_posix(): digest(p) for p in code}
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    (out / f"{name}.manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (out / f"{name}.sha256").write_text(combined.hexdigest() + "\n", encoding="utf-8")
    return f"{name}: {len(manifest)} files, {combined.hexdigest()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="?", default="prereg-3")
    parser.add_argument("--out", default="")
    parser.add_argument("--code", nargs="*", default=list(CANDOR_CODE))
    args = parser.parse_args(argv)
    out = (REPO / args.out) if args.out else OUT
    print(seal(args.name, out, tuple(args.code)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
