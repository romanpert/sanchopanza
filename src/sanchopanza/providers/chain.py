"""Composition: several deciders behind one contract.

- `FallbackDecider([a, b, c])`: ask `a`; if it is unavailable or answers nothing, ask `b`,
  and so on. Answers from different providers are merged question by question, so a local
  model can cover two questions and a hosted one the rest.
- `RoutedDecider({"guard": local, "citation": jev}, default=jev)`: one provider per
  decision point. The way to keep a sensitive point on-premise and the rest hosted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..contract import Decider, DeciderUnavailable, Decision, Question, State


class FallbackDecider:
    def __init__(self, deciders: Sequence[Decider]) -> None:
        if not deciders:
            raise ValueError("a fallback chain needs at least one decider")
        self._deciders = list(deciders)
        self.name = "fallback(" + ">".join(d.name for d in deciders) + ")"
        # One link that reads attachments is enough: the text-only ones refuse, the
        # chain records their error and the capable one still answers.
        self.accepts_attachments = any(getattr(d, "accepts_attachments", False) for d in deciders)

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        merged: dict = {}
        providers: list[str] = []
        tokens = cost = latency = 0
        model = "-"
        errors: list[str] = []
        for decider in self._deciders:
            pending = {k: q for k, q in questions.items() if k not in merged}
            if not pending:
                break
            try:
                decision = await decider.decide(point, state, pending)
            except DeciderUnavailable as error:
                errors.append(f"{decider.name}: {error}")
                continue
            if decision.answers:
                merged = {**merged, **decision.answers}
                providers.append(decision.provider)
                model = decision.model if model == "-" else model
            tokens += decision.input_tokens
            cost += decision.cost_usd
            latency += decision.latency_ms
        if not merged and errors and len(errors) == len(self._deciders):
            raise DeciderUnavailable("; ".join(errors))
        return Decision(
            point=point,
            answers=merged,
            provider="+".join(providers) or self.name,
            model=model,
            input_tokens=tokens,
            cost_usd=cost,
            latency_ms=latency,
        )


class RoutedDecider:
    def __init__(self, by_point: Mapping[str, Decider], default: Decider) -> None:
        self._by_point = dict(by_point)
        self._default = default
        self.name = "routed"

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        return await self._by_point.get(point, self._default).decide(point, state, questions)


class CascadeDecider:
    """Ask the cheap decider first; ask the expensive one only about what it was unsure of.

    The shape Claude Code's auto mode uses for tool permissions (a cheap first stage, the
    expensive stage only on what the first flags), with one difference that is the point
    of this package: the first stage here reports a calibrated confidence, so "unsure" is
    a number and not a guess. Measured on 212 recorded judgments with `claude-opus-5` as the
    expensive stage: every threshold from 0.2 to 0.5 matched or beat Opus alone at 10-20 %
    of its cost (`docs/results/2026-09-25-cascade/`).

    - `tau` is the confidence below which a question escalates: one number, or one per
      question kind (`{"truth": 0.4, "choice": 0.5}`). There is no default on purpose: it
      has to be derived on labelled cases of the decision it guards, like every threshold.
    - Only the questions that fell short escalate, in one call; confident answers stand.
    - An empty answer always escalates. An expensive stage that fails leaves the cheap
      answers in place: the cascade never answers less than its first stage would have.
    - `provider` reads `cheap>expensive` when anything escalated, so the journal says which
      decisions paid for the second stage.
    """

    def __init__(
        self,
        cheap: Decider,
        expensive: Decider,
        *,
        tau: float | Mapping[str, float],
    ) -> None:
        self._cheap = cheap
        self._expensive = expensive
        self._tau = tau
        self.name = f"cascade({cheap.name}>{expensive.name})"
        self.accepts_attachments = getattr(cheap, "accepts_attachments", False) and getattr(
            expensive, "accepts_attachments", False
        )

    def _threshold(self, question: Question) -> float:
        if isinstance(self._tau, Mapping):
            return float(self._tau.get(question.kind, 1.01))
        return float(self._tau)

    def unsure(self, decision: Decision, questions: Mapping[str, Question]) -> list[str]:
        """The questions the cheap stage did not answer with enough confidence."""
        return [
            key
            for key, question in questions.items()
            if decision.answer(key).empty
            or decision.answer(key).confidence < self._threshold(question)
        ]

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        try:
            first = await self._cheap.decide(point, state, questions)
        except DeciderUnavailable:
            first = Decision(point, {}, self._cheap.name, "-", error="cheap stage unavailable")
        pending = self.unsure(first, questions)
        if not pending:
            return first
        try:
            second = await self._expensive.decide(point, state, {k: questions[k] for k in pending})
        except DeciderUnavailable:
            if first.failed:
                raise
            return first
        answers = {**first.answers, **{k: a for k, a in second.answers.items() if k in pending}}
        return Decision(
            point=point,
            answers=answers,
            provider=f"{first.provider}>{second.provider}",
            model=first.model if first.model != "-" else second.model,
            input_tokens=first.input_tokens + second.input_tokens,
            cost_usd=first.cost_usd + second.cost_usd,
            latency_ms=first.latency_ms + second.latency_ms,
            error=None if answers else (first.error or second.error),
        )
