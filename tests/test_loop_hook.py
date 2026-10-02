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


def _transcript(tmp_path: Path, *, calls: int, narration: str) -> Path:
    """A Claude Code transcript with `calls` paired tool calls and the agent's own prose."""
    path = tmp_path / "sess.jsonl"
    lines = [{"type": "user", "message": {"role": "user", "content": GOAL}}]
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
                "content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "ok"}],
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
