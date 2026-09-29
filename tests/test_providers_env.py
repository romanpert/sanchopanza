"""Which decider the harness builds from the environment, and CLM through the Jev client."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from sanchopanza.contract import Truth
from sanchopanza.harness.claude_code import decider_from_env
from sanchopanza.providers.jev import clm


def test_no_key_no_provider_is_the_null_decider() -> None:
    assert decider_from_env({}).name == "null"


def test_an_unusable_provider_says_so_and_falls_back(capsys: pytest.CaptureFixture) -> None:
    assert decider_from_env({"SANCHOPANZA_PROVIDER": "llm"}).name == "null"
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert decider_from_env({"SANCHOPANZA_PROVIDER": "no-such-plugin"}).name == "null"
    assert "no-such-plugin" in capsys.readouterr().err


def test_llm_and_clm_are_built_when_asked() -> None:
    llm = decider_from_env({"SANCHOPANZA_PROVIDER": "llm", "ANTHROPIC_API_KEY": "k"})
    assert llm.name == "llm"
    assert decider_from_env({"SANCHOPANZA_PROVIDER": "clm"}).name == "clm"


def test_clm_speaks_the_typesafe_wire_format_to_its_own_server() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        answer = {"type": "noul", "noul": 0.9}  # the TypeSafe wire shape CLM mirrors
        return httpx.Response(200, json={"answers": {"relevant": answer}, "model": "CLM-v0.1-8B",
                                         "usage": {"input_tokens": 1000}})  # fmt: skip

    client = httpx.AsyncClient(base_url="http://clm.test:9000",
                               transport=httpx.MockTransport(handler))  # fmt: skip
    decider = clm(base_url="http://clm.test:9000", client=client)
    decision = asyncio.run(
        decider.decide("triage", {"text": "t"}, {"relevant": Truth("Relevant?")})
    )
    assert seen["url"].startswith("http://clm.test:9000/")
    assert seen["body"]["model"] == "CLM-v0.1-8B" and "relevant" in seen["body"]["questions"]
    assert decision.provider == "clm" and decision.answer("relevant").truth == pytest.approx(0.9)
    assert decision.cost_usd == 0.0  # self-hosted: no price
