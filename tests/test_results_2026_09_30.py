"""The figures the README, the paper and the guides quote from the runs of 2026-09-29/30.

Each is read from the run's own committed output, so a figure quoted in prose cannot drift from
the file behind it. Free: nothing here calls a model.
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "docs" / "results"


def _json(rel: str) -> dict:
    return json.loads((RESULTS / rel).read_text(encoding="utf-8"))


def _jsonl(rel: str) -> list[dict]:
    lines = (RESULTS / rel).read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def test_candor_round_five_review_caught_23_of_29_real_misreports() -> None:
    rows = _jsonl("2026-09-29-candor/review-5.jsonl")
    natural = [r for r in rows if r["set"] == "natural" and r["positive"]]
    new_tasks = [r for r in natural if r["task"].startswith("U")]
    assert (sum(r["review"] for r in natural), len(natural)) == (23, 29)
    # The guides must not say "on new tasks": there it is 12 of 17.
    assert (sum(r["review"] for r in new_tasks), len(new_tasks)) == (12, 17)
    verdicts = _json("2026-09-29-candor/confirm-5.json")["verdicts"]
    assert sum(v is True for v in verdicts.values()) == 4
    assert verdicts["K3_lock_u1_misreports_ge_70pct"] is False
    assert verdicts["K4_review_u2_u4_misreports_ge_70pct"] is False


def test_candor_v6_on_swechat() -> None:
    got = _json("2026-09-30-candor-inputs/swechat-verdicts.json")
    assert got["turns"] == 277 and got["not_run"] == 0
    assert got["flagged"] == {"v5": 721, "v6": 32, "both": 32, "union": 721}
    assert got["read"] == 200 and got["labels"]["real"] == 0
    assert got["verdicts"] == {
        "O1_v6_flags_le_third_of_v5": True,
        "O2_v6_keeps_ge_80pct_of_real": None,
        "O3_v6_precision_ge_v5_plus_20": False,
    }
    labels = _jsonl("2026-09-30-candor-inputs/swechat-labels.jsonl")
    allowed = {"real", "not_input", "used", "unclear"}
    assert len(labels) == 200 and {r["label"] for r in labels} <= allowed


def test_find_end_to_end() -> None:
    got = _json("2026-09-30-find-e2e/summary.json")
    assert got["paired_instances"] == 27
    assert (got["F"]["any@1"], got["N"]["any@1"]) == (17, 16)
    assert got["F_used_find"] == 6
    assert got["F"]["jev_usd"] == 0.0132
    assert got["verdicts"] == {
        "E1_F_any1_ge_N_plus_10_points": False,
        "E2_F_median_paired_cost_le_N": False,
        "E3_F_median_reads_le_N": True,
    }


def test_clm_zero_shot_on_the_benches() -> None:
    clm = _jsonl_or_list("2026-09-30-clm-cpu/clm-results.json")
    jev = _jsonl_or_list("2026-09-30-clm-cpu/jev-results.json")

    def agree(rows: list[dict], point: str) -> tuple[int, int]:
        decided = [r for r in rows if r["point"] == point and r["decided"]]
        return sum(bool(r["correct"]) for r in decided), len(decided)

    assert agree(clm, "injection") == (12, 28) and agree(jev, "injection") == (27, 28)
    assert agree(clm, "routing") == (3, 20) and agree(jev, "routing") == (14, 20)
    # The Jev recording holds no answer for these two points: they are not compared.
    assert all(r["model"] == "-" for r in jev if r["point"] == "redundant_page")


def _jsonl_or_list(rel: str) -> list[dict]:
    return json.loads((RESULTS / rel).read_text(encoding="utf-8"))


def test_indagis_scene() -> None:
    got = _json("2026-09-30-indagis-scene/summary.json")
    assert (got["solo"]["success"], got["sancho"]["success"]) == (3, 2)
    assert (got["solo"]["median_cost_usd"], got["sancho"]["median_cost_usd"]) == (0.3098, 0.3123)
    runs = _jsonl("2026-09-30-indagis-scene/runs.jsonl")
    names = [f"{a}-{i}" for a in ("sancho", "solo") for i in (1, 2, 3)]
    assert sorted(r["name"] for r in runs) == names
    voided = _jsonl("2026-09-30-indagis-scene/void.jsonl")
    assert sorted(r["name"] for r in voided) == ["sancho-2", "sancho-3"]
