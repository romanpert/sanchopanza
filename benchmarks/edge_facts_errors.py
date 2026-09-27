"""Where `verify_edge` and `relate_facts` go wrong, read from the recordings. Free.

    python benchmarks/edge_facts_errors.py   # writes docs/results/2026-09-27-edge-facts/

Nothing is called. The design is fixed in `docs/results/2026-09-27-edge-facts/prereg.md`:
everything here is descriptive, and no rule compared here changes code, because every
recording of these two points covers the same 50 + 50 cases and they were read first.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from collections import defaultdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from thresholds import wilson_lower  # noqa: E402

from sanchopanza import Thresholds  # noqa: E402
from sanchopanza.eval.bench import load_cases, run_bench  # noqa: E402
from sanchopanza.points import entities, graph  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, key_of  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-09-27-edge-facts"
BENCHES = ("graph.jsonl", "graph-c.jsonl", "graph-build.jsonl")
FOURTH = ROOT / "fixtures" / "fourth-batch.jsonl"
FACT_FIXTURES = ("fourth-batch.jsonl", "public-benches.jsonl", "edge-fix.jsonl")
ORDER = ROOT / "docs" / "results" / "2026-09-25-order" / "option-order.jsonl"
COSTLY = {"agree", "conflict"}
DIRECTION_CUT = 0.88  # the cut ed-26 suggests; examined, not proposed
TARGET = 0.80


def cases(point: str) -> list[dict[str, Any]]:
    return [c for c in load_cases(ROOT / "benches" / f for f in BENCHES) if c["point"] == point]


def _number(case_id: str) -> int:
    return int(case_id.split("-")[1])


# --- edges -----------------------------------------------------------------------------------


async def edge_rows() -> list[dict[str, Any]]:
    edge_cases = cases("edge")
    decider = RecordedDecider.from_file(FOURTH)
    verdicts = {r.id: r.predicted for r in await run_bench(edge_cases, decider)}
    rows = []
    for c in edge_cases:
        i = c["input"]
        state, qs = graph.edge_questions(
            subject=i["subject"],
            relation=i["relation"],
            obj=i["obj"],
            text=i["text"],
            direction_by_roles=False,  # the wording these recordings were made with
        )
        d = await decider.decide("edge", state, qs)
        rows.append(
            {
                "id": c["id"],
                "expected": c["expected"],
                "predicted": verdicts[c["id"]],
                "stated": d.answer("stated").truth,
                "direction": d.answer("direction").truth,
            }
        )
    return rows


def _precision_bound(rows: list[dict[str, Any]]) -> float:
    right = sum(r["expected"] == "supported" for r in rows)
    return round(wilson_lower(right, len(rows)), 3)


def edge_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    committed = [r for r in rows if r["predicted"] == "supported"]
    wrong = [r for r in committed if r["expected"] != "supported"]
    reversed_cases = [r for r in rows if r["expected"] == "reversed"]
    later = [r for r in committed if _number(r["id"]) > 20]
    later_cut = [r for r in later if r["direction"] >= DIRECTION_CUT]
    return {
        "committed": len(committed),
        "committed_wrong": [[r["id"], r["stated"], r["direction"]] for r in wrong],
        "min_direction_of_right_commits": min(
            r["direction"] for r in committed if r["expected"] == "supported"
        ),
        "commit_precision_wilson95_low": _precision_bound(committed),
        "reversed_caught": sum(r["predicted"] == "reversed" for r in reversed_cases),
        "reversed_total": len(reversed_cases),
        "reversed_missed": {
            r["id"]: [r["predicted"], r["direction"]]
            for r in reversed_cases
            if r["predicted"] != "reversed"
        },
        "no_literal_mention": sorted(r["id"] for r in rows if r["stated"] is None),
        "later_batch": {
            "committed_now": len(later),
            "committed_at_cut": len(later_cut),
            "wilson95_low_at_cut": _precision_bound(later_cut),
            "reaches_target": _precision_bound(later_cut) >= TARGET,
        },
    }


# --- facts -----------------------------------------------------------------------------------


def _entries(path: pathlib.Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def fact_recordings() -> dict[str, dict[str, dict[str, Any]]]:
    by_key = {}
    for c in cases("facts"):
        state, qs = entities.fact_questions(
            fact_a=c["input"]["fact_a"], fact_b=c["input"]["fact_b"]
        )
        by_key[key_of("facts", state, qs)] = c
    sources = [(name, ROOT / "fixtures" / name) for name in FACT_FIXTURES]
    sources.append(("option-order", ORDER))
    recs: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for name, path in sources:
        for e in _entries(path):
            if e.get("point") != "facts" or e.get("key") not in by_key:
                continue
            label = f"{name}:{e['arm']}" if "arm" in e else name
            recs[label][e["key"]] = {"answer": e["answers"]["relation"], "case": by_key[e["key"]]}
    return dict(recs)


def shipped(answer: dict[str, Any], t: Thresholds) -> str | None:
    """`entities.decide_facts`, on a recorded answer."""
    return answer["choice"] if answer["confidence"] >= t.relax else None


def unrelated_at_half(answer: dict[str, Any], t: Thresholds) -> str | None:
    verdict = shipped(answer, t)
    if verdict is not None:
        return verdict
    p = answer["probabilities"]
    top = max(p, key=p.get)
    return "unrelated" if top == "unrelated" and p[top] >= 0.5 else None


def score(recording: dict[str, dict[str, Any]], policy) -> dict[str, int]:
    t = Thresholds()
    decided = right = costly = 0
    for item in recording.values():
        verdict = policy(item["answer"], t)
        if verdict is None:
            continue
        expected = item["case"]["expected"]
        decided += 1
        right += verdict == expected
        costly += {verdict, expected} == COSTLY
    return {"n": len(recording), "decided": decided, "right": right, "costly": costly}


def unrelated_profile(recording: dict[str, dict[str, Any]]) -> dict[str, Any]:
    items = [i for i in recording.values() if i["case"]["expected"] == "unrelated"]
    top = [
        i
        for i in items
        if max(i["answer"]["probabilities"].items(), key=lambda kv: kv[1])[0] == "unrelated"
    ]
    return {
        "unrelated_cases": len(items),
        "unrelated_is_top": len(top),
        "p_when_top": sorted(round(i["answer"]["probabilities"]["unrelated"], 2) for i in top),
    }


# --- the Choice identity -----------------------------------------------------------------------


def choice_identity() -> dict[str, dict[str, float]]:
    """Recorded Choice confidence against (p_top - 1/k) / (1 - 1/k), by option count k."""
    worst: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    paths = sorted((ROOT / "fixtures").glob("*.jsonl"))
    paths += sorted((ROOT / "docs" / "results").glob("*/*.jsonl"))
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            answers = e.get("answers") if isinstance(e, dict) else None
            if not isinstance(answers, dict):
                continue
            for a in answers.values():
                if (
                    not isinstance(a, dict)
                    or a.get("kind") != "choice"
                    or not a.get("probabilities")
                ):
                    continue
                k = len(a["probabilities"])
                predicted = (max(a["probabilities"].values()) - 1 / k) / (1 - 1 / k)
                worst[k] = max(worst[k], abs(predicted - a["confidence"]))
                count[k] += 1
    return {str(k): {"n": count[k], "max_deviation": round(worst[k], 4)} for k in sorted(count)}


async def run() -> dict[str, Any]:
    rows = await edge_rows()
    recs = fact_recordings()
    return {
        "edge": edge_summary(rows),
        "facts": {
            name: {
                "shipped": score(rec, shipped),
                "unrelated_at_half": score(rec, unrelated_at_half),
            }
            for name, rec in sorted(recs.items())
        },
        "facts_unrelated_profile": unrelated_profile(recs["fourth-batch.jsonl"]),
        "choice_identity": choice_identity(),
        "edge_rows": rows,
    }


def main() -> int:
    result = asyncio.run(run())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    view = {k: v for k, v in result.items() if k != "edge_rows"}
    sys.stdout.write(json.dumps(view, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
