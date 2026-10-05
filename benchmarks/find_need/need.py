"""Measured need for find_in_repo on every recorded Claude Code session of this machine that ran a
task with a known gold patch, and an offline replay of nudge triggers on them. Free and offline.

    .venv/Scripts/python.exe -m benchmarks.find_need.need swe    # sessions, need table, dev set
    .venv/Scripts/python.exe -m benchmarks.find_need.need real   # real sessions, counts only

Sessions read (stream-json of `claude -p`, main thread only):
- adopt/singles: phase A's Verified singles, N and S (and the S reruns `-nojev1`); six of them
  are dev1's development singles (DEV1).
- adopt/dev-alwaysload and adopt/dev-nudge: the two development probes (34 sessions).
- adopt/runs: phase A and development chains of SWE-smith bugs, one stream per request; the gold
  of request k is bug k's patch. Reported apart: a chain's later requests start with context.
- find-e2e/runs: the localisation run (Read, Grep, Glob and, in arm F, find), N and F. Its
  voided sessions (find-e2e/void) are left out: cut or rerun under amendment 1.

Need, per session: searches (Grep, Glob, and Bash/PowerShell commands that `find_nudge.is_search`
counts) before the first Read of a gold file (`read_searches`, the dev log's measure); when there
is no such Read, before the first view of one (a shell command or Grep naming it).

The development set rule, written before the table was produced and not changed after:
- Eligible: a SWE-bench Verified instance (singles, development probes, find-e2e), not anywhere in
  phase D's draw (`benchmarks/adopt_d/singles-d.json`, drawn ids and spares), with at least one
  control-arm session (N; find-e2e's N).
- A session is hard when it never reached a gold file, or reached it after HARD_SEARCHES or more
  searches. Reaching is the first Read of a gold file, else the first view of one; in find-e2e a
  session that named a gold file in its answer (row.json `claimed`) without reading it reached it
  at its last search.
- Selected: instances where at least one control-arm session is hard, ranked by the share of hard
  sessions over all arms (descending), then the median searches to reach over all arms (never
  counts as 99, descending), then id. The first DEV_SIZE are the set; fewer if fewer qualify.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .replay import RULES, Call, reach, stream_calls

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CACHE = Path.home() / ".cache" / "sanchopanza"
ADOPT = CACHE / "adopt"
VERIFIED = CACHE / "find" / "swebench" / "verified.parquet"
CHAINS = ADOPT / "chains-validated.json"
PHASE_D = REPO / "benchmarks" / "adopt_d" / "singles-d.json"
SCRATCH = CACHE / "find-need"
OUT = HERE / "need-table.json"  # ids, counts and replay facts only, no session text
HARD_SEARCHES = 5
DEV_SIZE = 10
NEVER = 99
DEV1 = ("django__django-15315", "django__django-14752", "matplotlib__matplotlib-23412",
        "django__django-11206", "django__django-12708", "django__django-16631")  # fmt: skip
VARIANT = re.compile(r"-(nojev\d+|limit\d+|killed\d+|crashed\d+|r\d+)$")
INSTANCE_ID = re.compile(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+")
CONTROL_ARMS = ("N", "Nf")


def gold_files(patch: str) -> list[str]:
    """The files a patch changes (the same reading as `benchmarks/find/swebench.gold_files`)."""
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", patch, re.M)))


def verified() -> dict[str, dict[str, Any]]:
    import pyarrow.parquet as pq

    rows = pq.read_table(VERIFIED, columns=["instance_id", "repo", "patch", "difficulty"])
    return {r["instance_id"]: r for r in rows.to_pylist()}


def phase_d_ids() -> set[str]:
    return set(INSTANCE_ID.findall(PHASE_D.read_text(encoding="utf-8")))


def _split_variant(name: str) -> tuple[str, str]:
    m = VARIANT.search(name)
    return (name[: m.start()], m.group(1)) if m else (name, "")


# ---- the sessions --------------------------------------------------------------------------------


def _single(source: str, folder: Path, instance: str, variant: str) -> Iterator[dict[str, Any]]:
    for arm in sorted(p for p in folder.iterdir() if p.is_dir()):
        stream = arm / "stream-1.jsonl"
        if stream.exists():
            yield {"source": source, "instance": instance, "arm": arm.name, "variant": variant,
                   "request": 1, "stream": stream}  # fmt: skip


def locate() -> Iterator[dict[str, Any]]:
    """Every recorded session with a gold patch: where its stream is and what it ran."""
    for folder in sorted((ADOPT / "singles").iterdir()):
        instance, variant = _split_variant(folder.name)
        source = "dev1" if instance in DEV1 else "A-singles"
        yield from _single(source, folder, instance, variant)
    for probe in ("dev-alwaysload", "dev-nudge"):
        for folder in sorted((ADOPT / probe).iterdir()):
            if INSTANCE_ID.fullmatch(folder.name):
                yield from _single(probe, folder, folder.name, "")
    chains = json.loads(CHAINS.read_text(encoding="utf-8"))
    for folder in sorted((ADOPT / "runs").iterdir()):
        chain = max((c for c in chains if folder.name == c or folder.name.startswith(c + "-")),
                    key=len, default=None)  # fmt: skip
        if chain is None:
            continue
        variant = folder.name[len(chain) + 1 :]
        for arm in sorted(p for p in folder.iterdir() if p.is_dir()):
            for k, bug in enumerate(chains[chain]["bugs"], start=1):
                stream = arm / f"stream-{k}.jsonl"
                if stream.exists():
                    yield {"source": "chains", "instance": bug["instance_id"], "chain": chain,
                           "arm": arm.name, "variant": variant, "request": k, "stream": stream,
                           "gold": gold_files(bug["patch"])}  # fmt: skip
    for folder in sorted((CACHE / "find-e2e" / "runs").iterdir()):
        instance, arm = folder.name.rsplit("-", 1)
        row = folder / "row.json"
        claimed = (json.loads(row.read_text(encoding="utf-8")).get("claimed", [])
                   if row.exists() else [])  # fmt: skip
        yield {"source": "find-e2e", "instance": instance, "arm": arm, "variant": "", "request": 1,
               "stream": folder / "stream.jsonl", "claimed": claimed}  # fmt: skip


def _reached(facts: dict[str, Any], where: dict[str, Any], gold: list[str]) -> int | None:
    """Searches to reach a gold file (Read, else view, else a find-e2e answer naming it)."""
    if facts["read_searches"] is not None:
        return facts["read_searches"]
    if facts["view_searches"] is not None:
        return facts["view_searches"]
    claimed = {c.replace("\\", "/") for c in where.get("claimed", [])}
    if claimed & set(gold):
        return facts["searches_total"]
    return None


def resolved(where: dict[str, Any]) -> bool | None:
    """The session's grade: SWE-bench resolved (singles, probes), its bug resolved (chains), or
    every gold file among the first claimed (find-e2e, `all@1`). None: no grade recorded."""
    folder = where["stream"].parent
    grade = folder / ("row.json" if where["source"] == "find-e2e" else "grade.json")
    if not grade.exists():
        return None
    data = json.loads(grade.read_text(encoding="utf-8"))
    if where["source"] == "find-e2e":
        return data.get("all@1")
    if where["source"] == "chains":
        bugs = {b.get("instance_id"): b.get("resolved") for b in data.get("bugs", [])}
        return bugs.get(where["instance"])
    return data.get("resolved")


def fires(calls: list[Call], reached_at: int | None) -> dict[str, Any]:
    out = {}
    for name, rule in RULES.items():
        fire = rule(calls)
        out[name] = None if fire is None else {
            "call": fire.call, "search": fire.search, "kind": fire.kind,
            "before_reach": reached_at is None or fire.call < reached_at}  # fmt: skip
    return out


def describe(where: dict[str, Any], table: dict[str, dict[str, Any]]) -> dict[str, Any]:
    meta, calls = stream_calls(where["stream"])
    row = table.get(where["instance"])
    gold = where.get("gold") or (gold_files(row["patch"]) if row else [])
    facts = reach(calls, gold)
    searches = _reached(facts, where, gold)
    reached_at = facts["read_at"] or facts["view_at"]
    repo = row["repo"] if row else where.get("chain", where["instance"]).split("__")[0]
    return {
        **{k: v for k, v in where.items() if k not in ("stream", "claimed", "gold")},
        "stream": str(where["stream"].relative_to(CACHE)),
        "repo": repo,
        "difficulty": row["difficulty"] if row else None,
        "model": meta.get("model"),
        "gold": gold,
        "resolved": resolved(where),
        "tool_calls": len(calls),
        **facts,
        "reach_searches": searches,
        "hard": searches is None or searches >= HARD_SEARCHES,
        "fires": fires(calls, reached_at),
    }


# ---- tables --------------------------------------------------------------------------------------


def per_instance(rows: list[dict[str, Any]], excluded: set[str]) -> list[dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["source"] != "chains":
            by[r["instance"]].append(r)
    out = []
    for instance, group in by.items():
        reach_n = [NEVER if r["reach_searches"] is None else r["reach_searches"] for r in group]
        control = [r for r in group if r["arm"] in CONTROL_ARMS]
        out.append(
            {
                "instance": instance,
                "repo": group[0]["repo"],
                "difficulty": group[0]["difficulty"],
                "sessions": len(group),
                "hard": sum(r["hard"] for r in group),
                "control_sessions": len(control),
                "control_hard": sum(r["hard"] for r in control),
                "median_reach": statistics.median(reach_n),
                "arms": sorted(
                    f"{r['source']}:{r['arm']}{'-' + r['variant'] if r['variant'] else ''}"
                    f"={'never' if r['reach_searches'] is None else r['reach_searches']}"
                    f"{'' if r['resolved'] is None else ('/ok' if r['resolved'] else '/x')}"
                    for r in group
                ),  # fmt: skip
                "phase_d": instance in excluded,
            }
        )
    return sorted(out, key=lambda r: (-r["hard"] / r["sessions"], -r["median_reach"],
                                      r["instance"]))  # fmt: skip


def dev_set(instances: list[dict[str, Any]]) -> list[str]:
    """The rule of the module docstring, applied to the ranked per-instance table."""
    eligible = [r for r in instances if not r["phase_d"] and r["control_sessions"]
                and r["control_hard"]]  # fmt: skip
    return [r["instance"] for r in eligible[:DEV_SIZE]]


def replay_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per rule: sessions where it fires, of them on a name listing, hard sessions hit before the
    gold was reached, and fires in easy sessions."""
    out = {}
    for name in RULES:
        fired = [r for r in rows if r["fires"][name]]
        out[name] = {
            "fires": len(fired),
            "on_listing": sum(r["fires"][name]["kind"] == "listing" for r in fired),
            "hard_hit_before": sum(r["hard"] and r["fires"][name]["before_reach"] for r in fired),
            "fires_before_reach": sum(r["fires"][name]["before_reach"] for r in fired),
            "easy_fires": sum(not r["hard"] for r in fired),
        }
    return {"sessions": len(rows), "hard": sum(r["hard"] for r in rows), "rules": out}


