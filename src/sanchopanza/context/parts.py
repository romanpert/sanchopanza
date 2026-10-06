"""The structural guard split into parts, each within Claude Code's inline limit for a hook.

Claude Code keeps a hook's `additionalContext` inline only up to 10,000 characters; past that the
model sees a 2,000-character preview and a file path (`structural.INLINE_CHARS`). The limit is
per hook command: read in the 2.1.287 binary on 2026-10-06, each command's context goes through
the persist step on its own (`Pde(..., {threshold: 1e4})` per hook), the `SessionStart` contexts
are collected in one list with no aggregate cap, and the list reaches the model as one message,
`SessionStart hook additional context: ` and the parts joined by a newline. The hooks of one
event run at once and their contexts are collected as each finishes (`Promise.race`), so the
order of the parts is not guaranteed.

So the measured budget (`structural.STRUCT_CHARS`, 44,000 characters) is split over several
`SessionStart` commands (`sanchopanza guard-hook --part i`), one part each:

- Results go in the structural keep's order (`structural.order`), each whole into the first
  part with room (`structural.pack`): part 1 gets the results that matter most, so a part lost
  costs the least. A result is never cut between parts; one larger than a part leaves a pointer
  when it can be had again, and is lost otherwise, as it would be over the budget.
- Part 1 holds what the single block holds besides results: the requests, the work so far, the
  outputs the harness cut, the pointers, and the closing line. The others hold results only.
- Every part names itself on its first line ("part i of N") and says where the rest is, so the
  model can read them in any order. A single part is today's block, word for word.

Pure: the hook (`harness.guard_hook`) keeps the parts between `PreCompact` and `SessionStart`.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import guard, structural
from .guard import Guard
from .transcript import Call, calls


def default_parts(
    struct_chars: int = structural.STRUCT_CHARS, inline_chars: int = structural.INLINE_CHARS
) -> int:
    """How many `SessionStart` commands carry `struct_chars` of results at `inline_chars` each:
    one per `inline_chars` of results, and one more because part 1 spends about half its room on
    the requests, the trail and the pointers (6 at the defaults). 1 when there is no cap."""
    if inline_chars <= 0:
        return 1
    return 1 + math.ceil(max(struct_chars, 1) / inline_chars)


PARTS = default_parts()


def header(part: int, of: int) -> str:
    """The first line of part `part` of `of`. One part is the single block's header."""
    if of <= 1:
        return guard.HEADER
    if part == 1:
        rest = "Part 2 holds" if of == 2 else f"Parts 2 to {of} hold"
        return (
            f"[sanchopanza guard, part 1 of {of}: recorded before the compaction, kept verbatim. "
            f"{rest} more whole tool output and may come before or after this one; this part "
            "holds the requests, the work so far and what was left out]"
        )
    return (
        f"[sanchopanza guard, part {part} of {of}: more tool output recorded before the "
        f"compaction, kept verbatim; part 1 of {of} holds the requests, the work so far and what "
        "was left out]"
    )


def _results_overhead(parts: int) -> int:
    """Characters a results-only part takes besides its results, at the widest numbering."""
    widest = max(len(header(i, parts)) for i in range(2, parts + 1))
    return widest + len(guard.RESULTS_HEADING) + len(guard.CLOSING) + 2


@dataclass(frozen=True, slots=True)
class Split:
    """The parts in order (part 1 first), and what they carry as one guard (for the log and the
    summariser's note). No parts when there is nothing to add."""

    texts: tuple[str, ...]
    guard: Guard


def _first(base: Guard, of: int) -> str:
    text = guard.block(base, header(1, of))
    if text or of <= 1:
        return text
    return f"{header(1, of)}\n{guard.CLOSING}"  # results only, all of them in later parts


def split_calls(
    history: Sequence[Call],
    requests: Sequence[str],
    *,
    since: int = 0,
    budget: int = structural.STRUCT_CHARS,
    pointer_chars: int = structural.POINTER_CHARS,
    inline_chars: int = structural.INLINE_CHARS,
    parts: int = PARTS,
    web: bool = False,
) -> Split:
    """At most `parts` parts, each within `inline_chars`, holding up to `budget` characters of
    whole results between them. One part (or no cap) is `structural.build_from_calls`' block.
    Raises ValueError if a part would go over the cap (the hook then gives the rule's block)."""
    if parts <= 1 or inline_chars <= 0:
        single = structural.build_from_calls(
            history, requests, since=since, budget=budget, pointer_chars=pointer_chars,
            inline_chars=inline_chars, web=web,
        )  # fmt: skip
        text = guard.block(single)
        return Split((text,) if text else (), single)
    base = Guard(
        facts=(),
        requests=tuple(requests),
        trail=guard.trail_of(history),
        candidates=0,
        chooser="struct",
        clipped=guard.clipped_of(history, web=web),
        kind="results",
    )
    widening = len(header(1, parts)) - len(guard.HEADER)
    first_room = max(0, structural.room_for_results(base, pointer_chars, inline_chars) - widening)
    rest_room = max(0, inline_chars - _results_overhead(parts))
    ranked, superseded = structural.order(history, since=since, web=web)
    bins, pointers = structural.pack(
        history, ranked, (first_room, *[rest_room] * (parts - 1)), budget=budget,
        pointer_chars=pointer_chars, web=web,
    )  # fmt: skip
    first = dataclasses.replace(base, facts=structural.facts_of(history, bins[0]),
                                pointers=pointers,
                                candidates=len(ranked) + len(superseded))  # fmt: skip
    rest = [b for b in bins[1:] if b]
    whole = dataclasses.replace(first, facts=tuple(
        f for b in bins for f in structural.facts_of(history, b)))  # fmt: skip
    if whole.empty:
        return Split((), whole)
    of = 1 + len(rest)
    lead = _first(first, of)
    if structural.width(lead) > inline_chars:  # requests and trail alone overflow, as there
        first = dataclasses.replace(first, pointers=())
        whole = dataclasses.replace(whole, pointers=())
        lead = _first(first, of)
    texts = [lead] + [
        guard.block(dataclasses.replace(base, facts=structural.facts_of(history, b), requests=(),
                                        trail=(), clipped=()), header(i, of))
        for i, b in enumerate(rest, start=2)
    ]  # fmt: skip
    over = [i for i, text in enumerate(texts, start=1) if structural.width(text) > inline_chars]
    if over:
        raise ValueError(f"part {over[0]} of {of} is over {inline_chars} characters")
    return Split(tuple(texts), whole)


def split(
    messages: Sequence[Mapping[str, Any]],
    *,
    since: int = 0,
    facts_chars: int = structural.STRUCT_CHARS,
    requests_chars: int = guard.REQUESTS_CHARS,
    pointer_chars: int = structural.POINTER_CHARS,
    inline_chars: int = structural.INLINE_CHARS,
    parts: int = PARTS,
    web: bool = False,
) -> Split:
    """`split_calls` for a transcript (`history_from_claude_code`'s messages and boundary)."""
    return split_calls(
        calls(messages),
        guard.requests_of(messages, requests_chars),
        since=since,
        budget=facts_chars,
        pointer_chars=pointer_chars,
        inline_chars=inline_chars,
        parts=parts,
        web=web,
    )
