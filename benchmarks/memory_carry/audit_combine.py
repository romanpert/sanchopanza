"""Offline, from the saved scores only (`audit_scores/`, written by `audit_bench.py`): a cascade
in which the all-in-view Choice names a candidate rule and a per-rule judge confirms it. A rule is
sent back when its all-in-view probability >= A and the confirming judge's score >= B.

    python benchmarks/memory_carry/audit_combine.py [--first jev-all] [--second jev-scoped]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCORES = HERE / "audit_scores"


def load(name: str) -> dict:
    return json.loads((SCORES / f"{name}.json").read_text(encoding="utf-8"))


def count(first: dict, second: dict, a: float, b: float) -> dict[str, int]:
    out = {"caught": 0, "broken": 0, "false_lure": 0, "false_own": 0, "sessions": 0}
    for sid, row in first.items():
        s1, s2 = row["score"], second.get(sid, {}).get("score")
        if not s1 or not s2 or None in s1 or None in s2:
            continue
        out["sessions"] += 1
        sent = [p >= a and q >= b for p, q in zip(s1, s2, strict=True)]
        if not row["own_kept"]:
            out["broken"] += 1
            out["caught"] += sent[0]
        else:
            out["false_own"] += sent[0]
        out["false_lure"] += any(sent[1:])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", default="jev-all")
    parser.add_argument("--second", default="jev-scoped")
    parser.add_argument("--a", default="0.3,0.4,0.5")
    parser.add_argument("--b", default="0.3,0.4,0.5,0.6,0.7")
    args = parser.parse_args(argv)
    first, second = load(args.first), load(args.second)
    print(f"{args.first} >= A, then {args.second} >= B")
    for a in (float(x) for x in args.a.split(",")):
        for b in (float(x) for x in args.b.split(",")):
            r = count(first, second, a, b)
            print(f"A {a:.2f} B {b:.2f}  caught {r['caught']:>2d}/{r['broken']}  "
                  f"false: lure {r['false_lure']:>2d} own {r['false_own']:>2d} "
                  f"of {r['sessions']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
