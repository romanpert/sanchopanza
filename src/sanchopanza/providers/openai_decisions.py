"""OpenAI's Decisions API over HTTP. One file, no SDK, the same contract as every provider.

    POST https://api.openai.com/v1/decisions
    Authorization: Bearer $OPENAI_API_KEY
    {"model": "gpt-6-luna", "input": "...", "questions": [{"type", "name", "instructions", ...}]}

**Written against the official guide, measured once.** The format is the one in OpenAI's guide
(developers.openai.com/api/docs/guides/decisions, read 2026-10-16; public beta since
2026-10-06); the API reference page was not readable, so error bodies, limits and the field
constraints are not documented here and the tests stand on a mock of the guide's examples. One
sealed measurement (docs/results/2026-10-16-openai-decisions): on the public benches, asked as
sanchopanza ships, 200 of 244 rows right against Jev's 206 (−2.5 points [−6.1, +1.2], "no
concluyente" at −5), every query answered, its predicate probabilities better calibrated than
Jev's. Its thresholds are Jev's until someone derives its own.

Mapping, from the guide:
- `Truth` is a `predicate`; its answer is `probability`, and confidence is |2p - 1| as for
  every Truth here. A predicate has no criteria field, so the criteria go into the
  instructions as JSON.
- `Choice` is a `choice` with `choices: [{value, description}]`; the answer's `probabilities`
  come as a list of `{value, probability}` and `confidence` is the provider's own.
- `Score` is a `score` with `levels: [{label, description}]`, lowest first, each label the
  level's index and its description the level's text; the answer's `score` is the
  probability-weighted mean of the level indices, as Jev's, and its `probabilities` are keyed by
  index (`"0"`, `"1"`, ...), as Jev's.
- `Box` has no counterpart: refused before any request. A `refusal` answer, or one of another
  kind than the question asked, is no answer. Attachments are refused out loud (the guide takes
  base64 images; not wired yet). A Choice or Score answer without a confidence is no answer,
  where Jev's reads it as 0.

Price (guide, 2026-10): 0.10 USD per million input tokens and nothing else; past 272k input
tokens the rate doubles (secondary source, applied here on the safe side).

**Spending.** OpenAI is billed against a balance this project ran into debt with once, so
`create("openai-decisions")` never returns an uncapped client: `openai_decisions()` wraps it in
`CappedDecider` over a ledger on disk (`<home>/funds/openai-decisions-ledger.jsonl`, or
`SANCHOPANZA_OPENAI_DECISIONS_LEDGER`) that every process on the machine shares, hooks included.
Each call is reserved at a pessimistic estimate before it is made and settled at its reported
cost (the estimate when no usable token count comes back, or when the call was cut or the
service unreachable). The cap, `max_usd` or `SANCHOPANZA_OPENAI_DECISIONS_MAX_USD`, is the
ledger's total, 0.50 USD by default; it does not reset by itself: raise it, or start a new
ledger, by hand. An out-of-quota answer (402, or 429 `insufficient_quota`) trips the same shared
breaker as Jev's 402 and is never retried; only a rate-limit 429 is retried, three times.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import math
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env, funds
from ..budget import SpendLedger
from ..contract import (
    Answer,
    Box,
    Choice,
    DeciderOutOfFunds,
    DeciderUnavailable,
    Decision,
    Question,
    Score,
    State,
    Truth,
    as_number,
    truth_confidence,
    usable,
)
from ..media import attachments_in
from .capped import CappedDecider

BASE_URL = "https://api.openai.com"
PATH = "/v1/decisions"
DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_PRICE_PER_MTOK = 0.10
LONG_INPUT_TOKENS = 272_000
LONG_INPUT_FACTOR = 2.0
DEFAULT_MAX_USD = 0.50
BATCH = "openai-decisions"
# About four characters a token for English text; three keeps the estimate on the safe side
# for other languages and JSON.
CHARS_PER_TOKEN_ESTIMATE = 3
OUT_OF_FUNDS = 402
RATE_LIMITED = 429
QUOTA_CODES = frozenset({"insufficient_quota", "billing_hard_limit_reached"})
MAX_RETRIES = 3
BASE_WAIT_S = 1.0
MAX_WAIT_S = 30.0  # the longest Retry-After honoured; a longer one is a stop
WIRE_KIND = {"predicate": Truth, "choice": Choice, "score": Score}


def max_usd_from_env(env: Mapping[str, str] | None = None) -> float:
    """`SANCHOPANZA_OPENAI_DECISIONS_MAX_USD`, else `DEFAULT_MAX_USD`; a bad value is the
    default, never no cap."""
    raw = _env.get("OPENAI_DECISIONS_MAX_USD", "", env=env).strip()
    try:
        value = float(raw) if raw else DEFAULT_MAX_USD
    except ValueError:
        return DEFAULT_MAX_USD
    return value if math.isfinite(value) and value >= 0 else DEFAULT_MAX_USD


def ledger_path_from_env(env: Mapping[str, str] | None = None) -> Path:
    """`SANCHOPANZA_OPENAI_DECISIONS_LEDGER`, else the ledger beside the funds breaker."""
    raw = _env.get("OPENAI_DECISIONS_LEDGER", "", env=env).strip()
    return Path(raw) if raw else funds.funds_dir() / "openai-decisions-ledger.jsonl"


def _text(value: Any) -> str:
    """Free text for the wire: strings as they are, the rest as JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def to_wire(name: str, question: Question) -> dict[str, Any]:
    """Contract question to the Decisions API's question object."""
    if isinstance(question, Box):
        raise DeciderUnavailable("the Decisions API has no Box question (not sent)")
    if not isinstance(question, (Truth, Choice, Score)):
        raise DeciderUnavailable(f"unknown question type {type(question).__name__} (not sent)")
    instructions = _text(question.instructions)
    if isinstance(question, Truth):
        if question.criteria:
            instructions = f"{instructions}\n\nCriteria: {_text(dict(question.criteria))}"
        return {"type": "predicate", "name": name, "instructions": instructions}
    if isinstance(question, Choice):
        return {
            "type": "choice",
            "name": name,
            "instructions": instructions,
            "choices": [
                {"value": str(value), "description": _text(criteria)}
                for value, criteria in question.options.items()
            ],
        }
    return {
        "type": "score",
        "name": name,
        "instructions": instructions,
        "levels": [
            {"label": str(index), "description": _text(level)}
            for index, level in enumerate(question.levels)
        ],
    }


