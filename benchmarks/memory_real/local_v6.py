"""v6.1's shell touch on the maintainer's own Claude Code sessions that no pass has scored,
locally: no text leaves the machine (the touch calls no model), items stay in the cache and the
repository gets counts only.

    python benchmarks/memory_real/local_v6.py --check-v3      # the v3 pass's windows, rebuilt
    python benchmarks/memory_real/local_v6.py --build         # items of the fresh sessions
    python benchmarks/memory_real/local_v6.py --score         # v5 against v6.1, once

The only earlier local pass (`local.py`, 1a4963c, 2026-09-30 21:03) scored, per project folder,
the sessions after the first of one seeded window of six. `--check-v3` rebuilds those windows
from the sessions that existed then and counts their requests, scoring nothing: it gives the
13 groups that pass published but 202 requests against its 197, with that commit's code too and
no session grown or created since, so the windows may not be exactly those (amendment 5
declares it). Fresh targets are every other
session of a folder that started before END, each with the up to five sessions before it as
its pool, built as build_v6.py builds SWE-chat's items (Bash and PowerShell calls kept).
"""

from __future__ import annotations

import argparse
import functools
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build  # noqa: E402
import build_v4b  # noqa: E402
import build_v6  # noqa: E402
import local  # noqa: E402
import replay_v6 as rv  # noqa: E402
from score import OUT, metrics  # noqa: E402
from variants_v4b import load  # noqa: E402

CUT = datetime.fromisoformat("2026-09-30T21:03:31+02:00").timestamp()  # the v3 local pass
END = datetime.fromisoformat("2026-10-01T12:00:00+02:00").timestamp()  # before v6.1's design
POOL_SESSIONS = local.WINDOW - 1
ITEMS = build.CACHE / "items-v61-local.jsonl"
SELECTION = build.CACHE / "selection-v61-local.json"


@functools.cache
def stamp(path: Path) -> float:
    return local.first_stamp(path)


def folders(before: float) -> list[tuple[str, list[Path]]]:
    """Project folders (local.EXCLUDE out) with their sessions started before `before`, oldest
    first, as local.choose read them."""
    out = []
    for folder in sorted(local.PROJECTS.iterdir()):
        if not folder.is_dir() or any(x in folder.name for x in local.EXCLUDE):
            continue
        sessions = sorted((p for p in folder.glob("*.jsonl") if stamp(p) < before), key=stamp)
        out.append((folder.name, sessions))
    return out


def v3_windows() -> list[tuple[str, list[Path]]]:
    """local.choose() over the sessions that existed when it ran."""
    rng = random_for_v3()
    groups = [(n, s) for n, s in folders(CUT) if len(s) >= 3]
    rng.shuffle(groups)
    out = []
    for name, sessions in groups[: local.GROUPS]:
        width = min(local.WINDOW, len(sessions))
        start = rng.randrange(0, len(sessions) - width + 1)
        out.append((name, sessions[start : start + width]))
    return out


def random_for_v3() -> Any:
    import random

    return random.Random(local.SEED)


def check_v3() -> dict[str, int]:
    """The v3 pass's group and request counts from the rebuilt windows (no label is read)."""
    cache = Path(tempfile.mkdtemp())
    requests = groups = 0
    try:
        folder, build.CACHE = build.CACHE, cache
        (cache / "transcripts").mkdir()
        for _, sessions in v3_windows():
            groups += 1
            for path in sessions:
                shutil.copyfile(path, cache / "transcripts" / path.name)
            parts = [build.session_parts(p.stem) for p in sessions]
            for position in range(1, len(parts)):
                earlier = [p for p in parts[:position] if p]
                if parts[position] is not None and any(p["records"] for p in earlier):
                    requests += len(parts[position]["requests"])
        build.CACHE = folder
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    return {"groups": groups, "requests": requests}


def fresh() -> list[dict[str, Any]]:
    """Per folder, the sessions no pass scored: (folder, target, its pool sessions)."""
    scored = {p for _, window in v3_windows() for p in window[1:]}
    out = []
    for name, sessions in folders(END):
        for t, target in enumerate(sessions):
            if t == 0 or target in scored:
                continue
            out.append({"folder": name, "target": target,
                        "window": sessions[max(0, t - POOL_SESSIONS) : t + 1]})  # fmt: skip
    return out


def build_items() -> dict[str, Any]:
    """Items of the fresh targets to the cache, each with the folder its session started in;
    the selection (folder, session, first stamp) beside them."""
    chosen = fresh()
    cache = Path(tempfile.mkdtemp())
    n = 0
    folder_ids = {name: g for g, name in enumerate(sorted({c["folder"] for c in chosen}))}
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
                sids = [p.stem for p in c["window"]]
                for item in build_v4b.items_for(sids, folder_ids[c["folder"]], "local"):
                    if item["session"] == target:
                        row = {**item, "cwd": build_v6.cwd_of(target), "stamp": stamp(c["target"])}
                        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                        n += 1
    finally:
        build.CACHE = folder
        shutil.rmtree(cache, ignore_errors=True)
    summary = {"folders": len(folder_ids), "targets": len(chosen), "requests": n}
    targets = [[c["folder"], c["target"].stem, stamp(c["target"])] for c in chosen]
    SELECTION.write_text(json.dumps({**summary, "targets": targets}, indent=1), encoding="utf-8")
    return summary


def _row(items: list[dict[str, Any]], bash: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        shown, chars, by_tool = rv.touch_replay(items, Path(tmp), bash)
    m = metrics(items, shown)
    via = [(n, k) for n, d in by_tool.items() for k, t in d.items() if t == "Bash"]
    good = sum(items[n]["labels"][k] != "none" for n, k in via)
    return {**m, "chars_per_request": round(sum(chars.values()) / max(1, len(items))),
            "given_by_shell": len(via), "related_given_by_shell": good}  # fmt: skip


def score() -> dict[str, Any]:
    """v5's touch (file tools) against v6.1's (file tools and shell), on all fresh items and on
    those of sessions started after the v3 pass. Counts only, to the repository. A PowerShell
    call is replayed as PowerShell (its escape is a backtick)."""
    as_bash = rv.bash_event
    rv.bash_event = lambda item, transcript, touch: {
        **as_bash(item, transcript, touch),
        "tool_name": touch.get("shell", "Bash"),
    }
    items = load(ITEMS)
    after = [it for it in items if it["stamp"] >= CUT]
    shell_calls = [t.get("shell", "Bash") for it in items for t in it["touches"] if "command" in t]
    result: dict[str, Any] = {
        "requests": len(items),
        "sessions": len({it["session"] for it in items}),
        "shell_calls": {k: shell_calls.count(k) for k in sorted(set(shell_calls))},
    }
    for name, subset in (("all", items), ("after_v3_pass", after)):
        result[name] = {"requests": len(subset), "v5": _row(subset, False),
                        "v6.1": _row(subset, True)}  # fmt: skip
    (OUT / "local-v61.json").write_text(json.dumps(result, indent=1), encoding="utf-8",
                                        newline="\n")  # fmt: skip
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-v3", action="store_true")
    parser.add_argument("--count", action="store_true", help="fresh targets per folder only")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--score", action="store_true", help="v5 against v6.1, once")
    args = parser.parse_args(argv)
    if args.check_v3:
        print(json.dumps(check_v3()))
    if args.count:
        chosen = fresh()
        per: dict[str, int] = {}
        for c in chosen:
            per[c["folder"]] = per.get(c["folder"], 0) + 1
        print(len(chosen), "targets in", len(per), "folders")
    if args.build:
        print(json.dumps(build_items()))
    if args.score:
        print(json.dumps(score(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
