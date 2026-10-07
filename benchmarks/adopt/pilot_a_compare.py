"""The pilot of bet A against the gate's N: `long_compare.py` with arms N, A and A10 (free).

python benchmarks/adopt/pilot_a_compare.py [--gate C:\\sp-runs\\L]
    [--pilot C:\\sp-runs\\L-pilot-a] [--pilot10 C:\\sp-runs\\L-pilot-a10] [--json <out.json>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import long_compare  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", default=r"C:\sp-runs\L")
    parser.add_argument("--pilot", default=r"C:\sp-runs\L-pilot-a")
    parser.add_argument("--pilot10", default=r"C:\sp-runs\L-pilot-a10")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    arms = [f"N={args.gate}:N", f"A={args.pilot}:A", f"A10={args.pilot10}:A10"]
    return long_compare.main(
        [*(f"--arm={a}" for a in arms), *(["--json", args.json] * bool(args.json))]
    )


if __name__ == "__main__":
    sys.exit(main())
