"""Sancho: a calibrated, non-generative decision layer for LLM agent harnesses.

The knight thinks; the squire reads. A System One decision model (TypeSafe's Jev, a local
classifier, an LLM forced into a schema) takes the procedural decisions of an agent loop
(which model, which search, which page, which citation, which command) through the
harness's hooks and tools, with calibrated probabilities, asymmetric thresholds, fail-open
defaults and a journal entry for every decision.

    from sanchopanza import Squire, Thresholds
    from sanchopanza.providers import create

    squire = Squire(create("jev"), thresholds=Thresholds())
    tier = await squire.route_task("List the rulings that mention defamation since 2020")
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .answers import choice, labelled, score, truth
    from .budget import Meter
    from .contract import (
        Answer,
        Choice,
        Decider,
        DeciderUnavailable,
        Decision,
        Question,
        Score,
        State,
        Truth,
    )
    from .journal import JsonlJournal, MemoryJournal, NullJournal
    from .media import Attachment, attachments_in, image, without_attachments
    from .policy import Thresholds
    from .squire import GuardResult, Squire
    from .window import Change, ToolWindow

__version__ = "0.3.0"

# Resolved on first use (PEP 562). The Claude Code hook is a process per event, and loading
# the squire, asyncio and the provider scan for an event that needs no decision was most of
# its start-up (docs/adapters.md). `from sanchopanza import Squire` works as before.
_LAZY = {
    **dict.fromkeys(("choice", "labelled", "score", "truth"), "answers"),
    "Meter": "budget",
    **dict.fromkeys(
        (
            "Answer",
            "Choice",
            "Decider",
            "DeciderUnavailable",
            "Decision",
            "Question",
            "Score",
            "State",
            "Truth",
        ),
        "contract",
    ),
    **dict.fromkeys(("JsonlJournal", "MemoryJournal", "NullJournal"), "journal"),
    **dict.fromkeys(("Attachment", "attachments_in", "image", "without_attachments"), "media"),
    "Thresholds": "policy",
    **dict.fromkeys(("GuardResult", "Squire"), "squire"),
    **dict.fromkeys(("Change", "ToolWindow"), "window"),
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))


__all__ = [
    "Answer",
    "Attachment",
    "Change",
    "Choice",
    "Decider",
    "DeciderUnavailable",
    "Decision",
    "GuardResult",
    "JsonlJournal",
    "MemoryJournal",
    "Meter",
    "NullJournal",
    "Question",
    "Score",
    "Squire",
    "State",
    "Thresholds",
    "ToolWindow",
    "Truth",
    "__version__",
    "attachments_in",
    "choice",
    "image",
    "labelled",
    "score",
    "truth",
    "without_attachments",
]
