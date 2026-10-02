"""The loop guard as a hook: it advises above the threshold, and says nothing the rest of the time.

No model and no money: the decider is a fixed one, the transcript is written here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sanchopanza import answers
from sanchopanza.harness import loop_hook
from sanchopanza.policy import Thresholds
from sanchopanza.providers.fixed import BrokenDecider, FixedDecider
from sanchopanza.squire import Squire

GOAL = "Open the shop and report the item total, the tax and the total at checkout."


def _transcript(
    tmp_path: Path, *, calls: int, narration: str, results: list[str] | None = None
) -> Path:
    """A Claude Code transcript with `calls` paired tool calls and the agent's own prose.
    `results` gives each call's result text, oldest first; the rest are "ok"."""
    path = tmp_path / "sess.jsonl"
    lines = [{"type": "user", "message": {"role": "user", "content": GOAL}}]
    texts = list(results or [])
    texts = ["ok"] * (calls - len(texts)) + texts
    for i in range(calls):
        use = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": narration if i == calls - 1 else f"step {i}"},
                    {
                        "type": "tool_use",
                        "id": f"t{i}",
                        "name": "mcp__playwright__browser_click",
                        "input": {"target": "e54", "element": "Remove"},
                    },
                ],
            },
        }
        result = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": texts[i]}],
            },
        }
        lines += [use, result]
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return path


def _event(transcript: Path, session: str = "s1") -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "mcp__playwright__browser_click",
        "tool_input": {"target": "e54", "element": "Remove"},
        "transcript_path": str(transcript),
        "session_id": session,
    }


def _squire(goal_met: float, repeats: float) -> Squire:
    decider = FixedDecider(
        {"goal_met": answers.truth(goal_met), "repeats_check": answers.truth(repeats)}
    )
    return Squire(decider, thresholds=Thresholds(max_usd=1.0, max_decisions=50))


def _context(output: dict) -> str:
    return (output.get("hookSpecificOutput") or {}).get("additionalContext", "")


@pytest.mark.asyncio
async def test_it_says_the_goal_is_already_met(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=6, narration="Item total 9.99, tax 0.80, total 10.79")
    out = await loop_hook.post_tool_use(_event(transcript), _squire(0.97, 0.02))
    assert "established already" in _context(out)
    assert "0.97" in _context(out)


@pytest.mark.asyncio
async def test_it_says_the_check_is_a_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=6, narration="Clicking Remove once more")
    out = await loop_hook.post_tool_use(_event(transcript), _squire(0.05, 0.96))
    assert "already run" in _context(out)


@pytest.mark.asyncio
async def test_it_stays_quiet_below_the_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=6, narration="Still looking for the cart")
    assert await loop_hook.post_tool_use(_event(transcript), _squire(0.4, 0.4)) == {}


@pytest.mark.asyncio
async def test_it_asks_nothing_in_the_first_few_calls(tmp_path, monkeypatch):
    """Nothing can be a repeat of nothing, so an early session is not even asked about."""
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=2, narration="Opened the page")
    squire = _squire(0.99, 0.99)
    assert await loop_hook.post_tool_use(_event(transcript), squire) == {}
    assert squire.meter.decisions == 0


@pytest.mark.asyncio
async def test_a_decider_that_fails_leaves_the_session_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=6, narration="Item total 9.99")
    squire = Squire(BrokenDecider(), thresholds=Thresholds(max_usd=1.0, max_decisions=50))
    assert await loop_hook.post_tool_use(_event(transcript), squire) == {}


