"""Long-chain arms side by side, per chain and per bug: free, it only reads rows, grades and diffs.

    python benchmarks/adopt/long_compare.py [--arm NAME=ROOT:DIR ...] [--json <out.json>]

Default arms (Sonnet 5.5, `long_run.GATE_CHAINS`): N (the gate, `C:\\sp-runs\\L`), N2 (N again,
`L-n2`), Ne (N-early, `L-ne`) and A (the passages pilot, `L-pilot-a`); an arm whose root has no
row is left out. `pilot_a_compare.py` is this with N and A (and A10).

Per chain and arm: cost (owner USD; cut calls at their caps), cumulative cost at calls 10, 20, ...,
60, cost per resolved bug, per-bug F2P (`grade.json`; None until graded), requests, peak context,
compactions, give-ups (`long_report.give_ups`, the STATUS-launch definition) with how many came in
each context band, the unresolved give-ups (a give-up the grade did not resolve: the noise round's
main measure, since a no-change call on a bug an earlier request already fixed is no give-up),
how the arm ended, and for the passages arms the cuts and the re-request rates.
Per pair of arms, on the bugs both ran: discordant resolved bugs (McNemar's exact p, descriptive)
and discordant give-ups. `stable_flips`: on the bugs where N and N2 agree, how often Ne (or A) says
otherwise and which way, so what N already changes against itself is set aside.

How to read it:
- k=1 per chain and arm: descriptive, no inferential claim. N against N2 on the same chain is the
  noise floor; a contrast with another arm reads only against those discordants.
- (a) An arm cut at its cap ran fewer bugs (the gate's N on conan stopped at call 50, 32 USD; Ne
  holds 35 a chain): compare on the common bugs and the cumulative cost at the same call, not on
  the totals.
- (b) Ne runs conan and then pydantic in series under one root and N2 runs pydantic only: the first
  pair with a noise floor is pydantic once Ne's second chain is done.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import long_report  # noqa: E402

CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")  # long_run.GATE_CHAINS
MODEL = "sonnet"
DEFAULT_ARMS = (r"N=C:\sp-runs\L:N", r"N2=C:\sp-runs\L-n2:N", r"Ne=C:\sp-runs\L-ne:Ne",
                r"A=C:\sp-runs\L-pilot-a:A")  # fmt: skip
PAIRS = (("N", "N2"), ("N", "Ne"), ("N2", "Ne"), ("N", "A"), ("N2", "A"), ("Ne", "A"))
BANDS = ((0, 100_000), (100_000, 150_000), (150_000, 200_000), (200_000, None))
CHECKPOINTS = (10, 20, 30, 40, 50, 60)
DECLARED = (
    "k=1 per chain and arm (one run each): descriptive, no inferential statistics; "
    "N against N2 on the same chain is the noise floor"
)


def _json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ratio(a: float | None, b: float | None) -> float | None:
    return round(a / b, 4) if a is not None and b else None


def band(context: int) -> str:
    low, high = next((lo, hi) for lo, hi in BANDS if context >= lo and (hi is None or context < hi))
    return f"{low // 1000}-{high // 1000}k" if high else f">={low // 1000}k"


def _usd(call: Mapping[str, Any]) -> float:
    return float(call.get("owner_usd") or 0.0)


def bug_calls(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The last non-superseded bug call per instance id."""
    found: dict[str, dict[str, Any]] = {}
    for call in row.get("calls") or []:
        if call.get("kind") == "bug" and not call.get("superseded"):
            found = {**found, call["instance_id"]: call}
    return found


