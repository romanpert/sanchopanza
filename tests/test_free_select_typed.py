"""The typed, per-condition selection analysis: the pure parts (clause split, type filter,
combination, baselines, rule). No model, no transcript, no money."""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_free_select_typed", ROOT / "benchmarks/browse/free_select_typed.py"
)
typed = importlib.util.module_from_spec(spec)
sys.modules["browse_free_select_typed"] = typed
spec.loader.exec_module(typed)


def test_every_assistantbench_task_has_hand_written_conditions():
    assert len(typed.HAND_CONSTRAINTS) == 25
    assert all(typed.HAND_CONSTRAINTS.values())


def test_split_constraints_keeps_the_longest_clauses_in_order():
    q = "Short one. This clause is long enough to keep; and this one is also long enough here."
    assert typed.split_constraints(q) == (
        "This clause is long enough to keep",
        "and this one is also long enough here.",
    )
    assert typed.split_constraints(q, limit=1) == ("and this one is also long enough here.",)
    assert typed.split_constraints("") == ()


def test_constraint_claim_reads_as_a_predicate_or_quotes_the_clause():
    assert typed.constraint_claim("Bar X", "is a bar", hand=True) == "Bar X is a bar."
    assert typed.constraint_claim("X", "it was founded in a port", hand=False).startswith(
        "X is what this describes:"
    )


def test_top_type_and_kind_for():
    assert typed.top_type({"place": 0.2, "person": 0.7}) == ("person", 0.7)
    assert typed.top_type(None) == (None, 0.0)
    assert typed.kind_for("number_with_unit", 0.9, "name") == "number"
    assert typed.kind_for("number_with_unit", 0.3, "name") == "name"  # unclear: the agent's kind
    assert typed.kind_for(None, 0.0, "") == "name"
    assert typed.kind_for("title", 0.9, "number") == "name"


def test_type_filter_drops_only_firm_incompatible_types():
    assert not typed.keeps("title", 0.9, "website", 0.8)
    assert typed.keeps("place", 0.9, "organisation", 0.8)  # a venue is also a business
    assert typed.keeps("title", 0.9, "website", 0.4)  # the candidate's type is not firm
    assert typed.keeps("title", 0.4, "website", 0.9)  # the question's type is not firm
    assert typed.keeps(None, 0.0, "website", 0.9)
    assert not typed.keeps("person", 0.9, "other", 0.7)


def test_filters_leave_out_comparisons_unless_nothing_else_remains():
    conditions = ("is a bar", "is wheelchair accessible", "is the closest such bar to X")
    assert typed.filters(conditions) == [0, 1]
    assert typed.filters(("is the cheapest price",)) == [0]
    assert typed.filters(("is a mostly quiet bar",)) == [0]  # "mostly" is not "most"


def test_combine_is_the_product_and_needs_every_judgement():
    assert math.isclose(typed.combine([0.5, 0.8]), 0.4)
    assert typed.combine([0.5, None]) is None
    assert typed.combine([]) is None


def test_narration_pick_is_the_most_named_candidate_ties_to_the_higher_rank():
    narration = "I think Renzo Gracie fits. Equinox is a gym. Renzo Gracie again. Equinox too."
    assert typed.narration_pick(["Equinox", "Renzo Gracie"], narration, "name") == ("Equinox", 1.0)
    assert typed.narration_pick(["Nothing Here"], narration, "name") is None


def view(success, pick, own=False, gold=False, answered=True, in_set=True):
    return {
        "answered": answered,
        "success": success,
        "gold_in_set": in_set,
        "mean_call_usd": 0.1,
        "typed_pick": pick,
        "typed_is_own": own,
        "typed_is_gold": gold,
    }


def test_outcome_counts_fires_fixes_risks_and_the_gold_pick_rate():
    views = [
        view(False, ("gold", 0.8), gold=True),
        view(False, ("junk", 0.6)),
        view(True, ("own", 0.9), own=True, gold=True),
        view(True, ("junk", 0.2), in_set=False),
    ]
    out = typed.outcome(views, "typed", 0.5)
    assert (out["fires"], out["would_fix_upper_bound"], out["fires_on_right_risk"]) == (2, 1, 0)
    assert out["pick_is_gold_when_gold_in_set"] == "2/3"
    assert not typed.fires(view(False, ("x", 0.9), answered=False), "typed", 0.5)
