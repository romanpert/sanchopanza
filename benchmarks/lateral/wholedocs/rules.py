"""The candidate rule for whole documents: gate the paragraphs harder, widen the sentences.

On QASPER the shipped two stages (`triage_many` at 0.40, then `select_sentences` at 0.28) keep
31.5 % of a paper and every answer sentence in 83.1 % of questions. What the sentence stage
drops is the second or third sentence of a multi-sentence answer. Two changes, each doing one
job:

- **Window.** A sentence is kept when any sentence within `window` positions of it, in the same
  paragraph, clears the sentence cut. This is the recall half: the neighbours of a kept
  sentence travel with it.
- **Paragraph gate.** Only paragraphs whose final tournament probability clears `gate` go to
  the sentence stage at all. This is the compression half, and it saves the sentence calls of
  every paragraph under the gate.

A probability the decider did not return counts as a pass, as everywhere in the package: in
doubt, text enters. This module is pure; the proposed library change is described in
`docs/results/2026-09-28-lateral-wholedocs/README.md`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    gate: float  # final tournament probability a paragraph needs to reach the sentence stage
    cut: float  # sentence probability that makes a sentence (and its window) kept
    window: int  # neighbours kept on each side of a kept sentence, inside its paragraph

    def label(self) -> str:
        return f"gate {self.gate:.2f}, cut {self.cut:.2f}, window {self.window}"


SHIPPED = Rule(gate=0.40, cut=0.28, window=0)


def passes(p: float | None, cut: float) -> bool:
    return p is None or p >= cut


def widen(mask: Sequence[bool], window: int) -> list[bool]:
    """Keep every position within `window` of a kept one."""
    if window < 0:
        raise ValueError("window must be >= 0")
    n = len(mask)
    return [any(mask[max(0, j - window) : min(n, j + window + 1)]) for j in range(n)]


def paragraph_mask(
    kept: bool, final: float | None, sentences: Sequence[float | None], rule: Rule
) -> list[bool]:
    """Which sentences of one paragraph are kept under `rule`."""
    if not kept or not passes(final, rule.gate):
        return [False] * len(sentences)
    return widen([passes(p, rule.cut) for p in sentences], rule.window)


def document_mask(
    keep: Sequence[bool],
    finals: Sequence[float | None],
    sentences: Sequence[Sequence[float | None]],
    rule: Rule,
) -> list[list[bool]]:
    return [
        paragraph_mask(k, f, ps, rule) for k, f, ps in zip(keep, finals, sentences, strict=True)
    ]


def needs_sentence_call(kept: bool, final: float | None, rule: Rule) -> bool:
    """Only paragraphs past the gate are asked about their sentences."""
    return kept and passes(final, rule.gate)
