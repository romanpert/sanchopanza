"""The cascade re-pricing and frontier, reproduced from the recorded answers. No network.

`docs/results/2026-09-27-cascade-frontier/README.md` reports these figures. They are post hoc;
the confirmatory design is `prereg-confirm.md` of the same directory, pinned by hash here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results" / "2026-09-27-cascade-frontier"
SOURCE = ROOT / "docs" / "results" / "2026-09-25-cascade" / "rows.json"

pytestmark = pytest.mark.skipif(not SOURCE.exists(), reason="cascade recordings not present")


def _load():
    # Loaded by path: two benchmark scripts share module names elsewhere.
    spec = importlib.util.spec_from_file_location(
        "cascade_frontier", ROOT / "benchmarks" / "cascade" / "frontier.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def result():
    return _load().run()


def _at(frontier, tau):
    return next(f for f in frontier if f["tau"] == tau)


def test_the_confirmatory_pre_registration_is_the_hashed_one():
    raw = (RESULTS / "prereg-confirm.md").read_bytes().replace(b"\r\n", b"\n")
    expected = (RESULTS / "prereg-confirm.sha256").read_text(encoding="utf-8").strip()
    assert hashlib.sha256(raw).hexdigest() == expected


def test_the_registered_split_reproduces_the_failed_cost_ratio(result):
    reg = result["rjudge"]["symmetric"]
    assert reg["tau_from_derivation"] == 0.80
    held = reg["held_out_at_that_tau"]
    assert (held["acc"], held["cost_ratio"], held["escalated"]) == (0.9316, 0.5681, 152)
    assert result["rjudge"]["opus_alone_held_out"]["acc"] == 0.9316


def test_caching_the_prefix_moves_the_ratio_by_under_one_point(result):
    c = result["caching_rjudge"]
    assert c["smallest_opus_request_tokens"] == 1085
    ratios = [b["cost_ratio"] for b in c["by_prefix"]]
    assert ratios[0] == 0.5681 and ratios[-1] == 0.5613
    assert max(ratios) - min(ratios) < 0.01
    assert c["by_prefix"][-1]["opus_alone_usd"] == 1.4697


def test_the_frontier_is_flat_from_035(result):
    held = result["rjudge"]["symmetric"]["frontier_held_out"]
    assert (_at(held, 0.35)["acc"], _at(held, 0.35)["cost_ratio"]) == (0.9316, 0.2521)
    assert (_at(held, 0.65)["acc"], _at(held, 0.65)["cost_ratio"]) == (0.9354, 0.3967)
    every = result["rjudge"]["symmetric"]["frontier_all"]
    assert (_at(every, 0.45)["acc"], _at(every, 0.45)["cost_ratio"]) == (0.9464, 0.2703)


def test_one_sided_routing_never_reaches_opus(result):
    for rule in ("safe_only", "unsafe_only"):
        assert result["rjudge"][rule]["tau_from_derivation"] == 1.01
    assert result["rjudge"]["safe_only"]["held_out_at_that_tau"]["false_block_rate"] == 0.1969
    assert result["rjudge"]["unsafe_only"]["held_out_at_that_tau"]["false_allow_rate"] == 0.1103


def test_the_codex_prediction_stated_in_the_pre_registration(result):
    share = result["codex_jev_confidence"]["share_below"]
    assert share["0.5"] == 0.41
    assert result["codex_jev_confidence"]["haiku_cost_per_case"] == 0.002346
