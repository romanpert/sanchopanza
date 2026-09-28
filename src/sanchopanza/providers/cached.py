"""`CachedDecider`: the same question, answered once within a time window.

The provider this package was measured against is not deterministic: the same state, asked
again of the same pinned version, moved by up to 0.09 within a day. Inside one job that means
a decision near its cut can come out one way on the first ask and the other way on the
second, and both are paid. Wrapped, a repeat inside `ttl_seconds` returns the first answer,
identically and for free.

What it does not do: it does not make the provider deterministic. After the TTL the question
is asked again and may come back different; two processes without a shared `path` each ask
once. Choosing a TTL is choosing how long an answer is allowed to stand for the question.

The key is the decision point, the state and the questions (canonical JSON, keys sorted), the
order in which each question lists its options (the order the model sees moved answers), and
the provider's name and model. A decision that failed, answered nothing, answered only some of
the questions, or answered a number no threshold can use is never stored. A hit comes back
with cost, tokens and latency at zero and `@cache` after the provider's name, so a journal
never counts it as a paid call.

The optional store on disk is JSON lines holding the key (a hash) and the answers (numbers):
the text the agent read is not copied to it.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from ..contract import Answer, Decider, Decision, Question, State
from .recorded import order_of

SUFFIX = "@cache"
NUL = "\x00"


@dataclass(frozen=True, slots=True)
class _Entry:
    stored_at: float
    decision: Decision


def _decision_to_dict(decision: Decision) -> dict[str, Any]:
    return {
        "point": decision.point,
        "provider": decision.provider,
        "model": decision.model,
        "answers": {k: a.to_dict() for k, a in decision.answers.items()},
    }


def _decision_from_dict(raw: Mapping[str, Any]) -> Decision:
    return Decision(
        point=str(raw["point"]),
        answers={k: Answer.from_dict(v) for k, v in dict(raw["answers"]).items()},
        provider=str(raw["provider"]),
        model=str(raw["model"]),
    )


def _complete(decision: Decision, questions: Mapping[str, Question]) -> bool:
    if decision.failed or not decision.answers:
        return False
    return all(k in decision.answers and not decision.answers[k].empty for k in questions)


class CachedDecider:
    """Wraps any `Decider`; a repeat inside the TTL is answered from memory (or disk)."""

    def __init__(
        self,
        inner: Decider,
        *,
        ttl_seconds: float = 3600.0,
        path: Path | str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not ttl_seconds > 0:
            raise ValueError("ttl_seconds must be positive")
        self._inner = inner
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._path = Path(path) if path is not None else None
        self.name = f"cached({inner.name})"
        self.accepts_attachments = getattr(inner, "accepts_attachments", False)
        self.hits = 0
        self.skipped = 0
        self._entries: Mapping[str, _Entry] = self._load()

    def _model(self) -> str:
        inner = self._inner
        return str(getattr(inner, "model", None) or getattr(inner, "_model", None) or "")

    def _key(self, point: str, state: State, questions: Mapping[str, Question]) -> str:
        body = {
            "provider": self._inner.name,
            "model": self._model(),
            "point": point,
            "state": state,
            "questions": {k: asdict(q) for k, q in questions.items()},
            "order": order_of(questions),
        }
        serialized = json.dumps(body, sort_keys=True, ensure_ascii=False, default=repr)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _load(self) -> Mapping[str, _Entry]:
        if self._path is None or not self._path.exists():
            return {}
        entries: dict[str, _Entry] = {}
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            line = raw.replace(NUL, "").strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                entry = _Entry(float(row["stored_at"]), _decision_from_dict(row["decision"]))
            except (ValueError, KeyError, TypeError):
                self.skipped += 1
                continue
            entries[str(row["key"])] = entry  # a later line for the same key wins
        return entries

    def _store(self, key: str, entry: _Entry) -> None:
        self._entries = {**self._entries, key: entry}
        if self._path is None:
            return
        row = {
            "key": key,
            "stored_at": entry.stored_at,
            "decision": _decision_to_dict(entry.decision),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        key = self._key(point, state, questions)
        now = self._clock()
        found = self._entries.get(key)
        if found is not None and now - found.stored_at < self._ttl:
            self.hits += 1
            return replace(
                found.decision,
                provider=found.decision.provider + SUFFIX,
                input_tokens=0,
                cost_usd=0.0,
                latency_ms=0,
            )
        decision = await self._inner.decide(point, state, questions)  # unavailable: raises
        if _complete(decision, questions):
            self._store(key, _Entry(now, decision))
        return decision
