"""`python -m sanchopanza.candor status | release --by NAME --why TEXT | check FILE`.

`release` is for a person at their own terminal. While the lock is engaged the hook refuses
every tool call of the agent, this command included.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import check_record
from . import lock as lock_mod


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sanchopanza.candor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show the lock and what engaged it")
    release = sub.add_parser("release", help="release the lock (a human, with a reason)")
    release.add_argument("--by", required=True)
    release.add_argument("--why", required=True)
    checker = sub.add_parser("check", help="check a JSON record {said, did, task?} offline")
    checker.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    if args.command == "status":
        print(lock_mod.summary(lock_mod.read()))
        return 1 if lock_mod.read().engaged else 0
    if args.command == "release":
        before = lock_mod.read()
        if not before.engaged:
            print("no lock engaged")
            return 0
        print(lock_mod.summary(before))
        lock_mod.release(by=args.by, why=args.why)
        print("released")
        return 0
    record = json.loads(args.file.read_text(encoding="utf-8"))
    json.dump(check_record(record), sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
