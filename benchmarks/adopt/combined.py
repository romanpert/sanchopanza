"""Combined chains: two chains of one repository asked in ONE Claude Code session, in one working
copy, graded per chain. A 1M-window model reaches in them the 300k-400k context of the owner's
long sessions, which one chain (~160k at its end) never does. Free except `validate` (Docker).

    python benchmarks/adopt/combined.py plan                  # pairs, bugs, swaps, why not
    python benchmarks/adopt/combined.py validate <name|held> [--repo pydantic]  # Docker
    python benchmarks/adopt/combined.py report <name> [--rep N]   # per chain, after run.py grade

Combining. The first chain goes as validated. A bug of the second chain that conflicts with a
bug before it (hunks overlapping in a file, or a FAIL_TO_PASS test in common: the two could not
be undone together, or one test would grade two bugs) is replaced by the second chain's next
spare, in the drawn order, that conflicts with nothing before it and, when the second chain is a
related one, shares a code file with a bug before it. Only a development pair may swap: held-out
bugs stay as sealed, and a held-out pair that does not fit as it is is not used. Every patch is
normalised (`related.normalize`): two chains of one repository may touch one file, and
SWE-smith's end-of-file hunks would not apply twice. The combined chain is validated like any
chain (`validate.check`): every bug's FAIL_TO_PASS fails with all ten bugs in, and passes when
only that bug is fixed; PASS_TO_PASS* is taken again with all ten in.

Pairs. Development: `encode__starlette-1` then `encode__starlette-rel-1` (the long-session
pilot). Held out: per repository in `chains.PLAN` order, the first pair (an independent chain of
`tasks.md`, a related chain of `tasks-related.md`, each in sealed order) that fits with no swap
and validates. The result goes into chains-validated.json as `kind: combined`, so `run.py` runs
and grades it like any chain; `report` splits grade and cost by the chain each bug came from.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chains  # noqa: E402
import related  # noqa: E402

# `<repo>-long-<i>r<j>`: independent chain i, then related chain j, in one session.
DEV_PAIRS = (("encode__starlette-long-1r1", "encode__starlette-1", "encode__starlette-rel-1"),)


# ---- combining (pure) ----------------------------------------------------------------------------


def normed(bug: dict[str, Any], part: str) -> dict[str, Any]:
    original = bug.get("patch_original", bug["patch"])
    return {**bug, "patch": related.normalize(bug["patch"]), "patch_original": original,
            "part": part}  # fmt: skip


def conflict(bug: dict[str, Any], before: list[dict[str, Any]]) -> str:
    """Why `bug` cannot sit after `before` in one image ("" when it can)."""
    mine, tests = related.spans(bug["patch"]), set(bug["FAIL_TO_PASS"])
    for other in before:
        if related.overlaps(mine, related.spans(other["patch"])):
            return f"hunks overlap {short(other)}"
        if tests & set(other["FAIL_TO_PASS"]):
            return f"FAIL_TO_PASS shared with {short(other)}"
    return ""


def short(bug: dict[str, Any]) -> str:
    return bug["instance_id"].rsplit(".", 1)[1]


def combine(
    first: dict[str, Any], second: dict[str, Any], spares: list[dict[str, Any]], *,
    may_swap: bool,
) -> dict[str, Any]:  # fmt: skip
    """{"bugs": [...] or None, "swaps": [...], "why": [...]}: the ten bugs in order, each with its
    `part`, or None with the reasons when the pair does not fit."""
    linked = second.get("kind") == "related"
    bugs = [normed(b, first["chain"]) for b in first["bugs"]]
    why = [f"{short(b)}: {c}" for i, b in enumerate(bugs) if (c := conflict(b, bugs[:i]))]
    swaps: list[str] = []
    if why:  # the first chain is taken as it is, so a conflict inside it ends the pair
        return {"bugs": None, "swaps": swaps, "why": why}
    pool = [normed(s, second["chain"]) for s in spares]
    for bug in (normed(b, second["chain"]) for b in second["bugs"]):
        reason = conflict(bug, bugs)
        if not reason:
            bugs.append(bug)
            continue
        why.append(f"{short(bug)}: {reason}")
        fitting = (s for s in pool if fits_as_spare(s, bugs, linked))
        spare = next(fitting, None) if may_swap else None
        if spare is None:
            return {"bugs": None, "swaps": swaps, "why": why}
        pool.remove(spare)
        swaps.append(f"{short(bug)} -> {short(spare)}")
        bugs.append(spare)
    return {"bugs": bugs, "swaps": swaps, "why": why}


def fits_as_spare(spare: dict[str, Any], before: list[dict[str, Any]], linked: bool) -> bool:
    if conflict(spare, before):
        return False
    return not linked or bool(related.code_files(spare) & files(before))


def files(bugs: list[dict[str, Any]]) -> set[str]:
    return set().union(*(related.code_files(b) for b in bugs)) if bugs else set()


def unlinked(bugs: list[dict[str, Any]], part: str) -> list[str]:
    """Bugs of a related `part`, after its first (the seed of its draw), that share no code file
    with any bug before them."""
    start = next((i for i, b in enumerate(bugs) if b["part"] == part), len(bugs))
    return [short(b) for i, b in enumerate(bugs) if b["part"] == part and i > start
            and not related.code_files(b) & files(bugs[:i])]  # fmt: skip


# ---- the pairs -----------------------------------------------------------------------------------


def selection() -> dict[str, dict[str, Any]]:
    return {c["chain"]: c for c in [*chains.full(), *related.full()]}


def spares_of(name: str, chain: dict[str, Any], picked: dict[str, dict[str, Any]]) -> list[dict]:
    """The chain's drawn spares that validation did not already put into it."""
    inside = {b["instance_id"] for b in chain["bugs"]}
    return [s for s in picked[name]["spares"] if s["instance_id"] not in inside]


