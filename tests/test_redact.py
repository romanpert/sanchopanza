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


# --- the strict mask (the MCP guard's record, A3 review of 2026-10-16) -------------------------
# `mask` and `redact_secrets` stay as they were: recorded keys and published states depend on
# them. `mask_strict` adds what a tool result carries and the conservative list let through.


def test_strict_masks_a_private_key_cut_before_its_end():
    from sanchopanza.redact import mask_strict

    text = "key: -----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA7x"
    assert "MIIE" not in mask_strict(text) and mask_strict(text).startswith("key: ")


def test_strict_masks_json_and_repr_credential_values_and_keeps_the_key():
    from sanchopanza.redact import mask_strict

    cases = {'{"password": "hunter22"}': "hunter22", "{'api_key': 'k-123-456'}": "k-123-456",
             '{"Secret":"s3cr3t"}': "s3cr3t", '{"token": "t0k3n"}': "t0k3n",
             '{"Authorization": "Basic dXNlcjpwYXNz"}': "dXNl",
             '{"client_secret" : "abcdef"}': "abcdef"}  # fmt: skip
    for text, value in cases.items():
        out = mask_strict(text)
        assert "[secret]" in out and value not in out, text
    assert '"password"' in mask_strict('{"password": "hunter22"}')
    assert mask_strict('{"token_count": 12}') == '{"token_count": 12}'


def test_strict_masks_the_password_in_a_url():
    from sanchopanza.redact import mask_strict

    out = mask_strict("clone https://me:pa55w0rd@git.example.com/repo.git now")
    assert "pa55w0rd" not in out and "git.example.com/repo.git" in out


def test_strict_keeps_what_the_plain_mask_masks():
    from sanchopanza.redact import mask, mask_strict

    token = "ghp_" + "a" * 36
    assert mask_strict(f"token {token}") == mask(f"token {token}") == "token [secret]"


def test_the_plain_mask_is_unchanged():
    from sanchopanza.redact import mask

    assert mask('{"password": "hunter22"}') == '{"password": "hunter22"}'
    assert mask("https://me:pa55w0rd@host/x") == "https://me:pa55w0rd@host/x"