@pytest.mark.asyncio
async def test_no_transcript_means_no_question(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    squire = _squire(0.99, 0.99)
    event = {**_event(tmp_path / "nowhere.jsonl")}
    assert await loop_hook.post_tool_use(event, squire) == {}
    assert squire.meter.decisions == 0


@pytest.mark.asyncio
async def test_the_session_ceiling_silences_it(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    monkeypatch.setenv("SANCHOPANZA_SESSION_MAX_USD", "0.0001")
    transcript = _transcript(tmp_path, calls=6, narration="Item total 9.99")
    first = await loop_hook.post_tool_use(_event(transcript), _squire(0.97, 0.02))
    assert "established already" in _context(first)
    second = await loop_hook.post_tool_use(_event(transcript), _squire(0.97, 0.02))
    assert second == {}, "the ledger carries the spend between hook processes"


def test_what_a_call_was_in_a_few_words():
    assert loop_hook.short_input("browser_navigate", {"url": "https://x/y"}) == "https://x/y"
    assert loop_hook.short_input("browser_click", {"target": "e12", "element": "Login"}) == "e12"
    fields = {"fields": [{"name": "First Name", "target": "e1"}, {"name": "Zip", "target": "e2"}]}
    assert loop_hook.short_input("browser_fill_form", fields) == "First Name, Zip"
    assert loop_hook.short_input("browser_snapshot", {}) == ""


def test_what_the_agent_says_it_has_is_what_is_judged(tmp_path):
    """`done` is the agent's prose, not the tool results: a snapshot is 50,000 characters."""
    transcript = _transcript(tmp_path, calls=3, narration="Item total 9.99, tax 0.80")
    from sanchopanza.context.transcript import messages_from_claude_code

    messages = messages_from_claude_code(str(transcript))
    text = loop_hook.established(messages)
    assert "Item total 9.99, tax 0.80" in text
    assert "ok" not in text.split("\n")[-1] or "step" in text
    assert len(text) < 2000


SNAPSHOT_RESULT = """### Page
- Page URL: https://shop.example/checkout-step-two.html
- Page Title: Swag Labs
### Snapshot
```yaml
- generic [ref=e1]:
  - heading "Checkout: Overview" [level=2] [ref=e2]
  - generic [ref=e3]: "Item total: $9.99"
  - generic [ref=e4]: "Tax: $0.80"
  - generic [ref=e5]: "Total: $10.79"
  - link "Twitter" [ref=e9]:
    - /url: https://twitter.com/saucelabs
  - button "Finish" [ref=e6] [cursor=pointer]
```"""


def test_what_the_page_says_is_part_of_what_the_agent_has():
    """The fix of 2026-10-02: narration alone held no findings, so `goal_met` saw none."""
    facts = loop_hook.facts_seen(SNAPSHOT_RESULT, GOAL)
    assert "Item total: $9.99" in facts
    assert "Total: $10.79" in facts
    assert "/url:" not in facts, "a url is not a finding"
    assert len(facts) <= loop_hook.FACTS_LIMIT + 8


FIXTURES = Path(__file__).with_name("fixtures_loop")  # real results, B2 smoke, 2026-10-02


def test_a_find_result_gives_the_lines_that_say_something_however_deep():
    """Ten levels of `generic [ref=...]:` before the totals; the first fix kept the levels."""
    facts = loop_hook.facts_seen((FIXTURES / "find_item_total.txt").read_text("utf-8"), GOAL)
    assert "Item total: $9.99" in facts
    assert "Tax: $0.80" in facts and "Total: $10.79" in facts
    assert "[ref=" not in facts and "generic" not in facts


def test_a_screenshot_has_nothing_the_guard_can_read():
    """Playwright's code and an image path are not the page: the decision is recorded blind."""
    assert loop_hook.facts_seen((FIXTURES / "screenshot.txt").read_text("utf-8"), GOAL) == ""


def test_a_click_result_gives_where_the_agent_is_and_nothing_else():
    """Playwright MCP 0.0.83 saves the snapshot of an action to a file: only the URL is left."""
    facts = loop_hook.facts_seen((FIXTURES / "click_finish.txt").read_text("utf-8"), GOAL)
    assert facts.splitlines() == [
        "Page URL: https://www.saucedemo.com/checkout-step-two.html",
        "Page Title: Swag Labs",
    ]


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ('- generic [ref=e276]: "Item total: $55.97"', "Item total: $55.97"),
        ('  - button "Finish" [ref=e255] [cursor=pointer]', "button Finish"),
        ('- heading "Checkout: Overview" [level=2] [ref=e2]', "heading Checkout: Overview"),
        ('- textbox "First Name" [ref=e198]: Ada', "textbox First Name Ada"),
        ("- text: We love being scraped!", "We love being scraped!"),
        ("- generic [ref=e217]:", ""),
        ("- /url: index.html", ""),
        ("await page.locator('x').click();", ""),
        ("- Console: 8 errors, 0 warnings", ""),
        ("The total is 10.79 dollars", "The total is 10.79 dollars"),
    ],
)
def test_one_line_as_what_it_says(line, said):
    assert loop_hook.page_line(line) == said


