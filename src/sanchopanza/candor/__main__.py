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
    release.add_argument(
        "--session", default=None, help="the held session's id (needed when several are held)"
    )
    release.add_argument("--all", action="store_true", help="release every engaged lock")
    checker = sub.add_parser("check", help="check a JSON record {said, did, task?} offline")
    checker.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    if args.command == "status":
        held = lock_mod.engaged_paths()
        if not held:
            print("no lock engaged")
        for path in held:
            state = lock_mod.read(path)
            print(f"{path} (session {state.session or '-'})")
            print(lock_mod.summary(state), end="\n\n")
        return 1 if held else 0
    if args.command == "release":
        return _release(args)
    record = json.loads(args.file.read_text(encoding="utf-8"))
    json.dump(check_record(record), sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


def _release(args: argparse.Namespace) -> int:
    """Release one held lock, or every one with --all. With several held and no --session, it
    names them and releases none: a person picks which session they reviewed."""
    held = lock_mod.engaged_paths()
    if args.session:
        held = [p for p in held if lock_mod.read(p).session == args.session]
    if not held:
        print("no lock engaged" + (f" for session {args.session}" if args.session else ""))
        return 0
    if len(held) > 1 and not args.all:
        print("several sessions are held; pass --session ID or --all:")
        for path in held:
            print(f"  {lock_mod.read(path).session or '-'}  {path}")
        return 2
    for path in held:
        print(lock_mod.summary(lock_mod.read(path)))
        lock_mod.release(by=args.by, why=args.why, path=path)
    print("released")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
