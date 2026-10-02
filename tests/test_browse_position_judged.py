"""The hook asks the decider whether a request wants an element by its place (df595ba).

The word rule scored 0.30 / 0.20 and 0.50 / 0.31 on two sets it was not written on; Jev's
Truth question scored 0.929 / 1.0 on a set sealed after the question was frozen. These pin how
the hook uses it: the decider decides when there is one, the rule when there is none or the
session is past its ceiling, one call per request and session, the request only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sanchopanza import Squire
from sanchopanza.contract import Answer
from sanchopanza.providers.fixed import BrokenDecider, FixedDecider


def _truth(p: float) -> Answer:
    return Answer(kind="truth", truth=p, confidence=abs(2 * p - 1))


def _judge(goal: str, decider: object | None, tmp_path: Path, *, over: bool = False) -> bool:
    from sanchopanza.harness.browse_hook import judged_position

    squire = Squire(decider) if decider is not None else Squire()
    return asyncio.run(judged_position(goal, squire, tmp_path, over=over))


SIDEBAR = "Task: Open the second link in the navigation sidebar and say where it goes."
NAME = "Task: What is the last name of the person on the page?"


def test_the_decider_overrules_the_word_rule(tmp_path: Path) -> None:
    from sanchopanza.harness.browse_hook import asks_for_position

    assert not asks_for_position(SIDEBAR) and asks_for_position(NAME), "the rule's two misses"
    assert _judge(SIDEBAR, FixedDecider({"position": _truth(0.95)}), tmp_path / "a")
    assert not _judge(NAME, FixedDecider({"position": _truth(0.05)}), tmp_path / "b")


def test_without_a_decider_or_past_the_ceiling_the_rule_decides(tmp_path: Path) -> None:
    yes = FixedDecider({"position": _truth(0.95)})
    assert not _judge(SIDEBAR, None, tmp_path / "a"), "no provider: the rule"
    assert not _judge(SIDEBAR, BrokenDecider(), tmp_path / "b"), "provider down: the rule"
    assert not _judge(SIDEBAR, yes, tmp_path / "c", over=True), "over the ceiling: the rule"
    assert yes.calls == 0, "past the ceiling nothing is asked"


def test_a_verdict_holds_past_the_ceiling(tmp_path: Path) -> None:
    """Review of 38a5dab: past the ceiling the rule used to overrule the cached verdict, and a
    request judged a place got its next snapshot cut."""
    assert _judge(SIDEBAR, FixedDecider({"position": _truth(0.95)}), tmp_path)
    assert _judge(SIDEBAR, None, tmp_path, over=True), "the cached verdict, not the rule"


def test_an_unreadable_cache_is_asked_again(tmp_path: Path) -> None:
    for junk in ("[1, 2]", "3", "{half"):
        (tmp_path / "position.json").write_text(junk, encoding="utf-8")
        decider = FixedDecider({"position": _truth(0.95)})
        assert _judge(SIDEBAR, decider, tmp_path), junk
        assert decider.calls == 1, junk
        (tmp_path / "position.json").unlink()


def test_the_cache_stays_out_of_git(tmp_path: Path) -> None:
    folder = tmp_path / ".sanchopanza" / "archive" / "s1"
    assert _judge(SIDEBAR, FixedDecider({"position": _truth(0.95)}), folder)
    assert (tmp_path / ".sanchopanza" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert not list(folder.glob("*.tmp")), "the partial file was renamed into place"


def test_one_call_per_request_and_session(tmp_path: Path) -> None:
    decider = FixedDecider({"position": _truth(0.95)})
    for step in ("First I'll open the page", "Now I'll read the snapshot"):
        assert _judge(f"{SIDEBAR}\nAgent's step: {step}", decider, tmp_path)
    assert decider.calls == 1, "the agent's step changes, the request does not: asked once"
    assert not _judge(NAME, FixedDecider({"position": _truth(0.05)}), tmp_path)


async def test_the_hook_follows_the_decider_on_a_real_snapshot(tmp_path: Path, monkeypatch) -> None:
    from sanchopanza.harness import browse_hook

    from .test_browse import _big_snapshot, _playwright_event, _transcript

    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(tmp_path / "archive"))
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()

    asked: list[str] = []

    def squire(position: float) -> Squire:
        # every ranking question gets 0.5; the request's own question gets `position`
        def judge(state, question):  # type: ignore[no-untyped-def]
            if "request" in state:
                asked.append(state["request"])
                return _truth(position)
            return _truth(0.5)

        from sanchopanza.providers.local import LocalDecider

        return Squire(LocalDecider(judge, cost_usd_per_call=0.0001))

    place = _playwright_event(tmp_path / "a", _big_snapshot(400))
    place["transcript_path"] = _transcript(tmp_path / "a", SIDEBAR.removeprefix("Task: "))
    assert await browse_hook.post_tool_use(place, squire(0.95)) == {}, "a place: uncut"
    assert asked == [SIDEBAR.removeprefix("Task: ")], "uncut because the decider said so"
    name = _playwright_event(tmp_path / "b", _big_snapshot(400))
    name["transcript_path"] = _transcript(tmp_path / "b", NAME.removeprefix("Task: "))
    assert await browse_hook.post_tool_use(name, squire(0.05)), "not a place: cut as usual"
    assert len(asked) == 2


def test_only_the_request_is_sent(tmp_path: Path) -> None:
    from sanchopanza.harness.browse_hook import judged_position

    seen: list[dict] = []

    class Spy(FixedDecider):
        async def decide(self, point, state, questions):  # type: ignore[no-untyped-def]
            seen.append(dict(state))
            return await super().decide(point, state, questions)

    goal = f"{SIDEBAR}\nNow asked: and the third one?\nAgent's step: First I'll open it"
    squire = Squire(Spy({"position": _truth(0.9)}))
    assert asyncio.run(judged_position(goal, squire, tmp_path, over=False))
    request = seen[0]["request"]
    assert "Agent's step" not in request and "First I'll open it" not in request
    assert "second link in the navigation sidebar" in request and "third one" in request
    assert not request.startswith("Task:")
