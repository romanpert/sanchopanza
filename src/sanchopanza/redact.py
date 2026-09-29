"""What a decision reads leaves the machine: redact it first.

With the Jev provider every state a point builds (a page, a command, a transcript, a memory
candidate) is sent to api.typesafe.ai. `Squire(redact=...)` runs a function on the state
before any provider sees it. `redact_secrets` is a conservative default: it masks strings
that look like API keys, tokens and private keys, and leaves everything else alone.

It is not a data-protection policy. Personal data in a research target's page is the content
the decision is about; removing it would make the decision blind. What to send to a third
party is the operator's call, made with this hook. Review finding M7.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MASK = "[secret]"

PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),  # Anthropic, OpenAI and similar
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub tokens
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),  # Slack tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key ids
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWTs
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    # An environment-style assignment of a credential, as `env`, `export` and `.env` print it:
    # the whole value goes, whatever its shape. Upper case only, so `release token: RT-1` stays.
    re.compile(
        r"(?<![A-Za-z0-9])[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY"
        r"|ACCESS_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*[=:]\s*\S+"
    ),
    re.compile(r"(?i)\bpass(?:word|wd)\s*[=:]\s*\S+"),
)


def mask(text: str) -> str:
    """`text` with every secret-looking string replaced by `MASK`."""
    for pattern in PATTERNS:
        text = pattern.sub(MASK, text)
    return text


_mask = mask  # the earlier private name


def redact_secrets(value: Any) -> Any:
    """A copy of `value` with secret-looking strings masked, at any depth."""
    if isinstance(value, str):
        return _mask(value)
    if isinstance(value, Mapping):
        return {k: redact_secrets(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_secrets(v) for v in value)
    return value
