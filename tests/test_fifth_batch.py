"""The fifth batch of `edge` and `facts`: what exists of it, pinned. No network.

`docs/results/2026-09-27-edge-facts/fifth-batch.md` reports it. The batch was written, hashed
and blind-annotated first (a 402 from TypeSafe stopped the first attempt), then recorded later
the same day: 120 Jev calls, 0.0034 USD. One rule of the pre-registration licensed a change,
the `direction` question by roles, and it is now the default of `graph.edge_questions`.

What this file pins: the batch is the hashed one, its composition is the pre-registered one,
the second annotator's agreement, the defaults that follow from the verdicts, the verdict
arithmetic on synthetic rows, and the measured numbers.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys
from collections import Counter

import pytest

from sanchopanza import Thresholds
from sanchopanza.contract import Answer, Decision
from sanchopanza.points import entities, graph
from sanchopanza.providers.recorded import key_of

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import fifth_batch as fb  # noqa: E402


def test_the_batch_files_are_the_hashed_ones():
    for line in (fb.OUT / "hashes.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split()
        raw = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == digest, name


def test_the_composition_is_the_pre_registered_one():
    facts = Counter(c["expected"] for c in fb.facts_cases())
    edges = fb.edge_cases()
    assert facts == {"unrelated": 12, "agree": 9, "conflict": 9}
    assert Counter(c["expected"] for c in edges) == {
        "reversed": 12,
        "supported": 12,
        "unsupported": 6,
    }
    passive = re.compile(r"\b(fue|fueron|es|son|sera)\s+\w+(ad|id)(o|a|os|as)\b.*\bpor\b")
    reversed_passive = [
        c["id"] for c in edges if c["expected"] == "reversed" and passive.search(c["input"]["text"])
    ]
    assert sorted(reversed_passive) == sorted(fb.PASSIVE_REVERSED)
    assert len(reversed_passive) >= 6


def test_every_edge_case_reaches_the_decider():
    from sanchopanza.text import mention_present

    for c in fb.edge_cases():
        i = c["input"]
        assert mention_present(i["subject"], i["text"]) and mention_present(i["obj"], i["text"])


def test_the_two_annotators_agree_on_every_case():
    a = fb.annotators()
    assert a["all"] == {"n": 60, "agreement": 1.0, "kappa": 1.0}
    assert a["disputed"] == []


def test_only_the_licensed_variant_is_on_by_default():
    state, qs = entities.fact_questions(fact_a="a", fact_b="b")
    assert "examples" not in qs["relation"].options["unrelated"]
    _, qs_ex = entities.fact_questions(fact_a="a", fact_b="b", unrelated_examples=True)
    assert qs_ex["relation"].options["unrelated"]["examples"] == entities.UNRELATED_EXAMPLES
    assert key_of("facts", state, qs) != key_of("facts", state, qs_ex)

    args = {"subject": "A", "relation": "audita a", "obj": "B", "text": "B fue auditada por A."}
    state, qs = graph.edge_questions(**args)
    _, qs_old = graph.edge_questions(**args, direction_by_roles=False)
    assert qs["direction"] is graph.DIRECTION_BY_ROLES
    assert qs_old["direction"] is not graph.DIRECTION_BY_ROLES
    assert qs_old["stated"] == qs["stated"]
    assert key_of("edge", state, qs) != key_of("edge", state, qs_old)


def _facts_decision(p: dict[str, float]) -> Decision:
    top = max(p, key=p.get)
    k = len(p)
    confidence = (p[top] - 1 / k) / (1 - 1 / k)
    answer = Answer(kind="choice", confidence=confidence, choice=top, probabilities=p)
    return Decision("facts", {"relation": answer}, "test", "jev-1.13.0")


def test_the_candidate_facts_rule_only_adds_unrelated():
    t = Thresholds()
    low_unrelated = _facts_decision({"unrelated": 0.61, "agree": 0.30, "conflict": 0.09})
    low_agree = _facts_decision({"agree": 0.61, "unrelated": 0.30, "conflict": 0.09})
    assert entities.decide_facts(low_unrelated, t)[0] is None  # shipped: abstains
    assert entities.decide_facts(low_unrelated, t, unrelated_at=0.5)[0] == "unrelated"
    assert entities.decide_facts(low_agree, t, unrelated_at=0.5)[0] is None
    under_half = _facts_decision({"unrelated": 0.45, "agree": 0.35, "conflict": 0.20})
    assert entities.decide_facts(under_half, t, unrelated_at=0.5)[0] is None


def _row(expected: str, verdict: str, direction: float = 0.95) -> dict:
    return {"id": "x", "expected": expected, "verdict": verdict, "direction": direction}


def test_the_verdict_arithmetic_is_the_pre_registered_one():
    facts = {
        "shipped": {
            "shipped_policy": {"right": 20, "costly": 1},
            "unrelated_at_half": {"right": 24, "costly": 1},
        },
        "examples": {"shipped_policy": {"right": 22, "costly": 2}},
    }
    old = [_row("reversed", "review")] * 3 + [_row("supported", "supported")]
    new = [_row("reversed", "reversed")] * 3 + [_row("supported", "supported")]
    edge = {"shipped": fb.score_edge(old), "by_roles": fb.score_edge(new)}
    cut = {"derived": 0.88, "reported": {"reaches_target": False}}
    licensed = fb.verdicts(facts, edge, cut)
    assert licensed == {
        "facts_policy_unrelated_at_half": True,
        "facts_wording_examples": False,  # more right, but one costly error more
        "edge_wording_by_roles": True,
        "edge_direction_cut": False,
    }


def test_a_direction_cut_needs_sixteen_clean_commits():
    fifteen = [_row("supported", "supported")] * 15
    assert fb.derive_direction_cut(fifteen) is None
    sixteen = [_row("supported", "supported")] * 16 + [_row("reversed", "supported", 0.87)]
    assert fb.derive_direction_cut(sixteen) == 0.88
    # the fifth batch has 12 supported cases: even 12 of 12 cannot clear 80 %
    assert fb.at_cut([_row("supported", "supported")] * 12, 0.88)["reaches_target"] is False


def test_the_recording_licenses_only_the_direction_wording():
    import asyncio

    if not fb.RECORDING.exists() or not fb.FOURTH.exists():
        pytest.skip("fifth-batch or fourth-batch recording not present")
    report = asyncio.run(fb.run())
    assert report["recording"] == {"calls": 120, "cost_usd": 0.003359}
    facts = report["facts"]
    assert facts["shipped"]["shipped_policy"] == {"n": 30, "decided": 27, "right": 25, "costly": 1}
    assert facts["shipped"]["unrelated_at_half"] == facts["shipped"]["shipped_policy"]
    assert facts["examples"]["shipped_policy"] == {"n": 30, "decided": 26, "right": 25, "costly": 1}
    old, new = report["edge"]["shipped"], report["edge"]["by_roles"]
    assert (old["committed"], old["committed_wrong"], old["reversed_caught"]) == (12, ["ed-57"], 5)
    assert (new["committed"], new["committed_wrong"], new["reversed_caught"]) == (12, [], 10)
    assert (old["passive_reversed_caught"], new["passive_reversed_caught"]) == (1, 6)
    assert report["direction_cut"]["reported"]["reaches_target"] is False
    assert report["licensed"] == {
        "facts_policy_unrelated_at_half": False,
        "facts_wording_examples": False,
        "edge_wording_by_roles": True,
        "edge_direction_cut": False,
    }
    # what the verdicts leave as defaults
    assert entities.decide_facts.__kwdefaults__ == {"unrelated_at": None}
    assert entities.fact_questions.__kwdefaults__ == {"unrelated_examples": False}
    assert graph.edge_questions.__kwdefaults__["direction_by_roles"] is True


def test_the_direction_cut_derived_on_the_fourth_batch_cannot_be_reported_here():
    """Derivation is free (fourth-batch recording); reporting it needs the fifth batch, and
    with 12 supported cases even a perfect 12 of 12 has a Wilson lower bound of 0.757."""
    import asyncio

    from sanchopanza.providers.recorded import RecordedDecider

    if not fb.FOURTH.exists():
        pytest.skip("fourth-batch fixture not present")
    cases = fb.edge_cases(fb.FOURTH_EDGE_BENCHES)
    rows = asyncio.run(fb.edge_rows(RecordedDecider.from_file(fb.FOURTH), cases, by_roles=False))
    s = fb.score_edge(rows)
    assert (s["committed"], s["committed_wrong"], s["reversed_caught"]) == (17, ["ed-26"], 4)
    assert fb.derive_direction_cut(rows) == 0.88
    assert fb.at_cut(rows, 0.88)["wilson95_low"] == 0.806
    twelve = [
        _row(c["expected"], "supported") for c in fb.edge_cases() if c["expected"] == "supported"
    ]
    assert fb.at_cut(twelve, 0.88)["wilson95_low"] == 0.757
