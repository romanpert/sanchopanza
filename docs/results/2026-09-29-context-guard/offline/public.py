"""Offline, free: on 40 public trajectories, does the guard carry the values the future used?

Data, cut points and lexical NEEDED labels of docs/results/2026-09-28-context (OpenHands v0.54.0
with Qwen3-Coder-480B on real GitHub issues, `nebius/SWE-rebench-openhands-trajectories`,
CC-BY-4.0), rebuilt into ~/.cache by `benchmarks/context/build.py`. Nothing here was looked at
while the guard's rules were written.

At the cut (the point a compaction would happen) the whole history goes through `guard.build`.
Measured on the NEEDED results of at-risk tools (not Read/Grep/Glob/edits: their values can be
read again): the share whose needed tokens appear in the guard's fact lines (`any`: at least
one; `all`: every one), and the characters the facts take. Baselines at the same characters per
unit, newest result first, as a summary-free harness would keep them:

- `recent`: the most recent at-risk results verbatim, while they fit;
- `index`: `index_of(result, 240)` per result (the stub index of 2026-09-28-context-lean);
- `head`: the first 240 characters per result;
- `guard_no_shape`: the guard with every line of a result ranked in order of appearance
  (errors still first): the rarity rule ablated.

    python docs/results/2026-09-29-context-guard/offline/public.py
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BENCH = ROOT / "benchmarks" / "context"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(BENCH))

from sanchopanza.context import guard  # noqa: E402
from sanchopanza.context.index import index_of  # noqa: E402
from sanchopanza.context.transcript import Call, calls  # noqa: E402


def sibling(name: str) -> Any:
    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, BENCH / f"{name}.py")
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.modules[key] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    return sys.modules[key]


bench_run = sibling("run")


def present(hits: Sequence[str], text: str) -> tuple[bool, bool]:
    found = [h in text for h in hits]
    return any(found), bool(found) and all(found)


def newest_first(history: Sequence[Call], render: Callable[[Call], str], budget: int) -> str:
    kept: list[str] = []
    used = 0
    for call in reversed(history):
        if not guard.at_risk(call):
            continue
        text = render(call)
        if used + len(text) > budget:
            continue
        kept.append(text)
        used += len(text)
    return "\n".join(kept)


FACT_LINES = guard.fact_lines


def no_shape(text: str, limit: int = guard.LINES_PER_CALL) -> list[tuple[str, bool]]:
    """`guard.fact_lines` without the rarity rule: errors first, then order of appearance."""
    lines = FACT_LINES(text, limit=10_000)
    ranked = sorted(enumerate(lines), key=lambda p: (not p[1][1], p[0]))[:limit]
    return [line for _, line in sorted(ranked)]


def facts_text(g: guard.Guard) -> str:
    return "\n".join(f"{f.source}\n{f.line}" for f in g.facts)


def unit_rows(unit: Mapping[str, Any]) -> list[dict[str, Any]]:
    history = calls(unit["history"])
    labels = unit["labels"]
    g = guard.build(unit["history"])
    text = facts_text(g)
    budget = max(len(text), 1)
    guard.fact_lines = no_shape  # type: ignore[assignment]
    try:
        ablated = facts_text(guard.build(unit["history"]))
    finally:
        guard.fact_lines = FACT_LINES  # type: ignore[assignment]
    arms = {
        "guard": text,
        "guard_no_shape": ablated,
        "recent": newest_first(history, lambda c: c.result, budget),
        "index": newest_first(history, lambda c: index_of(c.result, 240), budget),
        "head": newest_first(history, lambda c: c.result[:240], budget),
    }
    rows = []
    for call in history:
        label = labels.get(call.id, {})
        if not label.get("needed") or not guard.at_risk(call):
            continue
        hits = list(label.get("hits") or [])
        if not hits:
            continue
        row: dict[str, Any] = {"unit": unit["unit"], "split": unit["split"], "tool": call.tool}
        for arm, kept in arms.items():
            row[f"{arm}_any"], row[f"{arm}_all"] = present(hits, kept)
        rows.append(row)
    return rows, {arm: len(kept) for arm, kept in arms.items()}, len(history)


def share(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "share": round(k / n, 3) if n else None}


def boot_diff(
    rows: Sequence[Mapping[str, Any]], a: str, b: str, seed: int = 20260929
) -> list[float]:
    units = sorted({r["unit"] for r in rows})
    groups = {u: [r for r in rows if r["unit"] == u] for u in units}
    rng = random.Random(seed)
    diffs = []
    for _ in range(2000):
        sample = [r for u in (rng.choice(units) for _ in units) for r in groups[u]]
        if sample:
            diffs.append((sum(r[a] for r in sample) - sum(r[b] for r in sample)) / len(sample))
    diffs.sort()
    return [round(diffs[int(0.025 * len(diffs))], 3), round(diffs[int(0.975 * len(diffs))], 3)]


def main() -> int:
    units = bench_run.load(bench_run.CACHE / "dataset", "all")
    if not units:
        raise SystemExit("no units: run benchmarks/context/build.py --fetch, then build.py")
    rows: list[dict[str, Any]] = []
    chars: dict[str, list[int]] = {}
    for unit in units:
        found, sizes, _ = unit_rows(unit)
        rows.extend(found)
        for arm, n in sizes.items():
            chars.setdefault(arm, []).append(n)
    arms = ("guard", "guard_no_shape", "recent", "index", "head")
    report: dict[str, Any] = {"units": len(units), "needed_at_risk": len(rows)}
    for split in ("dev", "test", "all"):
        part = rows if split == "all" else [r for r in rows if r["split"] == split]
        report[split] = {
            arm: {
                "any": share(sum(r[f"{arm}_any"] for r in part), len(part)),
                "all": share(sum(r[f"{arm}_all"] for r in part), len(part)),
            }
            for arm in arms
        }
    report["chars_per_unit_median"] = {a: sorted(v)[len(v) // 2] for a, v in chars.items()}
    report["guard_minus"] = {
        b: boot_diff([r for r in rows if r["split"] == "test"], "guard_any", f"{b}_any")
        for b in arms[1:]
    }
    (HERE / "public.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
