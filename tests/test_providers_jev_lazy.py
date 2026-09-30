"""The Jev client is built on the first question, not when the decider is made: a hook makes its
decider on every shell command and asks on few of them (adoption study, phase B)."""

from __future__ import annotations

import asyncio
import sys

from sanchopanza.providers.jev import JevDecider


def test_making_the_decider_builds_no_client() -> None:
    decider = JevDecider(api_key="k")
    assert decider._made is None
    asyncio.run(decider.aclose())  # closing one never used is fine


def test_the_first_question_builds_the_client_once(monkeypatch) -> None:  # noqa: ANN001
    decider = JevDecider(api_key="k", base_url="https://example.invalid/")
    first = decider._client()
    assert decider._client() is first and "httpx" in sys.modules
    assert str(first.base_url) == "https://example.invalid"
    assert first.headers["Authorization"] == "Bearer k"
    asyncio.run(decider.aclose())


def test_an_injected_client_is_used_as_it_is() -> None:
    marker = object()
    assert JevDecider(api_key="k", client=marker)._client() is marker
