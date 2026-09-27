"""The derived `memory_write` cut, reproduced from the recordings. No network.

`docs/results/2026-09-27-memory-write-cut/README.md` reports these numbers; the design was
pre-registered in `prereg.md` of the same directory and its hash is pinned here.
"""

from __future__ import annotations

import asyncio
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import memory_write_cut as mwc  # noqa: E402

from sanchopanza import Thresholds  # noqa: E402
from sanchopanza.points import memory  # noqa: E402

from .helpers import decision, yes  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-27-memory-write-cut"
RESULT = asyncio.run(mwc.run())


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_the_pre_registration_is_the_one_hashed_before_the_run():
    expected = (RESULTS / "prereg.sha256").read_text(encoding="utf-8").strip()
    assert _sha(RESULTS / "prereg.md") == expected


def test_the_split_is_stratified_and_seeded():
    assert (RESULT["split"]["A"], RESULT["split"]["B"]) == (51, 49)


def test_the_cut_derived_on_half_a():
    assert RESULT["cut"] == 0.54
    a = RESULT["derived_on_A"]
    assert (a["stored"], a["costly"]) == (19, 0)


def test_the_held_out_half_passes_every_pre_registered_check():
    b, conj = RESULT["derived_on_B"], RESULT["conjunction_on_B"]
    assert (b["hits"], b["costly"], b["stored"]) == (39, 1, 17)
    assert (conj["hits"], conj["costly"]) == (37, 2)
    assert b["precision"] == 0.941
    assert all(RESULT["checks"].values()) and RESULT["holds"]


def test_the_secondary_set_never_used_for_this_threshold():
    d, c = RESULT["derived_on_secondary"], RESULT["conjunction_on_secondary"]
    assert (d["hits"], d["costly"]) == (74, 1)
    assert (c["hits"], c["costly"]) == (60, 4)


def test_the_reverse_split_cannot_reach_the_target():
    """Descriptive: half B has 25 positives, too few for the lower bound to clear 80 %."""
    assert RESULT["reverse"]["cut"] is None


def test_resampling_is_descriptive_and_in_the_same_range():
    d = RESULT["descriptive"]
    assert d["kfold_10x5_mean_hits"] == 81.8
    assert d["kfold_10x5_mean_costly"] == 3.8
    assert d["kfold_cut_range"] == [0.45, 0.54]
    assert (d["loo"]["hits"], d["loo"]["costly"]) == (80, 4)


def test_the_shipped_default_is_the_derived_cut():
    t = Thresholds()
    assert t.remember == RESULT["cut"]
    assert round(1 - t.derivable, 2) == RESULT["cut"]
    assert (t.common_durable, t.common_derivable) == (0.70, 0.75)


def test_decide_write_with_the_default_is_the_single_cut_on_every_case():
    """The code the package ships stores exactly what the analysis scored, on all 208 cases."""
    rows = asyncio.run(mwc.policy_shape.memory_rows()) + asyncio.run(mwc.secondary_rows())
    assert len(rows) == 208
    t = Thresholds()
    for r in rows:
        d, s, v = r["x"]
        dec = decision("memory_write", durable=yes(d), specific=yes(s), derivable=yes(v))
        assert memory.decide_write(dec, t).store == mwc.stores(r, RESULT["cut"]), r["id"]