def test_over_budget_the_lines_about_the_goal_stay_in_page_order():
    filler = [f'- generic [ref=e{i}]: "Footer link number {i} about careers"' for i in range(40)]
    lines = [*filler[:20], '- generic [ref=e900]: "Item total: $9.99"', *filler[20:],
             '- generic [ref=e901]: "Total: $10.79"']  # fmt: skip
    facts = loop_hook.facts_seen("\n".join(lines), GOAL, budget=200)
    kept = facts.splitlines()
    assert "Item total: $9.99" in kept and "Total: $10.79" in kept
    assert kept.index("Item total: $9.99") < kept.index("Total: $10.79")
    assert len(facts) <= 200


def test_a_result_that_is_not_a_snapshot_is_just_shortened():
    assert loop_hook.facts_seen("The total is 10.79 dollars", GOAL) == "The total is 10.79 dollars"
    assert loop_hook.facts_seen("", GOAL) == ""
    long = loop_hook.facts_seen("x" * 5000, GOAL)
    # `truncate` marks the cut with " [...]", which it adds past the limit it was given.
    assert "[...]" in long and len(long) <= loop_hook.FACTS_LIMIT + 8


@pytest.mark.parametrize(
    "response",
    [
        SNAPSHOT_RESULT,
        {"content": [{"type": "text", "text": SNAPSHOT_RESULT}]},
        [{"type": "text", "text": SNAPSHOT_RESULT}],
        {"stdout": SNAPSHOT_RESULT},
    ],
)
def test_the_result_is_found_whatever_shape_the_tool_returns(response):
    assert "Item total" in loop_hook.result_text({"tool_response": response})


def test_no_result_leaves_only_the_narration(tmp_path):
    from sanchopanza.context.transcript import messages_from_claude_code

    transcript = _transcript(tmp_path, calls=3, narration="Opened the overview")
    messages = messages_from_claude_code(str(transcript))
    assert loop_hook.established(messages) == loop_hook.narration(messages)
    with_page = loop_hook.established(messages, SNAPSHOT_RESULT, GOAL)
    assert "On the page now:" in with_page and "Opened the overview" in with_page


MISS = "### Error\nError: \"button[data-test='continue']\" does not match any elements."


def _error_event(transcript: Path, result: str = MISS) -> dict:
    """A call the transcript does not hold yet, the same identical failure as before it."""
    return {
        **_event(transcript),
        "tool_use_id": "t-new",
        "tool_response": [{"type": "text", "text": result}],
    }


@pytest.mark.asyncio
async def test_two_failed_browser_actions_in_a_row_get_one_note(tmp_path, monkeypatch):
    """The 37-turn session: guessed selectors failing, and no snapshot ever taken. The two
    failures here carry the same message, which a text-only dedupe used to count as one."""
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=5, narration="Trying Continue", results=[MISS])
    out = await loop_hook.post_tool_use(_error_event(transcript), _squire(0.05, 0.05))
    text = _context(out)
    assert "last 2 browser actions failed" in text
    assert "browser_snapshot" in text
    assert "does not match any elements" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(("before", "speaks"), [(0, False), (2, False), (3, True), (4, False)])
async def test_the_error_note_is_said_at_two_and_at_four_only(
    tmp_path, monkeypatch, before, speaks
):
    """Not on every failure: a note repeated on each turn is a cost, not advice."""
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=6, narration="again", results=[MISS] * before)
    out = await loop_hook.post_tool_use(_error_event(transcript), _squire(0.05, 0.05))
    assert ("browser actions failed" in _context(out)) is speaks


