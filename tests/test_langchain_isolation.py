"""Conversations served by one `ToolSelectMiddleware` do not leak into each other.

Two findings of the 2026-09-25 review, each pinned by a test that failed before the fix:

- Without `key_of`, a conversation was keyed by its first human message and its catalog, so
  two users whose conversations open with the same words ("hi") shared one window, and the
  groups one of them widened it to reached the other.
- One `Squire`, one budget meter, served every conversation in the process: exhausting it in
  one conversation made every later conversation fall open to the full catalog.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any

from sanchopanza import Decision
from sanchopanza.harness.langchain import ToolSelectMiddleware
from sanchopanza.squire import Squire

from .helpers import squire, yes


@dataclass(frozen=True)
class Tool:
    name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Human:
    content: Any
    type: str = "human"


@dataclass(frozen=True)
class AI:
    content: str
    type: str = "ai"


@dataclass(frozen=True)
class Request:
    tools: list[Any]
    messages: list[Any]
    thread: str | None = None

    def override(self, **changes: Any) -> Request:
        return replace(self, **changes)


TOOLS = [
    Tool("aemps_buscar", "Search Spanish medicines"),
    Tool("aemps_ficha", "Fetch an SmPC"),
    Tool("chembl_search", "Bioactivity search"),
    Tool("web_search", "General web search", {"server": "web"}),
]
HI = [Human("hi")]
WIDENED = [*HI, AI("..."), Human("and its bioactivity?")]


class _ByPurpose:
    """`chembl` for anything about bioactivity, `aemps` otherwise. Counts calls."""

    name = "by-purpose"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point, state, questions):  # noqa: ANN001
        self.calls += 1
        want = "chembl" if "bioactivity" in state["purpose"] else "aemps"
        answers = {
            k: yes(0.9 if state["catalog"][int(k.split("_")[1])]["name"] == want else 0.02)
            for k in questions
            if k.startswith("needed_")
        }
        return Decision(point, answers, self.name, "t")


def _run(middleware: ToolSelectMiddleware, request: Request) -> list[str]:
    seen: list[Any] = []

    async def handler(r: Any) -> str:
        seen.append(r)
        return "ok"

    asyncio.run(middleware.awrap_model_call(request, handler))
    return [t.name for t in seen[0].tools]


def _thread(request: Any) -> str | None:
    return getattr(request, "thread", None)


# --- windows ---------------------------------------------------------------------------


def test_without_key_of_two_users_opening_with_hi_do_not_share_a_window():
    sq, _ = squire(_ByPurpose())
    mw = ToolSelectMiddleware(sq)
    assert _run(mw, Request(TOOLS, HI)) == ["aemps_buscar", "aemps_ficha"]  # user A, turn one
    assert "chembl_search" in _run(mw, Request(TOOLS, WIDENED))  # user A widens
    # user B opens with the same word: only what "hi" alone asks for, nothing of A's
    assert _run(mw, Request(TOOLS, HI)) == ["aemps_buscar", "aemps_ficha"]


def test_without_key_of_nothing_is_kept_between_requests():
    decider = _ByPurpose()
    sq, _ = squire(decider)
    mw = ToolSelectMiddleware(sq)
    for _ in range(3):
        _run(mw, Request(TOOLS, HI))
    assert decider.calls == 3  # the documented price of the safe default


def test_a_request_whose_key_is_none_is_not_pooled_with_others():
    sq, _ = squire(_ByPurpose())
    mw = ToolSelectMiddleware(sq, key_of=_thread)
    _run(mw, Request(TOOLS, WIDENED, thread=None))
    assert _run(mw, Request(TOOLS, HI, thread=None)) == ["aemps_buscar", "aemps_ficha"]


def test_with_key_of_each_thread_keeps_its_own_growing_window():
    decider = _ByPurpose()
    sq, _ = squire(decider)
    mw = ToolSelectMiddleware(sq, key_of=_thread)
    _run(mw, Request(TOOLS, HI, thread="a"))
    _run(mw, Request(TOOLS, HI, thread="b"))
    assert _run(mw, Request(TOOLS, WIDENED, thread="a")) == [
        "aemps_buscar",
        "aemps_ficha",
        "chembl_search",
    ]
    assert _run(mw, Request(TOOLS, HI, thread="b")) == ["aemps_buscar", "aemps_ficha"]
    calls = decider.calls
    _run(mw, Request(TOOLS, WIDENED, thread="a"))  # same turn again: no new decision
    assert decider.calls == calls


# --- budgets ---------------------------------------------------------------------------


def test_one_conversation_exhausting_its_budget_leaves_the_others_narrowed():
    sq, journal = squire(_ByPurpose(), max_decisions=1)
    mw = ToolSelectMiddleware(sq, key_of=_thread)
    assert _run(mw, Request(TOOLS, HI, thread="a")) == ["aemps_buscar", "aemps_ficha"]
    # a second conversation still gets a decision of its own, not the full catalog
    assert _run(mw, Request(TOOLS, HI, thread="b")) == ["aemps_buscar", "aemps_ficha"]
    assert len(journal.decisions()) >= 2  # both went to the journal the caller holds
    assert sq.meter.decisions == 0  # the template squire is never charged


def test_without_key_of_every_request_has_its_own_budget():
    sq, _ = squire(_ByPurpose(), max_decisions=1)
    mw = ToolSelectMiddleware(sq)
    for i in range(3):  # three conversations; one shared meter ran dry after the first
        assert _run(mw, Request(TOOLS, [Human(f"hi {i}")])) == ["aemps_buscar", "aemps_ficha"]


def test_a_factory_is_called_once_per_conversation():
    decider = _ByPurpose()
    made: list[Squire] = []

    def factory() -> Squire:
        made.append(squire(decider)[0])
        return made[-1]

    mw = ToolSelectMiddleware(factory, key_of=_thread)
    _run(mw, Request(TOOLS, HI, thread="a"))
    _run(mw, Request(TOOLS, WIDENED, thread="a"))
    _run(mw, Request(TOOLS, HI, thread="b"))
    assert len(made) == 2
    assert all(s.meter.decisions >= 1 for s in made)
