"""OpenAI's Decisions API adapter against a mock of the guide's examples. No network, no key:
httpx's MockTransport stands in for the service, as in test_funds. The spending tests are the
point: this provider must never spend past a cap shared by every process."""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest

httpx = pytest.importorskip("httpx")

from sanchopanza import funds  # noqa: E402
from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.contract import (  # noqa: E402
    Box,
    Choice,
    DeciderOutOfFunds,
    DeciderUnavailable,
    Score,
    Truth,
)
from sanchopanza.media import Attachment  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.providers import openai_decisions as od  # noqa: E402
from sanchopanza.providers.capped import CappedDecider, SpendCapReached  # noqa: E402

QUESTIONS = {
    "paid": Truth("Has the invoice been paid?", {"true": "a payment is recorded"}),
    "dept": Choice("Which team handles it?", {"billing": "payments", "support": {"what": "help"}}),
    "urgency": Score("How urgent is it?", ["not urgent", "somewhat urgent", "very urgent"]),
}

# The guide's answer shapes ("illustrative response excerpts"), keyed by the names asked.
OK = {
    "model": "gpt-6-luna",
    "answers": [
        {"type": "predicate", "name": "paid", "probability": 0.92},
        {
            "type": "choice",
            "name": "dept",
            "choice": "billing",
            "probabilities": [
                {"value": "billing", "probability": 0.95},
                {"value": "support", "probability": 0.05},
            ],
            "confidence": 0.93,
        },
        {
            "type": "score",
            "name": "urgency",
            "score": 1.1,
            "probabilities": [
                {"value": 0, "label": "0", "probability": 0.1},
                {"value": 1, "label": "1", "probability": 0.7},
                {"value": 2, "label": "2", "probability": 0.2},
            ],
            "confidence": 0.55,
        },
    ],
    "usage": {"input_tokens": 1000, "output_tokens": 0, "total_tokens": 1000},
}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("SANCHOPANZA_FUNDS_DIR", str(tmp_path / "funds"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SANCHOPANZA_OPENAI_DECISIONS_MAX_USD", "")
    monkeypatch.setenv("SANCHOPANZA_OPENAI_DECISIONS_LEDGER", "")
    monkeypatch.setattr(od, "BASE_WAIT_S", 0.0)


def _mock(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=od.BASE_URL, transport=httpx.MockTransport(handler))


def _client(handler, **kwargs) -> od.OpenAIDecisionsClient:
    return od.OpenAIDecisionsClient("sk-test", client=_mock(handler), **kwargs)


def _capped(handler, tmp_path, max_usd: float = 0.5) -> CappedDecider:
    return od.openai_decisions(
        "sk-test", max_usd=max_usd, ledger_path=tmp_path / "ledger.jsonl", client=_mock(handler)
    )


def _run(coro):
    return asyncio.run(coro)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=OK)


# A call billed at nine tenths of its estimate, as the three-characters-a-token estimate makes
# likely, and a cap that holds two and a half estimates: two calls fit, the third does not.
EST = od.estimate_usd("t", QUESTIONS)
BILLED = {**OK, "usage": {"input_tokens": int(EST * 0.9 * 1e6 / od.DEFAULT_PRICE_PER_MTOK)}}
CAP = 2.5 * EST


def _billed(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=BILLED)


def _answering(body):
    return _client(lambda request: httpx.Response(200, json=body))


# --- the wire ---------------------------------------------------------------------------


def test_request_follows_the_guide() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/decisions"
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=OK)

    _run(_client(handler, safety_identifier="u" * 200).decide("p", {"x": 1}, QUESTIONS))
    body = seen[0]
    assert body["model"] == "gpt-6-luna"
    assert json.loads(body["input"]) == {"x": 1}
    assert len(body["safety_identifier"]) == 128
    paid, dept, urgency = body["questions"]
    assert paid == {
        "type": "predicate",
        "name": "paid",
        "instructions": 'Has the invoice been paid?\n\nCriteria: {"true":"a payment is recorded"}',
    }
    assert dept["choices"] == [
        {"value": "billing", "description": "payments"},
        {"value": "support", "description": '{"what":"help"}'},
    ]
    assert urgency["levels"] == [
        {"label": "0", "description": "not urgent"},
        {"label": "1", "description": "somewhat urgent"},
        {"label": "2", "description": "very urgent"},
    ]


def test_mapping_instructions_go_as_json_text() -> None:
    wire = od.to_wire("q", Truth({"ask": "x"}, {"true": "y"}))  # type: ignore[arg-type]
    assert wire["instructions"].startswith('{"ask":"x"}')


def test_own_client_sends_the_bearer_key() -> None:
    client = od.OpenAIDecisionsClient("sk-test")
    made = client._client()
    assert made.headers["authorization"] == "Bearer sk-test"
    assert str(made.base_url).rstrip("/") == od.BASE_URL
    _run(client.aclose())