def _probabilities(raw: Any) -> dict[str, float]:
    """`[{value, probability}]` (the guide's list) or a mapping, to {value: p}; anything else is
    no distribution. A value that is not a finite number is NaN, which `usable` rejects."""
    if isinstance(raw, Mapping):
        return {str(k): _required(v) for k, v in raw.items()}
    if not isinstance(raw, (list, tuple)):
        return {}
    return {
        str(item["value"]): _required(item.get("probability"))
        for item in raw
        if isinstance(item, Mapping) and "value" in item
    }


def _required(value: Any) -> float:
    number = as_number(value)
    return math.nan if number is None else number


def from_wire(raw: Mapping[str, Any], question: Question | None = None) -> Answer | None:
    """One answer to contract. None for a refusal, an unknown type, or a type other than the
    question's: left out, never invented."""
    kind = str(raw.get("type", ""))
    expected = WIRE_KIND.get(kind)
    if expected is None or (question is not None and not isinstance(question, expected)):
        return None
    if kind == "predicate":
        p = as_number(raw.get("probability"))
        if p is None or not 0.0 <= p <= 1.0:
            return None
        return usable(Answer(kind="truth", truth=p, confidence=truth_confidence(p)))
    if kind == "choice":
        chosen = raw.get("choice")
        return usable(
            Answer(
                kind="choice",
                confidence=_required(raw.get("confidence")),
                choice=str(chosen) if chosen is not None else None,
                probabilities=_probabilities(raw.get("probabilities")),
            )
        )
    return usable(
        Answer(
            kind="score",
            confidence=_required(raw.get("confidence")),
            score=as_number(raw.get("score")),
            probabilities=_probabilities(raw.get("probabilities")),
        )
    )


def cost_usd(input_tokens: float, price_per_mtok: float = DEFAULT_PRICE_PER_MTOK) -> float:
    """Input tokens at the list price, doubled past the long-input threshold."""
    factor = LONG_INPUT_FACTOR if input_tokens > LONG_INPUT_TOKENS else 1.0
    return input_tokens * price_per_mtok * factor / 1_000_000


