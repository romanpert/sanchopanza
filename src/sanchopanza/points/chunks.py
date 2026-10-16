"""Return only what contributes: triage below the page, and triage with the other pages in view.

`triage.contribution_questions` keeps or drops a whole page. Two shapes go further, registered
by hash in `docs/results/2026-09-27-chunks/prereg.md` before they were measured:

- `sentence_questions`: one call per page, one Truth per sentence of it, over the same state.
  The page stays whole in the state, so each sentence is read in its context, and only the
  sentences that contribute go back to the agent.
- `context_questions`: one call per candidate set, one Truth per page. Unlike the Choice of
  `triage.set_questions`, which measured badly because its mass concentrates on one page, each
  page gets its own probability, while the model still reads every other page.

Both reuse the contribution criteria of `triage.CONTRIBUTES` unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..catalog import tag
from ..contract import Question, Truth
from ..text import match_window, truncate
from .triage import CONTRIBUTES

SENTENCE_MAX = 40
SENTENCE_LIMIT = 600
PAGE_LIMIT = 900
PAGE_MAX = 30
EXCERPTS = ("head", "window")  # how a page past its limit is shown (`text.match_window`)


def sentence_id(index: int) -> str:
    return f"S{index + 1}"


def page_id(index: int) -> str:
    return f"P{index + 1:02d}"


def _about(label: str, where: str) -> Truth:
    return Truth(
        f"Does {label} in `{where}` contain at least one fact that an answer to `purpose` "
        "would use, even if it answers only one part of `purpose` or only one step toward "
        f"the answer? Read the rest of `{where}` as context.",
        criteria=CONTRIBUTES.criteria,
    )


def sentence_questions(
    *, purpose: str, title: str, sentences: Sequence[str]
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    sentences = list(sentences)[:SENTENCE_MAX]
    body = "\n".join(
        f"{sentence_id(i)}| {truncate(s, SENTENCE_LIMIT)}" for i, s in enumerate(sentences)
    )
    state = {"purpose": truncate(purpose, 400), "title": truncate(title, 200), "sentences": body}
    qs: dict[str, Question] = {
        sentence_id(i): _about(f"sentence {sentence_id(i)}", "sentences")
        for i in range(len(sentences))
    }
    return state, tag("select_sentences", qs)


def context_questions(
    *,
    purpose: str,
    pages: Sequence[tuple[str, str]],
    page_limit: int | None = None,
    page_max: int | None = None,
    excerpt: str = "head",
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """One Truth per page, every page in view. `page_limit` and `page_max` default to
    `PAGE_LIMIT` and `PAGE_MAX`, the measured cuts (`limits.Limits`). `excerpt="head"`, the
    measured default, shows a long page's first `page_limit` characters; `"window"` (opt-in,
    roadmap C6) shows `text.match_window`: the same head unless the page's best match to
    `purpose` lies past it."""
    if excerpt not in EXCERPTS:
        raise ValueError(f"excerpt must be one of {EXCERPTS}, not {excerpt!r}")
    pages = list(pages)[: PAGE_MAX if page_max is None else page_max]
    limit = PAGE_LIMIT if page_limit is None else page_limit

    def view(x: str) -> str:
        return truncate(x, limit) if excerpt == "head" else match_window(x, purpose, limit)

    body = "\n".join(
        f"{page_id(i)}| {truncate(t, 120)}: {view(x)}" for i, (t, x) in enumerate(pages)
    )
    state = {"purpose": truncate(purpose, 400), "pages": body}
    qs: dict[str, Question] = {
        page_id(i): _about(f"page {page_id(i)}", "pages") for i in range(len(pages))
    }
    return state, tag("triage_pages", qs)
