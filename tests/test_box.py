"""Box, Jev 1.14's primitive: where in an image something is, as fractions of the image.

The wire (measured on jev-1.14.0, 2026-10-15): `{"type": "box", "instructions": ...}` with no
criteria, answered `{"type": "box", "box": {"top", "bottom", "left", "right"}, "confidence"}`.
jev-1.13.0 answers a Box with HTTP 400 "Invalid request.". A mocked transport, no network.
"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import httpx
import pytest

from sanchopanza.contract import Answer, Box, DeciderUnavailable, Decision, Truth
from sanchopanza.providers import jev
from sanchopanza.providers.cached import CachedDecider
from sanchopanza.providers.jev import JevDecider, from_wire, to_wire
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider

WIRE = {"type": "box", "box": {"top": 0.74, "bottom": 0.87, "left": 0.62, "right": 0.95},
        "confidence": 0.41}  # fmt: skip
SUBMIT = Box("the Submit button in `screenshot`")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SANCHOPANZA_JEV_MODEL", "SANCHO_JEV_MODEL"):
        monkeypatch.delenv(name, raising=False)


# --- the contract and the wire -------------------------------------------------------------


def test_a_box_question_goes_on_the_wire_without_criteria() -> None:
    assert SUBMIT.kind == "box"
    assert to_wire(SUBMIT) == {"type": "box", "instructions": "the Submit button in `screenshot`"}


def test_a_box_answer_comes_back_as_top_bottom_left_right_with_its_confidence() -> None:
    answer = from_wire(WIRE)
    assert answer.kind == "box" and not answer.empty
    assert answer.box == (0.74, 0.87, 0.62, 0.95)
    assert answer.confidence == pytest.approx(0.41)


@pytest.mark.parametrize(
    "box",
    [
        None,
        {"top": 0.1, "bottom": 0.2, "left": 0.3},  # a side missing
        {"top": 0.1, "bottom": 1.2, "left": 0.3, "right": 0.4},  # outside the image
        {"top": math.nan, "bottom": 0.2, "left": 0.3, "right": 0.4},
        {"top": 0.5, "bottom": 0.2, "left": 0.3, "right": 0.4},  # upside down
        {"top": "x", "bottom": 0.2, "left": 0.3, "right": 0.4},
    ],
)
def test_a_box_no_code_can_use_is_an_empty_answer(box: Any) -> None:
    answer = from_wire({"type": "box", "box": box, "confidence": 0.5})
    assert answer.empty and answer.box is None and answer.kind == "box"


def test_a_box_without_a_confidence_is_empty() -> None:
    assert from_wire({"type": "box", "box": WIRE["box"]}).empty


def test_answer_dicts_carry_a_box_only_when_there_is_one() -> None:
    """Recordings and caches written before Box keep their exact shape."""
    assert "box" not in Answer("truth", 0.8, truth=0.9).to_dict()
    raw = from_wire(WIRE).to_dict()
    assert raw["box"] == [0.74, 0.87, 0.62, 0.95]
    back = Answer.from_dict(raw)
    assert back.box == (0.74, 0.87, 0.62, 0.95) and back.confidence == pytest.approx(0.41)
    assert Answer.from_dict({**raw, "box": [0.5, 0.1, 0.0, 1.0]}).empty


# --- the client ------------------------------------------------------------------------------


def _client(seen: list[httpx.Request], status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            detail = {"error_type": "api_usage_error", "message": "Invalid request."}
            return httpx.Response(status, json={"detail": detail})
        body = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "jev-1.14.0", "usage": {"input_tokens": 1240},
            "answers": {"box": WIRE, "present": {"type": "noul", "noul": 1.0}},
        } if body else {})  # fmt: skip

    return httpx.AsyncClient(base_url=jev.BASE_URL, transport=httpx.MockTransport(handler))


QUESTIONS = {"present": Truth("Does `screenshot` show a Submit button?"), "box": SUBMIT}


def test_box_on_1_14_is_sent_and_parsed() -> None:
    seen: list[httpx.Request] = []
    decider = JevDecider("k", model="jev-1.14.0", client=_client(seen))
    decision = asyncio.run(decider.decide("browse", {"screenshot": "s"}, QUESTIONS))
    assert json.loads(seen[0].content)["questions"]["box"] == to_wire(SUBMIT)
    assert decision.answer("box").box == (0.74, 0.87, 0.62, 0.95)
    assert decision.answer("present").truth == 1.0


def test_box_on_1_13_is_refused_before_any_request() -> None:
    seen: list[httpx.Request] = []
    decider = JevDecider("k", model="jev-1.13.0", client=_client(seen))
    with pytest.raises(DeciderUnavailable) as raised:
        asyncio.run(decider.decide("browse", {"screenshot": "s"}, QUESTIONS))
    assert "jev-1.13.0" in str(raised.value) and "1.14" in str(raised.value)
    assert seen == []  # nothing paid, nothing sent


def test_box_on_an_alias_is_left_to_the_server_and_its_400_explained() -> None:
    seen: list[httpx.Request] = []
    decider = JevDecider("k", model="jev-latest", client=_client(seen, status=400))
    with pytest.raises(DeciderUnavailable) as raised:
        asyncio.run(decider.decide("browse", {"screenshot": "s"}, QUESTIONS))
    assert len(seen) == 1
    assert "Box" in str(raised.value) and "1.14" in str(raised.value)


def test_the_llm_provider_refuses_a_box_by_name() -> None:
    from sanchopanza.providers.llm import LLMDecider

    async def never(*_: Any) -> Any:
        raise AssertionError("must not be called")

    with pytest.raises(DeciderUnavailable, match="Box"):
        asyncio.run(LLMDecider(never).decide("p", "s", {"box": SUBMIT}))


# --- recordings and caches -------------------------------------------------------------------


class Boxing:
    name = "jev"
    model = "jev-1.14.0"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.calls += 1
        return Decision(point, {"box": from_wire(WIRE)}, self.name, self.model, 1240, 5e-5)


def test_a_box_is_recorded_and_replayed(tmp_path: Any) -> None:
    path = tmp_path / "rec.jsonl"
    asyncio.run(RecordingDecider(Boxing(), path).decide("browse", "s", {"box": SUBMIT}))
    replay = RecordedDecider.from_file(path, model="jev-1.14.0")
    decision = asyncio.run(replay.decide("browse", "s", {"box": SUBMIT}))
    assert decision.answer("box").box == (0.74, 0.87, 0.62, 0.95)
    assert decision.model == "jev-1.14.0"


def test_a_box_is_cached_on_disk_and_read_back(tmp_path: Any) -> None:
    inner = Boxing()
    path = tmp_path / "cache.jsonl"
    asyncio.run(CachedDecider(inner, path=path).decide("browse", "s", {"box": SUBMIT}))
    again = asyncio.run(CachedDecider(inner, path=path).decide("browse", "s", {"box": SUBMIT}))
    assert inner.calls == 1
    assert again.answer("box").box == (0.74, 0.87, 0.62, 0.95)