def test_answers_map_to_the_contract() -> None:
    decision = _run(_client(_ok).decide("p", "t", QUESTIONS))
    paid, dept, urgency = (decision.answer(k) for k in ("paid", "dept", "urgency"))
    assert paid.truth == pytest.approx(0.92) and paid.confidence == pytest.approx(0.84)
    assert dept.choice == "billing" and dept.confidence == pytest.approx(0.93)
    assert dept.probabilities == {"billing": 0.95, "support": 0.05}
    assert urgency.score == pytest.approx(1.1)
    assert urgency.probabilities == {"0": 0.1, "1": 0.7, "2": 0.2}
    assert decision.provider == "openai-decisions" and decision.model == "gpt-6-luna"
    assert decision.cost_usd == pytest.approx(1000 * 0.10 / 1e6)


def test_a_refusal_a_bad_probability_or_the_wrong_kind_is_left_out() -> None:
    body = {
        "answers": [
            {"type": "refusal", "name": "paid"},
            {"type": "predicate", "name": "dept", "probability": 0.9},  # a Choice was asked
            {"type": "predicate", "name": "urgency", "probability": 1.5},
        ],
        "usage": {"input_tokens": 10},
    }
    assert _run(_answering(body).decide("p", "t", QUESTIONS)).answers == {}


def test_choice_without_confidence_is_an_empty_answer() -> None:
    body = {"answers": [{"type": "choice", "name": "dept", "choice": "billing"}]}
    assert _run(_answering(body).decide("p", "t", QUESTIONS)).answer("dept").empty


def test_unnamed_answers_are_read_by_position_only_when_all_are_there() -> None:
    unnamed = [{k: v for k, v in a.items() if k != "name"} for a in OK["answers"]]
    full = _run(_answering({"answers": unnamed}).decide("p", "t", QUESTIONS))
    assert set(full.answers) == {"paid", "dept", "urgency"}
    short = _run(_answering({"answers": unnamed[1:]}).decide("p", "t", QUESTIONS))
    assert short.answers == {}


@pytest.mark.parametrize(
    "body",
    [
        [1, 2],
        {"answers": [{"type": "choice", "name": "dept", "probabilities": 0.5, "confidence": 1}]},
        {"answers": [], "usage": {"input_tokens": "n/a"}},
    ],
)
def test_malformed_bodies_never_raise_anything_but_unavailable(body) -> None:
    with contextlib.suppress(DeciderUnavailable):
        _run(_answering(body).decide("p", "t", QUESTIONS))


def test_box_unknown_types_and_attachments_are_refused_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("called")

    client = _client(handler)
    with pytest.raises(DeciderUnavailable, match="Box"):
        _run(client.decide("p", "t", {"where": Box("Where is the button?")}))
    with pytest.raises(DeciderUnavailable, match="unknown question"):
        _run(client.decide("p", "t", {"x": object()}))  # type: ignore[dict-item]
    image = Attachment(media_type="image/png", data=b"\x89PNG")
    with pytest.raises(DeciderUnavailable, match="attachment"):
        _run(client.decide("p", {"shot": image}, QUESTIONS))


def test_a_state_that_is_not_json_is_sent_as_text() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=OK)

    _run(_client(handler).decide("p", {"when": object()}, QUESTIONS))
    assert "when" in seen[0]["input"]


# --- errors and retries ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, {"message": "quota", "code": "insufficient_quota"}),
        (429, {"message": "quota", "type": "insufficient_quota", "code": None}),
        (429, {"message": "limit", "code": "billing_hard_limit_reached"}),
        (402, {"message": "pay"}),
    ],
)
def test_out_of_quota_trips_the_shared_breaker_and_is_not_retried(status, error) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, json={"error": error})

    client = _client(handler)
    with pytest.raises(DeciderOutOfFunds):
        _run(client.decide("p", "t", QUESTIONS))
    with pytest.raises(DeciderOutOfFunds, match="breaker open"):
        _run(client.decide("p", "t", QUESTIONS))
    assert len(calls) == 1
    assert funds.tripped(client._scope) is not None


def test_funds_message_does_not_send_an_openai_user_to_jev_preflight() -> None:
    text = funds.message({"provider": "openai-decisions", "status": 429, "at": 0})
    assert "jev-preflight" not in text and "openai-decisions account" in text
    assert "jev-preflight" in funds.message({"provider": "jev", "status": 402, "at": 0})


def test_rate_limit_is_retried_then_answers() -> None:
    replies = [httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}),
               httpx.Response(200, json=OK)]  # fmt: skip
    decision = _run(_client(lambda r: replies.pop(0)).decide("p", "t", QUESTIONS))
    assert decision.answer("paid").truth == pytest.approx(0.92)


def test_rate_limit_retries_are_bounded() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})

    with pytest.raises(DeciderUnavailable, match="429"):
        _run(_client(handler).decide("p", "t", QUESTIONS))
    assert len(calls) == od.MAX_RETRIES + 1