def held_candidates(picked: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(combined name, independent, related) for every held-out pair, repositories in
    `chains.PLAN` order and chains in sealed order within each."""
    out = []
    for repo, _, _ in chains.PLAN:
        mine = [c for c in picked.values() if c["repo"] == repo and c["split"] == "held"]
        plain = [c["chain"] for c in mine if c.get("kind") != "related"]
        linked = [c["chain"] for c in mine if c.get("kind") == "related"]
        base = repo.split("/")[1].split(".")[0]
        out += [(f"{base}-long-{a.rsplit('-', 1)[1]}r{b.rsplit('-', 1)[1]}", a, b)
                for a in plain for b in linked]  # fmt: skip
    return out


def build(
    name: str, first: str, second: str, done: dict[str, dict[str, Any]],
    picked: dict[str, dict[str, Any]],
) -> dict[str, Any]:  # fmt: skip
    """The combined chain from the two validated chains (not yet validated itself)."""
    a, b = done[first], done[second]
    split = "dev" if a["split"] == b["split"] == "dev" else "held"
    out = combine(a, b, spares_of(second, b, picked), may_swap=split == "dev")
    return {"chain": name, "repo": a["repo"], "image": a["image"], "split": split,
            "kind": "combined", "parts": [first, second], **out}  # fmt: skip


# ---- Docker --------------------------------------------------------------------------------------


def validate_one(chain: dict[str, Any]) -> dict[str, Any]:
    import docker_env
    import validate

    started = time.time()
    docker_env.pull(chain["image"])
    bugs = [dict(b) for b in chain["bugs"]]
    records, bad = validate.check(chain, bugs)
    for bug, record in zip(bugs, records, strict=True):
        bug["PASS_TO_PASS_STAR"] = record.pop("PASS_TO_PASS_STAR")
    history = [[r["instance_id"] + (" ok" if r["valid"] else " INVALID") for r in records]]
    return {**{k: v for k, v in chain.items() if k not in ("bugs", "why")},
            "why_swapped": chain["why"], "tag": validate.tag_of(chain["chain"]),
            "valid": not bad, "bugs": bugs, "records": records, "history": history,
            "seconds": round(time.time() - started)}  # fmt: skip


def validate_named(name: str, repo: str = "") -> int:
    import validate

    done, picked = validate.validated(), selection()
    if name == "held":  # the rule: per repository, the first pair that fits and validates
        chosen: set[str] = set()
        for n, a, b in held_candidates(picked):
            if repo not in picked[a]["repo"] or picked[a]["repo"] in chosen:
                continue
            if a not in done or b not in done:
                print(f"{n}: {a} or {b} not validated on its own yet; run validate.py first")
                return 1
            if not (done[a]["valid"] and done[b]["valid"]):
                print(f"{n}: {a} or {b} did not validate on its own; the pair is not used")
                continue
            chain = build(n, a, b, done, picked)
            if chain["bugs"] is None:
                print(f"{n}: does not fit ({'; '.join(chain['why'])})")
            elif finish(chain)["valid"]:
                chosen.add(picked[a]["repo"])
        return 0
    pairs = {n: (a, b) for n, a, b in (*DEV_PAIRS, *held_candidates(picked))}
    if name not in pairs:
        raise SystemExit(f"unknown combined chain {name}; known: {sorted(pairs)}")
    if not all(done.get(n, {}).get("valid") for n in pairs[name]):
        print(f"{name}: {pairs[name]} must each validate on its own first")
        return 1
    chain = build(name, *pairs[name], done, picked)
    if chain["bugs"] is None:
        print(f"{name}: does not fit ({'; '.join(chain['why'])})")
        return 1
    return 0 if finish(chain)["valid"] else 1


def finish(chain: dict[str, Any]) -> dict[str, Any]:
    import validate

    result = validate_one(chain)
    validate.save(result)
    print(result["chain"], "valid" if result["valid"] else "INVALID", result["history"],
          f"swaps {result['swaps']}", f"{result['seconds']} s", flush=True)  # fmt: skip
    return result


# ---- report --------------------------------------------------------------------------------------


def split_by_part(chain: dict[str, Any], grade: dict[str, Any], row: dict[str, Any]) -> list[dict]:
    """Resolved and cost per part, from run.py's grade.json and row.json of one arm."""
    parts = [b["part"] for b in chain["bugs"]]  # request k asks bug k (NOT RUN rows carry no id)
    graded = [g["instance_id"] for g in grade["bugs"]]
    if graded != [b["instance_id"] for b in chain["bugs"]]:
        raise SystemExit(f"{chain['chain']}: the grade's bugs are not the chain's, in its order")
    asked = {c["request"]: c.get("instance_id") for c in row["calls"] if c.get("instance_id")}
    if any(asked[k] != graded[k - 1] for k in asked):
        raise SystemExit(f"{chain['chain']}: a request asked another bug than the chain's")
    out = []
    for part in chain["parts"]:
        bugs = [g for g, p in zip(grade["bugs"], parts, strict=True) if p == part]
        calls = [c for c in row["calls"] if parts[c["request"] - 1] == part]
        out.append({"part": part, "resolved": sum(g["resolved"] for g in bugs), "bugs": len(bugs),
                    "cost_usd": round(sum(c.get("cost_usd", 0.0) for c in calls), 4),
                    "compactions": sum(len(c.get("compactions") or []) for c in calls),
                    "not_run": sum(str(c.get("status", "")).startswith("NOT RUN")
                                   for c in calls)})  # fmt: skip
    return out


def report(name: str, rep: int) -> int:
    import validate
    from run import ARM_SPECS, RUNS, run_name

    chain = validate.validated()[name]
    for arm in ARM_SPECS:
        evidence = RUNS / run_name(name, rep) / arm
        if not (evidence / "grade.json").exists():
            continue
        grade = json.loads((evidence / "grade.json").read_text(encoding="utf-8"))
        row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
        for part in split_by_part(chain, grade, row):
            print(json.dumps({"chain": name, "arm": arm, **part}))
    return 0


# ---- entry ---------------------------------------------------------------------------------------


def plan() -> int:
    import validate

    done, picked = validate.validated(), selection()
    for name, a, b in (*DEV_PAIRS, *held_candidates(picked)):
        have = {n: done.get(n) or picked[n] for n in (a, b)}  # validated if it is, else as drawn
        chain = build(name, a, b, have, picked)
        state = "fits" if chain["bugs"] else "does not fit"
        tail = ""
        if chain["bugs"]:
            tail = f" unlinked {unlinked(chain['bugs'], b)}" if picked[b].get("kind") else ""
        print(f"{name} ({chain['split']}): {a} + {b}: {state}; swaps {chain['swaps']}; "
              f"conflicts {chain['why']}{tail}; validated alone {[n in done for n in (a, b)]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "validate", "report"))
    parser.add_argument("name", nargs="?", default="")
    parser.add_argument("--rep", type=int, default=1)
    parser.add_argument("--repo", default="", help="validate held: one repository (disk)")
    args = parser.parse_args(argv)
    if args.action == "plan":
        return plan()
    if not args.name:
        raise SystemExit("name the combined chain (or `held` for validate)")
    if args.action == "validate":
        return validate_named(args.name, args.repo)
    return report(args.name, args.rep)


if __name__ == "__main__":
    raise SystemExit(main())
