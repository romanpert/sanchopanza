"""The verdict of lot jev114-checkdone, free: reads `done-scored.jsonl` and writes `analysis.json`.

    python benchmarks/jev114/checkdone114_analysis.py

The rule is docs/results/2026-10-16-checkdone114/prereg.md, "Metric and verdict":

- block = p(done) < cut; right = block on a `not_done` stop or no block on a `done` one;
- cuts read from the code: 1.13 at `Thresholds().done`, 1.14 at its `MODEL_PROFILES` value;
- primary: right decisions, 1.14 at the profile minus 1.13 at its cut, exact McNemar and a 95 %
  paired bootstrap over user-task clusters (`l4_stats`, 10,000 replicas, its seed);
  `jev114_paired.verdict` on that interval;
- guard: false blocks among `done` stops, 1.14 minus 1.13, cluster interval's upper bound at
  most +2 points;
- an arm missing an answer on more than 2 % of the stops withholds a favourable verdict.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import jev114_paired as paired  # noqa: E402
import l4_stats  # noqa: E402
import lot as lots  # noqa: E402

from sanchopanza.policy import Thresholds  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-16-checkdone114"
ROWS = OUT / "done-scored.jsonl"
MODELS = {"13r": "jev-1.13.0", "14": "jev-1.14.0"}
GUARD = 0.02  # false-block rate: 1.14 may exceed 1.13 by at most 2 points (CI upper bound)
MISSING = 0.02


def cuts() -> dict[str, float]:
    return {arm: Thresholds.for_model(model).done for arm, model in MODELS.items()}


def blocks(p: float, cut: float) -> bool:
    return p < cut


def right(row: Mapping[str, Any], arm: str, cut: float) -> bool:
    return blocks(row[f"p_{arm}"], cut) == (row["label"] == "not_done")


def acts(rows: Sequence[Mapping[str, Any]], arm: str, cut: float) -> dict[str, Any]:
    blocked = [r for r in rows if blocks(r[f"p_{arm}"], cut)]
    unfinished = sum(r["label"] == "not_done" for r in rows)
    hits = sum(r["label"] == "not_done" for r in blocked)
    return {"cut": cut, "right": sum(right(r, arm, cut) for r in rows), "n": len(rows),
            "blocks": len(blocked), "false_blocks": len(blocked) - hits,
            "precision": round(hits / len(blocked), 4) if blocked else None,
            "recall": round(hits / unfinished, 4) if unfinished else None}  # fmt: skip


def compare(rows: Sequence[Mapping[str, Any]], c13: float, c14: float) -> dict[str, Any]:
    new = [right(r, "14", c14) for r in rows]
    old = [right(r, "13r", c13) for r in rows]
    return l4_stats.paired_binary(new, old, [r["cluster"] for r in rows])


def guard(rows: Sequence[Mapping[str, Any]], c13: float, c14: float) -> dict[str, Any]:
    """False blocks among done stops, as 'not falsely blocked': its difference is minus the
    false-block difference, so the guard holds when the lower bound is at least -GUARD."""
    done = [r for r in rows if r["label"] == "done"]
    new = [not blocks(r["p_14"], c14) for r in done]
    old = [not blocks(r["p_13r"], c13) for r in done]
    result = l4_stats.paired_binary(new, old, [r["cluster"] for r in done])
    low = (result.get("ci95_cluster") or (None, None))[0]
    result["holds"] = low is not None and low >= -GUARD
    return result


def verdict(primary: Mapping[str, Any], guard_result: Mapping[str, Any], missing: float) -> str:
    ci = primary.get("ci95_cluster")
    if ci is None:
        return "no medido"
    first = paired.verdict(primary["diff"], ci[0], ci[1], primary["p"])
    if first == "peor":
        return "peor"
    if missing > MISSING:
        return "no concluyente"
    if first in ("no peor", "mejora") and guard_result["holds"]:
        return f"confirmado ({first})"
    return "no concluyente"


def auc_block(all_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Descriptive: how well each arm ranks unfinished stops below finished ones, no cut."""
    rows = [r for r in all_rows if r["p_13r"] is not None and r["p_14"] is not None]
    return lots.paired_auc([r["label"] == "not_done" for r in rows],
                           [1 - r["p_14"] for r in rows], [1 - r["p_13r"] for r in rows],
                           [r["cluster"] for r in rows])  # fmt: skip


def analyse(all_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    cut = cuts()
    rows = [r for r in all_rows if r["p_13r"] is not None and r["p_14"] is not None]
    missing = 1 - len(rows) / len(all_rows) if all_rows else 1.0
    primary = compare(rows, cut["13r"], cut["14"])
    g = guard(rows, cut["13r"], cut["14"])
    by_suite = {}
    for suite in sorted({r["suite"] for r in rows}):
        part = [r for r in rows if r["suite"] == suite]
        by_suite[suite] = {"13r": acts(part, "13r", cut["13r"]), "14": acts(part, "14", cut["14"])}
    by_attack = {}
    for name, keep in (("benign", lambda r: r["attack"] == "none"),
                       ("attacked", lambda r: r["attack"] != "none")):  # fmt: skip
        part = [r for r in rows if keep(r)]
        by_attack[name] = {"13r": acts(part, "13r", cut["13r"]), "14": acts(part, "14", cut["14"])}
    return {
        "cuts": cut,
        "n": len(all_rows),
        "answered_by_both": len(rows),
        "missing_share": round(missing, 4),
        "arms": {"13r": acts(rows, "13r", cut["13r"]), "14": acts(rows, "14", cut["14"])},
        "primary": primary,
        "guard": g,
        "verdict": verdict(primary, g, missing),
        "descriptive": {
            "14_at_13r_cut": {
                "arm": acts(rows, "14", cut["13r"]),
                "against_13r": compare(rows, cut["13r"], cut["13r"]),
            },  # fmt: skip
            "by_suite": by_suite,
            "by_attack": by_attack,
        },
    }


def main() -> int:
    rows = [json.loads(x) for x in ROWS.read_text(encoding="utf-8").splitlines() if x.strip()]
    result = analyse(rows)
    result["descriptive"]["auc_block"] = auc_block(rows)
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    p = result["primary"]
    print(f"{result['arms']['14']['right']} vs {result['arms']['13r']['right']} of "
          f"{result['answered_by_both']}; diff {p['diff']} {p['ci95_cluster']}; "
          f"guard {result['guard']['holds']}; verdict {result['verdict']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