def per_bug(row: Mapping[str, Any], grade: Mapping[str, Any],
            quits: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:  # fmt: skip
    """Per bug call. `gave_up_unresolved` is long_report's item `resolved` (None until graded)."""
    graded = {b["instance_id"]: bool(b["resolved"]) for b in grade.get("bugs") or []
              if "instance_id" in b}  # fmt: skip
    quit_ids = {i["instance_id"] for i in quits}
    real = {i["instance_id"] for i in quits if i.get("resolved") is False}
    return {iid: {"request": int(c["request"]), "status": c.get("status"),
                  "resolved": graded.get(iid), "gave_up": iid in quit_ids,
                  "gave_up_unresolved": None if graded.get(iid) is None else iid in real,
                  "context": int(c.get("peak_context") or 0), "owner_usd": _usd(c),
                  "compactions": len(c.get("compactions") or [])}
            for iid, c in bug_calls(row).items()}  # fmt: skip


def cumulative(calls: Sequence[Mapping[str, Any]]) -> dict[int, float]:
    """Owner USD spent up to each checkpoint call (calls without a number count in order)."""
    numbered = [(int(c.get("request") or i), _usd(c)) for i, c in enumerate(calls, start=1)]
    return {k: round(sum(u for r, u in numbered if r <= k), 4) for k in CHECKPOINTS}


def arm_line(evidence: Path) -> dict[str, Any] | None:
    """One arm of one chain as its row, grade and diffs say (None: it never ran)."""
    row = _json(evidence / "row.json")
    if row is None:
        return None
    grade = _json(evidence / "grade.json")
    quits = long_report.give_ups(evidence, row, grade)
    contexts = [i["context"] for i in quits["items"]]
    names = dict.fromkeys(map(band, contexts))
    bands = {b: sum(1 for c in contexts if band(c) == b) for b in names}
    calls = row.get("calls") or []
    cost = round(sum(_usd(c) for c in calls), 4)
    resolved = grade.get("resolved") if grade else None
    total = (grade or {}).get("bugs_total") or row.get("bugs")
    passages = row.get("passages") or {}
    bugs = per_bug(row, grade or {}, quits["items"])
    at = f"at_or_past_{long_report.GIVE_UP_AT // 1000}k"
    return {
        "model": row.get("model"),
        "stopped": row.get("stopped") or "",
        "partial": bool(row.get("partial")),
        "graded": grade is not None,
        "cost_usd": cost,
        "cumulative_usd": cumulative(calls),
        "calls_ran": sum(1 for c in calls if c.get("status") == "ran"),
        "calls_planned": row.get("requests_planned"),
        "resolved": resolved,
        "bugs": total,
        "f2p": round(resolved / total, 4) if resolved is not None and total else None,
        "cost_per_resolved": _ratio(cost, resolved) if resolved else None,
        "requests": sum(int(c.get("requests") or 0) for c in calls),
        "peak_context": max((int(c.get("peak_context") or 0) for c in calls), default=0),
        "compactions": sum(len(c.get("compactions") or []) for c in calls),
        "give_ups": {k: v for k, v in quits.items() if k not in ("items", "unresolved_contexts")},
        "give_up_bands": bands,
        "cuts": passages.get("cuts"),
        "r": passages.get("r"),
        "r_whole": passages.get("r_whole"),
        "chars_in": passages.get("chars_in"),
        "chars_out": passages.get("chars_out"),
        "gave_up_unresolved": {
            "count": quits["unresolved"],
            at: quits[f"unresolved_{at}"],
            "contexts": sorted(quits["unresolved_contexts"]),
        }
        if "unresolved" in quits
        else None,  # fmt: skip
        "per_bug": bugs,
    }


def _ran_both(x: Mapping[str, Any], y: Mapping[str, Any]) -> list[str]:
    return [i for i, b in x["per_bug"].items() if b["status"] == "ran"
            and y["per_bug"].get(i, {}).get("status") == "ran"]  # fmt: skip


def pair(x: Mapping[str, Any], y: Mapping[str, Any]) -> dict[str, Any]:
    """Discordant bugs between two arms of one chain, on the bugs both ran (and both graded)."""
    common = _ran_both(x, y)
    quits = long_report.bugs_mcnemar([x["per_bug"][i]["gave_up"] for i in common],
                                     [y["per_bug"][i]["gave_up"] for i in common])  # fmt: skip
    graded = [i for i in common if x["per_bug"][i]["resolved"] is not None
              and y["per_bug"][i]["resolved"] is not None]  # fmt: skip

    def on_graded(field: str) -> dict[str, Any] | None:
        return long_report.bugs_mcnemar([x["per_bug"][i][field] for i in graded],
                                        [y["per_bug"][i][field] for i in graded]) \
            if graded else None  # fmt: skip

    return {
        "common_ran": len(common),
        "graded_common": len(graded),
        "resolved_discordant": on_graded("resolved"),
        "give_up_discordant": quits,
        "gave_up_unresolved_discordant": on_graded("gave_up_unresolved"),
    }


def stable_flips(arms: Mapping[str, Any], base: Sequence[str], other: str) -> dict[str, Any] | None:
    """On the bugs every base arm and `other` ran and the base arms agree on, how often `other`
    says otherwise, and which way."""
    if other not in arms or any(b not in arms for b in base):
        return None
    out: dict[str, Any] = {}
    for field in ("resolved", "gave_up", "gave_up_unresolved"):
        seen = [i for i, b in arms[other]["per_bug"].items()
                if b["status"] == "ran" and b[field] is not None
                and all(arms[a]["per_bug"].get(i, {}).get("status") == "ran"
                        and arms[a]["per_bug"][i][field] is not None for a in base)]  # fmt: skip
        stable = [i for i in seen if len({arms[a]["per_bug"][i][field] for a in base}) == 1]
        mine = {i: arms[other]["per_bug"][i][field] for i in stable}
        theirs = {i: arms[base[0]]["per_bug"][i][field] for i in stable}
        up = sum(mine[i] and not theirs[i] for i in stable)
        down = sum(theirs[i] and not mine[i] for i in stable)
        out = {
            **out,
            field: {
                "seen": len(seen),
                "base_agree": len(stable),
                "other_true_base_false": up,
                "other_false_base_true": down,
            },
        }
    return out


def compare(arms_spec: Mapping[str, tuple[Path, str]]) -> dict[str, Any]:
    chains: dict[str, Any] = {}
    for chain in CHAINS:
        found = {
            name: line
            for name, (root, sub) in arms_spec.items()
            if (line := arm_line(root / "runs" / f"{chain}-{MODEL}" / sub)) is not None
        }
        n = found.get("N")
        ratios = {f"{a}_vs_N": {"cost": _ratio(v["cost_usd"], n["cost_usd"]),
                                "cost_per_resolved": _ratio(v["cost_per_resolved"],
                                                            n["cost_per_resolved"])}
                  for a, v in found.items() if a != "N" and n}  # fmt: skip
        pairs = {f"{a}_vs_{b}": pair(found[a], found[b]) for a, b in PAIRS
                 if a in found and b in found}  # fmt: skip
        flips = {f"{o}_vs_N+N2": f for o in ("Ne", "A")
                 if (f := stable_flips(found, ("N", "N2"), o)) is not None}  # fmt: skip
        chains = {**chains, chain: {"arms": found, "ratios": ratios, "pairs": pairs,
                                    "stable_flips": flips}}  # fmt: skip
    models = {v["model"] for c in chains.values() for v in c["arms"].values()}
    warn = [] if len(models) <= 1 else [f"different models in the rows: {sorted(models)}"]
    return {"declared": DECLARED, "warnings": warn, "chains": chains}


COLUMNS = ("cost_usd", "cost_per_resolved", "f2p", "resolved", "calls_ran", "requests",
           "peak_context", "compactions", "cuts", "r", "r_whole", "stopped")  # fmt: skip


def _gave_up(g: Mapping[str, Any], bands: Mapping[str, int]) -> str:
    return (
        f"gave up {g['give_ups']} (>=150k {g['at_or_past_150k']}, no change "
        f"{g['no_code_change']}, said so {g['said_so']}, median context "
        f"{g['median_context']}) by band {dict(bands)}"
    )


def _pair(name: str, p: Mapping[str, Any]) -> str:
    r, q, u = p["resolved_discordant"], p["give_up_discordant"], p["gave_up_unresolved_discordant"]
    res = (f"resolved only {name.split('_vs_')[0]} {r['treated_only']}, only "
           f"{name.split('_vs_')[1]} {r['control_only']}, p {r['p']:.3f} on {p['graded_common']}"
           if r else "resolved: not graded")  # fmt: skip
    return (
        f"  {name}: {p['common_ran']} common; {res}; gave up only left {q['treated_only']}, "
        f"only right {q['control_only']}"
        + (
            f"; unresolved give-ups only left {u['treated_only']}, only right {u['control_only']}"
            if u
            else ""
        )  # fmt: skip
    )


def table(data: Mapping[str, Any]) -> list[str]:
    out = [data["declared"], *(f"WARNING {w}" for w in data["warnings"])]
    for chain, c in data["chains"].items():
        out.append(chain)
        for arm, v in c["arms"].items():
            out.append(f"  {arm}: " + ", ".join(f"{k} {v.get(k)}" for k in COLUMNS))
            out.append(f"    {_gave_up(v['give_ups'], v['give_up_bands'])}")
            out.append(f"    unresolved give-ups (the main measure) {v['gave_up_unresolved']}")
            out.append(f"    cumulative USD at call {v['cumulative_usd']}")
        out.extend(f"  {a}: cost x{v['cost']}, per resolved bug x{v['cost_per_resolved']}"
                   for a, v in c["ratios"].items())  # fmt: skip
        out.extend(_pair(name, p) for name, p in c["pairs"].items())
        out.extend(f"  {name}: {json.dumps(f)}" for name, f in c["stable_flips"].items())
    return out


def parse_arms(specs: Sequence[str]) -> dict[str, tuple[Path, str]]:
    """`NAME=ROOT:DIR` (ROOT may hold a drive colon: the last colon splits)."""
    out: dict[str, tuple[Path, str]] = {}
    for spec in specs:
        name, rest = spec.split("=", 1)
        root, sub = rest.rsplit(":", 1)
        out = {**out, name: (Path(root), sub)}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", action="append", default=[], help="NAME=ROOT:DIR, repeatable")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    data = compare(parse_arms(args.arm or DEFAULT_ARMS))
    for line in table(data):
        print(line)
    if args.json:
        Path(args.json).write_bytes(json.dumps(data, indent=1).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
