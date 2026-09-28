"""Cut a long tool result on arrival to what the current task needs; archive the rest.

    result = await arrival.cut(squire, text, tool="Read", tool_input={...}, purpose=task)
    if result.text is not None:   # else pass the original through, `result.reason` says why
        ...

This is the multi-level tournament that was confirmed on documents, applied to a tool result
as it arrives, before it enters the conversation:

1. The result is split into blocks by its grain (`blocks.split`: paragraphs, code blocks, line
   groups of about `chunks.PAGE_LIMIT` characters).
2. `Squire.triage_many` judges every block with its siblings in view against `purpose` (the
   current task): one call up to 30 blocks, a tournament past it (96.5 % of evidence kept at
   3.1 % of the text on 100-page sets, `docs/results/2026-09-27-hierarchy/`).
3. In prose, a kept block the final round gave at least `Thresholds.document_paragraphs` (0.75)
   and with at least `MIN_SENTENCES` sentences goes to `Squire.select_sentences` with a window of
   `Thresholds.document_window` (2), the sentence stage of the rule confirmed on whole papers
   (`docs/results/2026-09-28-lateral-wholedocs/`). Code and logs are never cut below the block:
   a sentence splitter means nothing there.

One deliberate difference from `Squire.select_passages`, for retention: a block kept by the
tournament below the 0.75 gate is kept **whole** rather than dropped. The result is a superset of
that paper's arm W (93.2 % of answers whole, 39.7 % of the text), at more text than GW; the
archive makes the rest recoverable, and on a tool result a lost line costs a re-run.

Fail open, always: a decider that gave no answer, a cut that saves less than `min_saving`,
or anything unexpected returns `text=None` and the reason; the caller passes the original.
The decisions read redacted text (`redact.redact_secrets`, and the squire's own redactor);
the agent gets the real text of what is kept.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..redact import redact_secrets
from ..text import truncate
from . import blocks as blocks_mod
from .transcript import is_prompt, message_text

if TYPE_CHECKING:
    from ..squire import Squire

MIN_SENTENCES = 3
PURPOSE_LIMIT = 400  # chunks.context_questions truncates `purpose` here
HEADER = (
    "[sanchopanza cut this {tool} result on arrival to the parts that bear on the current "
    "task: {kept} of {total} chars kept, {omitted} omitted. Full text: {path} (Read it for "
    "anything omitted; line numbers after an omission are shifted, the markers give the "
    "original ones).]\n"
)


@dataclass(frozen=True, slots=True)
class Settings:
    threshold: int = 6_000  # results under this pass untouched
    error_threshold: int = 20_000  # a result that reads as a failure passes under this
    min_saving: float = 0.2  # a cut that saves less is not worth an altered result
    sentences: bool = True  # the sentence stage in prose blocks (3. above)


@dataclass(frozen=True, slots=True)
class Cut:
    """`text` is the agent-facing text without the header, or None: pass the original."""

    text: str | None
    reason: str
    report: Mapping[str, Any] = field(default_factory=dict)


# --- the purpose: what the agent is doing now ----------------------------------------------


def _call_summary(tool: str, tool_input: Mapping[str, Any]) -> str:
    for key in ("description", "prompt", "pattern", "query", "command", "file_path", "url"):
        value = tool_input.get(key)
        if value:
            return f"{tool} {key}={value}"
    return tool


def purpose_of(
    messages: Sequence[Mapping[str, Any]], tool: str, tool_input: Mapping[str, Any]
) -> str:
    """First real prompt, latest prompt, the agent's last stated intent, and this call.

    Each part has its share of the 400 characters the question shows, so a long first request
    cannot push the current step out of view.
    """
    prompts = [message_text(m) for m in messages if is_prompt(m)]
    intent = ""
    for message in reversed(messages):
        if message.get("role") == "assistant" and message_text(message):
            intent = message_text(message)
            break
    parts = []
    if prompts:
        parts.append(f"Task: {truncate(prompts[0], 130)}")
        if len(prompts) > 1 and prompts[-1] != prompts[0]:
            parts.append(f"Now asked: {truncate(prompts[-1], 110)}")
    if intent:
        parts.append(f"Agent's step: {truncate(intent, 90)}")
    parts.append(f"This call: {truncate(_call_summary(tool, tool_input), 60)}")
    return truncate("\n".join(parts), PURPOSE_LIMIT)


# --- the decision --------------------------------------------------------------------------


def _title(source: str, block: blocks_mod.Block, offset: int) -> str:
    a, b = block.first_line + offset, block.last_line + offset
    return f"{truncate(source, 80)} lines {a}-{b}"


def _looks_failed(text: str) -> bool:
    from .rules import FAILURE

    return bool(FAILURE.match(text))


def gate(text: str, settings: Settings) -> str | None:
    """Why a result passes untouched, or None when it goes to the decider. Pure."""
    if len(text) < settings.threshold:
        return f"under {settings.threshold} chars"
    if _looks_failed(text) and len(text) < settings.error_threshold:
        return f"reads as a failure, under {settings.error_threshold} chars"
    return None


async def _sentences(
    squire: Squire, purpose: str, title: str, text: str, block: blocks_mod.Block
) -> list[tuple[int, int]] | None:
    spans = blocks_mod.sentence_spans(text, block)
    if len(spans) < MIN_SENTENCES:
        return None
    sentences = [redact_secrets(text[a:b]) for a, b in spans]
    verdicts = await squire.select_sentences(
        purpose=purpose, title=title, sentences=sentences, window=squire.thresholds.document_window
    )
    kept = [span for span, (keep, _) in zip(spans, verdicts, strict=True) if keep]
    return kept if len(kept) < len(spans) else None


async def cut(
    squire: Squire,
    text: str,
    *,
    tool: str,
    tool_input: Mapping[str, Any] | None = None,
    purpose: str,
    settings: Settings | None = None,
    source: str = "",
    line_offset: int = 0,
) -> Cut:
    """Decide what of `text` the agent gets. Never raises on a decider failure."""
    settings = settings or Settings()
    tool_input = tool_input or {}
    passed = gate(text, settings)
    if passed:
        return Cut(None, passed)
    kind = blocks_mod.kind_of(tool, tool_input, text)
    found = blocks_mod.split(text, kind)
    base = {"kind": kind, "blocks": len(found), "chars": len(text)}
    if len(found) < 2:
        return Cut(None, "one block: nothing to choose between", base)
    label = source or _call_summary(tool, tool_input)
    pages = [(_title(label, b, line_offset), redact_secrets(b.of(text))) for b in found]
    verdicts = await squire.triage_many(purpose=purpose, pages=pages)
    answered = sum(p is not None for _, p in verdicts)
    report = {**base, "answered": answered, "kept_blocks": sum(k for k, _ in verdicts)}
    if answered == 0:
        # No probability at all is a failed or unreachable decider far more often than a real
        # answer: say so, instead of reading a refused call as a decision.
        return Cut(None, "no answer from the decider (failed or unreachable): passed whole", report)
    if report["kept_blocks"] == 0:
        # Nothing bears on the task by the decider's reading: more likely a purpose it could
        # not read than a result with nothing in it. In doubt, the agent gets it whole.
        return Cut(None, "the decider kept no block: passed whole", report)
    kept: list[bool | list[tuple[int, int]]] = [keep for keep, _ in verdicts]
    if settings.sentences and kind == "prose":
        gate_p = squire.thresholds.document_paragraphs
        jobs = {
            i: _sentences(squire, purpose, pages[i][0], text, found[i])
            for i, (keep, p) in enumerate(verdicts)
            if keep and p is not None and p >= gate_p
        }
        done = await asyncio.gather(*jobs.values())
        for i, spans in zip(jobs, done, strict=True):
            if spans is not None:
                kept[i] = spans
        report = {**report, "sentence_blocks": sum(s is not None for s in done)}
    out = blocks_mod.assemble(text, found, kept, line_offset=line_offset)
    saving = 1 - len(out) / len(text)
    report = {**report, "kept_chars": len(out), "saving": round(saving, 4)}
    if saving < settings.min_saving:
        return Cut(
            None, f"saves {saving:.0%}, under {settings.min_saving:.0%}: passed whole", report
        )
    omitted = sum(1 for k in kept if k is False)
    return Cut(out, f"kept {len(out)} of {len(text)} chars", {**report, "omitted": omitted})


def header(tool: str, kept: int, total: int, omitted: int, path: Any) -> str:
    return HEADER.format(tool=tool, kept=kept, total=total, omitted=omitted, path=path)
