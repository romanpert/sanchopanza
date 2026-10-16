"""The verdict of lot jev114-checkdone-w17, free: reads `done-scored.jsonl` and the launch log
`publish` copied, writes `analysis.json`. DRAFT until the registration is sealed.

    python benchmarks/jev114/checkdone_w17_analysis.py

The rule is benchmarks/jev114/w17_prereg.md (at the seal, `OUT/prereg.md`), "Metric and verdict":

- block = p(done) < cut, the cut read from the code (`Thresholds.for_model("jev-1.14.0").done`);
- primary, on the confirmation's finished stops: "not falsely blocked", new record minus old,
  exact McNemar (items) and a 95 % paired bootstrap over user-task clusters (`l4_stats`);
  `lot_stats.verdict_of` on that interval, "mejora" needing p < 0.05 and the lower bound > 0;
- guard, on the confirmation's unfinished stops: "caught", new minus old, cluster interval's
  lower bound at least -2 points;
- "confirmado (mejora)" only with a favourable primary, the guard holding, the last launch
  complete, at most 2 % of stops without an answer in either arm, and the new arm leaving at
  most 2 points more unanswered than the old one.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import l4_stats  # noqa: E402
import lot_stats  # noqa: E402

from sanchopanza.policy import Thresholds  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-17-checkdone-w17"
ROWS = OUT / "done-scored.jsonl"
MODEL = "jev-1.14.0"
GUARD = 0.02  # recall on unfinished stops: new may lose at most 2 points (CI lower bound)
MISSING = lot_stats.MISSING
FAILURE_GAP = lot_stats.FAILURE_GAP


def cut() -> float:
    return Thresholds.for_model(MODEL).done


def gaps(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    n = len(rows) or 1
    old = sum(r["p_old"] is None for r in rows) / n
    new = sum(r["p_new"] is None for r in rows) / n
    union = sum(r["p_old"] is None or r["p_new"] is None for r in rows) / n
    return {"missing_old": round(old, 4), "missing_new": round(new, 4),
            "missing_union": round(union, 4), "failure_gap": round(new - old, 4)}  # fmt: skip


def paired(
    rows: Sequence[Mapping[str, Any]], good: Callable[[float], bool], unit: str = "cluster"
) -> dict[str, Any]:
    """`good` per stop under each arm, new minus old, with McNemar and the cluster interval."""
    new = [good(r["p_new"]) for r in rows]
    old = [good(r["p_old"]) for r in rows]
    return l4_stats.paired_binary(new, old, [r[unit] for r in rows])


def primary(rows: Sequence[Mapping[str, Any]], c: float) -> dict[str, Any]:
    result = paired([r for r in rows if r["label"] == "done"], lambda p: p >= c)
    result["verdict"] = lot_stats.verdict_of(
        result.get("diff"), result.get("ci95_cluster"), result.get("p", 1.0)
    )
    return result


def guard(rows: Sequence[Mapping[str, Any]], c: float) -> dict[str, Any]:
    result = paired([r for r in rows if r["label"] == "not_done"], lambda p: p < c)
    low = (result.get("ci95_cluster") or (None, None))[0]
    result["holds"] = low is not None and low >= -GUARD
    return result


def verdict(
    first: Mapping[str, Any], second: Mapping[str, Any], found: Mapping[str, float], launch: str
) -> str:
    if launch != "complete":
        return f"sin veredicto (lanzamiento: {launch})"
    said = first.get("verdict", "no medido")
    if said in ("peor", "no medido"):
        return said
    if found["missing_union"] > MISSING or found["failure_gap"] > FAILURE_GAP:
        return "no concluyente"
    if said == "mejora" and second["holds"]:
        return "confirmado (mejora)"
    if said == "mejora":
        return "no se adopta (la guarda no se sostiene)"
    return said if said in ("no peor", "no concluyente") else "no concluyente"


def arm(rows: Sequence[Mapping[str, Any]], key: str, c: float) -> dict[str, Any]:
    done = [r for r in rows if r["label"] == "done"]
    unfinished = [r for r in rows if r["label"] == "not_done"]
    blocked = [r for r in rows if r[key] < c]
    hits = sum(r["label"] == "not_done" for r in blocked)
    return {"n": len(rows), "right": sum((r[key] < c) == (r["label"] == "not_done") for r in rows),
            "false_blocks": sum(r[key] < c for r in done), "done": len(done),
            "caught": hits, "not_done": len(unfinished),
            "precision": round(hits / len(blocked), 4) if blocked else None}  # fmt: skip


def describe(rows: Sequence[Mapping[str, Any]], c: float) -> dict[str, Any]:
    return {
        "old": arm(rows, "p_old", c),
        "new": arm(rows, "p_new", c),
        "right": right(rows, c),
    }


def right(rows: Sequence[Mapping[str, Any]], c: float) -> dict[str, Any]:
    """Right decisions (a block on an unfinished stop, none on a finished one), new minus old."""
    new = [(r["p_new"] < c) == (r["label"] == "not_done") for r in rows]
    old = [(r["p_old"] < c) == (r["label"] == "not_done") for r in rows]
    return l4_stats.paired_binary(new, old, [r["cluster"] for r in rows])


def by(rows: Sequence[Mapping[str, Any]], key: str, c: float) -> dict[str, Any]:
    return {name: describe([r for r in rows if r[key] == name], c)
            for name in sorted({r[key] for r in rows})}  # fmt: skip


def auc(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return lot_stats.paired_auc([r["label"] == "not_done" for r in rows],
                                [1 - r["p_new"] for r in rows], [1 - r["p_old"] for r in rows],
                                [r["cluster"] for r in rows])  # fmt: skip


def analyse(all_rows: Sequence[Mapping[str, Any]], launch: str | None = None) -> dict[str, Any]:
    c = cut()
    launch = lot_stats.launch_status(OUT) if launch is None else launch
    confirm_all = [r for r in all_rows if r["set"] == "confirm"]
    found = gaps(confirm_all)
    answered = [r for r in all_rows if r["p_old"] is not None and r["p_new"] is not None]
    confirm = [r for r in answered if r["set"] == "confirm"]
    dev = [r for r in answered if r["set"] == "dev"]
    first, second = primary(confirm, c), guard(confirm, c)
    return {
        "cut": c,
        "launch": launch,
        "n": {"confirm": len(confirm_all), "answered": len(confirm), "dev": len(dev)},
        "answers": found,
        "arms": describe(confirm, c),
        "primary": first,
        "guard": second,
        "verdict": verdict(first, second, found, launch),
        "descriptive": {
            "changed_only": describe([r for r in confirm if r["changed"]], c),
            "by_pipeline": by(confirm, "pipeline", c),
            "by_suite": by(confirm, "suite", c),
            "without_hijacked_runs": describe([r for r in confirm if not r["security"]], c),
            "at_0.5": describe(confirm, 0.5),
            "auc": auc(confirm),
            "dev_checkdone114": {
                "arms": describe(dev, c),
                "false_blocks": primary(dev, c),
                "recall": guard(dev, c),
            },  # fmt: skip
        },
    }


def main() -> int:
    rows = [json.loads(x) for x in ROWS.read_text(encoding="utf-8").splitlines() if x.strip()]
    result = analyse(rows)
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    p, g = result["primary"], result["guard"]
    print(f"false blocks {result['arms']['old']['false_blocks']} -> "
          f"{result['arms']['new']['false_blocks']} of {result['arms']['old']['done']}; "
          f"not falsely blocked {p['diff']} {p['ci95_cluster']} p {p['p']}; "
          f"recall {g['diff']} {g['ci95_cluster']} holds {g['holds']}; "
          f"verdict {result['verdict']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
