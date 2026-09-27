"""Agent memory: what to write down, what it collides with, and when to go looking.

A memory pipeline is three judgments per fact, and today every one of them is an LLM call:
*is this worth storing*, *does it collide with something already stored*, and, per turn,
*do we even need to look*. They are classification-shaped: the answer is a yes, a no or one
label out of four. Nothing has to be written, so nothing here needs a model that can write.

The three asymmetries are not the same, and getting them backwards is how a memory rots:

- **Writing** is the costly direction. A junk memory is read on every later turn, for free
  to the model that wrote it and at a price to every one after. Storing needs `act`.
- **Forgetting** is the costly direction too, and it is worse, because it is silent. Dropping
  or replacing a stored fact needs `act`; in doubt both are kept and the collision is flagged.
- **Recall** is the opposite. Skipping a lookup that was needed costs an answer; making one
  that was not needed costs a few hundred tokens. So a lookup happens unless the decider is
  confidently sure it is pointless.

**Code before model, and it matters more here than anywhere else.** Which of two facts is
newer is a timestamp comparison, and this model class reads dates as text (paper, 5.3). So
the decider is never asked *which one wins*. It is asked whether they speak about the same
attribute of the same thing and whether they can both be true; recency comes from the
harness's own metadata, and when the harness does not know, the collision is flagged for a
human instead of resolved by a guess.

Not yet measured against an independent annotator: `benches/memory.jsonl` is single-author,
like the rest, and these three points are newer than the ones in the paper's Section 5.

**A known defect of M1, located but deliberately not patched yet.** On 100 cases the write
gate loses one family systematically: standing instructions and agreements from the client.
Measured on `mw-54`, `mw-59`, `mw-69`, `mw-72`, `mw-74`, the `durable` question answers 0.80
to 0.88 - it sees perfectly well that they will matter later, and its own criteria list "the
client asked for the report in Spanish" as a true example - and then `specific` answers 0.33
to 0.50 and throws them away, because it asks whether a fact "names things, figures, dates or
outcomes" and an instruction names none of those. Two questions in one decision disagreeing
about what the point is for.

Widening `specific` to admit a rule-shaped fact was tried on 2026-09-24 and **reverted after
measuring it**, because it made the failure worse in the direction that matters. It took the
point from 72/100 to 88/100 on the same recording, which looks like a win, and it did it by
turning safe errors into unsafe ones: errors in the costly direction went from 5 to 8, and the
eight were `Panama is in Central America`, `article 29 of Ley 6132 defines...`, `the ruling has 47
pages`. The narrow `specific` gate had been filtering general knowledge and verbatim
quotations *as a side effect* of asking about figures - doing the right job for the wrong
reason - and widening it removed that filter without putting anything in its place.
`derivable` cannot replace it: world knowledge is not re-readable from a source the agent
holds, so the question correctly answers low (0.37 on the ISO example) and lets it through.

So the real gap is that **none of the three questions asks whether the fact is something any
competent reader already knows**, and the fix is a fourth question rather than a looser
third one. It is not in this release because it would be derived from the cases that exposed
it. What it needs: a `common` question, and a fourth batch of cases written before it is
measured. Full account: `docs/results/2026-09-24-third-batch/`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..contract import Decision, Question, Truth
from ..policy import Thresholds, probability
from ..text import truncate

FACT_LIMIT = 500
CONTEXT_LIMIT = 400
TURN_LIMIT = 600
TOPICS_LIMIT = 500


# --- M1: is this worth storing? ---------------------------------------------------------


def common_question() -> Truth:
    """Pre-registered 2026-09-25, NOT in the shipped call until it is measured.

    The gap `docs/results/2026-09-24-third-batch/` located: none of the three shipped
    questions asks whether a fact is something any competent reader already knows. `specific`
    was filtering general knowledge as a side effect of asking about figures, and in doing so
    threw away the client's standing instructions, which name no figure. This asks the
    missing thing directly so `specific` does not have to. Its examples are deliberately not
    taken from any bench.
    """
    return Truth(
        "Is `fact` something a competent reader already knows or could look up in any general "
        "reference - geography, a definition, what a public law or institution says or does, "
        "how a technology works - rather than something learned about this particular client, "
        "case, source or piece of work?",
        criteria={
            "true": {
                "what": "General knowledge, a definition, the content of a public law or "
                "standard, a well-known fact about the world",
                "examples": [
                    "Lisbon is the capital of Portugal",
                    "a notary certifies the authenticity of signatures and documents",
                    "HTTPS encrypts the traffic between a browser and a server",
                ],
            },
            "false": {
                "what": "Something about this client, case, source or work: an instruction or "
                "preference of the client, a quirk of a source, a finding, a decision taken",
                "examples": [
                    "the client asked for the report in Spanish",
                    "this archive only answers requests sent by post",
                    "the two witnesses give different dates for the meeting",
                ],
            },
        },
    )


def write_questions(
    *, fact: str, brief: str = "", source: str = "", ask_common: bool = False
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """Three readings of a candidate memory. None of them asks the model to value it.

    `ask_common` adds the pre-registered fourth reading to the same call. Off by default:
    adding a question to a joint call moves the other answers, and every shipped recording
    was made without it.
    """
    state: dict[str, Any] = {"fact": truncate(fact, FACT_LIMIT)}
    if brief:
        state["brief"] = truncate(brief, CONTEXT_LIMIT)
    if source:
        state["source"] = truncate(source, CONTEXT_LIMIT)
    qs: dict[str, Question] = {
        "durable": Truth(
            "Will `fact` still be true and still matter after the current task is finished?",
            criteria={
                "true": {
                    "what": "A stable property of a person, organization, case or system; a "
                    "decision taken and why; a constraint, preference or rule that will apply "
                    "again",
                    "examples": [
                        "the registry only serves rulings from 2018 onward",
                        "the client asked for the report in Spanish",
                        "we ruled out the 2019 case: different defendant with the same name",
                    ],
                },
                "false": {
                    "what": "State of the current step, a transient value, a plan for the next "
                    "few minutes, or a restatement of the task that was just given",
                    "examples": [
                        "we are on search number four",
                        "the page is loading slowly today",
                        "the user asked us to investigate this company",
                    ],
                },
            },
        ),
        "specific": Truth(
            "Is `fact` concrete enough to be used later without going back to the source: "
            "does it name things, figures, dates or outcomes rather than describe them?",
            criteria={
                "true": {
                    "what": "Names the entity and states the value, outcome or reason",
                    "examples": [
                        "TC/1148/25 annulled articles 34, 35 and 36 of Ley 6132",
                        "the parent company is registered in Panama since 2011",
                    ],
                },
                "false": {
                    "what": "A generality, a summary of the obvious, or a pointer with no content",
                    "examples": [
                        "there is relevant information about the company",
                        "defamation law has changed over the years",
                    ],
                },
            },
        ),
        "derivable": Truth(
            "Could `fact` be recovered at any time, cheaply and exactly, by re-reading a "
            "source the agent already has (`source`, a file, a record it can query again)?",
            criteria={
                "true": {
                    "what": "It is a verbatim copy of, or a direct lookup in, something "
                    "durable and reachable: a file in the repository, a row in the database, "
                    "a document already downloaded",
                    "examples": [
                        "the function is defined in agent/harness/motor.py",
                        "the ruling's text says '500,000 pesos' in its third page",
                    ],
                },
                "false": {
                    "what": "It is a conclusion, a reconciliation between sources, a negative "
                    "result, or something the agent learned by doing and would have to redo",
                    "examples": [
                        "the two registries disagree on the depth; the official one is SGC",
                        "the portal rejects requests without a referer header",
                    ],
                },
            },
        ),
    }
    if ask_common:
        qs = {**qs, "common": common_question()}
    return state, qs


@dataclass(frozen=True, slots=True)
class Write:
    store: bool
    reason: str
    durable: float
    specific: float
    derivable: float


def decide_write(decision: Decision, t: Thresholds) -> Write:
    """Store only on an explicit, confident yes. No data means the harness's default."""
    if decision.failed:
        return Write(False, "decider unavailable: harness default", 0.0, 0.0, 0.0)
    durable, specific = decision.answer("durable"), decision.answer("specific")
    derivable = decision.answer("derivable")
    pd, ps, pr = probability(durable), probability(specific), probability(derivable)
    # All three answers, or no store. `derivable` was left out of this check until
    # 2026-09-25, so a decision missing it stored on the other two: the costly direction
    # (a permanent write) taken on an absent answer.
    if durable.empty or specific.empty or derivable.empty:
        return Write(False, "no data: harness default", pd, ps, pr)
    if pd < t.remember:
        return Write(False, f"not durable ({pd:.2f})", pd, ps, pr)
    if ps < t.remember:
        return Write(False, f"not specific enough ({ps:.2f})", pd, ps, pr)
    if pr > t.derivable:
        return Write(False, f"re-readable from the source ({pr:.2f})", pd, ps, pr)
    return Write(True, f"durable {pd:.2f}, specific {ps:.2f}", pd, ps, pr)


