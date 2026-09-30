"""Browse, development: what the targets Jev ranks below 20 have in common. Free: replays
Phase 1's recording (the development steps, never the confirmation ones).

python benchmarks/browse/misses.py
"""

from __future__ import annotations

import asyncio
import collections
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.browse import Element  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase1 = _load("browse_run", HERE / "run.py")


async def main() -> int:
    steps = phase1.load_steps()
    rows = await phase1.run_arm(
        "JEV-BLEND", steps, phase1.recording(), phase1.Ceiling(0.0, live=False)
    )
    by_id = {s["id"]: s for s in steps}
    out = []
    for r in rows:
        step = by_id[r["id"]]
        elements = [Element.from_dict(e) for e in step["elements"]]
        target = next(e for e in elements if e.key in set(step["positives"]))
        out.append({
            "id": r["id"], "position": r["position"], "elements": r["elements"],
            "answered": r["answered"], "calls": r["calls"], "role": target.role,
            "unnamed": not target.name.strip(), "name_chars": len(target.name),
            "line": target.line()[:160], "task": step["task"][:120],
        })  # fmt: skip
    miss = [o for o in out if o["position"] is None or o["position"] > 20]
    hit = [o for o in out if o not in miss]
    print(f"steps {len(out)}, outside top 20: {len(miss)}")
    for label, group in (("miss", miss), ("hit", hit)):
        n = len(group) or 1
        print(label, "unnamed", round(sum(o["unnamed"] for o in group) / n, 3),
              "name>150", round(sum(o["name_chars"] > 150 for o in group) / n, 3),
              "pages>2400", round(sum(o["elements"] > 2400 for o in group) / n, 3),
              "calls==80", round(sum(o["calls"] >= 80 for o in group) / n, 3),
              collections.Counter(o["role"] for o in group).most_common(6))  # fmt: skip
    for o in miss:
        print(o["position"], o["elements"], o["calls"], "|", o["line"], "|", o["task"])
    path = phase1.RESULTS / "misses-dev.jsonl"
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
