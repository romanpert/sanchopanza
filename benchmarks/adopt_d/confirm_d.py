"""Verdicts of phase D of the adoption study, as `docs/results/2026-10-03-adopt-d/prereg.md` fixes
them ("Measures", "When an S session counts as the treatment", "Hypotheses and verdicts"). Free.

    python benchmarks/adopt_d/confirm_d.py            # every verdict and the per-instance table

Nothing is read until D's seal holds (`run_d.seal_refusal`) and D's frozen commit is filled in.

- A session **ran** when it was not NOT RUN, was not cut by the timeout and reported a result
  (`confirm.ran`). A **pair** (instance, repetition) is complete when both sessions ran on Haiku
  and Claude Code 2.1.285, were graded by the harness, and the S session is the treatment: phase
  A's amendment 5, (a) to (f) (`criteria`, which must agree with `confirm.with_decider`), its
  frozen copy D's commit, and (g) find_in_repo not deferred (`run_d.find_hidden`). Every exclusion
  is reported per arm and stratum, by criterion.
- Per instance, over its complete pairs: `res_N`, `res_S` (mean resolved), `cost_N`, `cost_S`
  (Claude Code's list price plus Jev's journal, `confirm.arm_result`), `turns_N`, `turns_S`.
- Bootstrap: 10,000 resamples of the instances (an instance carries its three pairs), seed
  20261004, percentile intervals. H1's lower bound is draws[100], the 1st percentile, one-sided:
  an exact simulation of the rule on phase A's resolve profile (`sim_h1.py`) gave draws[500] a
  type I error near 12 % at the margin, draws[100] near 5 %. The other intervals are two-sided 95 %.
- Adoption (H4): over every S session that ran as the treatment (graded or not, whatever its
  N), from the stream's tool uses, main thread and subagents: find_in_repo, ToolSearch, the
  `sanchopanza-code` skill (other skills apart). Delegation, both arms: Agent/Task calls, and the
  failed ones, where the result says `Agent type '<X>' not found` for an X other than the
  `subagent_type` asked (the hook's rewrite), beside every such "not found".
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any, TypeVar

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_d  # noqa: E402  (sets D's frozen copy before phase A's modules are imported)
from run_d import ARMS, D_MODEL, FIND_TOOL, REPS, confirm, evidence_of  # noqa: E402

SEED, RESAMPLES = 20261004, 10_000
MARGIN = Fraction(2, 26)  # H1: phase A's singles margin, 2 of 26, as a share
COST_NONINFERIOR = 1.10
LOWER = 0.01  # H1: draws[100] of 10,000
WATCHED = ("find", "tool_search", "skill", "skill_other")
SKILL = "sanchopanza-code"
DELEGATE = ("Agent", "Task")
NOT_FOUND = re.compile(r"Agent type '([^']+)' not found")
LETTERS = ("a", "b", "c", "d", "e", "f", "g")

T = TypeVar("T")


# ---- statistics (pure) ---------------------------------------------------------------------------


def resample(items: Sequence[T], stat: Callable[[list[T]], Any], seed: int = SEED,
             resamples: int = RESAMPLES) -> list[Any]:  # fmt: skip
    """The statistic over `resamples` resamples of the items with replacement, sorted."""
    rng = random.Random(seed)
    pool = list(items)
    return sorted(stat([rng.choice(pool) for _ in pool]) for _ in range(resamples))


def lower_bound(draws: Sequence[Any]) -> Any:
    """H1's one-sided bound: the 1st percentile (draws[100] of 10,000)."""
    return draws[int(LOWER * len(draws))]


def interval(draws: Sequence[Any]) -> tuple[Any, Any]:
    """Two-sided 95 %, as `confirm.paired_interval` takes it."""
    return draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]


def mean(values: Sequence[Any]) -> Any:
    return sum(values[1:], values[0]) / len(values)


def median_ratio(pairs: list[tuple[float, float]]) -> float:
    return statistics.median(s / n for s, n in pairs)


def ratio_interval(pairs: list[tuple[float, float]]) -> tuple[float, float, float]:
    """(median ratio, low, high), unrounded: verdicts compare these."""
    return (median_ratio(pairs), *interval(resample(pairs, median_ratio)))


