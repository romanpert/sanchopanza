"""The autopilot's offline measurements on a synthetic unit: the experimental tournament arm of
`benchmarks/context/run.py` and the arrival and recall simulations of `simulate.py`. No network.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from sanchopanza.context.transcript import calls as calls_of

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "context"


def _load(name: str):
    key = f"context_bench_{name}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, BENCH / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


labels_mod = _load("labels")
arms = _load("arms")
run = _load("run")
simulate = _load("simulate")

BODY = "".join(f"def helper_{i}(value):\n    return value + {i}\n\n" for i in range(300))


def _unit() -> dict:
    """25 reads; read 3 holds `renamed_symbol_3`, which the future uses after a prompt."""
    history = [{"role": "user", "content": [{"type": "text", "text": "Refactor the helpers"}]}]
    for i in range(25):
        extra = f"\nrenamed_symbol_{i} = compute_total_{i}()\n" if i == 3 else ""
        history.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": f"reading module {i}"},
                    {
                        "type": "tool_use",
                        "id": f"t{i}",
                        "name": "Read",
                        "input": {"file_path": f"/r/mod{i}.py"},
                    },
                ],
            }
        )
        history.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"t{i}",
                        "content": BODY[:7_000] + extra + BODY[7_000:9_000],
                    }
                ],
            }
        )
    future = [
        {"role": "user", "content": [{"type": "text", "text": "now fix mod3 helpers"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Looking at mod3 again"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Using renamed_symbol_3 from mod3."},
                {
                    "type": "tool_use",
                    "id": "f1",
                    "name": "Edit",
                    "input": {"file_path": "/r/mod3.py", "old": "renamed_symbol_3"},
                },
            ],
        },
    ]
    labels = labels_mod.label(history, future, calls_of(history))
    return {"history": history, "future": future, "labels": labels, "split": "test"}


def test_the_unit_has_one_needed_result():
    unit = _unit()
    needed = [k for k, v in unit["labels"].items() if v["needed"]]
    assert needed == ["t3"]


def test_the_tournament_arm_is_experimental_and_runs_free():
    assert "tournament" not in arms.ARMS and "tournament" in arms.KNOWN_ARMS
    unit = _unit()
    squire = arms.squire_for(arms.FakeDecider(), max_usd=0.01)
    result = asyncio.run(
        arms.run_arm("tournament", unit["history"], calls_of(unit["history"]), squire)
    )
    assert result.asked and result.decisions >= 1
    rows = asyncio.run(run.run_units([unit], ["keep_all", "tournament"], {"tournament": squire}))
    report = run.analyze(rows, ["keep_all", "tournament"], None, {"tournament": 0.3})
    assert set(report["splits"]["test"]) == {"keep_all", "tournament"}
    estimate = run.estimate([unit], ["tournament"])
    assert estimate["arms"]["tournament"]["asked"] >= 1


def test_the_live_run_refuses_the_unregistered_arm(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys, "argv", ["run.py", "--live", "--arms", "tournament", "--dataset", str(tmp_path)]
    )
    with pytest.raises(SystemExit, match="not registered"):
        run.main()


def _keep_marker(marker: str):
    from tests.context_helpers import ScriptedDecider

    def answer(point, key, state):
        if point == "triage_pages":
            import re

            parts = re.split(r"(?m)^(P\d\d)\| ", state["pages"])
            text = dict(zip(parts[1::2], parts[2::2], strict=True)).get(key, "")
            return 0.9 if marker in text else 0.02
        return None

    return ScriptedDecider(answer)


def test_arrival_simulation_counts_what_survives_literally():
    unit = _unit()
    squire = simulate.squire_for(_keep_marker("renamed_symbol_3"), max_usd=0.01)
    rows = asyncio.run(simulate.arrival_unit(unit, squire, simulate.arrival.Settings()))
    summary = simulate.arrival_summary(rows)
    # only read 3 has a block the decider keeps; the others keep none and pass whole
    assert summary["results"] == 25 and summary["cut"] == 1
    assert summary["needed_all_tokens_kept"] == 1.0
    assert summary["freed_in_cut"] > 0.5
    assert summary["reasons_passed"] == {"the decider kept no block": 24}


def test_arrival_simulation_reports_a_needed_token_lost():
    unit = _unit()
    squire = simulate.squire_for(_keep_marker("helper_1("), max_usd=0.01)
    summary = simulate.arrival_summary(
        asyncio.run(simulate.arrival_unit(unit, squire, simulate.arrival.Settings()))
    )
    assert summary["needed_all_tokens_kept"] == 0.0
    assert summary["needed_lost_recoverable"] == 1


def test_recall_simulation_hits_without_leakage():
    unit = _unit()
    squire = simulate.squire_for(_keep_marker("mod3"), max_usd=0.01)
    row = asyncio.run(simulate.recall_unit(unit, squire, "text"))
    jev = row["arms"]["jev"]
    assert row["masked"] >= 10
    assert jev["needed_masked"] == 1 and jev["hits"] == 1
    assert jev["leak_prompt"] == 0 and jev["leak_assistant"] == 0
    summary = simulate.recall_summary([row])
    assert summary["jev"]["hit_rate"] == 1.0
    assert "bm25@3" in summary


def test_the_query_never_holds_the_message_it_precedes():
    unit = _unit()
    query, _, said = simulate.query_at(unit["history"], unit["future"], 2, "text")
    assert "renamed_symbol_3" not in query
    assert "Looking at mod3 again" in said


def test_estimates_are_free_and_positive():
    unit = _unit()
    a = simulate.arrival_estimate([unit], simulate.arrival.Settings())
    r = simulate.recall_estimate([unit], "text")
    assert a["eligible_results"] == 25 and a["usd_high"] >= a["usd"] > 0
    assert r["calls_high"] >= 1 and r["usd_high"] > 0


def test_simulate_live_refuses_until_registered(tmp_path, monkeypatch):
    monkeypatch.setattr(simulate, "registered", lambda: False)
    with pytest.raises(SystemExit, match="not registered"):
        simulate.main(["recall", "--live", "--dataset", str(tmp_path)])


def test_simulate_live_refuses_without_units_or_one_split(tmp_path):
    assert simulate.registered()  # Amendment 2 is in prereg.md and hashed
    with pytest.raises(SystemExit, match="split all"):
        simulate.main(["recall", "--live", "--dataset", str(tmp_path)])
    with pytest.raises(SystemExit, match="split all"):
        simulate.main(["arrival", "--live", "--split", "test", "--dataset", str(tmp_path)])
