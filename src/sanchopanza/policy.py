"""Thresholds: from calibrated probabilities to actions.

Two principles come from the evidence on routers and from our own measurements:

1. **Asymmetry.** The direction whose error the operator sees (downgrade a model, drop
   a page, deny a command) needs more confidence than the cheap direction (upgrade,
   keep, allow). Badly calibrated routers drift to the majority class; asymmetry stops
   that drift from costing quality.
2. **No data, the default.** Every empty answer, failed call or sub-threshold confidence
   falls back to whatever the harness did before the squire existed. The squire can only
   improve an agent; it can never stop one.

**One number, not two, on a Truth point.** For every Truth answer in every recording in
this repository - 651 of them, zero deviation - the provider's `confidence` is exactly
`|2p - 1|`. So on a Truth-driven decision, probability and confidence are the same quantity,
and a policy that asks for both `p >= a` and `confidence >= c` is really asking for
`p >= max(a, (1 + c) / 2)`. Two gates on one number is one gate at the stricter value, and
the threshold named in the configuration is then not the one in force.

That is not hypothetical: `memory_write` shipped with `remember = 0.70` and a `relax = 0.60`
confidence gate, and enforced 0.80. Four of its measured misses were facts scoring 0.75 and
0.76. The redundant gates were removed in 0.2.0 - **no threshold value changed** - and the
gap between the shipped policy and a plain 0.5 cut fell from eight decisions to three.

A confidence gate still earns its place where there is no probability threshold beside it
and the point wants an abstention band: the citation verdict, the entity alignment band, the
edge check. There it is the only gate, and it is doing work. `tests/test_policy.py` pins the
identity as a canary: if the provider ever starts reporting a confidence that carries
information the probability does not, that test fails and every policy built on it is worth
revisiting.

The defaults below are the production thresholds measured in the paper (docs/paper.md).
They were fixed before the runs and never tuned on results. Per-primitive calibration
(Section 5.8 of the paper) says Truth answers are under-confident and Score answers are
the least reliable; `Thresholds.act` applies to Score-driven decisions and is the one to
keep high.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from typing import Any

from .contract import Answer


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Every knob a policy reads. Flat on purpose: one place, one name per threshold."""

    act: float = 0.75  # confidence needed for the costly direction (downgrade, drop, deny)
    relax: float = 0.60  # confidence needed for the cheap direction (upgrade, keep)
    allow_upgrade: bool = False  # may a task be sent to a deeper model than the default?
    redundant: float = 0.80  # probability that a query repeats an earlier one
    # Probability that a fetched page adds nothing the agent already holds.
    #
    # It shared `redundant` until 2026-09-24, on the stated theory that a repeated query and
    # a repeated page "are the same reading". They are not, and the first derivation large
    # enough to test it said so: 0.80 scores 26/34 out of sample on page redundancy while
    # 0.59 scores 33/34, and search's 0.80 is the value measured at 17/18 on its own bench.
    # One knob serving two points meant neither could move without breaking the other.
    #
    # 0.59 is the first threshold in this repository derived rather than chosen: on 75 new
    # cases, to a 90 % precision target, requiring the 95 % Wilson LOWER bound to clear it,
    # and reported on the 34 cases of a different batch - 100 % precision and 92 % recall
    # held out. The 80 % target derived 0.06 on the same data and MISSED out of sample at
    # 55 % precision, which is the argument for targeting high and the reason the looser
    # target is not the safer one. See `docs/results/2026-09-24-third-batch/`.
    adds_nothing: float = 0.59
    keyword: float = 0.60  # probability that a query is keyword-style (cheap search)
    relevance: float = 0.45  # below this, a page does not enter the context
    # The contribution cut of `Squire.triage_part`. Derived, not chosen: on 300 HotpotQA
    # questions, to 95 % joint recall of the supporting paragraphs at the smallest text kept;
    # confirmed on 300 new ones at 93.3 % joint recall with 52 % of the text kept, where the
    # relevance question at 0.45 kept both paragraphs in 19.7 % (docs/results/2026-09-25-triage).
    contributes: float = 0.28
    # `Squire.triage_pages` (every page asked in one call, the others in view) and
    # `Squire.select_sentences`. Derived on 600 HotpotQA questions, confirmed on 300 new: 98.3 %
    # of supporting pages kept at 34 % of the text in one call, and with sentences selected
    # inside the kept pages, every supporting sentence in 90.3 % at 22 % of the text
    # (docs/results/2026-09-27-chunks/).
    pages_in_context: float = 0.40
    sentences: float = 0.28
    # `Squire.triage_many`, sets past `chunks.PAGE_MAX`: round one in balanced groups keeps
    # p >= this, the survivors are judged together at `pages_in_context`. Derived on 100
    # HotpotQA questions with 100 pages each (round-one recall >= 99 %), confirmed on 200 new:
    # 96.5 % of questions keep both supporting pages at 3.1 % of the text, against 94.0 % at
    # 4.3 % for the groups alone and 50.5 % for BM25 (docs/results/2026-09-27-hierarchy/).
    pages_first_round: float = 0.18
    # `Squire.select_passages`, one long document: only paragraphs the tournament scores
    # at or above this reach the sentence stage, and each kept sentence brings
    # `document_window` neighbours. Fixed on 261 QASPER questions, confirmed on 219 new
    # ones: every answer sentence in 87.2 % at 21.0 % of the text
    # (docs/results/2026-09-28-lateral-wholedocs/). Not for short pages: on HotpotQA it
    # loses 7 points against `select_sentences` alone.
    document_paragraphs: float = 0.75
    document_window: int = 2
    injection: float = 0.70  # above this, a page is dropped and logged
    citation: float = 0.80  # confidence needed for an automatic citation verdict
    review: float = 0.70  # signal needed before the squire speaks about a report
    guard: float = 0.70  # probability needed to add a denial on a shell command
    entity_low: float = 0.25  # below: different entity
    entity_high: float = 0.75  # above: same entity; in between: not sure
    classify: float = 0.60  # probability needed to accept a closed-vocabulary label
    tools: float = 0.35  # below this, a tool group leaves the model's call (in doubt, keep)
    # Probability that a request defers what to do to something unread. It was read from
    # `relax` until 2026-09-25, which is a *confidence* knob for the cheap direction of every
    # point; a probability gate on one point borrowing it meant neither could move alone.
    # Same value, its own name: the failure mode `adds_nothing` was split out for.
    deferred: float = 0.60
    # Probability a group must reach to be ADDED to an open tool window after the agent has
    # read something. Its own knob because the error costs differ from `tools`: a missed
    # addition costs one discovery round trip (the group stays findable), a false one costs
    # its schema for the rest of the session, and an append-only window cannot take it back.
    #
    # NOT derived, and the attempt is on record. It equals `tools` because that is the only
    # measured cut for a per-group question. On 97 AgentDojo trajectories the observe answers
    # held 13 positives in 4,268 (a group called later that the window lacked): no cut clears
    # even a 50 % precision target at the Wilson lower bound, on either half. At 0.35 it adds
    # 51 groups of which 12 were needed (24 %); 20 of the 39 false ones are `web` on travel.
    # A number derived from 13 positives would be sampled, not measured.
    # See docs/results/2026-09-25-window/.
    window_add: float = 0.35
    saturated: float = 0.70  # probability that a research line is exhausted
    # `decide_write` stores iff durable >= remember, specific >= remember and derivable <=
    # `derivable`: one cut on the weakest margin, remember = c and derivable = 1 - c.
    # Derived, not chosen: c = 0.54 on half of the 100 cases, to an 80 % precision target on
    # the 95 % Wilson lower bound; on the other half 94 % precision and 39/49 against 37/49
    # for the previous 0.70 / 0.75 with one costly store against two, and on 108 cases never
    # used for this threshold one costly store against four (docs/results/
    # 2026-09-27-memory-write-cut/, pre-registered). Above `derivable` a candidate is
    # re-readable from its source and is not stored.
    remember: float = 0.54
    derivable: float = 0.46
    # The opt-in `decide_write_common` was measured at 0.70 / 0.75 and keeps them: its own
    # knobs, so that moving the default policy does not move a policy nobody re-measured.
    common_durable: float = 0.70
    common_derivable: float = 0.75
    # Fraction of decisions pre-registered for re-labelling. See `Squire.record`: the
    # point is that the sample is chosen before anyone has seen the outcome, so a
    # threshold can never be tuned on a set someone picked afterwards.
    audit: float = 0.0
    max_decisions: int = 400  # per job
    max_usd: float = 0.10  # per job
    # Windows of `points.injection.TEXT_LIMIT` characters scanned in one content scan. Eight
    # covers 16,000 characters, which is longer than every tool result in the AgentDojo
    # harvest and than most pages. Beyond it the scan stops and says so in the journal: a
    # gap that is recorded is a known limitation, a gap that is silent is the expensive kind.
    max_windows: int = 8

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> Thresholds:
        """Build from a flat mapping (a YAML block, env values). Unknown keys are ignored."""
        raw = raw or {}
        known = {f.name: f.type for f in fields(cls)}
        values: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in known:
                continue
            if key == "allow_upgrade":
                values[key] = _as_bool(value)
            elif key in ("max_decisions", "max_windows", "document_window"):
                values[key] = int(value)
            else:
                values[key] = float(value)
        return cls(**values)

    def with_(self, **changes: Any) -> Thresholds:
        return replace(self, **changes)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def confident(answer: Answer, threshold: float) -> bool:
    """True when the answer exists and its confidence reaches the threshold."""
    return not answer.empty and answer.confidence >= threshold


def probability(answer: Answer, default: float = 0.0) -> float:
    """The truth probability of a Truth answer, or `default` when there is none."""
    return answer.truth if answer.truth is not None else default
