"""The same benches as the recorded Jev run, through CLM on the CPU: long timeout, one at a time."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\roman\Desktop\proyectos\apps\sanchopanza\src")
os.environ["SANCHOPANZA_CLM_URL"] = "http://127.0.0.1:18392"
os.environ["SANCHOPANZA_CLM_MODEL"] = "clm-latest"

from sanchopanza.eval.bench import (  # noqa: E402
    load_cases,
    render_markdown,
    rows_to_json,
    run_bench,
    summarize,
)
from sanchopanza.providers import create  # noqa: E402

REPO = Path(r"C:\Users\roman\Desktop\proyectos\apps\sanchopanza")
FILES = [str(REPO / "benches" / f) for f in
         ("core.jsonl", "safety.jsonl", "retrieval.jsonl", "steerability.jsonl")]
OUT = Path(sys.argv[1])

cases = load_cases(FILES)
decider = create("clm", timeout_s=1800.0)
results = asyncio.run(run_bench(cases, decider, concurrency=1))
summary = summarize(results)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "results.json").write_text(json.dumps(rows_to_json(results), indent=1), encoding="utf-8")
(OUT / "summary.md").write_text(render_markdown(summary, title="CLM on CPU"), encoding="utf-8")
print(render_markdown(summary, title="CLM on CPU"))
