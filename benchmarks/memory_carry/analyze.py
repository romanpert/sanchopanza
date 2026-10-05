"""Paired analysis of carry runs: fact kept, tests, task and cost, arm against arm.

Pairs are (scene, model, repeat), pooled over every run folder given (a folder may be a glob,
for a shell that does not expand one; the same pair in two folders is an error). Excluded, and
listed as NOT RUN: a pair where either arm hit the usage limit or a session ended without a
result. A session its own `--max-budget-usd` stopped (`error_max_budget_usd`) counts as run, with
its checks as found (F1, "Exclusions"). A row that records its sessions' `init` is NOT RUN unless
every session ran Claude Code `carry.PIN` on the row's model, and the auth each session used
(`apiKeySource`) is reported. The primary test of every prereg in
`docs/results/2026-10-02-memory-carry/` is a one-sided exact McNemar on `fact_kept`. F1's family
ii also gets the three-way split (newer / stale / neither) per arm.

`--gate`: F1's headroom gate (N only): per family and model, the scenes whose fact the arm broke,
against the rule that a family needs at least `--need` (3) of its 8. A break counts only when the
task was done too (or the scene has no task check), decided 2026-10-05 after review; the count
of every fact not kept is reported beside it. The planned scenes are `carry.SETS[family]`: one
missing, or not run, is listed as NOT RUN, and a family with fewer than 8 run is `incomplete`
unless it already has its breaks.

    python benchmarks/memory_carry/analyze.py RUN_DIR [RUN_DIR ...] --a M --b N [--scenes x,y]
    python benchmarks/memory_carry/analyze.py RUN_DIR [RUN_DIR ...] --gate [--arm N] [--need 3]
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from collections import Counter
from math import comb
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from carry import MODELS, PIN, SETS, session_ran  # noqa: E402

BUDGET_STOP = "error_max_budget_usd"
F1 = ("principle", "stale", "parallel")
# Scene families by name: F1's three, the cross scenes, and the carry scenes before them.
FAMILIES = (("p_", "principle"), ("u_", "stale"), ("q_", "parallel"), ("x_", "cross"))
NEED = 3


def family(scene: str) -> str:
    return next((name for prefix, name in FAMILIES if scene.startswith(prefix)), "carry")


def folders(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        found = sorted(glob.glob(a)) if any(c in a for c in "*?[") else [a]
        out += [Path(f) for f in found if Path(f).is_dir()]
    return out


def rows(dirs: list[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: dict[tuple[Any, ...], str] = {}
    for d in dirs:
        path = d / "carry.json"
        if not path.exists():
            continue
        for r in json.loads(path.read_text(encoding="utf-8")):
            key = (r["scene"], r["model"], r["arm"], r["repeat"])
            if key in seen:
                raise SystemExit(f"{key} is in both {seen[key]} and {d.name}: pooling would mix")
            seen[key] = d.name
            out.append({**r, "run": d.name})
    return out


def finished(session: dict[str, Any], strict: bool) -> bool:
    """A session ran: exit 0, or stopped by its own budget cap. Rows that record the result's
    subtype (F1 on) also need a result: a session that ended without one did not run."""
    if strict:
        return session_ran(session)
    return not session.get("returncode") or session.get("subtype") == BUDGET_STOP


def pinned(row: dict[str, Any], pin: str = PIN) -> bool:
    """Every session that recorded its `init` ran the pinned Claude Code on the row's model."""
    inits = [s.get("init") for s in row.get("sessions") or [] if s.get("init")]
    return all(i.get("version") == pin and i.get("model") == MODELS.get(row["model"])
               for i in inits)  # fmt: skip


def ran(row: dict[str, Any] | None, pin: str = PIN) -> bool:
    if not row or row.get("limit_hit") or row.get("cut") or not row.get("second"):
        return False
    if "sessions" in row:  # F1 rows: every planned session, in order, on the pinned version
        sessions = row["sessions"]
        if any(s.get("init") for s in sessions) and not pinned(row, pin):
            return False
        return len(sessions) == len(row.get("planned") or sessions) and all(
            finished(s, True) for s in sessions)
    return finished(row["first"], False) and finished(row["second"], False)


def auth(found: list[dict[str, Any]]) -> dict[str, int]:
    """How the sessions signed in, from their `init` (`apiKeySource`; `none` is the OAuth login)."""
    return dict(Counter(str((s.get("init") or {}).get("api_key_source")) for r in found
                        for s in r.get("sessions") or [] if s.get("init")))  # fmt: skip


def mcnemar(a_only: int, b_only: int) -> float:
    """One-sided exact p that A keeps the fact more often than B."""
    k = a_only + b_only
    return sum(comb(k, i) for i in range(a_only, k + 1)) / 2**k if k else 1.0


def split(done: list[dict[str, Any]]) -> dict[str, int]:
    """Family ii: which rule the last session followed."""
    out = {"newer": 0, "stale": 0, "neither": 0}
    for r in done:
        if r.get("carried") in out:
            out[r["carried"]] += 1
    return out


