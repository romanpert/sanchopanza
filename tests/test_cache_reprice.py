"""The re-pricing in `docs/results/2026-09-25-cache/README.md`, read back from `reprice.json`.

`reprice.json` is produced by `benchmarks/agentdojo/reprice_shared_prefix.py` (count_tokens
only, free). This pins what the README quotes, so a regenerated file that moves a figure fails.
"""

from __future__ import annotations

import json
import pathlib

import pytest

FILE = pathlib.Path(__file__).resolve().parents[1] / "docs/results/2026-09-25-cache/reprice.json"

if not FILE.exists():  # pragma: no cover
    pytest.skip("cache re-pricing not present", allow_module_level=True)

DATA = json.loads(FILE.read_text(encoding="utf-8"))


def _ratio(run: str, arm: str, column: str) -> float:
    arms = DATA[run]["arms"]
    return round(arms[arm][column] / arms["full"][column], 2)


def test_the_headline_run_loses_most_of_the_windows_cost_advantage():
    assert _ratio("2026-09-25-e2e/runs-10.jsonl", "sancho", "as_run") == 0.45
    assert _ratio("2026-09-25-e2e/runs-10.jsonl", "sancho", "shared_prefix") == 0.88
    assert _ratio("2026-09-25-e2e/runs-10-parallel.jsonl", "sancho", "shared_prefix") == 0.77


def test_on_the_wide_catalog_search_stays_cheapest():
    run = "2026-09-25-wide/runs-5.jsonl"
    assert _ratio(run, "search", "shared_prefix") == 0.34
    assert _ratio(run, "sancho", "shared_prefix") == 0.54


def test_repricing_only_ever_lowers_a_cost():
    for run in DATA.values():
        for arm in run["arms"].values():
            assert 0 < arm["shared_prefix"] <= arm["as_run"]
