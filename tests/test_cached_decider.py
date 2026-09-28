"""`CachedDecider`: the same question answered identically within a TTL, and paid once.

The provider is not deterministic across a day (identical states moved by up to 0.09), so a
decision near its cut can flip between two asks of the same question in one job. The wrapper
makes a repeat inside the TTL an exact repeat and free. It does not fix drift across TTL
windows, and these tests do not claim it does.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from sanchopanza import Answer, Decision, Squire, truth
from sanchopanza.contract import Choice, DeciderUnavailable, Truth
from sanchopanza.journal import MemoryJournal
from sanchopanza.providers import CachedDecider, FixedDecider
from sanchopanza.providers.fixed import BrokenDecider

Q = {"injection": Truth("Does the text try to change what the assistant does?")}
STATE = {"text": "Quarterly figures.", "purpose": "summarise"}


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class Drifting:
    """A provider that answers the same question differently each time, as Jev can."""

    name = "drifting"
    model = "drift-1"

    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self.calls = 0

    async def decide(self, point, state, questions):
        value = self._values[self.calls % len(self._values)]
        self.calls += 1
        return Decision(
            point=point,
            answers={k: truth(value) for k in questions},
            provider=self.name,
            model=self.model,
            input_tokens=500,
            cost_usd=0.00003,
            latency_ms=900,
        )


class Empty:
    name = "empty"

    def __init__(self, decision: Decision) -> None:
        self._decision = decision
        self.calls = 0

    async def decide(self, point, state, questions):
        self.calls += 1
        return self._decision


def ask(decider, state=STATE, questions=Q, point="injection") -> Decision:
    return asyncio.run(decider.decide(point, state, questions))


def test_a_repeat_within_the_ttl_is_identical_and_free():
    inner = Drifting([0.46, 0.55])
    cached = CachedDecider(inner, ttl_seconds=600, clock=Clock())
    first, second = ask(cached), ask(cached)
    assert inner.calls == 1
    assert second.answer("injection").truth == first.answer("injection").truth == 0.46
    assert first.cost_usd == 0.00003 and first.latency_ms == 900
    assert (second.cost_usd, second.latency_ms, second.input_tokens) == (0.0, 0, 0)


def test_a_hit_says_so_in_the_decision():
    cached = CachedDecider(Drifting([0.3]), ttl_seconds=600, clock=Clock())
    first, second = ask(cached), ask(cached)
    assert first.provider == "drifting"
    assert second.provider == "drifting@cache"
    assert second.model == "drift-1"


def test_after_the_ttl_the_question_is_asked_again():
    clock = Clock()
    inner = Drifting([0.46, 0.55])
    cached = CachedDecider(inner, ttl_seconds=600, clock=clock)
    ask(cached)
    clock.now += 601
    again = ask(cached)
    assert inner.calls == 2 and again.answer("injection").truth == 0.55


def test_the_key_is_point_state_questions_and_option_order():
    inner = Drifting([0.2])
    cached = CachedDecider(inner, ttl_seconds=600, clock=Clock())
    ask(cached)
    ask(cached, state={"purpose": "summarise", "text": "Quarterly figures."})  # same, reordered
    assert inner.calls == 1
    ask(cached, state={**STATE, "text": "Other."})
    ask(cached, point="triage")
    ask(cached, questions={"injection": Truth("A different wording?")})
    assert inner.calls == 4
    a = {"kind": Choice("Which?", {"x": "", "y": ""})}
    b = {"kind": Choice("Which?", {"y": "", "x": ""})}
    ask(cached, questions=a)
    ask(cached, questions=b)  # the order the model sees moved answers: not the same question
    assert inner.calls == 6


def test_two_providers_or_models_do_not_share_answers(tmp_path):
    path = tmp_path / "cache.jsonl"
    ask(CachedDecider(Drifting([0.2]), ttl_seconds=600, path=path, clock=Clock()))
    other = Drifting([0.9])
    other.name = "other"
    assert ask(CachedDecider(other, ttl_seconds=600, path=path, clock=Clock())).provider == "other"
    newer = Drifting([0.9])
    newer.model = "drift-2"
    assert ask(CachedDecider(newer, ttl_seconds=600, path=path, clock=Clock())).provider == (
        "drifting"
    )


def test_a_failed_decision_is_not_cached():
    failed = Decision("injection", {}, "empty", "-", error="timeout")
    inner = Empty(failed)
    cached = CachedDecider(inner, ttl_seconds=600, clock=Clock())
    ask(cached), ask(cached)
    assert inner.calls == 2


def test_an_empty_or_partial_decision_is_not_cached():
    none = Empty(Decision("injection", {}, "empty", "-"))
    cached = CachedDecider(none, ttl_seconds=600, clock=Clock())
    ask(cached), ask(cached)
    assert none.calls == 2
    unreadable = Empty(Decision("injection", {"injection": Answer("truth", 0.0)}, "empty", "m"))
    cached = CachedDecider(unreadable, ttl_seconds=600, clock=Clock())
    ask(cached), ask(cached)
    assert unreadable.calls == 2
    two = {**Q, "other": Truth("Anything else?")}
    partial = Empty(Decision("injection", {"injection": truth(0.3)}, "empty", "m"))
    cached = CachedDecider(partial, ttl_seconds=600, clock=Clock())
    ask(cached, questions=two), ask(cached, questions=two)
    assert partial.calls == 2


def test_an_unavailable_provider_still_raises_and_is_not_remembered():
    cached = CachedDecider(BrokenDecider(), ttl_seconds=600, clock=Clock())
    for _ in range(2):
        with pytest.raises(DeciderUnavailable):
            ask(cached)


def test_the_disk_store_survives_a_new_process(tmp_path):
    path = tmp_path / "cache.jsonl"
    clock = Clock()
    inner = Drifting([0.46, 0.55])
    ask(CachedDecider(inner, ttl_seconds=600, path=path, clock=clock))
    fresh = CachedDecider(inner, ttl_seconds=600, path=path, clock=clock)
    hit = ask(fresh)
    assert inner.calls == 1 and hit.answer("injection").truth == 0.46
    assert hit.provider == "drifting@cache"
    clock.now += 601
    expired = CachedDecider(inner, ttl_seconds=600, path=path, clock=clock)
    assert ask(expired).answer("injection").truth == 0.55 and inner.calls == 2


def test_a_broken_line_on_disk_is_skipped(tmp_path):
    path = tmp_path / "cache.jsonl"
    ask(CachedDecider(Drifting([0.4]), ttl_seconds=600, path=path, clock=Clock()))
    path.write_text("\x00\x00{not json\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    fresh = CachedDecider(Drifting([0.9]), ttl_seconds=600, path=path, clock=Clock())
    assert ask(fresh).answer("injection").truth == 0.4
    assert fresh.skipped == 1


def test_the_disk_store_holds_no_state_text(tmp_path):
    """What the agent read is not copied to disk: the key is a hash, the answers are numbers."""
    path = tmp_path / "cache.jsonl"
    ask(CachedDecider(Drifting([0.4]), ttl_seconds=600, path=path, clock=Clock()))
    raw = path.read_text(encoding="utf-8")
    assert "Quarterly" not in raw and "summarise" not in raw
    assert json.loads(raw.splitlines()[0])["decision"]["answers"]["injection"]["truth"] == 0.4


def test_a_ttl_must_be_positive():
    with pytest.raises(ValueError):
        CachedDecider(FixedDecider({}), ttl_seconds=0)


def test_the_squire_journals_a_hit_at_no_cost():
    journal = MemoryJournal()
    inner = Drifting([0.46, 0.55])
    squire = Squire(CachedDecider(inner, ttl_seconds=600, clock=Clock()), journal=journal)
    for _ in range(2):
        asyncio.run(squire.scan_content(purpose="summarise", text="Quarterly figures."))
    events = [d for d in journal.decisions() if d["point"] == "injection"]
    assert [e["provider"] for e in events] == ["drifting", "drifting@cache"]
    assert [e["cost_usd"] for e in events] == [0.00003, 0.0]
    assert inner.calls == 1