def _input_text(state: State) -> str:
    return state if isinstance(state, str) else json.dumps(state, ensure_ascii=False, default=str)


def estimate_usd(
    state: State,
    questions: Mapping[str, Question],
    *,
    price_per_mtok: float = DEFAULT_PRICE_PER_MTOK,
) -> float:
    """A pessimistic price for one call, from the size of what would be sent."""
    asked = []
    for key, question in questions.items():
        try:
            asked.append(to_wire(key, question))
        except DeciderUnavailable:
            asked.append({"name": key})
    chars = len(_input_text(state)) + len(json.dumps(asked, ensure_ascii=False, default=str))
    return cost_usd(math.ceil(chars / CHARS_PER_TOKEN_ESTIMATE), price_per_mtok)


class OpenAIDecisionsClient:
    """The uncapped HTTP client. Use `openai_decisions()` (what `create("openai-decisions")`
    returns), which puts it behind the shared ledger; this class alone has no spending cap."""

    name = "openai-decisions"
    accepts_attachments = False

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = BASE_URL,
        model: str = DEFAULT_MODEL,
        price_per_mtok: float = DEFAULT_PRICE_PER_MTOK,
        timeout_s: float = 10.0,
        safety_identifier: str | None = None,
        client: Any | None = None,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise DeciderUnavailable("OPENAI_API_KEY is not set")
        if not (math.isfinite(price_per_mtok) and price_per_mtok > 0):
            raise ValueError("price_per_mtok must be a positive, finite number")
        if client is None and importlib.util.find_spec("httpx") is None:  # pragma: no cover
            raise DeciderUnavailable("install sanchopanza[jev] (httpx) to use this provider")
        self._key, self._base_url, self._timeout_s = key, base_url.rstrip("/"), timeout_s
        self._model, self._price = model, price_per_mtok
        self._safety_identifier = safety_identifier
        self._made: Any | None = client
        self._scope = funds.scope(self._base_url, key)
        self.last_status: int | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def price_per_mtok(self) -> float:
        return self._price

    def _client(self) -> Any:
        if self._made is None:
            import httpx

            self._made = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._key}",
                         "Content-Type": "application/json"},
                timeout=self._timeout_s,
            )  # fmt: skip
        return self._made

    async def aclose(self) -> None:
        if self._made is not None:
            await self._made.aclose()

    def _body(self, state: State, questions: Mapping[str, Question]) -> dict[str, Any]:
        found = attachments_in(state)
        if found:
            raise DeciderUnavailable(
                f"the state carries {len(found)} attachment(s); this provider sends text only "
                "(the Decisions API takes base64 images, not wired here)"
            )
        body: dict[str, Any] = {
            "model": self._model,
            "input": _input_text(state),
            "questions": [to_wire(key, q) for key, q in questions.items()],
        }
        if self._safety_identifier:
            body["safety_identifier"] = self._safety_identifier[:128]
        return body

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        body = self._body(state, questions)
        trip = funds.tripped(self._scope)
        if trip is not None:
            raise DeciderOutOfFunds(
                f"{self.name} did not answer: HTTP {trip.get('status', OUT_OF_FUNDS)} (out of "
                "funds; breaker open, not called)",
                int(trip.get("status") or OUT_OF_FUNDS),
            )
        start = time.monotonic()
        data = await self._send(body)
        latency_ms = int((time.monotonic() - start) * 1000)
        reported = as_number((data.get("usage") or {}).get("input_tokens"))
        tokens = int(reported) if reported is not None and reported > 0 else 0
        # No usable token count: the call is priced at the estimate, never at zero.
        cost = (
            cost_usd(tokens, self._price)
            if tokens
            else estimate_usd(state, questions, price_per_mtok=self._price)
        )
        return Decision(
            point=point,
            answers=_answers(data.get("answers"), questions),
            provider=self.name,
            model=str(data.get("model") or self._model),
            input_tokens=tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def _send(self, body: dict[str, Any]) -> Mapping[str, Any]:
        last = "no response"
        self.last_status = None
        for attempt in range(MAX_RETRIES + 1):
            client = self._client()
            import httpx

            try:
                response = await client.post(PATH, json=body)
            except httpx.HTTPError as error:
                raise DeciderUnavailable(
                    f"{self.name} unreachable: {error.__class__.__name__}"
                ) from error
            self.last_status = response.status_code
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as error:
                    raise DeciderUnavailable(f"{self.name} returned a non-JSON body") from error
                if not isinstance(data, Mapping):
                    raise DeciderUnavailable(f"{self.name} returned a body that is not an object")
                funds.clear(self._scope)
                return data
            error = _error(response)
            said = {error.get("code"), error.get("type")}
            if response.status_code == OUT_OF_FUNDS or said & QUOTA_CODES:
                status = response.status_code
                funds.trip(self._scope, self.name, status, str(error.get("message") or "")[:300])
                raise DeciderOutOfFunds(
                    f"{self.name} did not answer: HTTP {status} (out of quota)", status
                )
            reason = "; ".join(str(v)[:200] for v in (error.get("code"), error.get("message")) if v)
            last = f"HTTP {response.status_code}" + (f" ({reason})" if reason else "")
            # Only a rate limit is retried: a 5xx may have been billed, and is not repeated.
            if response.status_code != RATE_LIMITED or attempt == MAX_RETRIES:
                break
            wait = _retry_after(response)
            if wait is None:
                wait = BASE_WAIT_S * (2**attempt)
            if wait > MAX_WAIT_S:
                last += f"; Retry-After {wait:g} s"
                break
            await asyncio.sleep(wait)
        raise DeciderUnavailable(f"{self.name} did not answer: {last}")


def _retry_after(response: Any) -> float | None:
    """The seconds a 429's `Retry-After` header asks for, if it is a finite number."""
    headers = getattr(response, "headers", None) or {}
    value = as_number(headers.get("retry-after")) if hasattr(headers, "get") else None
    return value if value is not None and value >= 0 else None


def _answers(raw: Any, questions: Mapping[str, Question]) -> dict[str, Answer]:
    """Answers come in the order asked, each echoing its name. A list where no answer has a
    name is read by position only when it is exactly as long as the questions; a refusal, an
    unreadable answer or one of the wrong kind is left out, so the policy uses its default."""
    keys = list(questions)
    if isinstance(raw, Mapping):
        named = [(str(k), v) for k, v in raw.items()]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        items = [item for item in raw if isinstance(item, Mapping)]
        if any(item.get("name") for item in items):
            named = [(str(item.get("name") or ""), item) for item in items]
        elif len(items) == len(keys):
            named = list(zip(keys, items, strict=True))
        else:
            named = []
    else:
        named = []
    out: dict[str, Answer] = {}
    for name, item in named:
        if name in questions and isinstance(item, Mapping):
            answer = from_wire(item, questions[name])
            if answer is not None:
                out[name] = answer
    return out


def _error(response: Any) -> Mapping[str, Any]:
    """An OpenAI error body is `{"error": {"message", "type", "code"}}`."""
    try:
        body = response.json()
    except (ValueError, AttributeError):
        return {}
    error = body.get("error") if isinstance(body, Mapping) else None
    return error if isinstance(error, Mapping) else {}


def openai_decisions(
    api_key: str | None = None,
    *,
    max_usd: float | None = None,
    ledger_path: str | Path | None = None,
    **client_options: Any,
) -> CappedDecider:
    """The Decisions API behind the machine's shared ledger: what `create("openai-decisions")`
    returns. `max_usd` (else `SANCHOPANZA_OPENAI_DECISIONS_MAX_USD`, else 0.50) is the ledger's
    total across every process; 0 refuses every call. `client_options` go to the client."""
    cap = max_usd_from_env() if max_usd is None else max_usd
    if not (math.isfinite(cap) and cap >= 0):
        raise ValueError("max_usd must be a non-negative, finite number of dollars")
    if cap == 0:
        raise DeciderUnavailable(f"{BATCH}: the spending cap is 0 USD (not built)")
    client = OpenAIDecisionsClient(api_key, **client_options)
    ledger = SpendLedger(ledger_path or ledger_path_from_env(), cap_usd=cap)
    price = client.price_per_mtok

    def estimate(state: State, questions: Mapping[str, Question]) -> float:
        return estimate_usd(state, questions, price_per_mtok=price)

    return CappedDecider(
        client, ledger=ledger, batch=BATCH, max_usd=cap, price_per_mtok=price, estimate=estimate
    )
