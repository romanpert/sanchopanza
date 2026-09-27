"""M7 of the 0.3.0 review: what a decision reads leaves the machine, so it can be redacted first.

With the Jev provider every state goes to api.typesafe.ai. `Squire(redact=...)` runs on the
state before any provider sees it; `redact_secrets` is a conservative default for keys and
tokens. A redactor that fails does not send the unredacted state: the decision is skipped
and the harness keeps its default.
"""

from __future__ import annotations

import asyncio

from sanchopanza import Squire
from sanchopanza.contract import Truth
from sanchopanza.redact import redact_secrets


class Capture:
    name = "capture"

    def __init__(self):
        self.states = []

    async def decide(self, point, state, questions):
        from sanchopanza.contract import Decision

        self.states.append(state)
        return Decision(point, {}, "capture", "m")


def test_the_redactor_runs_before_the_provider():
    decider = Capture()
    squire = Squire(decider, redact=lambda s: {**s, "text": "[redacted]"})
    asyncio.run(squire.decide("p", {"text": "secret stuff", "k": 1}, {"q": Truth("q?")}))
    assert decider.states == [{"text": "[redacted]", "k": 1}]


def test_a_failing_redactor_sends_nothing():
    decider = Capture()

    def broken(state):
        raise ValueError("boom")

    decision = asyncio.run(
        Squire(decider, redact=broken).decide("p", {"text": "secret"}, {"q": Truth("q?")})
    )
    assert decider.states == [] and decision.failed


def test_redact_secrets_masks_keys_tokens_and_nested_values():
    state = {
        "text": "use sk-ant-api03-abcdefghijklmnopqrstuvwx and "
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "nested": {"auth": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"},
        "keep": "nothing secret here",
    }
    out = redact_secrets(state)
    flat = str(out)
    assert "sk-ant-api03" not in flat and "ghp_" not in flat and "eyJhbGci" not in flat
    assert out["keep"] == "nothing secret here"


def test_fork_keeps_the_redactor_and_starts_a_fresh_meter():
    decider = Capture()
    template = Squire(decider, redact=lambda s: {**s, "text": "[redacted]"})
    asyncio.run(template.decide("p", {"text": "a"}, {"q": Truth("q?")}))
    child = template.fork()
    assert child.meter.decisions == 0 and template.meter.decisions == 1
    asyncio.run(child.decide("p", {"text": "secret"}, {"q": Truth("q?")}))
    assert decider.states[-1] == {"text": "[redacted]"}
