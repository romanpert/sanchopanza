"""Jev 1.14 options on the client: the model, the two Danger Zone headers and the 400 a state
over the token limit gets, chosen by argument or by environment. A mocked transport, no network.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from sanchopanza.contract import DeciderUnavailable, Truth
from sanchopanza.harness.claude_code import decider_from_env
from sanchopanza.providers import jev
from sanchopanza.providers.jev import JevDecider, apreflight

ENV = ("SANCHOPANZA_JEV_MODEL", "SANCHO_JEV_MODEL", "SANCHOPANZA_JEV_LONG_CONTEXT",
       "SANCHO_JEV_LONG_CONTEXT", "SANCHOPANZA_JEV_IMAGES", "SANCHO_JEV_IMAGES")  # fmt: skip
OK = {"answers": {"q": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": 300}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(jev, "BASE_WAIT_S", 0.0)


class Seen:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    @property
    def body(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].content)

    @property
    def headers(self) -> httpx.Headers:
        return self.requests[-1].headers


def mocked(
    seen: Seen, reply: Callable[[httpx.Request], httpx.Response] | None = None
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.requests.append(request)
        if reply is not None:
            return reply(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={**OK, "model": body["model"]})

    return httpx.AsyncClient(base_url=jev.BASE_URL, transport=httpx.MockTransport(handler))


def ask(decider: JevDecider, state: Any = "s") -> Any:
    return asyncio.run(decider.decide("p", state, {"q": Truth("q?")}))


# --- the model ---------------------------------------------------------------------------


def test_the_model_stays_the_pinned_default_without_environment() -> None:
    seen = Seen()
    decision = ask(JevDecider("k", client=mocked(seen)))
    assert seen.body["model"] == jev.DEFAULT_MODEL == "jev-1.13.0"
    assert decision.model == "jev-1.13.0"


def test_the_environment_picks_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.14.0")
    seen = Seen()
    decider = JevDecider("k", client=mocked(seen))
    ask(decider)
    assert seen.body["model"] == "jev-1.14.0" and decider.model == "jev-1.14.0"


def test_an_explicit_model_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.14.0")
    seen = Seen()
    ask(JevDecider("k", model="jev-1.13.0", client=mocked(seen)))
    assert seen.body["model"] == "jev-1.13.0"


def test_model_from_env_reads_a_given_mapping_and_ignores_blanks() -> None:
    assert jev.model_from_env({"SANCHOPANZA_JEV_MODEL": "jev-1.14.0"}) == "jev-1.14.0"
    assert jev.model_from_env({"SANCHO_JEV_MODEL": "jev-1.14.0"}) == "jev-1.14.0"
    assert jev.model_from_env({"SANCHOPANZA_JEV_MODEL": "  "}) == jev.DEFAULT_MODEL
    assert jev.model_from_env({}) == jev.DEFAULT_MODEL


def test_the_harness_and_the_providers_factory_follow_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = {"TYPESAFE_API_KEY": "k", "SANCHOPANZA_JEV_MODEL": "jev-1.14.0",
           "SANCHOPANZA_JEV_LONG_CONTEXT": "1", "SANCHOPANZA_JEV_IMAGES": "true"}  # fmt: skip
    built = decider_from_env(env)
    assert built.name == "jev" and built.model == "jev-1.14.0"
    assert built.long_context is True and built.images is True
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    from sanchopanza.providers import create

    made = create("jev", api_key="k")
    assert made.model == "jev-1.14.0" and made.long_context and made.images


def test_the_preflight_asks_the_model_the_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.14.0")
    seen = Seen()

    def answered(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "answers": {"ok": {"type": "noul", "noul": 0.9}},
                "model": body["model"],
                "usage": {"input_tokens": 300},
            },
        )

    result = asyncio.run(apreflight("k", client=mocked(seen, answered)))
    assert seen.body["model"] == "jev-1.14.0"
    assert result.ok and result.model == "jev-1.14.0"


def test_the_bench_command_uses_the_environment_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """`sanchopanza bench --provider jev` builds `create("jev")`, which reads the variable."""
    from sanchopanza import cli

    monkeypatch.setenv("SANCHOPANZA_JEV_MODEL", "jev-1.14.0")
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    built: list[Any] = []
    real = JevDecider.__init__

    def spy(self: JevDecider, *args: Any, **kwargs: Any) -> None:
        real(self, *args, **kwargs)
        built.append(self)

    monkeypatch.setattr(JevDecider, "__init__", spy)
    cases = tmp_path / "none.jsonl"
    cases.write_text("", encoding="utf-8")
    cli.main(["bench", str(cases), "--provider", "jev"])
    assert built and built[0].model == "jev-1.14.0"


# --- the Danger Zone headers ---------------------------------------------------------------


def test_no_danger_zone_header_by_default() -> None:
    seen = Seen()
    ask(JevDecider("k", client=mocked(seen)))
    assert jev.LONG_CONTEXT_HEADER not in seen.headers
    assert jev.IMAGES_HEADER not in seen.headers


def test_long_context_sends_its_header() -> None:
    seen = Seen()
    ask(JevDecider("k", long_context=True, client=mocked(seen)))
    assert seen.headers[jev.LONG_CONTEXT_HEADER] == "true"
    assert jev.IMAGES_HEADER not in seen.headers


def test_images_sends_its_header() -> None:
    seen = Seen()
    ask(JevDecider("k", images=True, client=mocked(seen)))
    assert seen.headers[jev.IMAGES_HEADER] == "true"
    assert jev.LONG_CONTEXT_HEADER not in seen.headers


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_the_environment_turns_the_headers_on(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SANCHOPANZA_JEV_LONG_CONTEXT", value)
    monkeypatch.setenv("SANCHOPANZA_JEV_IMAGES", value)
    seen = Seen()
    ask(JevDecider("k", client=mocked(seen)))
    assert seen.headers[jev.LONG_CONTEXT_HEADER] == "true"
    assert seen.headers[jev.IMAGES_HEADER] == "true"


@pytest.mark.parametrize("value", ["", "0", "false", "off", "no"])
def test_the_environment_leaves_them_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SANCHOPANZA_JEV_LONG_CONTEXT", value)
    seen = Seen()
    ask(JevDecider("k", client=mocked(seen)))
    assert jev.LONG_CONTEXT_HEADER not in seen.headers


def test_an_explicit_false_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_JEV_LONG_CONTEXT", "1")
    seen = Seen()
    ask(JevDecider("k", long_context=False, client=mocked(seen)))
    assert jev.LONG_CONTEXT_HEADER not in seen.headers


def test_the_headers_reach_a_client_the_decider_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not only an injected client: the one built on first use carries them per request."""
    seen = Seen()
    real = httpx.AsyncClient

    def built(**kwargs: Any) -> httpx.AsyncClient:
        return real(
            **kwargs,
            transport=httpx.MockTransport(
                lambda r: seen.requests.append(r) or httpx.Response(200, json={**OK, "model": "m"})
            ),
        )

    monkeypatch.setattr(httpx, "AsyncClient", built)
    ask(JevDecider("k", long_context=True))
    assert seen.headers[jev.LONG_CONTEXT_HEADER] == "true"
    assert seen.headers["Authorization"] == "Bearer k"


