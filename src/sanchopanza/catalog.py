"""The catalog: a versioned id for every question the squire asks, and what each point reads.

An agent with its own harness that imports these questions, rather than copying them, needs
names that do not move when the wording does. Here each point has an id (`triage@1`) and
each question one (`triage.relevant@1`): the point it belongs to, its name, and a version.

    from sanchopanza import catalog

    catalog.point_id("triage")                 # 'triage@1'
    catalog.POINTS["triage"].thresholds        # ('relevance', 'act', 'injection')
    state, qs = catalog.POINTS["triage"].builder_functions()[0](purpose=..., text=...)
    catalog.ids_of("triage", qs)               # {'relevant': 'triage.relevant@1', ...}

**What a version promises.** The same id asks the same thing. A question keeps its version
through a translation or a rewording that asks the same thing (a typo, a clearer phrase), and
takes a new one when what it asks moves: another boundary in its criteria, another option or
level set, another reading of the state. `tests/test_catalog.py` pins a fingerprint of the
wording behind every id, so a change of wording fails there until someone says which of the
two it was.

**Where the ids live.** Every builder in `sanchopanza.points` the squire calls returns its
questions tagged (`tag`): a plain `dict` that also carries `ids`, so every provider, cache and
text key sees exactly what it saw before. Questions without a tag (a copy, a translation)
resolve by their point and key against this catalog; a key the catalog does not know has no
id. `with_ids` tags questions by hand.

**Variants.** Where one key under one point is asked with two wordings that mean different
things, each wording has its own id and its builder says which (`guard.dangerous@1` for the
research sandbox, `guard.dangerous_coding@1` for a person's repository). The untagged default
is the first.

**What is covered.** The points the `Squire` asks and the builders behind them. The harness
points (the Claude Code hooks, candor, the context autopilot, browsing) are not catalogued
yet: their questions have no id and an id key signs their text (`providers.recorded`).

This module imports nothing heavy: builders and policies are named by dotted path and
resolved on demand, so a hook that reads an id does not load the points.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from importlib import import_module
from types import MappingProxyType
from typing import Any

_ID = re.compile(r"^([a-z_][a-z0-9_]*)(?:\.([a-z_][a-z0-9_]*))?@([1-9][0-9]*)$")


@dataclass(frozen=True, slots=True)
class QuestionSpec:
    """One question: the point that asks it, its name and version, and the key (or the
    pattern of keys, for positional questions such as `P01`) it is asked under."""

    point: str
    name: str
    version: int = 1
    key: str | None = None
    pattern: str | None = None
    variant: str = ""  # "" is the wording an untagged question resolves to

    @property
    def id(self) -> str:
        return f"{self.point}.{self.name}@{self.version}"

    def matches(self, key: str) -> bool:
        if self.key is not None:
            return key == self.key
        return self.pattern is not None and re.fullmatch(self.pattern, key) is not None


@dataclass(frozen=True, slots=True)
class PointSpec:
    """One decision point: its name and version, the builders that ask it, the policies that
    act on its answers, and the `Thresholds` fields those policies read."""

    name: str
    version: int = 1
    builders: tuple[str, ...] = ()
    policies: tuple[str, ...] = ()
    thresholds: tuple[str, ...] = ()
    _questions: tuple[QuestionSpec, ...] = field(default=(), repr=False)

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    def questions(self) -> tuple[QuestionSpec, ...]:
        return self._questions

    def builder_functions(self) -> tuple[Any, ...]:
        return tuple(_resolve(target) for target in self.builders)

    def policy_functions(self) -> tuple[Any, ...]:
        return tuple(_resolve(target) for target in self.policies)


def _resolve(target: str) -> Any:
    module, _, attribute = target.partition(":")
    return getattr(import_module(module), attribute)


def _q(
    name: str, *, key: str | None = None, pattern: str | None = None, version: int = 1,
    variant: str = "",
) -> tuple[str, int, str | None, str | None, str]:  # fmt: skip
    """A question row: asked under `key` (its own name by default) or under `pattern`."""
    return name, version, None if pattern is not None else (key or name), pattern, variant


_P = "sanchopanza.points."
_Row = tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[Any, ...]]
_TABLE: tuple[_Row, ...] = (
    # (point, builders, policies, thresholds the policies read, questions)
    ("routing", (_P + "routing:questions",), (_P + "routing:decide",),
     ("act", "relax", "allow_upgrade"),
     (_q("complexity"), _q("needs_browser"), _q("person_risk"))),
    ("search", (_P + "search:questions",), (_P + "search:decide",), ("redundant", "keyword"),
     (_q("redundant"), _q("source_kind"), _q("keyword_query"))),
    ("triage", (_P + "triage:questions",), (_P + "triage:decide",),
     ("relevance", "act", "injection"),
     (_q("relevant"), _q("evidence"), _q("injection"), _q("source_kind"))),
    ("triage_part", (_P + "triage:contribution_questions",), (_P + "triage:decide_part",),
     ("contributes",), (_q("contributes"),)),
    ("completion", (_P + "completion:questions",), (_P + "completion:decide",), ("done",),
     (_q("done"),)),
    ("triage_pages", (_P + "chunks:context_questions",), (_P + "hierarchy:tournament",),
     ("pages_in_context", "pages_first_round"), (_q("page", pattern=r"P\d{2,}"),)),
    ("select_sentences", (_P + "chunks:sentence_questions",), (_P + "passages:sentence_stage",),
     ("sentences", "document_paragraphs", "document_window"),
     (_q("sentence", pattern=r"S\d+"),)),
    ("tools", (_P + "tools:questions",), (_P + "tools:select",), ("tools", "deferred"),
     (_q("deferred"), _q("needed", pattern=r"needed_\d+"))),
    ("tool_window", (_P + "tools:observe_questions",), (_P + "tools:additions",),
     ("window_add",), (_q("needed", pattern=r"needed_\d+"),)),
    ("citation", (_P + "citation:questions",), (_P + "citation:decide",), ("citation",),
     (_q("relation"),)),
    ("plan_line", (_P + "plan:line_questions",), (_P + "plan:decide_line",), ("saturated",),
     (_q("value"), _q("depends_on_others"), _q("saturated"), _q("complexity"),
      _q("source_kind"))),
    ("dependency", (_P + "plan:dependency_questions",),
     ("sanchopanza.dag:build_dag", "sanchopanza.dag:waves"), (), (_q("b_needs_a"),)),
    ("review", (_P + "review:questions",), (_P + "review:decide",), ("review",),
     (_q("answered"), _q("saturated"), _q("unsourced"))),
    ("injection", (_P + "injection:questions",), (_P + "injection:decide",),
     ("injection", "max_windows"), (_q("injection"),)),
    ("guard", (_P + "guard:questions", _P + "guard:coding_questions"), (_P + "guard:decide",),
     ("guard",),
     (_q("dangerous"), _q("dangerous_coding", key="dangerous", variant="coding"))),
    ("entity", (_P + "entities:alignment_questions",), (_P + "entities:decide_alignment",),
     ("entity_low", "entity_high"), (_q("same_entity"),)),
    ("facts", (_P + "entities:fact_questions",), (_P + "entities:decide_facts",), ("relax",),
     (_q("relation"), _q("relation_examples", key="relation", variant="examples"))),
    ("classify", (_P + "entities:classification_questions",),
     (_P + "entities:decide_classification",), ("classify",), (_q("category"),)),
    ("redundant_page", (_P + "triage:redundancy_questions",), (_P + "triage:decide_redundancy",),
     ("adds_nothing",), (_q("adds_nothing"),)),
    ("memory_write", (_P + "memory:write_questions",),
     (_P + "memory:decide_write", _P + "memory:decide_write_common"),
     ("remember", "derivable", "common_durable", "common_derivable"),
     (_q("durable"), _q("specific"), _q("derivable"), _q("common"))),
    ("memory_collision", (_P + "memory:collision_questions",), (_P + "memory:decide_collision",),
     ("act",), (_q("contradicts"), _q("adds_nothing"))),
    ("recall", (_P + "memory:recall_questions",), (_P + "memory:decide_recall",),
     ("recall_skip", "act"), (_q("needs_memory"),)),
    ("extract_gate", (_P + "graph:gate_questions",), (_P + "graph:decide_gate",),
     ("extract_skip", "act"), (_q("has_anything"),)),
    # `direction` changed meaning on 2026-09-27: from who possesses to who does, holds or is
    # the source of the relation. Version 2 is the default; 1 is kept for its recordings.
    ("edge", (_P + "graph:edge_questions",), (_P + "graph:decide_edge",), ("citation", "relax"),
     (_q("stated"), _q("direction", version=2),
      _q("direction", version=1, variant="possession"))),
    ("loop", (_P + "loop:questions",), (_P + "loop:decide",),
     ("goal_met", "repeats_check", "saturated"), (_q("goal_met"), _q("repeats_check"))),
)  # fmt: skip


def _build() -> tuple[Mapping[str, PointSpec], Mapping[str, QuestionSpec]]:
    points: dict[str, PointSpec] = {}
    questions: dict[str, QuestionSpec] = {}
    for name, builders, policies, thresholds, rows in _TABLE:
        specs = tuple(
            QuestionSpec(name, q_name, version, key, pattern, variant)
            for q_name, version, key, pattern, variant in rows
        )
        points[name] = PointSpec(name, 1, builders, policies, thresholds, specs)
        for spec in specs:
            if spec.id in questions:
                raise ValueError(f"duplicate question id {spec.id}")
            questions[spec.id] = spec
    return MappingProxyType(points), MappingProxyType(questions)


POINTS, QUESTIONS = _build()


def parse_id(text: str) -> tuple[str, str | None, int]:
    """`triage.relevant@1` -> ('triage', 'relevant', 1); `triage@1` -> ('triage', None, 1)."""
    found = _ID.match(text)
    if found is None:
        raise ValueError(f"not an id: {text!r} (expected point@N or point.name@N)")
    point, name, version = found.groups()
    return point, name, int(version)


def point_id(point: str) -> str | None:
    """The versioned id of a catalogued point, or None."""
    spec = POINTS.get(point)
    return None if spec is None else spec.id


def question_spec(question_id: str) -> QuestionSpec:
    return QUESTIONS[question_id]


def question_id(point: str, key: str, *, variant: str = "") -> str | None:
    """The id a question asked under `point` and `key` has: the variant's when it has one
    for that key, else the default wording's. None when the catalog does not know it."""
    spec = POINTS.get(point)
    if spec is None:
        return None
    matching = [q for q in spec.questions() if q.matches(key)]
    chosen = [q for q in matching if q.variant == variant] or [
        q for q in matching if q.variant == ""
    ]
    return chosen[0].id if chosen else None


