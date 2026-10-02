"""The navigation loop: one stateless step at a time, with a fake browser and a scripted model.

Nothing here calls a model or opens a browser: the loop takes both as arguments, which is also
how the package stays free of any LLM client.
"""

from __future__ import annotations

import pytest

from sanchopanza.navigate import Action, Browser, navigate, parse_action, prompt_for

PAGE_ONE = """- Page URL: https://books.example/
- Page Title: All products
- Page Snapshot:
```yaml
- generic [active] [ref=e1]:
  - heading "Categories" [level=2] [ref=e2]
  - link "Travel" [ref=e3] [cursor=pointer]:
    - /url: /travel
  - link "Mystery" [ref=e4] [cursor=pointer]:
    - /url: /mystery
  - paragraph [ref=e5]: We love being scraped
```"""

PAGE_TWO = """- Page URL: https://books.example/travel
- Page Title: Travel
- Page Snapshot:
```yaml
- generic [active] [ref=e1]:
  - heading "Travel" [level=1] [ref=e2]
  - link "It's Only the Himalayas" [ref=e3] [cursor=pointer]:
    - /url: /himalayas
  - paragraph [ref=e4]: Price 45.17 GBP
```"""


class FakeBrowser:
    """Two pages and a click that moves between them; every call is recorded."""

    def __init__(self, pages: list[tuple[str, str, str]]) -> None:
        self.pages = pages
        self.at = 0
        self.acted: list[str] = []
        self.fail: str = ""

    async def snapshot(self) -> tuple[str, str, str]:
        return self.pages[self.at]

    async def act(self, action: Action) -> str:
        self.acted.append(action.line())
        if self.fail:
            return self.fail
        if action.kind == "click" and self.at + 1 < len(self.pages):
            self.at += 1
        return "ok"


def pages() -> list[tuple[str, str, str]]:
    return [
        (PAGE_ONE, "https://books.example/", "All products"),
        (PAGE_TWO, "https://books.example/travel", "Travel"),
    ]


def scripted(replies: list[str]) -> tuple[object, list[str]]:
    seen: list[str] = []

    async def actor(prompt: str) -> str:
        seen.append(prompt)
        return replies[min(len(seen) - 1, len(replies) - 1)]

    return actor, seen


def test_parse_action_reads_each_kind():
    clicked = '{"act": "click", "ref": "e3"}'
    assert parse_action(clicked) == Action("click", ref="e3", raw=clicked)
    filled = parse_action('{"act":"fill","ref":"e9","text":"boots"}')
    assert (filled.kind, filled.ref, filled.text) == ("fill", "e9", "boots")
    answered = parse_action('Here: {"act":"answer","answer":"45.17","quote":"Price 45.17 GBP"}')
    assert answered.kind == "answer"
    assert (answered.answer, answered.quote) == ("45.17", "Price 45.17 GBP")
    assert parse_action('{"act":"click","ref":"[ref=e12]"}').ref == "e12"


@pytest.mark.parametrize(
    "reply",
    ["no json here", "{not json}", '{"act": "teleport", "ref": "e3"}', '{"act":"click"}', ""],
)
def test_an_unusable_reply_is_not_guessed_at(reply):
    """A loop that repairs the model's reply measures the repair too."""
    assert parse_action(reply).kind == ""


@pytest.mark.asyncio
async def test_the_loop_clicks_then_answers_and_keeps_the_evidence():
    browser = FakeBrowser(pages())
    actor, seen = scripted(
        [
            '{"act":"click","ref":"e3"}',
            '{"act":"answer","answer":"45.17","quote":"Price 45.17 GBP"}',
        ]
    )
    out = await navigate("the price of the Himalayas book under Travel", browser=browser,
                         actor=actor, max_steps=5)  # fmt: skip
    assert (out.stopped, out.answer, out.quote) == ("answered", "45.17", "Price 45.17 GBP")
    assert out.url == "https://books.example/travel"
    assert browser.acted == ["click e3"]
    assert [s.index for s in out.steps] == [1, 2]
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_a_step_never_shows_the_pages_already_visited():
    """The point of the loop: a step's prompt holds what was done, not what was read."""
    browser = FakeBrowser(pages())
    actor, seen = scripted(['{"act":"click","ref":"e3"}', '{"act":"give_up","answer":"enough"}'])
    await navigate("the price under Travel", browser=browser, actor=actor, max_steps=5)
    assert "Mystery" not in seen[1], "the first page's elements are in the second step's prompt"
    assert "click e3" in seen[1], "what was done is in it"
    assert "It's Only the Himalayas" in seen[1]


