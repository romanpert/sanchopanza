"""The LangChain middleware narrows the tools of a request and never breaks the call."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any

from sanchopanza.harness.langchain import (
    ToolSelectMiddleware,
    catalog_of,
    default_group_of,
    last_human_text,
)
from sanchopanza.providers import FixedDecider, NullDecider

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

    def override(self, **changes: Any) -> Request:
        return replace(self, **changes)


TOOLS = [
    Tool("aemps_buscar", "Search Spanish medicines"),
    Tool("aemps_ficha", "Fetch an SmPC"),
    Tool("chembl_search", "Bioactivity search"),
    Tool("web_search", "General web search", {"server": "web"}),
]
MESSAGES = [AI("hola"), Human("¿interacción entre Sintrom e ibuprofeno?")]


def _handler_capturing(seen: list[Any]):
    async def handler(request: Any) -> str:
        seen.append(request)
        return "ok"

    return handler


def _run(middleware: ToolSelectMiddleware, request: Request) -> Request:
    seen: list[Any] = []
    asyncio.run(middleware.awrap_model_call(request, _handler_capturing(seen)))
    return seen[0]


def test_groups_come_from_metadata_server_then_name_prefix():
    assert default_group_of(Tool("web_search", metadata={"server": "web"})) == "web"
    assert default_group_of(Tool("aemps_buscar")) == "aemps"
    assert default_group_of(Tool("bare")) == "bare"
    catalog, groups = catalog_of(TOOLS, default_group_of)
    assert [g["name"] for g in catalog] == ["aemps", "chembl", "web"]
    assert catalog[0]["about"].startswith("2 tools (aemps_buscar, aemps_ficha)")
    assert [t.name for t in groups["aemps"]] == ["aemps_buscar", "aemps_ficha"]


def test_the_purpose_is_the_last_human_message_even_as_content_blocks():
    assert last_human_text(MESSAGES) == "¿interacción entre Sintrom e ibuprofeno?"
    blocks = [Human([{"type": "text", "text": "dosis"}, {"type": "text", "text": "pediátrica"}])]
    assert last_human_text(blocks) == "dosis pediátrica"
    assert last_human_text([AI("solo asistente")]) == ""


def test_the_request_goes_on_with_only_the_needed_groups_and_the_pinned_one():
    # catalog order is aemps, chembl, web -> needed_0, needed_1, needed_2
    decider = FixedDecider({"needed_0": yes(0.9), "needed_1": yes(0.05), "needed_2": yes(0.1)})
    sq, _ = squire(decider)
    seen = _run(ToolSelectMiddleware(sq, always={"web"}), Request(TOOLS, MESSAGES))
    assert [t.name for t in seen.tools] == ["aemps_buscar", "aemps_ficha", "web_search"]
    assert seen.messages == MESSAGES and decider.calls == 1


def test_nothing_changes_when_there_is_nothing_to_decide():
    decider = FixedDecider({"needed_0": yes(0.9), "needed_1": yes(0.0)})
    sq, _ = squire(decider)
    mw = ToolSelectMiddleware(sq)
    no_tools = Request([], MESSAGES)
    assert _run(mw, no_tools) is no_tools
    one_group = Request(TOOLS[:2], MESSAGES)
    assert _run(mw, one_group) is one_group
    no_human = Request(TOOLS, [AI("x")])
    assert _run(mw, no_human) is no_human
    unnamed = Request([*TOOLS, Tool("")], MESSAGES)
    assert _run(mw, unnamed) is unnamed
    assert decider.calls == 0


def test_a_silent_decider_leaves_the_full_catalog():
    sq, _ = squire(NullDecider())
    request = Request(TOOLS, MESSAGES)
    assert _run(ToolSelectMiddleware(sq), request) is request


def test_a_request_without_override_is_passed_through():
    @dataclass(frozen=True)
    class Bare:
        tools: list[Any]
        messages: list[Any]

    sq, _ = squire(FixedDecider({"needed_0": yes(0.9), "needed_1": yes(0.0), "needed_2": yes(0.0)}))
    request = Bare(TOOLS, MESSAGES)
    assert _run(ToolSelectMiddleware(sq), request) is request


def test_the_sync_path_narrows_outside_an_event_loop():
    sq, _ = squire(FixedDecider({"needed_0": yes(0.9), "needed_1": yes(0.0), "needed_2": yes(0.0)}))
    seen: list[Any] = []
    ToolSelectMiddleware(sq).wrap_model_call(Request(TOOLS, MESSAGES), lambda r: seen.append(r))
    assert [t.name for t in seen[0].tools] == ["aemps_buscar", "aemps_ficha"]


# Windows persist per `key_of` only; without it nothing is kept between requests
# (tests/test_langchain_isolation.py). These tests drive a single conversation.
ONE_CONVERSATION = lambda request: "one"  # noqa: E731


class _ByPurpose:
    """Needs `aemps` for the first question and `chembl` for the second; counts calls."""

    name = "by-purpose"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point, state, questions):  # noqa: ANN001
        from sanchopanza import Decision

        self.calls += 1
        want = "chembl" if "bioactividad" in state["purpose"] else "aemps"
        answers = {
            k: yes(0.9 if state["catalog"][int(k.split("_")[1])]["name"] == want else 0.02)
            for k in questions
            if k.startswith("needed_")
        }
        return Decision(point, answers, self.name, "t")


def test_a_new_turn_widens_the_tools_and_never_drops_what_the_last_turn_had():
    # Until 2026-09-25 each call re-selected: turn two would have carried chembl WITHOUT
    # aemps, rewriting the tools array to a different set - the 4.15x churn pattern.
    decider = _ByPurpose()
    sq, _ = squire(decider)
    mw = ToolSelectMiddleware(sq, key_of=ONE_CONVERSATION)
    first = _run(mw, Request(TOOLS, MESSAGES))
    assert [t.name for t in first.tools] == ["aemps_buscar", "aemps_ficha"]
    turn_two = [*MESSAGES, AI("..."), Human("¿y su bioactividad?")]
    second = _run(mw, Request(TOOLS, turn_two))
    assert [t.name for t in second.tools] == ["aemps_buscar", "aemps_ficha", "chembl_search"]


def test_calls_within_one_turn_pay_for_no_new_decision():
    decider = _ByPurpose()
    sq, _ = squire(decider)
    mw = ToolSelectMiddleware(sq, key_of=ONE_CONVERSATION)
    for _ in range(4):  # the agent loop calling the model again after each tool result
        _run(mw, Request(TOOLS, MESSAGES))
    assert decider.calls == 1


def test_grow_false_keeps_the_first_selection_for_the_whole_conversation():
    sq, _ = squire(_ByPurpose())
    mw = ToolSelectMiddleware(sq, grow=False, key_of=ONE_CONVERSATION)
    _run(mw, Request(TOOLS, MESSAGES))
    turn_two = [*MESSAGES, AI("..."), Human("¿y su bioactividad?")]
    assert [t.name for t in _run(mw, Request(TOOLS, turn_two)).tools] == [
        "aemps_buscar",
        "aemps_ficha",
    ]


def test_a_second_conversation_under_a_shared_key_still_widens_on_its_own_turns():
    sq, _ = squire(_ByPurpose())
    mw = ToolSelectMiddleware(sq, key_of=ONE_CONVERSATION)  # two users, one key
    long = [*MESSAGES, AI("."), Human("otra"), AI("."), Human("y otra más")]
    _run(mw, Request(TOOLS, long))  # conversation A: three human turns under this key
    b_turn_two = [*MESSAGES, AI("..."), Human("¿y su bioactividad?")]
    names = [t.name for t in _run(mw, Request(TOOLS, b_turn_two)).tools]
    assert "chembl_search" in names


def test_callers_can_key_conversations_by_thread():
    sq, _ = squire(_ByPurpose())
    mw = ToolSelectMiddleware(sq, key_of=lambda request: getattr(request, "thread", None))

    @dataclass(frozen=True)
    class Threaded(Request):
        thread: str = ""

    _run(mw, Threaded(TOOLS, MESSAGES, thread="a"))
    _run(mw, Threaded(TOOLS, MESSAGES, thread="b"))
    assert len(mw._windows) == 2  # noqa: SLF001