def test_a_server_error_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(DeciderUnavailable, match="503"):
        _run(_client(handler).decide("p", "t", QUESTIONS))
    assert len(calls) == 1


def test_not_enabled_is_unavailable_with_the_reason() -> None:
    error = {"message": "Decision API is not enabled for this user", "code": "forbidden"}
    client = _client(lambda r: httpx.Response(403, json={"error": error}))
    with pytest.raises(DeciderUnavailable, match="not enabled"):
        _run(client.decide("p", "t", QUESTIONS))


# --- spending ----------------------------------------------------------------------------


def test_create_returns_the_capped_decider_on_the_shared_ledger(tmp_path, monkeypatch) -> None:
    with pytest.raises(DeciderUnavailable, match="OPENAI_API_KEY"):
        create("openai-decisions")
    monkeypatch.setenv("SANCHOPANZA_OPENAI_DECISIONS_LEDGER", str(tmp_path / "l.jsonl"))
    decider = create("openai-decisions", api_key="sk-test")
    assert isinstance(decider, CappedDecider) and decider.name == "openai-decisions"
    assert decider._ledger.path == tmp_path / "l.jsonl"
    assert decider._ledger.cap_usd == od.DEFAULT_MAX_USD


def test_the_default_ledger_sits_beside_the_funds_breaker() -> None:
    assert od.ledger_path_from_env({}).parent == funds.funds_dir()


def test_the_cap_holds_across_instances_as_hook_processes_build_them(tmp_path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _billed(request)

    for _ in range(4):  # four hook processes, each with a fresh decider
        decider = _capped(handler, tmp_path, max_usd=CAP)
        with contextlib.suppress(SpendCapReached):
            _run(decider.decide("p", "t", QUESTIONS))
    assert len(calls) == 2
    assert SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1).spent() <= CAP


def test_concurrent_calls_cannot_pass_the_cap_together(tmp_path) -> None:
    calls: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        await asyncio.sleep(0.01)
        return _billed(request)

    decider = _capped(handler, tmp_path, max_usd=CAP)

    async def many():
        return await asyncio.gather(
            *(decider.decide("p", "t", QUESTIONS) for _ in range(20)), return_exceptions=True
        )

    results = _run(many())
    assert len(calls) <= 2
    assert sum(isinstance(r, SpendCapReached) for r in results) >= 18


def test_without_a_token_count_the_call_is_priced_at_its_estimate(tmp_path) -> None:
    body = {**OK, "usage": {}}
    decider = _capped(lambda r: httpx.Response(200, json=body), tmp_path)
    decision = _run(decider.decide("p", "t", QUESTIONS))
    assert decision.cost_usd == pytest.approx(EST) and EST > 0
    assert SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1).spent() > 0


def test_an_unreachable_call_keeps_its_estimate_in_the_ledger(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    decider = _capped(handler, tmp_path)
    with pytest.raises(DeciderUnavailable, match="unreachable"):
        _run(decider.decide("p", "t", QUESTIONS))
    spent = SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1).spent()
    assert spent == pytest.approx(od.estimate_usd("t", QUESTIONS))


def test_a_cap_of_zero_builds_nothing_and_bad_caps_or_prices_raise(tmp_path) -> None:
    with pytest.raises(DeciderUnavailable, match="0 USD"):
        od.openai_decisions("sk-test", max_usd=0, ledger_path=tmp_path / "l.jsonl")
    for bad in (float("nan"), float("inf"), -1.0):
        with pytest.raises(ValueError):
            od.openai_decisions("sk-test", max_usd=bad, ledger_path=tmp_path / "l.jsonl")
    for price in (0.0, -0.1, float("nan")):
        with pytest.raises(ValueError):
            od.OpenAIDecisionsClient("sk-test", price_per_mtok=price)


def test_cap_from_env_and_a_bad_value_keeps_the_default() -> None:
    assert od.max_usd_from_env({"SANCHOPANZA_OPENAI_DECISIONS_MAX_USD": "2"}) == 2.0
    for bad in ("x", "nan", "-1", "inf"):
        env = {"SANCHOPANZA_OPENAI_DECISIONS_MAX_USD": bad}
        assert od.max_usd_from_env(env) == od.DEFAULT_MAX_USD


def test_long_input_is_billed_double() -> None:
    assert od.cost_usd(272_000) == pytest.approx(0.0272)
    assert od.cost_usd(272_001) == pytest.approx(272_001 * 0.2 / 1e6)


def test_the_estimate_is_on_the_safe_side_of_four_characters_a_token() -> None:
    chars = len(json.dumps([od.to_wire(k, q) for k, q in QUESTIONS.items()])) + 1
    assert od.estimate_usd("t", QUESTIONS) >= od.cost_usd(chars / 4)
