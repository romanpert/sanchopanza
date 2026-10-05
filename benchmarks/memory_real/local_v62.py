"""Amendment 6, part B: v6.2 (the shell touch on writes only) against v5 on the maintainer's
sessions started in [SINCE, UNTIL), locally (the touch calls no model; the repository gets
counts only; commands for the audit stay in the cache).

    python benchmarks/memory_real/local_v62.py --count          # targets, no label read
    python benchmarks/memory_real/local_v62.py --build          # once, after BUILD_AFTER
    python benchmarks/memory_real/local_v62.py --score          # once; also writes AUDIT, a
                                                                # seeded sample of the shell gives

Targets: every session of a project folder (local.EXCLUDE out) whose first stamp is in
[SINCE, UNTIL), not the first of its folder, with up to five sessions before it as its pool;
items as local_v6.py builds them (Bash and PowerShell kept, PowerShell replayed as such).
"""

from __future__ import annotations

import argparse
import functools
import json
import random
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
import build_v4b  # noqa: E402
import build_v6  # noqa: E402
import local_v6 as lv  # noqa: E402
import replay_v6 as rv  # noqa: E402
from score import OUT, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402
from variants_v62 import with_shell_label  # noqa: E402

from sanchopanza.harness import memory_hook as mh  # noqa: E402

SINCE = datetime.fromisoformat("2026-10-01T12:00:00+02:00").timestamp()
UNTIL = datetime.fromisoformat("2026-10-04T00:00:00+02:00").timestamp()
BUILD_AFTER = datetime.fromisoformat("2026-10-04T06:00:00+02:00").timestamp()
ITEMS = build.CACHE / "items-v62-local.jsonl"
AUDIT = build.CACHE / "audit-v62-local.jsonl"
SAMPLE, SEED = 60, 20261004


def targets() -> list[dict[str, Any]]:
    out = []
    for name, sessions in lv.folders(UNTIL):
        for t, target in enumerate(sessions):
            if t and lv.stamp(target) >= SINCE:
                out.append({"folder": name, "target": target,
                            "window": sessions[max(0, t - lv.POOL_SESSIONS) : t + 1]})  # fmt: skip
    return out


def build_items() -> dict[str, Any]:
    if time.time() < BUILD_AFTER:
        raise SystemExit("amendment 6: the local items are built after 2026-10-04 06:00")
    chosen, n = targets(), 0
    ids = {name: g for g, name in enumerate(sorted({c["folder"] for c in chosen}))}
    cache = Path(tempfile.mkdtemp())
    folder, build.CACHE = build.CACHE, cache
    try:
        (cache / "transcripts").mkdir()
        build_v4b.views = build_v6.views
        build_v4b.session = functools.cache(build_v4b.session)
        with ITEMS.open("w", encoding="utf-8", newline="\n") as handle:
            for c in chosen:
                for path in c["window"]:
                    if not (cache / "transcripts" / path.name).exists():
                        shutil.copyfile(path, cache / "transcripts" / path.name)
                target = c["target"].stem
                for item in build_v4b.items_for([p.stem for p in c["window"]], ids[c["folder"]],
                                                "local"):  # fmt: skip
                    if item["session"] == target:
                        row = {**item, "cwd": build_v6.cwd_of(target)}
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                        n += 1
    finally:
        build.CACHE = folder
        shutil.rmtree(cache, ignore_errors=True)
    return {"folders": len(ids), "targets": len(chosen), "requests": n}


def _replay(items: list[dict[str, Any]], shell: bool) -> tuple[Any, Any, list[dict[str, Any]]]:
    """(shown per item, characters, every record a shell call gave with its command)."""
    as_bash = rv.bash_event
    gives: list[dict[str, Any]] = []
    original = mh.touch

    def touch(event: Any) -> Any:
        out = original(event)
        if out and event.get("tool_name") in mh.SHELL_TOOLS:
            gives.append({"command": event["tool_input"]["command"][:1500],
                          "context": out["hookSpecificOutput"]["additionalContext"]})  # fmt: skip
        return out

    rv.bash_event = lambda item, transcript, touch: {
        **as_bash(item, transcript, touch),
        "tool_name": touch.get("shell", "Bash"),
    }
    rv.mh.touch = touch
    try:
        with tempfile.TemporaryDirectory() as tmp:
            shown, chars, _ = rv.touch_replay(items, Path(tmp), shell)
    finally:
        rv.bash_event, rv.mh.touch = as_bash, original
    return shown, chars, gives


def score() -> dict[str, Any]:
    items = load(ITEMS)
    plus = with_shell_label(items)
    result: dict[str, Any] = {"requests": len(items),
                              "sessions": len({it["session"] for it in items})}  # fmt: skip
    gives: list[dict[str, Any]] = []
    for arm, shell in (("v5", False), ("v6.2", True)):
        shown, chars, given = _replay(items, shell)
        result[arm] = {"sealed": metrics(items, shown), "+shell": metrics(plus, shown),
                       "chars_per_request": round(sum(chars.values()) / max(1, len(items))),
                       "given_by_shell": len(given)}  # fmt: skip
        gives = given if shell else gives
    with AUDIT.open("w", encoding="utf-8", newline="\n") as handle:
        for g in random.Random(SEED).sample(gives, min(SAMPLE, len(gives))):
            row = {"command": g["command"], "file": g["context"].split("\n")[0][:300]}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (OUT / "local-v62.json").write_text(json.dumps(result, indent=1), encoding="utf-8",
                                        newline="\n")  # fmt: skip
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args(argv)
    if args.count:
        print(len(targets()), "target sessions")
    if args.build:
        print(json.dumps(build_items()))
    if args.score:
        print(json.dumps(score(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