def dev_log_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The dev log's replay used the 34 probe sessions and the Read-only measure."""
    probe = [{**r, "hard": r["read_searches"] is None or r["read_searches"] >= HARD_SEARCHES,
              "fires": {k: (None if v is None else {**v, "before_reach": r["read_at"] is None
                                                    or v["call"] < r["read_at"]})
                        for k, v in r["fires"].items()}}
             for r in rows if r["source"] in ("dev-alwaysload", "dev-nudge")]  # fmt: skip
    return {
        **replay_summary(probe),
        "hard_sessions": sorted(f"{r['instance']} {r['arm']}" for r in probe if r["hard"]),
    }


def run_swe() -> dict[str, Any]:
    table = verified()
    excluded = phase_d_ids()
    rows = [describe(where, table) for where in locate()]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "sessions.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    singles = [r for r in rows if r["source"] != "chains"]
    chains = [r for r in rows if r["source"] == "chains"]
    first = [r for r in chains if r["request"] == 1 or r["arm"].endswith(("f", "fn"))]
    instances = per_instance(rows, excluded)
    picked = dev_set(instances)
    report = {
        "rule": "see need.py docstring",
        "hard_searches": HARD_SEARCHES,
        "counts": {
            "sessions": len(rows),
            "single_sessions": len(singles),
            "chain_requests": len(chains),
            "by_source": Counter(r["source"] for r in rows),
            "models": Counter(r["model"] for r in rows),
            "instances": len(instances),
            "hard_single_sessions": sum(r["hard"] for r in singles),
            "hard_control_single_sessions": sum(
                r["hard"] for r in singles if r["arm"] in CONTROL_ARMS
            ),  # fmt: skip
            "control_single_sessions": sum(r["arm"] in CONTROL_ARMS for r in singles),
            "hard_chain_requests": sum(r["hard"] for r in chains),
            "hard_chain_requests_fresh_or_first": sum(r["hard"] for r in first),
            "chain_requests_fresh_or_first": len(first),
        },
        "dev_log_check": dev_log_check(rows),
        "replay_singles": replay_summary(singles),
        "replay_chains_fresh_or_first": replay_summary(first),
        "instances": instances,
        "ranked_hard_control": [r for r in instances if r["control_hard"]],
        "dev_set": picked,
    }
    OUT.write_text(json.dumps(report, indent=1, default=dict), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("what", choices=("swe", "real"))
    args = parser.parse_args(argv)
    if args.what == "real":
        from .real import run_real

        print(json.dumps(run_real(), indent=1, default=dict))
        return 0
    report = run_swe()
    brief = {k: report[k] for k in ("counts", "dev_log_check", "replay_singles",
                                    "replay_chains_fresh_or_first", "dev_set")}  # fmt: skip
    print(json.dumps(brief, indent=1, default=dict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
