"""TypeSafe Jev over its native HTTP API. One file, no SDK: the wire format fits in 60 lines.

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer $TYPESAFE_API_KEY
    {"model": "jev-latest", "state": ..., "questions": {id: {"type", "instructions", "criteria"}}}

Price (2026-09): 0.042 USD per million input tokens, output free. The price is a
constructor argument, not a constant, so a change is configuration, not code.
The model defaults to a pinned version rather than an alias: see DEFAULT_MODEL.
`SANCHOPANZA_JEV_MODEL` names another one without touching code (`jev-1.14.0`, say).
Two optional "Danger Zone" headers, by argument or by environment, on 1.13 and 1.14 alike:
`long_context` (`SANCHOPANZA_JEV_LONG_CONTEXT=1`) raises the limit from 64k tokens per
request and 32k per question to 262k, "slower and less accurate" by the vendor's own word;
`images` (`SANCHOPANZA_JEV_IMAGES=1`) lets the state carry PNG or JPEG images
(`providers.jev_assets`). Without the first, a longer state is a 400 `max_tokens_exceeded`,
raised here as `DeciderUnavailable` with that reason.
Retries: 429 and 529 with bounded exponential backoff. No unbounded loops.
Out of funds: a 402 trips a breaker shared by every process (`sanchopanza.funds`); while it is
fresh no call is made, and `preflight()` is the one-cent check a launcher runs before spending.
"""

from __future__ import annotations

import asyncio
import functools
import importlib.util
import math
import os
import time
import warnings
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .. import _env, funds
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
    as_box,
    as_number,
    truth_confidence,
    usable,
)
from ..media import attachments_in
from . import jev_assets, jev_models

BASE_URL = "https://api.typesafe.ai"
PATH = "/v1/systemone"
# **Pinned, not an alias, and the vendor says to pin.** Their own model page: "An alias
# moves when a new release ships, so the answers behind it can change without a change on
# your side... If you have tuned confidence thresholds against a specific version, pin
# that version's ID instead of the alias and move to the new one on your own schedule."
# This package is nothing but tuned thresholds, and a non-generative model gives no
# "the output looks odd" signal when it moves: no error, no failing test, no log line.
# This is the version every number in docs/paper.md was measured against. Pass
# `model="jev-latest"` deliberately if you want to track the alias.
DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_PRICE_PER_MTOK = 0.042
LONG_CONTEXT_HEADER = "TypeSafe-Danger-Zone-Long-Context"
IMAGES_HEADER = "TypeSafe-Danger-Zone-Images"
MAX_TOKENS_EXCEEDED = "max_tokens_exceeded"
REFUSED = 400
_ON = frozenset({"1", "true", "yes", "on"})

KIND_TO_WIRE = {"choice": "choice", "score": "score", "truth": "noul", "box": "box"}
WIRE_TO_KIND = {v: k for k, v in KIND_TO_WIRE.items()}
RETRYABLE = frozenset({429, 529})
OUT_OF_FUNDS = 402
REFUSED_AUTH = frozenset({401, 403})
MAX_RETRIES = 3
BASE_WAIT_S = 0.25


def model_from_env(env: Mapping[str, str] | None = None) -> str:
    """`SANCHOPANZA_JEV_MODEL` (or the legacy `SANCHO_JEV_MODEL`), else `DEFAULT_MODEL`."""
    return _env.get("JEV_MODEL", "", env=env).strip() or DEFAULT_MODEL


def _flag(name: str, env: Mapping[str, str] | None) -> bool:
    return _env.get(name, "", env=env).strip().lower() in _ON