@pytest.mark.asyncio
async def test_a_success_ends_the_streak(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=5, narration="clicked", results=[MISS, MISS])
    event = _error_event(transcript, "### Page\n- ok")
    out = await loop_hook.post_tool_use(event, _squire(0.05, 0.05))
    assert "failed" not in _context(out)


CLICK = "mcp__playwright__browser_click"


class _Call:
    def __init__(self, result: str, id_: str = "", tool: str = CLICK) -> None:
        self.result, self.is_error, self.tool, self.id = result, False, tool, id_


def test_the_streak_does_not_count_the_same_failure_twice():
    """The transcript may already hold the call this event is about: it is found by its id."""
    held = [_Call("ok", "a"), _Call(MISS, "b"), _Call(MISS, "c")]
    assert loop_hook.error_streak(held, MISS, CLICK, use_id="c")[0] == 2
    assert loop_hook.error_streak(held, MISS, CLICK, use_id="d")[0] == 3
    # With no id at all, the last identical failure is taken to be this one.
    assert loop_hook.error_streak(held, MISS, CLICK)[0] == 2


def test_a_streak_with_a_call_outside_the_browser_is_not_called_a_browser_streak():
    streak, _, browser = loop_hook.error_streak([_Call(MISS, "a")], "Error: no file", "Read", "b")
    assert (streak, browser) == (2, False)
    assert "browser_snapshot" not in loop_hook.error_note(streak, ["x", "y"], browser)


@pytest.mark.asyncio
async def test_the_error_note_needs_no_decider(tmp_path, monkeypatch):
    """It is counted, not asked: a dead decider does not silence it."""
    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    transcript = _transcript(tmp_path, calls=5, narration="again", results=[MISS])
    squire = Squire(BrokenDecider(), thresholds=Thresholds(max_usd=1.0, max_decisions=50))
    out = await loop_hook.post_tool_use(_error_event(transcript), squire)
    assert "browser actions failed" in _context(out)


@pytest.mark.asyncio
async def test_the_journal_says_what_the_guard_saw_and_whether_it_spoke(tmp_path, monkeypatch):
    """So a phase can tell a silent guard from a blind one."""
    from sanchopanza.journal import JsonlJournal

    monkeypatch.setenv("SANCHOPANZA_LOOP_HOME", str(tmp_path / "loop"))
    path = tmp_path / "journal.jsonl"
    transcript = _transcript(tmp_path, calls=6, narration="On the overview")
    decider = FixedDecider({"goal_met": answers.truth(0.95), "repeats_check": answers.truth(0.1)})
    squire = Squire(decider, thresholds=Thresholds(max_usd=1.0, max_decisions=50),
                    journal=JsonlJournal(path))  # fmt: skip
    event = {**_event(transcript), "tool_response": SNAPSHOT_RESULT}
    await loop_hook.post_tool_use(event, squire)
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    decision = next(r for r in records if r.get("kind") == "decision")
    assert decision["data"]["outcome"]["spoke"] is True
    assert decision["data"]["outcome"]["page_chars"] > 0


def test_a_hook_that_fails_leaves_a_trace_in_the_journal(tmp_path, monkeypatch, capsys):
    """A failing hook and an absent one used to look the same: no journal at all."""
    from sanchopanza.harness import claude_code
    from sanchopanza.journal import JsonlJournal

    path = tmp_path / "journal.jsonl"
    squire = Squire(BrokenDecider(), thresholds=Thresholds(max_usd=1.0, max_decisions=5),
                    journal=JsonlJournal(path))  # fmt: skip

    async def boom(event, squire):
        raise TimeoutError("the decider did not answer in 10 s")

    monkeypatch.setattr(claude_code, "squire_from_env", lambda redact=False: squire)
    monkeypatch.setattr(loop_hook, "post_tool_use", boom)
    event = {"hook_event_name": "PostToolUse", "tool_name": CLICK, "transcript_path": "x"}
    monkeypatch.setattr(loop_hook.hookio, "stdin_text", lambda: json.dumps(event))
    assert loop_hook.main() == 0, "it still fails open"
    assert capsys.readouterr().out == "", "and says nothing to the agent"
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
    assert [r["kind"] for r in records] == ["loop_error"]
    assert "did not answer" in records[0]["data"]["error"]
