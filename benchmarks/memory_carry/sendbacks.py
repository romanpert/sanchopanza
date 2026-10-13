"""Every send-back the audit made in a carry run, from each V or S pair's hook log: which session,
which rule, and whether it was the scene's own rule or another (a decoy). Criterion 2 of
`prereg-v8.md` counts second sessions sent back by a rule other than the scene's own. For F1's
family ii the scene's older rule A (`stale`) is not its own: a send-back quoting it is false,
labelled STALE.

    python benchmarks/memory_carry/sendbacks.py RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from carry import ALL_RULES, STALE_OLD  # noqa: E402


def sendbacks(pair: Path) -> list[dict[str, object]]:
    """(session number, rule text, own) for every rule a Stop sent back, in order."""
    scene = pair.name.split("-")[0]
    session, out = 0, []
    log = pair / "hook-log.jsonl"
    if not log.exists():
        return []
    for line in log.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("event") == "SessionStart" and row.get("source") == "startup":
            session += 1
        if row.get("event") == "rules":
            for text in row.get("broken") or []:
                # the scene's fact inside a longer sentence is still its own rule: v8.1's splitter
                # keeps `columns`' lead-in "For context: ...", and equality called it a decoy
                old = STALE_OLD.get(scene)
                out.append({"session": session, "rule": text, "own": ALL_RULES[scene] in text,
                            "stale": bool(old) and old in text})  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    runs = [Path(a) for a in (argv or sys.argv[1:])]
    pairs = [p for r in runs for arm in ("V", "S") for p in sorted(r.glob(f"*-{arm}-*"))
             if p.is_dir()]  # fmt: skip
    false_second = 0
    for pair in pairs:
        found = sendbacks(pair)
        lures = [f for f in found if not f["own"] and f["session"] >= 2]
        false_second += bool(lures)
        for f in found:
            kind = "own " if f["own"] else "STALE" if f.get("stale") else "DECOY"
            print(f"{pair.parent.name}/{pair.name} s{f['session']} {kind} {str(f['rule'])[:90]}")
    print(f"V and S pairs {len(pairs)}; later sessions sent back by a decoy or a stale rule: "
          f"{false_second}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
