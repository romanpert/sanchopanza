"""The cascade numbers, replayed from `fixtures/cascade-jev.jsonl` and
`docs/results/2026-09-25-cascade/llm-answers.jsonl`. No network.

The data is not redistributed. Point SANCHOPANZA_RJUDGE at a clone of github.com/Lordog/R-Judge,
SANCHOPANZA_REGISTER at the private register's export (not released) and
SANCHOPANZA_ATBENCH_CODEX at ATBench-Codex's test.json, or these tests skip. What they pin
is `docs/results/2026-09-25-cascade/`.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import pathlib
import sys

import pytest

from sanchopanza import _env

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "cascade"))

# Two benches ship a `run.py`: loaded by path under its own name, or whichever test
# imports first hands the other its module.
_spec = importlib.util.spec_from_file_location(
    "cascade_run", ROOT / "benchmarks" / "cascade" / "run.py"
)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

PATHS = {
    "rjudge": _env.get("RJUDGE"),
    "register": _env.get("REGISTER"),
    "codex": _env.get("ATBENCH_CODEX"),
}
pytestmark = pytest.mark.skipif(
    not all(p and pathlib.Path(p).exists() for p in PATHS.values()),
    reason="SANCHOPANZA_RJUDGE, SANCHOPANZA_REGISTER and SANCHOPANZA_ATBENCH_CODEX not all set",
)


@pytest.fixture(scope="module")
def rows():
    cases = run.load_all(argparse.Namespace(**PATHS))
    return asyncio.run(run.table(cases))


def _acc(rows, name, arm):
    sub = [r for r in rows if r["set"] == name]
    return round(sum(r[arm] == r["label"] for r in sub) / len(sub), 4)


def test_jev_answers_every_case_from_the_recording(rows):
    assert len(rows) == 571 + 298 + 500
    assert all(r["jev"] is not None for r in rows)


def test_jev_and_haiku_alone(rows):
    assert _acc(rows, "rjudge", "jev") == 0.8809
    assert _acc(rows, "register", "jev") == 0.8255
    assert _acc(rows, "codex", "jev") == 0.78
    assert _acc(rows, "rjudge", "haiku") == 0.725
    assert _acc(rows, "register", "haiku") == 0.745
    assert _acc(rows, "codex", "haiku") == 0.738


def test_opus_on_the_cases_it_answered(rows):
    for name, n, acc, jev in (("rjudge", 541, 0.9501, 0.8799), ("register", 285, 0.8912, 0.8281)):
        block = run.answered_accuracy([r for r in rows if r["set"] == name], "opus")
        assert (block["n"], block["acc"], block["jev_same_cases"]) == (n, acc, jev)
