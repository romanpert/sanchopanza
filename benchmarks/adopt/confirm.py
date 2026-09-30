"""Verdicts of the adoption study's confirmation, as `prereg-confirm.md` fixes them. Free.

    python benchmarks/adopt/confirm.py B              # the development pilot and the rule to run C
    python benchmarks/adopt/confirm.py C              # the long-session stratum (sealed only)
    python benchmarks/adopt/confirm.py A              # the confirmation (sealed only)
    python benchmarks/adopt/confirm.py A --blocks     # every guard block of the S arms, to read

Everything but B refuses to read until the seal holds: `prereg-confirm.sha256` equals the hash
of the files its manifest names, as they are now (`benchmarks/candor/seal.py`).

- A request **ran** when it was not NOT RUN, was not cut by the timeout and reported a result.
  An arm is **complete** when every request ran. Only pairs where both arms are complete enter
  the cost and exploration statistics; the others are listed apart with their cost over the
  requests both arms ran.
- Cost: list price of every Claude Code call (`run.call_cost`) plus Jev's journal (per arm; it
  is added whole to the cost over common requests too, being cents).
- Exploration: per request that ran, the main thread's tool calls (no subagent's) before its
  first edit; the ratio per request is (treatment + 1) / (control + 1).
- H3 reads the verdict of each block from `false-blocks.jsonl` beside the prereg
  ({"key": ..., "false": true|false, "why": ...}); a block with no verdict leaves H3 pending.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import statistics
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run import MODELS, ROOT, RUNS  # noqa: E402

REPO = HERE.parents[1]
RESULTS = REPO / "docs" / "results" / "2026-09-30-adopt"
SEAL = RESULTS / "prereg-confirm.sha256"
MANIFEST = RESULTS / "prereg-confirm.manifest.json"
VERDICTS = RESULTS / "false-blocks.jsonl"
SINGLES = ROOT / "singles"
SEED, RESAMPLES = 20261002, 10_000
EDITS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELLS = ("Bash", "PowerShell")
RULE_COST, RULE_BUGS = 0.90, 1  # B -> run C, and C's "lever shown": Sm <= 0.90 of N, >= N - 1
MARGIN = {"chains": 3, "related": 1, "singles": 2}  # H1: bugs the S arm may resolve fewer
B_CHAIN = "encode__starlette-long-1r1"
PHASE_MODEL = {"A": MODELS["haiku"], "B": MODELS["sonnet"], "C": MODELS["sonnet"]}
CONTROL = {"Sm": "N", "Sf": "Nf", "S": "N"}


# ---- statistics (pure) ---------------------------------------------------------------------------


def paired_interval(
    pairs: Sequence[tuple[float, float]], stat: Callable[[list[tuple[float, float]]], float]
) -> tuple[float, float, float]:
    """(statistic, low, high): percentile 95 % interval over paired resamples of the tasks."""
    rng = random.Random(SEED)
    items = list(pairs)
    draws = sorted(stat([rng.choice(items) for _ in items]) for _ in range(RESAMPLES))
    return stat(items), draws[int(0.025 * RESAMPLES)], draws[int(0.975 * RESAMPLES) - 1]


def median_ratio(pairs: list[tuple[float, float]]) -> float:
    """Median over pairs of treatment/control. Callers pass positive controls only."""
    return statistics.median(t / c for t, c in pairs)


def total_difference(pairs: list[tuple[float, float]]) -> float:
    return sum(t - c for t, c in pairs)


def ratio_verdict(point: float, high: float) -> str:
    if point < 1 and high < 1:
        return "confirmed"
    return "direction only, not confirmed" if point < 1 else "not confirmed"


# ---- reading the runs ----------------------------------------------------------------------------


def events(stream: Path) -> list[dict[str, Any]]:
    out = []
    for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def blocks_of(item: dict[str, Any]) -> list[dict[str, Any]]:
    content = (item.get("message") or {}).get("content") or []
    return [b for b in content if isinstance(b, dict)]


def exploration(stream: Path) -> int:
    """The main thread's tool calls before its first edit (all of them if it never edits).
    A subagent's calls carry `parent_tool_use_id` and are not counted."""
    count = 0
    for event in events(stream):
        if event.get("type") != "assistant" or event.get("parent_tool_use_id"):
            continue
        for block in blocks_of(event):
            if block.get("type") != "tool_use":
                continue
            if block.get("name") in EDITS:
                return count
            count += 1
    return count


def result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, list):
        return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return str(content)


