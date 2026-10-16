"""The A3 replay's deciders: recorded first, live second, capped, and stopped dead (replay.py).

- `Answers`: answers.jsonl first (hashed keys and numbers, no text), the live decider second; a
  live answer is written down only when it is usable (`usable_p`).
- `Tap`: notes every decision of the event being judged, failures and unusable answers included,
  so a call without an answer is never scored as "not flagged" by mistake.
- `StopDead`: stops the run at a cap refusal, an outage, another model, or MAX_FAILURES failed
  or unusable answers in a row; every later call is refused unasked.
- `Estimate` and `Gate`: the dry run (no call).
- `load_key`: TYPESAFE_API_KEY from the file SANCHOPANZA_KEYS_ENV names, inside the process.
"""

from __future__ import annotations

import contextvars
import json
import math
import os
import pathlib
import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from sanchopanza.contract import Answer, DeciderUnavailable, Decision
from sanchopanza.providers.recorded import key_of, order_of

MODEL = "jev-1.13.0"
PRICE_PER_MTOK = 0.042
TIMEOUT_S = 20.0
MAX_FAILURES = 3
STOP_STATUSES = frozenset({401, 402, 403, 429})
CAP, PAUSE = "cap", "pause"
HALTED: list[str] = []
TAPPED: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "a3_tapped", default=None
)


def usable_p(decision: Decision) -> float | None:
    """The decision's first probability when it is a number in [0, 1], else None."""
    if decision.failed or not decision.answers:
        return None
    p = next(iter(decision.answers.values())).truth
    if p is None or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
        return None
    return float(p)


class Answers:
    """Recorded first (answers.jsonl, then this run's), `live` second. Without `live` a miss is an
    empty decision: the hook fails open and the row says so."""

    def __init__(self, path: pathlib.Path, live: Any = None) -> None:
        self.name, self.model, self._path, self._live = "jev", MODEL, path, live
        self._known: dict[tuple[str, str], Decision] = {}
        self.seen: set[tuple[str, str]] = set()  # every question asked of it, recorded or not
        self.asked = 0
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        for line in filter(None, lines):
            row = json.loads(line)
            decision = _decision_of(row)
            if row.get("model") == MODEL and usable_p(decision) is not None:
                self._known[(row["key"], row["order"])] = decision

    def __len__(self) -> int:
        return len(self._known)

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        slot = (key_of(point, state, questions, MODEL), order_of(questions))
        self.seen.add(slot)
        if slot in self._known:
            return replace(self._known[slot], provider="recorded", cost_usd=0.0, latency_ms=0)
        if self._live is None:
            return Decision(point, {}, "recorded", "-", error="not recorded")
        self.asked += 1
        decision = await self._live.decide(point, state, questions)
        if usable_p(decision) is not None:
            self._known[slot] = decision
            self._write(slot, point, decision)
        return decision

    def _write(self, slot: tuple[str, str], point: str, decision: Decision) -> None:
        row = {"key": slot[0], "order": slot[1], "point": point, "model": decision.model,
               "default": False, "input_tokens": decision.input_tokens,
               "cost_usd": decision.cost_usd, "latency_ms": decision.latency_ms,
               "answers": {k: a.to_dict() for k, a in decision.answers.items()}}  # fmt: skip
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row) + "\n")


def _decision_of(row: Mapping[str, Any]) -> Decision:
    answers = {k: Answer.from_dict(v) for k, v in (row.get("answers") or {}).items()}
    return Decision(str(row.get("point")), answers, "recorded", str(row.get("model")),
                    input_tokens=int(row.get("input_tokens") or 0),
                    cost_usd=float(row.get("cost_usd") or 0.0))  # fmt: skip


class Tap:
    """Notes every decision of the event being judged (TAPPED) and passes it on: an exception
    is noted and raised again, an answer without a usable p is noted as "empty answer"."""

    def __init__(self, inner: Any) -> None:
        self._inner, self.name, self.model = inner, inner.name, MODEL

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        seen = TAPPED.get()
        try:
            decision = await self._inner.decide(point, state, questions)
        except Exception as error:
            if seen is not None:
                seen.append({"point": point, "p": None, "model": "-",
                             "error": f"{type(error).__name__}: {str(error)[:200]}"})  # fmt: skip
            raise
        if seen is not None:
            p = usable_p(decision)
            error = decision.error or (None if p is not None else "empty answer")
            seen.append({"point": point, "p": p, "model": decision.model, "error": error})
        return decision