def compare(all_rows: list[dict[str, Any]], a: str, b: str,
            scenes: set[str] | None = None) -> dict[str, Any]:  # fmt: skip
    pairs: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = {}
    for r in all_rows:
        if scenes and r["scene"] not in scenes:
            continue
        pairs.setdefault((r["scene"], r["model"], r["repeat"]), {})[r["arm"]] = r
    done = {k: p for k, p in pairs.items() if ran(p.get(a)) and ran(p.get(b))}
    not_run = sorted(k for k, p in pairs.items() if a in p and b in p and k not in done)
    count = {arm: {"fact": 0, "tests": 0, "task": 0, "task_n": 0} for arm in (a, b)}
    a_only = b_only = 0
    ratios = []
    for p in done.values():
        for arm in (a, b):
            r = p[arm]
            count[arm]["fact"] += bool(r["fact_kept"])
            count[arm]["tests"] += bool(r["tests_pass"])
            if r["task_pass"] is not None:
                count[arm]["task"] += bool(r["task_pass"])
                count[arm]["task_n"] += 1
        a_only += bool(p[a]["fact_kept"]) and not p[b]["fact_kept"]
        b_only += bool(p[b]["fact_kept"]) and not p[a]["fact_kept"]
        if p[b]["cost"]:
            ratios.append(p[a]["cost"] / p[b]["cost"])
    out = {"pairs": len(done), "not_run": not_run, "count": count, "a_only": a_only,
           "b_only": b_only, "p": mcnemar(a_only, b_only),
           "cost_ratio": statistics.median(ratios) if ratios else None,
           "broken": {arm: sorted(f"{k[0]} r{k[2]}" for k, p in done.items()
                                  if not p[arm]["fact_kept"]) for arm in (a, b)}}  # fmt: skip
    if any(p[arm].get("stale_kept") is not None for p in done.values() for arm in (a, b)):
        out["stale_split"] = {arm: split([p[arm] for p in done.values()]) for arm in (a, b)}
    out["auth"] = {arm: auth([p[arm] for p in pairs.values() if arm in p]) for arm in (a, b)}
    return out


def broke(row: dict[str, Any]) -> bool:
    """A break the gate counts: the fact not kept, with the task done (or no task check)."""
    return not row["fact_kept"] and row.get("task_pass") is not False


def gate(all_rows: list[dict[str, Any]], arm: str = "N", need: int = NEED,
         pin: str = PIN) -> list[dict[str, Any]]:  # fmt: skip
    """Per family and model: of the planned scenes (`carry.SETS`), those whose fact the arm broke
    with the task done, those not kept at all, and those not run."""
    mine = [r for r in all_rows if r["arm"] == arm]
    families = {family(r["scene"]) for r in mine}
    families |= set(F1) if families & set(F1) else set()
    models = sorted({r["model"] for r in mine})
    cells = [(fam, model) for fam in sorted(families) for model in models]
    return [gate_cell(fam, model, arm, [r for r in mine if family(r["scene"]) == fam
                                        and r["model"] == model], need, pin)
            for fam, model in cells]  # fmt: skip


def _name(row: dict[str, Any]) -> str:
    return f"{row['scene']} r{row['repeat']}"


def gate_cell(fam: str, model: str, arm: str, found: list[dict[str, Any]], need: int,
              pin: str) -> dict[str, Any]:  # fmt: skip
    planned = SETS.get(fam) or sorted({r["scene"] for r in found})
    done = [r for r in found if ran(r, pin)]
    seen = {r["scene"] for r in found}
    counted = sorted(_name(r) for r in done if broke(r))
    not_kept = sorted(_name(r) for r in done if not r["fact_kept"])
    not_run = sorted([_name(r) for r in found if not ran(r, pin)]
                     + [f"{s} (missing)" for s in planned if s not in seen])  # fmt: skip
    verdict = "PASS" if len(counted) >= need else "incomplete" if len(done) < len(planned) \
        else "fail"
    row = {"family": fam, "model": model, "arm": arm, "planned": len(planned), "ran": len(done),
           "broken": len(counted), "not_kept": len(not_kept), "verdict": verdict,
           "pass": verdict == "PASS", "broken_scenes": counted, "not_kept_scenes": not_kept,
           "not_run": not_run, "auth": auth(found),
           "cost": round(sum(float(r.get("cost") or 0.0) for r in found), 3)}  # fmt: skip
    if any(r.get("stale_kept") is not None for r in done):
        row["stale_split"] = split(done)
    return row


def gate_text(table: list[dict[str, Any]], need: int = NEED) -> str:
    lines = [f"headroom gate: a family passes on a model when the arm breaks >= {need} facts "
             "with the task done; fewer than all planned run and no pass: incomplete",
             f"{'family':<10} {'model':<8} {'ran':>5} {'broken':>6} {'not kept':>8} "
             f"{'verdict':<10} {'USD':>7}  broken (task done) / not run"]  # fmt: skip
    for r in table:
        extra = ", ".join(r["broken_scenes"]) or "-"
        extra += f" | NOT RUN: {', '.join(r['not_run'])}" if r["not_run"] else ""
        extra += f" | split {r['stale_split']}" if "stale_split" in r else ""
        extra += f" | auth {r['auth']}" if r["auth"] else ""
        lines.append(f"{r['family']:<10} {r['model']:<8} {r['ran']:>2}/{r['planned']:<2} "
                     f"{r['broken']:>6} {r['not_kept']:>8} {r['verdict']:<10} "
                     f"{r['cost']:>7.2f}  {extra}")  # fmt: skip
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--a")
    parser.add_argument("--b")
    parser.add_argument("--scenes", default="")
    parser.add_argument("--gate", action="store_true", help="F1's headroom gate table")
    parser.add_argument("--arm", default="N", help="the gate's arm")
    parser.add_argument("--need", type=int, default=NEED)
    args = parser.parse_args(argv)
    found = rows(folders(args.runs))
    if args.gate:
        table = gate(found, args.arm, args.need)
        print(gate_text(table, args.need))
        print(json.dumps(table, indent=1))
        return 0
    if not (args.a and args.b):
        parser.error("--a and --b are required without --gate")
    scenes = set(args.scenes.split(",")) if args.scenes else None
    print(json.dumps(compare(found, args.a, args.b, scenes), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
