"""Browse, development: what naming unnamed elements (classes, holder) changes. Free: BM25 only.

python benchmarks/browse/hints.py

Compares Phase 1's development steps read by the reader of the time (`steps.jsonl`) with the
same steps read by the current one (`steps-hints.jsonl`, refetched): how many target lines and
element lines changed, and where BM25 ranks the target in each. BM25 is a direction, not the
measure: the ranking that ships is Jev's, and that needs new calls.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.browse import Element, rank  # noqa: E402

CACHE = pathlib.Path.home() / ".cache" / "sanchopanza" / "mind2web"
KS = (1, 5, 10, 20, 30)


def load(name: str) -> dict[str, dict]:
    rows = (CACHE / name).read_text(encoding="utf-8").splitlines()
    return {r["id"]: r for r in (json.loads(x) for x in rows if x.strip())}


async def position(step: dict) -> int | None:
    elements = [Element.from_dict(e) for e in step["elements"]]
    ranked = await rank(step["task"], elements, done=step["previous"], keep=len(elements))
    keys = [r.element.key for r in ranked]
    return min((keys.index(k) + 1 for k in step["positives"] if k in keys), default=None)


async def main() -> int:
    old, new = load("steps.jsonl"), load("steps-hints.jsonl")
    ids = [i for i in old if i in new]
    rows = []
    for i in ids:
        a, b = old[i], new[i]
        lines_a = {e["key"]: Element.from_dict(e).line() for e in a["elements"]}
        lines_b = {e["key"]: Element.from_dict(e).line() for e in b["elements"]}
        target = a["positives"][0]
        rows.append({
            "id": i, "target_changed": lines_a.get(target) != lines_b.get(target),
            "elements_changed": sum(lines_a.get(k) != v for k, v in lines_b.items()),
            "elements": len(lines_b), "old": await position(a), "new": await position(b),
            "target_line": lines_b.get(target, "")[:140],
        })  # fmt: skip
    n = len(rows)
    print(f"steps {n}; target line changed in {sum(r['target_changed'] for r in rows)}; "
          f"elements changed {sum(r['elements_changed'] for r in rows)} of "
          f"{sum(r['elements'] for r in rows)}")  # fmt: skip
    for k in KS:
        hit = [sum(1 for r in rows if r[w] is not None and r[w] <= k) / n for w in ("old", "new")]
        print(f"BM25 R@{k}: {hit[0]:.3f} -> {hit[1]:.3f}")
    for r in rows:
        if r["target_changed"]:
            print(r["old"], "->", r["new"], "|", r["target_line"])
    out = HERE.parents[1] / "docs" / "results" / "2026-09-30-browse" / "hints-dev.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
