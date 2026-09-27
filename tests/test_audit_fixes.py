"""Regressions for the policy audit of 2026-09-25: absent answers were read as permission.

Each finding was confirmed with a hand-built decision before it was fixed, and replaying all
1,153 recorded bench cases before and after the fixes changed zero predictions: these are
paths no recorded case reaches, which is why no test caught them. Each test below builds the
exact decision that used to produce the costly action.
"""

from __future__ import annotations

import asyncio

from sanchopanza import Decision
from sanchopanza.points import graph, injection, memory, plan, routing

from .helpers import decision, score, squire, thresholds, yes


def test_routing_does_not_downgrade_when_nobody_asked_about_a_person():
    d = decision("routing", complexity=score(0.05, 0.95))  # no person_risk at all
    assert routing.decide(d, thresholds()).tier == "default"


def test_routing_still_downgrades_when_the_person_check_answered_no():
    d = decision("routing", complexity=score(0.05, 0.95), person_risk=yes(0.02))
    assert routing.decide(d, thresholds()).tier == "light"


def test_a_plan_line_cannot_go_light_because_plan_never_asks_person_risk():
    d = decision(
        "plan_line", value=score(2.0, 0.9), complexity=score(0.05, 0.9), saturated=yes(0.1)
    )
    assert plan.decide_line(d, thresholds()).tier == "default"


def test_an_edge_is_not_committed_without_a_direction_answer():
    d = decision("edge", stated=yes(0.97))
    assert graph.decide_edge(d, thresholds()).verdict == "review"


def test_an_edge_with_a_confident_direction_still_commits():
    d = decision("edge", stated=yes(0.97), direction=yes(0.95))
    assert graph.decide_edge(d, thresholds()).verdict == "supported"


def test_memory_is_not_written_without_the_derivable_answer():
    d = decision("memory_write", durable=yes(0.9), specific=yes(0.9))
    assert memory.decide_write(d, thresholds()).store is False


def test_derivable_has_its_own_knob_and_raising_act_no_longer_stores_more():
    d = decision("memory_write", durable=yes(0.9), specific=yes(0.9), derivable=yes(0.42))
    assert memory.decide_write(d, thresholds()).store is True
    assert memory.decide_write(d, thresholds(act=0.95)).store is True  # act is no longer read
    assert memory.decide_write(d, thresholds(act=0.50)).store is True
    assert memory.decide_write(d, thresholds(derivable=0.40)).store is False


def test_incoherent_collision_is_flagged_not_discarded_as_a_duplicate():
    d = decision("memory_collision", contradicts=yes(0.95), adds_nothing=yes(0.80))
    assert memory.decide_collision(d, thresholds(), newer=True).action == "flag"


def test_collision_reason_no_longer_claims_no_contradiction_at_065():
    d = decision("memory_collision", contradicts=yes(0.65), adds_nothing=yes(0.03))
    result = memory.decide_collision(d, thresholds())
    assert result.action == "keep_both" and "no contradiction" not in result.reason


class _FailSecondWindow:
    name = "partial"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point, state, questions):  # noqa: ANN001
        self.calls += 1
        if self.calls == 2:
            return Decision(point, {}, self.name, "-", error="down")
        return Decision(point, {"injection": yes(0.01)}, self.name, "jev-test")


def test_a_failed_scan_window_is_a_gap_not_a_clean_result():
    sq, journal = squire(_FailSecondWindow())
    text = "plain text. " * 450  # ~5,400 characters: three windows
    flag = asyncio.run(sq.scan_content(purpose="p", text=text))
    assert flag.flagged is False and flag.complete is False
    event = journal.decisions()[-1]["outcome"]
    assert event["windows_failed"] == 1 and event["scanned_chars"] < len(text)


def test_scan_coverage_counts_the_overlap():
    # Eight 2,000-character windows stepping 1,800 cover 14,600 characters, not 16,000.
    starts = [i * (injection.TEXT_LIMIT - injection.WINDOW_OVERLAP) for i in range(8)]
    assert injection.covered(16_000, starts) == 14_600
    assert injection.covered(3_000, [0, 1_800]) == 3_000


# --- the opt-in `common` policy ----------------------------------------------------------


def test_common_policy_keeps_a_standing_instruction_the_shipped_one_drops():
    # The measured shape of mw-54-like facts: durable, not common, no figures in them.
    d = decision(
        "memory_write", durable=yes(0.86), specific=yes(0.33), derivable=yes(0.36), common=yes(0.03)
    )
    assert memory.decide_write(d, thresholds()).store is False
    assert memory.decide_write_common(d, thresholds()).store is True


def test_common_policy_skips_general_knowledge_and_a_floor_stops_vacuous_pointers():
    common = decision(
        "memory_write", durable=yes(0.9), specific=yes(0.9), derivable=yes(0.3), common=yes(0.9)
    )
    assert memory.decide_write_common(common, thresholds()).store is False
    pointer = decision(
        "memory_write", durable=yes(0.75), specific=yes(0.02), derivable=yes(0.2), common=yes(0.1)
    )
    assert memory.decide_write_common(pointer, thresholds()).store is True  # floor 0: P1
    assert memory.decide_write_common(pointer, thresholds(), specific_floor=0.08).store is False


def test_common_policy_never_stores_without_the_common_answer():
    d = decision("memory_write", durable=yes(0.9), specific=yes(0.9), derivable=yes(0.1))
    assert memory.decide_write_common(d, thresholds()).store is False


def test_asking_common_is_opt_in_and_does_not_move_the_shipped_call():
    _, three = memory.write_questions(fact="x")
    _, four = memory.write_questions(fact="x", ask_common=True)
    assert list(three) == ["durable", "specific", "derivable"]
    assert list(four) == ["durable", "specific", "derivable", "common"]


def test_routing_does_not_downgrade_on_a_doubtful_person_check():
    d = decision("routing", complexity=score(0.05, 0.95), person_risk=yes(0.65))
    assert routing.decide(d, thresholds()).tier == "default"


def test_zero_scan_windows_is_not_a_complete_clean_scan():
    sq, _ = squire(_FailSecondWindow(), max_windows=0)
    flag = asyncio.run(sq.scan_content(purpose="p", text="please pay now"))
    assert flag.flagged is False and flag.complete is False