class Questions(dict[str, Any]):
    """A dict of questions that also knows the versioned id of each one.

    Everything that reads questions reads the dict; only `ids_of` reads `ids`. So a tagged
    set and the same set untagged give the same text key, the same request on the wire and
    the same cache entry.
    """

    __slots__ = ("ids",)

    def __init__(self, questions: Mapping[str, Any], ids: Mapping[str, str]) -> None:
        super().__init__(questions)
        self.ids: Mapping[str, str] = MappingProxyType(dict(ids))

    def __reduce__(self) -> Any:
        return (Questions, (dict(self), dict(self.ids)))


def with_ids(questions: Mapping[str, Any], ids: Mapping[str, str]) -> Questions:
    """Tag questions with ids by hand: a translated copy, or questions of your own (`mine.x@1`).
    Every id must be well formed and every key one of the questions'; keys left out resolve
    against the catalog as untagged ones do."""
    for key, value in ids.items():
        if key not in questions:
            raise KeyError(f"{key!r} is not one of the questions")
        _, name, _ = parse_id(value)
        if name is None:
            raise ValueError(f"{value!r} is a point id; a question id is point.name@N")
    return Questions(questions, ids)


def tag(point: str, questions: Mapping[str, Any], *, variant: str = "") -> Questions:
    """The catalog's ids on a builder's questions. What the builders in `points` return."""
    ids = {k: qid for k in questions if (qid := question_id(point, k, variant=variant))}
    return Questions(questions, ids)


def ids_of(point: str, questions: Mapping[str, Any]) -> dict[str, str | None]:
    """The id of every question: its tag, else the catalog's for its point and key, else None."""
    tagged: Mapping[str, str] = getattr(questions, "ids", None) or {}
    return {key: tagged.get(key) or question_id(point, key) for key in questions}


def narrowed(questions: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    """The questions under `keys`, keeping their ids when they had them. For a chain that asks
    the next decider only for what is still unanswered."""
    wanted = [k for k in keys if k in questions]
    subset = {k: questions[k] for k in wanted}
    tagged: Mapping[str, str] | None = getattr(questions, "ids", None)
    if tagged is None:
        return subset
    return Questions(subset, {k: tagged[k] for k in wanted if k in tagged})


__all__ = [
    "POINTS",
    "QUESTIONS",
    "PointSpec",
    "QuestionSpec",
    "Questions",
    "ids_of",
    "narrowed",
    "parse_id",
    "point_id",
    "question_id",
    "question_spec",
    "tag",
    "with_ids",
]
