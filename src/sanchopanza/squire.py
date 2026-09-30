"""The squire: one decider, one set of thresholds, one journal, one budget.

Every method is a decision point with the same shape:

    build questions -> decide (or not) -> apply the pure policy -> journal -> return

Three guarantees that are not negotiable:

- **Fail-open.** If the decider does not answer, the method returns the default the harness
  had before, and the error is journaled. A provider outage degrades routing; it never
  stops a job.
- **Own budget.** Decisions and dollars per job. A decision costs a ten-thousandth of a
  dollar; a loop without a cap charges anyway.
- **Everything is written.** Each decision goes to the journal with its probabilities,
  confidence, cost, latency and the policy outcome. It is the audit trail and, later, the
  labelled set thresholds are tuned on.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from .budget import Meter
from .contract import Decider, DeciderUnavailable, Decision, Question, State
from .dag import Edge, build_dag, waves
from .journal import Journal, NullJournal, decision_event
from .points import (
    chunks,
    citation,
    completion,
    entities,
    graph,
    guard,
    hierarchy,
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
from .policy import Thresholds
from .providers.null import NullDecider
from .text import is_repeat, mention_present, quote_present, split_sentences


@dataclass(frozen=True, slots=True)
class GuardResult:
    denied: bool
    origin: str | None  # "code" | "decider" | None
    reason: str
    probability: float


class Squire:
    def __init__(
        self,
        decider: Decider | None = None,
        *,
        thresholds: Thresholds | None = None,
        journal: Journal | None = None,
        brief: str = "",
        profile: str = "",
        redact: Callable[[State], State] | None = None,
    ) -> None:
        # `is not None`, not truthiness: `RecordedDecider` defines `__len__` as its count of
        # exact keys, so a recording holding only defaults was falsy and silently replaced by
        # the null decider - every answer empty, no error.
        self._decider: Decider = decider if decider is not None else NullDecider()
        self._t = thresholds if thresholds is not None else Thresholds()
        self._journal: Journal = journal if journal is not None else NullJournal()
        self._brief = brief
        self._profile = profile
        # Runs on every state before a provider sees it (review M7; see `redact.py`).
        self._redact = redact
        self._meter = Meter()
        self._queries: tuple[str, ...] = ()
        self._cap_warned = False
        self._last_selection: frozenset[str] | None = None
        self._churn_warned = False
        self._model_seen: str | None = None
        self._model_warned = False

    def fork(self) -> Squire:
        """A fresh squire - new meter, no history - with this one's configuration.

        Same decider, thresholds, journal, brief, profile and redactor. For a harness that
        serves several users or conversations from one template: each gets its own budget and
        its own query memory. It lives here, not in each adapter, so that a setting added to
        the squire (the redactor was the first) cannot be silently dropped by a copy.
        """
        return Squire(
            self._decider,
            thresholds=self._t,
            journal=self._journal,
            brief=self._brief,
            profile=self._profile,
            redact=self._redact,
        )

    # --- plumbing --------------------------------------------------------------------

    @property
    def thresholds(self) -> Thresholds:
        return self._t

    @property
    def meter(self) -> Meter:
        return self._meter

    @property
    def journal(self) -> Journal:
        return self._journal

    @property
    def provider(self) -> str:
        return self._decider.name

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        """One decision under the cap and fail-open. Never raises."""
        if not self._meter.within(self._t.max_decisions, self._t.max_usd):
            if not self._cap_warned:
                self._cap_warned = True
                self._journal.record(
                    "warning", {"message": "squire budget exhausted: defaults from here on"}
                )
            return Decision(point, {}, "budget", "-", error="budget exhausted")
        if self._redact is not None:
            try:
                state = self._redact(state)
            except Exception as error:  # never send the state the redactor failed to clean
                return Decision(
                    point, {}, self._decider.name, "-", error=f"redaction failed: {error!r}"
                )
        self._meter = self._meter.reserve()
        try:
            decision = await self._decider.decide(point, state, questions)
        except DeciderUnavailable as error:
            decision = Decision(point, {}, self._decider.name, "-", error=str(error))
        except Exception as error:  # a provider bug must not take the agent down
            decision = Decision(
                point, {}, self._decider.name, "-", error=f"{error.__class__.__name__}: {error}"
            )
        self._meter = self._meter.charge(decision.cost_usd)
        return decision

    @property
    def exhausted(self) -> bool:
        """True once the cap is reached. Not an outage: an attacker can cause it, by feeding
        long documents, so a policy must not answer it the way it answers a provider down."""
        return not self._meter.within(self._t.max_decisions, self._t.max_usd)

    def record(self, decision: Decision, **outcome: Any) -> None:
        self._warn_if_the_model_changed(decision)
        event = decision_event(decision, outcome)
        if self._sampled_for_audit(decision):
            event["audit"] = True
        self._journal.record("decision", event)

    def _warn_if_the_model_changed(self, decision: Decision) -> None:
        """Say so, once, if two different models answered within one session.

        Thresholds are calibrated against a version. The vendor's own guidance is to pin one
        rather than track an alias, because "an alias moves when a new release ships, so the
        answers behind it can change without a change on your side". A non-generative model
        gives no signal when that happens: no error, no failing test, no odd-looking output.
        The one observable is the model id the response carries, so the squire watches it.
        """
        model = decision.model
        if not model or model == "-" or decision.failed:
            return
        if self._model_seen is None:
            self._model_seen = model
            return
        if model != self._model_seen and not self._model_warned:
            self._model_warned = True
            self._journal.record(
                "warning",
                {
                    "message": "two different model versions answered within one session. "
                    "Thresholds are calibrated per version; pin one instead of tracking an "
                    "alias.",
                    "first": self._model_seen,
                    "now": model,
                },
            )

    def _sampled_for_audit(self, decision: Decision) -> bool:
        """Is this decision in the pre-registered sample to be re-labelled later?

        `Thresholds.audit` is the fraction, and the choice is a hash of the decision's own
        answers, so it is **deterministic and reproducible**: the same decision is always in
        the sample or always out, and the sample is fixed before anyone has seen whether the
        decision was right. That is the whole point. The failure this prevents is the one
        that inflates every published result in this area: tuning a threshold on cases
        chosen after the fact.

        The hash covers the decision's position in the session as well as its answers. An
        earlier draft hashed the answers alone, and a smoke test over 200 identical decisions
        sampled 200 of them at a fraction of 0.2: with the position left out, two decisions
        that answered the same way are the same draw, so the sample picks *classes* of
        decision rather than decisions. Confident binary points return the same numbers again
        and again, which is exactly where that bias bites hardest. Reproducibility survives:
        replaying the same sequence reproduces the same sample.

        It samples decisions the model actually answered, at any confidence. Abstentions are
        already visible in the journal as abstentions and need no flag to be found.

        The shipped pattern this copies reviews everything below the threshold *and* a
        random fraction above it, as a standing audit of the threshold itself rather than of
        the model (AWS Augmented AI condition syntax). Ours is the second half; the first
        half is a journal query, because a sub-threshold decision is already recorded.
        """
        if self._t.audit <= 0.0 or decision.failed or not decision.answers:
            return False
        material = f"{decision.point}|{self._meter.decisions}|" + "|".join(
            f"{key}:{answer.choice}:{answer.score}:{answer.truth}:{answer.confidence}"
            for key, answer in sorted(decision.answers.items())
        )
        digest = hashlib.blake2b(material.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % 10_000 < self._t.audit * 10_000

    # --- decision points -------------------------------------------------------------

    async def route_task(
        self, task: str, *, requested: str | None = None, default: routing.Tier = "default"
    ) -> routing.Routing:
        """Which tier of model a delegated task deserves."""
        state, qs = routing.questions(task, brief=self._brief, profile=self._profile)
        decision = await self.decide("routing", state, qs)
        result = routing.decide(decision, self._t, default=default)
        self.record(decision, requested=requested, chosen=result.tier, reason=result.reason)
        return result

    async def route_search(
        self, query: str, *, cheap_available: bool = False
    ) -> search.SearchRoute:
        """Where a query goes. Remembers earlier queries to catch repeats."""
        repeat = is_repeat(query, self._queries)
        state, qs = search.questions(query, previous=self._queries, brief=self._brief)
        decision = await self.decide("search", state, qs)
        result = search.decide(
            decision, self._t, cheap_available=cheap_available, repeat_by_code=repeat
        )
        if result.route != "cut":
            self._queries = (*self._queries, query)
        self.record(decision, route=result.route, category=result.category, reason=result.reason)
        return result

    async def triage_page(
        self,
        *,
        purpose: str,
        title: str = "",
        url: str = "",
        text: str,
        allowed_kinds: Iterable[str] | None = None,
        denied_kinds: Iterable[str] | None = None,
    ) -> triage.Triage:
        """A page's place in the context. Provenance goes in `allowed_kinds`, not in `purpose`.

        **Not for a purpose with several parts.** Its relevance question asks whether the page
        addresses the whole purpose, and at the shipped cut it kept both supporting paragraphs
        in 19.7 % of 300 multi-part HotpotQA questions. Use `triage_part` there
        (`docs/results/2026-09-25-triage/`). The injection and source-kind answers of this
        call stay useful either way.

        **Not the way to keep documents out of a call.** On a fixed 20-document sequence,
        dropping at its relevance cut lost 4 answers in 10; `triage_many` over the documents'
        passages kept 9/9 at 79.5 % fewer input tokens (docs/results/2026-09-28-fixed-pages/).

        Stating "only official sources" inside the purpose asks the relevance question to
        carry a requirement it does not answer; the source-kind Choice in the same decision
        does, better calibrated and for free. Measured: `docs/results/2026-09-24-steerability`.
        """
        state, qs = triage.questions(purpose=purpose, title=title, url=url, text=text)
        decision = await self.decide("triage", state, qs)
        result = triage.decide(
            decision, self._t, allowed_kinds=allowed_kinds, denied_kinds=denied_kinds
        )
        self.record(
            decision,
            url=url,
            keep=result.keep,
            reason=result.reason,
            source_kind=result.source_kind,
        )
        return result

    async def triage_part(self, *, purpose: str, title: str = "", text: str) -> triage.Part:
        """Does this page hold any fact the answer to `purpose` would use, even one step of it?

        The triage for multi-part purposes. Confirmed on 300 HotpotQA questions nothing was
        chosen on: both supporting paragraphs kept in 93.3 % at 52 % of the text, against
        80.3 % for BM25 given more text and 19.7 % for `triage_page` at its shipped cut
        (`docs/results/2026-09-25-triage/`). One question, its own call: that is the shape
        that was measured. Pair it with `scan_content` or `triage_page` for injection.
        """
        state, qs = triage.contribution_questions(purpose=purpose, title=title, text=text)
        decision = await self.decide("triage_part", state, qs)
        result = triage.decide_part(decision, self._t)
        self.record(decision, keep=result.keep, reason=result.reason)
        return result

    async def check_done(
        self, *, task: str, record: str, cut: float = 0.5
    ) -> completion.Completion:
        """Did the agent do what `task` asked, as far as `record` shows? For a Stop hook.

        On 655 AgentDojo trajectories, against the benchmark's own environment check: 94 %
        right where trusting the agent is 52 %, AUC 0.98 (docs/results/2026-09-25-completion/).
        No data means no opinion: the harness keeps its own stop rule.
        """
        state, qs = completion.questions(task=task, record=record)
        decision = await self.decide("completion", state, qs)
        result = completion.decide(decision, cut=cut)
        self.record(decision, done=result.done, reason=result.reason)
        return result

    async def triage_pages(
        self, *, purpose: str, pages: Sequence[tuple[str, str]]
    ) -> list[tuple[bool, float | None]]:
        """Which of these pages hold a fact the answer needs, judged with the others in view.

        One call for the whole set, one probability per page. Confirmed on 300 HotpotQA
        questions nothing was chosen on: 98.3 % of supporting pages kept at 34 % of the text,
        where asking page by page kept 94.3 % at 53 % in ten calls
        (docs/results/2026-09-27-chunks/). Up to `chunks.PAGE_MAX` pages; later ones and
        unanswered ones are kept: in doubt, a page enters.
        """
        state, qs = chunks.context_questions(purpose=purpose, pages=pages)
        decision = await self.decide("triage_pages", state, qs)
        out: list[tuple[bool, float | None]] = []
        for index in range(len(pages)):
            p = decision.answer(chunks.page_id(index)).truth if index < chunks.PAGE_MAX else None
            out.append((p is None or p >= self._t.pages_in_context, p))
        self.record(decision, kept=sum(keep for keep, _ in out), pages=len(pages))
        return out

    async def triage_many(
        self, *, purpose: str, pages: Sequence[tuple[str, str]]
    ) -> list[tuple[bool, float | None]]:
        """`triage_pages` for any number of pages: a tournament of in-context calls.

        Up to `chunks.PAGE_MAX` it is one call. Past it, balanced groups at the lenient
        `pages_first_round` cut, then the survivors judged together at `pages_in_context`.
        Confirmed on 200 HotpotQA questions with 100 pages each: both supporting pages kept in
        96.5 % at 3.1 % of the text, in five calls (docs/results/2026-09-27-hierarchy/).
        The recommended way to keep documents out of an answering call: over each document's
        passages, 9/9 answers kept at 79.5 % fewer input tokens on a fixed sequence, one call
        (docs/results/2026-09-28-fixed-pages/). Unanswered pages are kept. The probability
        returned is the last one the page got.
        """

        async def judge(ids: Sequence[int]) -> list[float | None]:
            state, qs = chunks.context_questions(purpose=purpose, pages=[pages[i] for i in ids])
            decision = await self.decide("triage_pages", state, qs)
            self.record(decision, pages=len(ids))
            return [decision.answer(chunks.page_id(k)).truth for k in range(len(ids))]

        result = await hierarchy.tournament(
            len(pages),
            judge,
            size=chunks.PAGE_MAX,
            first_cut=self._t.pages_first_round,
            final_cut=self._t.pages_in_context,
        )
        return [(v.keep, v.last) for v in result.pages]

    async def select_sentences(
        self, *, purpose: str, title: str = "", sentences: Sequence[str], window: int = 0
    ) -> list[tuple[bool, float | None]]:
        """Which sentences of a page hold a fact the answer needs, each read in the page.

        Meant inside the pages `triage_pages` keeps: together they returned every supporting
        sentence in 90.3 % of 300 new questions at 22 % of the text. Sentences past
        `chunks.SENTENCE_MAX` and unanswered ones are kept. `window` also keeps every sentence
        within that many positions of a kept one; probabilities are returned as answered.
        """
        if window < 0:
            raise ValueError("window must be >= 0")
        state, qs = chunks.sentence_questions(purpose=purpose, title=title, sentences=sentences)
        decision = await self.decide("select_sentences", state, qs)
        out: list[tuple[bool, float | None]] = []
        for index in range(len(sentences)):
            key = chunks.sentence_id(index)
            p = decision.answer(key).truth if index < chunks.SENTENCE_MAX else None
            out.append((p is None or p >= self._t.sentences, p))
        if window:
            flags = [keep for keep, _ in out]
            out = [
                (any(flags[max(0, j - window) : j + window + 1]), p) for j, (_, p) in enumerate(out)
            ]
        self.record(decision, kept=sum(keep for keep, _ in out), sentences=len(sentences))
        return out

    async def select_passages(
        self, *, purpose: str, pages: Sequence[tuple[str, str]]
    ) -> list[list[tuple[bool, float | None]] | None]:
        """The passages of one long document the answer needs: paragraphs, then sentences.

        `triage_many` over the paragraphs; only those it keeps at or above
        `Thresholds.document_paragraphs` go to `select_sentences`, with a window of
        `Thresholds.document_window`. One entry per page: `None` for a paragraph not sent on,
        else one `(keep, probability)` per sentence of `text.split_sentences(page)`. Confirmed on
        219 new QASPER questions: every answer sentence in 87.2 % at 21.0 % of the text, and an
        answering model scored as well from it as from the whole paper
        (docs/results/2026-09-28-lateral-wholedocs/). For one long document, not short pages.
        """
        kept = await self.triage_many(purpose=purpose, pages=pages)
        gate = self._t.document_paragraphs

        async def sentences_of(title: str, body: str) -> list[tuple[bool, float | None]]:
            return await self.select_sentences(
                purpose=purpose,
                title=title,
                sentences=split_sentences(body),
                window=self._t.document_window,
            )

        jobs = [
            sentences_of(title, body) if keep and (p is None or p >= gate) else None
            for (title, body), (keep, p) in zip(pages, kept, strict=True)
        ]
        done = await asyncio.gather(*(job for job in jobs if job is not None))
        answers = iter(done)
        return [None if job is None else next(answers) for job in jobs]

    async def prune_context(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        arm: str = "sanchopanza",
        keep_recent: int = 6,
        small: int = 400,
    ) -> Any:
        """At compaction, which old tool results to stub. Returns a `context.compact.Plan`.

        Deterministic rules first (`context.rules`), then one in-context decision (point
        `context`) over the calls they leave, a tournament past `points.context.CALL_MAX`.
        Below `Thresholds.context_keep` a result is stubbed; unanswered ones are kept. Writes
        nothing: `context.compact.apply` does, archiving each stubbed text first. NOT measured
        yet on coding transcripts; `arm` runs the `rules`-only or the `fastjev` replica instead.
        """
        from .context import compact

        return await compact.plan(
            self, list(messages), arm=arm, keep_recent=keep_recent, small=small
        )

    async def triage_results(
        self, results: Sequence[Mapping[str, Any]], *, purpose: str
    ) -> list[dict[str, Any]]:
        """Filter and reorder search results: evidence first."""
        triaged = await asyncio.gather(
            *(
                self.triage_page(
                    purpose=purpose,
                    title=str(r.get("title", "")),
                    url=str(r.get("url", "")),
                    text=str(r.get("text", "")),
                )
                for r in results
            )
        )
        kept = [(tr, r) for tr, r in zip(triaged, results, strict=True) if tr.keep]
        kept.sort(key=lambda pair: (pair[0].evidence, pair[0].relevance), reverse=True)
        return [
            {**dict(r), "source_kind": tr.source_kind, "evidence": tr.evidence} for tr, r in kept
        ]

    async def select_tools(
        self,
        *,
        purpose: str,
        catalog: Sequence[Mapping[str, Any]],
        clues: str = "",
        always: Iterable[str] = (),
        honour_deferred: bool = True,
        warn_churn: bool = True,
    ) -> tools.Selection:
        """Which groups of a tool catalog the model's call should carry. Never empty.

        Large catalogs are asked in chunks, in parallel, and merged before the policy runs
        once over the whole catalog. `always` groups are pinned by code, not by the model,
        and groups a kept group `requires` are added in code after it.

        `honour_deferred=False` narrows even when the request defers its instructions; the
        probability is still returned on the selection. That is for a caller that can widen
        later once the deferred content is read (`sanchopanza.window.ToolWindow`), and wrong
        for one that selects once for the whole session.
        """
        groups = [dict(g) for g in catalog]
        if not groups:
            return tools.Selection((), (), "empty catalog", {})
        probs, deferred, decisions = await self.ask_groups(
            "tools",
            groups,
            lambda chunk: tools.questions(purpose=purpose, catalog=chunk, clues=clues),
        )
        selection = tools.select(
            probs,
            self._t,
            always=always,
            failed=all(d.failed for d in decisions),
            deferred=deferred if honour_deferred else None,
            requires=tools.requires_of(groups),
        )
        selection = replace(selection, deferred=deferred)
        if warn_churn:  # a ToolWindow opening a new conversation is not a session churning
            self._warn_if_the_catalog_churns(selection)
        for d in decisions:
            self.record(
                d, kept=len(selection.keep), dropped=len(selection.dropped), reason=selection.reason
            )
        return selection

    async def ask_groups(
        self,
        point: str,
        groups: Sequence[Mapping[str, Any]],
        build: Callable[
            [Sequence[Mapping[str, Any]]], tuple[Mapping[str, Any], dict[str, Question]]
        ],
    ) -> tuple[dict[str, float | None], float | None, list[Decision]]:
        """Ask one per-group question over a catalog, in parallel chunks, and merge.

        Returns the probability per group (None where the decider said nothing), the
        `deferred` probability if the questions carried it, and the raw decisions, which the
        caller journals with its own outcome.
        """
        chunks = [
            groups[i : i + tools.GROUPS_PER_CALL]
            for i in range(0, len(groups), tools.GROUPS_PER_CALL)
        ]
        decisions = list(await asyncio.gather(*(self.decide(point, *build(c)) for c in chunks)))
        probs: dict[str, float | None] = {}
        deferred: float | None = None
        for d, c in zip(decisions, chunks, strict=True):
            probs.update(tools.probabilities_of(d, c))
            chunk_deferred = tools.deferred_of(d)
            if chunk_deferred is not None:
                # Chunks each carry the question; the most worried chunk wins, because one
                # chunk seeing a deferral is enough for the request to be one.
                deferred = chunk_deferred if deferred is None else max(deferred, chunk_deferred)
        return probs, deferred, decisions

    def _warn_if_the_catalog_churns(self, selection: tools.Selection) -> None:
        """Say so, once, when a session narrows its tool catalog to a *different* set.

        This is the only place the package can notice the most expensive mistake it is able
        to cause. Tool definitions sit at the front of the prompt prefix, so changing them
        invalidates the tools, system and message caches together. Measured over 8 turns on
        claude-sonnet-5 (`benchmarks/cache/`): narrowing once is 43 % cheaper than not
        narrowing, alternating between two stable subsets is 14 % *dearer* than not
        narrowing, and a different subset each turn reads **zero** tokens from cache and
        costs 4.15x the run that decided once.

        A warning and not an error: some harnesses change the tool set through channels that
        do preserve the cache (a server-side tool search, or `tool_addition` / `tool_removal`
        blocks with `defer_loading`), and the squire cannot tell from here which one is in
        use. It can only tell that the selection moved, which is the thing worth knowing.
        """
        current = frozenset(selection.keep)
        if (
            self._last_selection is not None
            and current != self._last_selection
            and not self._churn_warned
        ):
            self._churn_warned = True
            self._journal.record(
                "warning",
                {
                    "message": "the tool selection changed within one session. If this is "
                    "written back into the `tools` array it invalidates the whole prompt "
                    "cache and costs more than the schemas it saves: select once per "
                    "session, or use a channel that appends instead of swapping. See "
                    "benchmarks/cache/results/summary.md.",
                    "previous": sorted(self._last_selection),
                    "now": sorted(current),
                },
            )
        self._last_selection = current

    async def verify_citation(
        self, *, claim: str, quote: str, source: str
    ) -> tuple[citation.Verdict, float]:
        """Literal presence in code; meaning in the decider; doubt to review."""
        found = quote_present(quote, source)
        if not found:
            decision = Decision("citation", {}, "code", "-")
            verdict, confidence = citation.decide(decision, self._t, quote_found=False)
            self.record(decision, verdict=verdict, confidence=confidence)
            return verdict, confidence
        state, qs = citation.questions(claim, source)
        decision = await self.decide("citation", state, qs)
        verdict, confidence = citation.decide(decision, self._t, quote_found=True)
        self.record(decision, verdict=verdict, confidence=confidence)
        return verdict, confidence

    async def evaluate_plan(
        self, lines: Sequence[Mapping[str, Any]], *, findings: str = ""
    ) -> list[dict[str, Any]]:
        """Score a plan's lines and, for small plans, add dependencies and parallel waves."""
        titles = [str(line.get("title", "")) for line in lines]

        async def one(index: int, line: Mapping[str, Any]) -> dict[str, Any]:
            others = [t for i, t in enumerate(titles) if i != index]
            state, qs = plan.line_questions(
                line, brief=self._brief, others=others, findings=findings
            )
            decision = await self.decide("plan_line", state, qs)
            ev = plan.decide_line(decision, self._t)
            result = {
                "title": titles[index],
                "priority": ev.priority,
                "parallel": ev.parallel,
                "saturated": ev.saturated,
                "tier": ev.tier,
                "source_kind": ev.source_kind,
                "reason": ev.reason,
            }
            self.record(decision, **result)
            return result

        evaluated = list(await asyncio.gather(*(one(i, line) for i, line in enumerate(lines))))
        if 2 <= len(lines) <= plan.MAX_LINES_FOR_DAG:
            edges, layers = await self.dependencies(
                [{**dict(line), "id": str(line.get("title", ""))} for line in lines]
            )
            depends: dict[str, list[str]] = {}
            for a, b in edges:
                depends.setdefault(b, []).append(a)
            wave_of = {n: i + 1 for i, layer in enumerate(layers) for n in layer}
            evaluated = [
                {
                    **e,
                    "depends_on": sorted(depends.get(e["title"], [])),
                    "wave": wave_of.get(e["title"], 1),
                    "parallel": e["title"] not in depends,
                }
                for e in evaluated
            ]
        return sorted(evaluated, key=lambda e: (e.get("wave", 1), -e["priority"]))

    async def dependency_pairs(self, lines: Sequence[Mapping[str, Any]]) -> dict[Edge, float]:
        """Ask the decider about every ordered pair. Raw probabilities; the DAG is built later."""
        ids = [str(line.get("id") or line.get("title", "")) for line in lines]
        by_id = {i: line for i, line in zip(ids, lines, strict=True)}

        async def pair(a: str, b: str) -> tuple[Edge, float]:
            state, qs = plan.dependency_questions(
                a_title=str(by_id[a].get("title", "")),
                a_goal=str(by_id[a].get("goal", "")),
                b_title=str(by_id[b].get("title", "")),
                b_goal=str(by_id[b].get("goal", "")),
            )
            decision = await self.decide("dependency", state, qs)
            p = decision.answer("b_needs_a").truth
            self.record(decision, a=a, b=b, probability=p)
            return (a, b), (p if p is not None else 0.0)

        pairs = await asyncio.gather(*(pair(a, b) for a in ids for b in ids if a != b))
        return dict(pairs)

    async def dependencies(
        self, lines: Sequence[Mapping[str, Any]]
    ) -> tuple[set[Edge], list[list[str]]]:
        """Clean DAG of a plan: pairs to the decider, cycles and transitives to code."""
        ids = [str(line.get("id") or line.get("title", "")) for line in lines]
        pairs = await self.dependency_pairs(lines)
        edges = build_dag(ids, pairs)
        layers = waves(ids, edges)
        self._journal.record(
            "decision",
            {
                "point": "dag",
                "provider": "code",
                "model": "-",
                "cost_usd": 0.0,
                "outcome": {"edges": sorted(edges), "waves": layers},
            },
        )
        return edges, layers

    async def review_report(self, task: str, result: str) -> review.Review | None:
        state, qs = review.questions(task, result)
        decision = await self.decide("review", state, qs)
        outcome = review.decide(decision, self._t)
        self.record(decision, message=outcome.message if outcome else None)
        return outcome

    async def scan_content(self, *, purpose: str, text: str, source: str = "") -> injection.Flag:
        """Detection over content that has already arrived. It cannot withhold anything.

        The prevention path is `triage_page`, inside a tool the agent called, where a page
        can still be kept out. This one exists for the other case - a built-in fetch whose
        result the harness will not let anything replace - and it buys three things that do
        not require the model to comply: the operator is warned, the event is journalled,
        and the passage is named as data in front of the model. `points.injection` states
        the difference; do not present this as a barrier.

        Two layers, as in `guard_command`: the keyword list runs first and for free, and when
        it fires the model is not called at all. Otherwise the text is scanned in overlapping
        windows and the highest probability wins, because a payload does not have to be near
        the top and truncating at one window is what made 7 of the AgentDojo cases invisible.
        `max_windows` bounds the cost of a very long document; what was and was not looked at
        goes into the journal rather than being silently dropped.
        """
        reason = injection.code_signal(text)
        if reason:
            decision = Decision("injection", {}, "code", "-")
            self.record(decision, source=source[:200], flagged=True, origin="code", reason=reason)
            return injection.decide(decision, self._t, source=source, code_reason=reason)

        every = injection.windows(text)
        slices = every[: self._t.max_windows]
        if not slices:
            # Nothing scanned: complete only if there was nothing to scan. With
            # `max_windows <= 0` a non-empty text used to come back clean AND complete.
            return injection.Flag(False, 0.0, complete=not every)
        step = max(injection.TEXT_LIMIT - injection.WINDOW_OVERLAP, 1)
        best: Decision | None = None
        best_p = -1.0
        judged: list[int] = []  # start offsets of the windows the model actually answered
        failed = 0
        for index, chunk in enumerate(slices):
            state, qs = injection.questions(purpose=purpose, text=chunk)
            decision = await self.decide("injection", state, qs)
            answer = decision.answer("injection")
            if decision.failed or answer.truth is None:
                # Until 2026-09-25 a failed window scored 0.0 and the scan came back clean
                # with the journal claiming full coverage. A window nobody judged is a gap.
                failed += 1
                best = best or decision
                continue
            judged.append(index * step)
            p = answer.truth
            if p > best_p:
                best_p, best = p, decision
            if p > self._t.injection:
                break  # one window is enough; the rest cannot clear it
        assert best is not None
        flag = injection.decide(best, self._t, source=source)
        scanned = injection.covered(len(text), judged)
        complete = flag.flagged or scanned >= len(text)
        flag = replace(flag, complete=complete)
        self.record(
            best,
            source=source[:200],
            flagged=flag.flagged,
            probability=flag.probability,
            origin=flag.origin,
            windows=len(slices),
            windows_total=len(every),
            windows_failed=failed,
            scanned_chars=scanned,
            total_chars=len(text),
            complete=complete,
        )
        return flag

    async def guard_command(
        self,
        command: str,
        *,
        environment: Mapping[str, Any] | None = None,
        profile: str = "sandbox",
    ) -> GuardResult:
        """Deny-list in code first; the decider can add a denial, never an approval.

        `profile="coding"` (Claude Code and Codex on a person's repository): the narrow list and
        the coding question, with `environment` from `guard.coding_environment`. The default
        `sandbox` is the research container the list and the question were written for."""
        coding = profile == "coding"
        why = guard.coding_denial(command) if coding else guard.code_denial(command)
        if why:
            decision = Decision("guard", {}, "code", "-")
            self.record(decision, command=command[:200], denied=True, origin="code", reason=why)
            return GuardResult(True, "code", why, 1.0)
        if coding:
            state, qs = guard.coding_questions(
                command, environment=environment or guard.coding_environment(".")
            )
        else:
            state, qs = guard.questions(command, environment=environment)
        decision = await self.decide("guard", state, qs)
        dangerous, p = guard.decide(decision, self._t)
        reason = f"the decision model flags it as dangerous ({p:.2f})" if dangerous else ""
        self.record(
            decision,
            command=command[:200],
            denied=dangerous,
            origin="decider" if dangerous else None,
            probability=p,
        )
        return GuardResult(dangerous, "decider" if dangerous else None, reason, p)

    async def same_entity(
        self, *, a: str, context_a: str = "", b: str, context_b: str = ""
    ) -> tuple[bool | None, float]:
        state, qs = entities.alignment_questions(a=a, context_a=context_a, b=b, context_b=context_b)
        decision = await self.decide("entity", state, qs)
        same, p = entities.decide_alignment(decision, self._t)
        self.record(decision, a=a[:120], b=b[:120], same=same, probability=p)
        return same, p

    async def relate_facts(self, *, fact_a: str, fact_b: str) -> tuple[str | None, float]:
        state, qs = entities.fact_questions(fact_a=fact_a, fact_b=fact_b)
        decision = await self.decide("facts", state, qs)
        relation, confidence = entities.decide_facts(decision, self._t)
        self.record(decision, relation=relation, confidence=confidence)
        return relation, confidence

    async def classify(
        self,
        *,
        field: str,
        text: str,
        options: Mapping[str, Any],
        context: str = "",
        add_other: bool = True,
    ) -> tuple[str | None, float, dict[str, float]]:
        state, qs = entities.classification_questions(
            field=field, text=text, options=options, context=context, add_other=add_other
        )
        decision = await self.decide("classify", state, qs)
        category, p, dist = entities.decide_classification(decision, self._t, options=options)
        self.record(decision, field=field, category=category, probability=p)
        return category, p, dist

    # --- fetch-heavy retrieval, memory and graph ------------------------------------

    async def triage_redundant(self, *, purpose: str, text: str, known: str) -> triage.Redundancy:
        """Does this page repeat what the agent already holds? Drops only on a confident yes.

        The lever the end-to-end A/B could not exercise, because its agent fetched one or
        two documents per task. It bites when a job gathers many sources about one event.
        """
        state, qs = triage.redundancy_questions(purpose=purpose, text=text, known=known)
        decision = await self.decide("redundant_page", state, qs)
        result = triage.decide_redundancy(decision, self._t)
        self.record(decision, drop=result.drop, reason=result.reason)
        return result

    async def remember(
        self,
        fact: str,
        *,
        source: str = "",
        ask_common: bool = False,
        specific_floor: float = 0.0,
        trust: Literal["trusted", "untrusted"] = "trusted",
    ) -> memory.Write:
        """Is this worth writing to long-term memory? Stores only on a confident yes.

        `ask_common=True` asks the fourth question and applies `memory.decide_write_common`:
        measured far better on standing instructions, with a floor trade documented there.

        `trust="untrusted"` for a fact taken from text the agent read (a page, a tool result,
        an email): memory is where an injected instruction outlives the conversation that
        carried it. The fact is scanned first; a flagged fact, or one the scan could not read
        entirely, is not stored and the memory decision is not asked. Review finding M2.
        """
        if trust == "untrusted":
            flag = await self.scan_content(
                purpose="a fact the agent is about to write to its long-term memory",
                text=fact,
                source="memory candidate",
            )
            if flag.flagged or not flag.complete:
                reason = (
                    f"untrusted fact carries instructions ({flag.probability:.2f})"
                    if flag.flagged
                    else "untrusted fact not fully scanned: not stored"
                )
                return memory.Write(False, reason, 0.0, 0.0, 0.0)
        state, qs = memory.write_questions(
            fact=fact, brief=self._brief, source=source, ask_common=ask_common
        )
        decision = await self.decide("memory_write", state, qs)
        result = (
            memory.decide_write_common(decision, self._t, specific_floor=specific_floor)
            if ask_common
            else memory.decide_write(decision, self._t)
        )
        self.record(decision, store=result.store, reason=result.reason)
        return result

    async def reconcile(
        self, *, new: str, stored: str, newer: bool | None = None
    ) -> memory.Reconciliation:
        """What to do with a candidate memory that touches a stored one.

        `newer` comes from the harness's timestamps, never from the decider: this model
        class reads dates as text, and replacing the wrong way round is a silent loss.
        Without it a real collision is flagged, not resolved.
        """
        state, qs = memory.collision_questions(new=new, stored=stored)
        decision = await self.decide("memory_collision", state, qs)
        result = memory.decide_collision(decision, self._t, newer=newer)
        self.record(decision, action=result.action, reason=result.reason)
        return result

    async def needs_recall(self, turn: str, *, topics: str = "") -> memory.Recall:
        """Does this turn need a memory lookup at all? Skips only on a confident no."""
        state, qs = memory.recall_questions(turn=turn, topics=topics)
        decision = await self.decide("recall", state, qs)
        result = memory.decide_recall(decision, self._t)
        self.record(decision, look=result.look, reason=result.reason)
        return result

    async def gate_extraction(
        self, *, chunk: str, looking_for: str, kinds: Sequence[str] = ()
    ) -> graph.Gate:
        """Is this chunk worth a generative extraction call? Skips only on a confident no."""
        state, qs = graph.gate_questions(chunk=chunk, looking_for=looking_for, kinds=kinds)
        decision = await self.decide("extract_gate", state, qs)
        result = graph.decide_gate(decision, self._t)
        self.record(decision, extract=result.extract, reason=result.reason)
        return result

    async def verify_edge(
        self,
        *,
        subject: str,
        relation: str,
        obj: str,
        text: str,
        trust: Literal["trusted", "untrusted"] = "trusted",
        direction_by_roles: bool = True,
    ) -> graph.EdgeCheck:
        """Does the text state this triple? Mentions in code, meaning in the decider.

        `direction_by_roles=False` asks the earlier `direction` wording; only a replay of a
        recording made with it needs that (`graph.edge_questions`).

        `trust="untrusted"` for text the agent fetched: an attacker who writes the page can
        write a sentence that states any edge, and the graph keeps it. A text that carries
        instructions, or that the scan could not read entirely, sends the edge to review
        instead of committing it. Review finding M3.
        """
        if trust == "untrusted":
            flag = await self.scan_content(
                purpose=f"evidence for the relation: {subject} {relation} {obj}",
                text=text,
                source="edge evidence",
            )
            if flag.flagged or not flag.complete:
                return graph.EdgeCheck("review", 0.0, 0.0, 0.0)
        found = mention_present(subject, text) and mention_present(obj, text)
        if not found:
            decision = Decision("edge", {}, "code", "-")
            result = graph.decide_edge(decision, self._t, mentions_found=False)
            self.record(decision, verdict=result.verdict, reason="a mention is not in the text")
            return result
        state, qs = graph.edge_questions(
            subject=subject,
            relation=relation,
            obj=obj,
            text=text,
            direction_by_roles=direction_by_roles,
        )
        decision = await self.decide("edge", state, qs)
        result = graph.decide_edge(decision, self._t, mentions_found=True)
        self.record(decision, verdict=result.verdict, stated=result.stated)
        return result

    async def check_loop(
        self, *, goal: str, done: str, pending: str = "", checks: Sequence[str] = ()
    ) -> loop.LoopAdvice:
        """Is the goal already met, or is this check a repeat? Advises; never denies."""
        state, qs = loop.questions(goal=goal, done=done, pending=pending, checks=checks)
        decision = await self.decide("loop", state, qs)
        result = loop.decide(decision, self._t)
        self.record(decision, message=result.message or None)
        return result
