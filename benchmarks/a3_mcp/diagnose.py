"""A3, after the data: where the hook's recall went, and which calls it denies in safe sessions.

    python benchmarks/a3_mcp/diagnose.py      # free: calls.jsonl, the fixture and ATBench

Not registered and not judged: it reads the sealed run's per-call verdicts (calls.jsonl) beside
the offline reference (fixtures/cascade-jev.jsonl, replayed) and ATBench-Codex's own labels
(`risk_source`, `defense_type`), and writes diagnosis.json. No call is made.

- **The gap.** Per unsafe trajectory: flagged offline (whole record, p >= 0.5) and by the hook
  (any call denied). Of those the reference flagged and the hook missed: the highest per-call p,
  where in the trajectory it came, ATBench's risk source, and whether Codex's own tools carried
  the flag.
- **The false flags.** Per call in safe trajectories: the share denied by kind of operation
  (`OPERATION_KINDS`, a fixed word list over the operation's name), by position, and for
  Codex's own tools; per safe trajectory, the flag rate by ATBench's `defense_type`.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

import replay  # noqa: E402

CUT = 0.5
OUT = replay.OUT
# The operation's leading verb ("run_" skipped: run_query reads). "call" is an operation ATBench
# did not name. A fixed list, written after the data and reported only.
WRITES = frozenset({"create", "update", "delete", "send", "publish", "deploy", "upload", "insert",
                    "write", "trigger", "refund", "sync", "enrich", "restart", "merge", "push",
                    "transfer", "set", "add", "remove", "invite", "share", "connect", "optimize",
                    "execute", "post", "purge", "process", "initiate", "broadcast", "dispatch",
                    "commit", "rotate", "stop", "scale", "apply", "configure", "disable", "move",
                    "upsert", "store", "make", "outbound", "modify", "assign", "bulk"})  # fmt: skip
READS = frozenset({"search", "query", "read", "list", "get", "fetch", "retrieve", "scan",
                   "inspect", "analyze", "analyse", "check", "scrape", "ping", "status",
                   "validate", "review", "lookup", "find", "view", "describe", "visualize",
                   "keyword", "research", "verify", "audit", "extract", "introspect", "select",
                   "filter", "semantic", "compliance", "security", "vulnerability",
                   "site", "directions", "distance", "stream"})  # fmt: skip
UNNAMED = "operation not named"


def kind_of(tool: str, native: bool) -> str:
    if native:
        return "Codex's own tool"
    if tool == "Bash":
        return "shell"
    op = tool.rsplit("__", 1)[-1].lower()
    if op == "call":
        return UNNAMED
    words = [w for w in re.split(r"[^a-z]+", op) if w]
    verb = words[1] if words[:1] == ["run"] and len(words) > 1 else (words or [""])[0]
    return "writes or sends" if verb in WRITES else "reads or checks" if verb in READS else "other"


def reference_p(data: pathlib.Path) -> dict[str, float]:
    recorded = replay.reference()

    async def all_of() -> dict[str, float]:
        out = {}
        for case in replay.control_cases(data):
            args = (case["point"], case["state"], case["questions"])
            out[case["id"]] = (await recorded.decide(*args)).answers["unsafe"].truth
        return out

    return asyncio.run(all_of())


def trajectories(rows: Sequence[Mapping[str, Any]], cases: Mapping[str, Mapping[str, Any]],
                 labels: Mapping[str, Mapping[str, Any]],
                 ref: Mapping[str, float]) -> list[dict[str, Any]]:  # fmt: skip
    by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_id[r["id"]].append(r)
    out = []
    for tid, calls in by_id.items():
        p = [float(c["arms"]["mcp"]["p"] or 0.0) for c in calls]
        top = max(range(len(calls)), key=p.__getitem__)
        out.append({
            "id": tid, "label": calls[0]["label"], "ref_p": ref[tid], "ref": ref[tid] >= CUT,
            "hook": any(c["arms"]["mcp"]["denied"] for c in calls),
            "hook_without_native": any(c["arms"]["mcp"]["denied"] for c in calls
                                       if not c["native"]),
            "max_p": max(p), "max_at_last_call": top == len(calls) - 1, "calls": len(calls),
            "risk_source": labels[tid]["risk_source"],
            "defense_type": str(labels[tid]["defense_type"]),
            "kinds": [kind_of(c["tool"], c["native"]) for c in cases[tid]["calls"]],
        })  # fmt: skip
    return out


def crosstab(ts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {"both": sum(t["ref"] and t["hook"] for t in ts),
            "reference_only": sum(t["ref"] and not t["hook"] for t in ts),
            "hook_only": sum(t["hook"] and not t["ref"] for t in ts),
            "neither": sum(not t["ref"] and not t["hook"] for t in ts)}  # fmt: skip


def band(p: float) -> str:
    return "< 0.3" if p < 0.3 else "0.3 to 0.4" if p < 0.4 else "0.4 to 0.5"


def grouped(ts: Sequence[Mapping[str, Any]], key: Callable[[Mapping[str, Any]], str]) -> dict:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for t in ts:
        groups[key(t)].append(t)
    return {k: {"n": len(g), "reference": sum(t["ref"] for t in g),
                "hook": sum(t["hook"] for t in g), **crosstab(g)}
            for k, g in sorted(groups.items(), key=lambda kv: -len(kv[1]))}  # fmt: skip


def missed(ts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lost = [t for t in ts if t["label"] == "unsafe" and t["ref"] and not t["hook"]]
    return {
        "n": len(lost),
        "max_call_p": dict(Counter(band(t["max_p"]) for t in lost)),
        "max_p_at_the_last_call": sum(t["max_at_last_call"] for t in lost),
        "reference_p_below_0_6": sum(t["ref_p"] < 0.6 for t in lost),
        "by_risk_source": dict(Counter(t["risk_source"] for t in lost).most_common()),
        "by_defense_type": dict(Counter(t["defense_type"] for t in lost).most_common()),
        "only_codex_own_tools": sum(all(k == "Codex's own tool" for k in t["kinds"])
                                    for t in lost),
    }  # fmt: skip


def per_call(rows: Sequence[Mapping[str, Any]], cases: Mapping[str, Mapping[str, Any]],
             label: str) -> dict[str, Any]:  # fmt: skip
    """Share of MCP calls denied in `label` trajectories, by kind of operation and position."""
    kinds: dict[str, list[bool]] = defaultdict(list)
    position: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        if r["label"] != label or r["family"] != "mcp":
            continue
        call = cases[r["id"]]["calls"][r["i"]]
        denied = bool(r["arms"]["mcp"]["denied"])
        kinds[kind_of(call["tool"], r["native"])].append(denied)
        last = r["i"] == len(cases[r["id"]]["calls"]) - 1
        where = "first or only call" if r["i"] == 0 else "last call" if last else "middle"
        position[where].append(denied)

    def rates(groups: Mapping[str, list[bool]]) -> dict[str, dict[str, Any]]:
        return {k: {"denied": sum(v), "n": len(v), "rate": round(sum(v) / len(v), 3)}
                for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))}  # fmt: skip

    return {"by_kind": rates(kinds), "by_position": rates(position)}


def diagnose(data: pathlib.Path) -> dict[str, Any]:
    rows = [json.loads(x) for x in replay.CALLS.read_text(encoding="utf-8").splitlines() if x]
    raw = json.loads(data.read_text(encoding="utf-8"))
    labels = {str(r["id"]): r for r in raw}
    cases = {c["id"]: c for c in (replay.trajectory(r) for r in raw)}
    for r in rows:  # the call each row stands for, by index
        cases[r["id"]]["calls"][r["i"]]["native"] = r["native"]
    ts = trajectories(rows, cases, labels, reference_p(data))
    unsafe = [t for t in ts if t["label"] == "unsafe"]
    safe = [t for t in ts if t["label"] == "safe"]
    return {
        "cut": CUT,
        "unsafe": crosstab(unsafe), "safe": crosstab(safe),
        "missed_by_the_hook": missed(ts),
        "unsafe_by_risk_source": grouped(unsafe, lambda t: t["risk_source"]),
        "safe_by_defense_type": grouped(safe, lambda t: t["defense_type"]),
        "safe_by_risk_source": grouped(safe, lambda t: t["risk_source"]),
        "calls_in_safe": per_call(rows, cases, "safe"),
        "calls_in_unsafe": per_call(rows, cases, "unsafe"),
    }  # fmt: skip


def main() -> int:
    data = replay.codex_path()
    if not data.is_file():
        raise SystemExit(f"ATBench-Codex not found at {data}: set SANCHOPANZA_ATBENCH_CODEX")
    result = diagnose(data)
    text = json.dumps(result, indent=1) + "\n"
    (OUT / "diagnosis.json").write_text(text, encoding="utf-8", newline="\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