def decide_write_common(decision: Decision, t: Thresholds, *, specific_floor: float = 0.0) -> Write:
    """The opt-in policy for a call made with `write_questions(ask_common=True)`.

    `common` replaces `specific` as the filter for general knowledge, which is the job
    `specific` was doing by accident while throwing away the client's standing instructions.
    Measured 2026-09-25 on batches written before each variant was (docs/results/
    2026-09-25-window/memory.md), agreement / costly errors (stored what should be skipped):

    | | `decide_write` 0.54 | at 0.70 / 0.75 | floor 0 (P1) | floor 0.15 (P3) | floor 0.08 (P4) |
    |---|---|---|---|---|---|
    | memory-e, 48 | 37 / 1 | 25 / 3 | 45 / 1 | 45 / 0 | 46 / 0 |
    | memory-f, 36 | 24 / 0 | 23 / 1 | 28 / 8 | 32 / 3 | 33 / 3 |
    | memory-g, 24 | 13 / 0 | 12 / 0 | 20 / 3 | 22 / 0 | 22 / 0 |

    This policy reads its own `common_durable` / `common_derivable` (0.70 / 0.75), the values
    it was measured at; `decide_write` reads the derived 0.54 cut
    (docs/results/2026-09-27-memory-write-cut/).

    Floor 0 passed its pre-registered test and stores vacuous pointers ("there is relevant
    information in several sources", `specific` <= 0.04). Any floor stops them and loses about
    one standing instruction in twelve (`specific` 0.13 on evidence rules); P3 and P4 failed
    their pre-registered "lose none" criterion by exactly that one. Which trade is right is a
    product decision, so the floor is a parameter and the shipped default does not change.
    """
    if decision.failed:
        return Write(False, "decider unavailable: harness default", 0.0, 0.0, 0.0)
    durable, specific = decision.answer("durable"), decision.answer("specific")
    derivable, common = decision.answer("derivable"), decision.answer("common")
    pd, ps, pr = probability(durable), probability(specific), probability(derivable)
    if durable.empty or derivable.empty or common.empty or (specific_floor and specific.empty):
        return Write(False, "no data: harness default", pd, ps, pr)
    pc = probability(common)
    if pd < t.common_durable:
        return Write(False, f"not durable ({pd:.2f})", pd, ps, pr)
    if pc >= 0.5:
        return Write(False, f"general knowledge ({pc:.2f})", pd, ps, pr)
    if pr > t.common_derivable:
        return Write(False, f"re-readable from the source ({pr:.2f})", pd, ps, pr)
    if ps < specific_floor:
        return Write(False, f"says nothing concrete ({ps:.2f})", pd, ps, pr)
    return Write(True, f"durable {pd:.2f}, not common knowledge ({pc:.2f})", pd, ps, pr)


