"""v5 of the rules on rounds 1-4, in sample: every v5 change was shaped on round-4 sessions read
by hand, so these numbers are not a result. They check that v5 does what it was built for, what
it costs in honest sessions, and how many doubts the frontier would send to a judge.

    CANDOR_SRC=<dir> python benchmarks/candor/explore_v5.py dump OUT.json  # rules in <dir>
    python benchmarks/candor/explore_v5.py compare V4.json V5.json

Run `dump` once with CANDOR_SRC set to the v4 source (`git archive <v4> src`) and once with
the working tree, then `compare`. Free: no model is called; raw runs are local.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# `monitors` puts the working tree's src first; CANDOR_SRC loads another version before it, so
# that version is the one cached in sys.modules for every later import.
if os.environ.get("CANDOR_SRC"):
    sys.path.insert(0, os.environ["CANDOR_SRC"])
    importlib.import_module("sanchopanza.candor.rules")
    importlib.import_module("sanchopanza.candor.judge")
sys.path.insert(0, str(HERE))
ROUNDS = ("1", "2", "3", "4")


def _round_items(name: str) -> list[dict[str, Any]]:
    os.environ["CANDOR_ROUND"] = name
    import rounds

    importlib.reload(rounds)
    import monitors

    importlib.reload(monitors)
    stored = {}
    scored = rounds.path("scored.jsonl")
    if scored.exists():
        for line in scored.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                stored[row["id"]] = row
    out = []
    for item in monitors.items():
        if item["id"] not in stored:
            continue
        s = stored[item["id"]]
        out.append({**item, "positive": bool(s["positive"]), "round": name})
    return out


def _verdict(item: dict[str, Any]) -> dict[str, Any]:
    import monitors

    from sanchopanza.candor import rules as rules_mod

    turn = monitors.turn_of(item, block=True, snapshot=True)
    report = rules_mod.check(turn)
    found = [f.to_dict() for f in report.findings]
    ranks = {"critical": 3, "high": 2, "medium": 1}
    worst = max((ranks[f["severity"]] for f in found), default=0)
    try:  # v5 moved the frontier out of rules; older sources have neither
        from sanchopanza.candor.frontier import doubts
    except ImportError:
        doubts = getattr(rules_mod, "doubts", None)
    raised = (
        [{"kind": d.kind, "subject": d.subject} for d in doubts(turn, report)] if doubts else []
    )
    return {
        "critical": worst >= 3,
        "high": worst >= 2,
        "rules": sorted({f"{f['severity']}:{f['rule']}" for f in found}),
        "doubts": raised,
    }


def dump(path: Path) -> int:
    rows = []
    for name in ROUNDS:
        for item in _round_items(name):
            rows.append({"id": item["id"], "round": name, "set": item["set"],
                         "positive": item["positive"], "task": item.get("task", ""),
                         **_verdict(item)})  # fmt: skip
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    sys.stdout.write(f"{len(rows)} items -> {path}\n")
    return 0


def _cells(rows: list[dict[str, Any]], arm: str) -> dict[str, dict[str, int]]:
    out: dict[str, Counter[str]] = {}
    for r in rows:
        group = f"r{r['round']}:{r['set']}:{'pos' if r['positive'] else 'neg'}"
        cell = out.setdefault(group, Counter())
        cell["n"] += 1
        cell[f"{arm}_critical"] += r["critical"]
        cell[f"{arm}_high"] += r["high"]
    return {g: dict(c) for g, c in sorted(out.items())}


def compare(old_path: Path, new_path: Path) -> int:
    old = {(r["round"], r["id"]): r for r in json.loads(old_path.read_text(encoding="utf-8"))}
    new = json.loads(new_path.read_text(encoding="utf-8"))
    table: dict[str, dict[str, int]] = {}
    for arm, rows in (("v4", list(old.values())), ("v5", new)):
        for group, cell in _cells(rows, arm).items():
            table.setdefault(group, {}).update(cell)
    changed = []
    for r in new:
        o = old.get((r["round"], r["id"]))
        if o and (
            o["critical"] != r["critical"] or o["high"] != r["high"] or o["rules"] != r["rules"]
        ):
            changed.append({"round": r["round"], "id": r["id"], "positive": r["positive"],
                            "v4": o["rules"], "v5": r["rules"]})  # fmt: skip
    doubted = [r for r in new if r["doubts"]]
    kinds = Counter(d["kind"] for r in new for d in r["doubts"])
    summary = {
        "table": table,
        "changed": changed,
        "doubts": {
            "items": len(doubted),
            "questions": sum(kinds.values()),
            "by_kind": dict(kinds),
            "positives": sum(r["positive"] for r in doubted),
        },  # fmt: skip
    }
    sys.stdout.write(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "dump":
        return dump(Path(argv[1]))
    if len(argv) >= 3 and argv[0] == "compare":
        return compare(Path(argv[1]), Path(argv[2]))
    sys.stderr.write(__doc__ or "")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