def guard_blocks(stream: Path, key: str) -> tuple[list[dict[str, Any]], int]:
    """(each PreToolUse denial with the command it stopped, shell commands asked), subagents
    included: a block of a subagent's command is a block of the arm."""
    found, shells, asked = [], 0, {}
    for event in events(stream):
        for block in blocks_of(event):
            if block.get("type") == "tool_use":
                asked[str(block.get("id"))] = block
                shells += block.get("name") in SHELLS
            elif block.get("type") == "tool_result" and block.get("is_error"):
                text = result_text(block)
                if text.startswith("PreToolUse:") and "denied" in text.lower():
                    use = asked.get(str(block.get("tool_use_id")), {})
                    found.append({"key": f"{key}/{stream.stem}/{block.get('tool_use_id')}",
                                  "tool": use.get("name"), "input": use.get("input"),
                                  "message": text[:400]})  # fmt: skip
    return found, shells


def ran(call: dict[str, Any]) -> bool:
    return (not str(call.get("status", "")).startswith("NOT RUN") and call.get("exit") != -9
            and call.get("subtype") is not None)  # fmt: skip


def arm_result(evidence: Path, model: str) -> dict[str, Any] | None:
    """Resolved bugs, cost and exploration per request, completeness and adoption of one task
    and arm; None when it has not run or been graded, or ran with another model."""
    row_path, grade_path = evidence / "row.json", evidence / "grade.json"
    if not row_path.exists() or not grade_path.exists():
        return None
    row = json.loads(row_path.read_text(encoding="utf-8"))
    if row.get("model") != model:
        return None
    grade = json.loads(grade_path.read_text(encoding="utf-8"))
    requests = {c["request"]: c for c in row["calls"]}
    done = {k for k, c in requests.items() if ran(c)}
    tools: dict[str, int] = {}
    for k in done:
        for name, n in (requests[k].get("tools") or {}).items():
            tools[name] = tools.get(name, 0) + n
    resolved = grade["resolved"]
    return {"resolved": int(resolved) if isinstance(resolved, bool) else resolved,
            "complete": len(done) == len(requests), "ran": sorted(done),
            "request_cost": {k: c.get("cost_usd", 0.0) for k, c in requests.items()},
            "jev": row.get("jev_usd", 0.0),
            "cost": sum(c.get("cost_usd", 0.0) for c in row["calls"]) + row.get("jev_usd", 0.0),
            "exploration": {k: exploration(evidence / f"stream-{k}.jsonl") for k in sorted(done)
                            if (evidence / f"stream-{k}.jsonl").exists()},
            "find_calls": tools.get("mcp__sanchopanza__find_in_repo", 0),
            "skill_calls": tools.get("Skill", 0),
            "memory": memory_shown(evidence)}  # fmt: skip


def common_cost(treat: dict[str, Any], control: dict[str, Any]) -> tuple[float, float, list]:
    """Cost of each arm over the requests both ran, and those requests."""
    both = sorted(set(treat["ran"]) & set(control["ran"]))
    t = sum(treat["request_cost"][k] for k in both) + treat["jev"]
    c = sum(control["request_cost"][k] for k in both) + control["jev"]
    return t, c, both


def memory_shown(evidence: Path) -> dict[str, int]:
    path, out = evidence / "memory.jsonl", {"prompts": 0, "injected": 0, "records": 0}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("event") == "UserPromptSubmit":
                shown = event.get("shown") or []
                out = {"prompts": out["prompts"] + 1, "injected": out["injected"] + bool(shown),
                       "records": out["records"] + len(shown)}  # fmt: skip
    return out


def pairs_of(
    tasks: list[str], treat: str, control: str, root: Path, model: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Per task the two arms' results; and the tasks missing an arm (not run, not graded, or
    another model), which leave the verdicts that need them undecided."""
    rows, missing = [], []
    for task in tasks:
        t = arm_result(root / task / treat, model)
        c = arm_result(root / task / control, model)
        if t is None or c is None:
            missing.append(task)
        else:
            rows.append({"task": task, "treat": t, "control": c})
    return rows, missing


# ---- the verdicts --------------------------------------------------------------------------------


def success(rows: list[dict[str, Any]], margin: int, missing: list[str]) -> dict[str, Any]:
    """The point difference decides; its paired interval is reported. A missing task leaves
    it undecided (None)."""
    pairs = [(float(r["treat"]["resolved"]), float(r["control"]["resolved"])) for r in rows]
    point, low, high = paired_interval(pairs, total_difference) if pairs else (0.0, 0.0, 0.0)
    holds = None if missing or not pairs else point >= -margin
    return {"treat": sum(p[0] for p in pairs), "control": sum(p[1] for p in pairs),
            "difference": point, "interval": [low, high], "margin": -margin,
            "holds": holds}  # fmt: skip


def apart(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(pairs where both arms are complete, the others with their common-request costs)."""
    whole = [r for r in rows if r["treat"]["complete"] and r["control"]["complete"]]
    rest = []
    for r in rows:
        if r in whole:
            continue
        t, c, both = common_cost(r["treat"], r["control"])
        rest.append({"task": r["task"], "common_requests": both, "treat_usd": round(t, 4),
                     "control_usd": round(c, 4)})  # fmt: skip
    return whole, rest