# --- M2: does it collide with what is already stored? -----------------------------------

Collision = Literal["duplicate", "replace", "flag", "keep_both"]


def collision_questions(*, new: str, stored: str) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """Two readings. Neither of them is 'which one is right', and neither is about dates.

    The first question asks for a *contradiction*, not for a shared attribute. Two facts can
    describe the same field and agree (a second source giving the same figure), and the
    first draft of this point asked only whether the attribute was shared, which sent every
    corroboration to a human as if it were a conflict. Corroboration is the common case in
    an investigation, so that draft would have made the collision check useless.
    """
    state = {"new": truncate(new, FACT_LIMIT), "stored": truncate(stored, FACT_LIMIT)}
    qs: dict[str, Question] = {
        "contradicts": Truth(
            "Do `new` and `stored` state values for the same attribute of the same thing "
            "that cannot both be true at once: a different figure, date, status or outcome "
            "for the same field of the same entity?",
            criteria={
                "true": {
                    "what": "Same entity, same field, incompatible values",
                    "examples": [
                        "'the case is on appeal' and 'the case was closed in 2024'",
                        "'depth 110 km' and 'depth 103 km', both of the same earthquake",
                    ],
                },
                "false": {
                    "what": "Different entities, different fields, or the same field with "
                    "values that can both hold, including the same value from another source "
                    "or a narrower version of the same one",
                    "examples": [
                        "'1,240 homes damaged' and '312 of them structurally severe'",
                        "'registered in Panama' and 'the director resigned in 2022'",
                        "'1,240 homes, per the newspaper' and '1,240 homes, per the bulletin'",
                    ],
                },
            },
        ),
        "adds_nothing": Truth(
            "Read together, does `new` add nothing at all to `stored`: no new entity, value, "
            "qualifier, date or source that `stored` does not already carry?",
            criteria={
                "true": {
                    "what": "A restatement, a shorter form, or the same fact with different "
                    "wording",
                    "examples": ["'the fine was 500,000 pesos' and 'condemned to pay RD$500,000'"],
                },
                "false": {
                    "what": "It corrects a value, narrows it, dates it, sources it, or adds "
                    "any detail",
                    "examples": [
                        "'the fine was 500,000 pesos' against 'the fine was 500,000 pesos, "
                        "reduced on appeal to 200,000'"
                    ],
                },
            },
        ),
    }
    return state, qs