@pytest.mark.asyncio
async def test_an_unparsed_reply_stops_the_loop_and_says_so():
    browser = FakeBrowser(pages())
    actor, _ = scripted(["I would click the Travel link."])
    out = await navigate("anything", browser=browser, actor=actor)
    assert out.stopped == "unparsed"
    assert "I would click" in out.quote
    assert browser.acted == []


@pytest.mark.asyncio
async def test_the_same_action_three_times_on_the_same_page_is_stuck():
    browser = FakeBrowser(pages())
    browser.fail = "error: element not found"
    actor, _ = scripted(['{"act":"click","ref":"e3"}'])
    out = await navigate("anything", browser=browser, actor=actor, max_steps=9)
    assert out.stopped == "stuck"
    assert len(out.steps) == 3
    assert out.steps[-1].note.startswith("the 3")


@pytest.mark.asyncio
async def test_the_steps_run_out():
    browser = FakeBrowser([pages()[1]])
    actor, _ = scripted(['{"act":"click","ref":"e3"}', '{"act":"click","ref":"e4"}'])
    out = await navigate("anything", browser=browser, actor=actor, max_steps=2)
    assert out.stopped == "max_steps"
    assert not out.answered


@pytest.mark.asyncio
async def test_a_browser_that_dies_is_not_a_measurement_of_the_loop():
    class Dead:
        async def snapshot(self):
            raise RuntimeError("browser closed")

        async def act(self, action):  # pragma: no cover - never reached
            return ""

    actor, _ = scripted(['{"act":"click","ref":"e3"}'])
    out = await navigate("anything", browser=Dead(), actor=actor)
    assert out.stopped == "browser"
    assert "browser closed" in out.quote


@pytest.mark.asyncio
async def test_the_big_model_is_asked_only_below_the_cut():
    """With no decider every element's probability is None, which counts as unsure."""
    browser = FakeBrowser(pages())
    small, small_seen = scripted(['{"act":"give_up","answer":"small"}'])
    big, big_seen = scripted(['{"act":"give_up","answer":"big"}'])
    out = await navigate("anything", browser=browser, actor=small, big_actor=big,
                         escalate_below=0.8)  # fmt: skip
    assert out.answer == "big"
    assert (len(small_seen), len(big_seen)) == (0, 1)
    assert out.steps[0].escalated is True

    browser = FakeBrowser(pages())
    small, small_seen = scripted(['{"act":"give_up","answer":"small"}'])
    big, big_seen = scripted(['{"act":"give_up","answer":"big"}'])
    out = await navigate("anything", browser=browser, actor=small, big_actor=big,
                         escalate_below=None)  # fmt: skip
    assert out.answer == "small"
    assert (len(small_seen), len(big_seen)) == (1, 0)


def test_the_prompt_says_the_step_and_what_was_done():
    text = prompt_for("find the price", done=["click e3"], url="https://x/", title="T",
                      lean="page text", elements_shown="- link [ref=e3]", step=2,
                      max_steps=12)  # fmt: skip
    assert "Goal: find the price" in text
    assert "step 2 of at most 12" in text
    assert "  1. click e3" in text
    assert "page text" in text and "- link [ref=e3]" in text
    assert '"act": "click"' in text


def test_a_browser_satisfies_the_protocol():
    assert isinstance(FakeBrowser(pages()), Browser)


def test_a_key_press_is_an_action_and_needs_a_key():
    pressed = parse_action('{"act":"press","key":"Enter"}')
    assert (pressed.kind, pressed.text, pressed.line()) == ("press", "Enter", "press Enter")
    assert parse_action('{"act":"press","text":"Enter"}').text == "Enter"
    assert parse_action('{"act":"press"}').kind == ""
