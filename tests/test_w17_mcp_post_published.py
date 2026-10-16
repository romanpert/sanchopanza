"""W17's published result (docs/results/2026-10-16-w17-mcp-post/): the per-call rows reproduce
the published arms, the development rule's comparisons and its outcome, free. The by-risk-source
counts need ATBench's labels on disk and are not checked here."""

from __future__ import annotations

import json
from pathlib import Path

from .helpers import bench_module

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "results" / "2026-10-16-w17-mcp-post"
analysis = bench_module(REPO / "benchmarks" / "a3_mcp", "w17_analysis")


def _rows() -> list[dict]:
    lines = (OUT / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def _published() -> dict:
    return json.loads((OUT / "analysis.json").read_text(encoding="utf-8"))


def test_the_published_rows_reproduce_the_arms_and_the_outcome() -> None:
    rows, published = _rows(), _published()
    ts = analysis.trajectories(rows)
    assert len(rows) == 1188 and len(ts) == 500
    arms = {name: analysis.arm(ts, *cuts) for name, cuts in analysis.ARMS.items()}
    assert arms == published["arms"]
    gain = analysis.paired(ts, "unsafe", analysis.ARMS["pre+post"], analysis.ARMS["pre"])
    rise = analysis.paired(ts, "safe", analysis.ARMS["pre+post"], analysis.ARMS["pre"])
    assert json.loads(json.dumps(gain)) == published["paired"]["pre+post_vs_pre_unsafe"]
    assert json.loads(json.dumps(rise)) == published["paired"]["pre+post_vs_pre_safe"]
    cover = analysis.coverage(rows)
    assert cover == published["coverage"]
    outcome = analysis.outcome(gain, rise, cover, published["pre_matches_a3"])
    assert outcome == published["development_rule"]


def test_the_published_verdict_is_does_not_license_on_the_fpr_term() -> None:
    published = _published()
    rule = published["development_rule"]
    assert rule["outcome"] == analysis.NOT_LICENSED
    assert rule["i_more_unsafe_caught"] and rule["coverage_and_provenance"]
    assert not rule["ii_fpr_rise_bounded"]
    gain = published["paired"]["pre+post_vs_pre_unsafe"]
    rise = published["paired"]["pre+post_vs_pre_safe"]
    assert (gain["only_new"], gain["only_old"]) == (35, 0)
    assert (rise["only_new"], rise["only_old"]) == (14, 0)
    assert rise["upper95_one_sided"] > analysis.FPR_RISE_MAX
    assert published["seal"]["matches_seal"] and published["pre_matches_a3"]


def test_the_published_answers_are_numbers_under_hashed_keys() -> None:
    lines = (OUT / "answers.jsonl").read_text(encoding="utf-8").splitlines()
    answers = [json.loads(x) for x in lines if x.strip()]
    assert len(answers) == 1188
    assert {a["model"] for a in answers} == {analysis.MODEL}
    assert round(sum(a["cost_usd"] for a in answers), 6) == _published()["ledger_usd"]
    fields = {"key", "order", "point", "model", "default", "input_tokens", "cost_usd",
              "latency_ms", "answers"}  # fmt: skip
    assert all(set(a) == fields and len(a["key"]) == 16 for a in answers)