# --- a state over the limit ----------------------------------------------------------------


def _over_limit(_: httpx.Request) -> httpx.Response:
    return httpx.Response(400, json={"detail": {"error_type": "max_tokens_exceeded"}})


def test_max_tokens_exceeded_is_unavailable_with_the_reason_and_the_way_out() -> None:
    seen = Seen()
    with pytest.raises(DeciderUnavailable) as raised:
        ask(JevDecider("k", client=mocked(seen, _over_limit)))
    message = str(raised.value)
    assert "max_tokens_exceeded" in message and "HTTP 400" in message
    assert "long_context" in message and "SANCHOPANZA_JEV_LONG_CONTEXT" in message
    assert len(seen.requests) == 1  # a 400 is not retried


def test_max_tokens_exceeded_with_long_context_on_says_the_state_is_too_long() -> None:
    with pytest.raises(DeciderUnavailable) as raised:
        ask(JevDecider("k", long_context=True, client=mocked(Seen(), _over_limit)))
    message = str(raised.value)
    assert "max_tokens_exceeded" in message and "262k" in message
    assert "SANCHOPANZA_JEV_LONG_CONTEXT" not in message


def test_another_400_names_the_error_type_the_server_gave() -> None:
    def refused(_: httpx.Request) -> httpx.Response:
        detail = {"error_type": "api_usage_error", "message": "Invalid request."}
        return httpx.Response(400, json={"detail": detail})

    with pytest.raises(DeciderUnavailable) as raised:
        ask(JevDecider("k", client=mocked(Seen(), refused)))
    assert "HTTP 400" in str(raised.value) and "api_usage_error" in str(raised.value)


def test_a_400_without_json_still_reads_as_http_400() -> None:
    with pytest.raises(DeciderUnavailable, match="HTTP 400"):
        ask(JevDecider("k", client=mocked(Seen(), lambda _: httpx.Response(400, text="nope"))))
