"""Building a knowledge graph: which chunks deserve an extraction call, and which of the
triples that come back are actually in the text.

Graph construction is the clearest case of the substitution economy in this package. A
GraphRAG-style pipeline sends *every* chunk of the corpus to a generative model to have
entities and relations pulled out of it, and then sends candidate pairs back to have
duplicates merged. Extraction has to generate, so it stays where it is. The two judgments
around it do not:

- **The gate.** Most chunks of a real corpus contain nothing the schema is looking for:
  boilerplate, navigation, legal footers, tables of contents, acknowledgements. Asking
  whether a chunk contains anything at all costs 29 millionths of a dollar; extracting from
  it costs a generative call with its output. Skipping a chunk that had something costs
  graph coverage, so the gate only skips on a confident no.
- **The edge check.** Extraction hallucinates relations that the chunk does not state, and
  a wrong edge is worse than a missing one because everything downstream believes it. The
  check is the verify-and-escalate cascade of the citation point, applied to a triple: the
  subject and object strings are matched in the text by code, and only the relation between
  them is asked of the decider.

Entity resolution, the third judgment, is already `entities.alignment_questions`, and it
is the one with a measured number (24/24 on hard pairs, paper G1).

Not yet measured against an independent annotator: `benches/graph-build.jsonl` is
single-author, and these two points are newer than the ones in the paper's Section 5.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..contract import Decision, Question, Truth
from ..policy import Thresholds, confident, probability
from ..text import truncate

CHUNK_LIMIT = 1200
SCHEMA_LIMIT = 500
TRIPLE_LIMIT = 200


# --- G5: is this chunk worth an extraction call? ----------------------------------------


def gate_questions(
    *, chunk: str, looking_for: str, kinds: Sequence[str] = ()
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """`looking_for` states the extraction schema in one phrase; `kinds` names its types."""
    state: dict[str, Any] = {
        "looking_for": truncate(looking_for, SCHEMA_LIMIT),
        "chunk": truncate(chunk, CHUNK_LIMIT),
    }
    if kinds:
        state["kinds"] = [str(k) for k in kinds]
    qs: dict[str, Question] = {
        "has_anything": Truth(
            "Does `chunk` state at least one thing of the kind `looking_for` describes "
            "(`kinds` lists the types, if given): a named entity of that sort, or a relation "
            "or attribute of one?",
            criteria={
                "true": {
                    "what": "Names at least one instance and says something about it, even in "
                    "passing, even if the chunk is mostly about something else",
                    "examples": [
                        "a paragraph of a ruling that names the defendant and the sentence",
                        "a sentence of a news article that names the company and its owner",
                    ],
                },
                "false": {
                    "what": "Structural or generic text with no instance in it: navigation, "
                    "headers and footers, a table of contents, a cookie notice, boilerplate "
                    "legal text, a list of section titles, generalities about the domain",
                    "examples": [
                        "'Inicio | Noticias | Contacto | Aviso legal'",
                        "'This site uses cookies to improve your experience.'",
                        "'Defamation is regulated by law in most jurisdictions.'",
                    ],
                },
            },
        )
    }
    return state, qs


@dataclass(frozen=True, slots=True)
class Gate:
    extract: bool
    reason: str
    probability: float


def decide_gate(decision: Decision, t: Thresholds) -> Gate:
    """Skip the extraction call only on a confident no. Everything else extracts."""
    if decision.failed:
        return Gate(True, "decider unavailable: extract", 0.0)
    answer = decision.answer("has_anything")
    p = probability(answer, default=1.0)
    if answer.empty:
        return Gate(True, "no data: extract", p)
    if p <= 1.0 - t.act:
        return Gate(False, f"nothing of that kind ({p:.2f})", p)
    return Gate(True, f"may contain something ({p:.2f})", p)


# --- G6: does the text actually state this edge? ----------------------------------------


# The shipped `direction` question asks which side "has" the relation and which it is "had
# towards": a possession wording. The misses of the fourth batch cluster on actions read from
# a passive sentence (ed-24, ed-26, ed-30, ed-45, ed-47). This variant asks by roles, for
# actions as well as possession, and says how to read a passive. Written for the fifth batch
# (docs/results/2026-09-27-edge-facts/prereg.md); off by default until that batch licenses it.
DIRECTION_BY_ROLES = Truth(
    "If the relation is there at all, does `text` give the roles as the triple does: "
    "`triple.subject` as the one that does, holds or is the source of `triple.relation`, and "
    "`triple.object` as the one it is done to, held by or directed at? Judge by roles, not "
    "by word order: in a passive sentence the one that acts comes after 'por' or 'by'.",
    criteria={
        "true": {
            "what": "The triple's subject is the one the text has doing or holding the "
            "relation, whether the sentence is active or passive",
            "examples": [
                "text: 'the permit was granted to Alfa by the city council' for "
                "(city council, granted a permit to, Alfa)",
                "text: 'Delta is a subsidiary of Omega' for (Omega, parent_of, Delta)",
            ],
        },
        "false": {
            "what": "The text states the same relation with the roles swapped: the triple's "
            "subject is the one it is done to, held by or directed at",
            "examples": [
                "text: 'the accounts of Beta were audited by Gamma' for (Beta, audits, Gamma)",
                "text: 'Omega is the parent of Delta' for (Delta, parent_of, Omega)",
            ],
        },
    },
)


def edge_questions(
    *, subject: str, relation: str, obj: str, text: str, direction_by_roles: bool = True
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """One reading of a candidate triple against the chunk it was extracted from.

    `direction` asks who does, holds or is the source of the relation (`DIRECTION_BY_ROLES`),
    licensed by the fifth batch (docs/results/2026-09-27-edge-facts/fifth-batch.md).
    `direction_by_roles=False` is the earlier possession wording, kept so the recordings made
    with it still replay.
    """
    state = {
        "triple": {
            "subject": truncate(subject, TRIPLE_LIMIT),
            "relation": truncate(relation, TRIPLE_LIMIT),
            "object": truncate(obj, TRIPLE_LIMIT),
        },
        "text": truncate(text, CHUNK_LIMIT),
    }
    qs: dict[str, Question] = {
        "stated": Truth(
            "Does `text` state that `triple.subject` stands in the relation "
            "`triple.relation` to `triple.object`?",
            criteria={
                "true": {
                    "what": "The text says it, in any wording, including as an apposition or "
                    "a subordinate clause",
                    "examples": [
                        "text: 'Inversiones Delta, propiedad de Mario Reyes desde 2011' for "
                        "(Mario Reyes, owns, Inversiones Delta)"
                    ],
                },
                "false": {
                    "what": "The text mentions both but does not state this relation between "
                    "them, states a different relation, states the reverse, or only makes it "
                    "plausible",
                    "examples": [
                        "text: 'Reyes declared before the court about Inversiones Delta' for "
                        "(Mario Reyes, owns, Inversiones Delta)",
                        "text: 'the parent company of Delta is Omega' for "
                        "(Delta, parent_of, Omega)",
                    ],
                },
            },
        ),
        "direction": Truth(
            "If the relation is there at all, is it in the direction the triple states, with "
            "`triple.subject` as the one that has it and `triple.object` as the one it is "
            "had towards, rather than the other way round?",
            criteria={
                "true": {"what": "The text's direction matches the triple's"},
                "false": {
                    "what": "The text states the same relation with the roles swapped",
                    "examples": [
                        "text: 'Omega is the parent of Delta' for (Delta, parent_of, Omega)"
                    ],
                },
            },
        ),
    }
    if direction_by_roles:
        qs = {**qs, "direction": DIRECTION_BY_ROLES}
    return state, qs


@dataclass(frozen=True, slots=True)
class EdgeCheck:
    verdict: str  # "supported" | "reversed" | "unsupported" | "review"
    stated: float
    direction: float
    confidence: float

    @property
    def commit(self) -> bool:
        return self.verdict == "supported"


def decide_edge(decision: Decision, t: Thresholds, *, mentions_found: bool = True) -> EdgeCheck:
    """Commit a triple only on a confident yes in the stated direction.

    `mentions_found` is code's own answer to whether both strings appear in the text at all,
    the same literal check the citation point does before spending a call. A triple whose
    subject or object is not in the chunk was invented by the extractor, and no model has
    to be asked about it.
    """
    if not mentions_found:
        return EdgeCheck("unsupported", 0.0, 0.0, 1.0)
    if decision.failed:
        return EdgeCheck("review", 0.0, 0.0, 0.0)
    stated, direction = decision.answer("stated"), decision.answer("direction")
    ps, pdir = probability(stated), probability(direction, default=1.0)
    if stated.empty:
        return EdgeCheck("review", ps, pdir, 0.0)

    # The direction is read FIRST, and the order is the whole fix. Fifty cases with eleven
    # reversed triples produced `reversed` exactly zero times, because `stated` was gated on
    # `citation` (0.80) before `direction` was ever looked at - and a reversed triple is
    # precisely the case where `stated` is unsure, since the relation is there but not as
    # written. On `ed-22` the decision already contained `direction` 0.05 at confidence 0.90:
    # the model knew, we had paid for the answer, and the policy threw it away and abstained.
    # A confident "the roles are swapped" is a verdict, not a reason to ask a person.
    if not direction.empty and pdir < 0.5 and confident(direction, t.relax):
        return EdgeCheck("reversed", ps, pdir, direction.confidence)

    if not confident(stated, t.citation):
        return EdgeCheck("review", ps, pdir, stated.confidence)
    if ps < 0.5:
        return EdgeCheck("unsupported", ps, pdir, stated.confidence)

    # Doubt about the direction must not commit. `ed-47` answered `direction` 0.57 at
    # confidence 0.14 - an honest "I do not know" - and the old order read that as "the
    # direction is fine" and committed a backwards edge, which is the one error in this
    # point that nothing downstream can catch. Invariant 2 of the package says the costly
    # direction needs more confidence; committing is the costly direction here.
    #
    # An ABSENT direction answer is doubt too. Until 2026-09-25 this line read
    # `not direction.empty and ...`, so a decision with no `direction` at all committed the
    # edge on `stated` alone - the policy's one irreversible action taken on a missing answer.
    if direction.empty or not confident(direction, t.relax):
        return EdgeCheck("review", ps, pdir, direction.confidence)
    return EdgeCheck("supported", ps, pdir, stated.confidence)
