"""What to keep of command output the conversation is about to lose: the questions.

Written for the compaction guard (`context.keep`) after its first decider questions were read
against their recordings (docs/results/2026-09-29-context-guard/prereg-prompt-recall.md,
amendment 5). Three faults of the reused page questions (`chunks`), each fixed here:

- **The request never reached the model.** `chunks` puts the question inside `purpose` and cuts
  it to 400 characters; the guard's 301-character preamble left about 95 characters of the
  person's request, so "the limit the diagnostic run complained about" was never read. Here the
  requests are a field of their own (`REQUESTS_LIMIT`), and the judgment is in the
  instructions, where it belongs.
- **Criteria from another domain.** `triage.CONTRIBUTES` is about pages answering a question
  (founders, rulings). Command output is kept for another reason: the value exists only there.
  The levels below describe that, with examples from domains none of the measured tasks use.
- **A yes or no cannot rank inside a budget.** When 400 characters must be chosen, what matters
  is the order among the lines kept. A Score of four levels, each a situation, gives a position;
  Indagis measured the same fix on long documents (approved paragraphs ordered by a four-level
  score, commit 5519f8a there).

Pure: builds states and questions, reads answers. The calls are in `context.keep`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..contract import Decision, Question, Score
from ..text import truncate

REQUESTS_LIMIT = 2_400
NOTES_LIMIT = 1_500
BLOCK_LIMIT = 900
LINE_LIMIT = 300
BLOCKS_PER_CALL = 12
LINES_PER_CALL = 30
TOP = 3.0  # the highest level: scores run from 0 to TOP

LEVELS: tuple[Mapping[str, Any], ...] = (
    {
        "what": "Nothing the remaining work needs: a banner, a progress or status line, a "
        "header, a separator, or one record among many printed in the same shape that the "
        "requests do not single out",
        "examples": [
            "Collecting packages ... done",
            "row 118 of 400: item=K-2291 qty=4",
            "==== 36 checks ====",
        ],
    },
    {
        "what": "Background only: about the same work as the requests, but no exact value "
        "they would use, or a value anyone could get again by reading a file",
        "examples": [
            "Loaded config from settings/app.toml",
            "3 warnings (deprecated option 'verbose')",
        ],
    },
    {
        "what": "A specific value the remaining work might use, though the requests do not "
        "point to it: a count, a version, a path created, a measured number",
        "examples": [
            "wrote 1,284 rows to exports/2026-09.csv",
            "resolved lodash@4.17.21",
        ],
    },
    {
        "what": "An exact value the requests point to, however they phrase it, and that exists "
        "only in this output: an identifier or key issued once, a limit or threshold a "
        "check reported, the code, name or expected value of a failure",
        "examples": [
            "migration applied, handle mig_7QK2-hollow",
            "quota exceeded: max 250 per hour (ref Q-418)",
            '{"status": "failed", "step": "schema-lint", "want": "v3"}',
        ],
    },
)

WHY = (
    "The conversation is about to be compacted and this command output will be lost; the "
    "command cannot be run again. Judge it against the work described in `requests`"
)


def block_id(index: int) -> str:
    return f"B{index + 1:02d}"


def line_id(index: int) -> str:
    return f"L{index + 1}"


def _base(requests: str, notes: str) -> dict[str, str]:
    state = {"requests": truncate(requests, REQUESTS_LIMIT)}
    if notes.strip():
        state = {**state, "notes": truncate(notes, NOTES_LIMIT)}
    return state


def block_questions(
    *, requests: str, blocks: Sequence[tuple[str, str]], notes: str = ""
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """One Score per block of output (`blocks` is [(command, text)]), all in view together."""
    blocks = list(blocks)[:BLOCKS_PER_CALL]
    body = "\n\n".join(
        f"{block_id(i)}| {truncate(c, 160)}\n{truncate(t, BLOCK_LIMIT)}"
        for i, (c, t) in enumerate(blocks)
    )
    where = " and `notes`" if notes.strip() else ""
    qs: dict[str, Question] = {
        block_id(i): Score(
            f"{WHY}{where}. How much of what block {block_id(i)} in `outputs` holds must be "
            "kept? Score its most important line.",
            LEVELS,
        )
        for i in range(len(blocks))
    }
    return {**_base(requests, notes), "outputs": body}, qs


def line_questions(
    *, requests: str, command: str, lines: Sequence[str], notes: str = ""
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """One Score per line of one block, each line read inside its block."""
    lines = list(lines)[:LINES_PER_CALL]
    body = "\n".join(f"{line_id(i)}| {truncate(x, LINE_LIMIT)}" for i, x in enumerate(lines))
    where = " and `notes`" if notes.strip() else ""
    qs: dict[str, Question] = {
        line_id(i): Score(
            f"{WHY}{where}. How much must line {line_id(i)} of `output` be kept? Read the "
            "other lines as context.",
            LEVELS,
        )
        for i in range(len(lines))
    }
    state = {**_base(requests, notes), "command": truncate(command, 160), "output": body}
    return state, qs


def scores_of(decision: Decision, count: int, key: Any) -> list[float | None]:
    """The score of each of `count` items, None where nothing usable came back."""
    return [decision.answer(key(i)).score if not decision.failed else None for i in range(count)]