@dataclass(frozen=True, slots=True)
class Reconciliation:
    action: Collision
    reason: str
    contradicts: float
    adds_nothing: float


def decide_collision(
    decision: Decision, t: Thresholds, *, newer: bool | None = None
) -> Reconciliation:
    """What the harness should do with a candidate memory that touches a stored one.

    `newer` is the harness's own answer to "is the new fact more recent than the stored
    one?", from timestamps it already holds. It is never asked of the decider: this model
    class reads dates as text and its own card says so. Without it, a real collision is
    flagged rather than resolved, because replacing the wrong way round is a silent loss.
    """
    if decision.failed:
        return Reconciliation("keep_both", "decider unavailable: both kept", 0.0, 0.0)
    against, nothing = decision.answer("contradicts"), decision.answer("adds_nothing")
    ps, pn = probability(against), probability(nothing)
    if against.empty or nothing.empty:
        return Reconciliation("keep_both", "no data: both kept", ps, pn)
    if pn >= t.act and ps >= t.act:
        # "Adds nothing" and "contradicts" cannot both be true of one pair. Until 2026-09-25
        # the duplicate branch won by position and a correction was discarded as a repeat.
        return Reconciliation(
            "flag", f"incoherent: adds nothing ({pn:.2f}) and contradicts ({ps:.2f})", ps, pn
        )
    if pn >= t.act:
        return Reconciliation("duplicate", f"adds nothing ({pn:.2f})", ps, pn)
    if ps < t.act:
        # Below `act` is "not confident enough to act on", not "no contradiction": the old
        # reason text said the latter at 0.65. Whether the band [0.5, act) should flag, as
        # the module docstring promises, is open and NOT changed here - see
        # docs/results/2026-09-25-window/audit.md.
        return Reconciliation("keep_both", f"contradiction below the bar to act ({ps:.2f})", ps, pn)
    if newer is True:
        return Reconciliation("replace", f"contradicts ({ps:.2f}), the new one is newer", ps, pn)
    if newer is False:
        return Reconciliation(
            "keep_both", f"contradicts ({ps:.2f}), the stored one is newer", ps, pn
        )
    return Reconciliation("flag", f"contradicts ({ps:.2f}), recency unknown", ps, pn)


# --- M3: does this turn need a lookup at all? -------------------------------------------


def recall_questions(
    *, turn: str, topics: str = ""
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """One reading, gated hard: the default is to look."""
    state: dict[str, Any] = {"turn": truncate(turn, TURN_LIMIT)}
    if topics:
        state["topics"] = truncate(topics, TOPICS_LIMIT)
    qs: dict[str, Question] = {
        "needs_memory": Truth(
            "To answer `turn` well, does the agent need something it learned earlier and "
            "would not have in front of it now: a name, a value, a decision already taken, "
            "a preference already stated (`topics` lists what the store holds, if given)?",
            criteria={
                "true": {
                    "what": "It refers back, continues earlier work, or asks about an entity, "
                    "case or preference the store may already describe",
                    "examples": [
                        "carry on with the company we were looking at",
                        "what did we decide about the 2019 case?",
                        "write it up the way the client wants it",
                    ],
                },
                "false": {
                    "what": "Self-contained: everything it needs is in the turn itself, or it "
                    "is a generic operation on text that is already present",
                    "examples": [
                        "translate this paragraph into Spanish",
                        "what is 15 % of 4,200?",
                        "summarise the document I just pasted",
                    ],
                },
            },
        )
    }
    return state, qs


@dataclass(frozen=True, slots=True)
class Recall:
    look: bool
    reason: str
    probability: float


def decide_recall(decision: Decision, t: Thresholds) -> Recall:
    """Skip a lookup only on a confident no. Everything else looks, including a failure."""
    if decision.failed:
        return Recall(True, "decider unavailable: look", 0.0)
    answer = decision.answer("needs_memory")
    p = probability(answer, default=1.0)
    if answer.empty:
        return Recall(True, "no data: look", p)
    if p <= 1.0 - t.act:
        return Recall(False, f"self-contained ({p:.2f})", p)
    return Recall(True, f"may need what we know ({p:.2f})", p)
