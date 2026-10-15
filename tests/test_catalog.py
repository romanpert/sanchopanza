"""The catalog: a versioned id for every question the squire asks, and what each point reads.

A consumer that imports the questions instead of copying them needs three things from here:
ids that never collide, ids that every builder actually attaches, and a canary that fails
when a question's wording moves without its id saying whether the meaning moved too.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, fields
from typing import Any

import pytest

from sanchopanza import catalog
from sanchopanza.contract import Question, Truth
from sanchopanza.points import (
    chunks,
    citation,
    completion,
    entities,
    graph,
    guard,
    injection,
    loop,
    memory,
    plan,
    review,
    routing,
    search,
    tools,
    triage,
)
from sanchopanza.policy import Thresholds

Built = tuple[Mapping[str, Any], Mapping[str, Question]]
GROUPS = [{"name": "email", "about": "read and send mail"}]

# One sample call per builder, with the variant it should tag. Every catalogued id must be
# reached by one of these, so a question added to the catalog without a builder fails here.
SAMPLES: dict[str, tuple[str, Callable[[], Built]]] = {
    "routing": ("routing", lambda: routing.questions("List the rulings since 2020", brief="b")),
    "search": ("search", lambda: search.questions("sismo Oaxaca", previous=["sismo"])),
    "triage": ("triage", lambda: triage.questions(purpose="p", title="t", text="x")),
    "triage_part": ("triage_part", lambda: triage.contribution_questions(purpose="p", text="x")),
    "completion": ("completion", lambda: completion.questions(task="t", record="r")),
    "triage_pages": (
        "triage_pages",
        lambda: chunks.context_questions(purpose="p", pages=[("a", "x"), ("b", "y")]),
    ),
    "select_sentences": (
        "select_sentences",
        lambda: chunks.sentence_questions(purpose="p", title="t", sentences=["A.", "B."]),
    ),
    "tools": ("tools", lambda: tools.questions(purpose="p", catalog=GROUPS)),
    "tool_window": (
        "tool_window",
        lambda: tools.observe_questions(purpose="p", just_read="r", catalog=GROUPS),
    ),
    "citation": ("citation", lambda: citation.questions("claim", "section")),
    "plan_line": ("plan_line", lambda: plan.line_questions({"title": "t", "goal": "g"})),
    "dependency": (
        "dependency",
        lambda: plan.dependency_questions(a_title="a", a_goal="x", b_title="b", b_goal="y"),
    ),
    "review": ("review", lambda: review.questions("task", "result")),
    "injection": ("injection", lambda: injection.questions(purpose="p", text="x")),
    "guard": ("guard", lambda: guard.questions("ls -la")),
    "guard/coding": (
        "guard",
        lambda: guard.coding_questions("ls -la", environment=guard.coding_environment(".")),
    ),
    "entity": ("entity", lambda: entities.alignment_questions(a="A", b="B")),
    "facts": ("facts", lambda: entities.fact_questions(fact_a="a", fact_b="b")),
    "facts/examples": (
        "facts",
        lambda: entities.fact_questions(fact_a="a", fact_b="b", unrelated_examples=True),
    ),
    "classify": (
        "classify",
        lambda: entities.classification_questions(
            field="court", text="x", options={"civil": "Civil", "criminal": "Criminal"}
        ),
    ),
    "redundant_page": (
        "redundant_page",
        lambda: triage.redundancy_questions(purpose="p", text="x", known="k"),
    ),
    "memory_write": ("memory_write", lambda: memory.write_questions(fact="f", ask_common=True)),
    "memory_collision": (
        "memory_collision",
        lambda: memory.collision_questions(new="a", stored="b"),
    ),
    "recall": ("recall", lambda: memory.recall_questions(turn="t")),
    "extract_gate": ("extract_gate", lambda: graph.gate_questions(chunk="c", looking_for="l")),
    "edge": (
        "edge",
        lambda: graph.edge_questions(subject="s", relation="r", obj="o", text="t"),
    ),
    "edge/possession": (
        "edge",
        lambda: graph.edge_questions(
            subject="s", relation="r", obj="o", text="t", direction_by_roles=False
        ),
    ),
    "loop": ("loop", lambda: loop.questions(goal="g", done="d", pending="p")),
}

# The wording each id stands for, as a fingerprint of the question's content in the sample
# call above. A failure here means a question's text, criteria, options or levels moved.
# If the meaning moved, give it a new version in `catalog.py` (and a new line here); if it
# did not (a typo, a clearer phrase that asks the same thing), update the fingerprint only.
WORDING = {
    "citation.relation@1": "7854d2eb53da",
    "classify.category@1": "4b06665c3a47",
    "completion.done@1": "50e09e575e18",
    "dependency.b_needs_a@1": "f956a6152680",
    "edge.direction@1": "7cb93a636fbe",
    "edge.direction@2": "53c5c73ecf6a",
    "edge.stated@1": "1f83efd52695",
    "entity.same_entity@1": "090f7d5ca715",
    "extract_gate.has_anything@1": "464bd7f31fb5",
    "facts.relation@1": "cc8545c92976",
    "facts.relation_examples@1": "93af0251f431",
    "guard.dangerous@1": "0f4d1d61c407",
    "guard.dangerous_coding@1": "79b854f3dc64",
    "injection.injection@1": "bd34eadd7e13",
    "loop.goal_met@1": "ba770bbdae8e",
    "loop.repeats_check@1": "d3d24b7a2546",
    "memory_collision.adds_nothing@1": "4aee51b01f85",
    "memory_collision.contradicts@1": "f84fea045fa8",
    "memory_write.common@1": "f7764f7297a9",
    "memory_write.derivable@1": "89ffc00d3f9d",
    "memory_write.durable@1": "fa950578e424",
    "memory_write.specific@1": "2bd7ff09f627",
    "plan_line.complexity@1": "66d4ba1af537",
    "plan_line.depends_on_others@1": "7154420cb536",
    "plan_line.saturated@1": "a84b6fa548f7",
    "plan_line.source_kind@1": "4ae6a0d0bf98",
    "plan_line.value@1": "a74b05046abe",
    "recall.needs_memory@1": "b2b7a29cfb06",
    "redundant_page.adds_nothing@1": "87a19665c3e5",
    "review.answered@1": "953770304239",
    "review.saturated@1": "9ac15dfa6614",
    "review.unsourced@1": "aa43f9d11f75",
    "routing.complexity@1": "c669bec50c0f",
    "routing.needs_browser@1": "c1cabf24f4e2",
    "routing.person_risk@1": "d9e6c2e4a553",
    "search.keyword_query@1": "7c654a737765",
    "search.redundant@1": "cc7f3814cb31",
    "search.source_kind@1": "716adeaf04c7",
    "select_sentences.sentence@1": "a8bdb3995371",
    "tool_window.needed@1": "7aef66754561",
    "tools.deferred@1": "44f58136691a",
    "tools.needed@1": "5fe23714858a",
    "triage.evidence@1": "f11810cea5e7",
    "triage.injection@1": "bd34eadd7e13",
    "triage.relevant@1": "726f5f1a6318",
    "triage.source_kind@1": "e912d2f804ac",
    "triage_pages.page@1": "e4b715da056d",
    "triage_part.contributes@1": "1930a5f061c7",
}


def fingerprint(question: Question) -> str:
    body = json.dumps(asdict(question), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def built_ids() -> dict[str, str]:
    """Every id the sample calls attach, with the fingerprint of the first question under it."""
    seen: dict[str, str] = {}
    for point, build in SAMPLES.values():
        _, questions = build()
        for key, qid in catalog.ids_of(point, questions).items():
            assert qid is not None, f"{point}: {key} has no id"
            seen.setdefault(qid, fingerprint(questions[key]))
    return seen


def test_ids_are_unique_and_well_formed() -> None:
    ids = [spec.id for spec in catalog.QUESTIONS.values()]
    assert len(ids) == len(set(ids))
    assert set(catalog.QUESTIONS) == set(ids)
    for qid in ids:
        assert re.fullmatch(r"[a-z_]+\.[a-z_]+@[1-9][0-9]*", qid), qid
        point, name, version = catalog.parse_id(qid)
        assert f"{point}.{name}@{version}" == qid
        assert catalog.question_spec(qid).point == point
    points = [spec.id for spec in catalog.POINTS.values()]
    assert len(points) == len(set(points))
    for name, spec in catalog.POINTS.items():
        assert spec.name == name
        assert spec.id == f"{name}@{spec.version}"
        assert catalog.parse_id(spec.id) == (name, None, spec.version)


def test_one_spec_per_key_and_variant() -> None:
    """Two specs answering the same (point, key, variant) would make an id ambiguous."""
    slots = [(s.point, s.key or s.pattern, s.variant) for s in catalog.QUESTIONS.values()]
    assert len(slots) == len(set(slots))
    for spec in catalog.QUESTIONS.values():
        assert (spec.key is None) != (spec.pattern is None), spec.id
        assert spec.point in catalog.POINTS, spec.id


def test_every_builder_tags_every_question_and_every_id_is_built() -> None:
    assert set(built_ids()) == set(catalog.QUESTIONS)


def test_the_wording_behind_each_id_is_pinned() -> None:
    assert built_ids() == WORDING


@pytest.mark.parametrize(
    ("sample", "key", "expected"),
    [
        ("guard", "dangerous", "guard.dangerous@1"),
        ("guard/coding", "dangerous", "guard.dangerous_coding@1"),
        ("facts", "relation", "facts.relation@1"),
        ("facts/examples", "relation", "facts.relation_examples@1"),
        ("edge", "direction", "edge.direction@2"),
        ("edge/possession", "direction", "edge.direction@1"),
        ("triage_pages", "P02", "triage_pages.page@1"),
        ("select_sentences", "S2", "select_sentences.sentence@1"),
        ("tools", "needed_0", "tools.needed@1"),
    ],
)
def test_variants_and_positional_keys_get_their_own_id(sample: str, key: str, expected: str):
    point, build = SAMPLES[sample]
    assert catalog.ids_of(point, build()[1])[key] == expected


def test_untagged_questions_resolve_by_point_and_key() -> None:
    """A copy of a question (translated, say) asked under a catalogued point and key."""
    plain = {"relevant": Truth("¿Trata `text` de lo que busca `purpose`?"), "mine": Truth("?")}
    assert catalog.ids_of("triage", plain) == {"relevant": "triage.relevant@1", "mine": None}
    assert catalog.ids_of("not_a_point", plain) == {"relevant": None, "mine": None}


def test_explicit_ids_win_over_the_catalog() -> None:
    plain = {"relevant": Truth("?")}
    tagged = catalog.with_ids(plain, {"relevant": "triage.evidence@1"})
    assert tagged == plain  # still the same questions: every other reader sees no difference
    assert catalog.ids_of("triage", tagged) == {"relevant": "triage.evidence@1"}
    assert catalog.ids_of("triage", plain) == {"relevant": "triage.relevant@1"}


def test_with_ids_refuses_an_id_the_catalog_does_not_know_only_when_asked() -> None:
    tagged = catalog.with_ids({"q": Truth("?")}, {"q": "mine.own@3"})
    assert catalog.ids_of("anything", tagged) == {"q": "mine.own@3"}
    with pytest.raises(ValueError):
        catalog.with_ids({"q": Truth("?")}, {"q": "not an id"})
    with pytest.raises(KeyError):
        catalog.with_ids({"q": Truth("?")}, {"other": "triage.relevant@1"})


def test_narrowing_keeps_the_ids() -> None:
    _, questions = SAMPLES["guard/coding"][1]()
    narrowed = catalog.narrowed(questions, ["dangerous"])
    assert catalog.ids_of("guard", narrowed) == {"dangerous": "guard.dangerous_coding@1"}
    assert catalog.narrowed({"a": Truth("?")}, ["a"]) == {"a": Truth("?")}


def test_policies_resolve_and_thresholds_exist() -> None:
    names = {f.name for f in fields(Thresholds)}
    for spec in catalog.POINTS.values():
        assert spec.builders, spec.name
        for builder in spec.builder_functions():
            assert callable(builder), spec.name
        for policy in spec.policy_functions():
            assert callable(policy), spec.name
        for threshold in spec.thresholds:
            assert threshold in names, (spec.name, threshold)
            assert hasattr(Thresholds(), threshold)


def test_point_ids_and_questions_of_a_point() -> None:
    assert catalog.point_id("triage") == "triage@1"
    assert catalog.point_id("unknown") is None
    assert {s.id for s in catalog.POINTS["routing"].questions()} == {
        "routing.complexity@1",
        "routing.needs_browser@1",
        "routing.person_risk@1",
    }


def test_the_catalog_is_read_only() -> None:
    with pytest.raises(TypeError):
        catalog.POINTS["x"] = catalog.POINTS["triage"]  # type: ignore[index]
    with pytest.raises(TypeError):
        catalog.QUESTIONS["x"] = catalog.QUESTIONS["triage.relevant@1"]  # type: ignore[index]
