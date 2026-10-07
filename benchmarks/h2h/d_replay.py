"""D offline: would a check of the returned documents have caught the answer the agent missed?

BrowseComp-Plus confirmation of 2026-10-06 (`docs/results/2026-10-07-h2h-s2/README.md`): 17
sessions (8 N, 9 S) got a gold document back from a search and still answered wrong. This replay
asks Jev `triage_part` (does this document hold any fact the answer would use; the measured shape
for multi-part questions) about every unique document those sessions saw, and about the documents
of a fixed sample of right sessions and of sessions that never saw a gold document, so a flag can
be read against its false alarms.

    python benchmarks/h2h/d_replay.py --plan              # free: sizes
    python benchmarks/h2h/d_replay.py --live --cap 0.40   # Jev, owner OK 2026-10-07
    python benchmarks/h2h/d_replay.py --report [--out x]  # free

Decisions go to the private cache (`~/.cache/sanchopanza/bcp/h2h/d-replay/`): query id, docid,
labels, probability; never a question, a document or an answer. One decision per (query,
document), shared by the sessions that saw it; a resume skips what is done. The squire's own
budget is the hard cap; three Jev failures in a row stop the run (a 402 fails them all).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import random
import sqlite3
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bcp_data  # noqa: E402
import compare_lines  # noqa: E402
import gaia_arms  # noqa: E402

PHASE = "bcp/h2h/bcp-conf"
RUNS = pathlib.Path("C:/sp-runs/h2h/bcp-conf")
OWN = bcp_data.CACHE / "h2h" / "d-replay"
SEED = 20261007
SAMPLE = {"right_with_gold": 15, "wrong_never": 10}
GATE = 6
STOP_AFTER_FAILURES = 3


def sessions(runs: pathlib.Path = RUNS) -> list[dict[str, Any]]:
    """Every graded BCP conf session with the unique documents its searches returned, in order."""
    gold = bcp_data.read_qrels(bcp_data.QRELS["gold"])
    out = []
    for arm in ("SONNET-CC", "SONNET-SP"):
        for row in compare_lines.rows_of("bcp", PHASE, arm):
            log = runs / pathlib.Path(row["workdir"]).parent.name / "side" / "bcp.jsonl"
            if not log.exists():
                continue
            docs: list[str] = []
            for line in log.read_text(encoding="utf-8").splitlines():
                call = json.loads(line) if line.strip() else {}
                if call.get("tool") == "search":
                    docs += [str(d) for d in call.get("docids") or [] if str(d) not in docs]
            seen = bool(set(gold.get(str(row["task"]), [])) & set(docs))
            group = ("right" if row["ok_final"] else "wrong") + ("_with_gold" if seen else "_never")
            out.append({"task": str(row["task"]), "arm": arm, "group": group, "docs": docs})
    return out


def chosen(all_sessions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """All wrong sessions that saw a gold document, and the fixed samples of the other groups."""
    order = sorted(all_sessions, key=lambda s: (s["task"], s["arm"]))
    picked = [s for s in order if s["group"] == "wrong_with_gold"]
    for group, n in SAMPLE.items():
        pool = sorted((s for s in all_sessions if s["group"] == group),
                      key=lambda s: (s["task"], s["arm"]))  # fmt: skip
        picked += random.Random(f"{SEED}-{group}").sample(pool, min(n, len(pool)))
    return picked


def pairs(picked: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    seen: dict[tuple[str, str], None] = {}
    for s in picked:
        for d in s["docs"]:
            seen.setdefault((s["task"], d), None)
    return list(seen)


def done(path: pathlib.Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {(r["task"], r["docid"]): r for r in rows if not r.get("failed")}


async def run_live(todo: Sequence[tuple[str, str]], cap: float, out: pathlib.Path) -> dict:
    from sanchopanza import Squire
    from sanchopanza.policy import Thresholds
    from sanchopanza.providers import create

    limits = replace(Thresholds(), max_decisions=10_000_000, max_usd=cap)
    squire = Squire(create("jev", api_key=gaia_arms.secret(gaia_arms.JEV_KEY)), thresholds=limits)
    secret = bcp_data.password()
    queries = {q.query_id: bcp_data.decrypt(q.query, secret) for q in bcp_data.load()}
    gold = bcp_data.read_qrels(bcp_data.QRELS["gold"])
    evidence = bcp_data.read_qrels(bcp_data.QRELS["evidence"])
    db = sqlite3.connect(f"file:{bcp_data.DOCS}?mode=ro", uri=True, check_same_thread=False)
    gate, state = asyncio.Semaphore(GATE), {"failures": 0, "stopped": "", "written": 0}
    out.parent.mkdir(parents=True, exist_ok=True)

    async def one(task: str, docid: str) -> None:
        if state["stopped"]:
            return
        async with gate:
            if state["stopped"] or squire.exhausted:
                state["stopped"] = state["stopped"] or "cap"
                return
            found = db.execute("SELECT text FROM docs WHERE docid = ?", (docid,)).fetchone()
            text = found[0] if found else ""
            part = await squire.triage_part(purpose=queries[task], text=text)
        failed = part.reason.startswith("no data")
        state["failures"] = state["failures"] + 1 if failed else 0
        if state["failures"] >= STOP_AFTER_FAILURES:
            state["stopped"] = "jev failures"
        row = {"task": task, "docid": docid, "gold": docid in gold.get(task, []),
               "evidence": docid in evidence.get(task, []), "p": part.probability,
               "keep": part.keep, "failed": failed, "chars": len(text)}  # fmt: skip
        with out.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        state["written"] += 1

    await asyncio.gather(*(one(t, d) for t, d in todo))
    return {
        "written": state["written"],
        "stopped": state["stopped"] or "done",
        "usd": round(squire.meter.cost_usd, 4),
        "decisions": squire.meter.decisions,
    }


def auc(pos: Sequence[float], neg: Sequence[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def report(picked: Sequence[Mapping[str, Any]], decided: Mapping[tuple[str, str], Mapping]) -> dict:
    """Separation of gold from the rest, and per group what a flag at each cut would have done."""
    rows = list(decided.values())
    gold_p = [r["p"] for r in rows if r["gold"]]
    out: dict[str, Any] = {
        "decisions": len(rows),
        "auc_gold_vs_rest": auc(gold_p, [r["p"] for r in rows if not r["gold"]]),
        "auc_gold_vs_not_evidence": auc(gold_p, [r["p"] for r in rows if not r["evidence"]]),
        "groups": {},
    }
    for group in ("wrong_with_gold", "right_with_gold", "wrong_never"):
        mine = [s for s in picked if s["group"] == group]
        cuts = {}
        for cut in (0.5, 0.7, 0.8, 0.9, 0.95):
            caught, flags = 0, []
            for s in mine:
                got = [decided.get((s["task"], d)) for d in s["docs"]]
                got = [g for g in got if g]
                caught += any(g["gold"] and g["p"] >= cut for g in got)
                flags.append(sum(1 for g in got if not g["gold"] and g["p"] >= cut))
            cuts[str(cut)] = {"sessions_gold_flagged": caught,
                              "false_flags_median": statistics.median(flags) if flags else 0,
                              "false_flags_mean": round(statistics.mean(flags), 1) if flags else 0,
                              }  # fmt: skip
        out["groups"][group] = {"sessions": len(mine), "by_cut": cuts}
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    for flag in ("--plan", "--live", "--report"):
        mode.add_argument(flag, action="store_true")
    ap.add_argument("--cap", type=float, default=0.0, help="hard USD cap of the live run")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    picked = chosen(sessions())
    todo_all = pairs(picked)
    path = OWN / "decisions.jsonl"
    decided = done(path)
    todo = [p for p in todo_all if p not in decided]
    if args.plan:
        groups = {g: sum(1 for s in picked if s["group"] == g) for g in
                  ("wrong_with_gold", "right_with_gold", "wrong_never")}  # fmt: skip
        print(json.dumps({"sessions": groups, "pairs": len(todo_all), "left": len(todo)}))
        return 0
    if args.live:
        if not 0 < args.cap <= 0.40:
            raise SystemExit("--cap is required, at most 0.40 USD (owner's OK, 2026-10-07)")
        print(json.dumps(asyncio.run(run_live(todo, args.cap, path))))
        return 0
    text = json.dumps(report(picked, decided), indent=1)
    if args.out:
        pathlib.Path(args.out).write_bytes((text + "\n").encode("utf-8"))
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