def ratio_summary(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    point, low, high = ratio_interval(pairs)
    return {"instances": len(pairs), "median_ratio": round(point, 4),
            "interval": [round(low, 4), round(high, 4)]}  # fmt: skip


# ---- reading the sessions ------------------------------------------------------------------------


def uses(stream: Path) -> dict[str, int]:
    """What a session called, main thread and subagents: the watched tools, and delegation with
    its failures (the hook's rewrite to an agent type the harness has no name for)."""
    calls: Counter[str] = Counter()
    asked: dict[str, Any] = {}
    failed = not_found = 0
    for event in confirm.events(stream) if stream.exists() else []:
        for block in confirm.blocks_of(event):
            if block.get("type") == "tool_use":
                name, given = str(block.get("name")), block.get("input") or {}
                calls[name] += 1
                if name == "Skill":
                    calls["skill" if given.get("skill") == SKILL else "skill_other"] += 1
                if name in DELEGATE:
                    asked[str(block.get("id"))] = given.get("subagent_type")
            elif block.get("type") == "tool_result" and block.get("is_error"):
                if found := NOT_FOUND.search(confirm.result_text(block)):
                    not_found += 1
                    tool_use = str(block.get("tool_use_id"))
                    failed += tool_use in asked and found.group(1) != asked[tool_use]
    return {"find": calls[FIND_TOOL], "tool_search": calls["ToolSearch"],
            "skill": calls["skill"], "skill_other": calls["skill_other"],
            "agent": sum(calls[d] for d in DELEGATE), "delegation_failed": failed,
            "agent_not_found": not_found}  # fmt: skip


def criteria(evidence: Path) -> dict[str, bool]:
    """The treatment's criteria for an S session, one by one: D's commit, (a) to (f) as
    `confirm.with_decider` reads them, and (g). Code drift between the two is an error."""
    row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
    frozen = (row.get("sanchopanza") or {}).get("frozen") or {}
    probes = row.get("decider") or []
    hooks = confirm._jsonl(evidence / "hooks.jsonl")
    decisions = [e.get("data") or {} for e in confirm._jsonl(evidence / "journal.jsonl")
                 if e.get("kind") == "decision"]  # fmt: skip
    asked = [d for d in decisions if d.get("provider") == "jev"]
    out = {"commit": frozen.get("commit") == run_d.D_COMMIT,
           "a": {"jev", "mcp"} <= set(frozen.get("extras") or []),
           "b": bool(probes) and all(p == run_d.DECIDER for p in probes),
           "c": confirm.find_connected(evidence),
           "d": bool(hooks) and all(h.get("key") is True for h in hooks),
           "e": all(d.get("provider") in confirm.DECIDER_PROVIDERS for d in decisions),
           "f": sum(bool(d.get("error")) for d in asked) <= confirm.DECIDER_ERRORS * len(asked),
           "g": run_d.find_visible(evidence)}  # fmt: skip
    if all(out[c] for c in "abcdef") != confirm.with_decider(evidence, frozen, row):
        raise RuntimeError(f"{evidence}: criteria disagree with confirm.with_decider")
    return out


def exclusions(evidence: Path, arm: str) -> list[str]:
    """Why a session does not count in a pair, as codes ([] when it does). "not graded" comes
    last: a session that ran (as the treatment) still counts for adoption and delegation."""
    if not (evidence / "row.json").exists():
        return ["no row" if not evidence.exists() else "started, no row"]
    row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
    call = row["calls"][0]
    if row.get("model") != D_MODEL:
        return ["model"]
    if row.get("claude_version") != run_d.CLAUDE_VERSION:
        return ["claude version"]
    if not confirm.ran(call):
        return [f"did not run ({call.get('status') or call.get('exit') or call.get('subtype')})"]
    codes = []
    if arm == "S":
        codes = [c if c == "commit" else f"({c})" for c, ok in criteria(evidence).items() if not ok]
    if not (evidence / "grade.json").exists():
        codes.append("not graded")
    return codes


def why_not(evidence: Path, arm: str) -> str:
    """The exclusions as one line ("" when the session counts)."""
    return "; ".join(exclusions(evidence, arm))


def session(evidence: Path, arm: str) -> dict[str, Any]:
    codes = exclusions(evidence, arm)
    out: dict[str, Any] = {"why": "; ".join(codes), "codes": codes}
    if any(c != "not graded" for c in codes):
        return out
    row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
    out = {**out, "turns": row["calls"][0].get("turns") or 0, "jev": row.get("jev_usd", 0.0),
           **uses(evidence / "stream-1.jsonl")}  # fmt: skip
    if codes:
        return out
    result = confirm.arm_result(evidence, D_MODEL, run_d.D_COMMIT if arm == "S" else None)
    if result is None or not result["complete"]:
        return {**out, "why": "refused by confirm.arm_result", "codes": ["arm_result"]}
    return {**out, "resolved": int(result["resolved"]), "cost": result["cost"]}


def instance(name: str, stratum: str | None) -> dict[str, Any]:
    reps = []
    for rep in range(1, REPS + 1):
        sessions = {arm: session(evidence_of(name, rep, arm), arm) for arm in ARMS}
        complete = all(not s["why"] for s in sessions.values())
        reps.append({"rep": rep, **sessions, "complete": complete})
    return summarize({"instance": name, "stratum": stratum, "reps": reps})


def summarize(item: dict[str, Any]) -> dict[str, Any]:
    """The per-instance means over its complete pairs (none: only the reasons)."""
    pairs = [r for r in item["reps"] if r["complete"]]
    out = {**item, "pairs": len(pairs)}
    if not pairs:
        return out
    k = len(pairs)
    for arm in ARMS:
        out[f"res_{arm}"] = Fraction(sum(r[arm]["resolved"] for r in pairs), k)
        out[f"cost_{arm}"] = sum(r[arm]["cost"] for r in pairs) / k
        out[f"turns_{arm}"] = sum(r[arm]["turns"] for r in pairs) / k
    return out


# ---- the verdicts --------------------------------------------------------------------------------


def h1(table: list[dict[str, Any]]) -> dict[str, Any]:
    """Non-inferior success: draws[100] (the 1st percentile) of D = mean(res_S - res_N) at least
    -2/26. Undecided while any instance has no complete pair."""
    missing = [t["instance"] for t in table if not t["pairs"]]
    diffs = [t["res_S"] - t["res_N"] for t in table if t["pairs"]]
    if not diffs:
        return {"holds": None, "missing": missing, "why": "no complete pair"}
    point, low = mean(diffs), lower_bound(resample(diffs, mean))
    return {"instances": len(diffs), "difference": round(float(point), 4),
            "lower_bound_1pct": round(float(low), 4), "margin": round(-float(MARGIN), 4),
            "holds": None if missing else low >= -MARGIN, "missing": missing}  # fmt: skip


def h2(table: list[dict[str, Any]]) -> dict[str, Any]:
    """Cost: median over instances of cost_S / cost_N with its two-sided 95 % interval;
    non-inferior when the upper bound is below 1.10, cheaper when below 1."""
    used = [t for t in table if t["pairs"] and t["cost_N"] > 0]
    left = [t["instance"] for t in table if t not in used]
    if not used:
        return {"verdict": "no data", "not_used": left}
    pairs = [(t["cost_S"], t["cost_N"]) for t in used]
    high = ratio_interval(pairs)[2]  # unrounded: the verdicts compare this
    return {**ratio_summary(pairs), "non_inferior": high < COST_NONINFERIOR, "cheaper": high < 1.0,
            "cost_S": round(sum(t["cost_S"] for t in used), 4),
            "cost_N": round(sum(t["cost_N"] for t in used), 4), "not_used": left}  # fmt: skip


def treated(item: dict[str, Any]) -> list[dict[str, Any]]:
    """The S sessions of an instance that ran as the treatment, graded or not."""
    return [r["S"] for r in item["reps"] if r["S"]["why"] in ("", "not graded")]


def share_with(groups: list[list[int]]) -> float:
    sessions = [n for g in groups for n in g]
    return sum(n > 0 for n in sessions) / len(sessions)


def adoption(table: list[dict[str, Any]]) -> dict[str, Any]:
    """H4, no verdict: per tool, the share of S sessions with a call (interval over instances)
    and the calls per session."""
    groups = [treated(t) for t in table if treated(t)]
    if not groups:
        return {"sessions": 0}
    out: dict[str, Any] = {"sessions": sum(len(g) for g in groups)}
    for key in WATCHED:
        counts = [[s[key] for s in g] for g in groups]
        low, high = interval(resample(counts, share_with))
        out[key] = {"share": round(share_with(counts), 4), "interval": [round(low, 4),
                    round(high, 4)], "per_session": round(sum(map(sum, counts)) /
                    out["sessions"], 4)}  # fmt: skip
    return out


def counted(item: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    """An arm's sessions that ran (the S ones as the treatment), graded or not."""
    return [r[arm] for r in item["reps"] if r[arm]["why"] in ("", "not graded")]


def delegation(table: list[dict[str, Any]]) -> dict[str, Any]:
    """Per arm, no verdict: Agent/Task calls per session, the failed delegations (the hook's
    rewrite to an unknown agent type) and every "Agent type ... not found"."""
    out = {}
    for arm in ARMS:
        sessions = [s for t in table for s in counted(t, arm)]
        n = len(sessions)
        out[arm] = {"sessions": n, "agent_calls": sum(s["agent"] for s in sessions),
                    "agent_per_session": round(sum(s["agent"] for s in sessions) / n, 4) if n
                    else None,
                    "delegation_failed": sum(s["delegation_failed"] for s in sessions),
                    "sessions_with_failed": sum(s["delegation_failed"] > 0 for s in sessions),
                    "agent_not_found": sum(s["agent_not_found"] for s in sessions)}  # fmt: skip
    return out


def excluded(table: list[dict[str, Any]]) -> dict[str, Any]:
    """Per arm, every session's exclusion codes counted (a session can carry several)."""
    out = {}
    for arm in ARMS:
        sessions = [r[arm] for t in table for r in t["reps"]]
        codes = Counter(c.split(" (")[0] if c.startswith("did not run") else c
                        for s in sessions for c in s["codes"])  # fmt: skip
        out[arm] = {"sessions": len(sessions), "counted": sum(not s["codes"] for s in sessions),
                    **dict(sorted(codes.items()))}  # fmt: skip
    return out


def by_stratum(table: list[dict[str, Any]], what: Callable[[list], Any]) -> dict[str, Any]:
    strata = dict.fromkeys(str(t["stratum"]) for t in table)
    return {s: what([t for t in table if str(t["stratum"]) == s]) for s in strata}


def exploratory(table: list[dict[str, Any]]) -> dict[str, Any]:
    """Turns ratio, cost per turn, and within S the sessions that called find against those that
    did not (selected by the agent: not causal). No verdict."""
    used = [t for t in table if t["pairs"] and t["turns_N"] > 0 and t["turns_S"] > 0]
    turns = ratio_summary([(t["turns_S"], t["turns_N"]) for t in used]) if used else {}
    per_turn = ratio_summary([(t["cost_S"] / t["turns_S"], t["cost_N"] / t["turns_N"])
                              for t in used]) if used else {}  # fmt: skip
    s_done = [r["S"] for t in table for r in t["reps"] if r["complete"]]
    split = {}
    for label, group in (("called_find", [s for s in s_done if s["find"]]),
                         ("did_not", [s for s in s_done if not s["find"]])):  # fmt: skip
        split[label] = {"sessions": len(group),
                        "resolved": sum(s["resolved"] for s in group),
                        "mean_cost": round(mean([s["cost"] for s in group]), 4) if group
                        else None}  # fmt: skip
    return {"turns_ratio": turns, "cost_per_turn_ratio": per_turn, "find_split": split}


def beside(table: list[dict[str, Any]]) -> dict[str, Any]:
    """Reported beside, deciding nothing: totals per arm and stratum, flips between
    repetitions, Jev's spend, every guard block of the S sessions with its command."""

    def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
        pairs = [r for t in rows for r in t["reps"] if r["complete"]]
        return {arm: {"sessions": len(pairs), "resolved": sum(r[arm]["resolved"] for r in pairs),
                      "cost": round(sum(r[arm]["cost"] for r in pairs), 4),
                      "turns": sum(r[arm]["turns"] for r in pairs)} for arm in ARMS}  # fmt: skip

    flips = {arm: [t["instance"] for t in table
                   if len({r[arm]["resolved"] for r in t["reps"] if r["complete"]}) > 1]
             for arm in ARMS}  # fmt: skip
    blocks: list[dict[str, Any]] = []
    for t in table:
        for r in t["reps"]:
            stream = evidence_of(t["instance"], r["rep"], "S") / "stream-1.jsonl"
            if stream.exists():
                blocks += confirm.guard_blocks(stream, f"{t['instance']}/r{r['rep']}/S")[0]
    jev = sum(s.get("jev", 0.0) for t in table for s in treated(t))
    return {"totals": totals(table), "totals_by_stratum": by_stratum(table, totals),
            "flips": flips, "jev_usd": round(jev, 4), "guard_blocks": blocks}  # fmt: skip


def per_instance(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for t in table:
        row = {"instance": t["instance"], "stratum": t["stratum"], "pairs": t["pairs"],
               "incomplete": {f"r{r['rep']}": {a: r[a]["why"] for a in ARMS if r[a]["why"]}
                              for r in t["reps"] if not r["complete"]}}  # fmt: skip
        if t["pairs"]:
            row |= {k: round(float(t[k]), 4) for arm in ARMS
                    for k in (f"res_{arm}", f"cost_{arm}", f"turns_{arm}")}  # fmt: skip
            row["find_calls_S"] = [r["S"]["find"] for r in t["reps"] if r["complete"]]
        out.append(row)
    return out


def verdicts(table: list[dict[str, Any]]) -> dict[str, Any]:
    return {"H1": h1(table), "H2": h2(table), "H4": adoption(table),
            "H4_by_stratum": by_stratum(table, adoption), "delegation": delegation(table),
            "delegation_by_stratum": by_stratum(table, delegation),
            "exclusions": excluded(table), "exclusions_by_stratum": by_stratum(table, excluded),
            "exploratory": exploratory(table),
            "beside": beside(table), "per_instance": per_instance(table)}  # fmt: skip


def refusal() -> str | None:
    if not run_d.D_COMMIT:
        return "D_COMMIT is not filled in: nothing is read"
    if why := run_d.seal_refusal():
        return f"{why}: nothing held out is read"
    return None


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    if why := refusal():
        raise SystemExit(why)
    table = [instance(i["instance_id"], i["stratum"]) for i in run_d.instances()]
    print(json.dumps(verdicts(table), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