def long_context_from_env(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_JEV_LONG_CONTEXT` set to 1, true, yes or on."""
    return _flag("JEV_LONG_CONTEXT", env)


def images_from_env(env: Mapping[str, str] | None = None) -> bool:
    """`SANCHOPANZA_JEV_IMAGES` set to 1, true, yes or on."""
    return _flag("JEV_IMAGES", env)


def to_wire(question: Question) -> dict[str, Any]:
    """Contract question to TypeSafe request format."""
    if isinstance(question, Choice):
        return {
            "type": "choice",
            "instructions": question.instructions,
            "criteria": dict(question.options),
        }
    if isinstance(question, Score):
        return {
            "type": "score",
            "instructions": question.instructions,
            "criteria": list(question.levels),
        }
    if isinstance(question, Truth):
        body: dict[str, Any] = {"type": "noul", "instructions": question.instructions}
        if question.criteria:
            body["criteria"] = dict(question.criteria)
        return body
    if isinstance(question, Box):
        return {"type": "box", "instructions": question.instructions}
    raise TypeError(f"unknown question type: {type(question)!r}")


def truth_wire_confidence_differs(raw: Mapping[str, Any], truth: float | None) -> bool:
    """Whether the provider sent its own confidence for a Truth answer, other than |2p - 1|.

    The Truth wire carries only `noul`; the confidence of a yes/no is computed here
    (`truth_confidence`), so every recording in this repository shows confidence = |2p - 1|
    by construction, not because the provider says so. Should the provider start sending a
    Truth confidence that carries information the probability does not, the answer still uses
    ours (every threshold was set against it), and `from_wire` says so once.
    """
    given = as_number(raw.get("confidence"))
    return given is not None and truth is not None and abs(given - truth_confidence(truth)) > 1e-6


@functools.cache
def _warn_truth_wire_confidence() -> None:
    warnings.warn(
        "Jev sent a confidence for a Truth answer that differs from |2p - 1|; sanchopanza "
        "ignores it. Policies that ask for both p and confidence may deserve a second look.",
        RuntimeWarning,
        stacklevel=3,
    )


def from_wire(raw: Mapping[str, Any]) -> Answer:
    """TypeSafe answer to contract. Tolerates missing fields.

    httpx's JSON parser accepts NaN and Infinity, and so does `float()`. A value that is not
    a finite number (or a probability outside [0, 1]) comes back as an empty answer, the
    same as a missing one: it must never reach a threshold, where NaN reads as permission.
    """
    kind = WIRE_TO_KIND.get(str(raw.get("type", "")), "truth")
    probabilities = {str(k): _required(v) for k, v in (raw.get("probabilities") or {}).items()}
    if kind == "truth":
        truth = as_number(raw.get("noul"))
        if truth_wire_confidence_differs(raw, truth):
            _warn_truth_wire_confidence()
        return usable(
            Answer(
                kind="truth",
                confidence=truth_confidence(truth) if truth is not None else 0.0,
                truth=truth,
            )
        )
    if kind == "box":
        # No confidence on the wire is no answer: a box always comes back, even for a thing
        # the image does not show, so its confidence is the least a caller can need.
        return usable(
            Answer(kind="box", confidence=_required(raw.get("confidence")),
                   box=as_box(raw.get("box")))
        )  # fmt: skip
    confidence = _required(raw.get("confidence") or 0.0)
    if kind == "choice":
        chosen = raw.get("choice")
        return usable(
            Answer(
                kind="choice",
                confidence=confidence,
                choice=str(chosen) if chosen is not None else None,
                probabilities=probabilities,
            )
        )
    return usable(
        Answer(
            kind="score",
            confidence=confidence,
            score=as_number(raw.get("score")),
            probabilities=probabilities,
        )
    )


def _required(value: Any) -> float:
    """A number the wire must carry: missing or unparseable is NaN, which `usable` rejects."""
    number = as_number(value)
    return math.nan if number is None else number


class JevDecider:
    """Async client for Jev. One instance per job; it reuses the connection."""

    name = "jev"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = BASE_URL,
        model: str | None = None,
        price_per_mtok: float = DEFAULT_PRICE_PER_MTOK,
        timeout_s: float = 10.0,
        client: Any | None = None,
        long_context: bool | None = None,
        images: bool | None = None,
    ) -> None:
        """`model`, `long_context` and `images` left at None come from the environment
        (`model_from_env`, `long_context_from_env`, `images_from_env`); a value given wins."""
        key = api_key or os.environ.get("TYPESAFE_API_KEY", "")
        if not key:
            raise DeciderUnavailable("TYPESAFE_API_KEY is not set")
        if client is None and importlib.util.find_spec("httpx") is None:  # pragma: no cover
            raise DeciderUnavailable("install sanchopanza[jev] to use the Jev provider")
        self._model = model or model_from_env()
        self._long_context = long_context_from_env() if long_context is None else long_context
        self._images = images_from_env() if images is None else images
        self.accepts_attachments = self._images
        self._price = price_per_mtok
        self._key, self._base_url, self._timeout_s = key, base_url.rstrip("/"), timeout_s
        # Built on the first question, not here: importing httpx and loading the CA bundle took
        # 0.6 s, and a hook builds its decider on every shell command while it asks on 2 % of
        # them (the adoption study's phase B: 1.3-1.7 s per PreToolUse with a key, 0.4 s without).
        self._made: Any | None = client
        self._scope = funds.scope(self._base_url, key)

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

    @property
    def model(self) -> str:
        return self._model

    @property
    def long_context(self) -> bool:
        return self._long_context

    @property
    def images(self) -> bool:
        return self._images

    def _headers(self) -> dict[str, str]:
        """The Danger Zone headers this decider was built with, sent on every request."""
        on = ((LONG_CONTEXT_HEADER, self._long_context), (IMAGES_HEADER, self._images))
        return {name: "true" for name, wanted in on if wanted}

    accepts_attachments = False

    def _body(self, state: State, questions: Mapping[str, Question]) -> dict[str, Any]:
        """The request: model, state, questions, and `assets` when the state holds images."""
        if _has_box(questions) and jev_models.supports_box(self._model) is False:
            raise DeciderUnavailable(
                f"Box needs jev-1.14.0 or later and this decider asks {self._model}, which "
                "answers it with HTTP 400: set model= or SANCHOPANZA_JEV_MODEL (not sent)"
            )
        found = attachments_in(state)
        if found and not self._images:
            # Refuse loudly. The alternative, sending the state with the attachment stripped
            # out, returns a confident answer to a question about something the model never
            # saw, which is worse than no answer: the squire's fail-open turns this into the
            # harness default and journals the reason. Turn images on, route the point to a
            # provider that reads them (RoutedDecider) or put one in front (FallbackDecider).
            kinds = ", ".join(sorted({a.media_type for a in found}))
            raise DeciderUnavailable(
                f"this decider was built for text only and the state carries {len(found)} "
                f"attachment(s) ({kinds}); Jev reads PNG and JPEG behind its Danger Zone "
                "header: images=True or SANCHOPANZA_JEV_IMAGES=1"
            )
        assets: dict[str, Any] = {}
        if found:
            state, assets = jev_assets.to_assets(state)
        body: dict[str, Any] = {
            "model": self._model,
            "state": state,
            "questions": {key: to_wire(q) for key, q in questions.items()},
        }
        return {**body, "assets": assets} if assets else body

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        body = self._body(state, questions)
        trip = funds.tripped(self._scope)
        if trip is not None:
            raise DeciderOutOfFunds(
                # Same prefix as a real 402: launchers grep for "did not answer: HTTP 40[123]".
                f"{self.name} did not answer: HTTP {trip.get('status', OUT_OF_FUNDS)} (out of "
                "funds; breaker open, not called)",
                int(trip.get("status") or OUT_OF_FUNDS),
            )
        start = time.monotonic()
        data = await self._send(body)
        latency_ms = int((time.monotonic() - start) * 1000)
        answers = {key: from_wire(value) for key, value in (data.get("answers") or {}).items()}
        tokens = int((data.get("usage") or {}).get("input_tokens") or 0)
        return Decision(
            point=point,
            answers=answers,
            provider=self.name,
            model=str(data.get("model") or self._model),
            input_tokens=tokens,
            cost_usd=tokens * self._price / 1_000_000,
            latency_ms=latency_ms,
        )

    async def _send(self, body: dict[str, Any]) -> dict[str, Any]:
        last = "no response"
        self.last_status: int | None = None
        for attempt in range(MAX_RETRIES + 1):
            client = self._client()
            import httpx

            headers = self._headers()
            try:
                if headers:
                    response = await client.post(PATH, json=body, headers=headers)
                else:
                    response = await client.post(PATH, json=body)
                self.last_status = response.status_code
            except httpx.HTTPError as error:
                raise DeciderUnavailable(f"jev unreachable: {error.__class__.__name__}") from error
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as error:
                    raise DeciderUnavailable("jev returned a non-JSON body") from error
                funds.clear(self._scope)
                return data
            if response.status_code == OUT_OF_FUNDS:
                detail = response.text[:300] if hasattr(response, "text") else ""
                funds.trip(self._scope, self.name, OUT_OF_FUNDS, detail)
                raise DeciderOutOfFunds(f"{self.name} did not answer: HTTP 402 (out of funds)")
            if response.status_code == REFUSED:
                raise DeciderUnavailable(self._refusal(response, body))
            last = f"HTTP {response.status_code}"
            if response.status_code not in RETRYABLE or attempt == MAX_RETRIES:
                break
            await asyncio.sleep(BASE_WAIT_S * (2**attempt))
        raise DeciderUnavailable(f"jev did not answer: {last}")

    def _refusal(self, response: Any, body: Mapping[str, Any]) -> str:
        """Why a 400 came back, from the body's `detail`, in words a journal can act on."""
        detail = _detail(response)
        kind = str(detail.get("error_type") or "")
        if kind == MAX_TOKENS_EXCEEDED:
            if self._long_context:
                return (
                    "jev did not answer: HTTP 400 max_tokens_exceeded (the state is over "
                    "262k tokens even with long context on; cut it or split the call)"
                )
            return ("jev did not answer: HTTP 400 max_tokens_exceeded (over 64k tokens per "
                    "request or 32k per question; long_context=True or "
                    "SANCHOPANZA_JEV_LONG_CONTEXT=1 raises both to 262k)")  # fmt: skip
        said = "; ".join(str(v)[:200] for v in (kind, detail.get("message")) if v)
        asks_box = any(q.get("type") == "box" for q in (body.get("questions") or {}).values())
        if asks_box:  # 1.13 answers a Box with a bare "Invalid request."
            said = "; ".join(x for x in (said, f"Box needs jev-1.14.0 or later; "
                                               f"{self._model} may not be") if x)  # fmt: skip
        return "jev did not answer: HTTP 400" + (f" ({said})" if said else "")


def _has_box(questions: Mapping[str, Question]) -> bool:
    return any(isinstance(q, Box) for q in questions.values())


def _detail(response: Any) -> Mapping[str, Any]:
    """A TypeSafe error body is `{"detail": {"error_type": ..., "message": ...}}`."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return {}
    return detail if isinstance(detail, Mapping) else {}


@dataclass(frozen=True)
class PreflightResult:
    """What a launcher needs before spending: did one real decision come back, and if not why."""

    ok: bool
    reason: str  # ok | no_funds | auth | no_key | unreachable | other
    http_status: int | None
    cost_usd: float
    model: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: `python -m sanchopanza jev-preflight` exits with these. Anything but 0 means: do not launch.
#: From 10 up: argparse exits 2 on a mistyped flag, which must not read as "out of funds".
PREFLIGHT_EXIT = {
    "ok": 0,
    "no_funds": 10,
    "auth": 11,
    "no_key": 12,
    "unreachable": 13,
    "other": 14,
}
PREFLIGHT_STATE = "A launcher checks that the decision service answers before a paid run."
PREFLIGHT_QUESTION = "Is this text about checking that a service answers?"


def _preflight_reason(status: int | None) -> str:
    if status in REFUSED_AUTH:
        return "auth"
    if status is None or status in RETRYABLE or status >= 500:
        return "unreachable"
    return "other"


async def apreflight(
    api_key: str | None = None,
    *,
    timeout_s: float = 15.0,
    base_url: str = BASE_URL,
    model: str | None = None,
    client: Any | None = None,
) -> PreflightResult:
    """One real decision (one Truth, about 300 input tokens, about 13 micro-dollars), past the
    breaker. A 200 with a usable answer clears the breaker; a 402 trips it. Never raises.
    The model is `model`, else the one `SANCHOPANZA_JEV_MODEL` names, else `DEFAULT_MODEL`."""
    model = model or model_from_env()
    try:
        decider = JevDecider(
            api_key, base_url=base_url, model=model, timeout_s=timeout_s, client=client
        )
    except DeciderUnavailable as error:
        reason = "no_key" if "TYPESAFE_API_KEY" in str(error) else "other"
        return PreflightResult(False, reason, None, 0.0, model, str(error))
    body = {
        "model": model,
        "state": PREFLIGHT_STATE,
        "questions": {"ok": to_wire(Truth(PREFLIGHT_QUESTION))},
    }
    try:
        data = await decider._send(body)
    except DeciderOutOfFunds as error:
        return PreflightResult(False, "no_funds", OUT_OF_FUNDS, 0.0, model, str(error))
    except DeciderUnavailable as error:
        status = getattr(decider, "last_status", None)
        return PreflightResult(False, _preflight_reason(status), status, 0.0, model, str(error))
    except Exception as error:  # noqa: BLE001 - a launcher reads the reason, never a traceback
        detail = f"{error.__class__.__name__}: {error}"
        return PreflightResult(False, "other", None, 0.0, model, detail)
    finally:
        if client is None:
            await decider.aclose()
    tokens = int((data.get("usage") or {}).get("input_tokens") or 0)
    cost = tokens * DEFAULT_PRICE_PER_MTOK / 1_000_000
    answer = from_wire((data.get("answers") or {}).get("ok") or {})
    served = str(data.get("model") or model)
    if answer.empty:
        return PreflightResult(False, "other", 200, cost, served, "200 without a usable answer")
    return PreflightResult(True, "ok", 200, cost, served, f"{tokens} input tokens")


def preflight(api_key: str | None = None, **kwargs: Any) -> PreflightResult:
    """`apreflight` for a launcher that is not inside an event loop."""
    return asyncio.run(apreflight(api_key, **kwargs))


CLM_URL = "http://localhost:8000"
CLM_MODEL = "CLM-v0.1-8B"


def clm(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> JevDecider:
    """CLM-8B (Contrastive-LM, Stanford and NVIDIA, Apache-2.0) behind its `clm-serve`, which
    exposes a TypeSafe-compatible endpoint: this is the Jev client pointed at it, not a second
    client. Self-hosted, so no price and no key unless the server asks for one.

    `SANCHOPANZA_CLM_URL` (default http://localhost:8000), `SANCHOPANZA_CLM_MODEL` and
    `CLM_API_KEY` configure it. Tested against a mock of the TypeSafe wire format only: CLM needs
    a Linux machine with an NVIDIA GPU, and no measurement here has used a real CLM server.
    TypeSafe's Danger Zone headers are not sent unless asked for by argument: the
    `SANCHOPANZA_JEV_*` variables are Jev's, not CLM's.
    """
    kwargs = {"long_context": False, "images": False, **kwargs}
    decider = JevDecider(
        api_key or os.environ.get("CLM_API_KEY") or "local",
        base_url=base_url or os.environ.get("SANCHOPANZA_CLM_URL") or CLM_URL,
        model=model or os.environ.get("SANCHOPANZA_CLM_MODEL") or CLM_MODEL,
        price_per_mtok=0.0,
        **kwargs,
    )
    decider.name = "clm"
    return decider
