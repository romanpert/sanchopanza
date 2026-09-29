"""The lean-compaction registration cannot move after the fact.

1. `prereg.md` hashes to the first line of `prereg.sha256`, written before any paid run of the
   main experiment (amendments go below a `---` line and add a line; the first never changes).
2. The generated repositories and hidden tests hash to what `tasks.sha256` recorded.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

RESULTS = Path(__file__).parents[1] / "docs" / "results" / "2026-09-28-context-lean"
REGISTERED = "be08d6e5e8594017e1b2dbc2c5dafeea4b02451292ef16d145df32e049006a04"


def test_the_registration_has_not_moved():
    text = (RESULTS / "prereg.md").read_bytes()
    before_amendments = text.split(b"\n---\n", 1)[0] if b"\n---\n" in text else text
    assert hashlib.sha256(before_amendments).hexdigest() == REGISTERED
    first = (RESULTS / "prereg.sha256").read_text("utf-8").splitlines()[0].split()[0]
    assert first == REGISTERED


def test_the_task_fingerprints_are_recorded():
    lines = (RESULTS / "tasks.sha256").read_text("utf-8").splitlines()
    assert [line.split()[0] for line in lines] == [
        "2f139c415022408667f531ccaddea9468225f8a84fbaaa4d8f7912b2071efb54",
        "0520552d1c96a2a21ebbdba48337ca32ceeccbe580924b4e6a67665da10e95e2",
    ]


def test_the_generator_still_builds_the_registered_tasks(tmp_path):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("lean_tasks", RESULTS / "tasks.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RESULTS))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        module.build(tmp_path)
        assert module.tree_digest(tmp_path / "repos") == (
            "2f139c415022408667f531ccaddea9468225f8a84fbaaa4d8f7912b2071efb54"
        )
    finally:
        sys.path.remove(str(RESULTS))
        sys.modules.pop(spec.name, None)


def test_the_registered_haiku_result_is_what_the_rows_say():
    """N 5/7, L 3/7, K 0/6 valid (t05-K invalid): recomputed from runs.jsonl, not typed in."""
    import json

    rows = [json.loads(line) for line in (RESULTS / "runs.jsonl").read_text("utf-8").splitlines()]
    haiku = [r for r in rows if r["model"] == "haiku" and r["valid"]]
    wins = {arm: sum(r["success"] for r in haiku if r["arm"] == arm) for arm in "NKL"}
    runs = {arm: sum(1 for r in haiku if r["arm"] == arm) for arm in "NKL"}
    assert (wins, runs) == ({"N": 5, "K": 0, "L": 3}, {"N": 7, "K": 6, "L": 7})
    tokens = {arm: sum(r["usage"]["input_all"] for r in haiku if r["arm"] == arm) for arm in "NL"}
    assert tokens["L"] > tokens["N"]  # H2 failed: lean masking used more input tokens
