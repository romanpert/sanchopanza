"""How much of each text a decision point shows the decider, as one value.

Every default is the cut the published measurements ran with, and none changes here. They were
set against Jev's default window (64k tokens a request, 32k a question), and several measured
failures were these cuts, not the model: the memory gate saw 75 % of its evidence inside 900
characters, AgentDojo payloads past character 2,000 were invisible to a single window. With the
long-context header (`JevDecider(long_context=True)`, up to 262k tokens) an experiment arm can
raise them: `Squire(decider, limits=Limits(page_chars=20_000))`. The question builders in
`points` take the same numbers as keyword arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from .points import chunks, completion, injection, memory, triage
from .points import context as context_point


@dataclass(frozen=True, slots=True)
class Limits:
    page_chars: int = chunks.PAGE_LIMIT  # a page of an in-context set (triage_pages, memory)
    pages_per_call: int = chunks.PAGE_MAX  # pages in one in-context call; a tournament past it
    triage_chars: int = triage.TEXT_LIMIT  # the page text of triage_page / triage_part
    completion_record_chars: int = completion.RECORD_LIMIT  # check_done's record
    history_chars: int = context_point.HISTORY_LIMIT  # the compaction guard's history
    result_chars: int = context_point.RESULT_LIMIT  # a candidate result in it, head and tail
    memory_record_chars: int = memory.RECORD_LIMIT  # an earlier record at memory_recall
    injection_window_chars: int = injection.TEXT_LIMIT  # one window of scan_content

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field.name} must be a positive number of characters")
        if self.injection_window_chars <= injection.WINDOW_OVERLAP:
            raise ValueError(
                f"injection_window_chars must be over the {injection.WINDOW_OVERLAP} "
                "characters consecutive windows share"
            )