class StopDead:
    """A live decider that stops the run dead (HALTED) at a cap refusal, an outage, another
    model, or MAX_FAILURES failed or unusable answers in a row."""

    def __init__(self, inner: Any) -> None:
        self._inner, self.name, self._fails = inner, inner.name, 0

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        from sanchopanza.providers.capped import SpendCapReached

        if HALTED:
            raise DeciderUnavailable(f"halted, not called: {HALTED[0]}")
        try:
            decision = await self._inner.decide(point, state, questions)
        except SpendCapReached as error:
            HALTED.append(f"{CAP}: {error}")
            raise
        except Exception as error:
            self._failed(error)
            raise
        if decision.model != MODEL:
            HALTED.append(f"{PAUSE}: asked {MODEL}, served {decision.model}: not recorded")
            raise DeciderUnavailable(HALTED[-1])
        if usable_p(decision) is None:
            self._failed(RuntimeError(decision.error or "empty answer"))
        else:
            self._fails = 0
        return decision

    def _failed(self, error: Exception) -> None:
        self._fails += 1
        found = re.search(r"HTTP (\d{3})", str(error))
        outage = found and (int(found.group(1)) in STOP_STATUSES or int(found.group(1)) >= 500)
        if (outage or "unreachable" in str(error) or self._fails >= MAX_FAILURES) and not HALTED:
            HALTED.append(f"{PAUSE}: {type(error).__name__}: {str(error)[:200]}")


def live_decider(ledger_path: pathlib.Path, cap_usd: float, batch: str,
                 batch_cap_usd: float | None = None) -> Any:  # fmt: skip
    """Jev under the ledger's `cap_usd` and the batch's own cap (`batch_cap_usd`, else the
    ledger's), stopped dead by `StopDead`."""
    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers import CappedDecider
    from sanchopanza.providers.jev import JevDecider

    ledger = SpendLedger(ledger_path, cap_usd=cap_usd)
    jev = JevDecider(model=MODEL, timeout_s=TIMEOUT_S, long_context=False, images=False)
    batch_cap = cap_usd if batch_cap_usd is None else batch_cap_usd
    return StopDead(CappedDecider(jev, ledger=ledger, batch=batch, max_usd=batch_cap,
                                  price_per_mtok=PRICE_PER_MTOK))  # fmt: skip


class Estimate:
    """Dry: asks nothing; notes what each distinct call would send and its price three ways
    (a question both arms ask is paid once: `Answers` keeps the first answer)."""

    def __init__(self, fit: tuple[float, float]) -> None:
        self.name, self.model, self.calls, self._fit = "dry", MODEL, [], fit
        self._seen: set[tuple[str, str]] = set()

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        from sanchopanza.providers.capped import estimate_usd

        slot = (key_of(point, state, questions, MODEL), order_of(questions))
        if slot in self._seen:
            return Decision(point, {}, "dry", "-", error="dry run: asked already")
        self._seen.add(slot)
        chars = len(str(state.get("record") or state.get("command") or ""))
        tokens = self._fit[0] + self._fit[1] * chars
        self.calls.append({"point": point, "chars": chars,
                           "reserve_usd": estimate_usd(state, questions,
                                                       price_per_mtok=PRICE_PER_MTOK),
                           "fit_usd": tokens * PRICE_PER_MTOK / 1e6})  # fmt: skip
        return Decision(point, {}, "dry", "-", error="dry run: not asked")


class Gate:
    """Recorded answers first; the rest to `fallback` (the estimator, in a dry run)."""

    def __init__(self, recorded: Answers, fallback: Any) -> None:
        self._recorded, self._fallback, self.name, self.model = recorded, fallback, "jev", MODEL

    @property
    def seen(self) -> set[tuple[str, str]]:
        """Every question asked of it: the recorded answers' (the disjoint check reads it)."""
        return self._recorded.seen

    @seen.setter
    def seen(self, value: set[tuple[str, str]]) -> None:
        self._recorded.seen = value

    async def decide(self, point: str, state: Any, questions: Mapping[str, Any]) -> Decision:
        decision = await self._recorded.decide(point, state, questions)
        if decision.answers:
            return decision
        return await self._fallback.decide(point, state, questions)


def load_key() -> None:
    """TYPESAFE_API_KEY into this process from the file SANCHOPANZA_KEYS_ENV names, when unset.
    Never printed. (Lot L4's `load_key`, copied so the sealed code is all it runs.)"""
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    named = os.environ.get("SANCHOPANZA_KEYS_ENV", "")
    if not named or not pathlib.Path(named).is_file():
        raise SystemExit("TYPESAFE_API_KEY unset and SANCHOPANZA_KEYS_ENV names no file")
    for line in pathlib.Path(named).read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition("=")
        if name.strip() == "TYPESAFE_API_KEY" and value.strip():
            os.environ["TYPESAFE_API_KEY"] = value.strip().strip('"').strip("'")
            return
    raise SystemExit("no TYPESAFE_API_KEY line in the file SANCHOPANZA_KEYS_ENV names")