def cheaper(rows: list[dict[str, Any]]) -> dict[str, Any]:
    whole, rest = apart(rows)
    pairs = [(r["treat"]["cost"], r["control"]["cost"]) for r in whole]
    if not pairs:
        return {"verdict": "no data", "incomplete": rest}
    point, low, high = paired_interval(pairs, median_ratio)
    return {"pairs": len(pairs), "median_ratio": round(point, 4),
            "interval": [round(low, 4), round(high, 4)],
            "treat_usd": round(sum(p[0] for p in pairs), 2),
            "control_usd": round(sum(p[1] for p in pairs), 2),
            "verdict": ratio_verdict(point, high), "incomplete": rest}  # fmt: skip


def explores_less(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [(r["treat"]["exploration"][k] + 1.0, r["control"]["exploration"][k] + 1.0)
             for r in rows for k in range(2, 6)
             if k in r["treat"]["exploration"] and k in r["control"]["exploration"]]  # fmt: skip
    if not pairs:
        return {"verdict": "no data"}
    point, low, high = paired_interval(pairs, median_ratio)
    return {"requests": len(pairs), "median_ratio": round(point, 4),
            "interval": [round(low, 4), round(high, 4)],
            "verdict": ratio_verdict(point, high)}  # fmt: skip


def read_verdicts() -> dict[str, dict[str, Any]]:
    out = {}
    if VERDICTS.exists():
        for line in VERDICTS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                v = json.loads(line)
                out[v["key"]] = v
    return out


def false_blocks(found: list[dict[str, Any]], shells: int) -> dict[str, Any]:
    verdicts = read_verdicts()
    pending = [b["key"] for b in found if b["key"] not in verdicts]
    false = [b["key"] for b in found if verdicts.get(b["key"], {}).get("false")]
    rate = len(false) / shells if shells else 0.0
    lost = [k for k in false if lost_to_block(k)]
    return {"blocks": len(found), "false": len(false), "shell_commands": shells,
            "rate": round(rate, 4), "lost_bugs": lost, "pending": pending,
            "holds": None if pending else rate <= 0.01 and not lost}  # fmt: skip


def resolved_at(evidence: Path, request: int) -> bool:
    grade = json.loads((evidence / "grade.json").read_text(encoding="utf-8"))
    bugs = grade.get("bugs")
    return bool(bugs[request - 1]["resolved"] if bugs else grade["resolved"])


def lost_to_block(key: str) -> bool:
    """A false block in a request whose bug the control arm resolved and the S arm did not."""
    task, arm, stream = key.split("/")[:3]
    request = int(stream.split("-")[1])
    root = RUNS if (RUNS / task).exists() else SINGLES
    return resolved_at(root / task / CONTROL[arm], request) and not resolved_at(
        root / task / arm, request
    )


def long_session(row: dict[str, Any] | None) -> dict[str, Any]:
    """B's rule to run C, and C's "lever shown" per pair: cost over the requests both arms ran."""
    if row is None:
        return {"holds": None, "why": "not graded yet"}
    t, c = row["treat"], row["control"]
    t_usd, c_usd, both = common_cost(t, c)
    ratio = t_usd / c_usd if c_usd else 1.0
    ok = ratio <= RULE_COST and t["resolved"] >= c["resolved"] - RULE_BUGS
    return {"holds": ok, "cost_ratio": round(ratio, 4), "resolved": [t["resolved"], c["resolved"]],
            "common_requests": both, "complete": [t["complete"], c["complete"]]}  # fmt: skip


def held(kind: str) -> list[str]:
    if kind == "singles":
        rows = json.loads((HERE / "singles-selected.json").read_text(encoding="utf-8"))
        return [r["instance_id"] for r in rows if r["split"] == "held"]
    name = "related-selected.json" if kind == "related" else "chains-selected.json"
    chains = json.loads((HERE / name).read_text(encoding="utf-8"))["chains"]
    return [c["chain"] for c in chains if c["split"] == "held"]


def c_tasks() -> list[str]:
    """The held-out combined chains the rule picked: per repository, the first candidate that
    validated (`combined.py validate held`)."""
    import combined
    import validate

    done, chosen, out = validate.validated(), set(), []
    for name, first, _ in combined.held_candidates(combined.selection()):
        repo = done.get(first, {}).get("repo")
        if repo not in chosen and done.get(name, {}).get("valid"):
            chosen.add(repo)
            out.append(name)
    return out


def blocks_in(arms: list[tuple[str, str, Path]], model: str) -> tuple[list[dict], int]:
    found, shells = [], 0
    for task, arm, root in arms:
        result = arm_result(root / task / arm, model)
        for k in result["ran"] if result else []:
            f, s = guard_blocks(root / task / arm / f"stream-{k}.jsonl", f"{task}/{arm}")
            found, shells = [*found, *f], shells + s
    return found, shells


def a_arms() -> list[tuple[str, str, Path]]:
    chains = [*held("chains"), *held("related")]
    return [*((t, "Sm", RUNS) for t in chains), *((t, "Sf", RUNS) for t in held("related")),
            *((t, "S", SINGLES) for t in held("singles"))]  # fmt: skip


def phase_a() -> dict[str, Any]:
    model = PHASE_MODEL["A"]
    ch, ch_missing = pairs_of([*held("chains"), *held("related")], "Sm", "N", RUNS, model)
    rel, rel_missing = pairs_of(held("related"), "Sf", "Nf", RUNS, model)
    si, si_missing = pairs_of(held("singles"), "S", "N", SINGLES, model)
    found, shells = blocks_in(a_arms(), model)
    h1 = {"chains": success(ch, MARGIN["chains"], ch_missing),
          "related": success(rel, MARGIN["related"], rel_missing),
          "singles": success(si, MARGIN["singles"], si_missing)}  # fmt: skip
    h2, explore = cheaper(ch), explores_less(apart(rel)[0])
    return {"missing": {"chains": ch_missing, "related": rel_missing, "singles": si_missing},
            "H1": h1, "H2": h2, "H2_singles_reported": cheaper(si),
            "H_new_session_exploration": explore, "H3": false_blocks(found, shells),
            "H4": adoption([*ch, *rel, *si]),
            "H_session": decided(h1["chains"]["holds"], h2["verdict"] == "confirmed"),
            "H_new_session": decided(h1["related"]["holds"],
                                     explore["verdict"] == "confirmed")}  # fmt: skip


def decided(success_holds: bool | None, other: bool) -> bool | None:
    return None if success_holds is None else success_holds and other


def adoption(rows: list[dict[str, Any]]) -> dict[str, int]:
    t = [r["treat"] for r in rows]
    return {"find_calls": sum(x["find_calls"] for x in t),
            "skill_calls": sum(x["skill_calls"] for x in t),
            "memory_prompts": sum(x["memory"]["prompts"] for x in t),
            "memory_injected": sum(x["memory"]["injected"] for x in t),
            "memory_records": sum(x["memory"]["records"] for x in t)}  # fmt: skip


# ---- the seal ------------------------------------------------------------------------------------


def seal_holds() -> bool:
    """The seal file exists and still matches the files its manifest names."""
    if not SEAL.exists() or not MANIFEST.exists():
        return False
    spec = importlib.util.spec_from_file_location("adopt_seal", REPO / "benchmarks" / "candor" /
                                                  "seal.py")  # fmt: skip
    assert spec is not None and spec.loader is not None
    seal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seal)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for path, digest in manifest.items():
        if not (REPO / path).exists() or seal.digest(REPO / path) != digest:
            return False
    import hashlib

    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    return combined.hexdigest() == SEAL.read_text(encoding="utf-8").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("A", "B", "C"))
    parser.add_argument("--blocks", action="store_true", help="list the S arms' guard blocks")
    args = parser.parse_args(argv)
    if args.phase != "B" and not seal_holds():
        raise SystemExit("the confirmation is not sealed (or the seal no longer matches): "
                         "nothing held out is read")  # fmt: skip
    model = PHASE_MODEL[args.phase]
    if args.phase == "B":
        tasks = [B_CHAIN]
    elif args.phase == "C":
        tasks = c_tasks()
    if args.blocks:
        arms = a_arms() if args.phase == "A" else [(t, "Sm", RUNS) for t in tasks]
        for block in blocks_in(arms, model)[0]:
            print(json.dumps(block, ensure_ascii=False))
        return 0
    if args.phase == "A":
        out = phase_a()
    else:
        rows, missing = pairs_of(tasks, "Sm", "N", RUNS, model)
        per_task = [{"task": r["task"], **long_session(r)} for r in rows]
        out = {args.phase: per_task, "missing": missing, "tasks": tasks}
        if args.phase == "C":
            out["lever_shown"] = None if missing else all(p["holds"] for p in per_task)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
