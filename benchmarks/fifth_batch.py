"""The fifth batch of `edge` and `facts`: the check the edge-facts pre-registration fixed.

    python benchmarks/fifth_batch.py                     # replay: free, writes analysis.json
    python benchmarks/fifth_batch.py --record --env-file PATH   # asks Jev once, capped

The protocol is the section "What would license a change later (the fifth batch)" of
`docs/results/2026-09-27-edge-facts/prereg.md`, and it is applied literally here:

- `facts` policy: `unrelated` accepted at p >= 0.5 when it is the top option ships iff, with
  the shipped question, it agrees with more labels than the shipped policy and makes no more
  costly (`agree` / `conflict`) errors.
- `facts` wording: the examples on `unrelated` ship iff the same holds for the new question
  against the old, both under the shipped policy.
- `edge` wording: the `direction` question by roles ships iff it catches more `reversed` and
  commits no more wrong edges.
- `edge` threshold: a `direction` cut is derived on one batch to 80 % on the Wilson lower
  bound (the rule of `benchmarks/thresholds.py`, mirrored here because that file has no entry
  for this point) and reported on the other.

The cases (`benches/graph-d.jsonl`, `graph-e.jsonl`) were hashed into
`docs/results/2026-09-27-edge-facts/fifth-batch/hashes.txt` before the first call. The
recording lives in `fixtures/fifth-batch/`, one level below `fixtures/`, so the Choice-identity
canary of the edge-facts analysis (7,162 answers, `tests/test_edge_facts.py`) still counts the
set it was published on.

Recording costs about 120 calls at ~0.00002 USD each. The cap is hard: the run stops before a
call once the spend of the decisions already made reaches `CAP_USD`, and it never re-asks a
key that is already in the recording.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from agreement import kappa  # noqa: E402
from thresholds import wilson_lower  # noqa: E402

from sanchopanza import Thresholds  # noqa: E402
from sanchopanza.eval.bench import load_cases  # noqa: E402
from sanchopanza.points import entities, graph  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider, key_of  # noqa: E402
from sanchopanza.text import mention_present  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-09-27-edge-facts" / "fifth-batch"
RECORDING = ROOT / "fixtures" / "fifth-batch" / "recording.jsonl"
EDGE_BENCH = ROOT / "benches" / "graph-d.jsonl"
FACTS_BENCH = ROOT / "benches" / "graph-e.jsonl"
FOURTH = ROOT / "fixtures" / "fourth-batch.jsonl"
FOURTH_EDGE_BENCHES = (ROOT / "benches" / "graph-build.jsonl", ROOT / "benches" / "graph-c.jsonl")
MODEL = "jev-1.13.0"
CAP_USD = 0.05
COSTLY = {"agree", "conflict"}
UNRELATED_AT = 0.5
TARGET = 0.80
# Reversed cases whose text is a passive sentence ("fue adquirida por", "son contratados por").
PASSIVE_REVERSED = ("ed-52", "ed-54", "ed-57", "ed-62", "ed-66", "ed-67", "ed-73", "ed-74")


def facts_cases() -> list[dict[str, Any]]:
    return [c for c in load_cases([FACTS_BENCH]) if c["point"] == "facts"]


def edge_cases(paths=(EDGE_BENCH,)) -> list[dict[str, Any]]:
    return [c for c in load_cases(list(paths)) if c["point"] == "edge"]


def fact_query(case: dict[str, Any], *, examples: bool):
    i = case["input"]
    return entities.fact_questions(
        fact_a=i["fact_a"], fact_b=i["fact_b"], unrelated_examples=examples
    )


def edge_query(case: dict[str, Any], *, by_roles: bool):
    i = case["input"]
    return graph.edge_questions(
        subject=i["subject"],
        relation=i["relation"],
        obj=i["obj"],
        text=i["text"],
        direction_by_roles=by_roles,
    )


def queries() -> list[tuple[str, str, Any, Any]]:
    """(arm, point, state, questions) for every call of the batch, in a fixed order."""
    out = []
    for examples, arm in ((False, "facts:shipped"), (True, "facts:examples")):
        for c in facts_cases():
            out.append((arm, "facts", *fact_query(c, examples=examples)))
    for by_roles, arm in ((False, "edge:shipped"), (True, "edge:by_roles")):
        for c in edge_cases():
            out.append((arm, "edge", *edge_query(c, by_roles=by_roles)))
    return out


# --- recording ---------------------------------------------------------------------------------


def _key_from_env_file(path: pathlib.Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "TYPESAFE_API_KEY":
            return value.strip().strip('"').strip("'")
    raise SystemExit(f"TYPESAFE_API_KEY not in {path}")


def _recorded_spend() -> tuple[set[str], float]:
    if not RECORDING.exists():
        return set(), 0.0
    keys, spent = set(), 0.0
    for line in RECORDING.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            keys.add(e["key"])
            spent += float(e.get("cost_usd") or 0.0)
    return keys, spent


async def record(env_file: pathlib.Path | None) -> int:
    from sanchopanza.providers.jev import JevDecider

    key = os.environ.get("TYPESAFE_API_KEY") or (_key_from_env_file(env_file) if env_file else "")
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY: pass --env-file")
    done, spent = _recorded_spend()
    jev = JevDecider(key, model=MODEL)
    recorder = RecordingDecider(jev, RECORDING)
    calls = 0
    try:
        for arm, point, state, qs in queries():
            if key_of(point, state, qs) in done:
                continue
            if spent >= CAP_USD:
                sys.stderr.write(f"cap reached at {spent:.6f} USD before {arm}; stopping\n")
                return 2
            decision = await recorder.decide(point, state, qs)
            calls += 1
            spent += decision.cost_usd
            done.add(key_of(point, state, qs))
            if decision.model != MODEL:
                sys.stderr.write(f"model moved: {decision.model} != {MODEL}; stopping\n")
                return 3
            if decision.failed or not decision.answers:
                sys.stderr.write(f"empty answer on {arm}; stopping\n")
                return 4
    finally:
        await jev.aclose()
    sys.stdout.write(f"calls {calls}, recorded spend {spent:.6f} USD\n")
    return 0


# --- the second annotator ----------------------------------------------------------------------


def annotators() -> dict[str, Any]:
    """Author (`expected`) against the blind second annotator, per point and overall.

    The rule of the earlier batches (`docs/results/2026-09-24-fifty/README.md`): a label is
    not changed because a model disagrees with it; disputed cases are kept and listed.
    """
    second = {}
    for line in (OUT / "annotator-2.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            second[row["id"]] = row["label"]
    first = {c["id"]: c["expected"] for c in facts_cases() + edge_cases()}
    out: dict[str, Any] = {}
    groups = (
        ("facts", [c["id"] for c in facts_cases()]),
        ("edge", [c["id"] for c in edge_cases()]),
    )
    for point, ids in groups:
        observed, k = kappa([(first[i], second[i]) for i in ids])
        out[point] = {"n": len(ids), "agreement": round(observed, 3), "kappa": round(k, 3)}
    observed, k = kappa([(first[i], second[i]) for i in first])
    out["all"] = {"n": len(first), "agreement": round(observed, 3), "kappa": round(k, 3)}
    out["disputed"] = sorted(i for i in first if first[i] != second.get(i))
    return out


# --- scoring -------------------------------------------------------------------------------------


def score_facts(rows: list[dict[str, Any]]) -> dict[str, int]:
    decided = [r for r in rows if r["verdict"] is not None]
    return {
        "n": len(rows),
        "decided": len(decided),
        "right": sum(r["verdict"] == r["expected"] for r in decided),
        "costly": sum({r["verdict"], r["expected"]} == COSTLY for r in decided),
    }


async def facts_arm(decider, *, examples: bool) -> dict[str, Any]:
    t = Thresholds()
    shipped, candidate = [], []
    for c in facts_cases():
        state, qs = fact_query(c, examples=examples)
        d = await decider.decide("facts", state, qs)
        if d.failed or not d.answers:
            raise SystemExit(f"{c['id']}: no recording; the fifth batch is replay-only")
        a = d.answer("relation")
        base = {"id": c["id"], "expected": c["expected"], "choice": a.choice}
        base["p"] = {k: round(v, 3) for k, v in a.probabilities.items()}
        shipped.append({**base, "verdict": entities.decide_facts(d, t)[0]})
        verdict = entities.decide_facts(d, t, unrelated_at=UNRELATED_AT)[0]
        candidate.append({**base, "verdict": verdict})
    return {
        "shipped_policy": score_facts(shipped),
        "unrelated_at_half": score_facts(candidate),
        "rows": shipped,
    }


async def edge_rows(decider, cases, *, by_roles: bool) -> list[dict[str, Any]]:
    t = Thresholds()
    rows = []
    for c in cases:
        i = c["input"]
        found = mention_present(i["subject"], i["text"]) and mention_present(i["obj"], i["text"])
        state, qs = edge_query(c, by_roles=by_roles)
        d = await decider.decide("edge", state, qs) if found else None
        if found and (d.failed or not d.answers):
            raise SystemExit(f"{c['id']}: no recording; the fifth batch is replay-only")
        check = (
            graph.decide_edge(d, t)
            if found
            else graph.decide_edge(d or _empty(), t, mentions_found=False)
        )
        rows.append(
            {
                "id": c["id"],
                "expected": c["expected"],
                "verdict": check.verdict,
                "stated": d.answer("stated").truth if found else None,
                "direction": d.answer("direction").truth if found else None,
            }
        )
    return rows


def _empty():
    from sanchopanza.contract import Decision

    return Decision("edge", {}, "code", "-")


def score_edge(rows: list[dict[str, Any]]) -> dict[str, Any]:
    committed = [r for r in rows if r["verdict"] == "supported"]
    wrong = [r["id"] for r in committed if r["expected"] != "supported"]
    reversed_rows = [r for r in rows if r["expected"] == "reversed"]
    caught = [r["id"] for r in reversed_rows if r["verdict"] == "reversed"]
    decided = [r for r in rows if r["verdict"] != "review"]
    right_commits = len(committed) - len(wrong)
    return {
        "n": len(rows),
        "decided": len(decided),
        "right": sum(r["verdict"] == r["expected"] for r in decided),
        "committed": len(committed),
        "committed_wrong": wrong,
        "commit_precision_wilson95_low": round(wilson_lower(right_commits, len(committed)), 3),
        "reversed_caught": len(caught),
        "reversed_total": len(reversed_rows),
        "passive_reversed_caught": sum(i in PASSIVE_REVERSED for i in caught),
        "supported_committed": right_commits,
    }


def derive_direction_cut(rows: list[dict[str, Any]]) -> float | None:
    """`thresholds.derive`, for the direction of committed edges: the cut with the most recall
    whose precision LOWER BOUND clears the target. Acting is committing."""
    commits = [r for r in rows if r["verdict"] == "supported"]
    positives = sum(r["expected"] == "supported" for r in rows)
    best: tuple[float, float] | None = None
    for step in range(1, 100):
        cut = step / 100
        act = [r for r in commits if r["direction"] >= cut]
        if not act:
            continue
        hits = sum(r["expected"] == "supported" for r in act)
        if wilson_lower(hits, len(act)) < TARGET:
            continue
        recall = hits / positives if positives else 0.0
        if best is None or recall > best[1]:
            best = (cut, recall)
    return None if best is None else best[0]


def at_cut(rows: list[dict[str, Any]], cut: float) -> dict[str, Any]:
    act = [r for r in rows if r["verdict"] == "supported" and r["direction"] >= cut]
    hits = sum(r["expected"] == "supported" for r in act)
    return {
        "cut": cut,
        "committed": len(act),
        "right": hits,
        "wilson95_low": round(wilson_lower(hits, len(act)), 3),
        "reaches_target": wilson_lower(hits, len(act)) >= TARGET,
        "best_possible_wilson95_low": round(
            wilson_lower(*(2 * [sum(r["expected"] == "supported" for r in rows)])), 3
        ),
    }


def verdicts(facts: dict[str, Any], edge: dict[str, Any], cut: dict[str, Any]) -> dict[str, Any]:
    def better(new: dict[str, int], old: dict[str, int]) -> bool:
        return new["right"] > old["right"] and new["costly"] <= old["costly"]

    old_q, new_q = facts["shipped"], facts["examples"]
    e_old, e_new = edge["shipped"], edge["by_roles"]
    return {
        "facts_policy_unrelated_at_half": better(
            old_q["unrelated_at_half"], old_q["shipped_policy"]
        ),
        "facts_wording_examples": better(new_q["shipped_policy"], old_q["shipped_policy"]),
        "edge_wording_by_roles": (
            e_new["reversed_caught"] > e_old["reversed_caught"]
            and len(e_new["committed_wrong"]) <= len(e_old["committed_wrong"])
        ),
        "edge_direction_cut": cut["derived"] is not None and cut["reported"]["reaches_target"],
    }


async def run() -> dict[str, Any]:
    decider = RecordedDecider.from_file(RECORDING)
    facts = {
        "shipped": await facts_arm(decider, examples=False),
        "examples": await facts_arm(decider, examples=True),
    }
    new = edge_cases()
    old_rows = await edge_rows(
        RecordedDecider.from_file(FOURTH), edge_cases(FOURTH_EDGE_BENCHES), by_roles=False
    )
    shipped_rows = await edge_rows(decider, new, by_roles=False)
    roles_rows = await edge_rows(decider, new, by_roles=True)
    edge = {
        "shipped": score_edge(shipped_rows),
        "by_roles": score_edge(roles_rows),
        "rows": {"shipped": shipped_rows, "by_roles": roles_rows},
    }
    derived = derive_direction_cut(old_rows)
    cut = {
        "derived_on": "fourth batch, shipped question (50 cases)",
        "derived": derived,
        "reported": at_cut(shipped_rows, derived if derived is not None else 1.0),
    }
    spend = sum(
        float(json.loads(line).get("cost_usd") or 0.0)
        for line in RECORDING.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    return {
        "facts": facts,
        "edge": edge,
        "direction_cut": cut,
        "licensed": verdicts(facts, edge, cut),
        "recording": {"calls": len(decider), "cost_usd": round(spend, 6)},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--record", action="store_true", help="ask Jev (capped); otherwise replay")
    p.add_argument("--env-file", type=pathlib.Path, default=None)
    args = p.parse_args()
    if args.record:
        return asyncio.run(record(args.env_file))
    agreement_view = annotators()
    if not RECORDING.exists():
        OUT.mkdir(parents=True, exist_ok=True)
        blocked = {"annotators": agreement_view, "recording": None, "licensed": None}
        (OUT / "analysis.json").write_text(json.dumps(blocked, indent=1), encoding="utf-8")
        sys.stdout.write(json.dumps(blocked, indent=1) + "\n")
        sys.stdout.write("no recording: nothing to score, and so nothing is licensed\n")
        return 1
    result = {**asyncio.run(run()), "annotators": agreement_view}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    view = {
        "facts": {
            k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in result["facts"].items()
        },
        "edge": {k: v for k, v in result["edge"].items() if k != "rows"},
        "direction_cut": result["direction_cut"],
        "licensed": result["licensed"],
        "recording": result["recording"],
        "annotators": agreement_view,
    }
    sys.stdout.write(json.dumps(view, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
