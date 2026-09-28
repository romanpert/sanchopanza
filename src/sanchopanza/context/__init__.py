"""Context pruning at compaction: keep every message, stub the tool results nothing needs.

    from sanchopanza.context import compact, messages_from_claude_code
    messages = messages_from_claude_code(transcript_path)
    plan = await squire.prune_context(messages)
    pruned = compact.apply(messages, plan, archive_dir)

`transcript` reads conversations and pairs tool calls with their results, `rules` decides
what code can decide for free, and `compact` plans, applies and reports. `compact` is loaded
on first use: it imports the decision points, which import `transcript` from here.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .rules import Verdict, triage_rules
from .transcript import Call, calls, messages_from_claude_code

__all__ = [
    "Call",
    "Verdict",
    "calls",
    "compact",
    "messages_from_claude_code",
    "triage_rules",
]


def __getattr__(name: str) -> Any:
    if name == "compact":
        return import_module(".compact", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
