"""Browse, sensitivity: the end-to-end phases without each phase's first, cache-warming run.

python benchmarks/browse/warmup.py

The first session of a phase writes the prompt-cache prefix every later session reads, and it is
always a PLAIN session (PLAIN runs first in each run). In Phase 3e it wrote 49,489 cache tokens
against about 13,800 for the same task's other sessions and cost 0.231 USD against about 0.10.
This drops run 1 of each phase's first task in both arms (paired) and recomputes the registered
statistic. Descriptive: the registered results stand as published.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "docs" / "results" / "2026-09-30-browse"
PHASES = {
    "3 (playwright-cli)": "e2e-sessions.jsonl",
    "3b (Playwright MCP)": "e2e-mcp-sessions.jsonl",
    "3c (Playwright MCP, fixed)": "e2e-mcp-fixed-sessions.jsonl",
    "3d (Playwright MCP, new tasks)": "e2e-mcp-new-sessions.jsonl",
    "3e (playwright-cli, new tasks)": "e2e-cli-new-sessions.jsonl",
    "3f (Playwright MCP, wide)": "e2e-mcp-wide-sessions.jsonl",
    "3g (playwright-cli, wide)": "e2e-cli-wide-sessions.jsonl",
}


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load("browse_e2e", HERE / "e2e.py")


def main() -> int:
    out = {}
    for phase, name in PHASES.items():
        path = RESULTS / name
        if not path.exists():
            continue
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        rows = [r for r in rows if r["run"] > 0]
        first = rows[0]
        kept = [r for r in rows if not (r["task"] == first["task"] and r["run"] == first["run"])]
        both = {k: base.analyze(v)["LEAN_minus_PLAIN_usd_per_task"]
                for k, v in (("all", rows), ("without_warmup", kept))}  # fmt: skip
        out[phase] = {
            "first_session": {k: first[k] for k in ("task", "arm", "list_usd", "cache_write")},
            "all": {k: both["all"][k] for k in ("value", "bootstrap95")},
            "without_warmup": {k: both["without_warmup"][k] for k in ("value", "bootstrap95")},
        }
    (RESULTS / "warmup.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
