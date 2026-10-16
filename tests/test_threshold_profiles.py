"""Thresholds per Jev model: 1.13 exactly as it was, 1.14 its recalibrated profile.

The profile is data (`policy.MODEL_PROFILES`), chosen by the effective model: the decider's
`model`, which for Jev is `SANCHOPANZA_JEV_MODEL` or `DEFAULT_MODEL`. Its values come from
docs/results/2026-10-15-jev114-recal/ and a test below holds them to that analysis.
No test here calls a paid provider.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import fields
from pathlib import Path

import pytest

from sanchopanza import Squire, Thresholds
from sanchopanza.candor.judge import HOLISTIC_CUT, holistic
from sanchopanza.candor.rules import Report, Turn
from sanchopanza.contract import Answer, Decision
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.points import graph, loop, memory
from sanchopanza.policy import MODEL_PROFILES
from sanchopanza.providers import FixedDecider
from sanchopanza.providers.jev import DEFAULT_MODEL

from .helpers import decision, yes

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "docs" / "results" / "2026-10-15-jev114-recal" / "analysis.json"

# Every value 1.13 reads, as it was before profiles existed. A change here is a change to the
# measured policy and needs its own result, not a profile.
JEV_113 = {
    "act": 0.75, "relax": 0.60, "allow_upgrade": False, "redundant": 0.80,
    "adds_nothing": 0.59, "keyword": 0.60, "relevance": 0.45, "contributes": 0.28,
    "pages_in_context": 0.40, "sentences": 0.28, "pages_first_round": 0.18,
    "document_paragraphs": 0.75, "document_window": 2, "context_keep": 0.5,
    "injection": 0.70, "citation": 0.80, "review": 0.70, "guard": 0.70, "entity_low": 0.25,
    "entity_high": 0.75, "classify": 0.60, "tools": 0.35, "deferred": 0.60, "window_add": 0.35,
    "saturated": 0.70, "goal_met": None, "repeats_check": None, "extract_skip": None,
    "recall_skip": None, "done": 0.5, "holistic": 0.83, "remember": 0.54, "derivable": 0.46,
    "common_durable": 0.70, "common_derivable": 0.75, "audit": 0.0, "max_decisions": 400,
    "max_usd": 0.10, "max_windows": 8,
    # Added 2026-10-15 with the opt-in MCP guard (A3): a new cut, not a moved one; it is the cut
    # `points.actions.decide` was measured at offline (docs/results/2026-10-16-a3-mcp/prereg.md).
    "action_stop": 0.5,
    # Added 2026-10-16 with the opt-in MCP guard after the call (W17): a new cut, not a moved
    # one; the cut the offline reference, whose records end on the last result, was measured at.
    "action_result_stop": 0.5,
}  # fmt: skip
JEV_114 = {"adds_nothing": 0.61, "goal_met": 0.57, "repeats_check": 0.60, "extract_skip": 0.27,
           "recall_skip": 0.10, "done": 0.30, "holistic": 0.90}  # fmt: skip


class _Modelled(FixedDecider):
    def __init__(self, model: str, answers: dict[str, Answer] | None = None) -> None:
        super().__init__(answers or {})
        self.model = model


def _values(t: Thresholds) -> dict[str, object]:
    return {f.name: getattr(t, f.name) for f in fields(t)}


# --- 1.13 does not move -------------------------------------------------------------------


def test_the_113_policy_is_every_value_it_was():
    assert _values(Thresholds()) == JEV_113


@pytest.mark.parametrize("model", ["jev-1.13.0", DEFAULT_MODEL, None, "", "jev-latest",
                                   "claude-sonnet-5", "jev-1.12.0"])  # fmt: skip
def test_only_a_profiled_model_moves_a_threshold(model):
    assert Thresholds.for_model(model) == Thresholds()


def test_113_reads_the_shared_knobs_it_always_read():
    t = Thresholds()
    assert (t.goal_met_cut, t.repeats_check_cut) == (t.saturated, t.saturated) == (0.70, 0.70)
    assert t.extract_skip_cut == t.recall_skip_cut == 1.0 - t.act == 0.25
    moved = Thresholds().with_(saturated=0.9, act=0.9)
    assert (moved.goal_met_cut, moved.repeats_check_cut) == (0.9, 0.9)
    assert moved.extract_skip_cut == moved.recall_skip_cut == pytest.approx(0.1)


def test_the_default_model_is_still_113():
    assert DEFAULT_MODEL == "jev-1.13.0"


# --- 1.14 reads its profile -----------------------------------------------------------------


def test_the_114_profile_is_the_recalibration_and_nothing_else():
    assert dict(MODEL_PROFILES["jev-1.14.0"]) == JEV_114
    t = Thresholds.for_model("jev-1.14.0")
    assert _values(t) == {**JEV_113, **JEV_114}


def test_the_114_profile_is_what_the_analysis_derived():
    if not ANALYSIS.exists():
        pytest.skip("analysis not present")
    profile = json.loads(ANALYSIS.read_text(encoding="utf-8"))["profile"]
    assert profile == JEV_114  # memory_write's 1.14 derivation was unreachable: no entry


def test_a_profile_cannot_be_edited_at_run_time():
    with pytest.raises(TypeError):
        MODEL_PROFILES["jev-1.14.0"]["done"] = 0.9  # type: ignore[index]


def test_the_squire_takes_the_profile_of_its_deciders_model():
    assert Squire(_Modelled("jev-1.14.0")).thresholds == Thresholds.for_model("jev-1.14.0")
    assert Squire(_Modelled("jev-1.13.0")).thresholds == Thresholds()
    assert Squire(FixedDecider({})).thresholds == Thresholds()  # no model, no profile


def test_explicit_thresholds_win_over_the_profile():
    mine = Thresholds().with_(done=0.42)
    assert Squire(_Modelled("jev-1.14.0"), thresholds=mine).thresholds is mine


def test_a_mapping_lays_over_a_base_profile():
    base = Thresholds.for_model("jev-1.14.0")
    t = Thresholds.from_mapping({"done": "0.4"}, base=base)
    assert (t.done, t.goal_met, t.adds_nothing) == (0.4, 0.57, 0.61)
    assert Thresholds.from_mapping({"done": "0.4"}) == Thresholds().with_(done=0.4)


def test_the_hook_squire_follows_the_jev_model_in_the_environment(tmp_path):
    from sanchopanza.harness.claude_code import squire_from_env

    env = {"SANCHOPANZA_PROVIDER": "recorded", "SANCHOPANZA_FIXTURE": str(tmp_path / "none"),
           "SANCHOPANZA_JOURNAL": str(tmp_path / "j.jsonl")}  # fmt: skip
    assert squire_from_env(env).thresholds == Thresholds()
    env14 = {**env, "SANCHOPANZA_JEV_MODEL": "jev-1.14.0", "SANCHOPANZA_T_HOLISTIC": "0.95"}
    assert squire_from_env(env14).thresholds == Thresholds.for_model("jev-1.14.0").with_(
        holistic=0.95
    )


# --- each point reads its own cut -----------------------------------------------------------


def test_the_loop_reads_goal_met_and_repeats_check_cuts():
    d = decision("loop", goal_met=yes(0.6), repeats_check=yes(0.62))
    assert not loop.decide(d, Thresholds()).speaks
    advice = loop.decide(d, Thresholds.for_model("jev-1.14.0"))
    assert "established already" in advice.message and "already run" in advice.message


def test_the_extraction_gate_and_recall_read_their_own_cuts():
    t14 = Thresholds.for_model("jev-1.14.0")
    gate = decision("graph_gate", has_anything=yes(0.26))
    assert graph.decide_gate(gate, Thresholds()).extract
    assert not graph.decide_gate(gate, t14).extract
    look = decision("recall", needs_memory=yes(0.2))
    assert not memory.decide_recall(look, Thresholds()).look
    assert memory.decide_recall(look, t14).look


def test_check_done_cuts_at_the_squires_done_unless_told_otherwise():
    answers = {"done": yes(0.4)}
    assert asyncio.run(Squire(_Modelled("jev-1.13.0", answers)).check_done(
        task="t", record="r")).done is False  # fmt: skip
    assert asyncio.run(Squire(_Modelled("jev-1.14.0", answers)).check_done(
        task="t", record="r")).done is True  # fmt: skip
    assert asyncio.run(Squire(_Modelled("jev-1.14.0", answers)).check_done(
        task="t", record="r", cut=0.5)).done is False  # fmt: skip


def test_the_stop_hook_leaves_the_cut_to_the_squire_by_default():
    assert HarnessConfig().done_cut is None


class _Holistic:
    def __init__(self, p: float, t: Thresholds | None) -> None:
        self.p = p
        if t is not None:
            self.thresholds = t

    async def decide(self, point, state, questions):  # noqa: ANN001
        return Decision(point, {"misstates": Answer(kind="truth", confidence=0.7, truth=self.p)},
                        "fake", "m")  # fmt: skip

    def record(self, decision, **fields) -> None:  # noqa: ANN001, ANN003
        pass


def test_the_holistic_note_cuts_at_the_squires_profile():
    turn = Turn(said="All good.", did=())
    assert Thresholds().holistic == HOLISTIC_CUT
    flagged = asyncio.run(holistic(_Holistic(0.85, Thresholds()), turn, Report()))
    assert len(flagged.findings) == 1
    quiet = asyncio.run(holistic(_Holistic(0.85, Thresholds.for_model("jev-1.14.0")), turn,
                                 Report()))  # fmt: skip
    assert quiet.findings == ()
    bare = asyncio.run(holistic(_Holistic(0.85, None), turn, Report()))  # no thresholds: 0.83
    assert len(bare.findings) == 1
