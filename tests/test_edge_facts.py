"""The edge and facts error analysis, reproduced from the recordings. No network.

`docs/results/2026-09-27-edge-facts/README.md` reports these figures; the design is the
pre-registration in the same directory, pinned by hash here.
"""

from __future__ import annotations

import asyncio
import hashlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results" / "2026-09-27-edge-facts"
sys.path.insert(0, str(ROOT / "benchmarks"))

import edge_facts_errors as efe  # noqa: E402


@pytest.fixture(scope="module")
def result():
    return asyncio.run(efe.run())


def test_the_pre_registration_is_the_hashed_one():
    raw = (RESULTS / "prereg.md").read_bytes().replace(b"\r\n", b"\n")
    expected = (RESULTS / "prereg.sha256").read_text(encoding="utf-8").strip()
    assert hashlib.sha256(raw).hexdigest() == expected


def test_seventeen_edges_committed_and_one_backwards(result):
    e = result["edge"]
    assert e["committed"] == 17
    assert e["committed_wrong"] == [["ed-26", 0.91, 0.87]]
    assert e["min_direction_of_right_commits"] == 0.90
    assert e["commit_precision_wilson95_low"] == 0.73
    assert (e["reversed_caught"], e["reversed_total"]) == (4, 11)


def test_a_direction_cut_from_one_case_cannot_reach_the_target(result):
    later = result["edge"]["later_batch"]
    assert (later["committed_now"], later["committed_at_cut"]) == (9, 8)
    assert later["wilson95_low_at_cut"] == 0.676
    assert later["reaches_target"] is False


def test_the_cases_decided_in_code(result):
    assert result["edge"]["no_literal_mention"] == [
        "ed-04",
        "ed-05",
        "ed-33",
        "ed-39",
        "ed-40",
        "ed-41",
        "ed-50",
    ]


def test_facts_under_the_shipped_policy(result):
    s = result["facts"]["fourth-batch.jsonl"]["shipped"]
    assert (s["right"], s["decided"], s["costly"]) == (36, 40, 2)
    profile = result["facts_unrelated_profile"]
    assert (profile["unrelated_cases"], profile["unrelated_is_top"]) == (12, 8)


def test_the_candidate_rule_never_adds_a_costly_error_on_any_recording(result):
    facts = result["facts"]
    assert len(facts) == 6
    for scores in facts.values():
        a, b = scores["shipped"], scores["unrelated_at_half"]
        assert b["right"] >= a["right"]  # +0 on the first recording since 2026-09-28
        assert b["costly"] == a["costly"]
    alt = facts["fourth-batch.jsonl"]["unrelated_at_half"]
    assert (alt["right"], alt["decided"]) == (41, 46)


def test_choice_confidence_is_the_rescaled_top_probability(result):
    """A canary like the Truth one in test_policy.py: if it fails, revisit every Choice gate."""
    identity = result["choice_identity"]
    assert sum(v["n"] for v in identity.values()) == 7162
    assert all(v["max_deviation"] < 0.025 for v in identity.values())
