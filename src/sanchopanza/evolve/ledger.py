"""Append-only ledger of tried hypotheses, so a refuted edit is not proposed again.

One JSON object per line. A hypothesis is the edit set, identified by `edits_hash` (order-free,
and free of the incumbent's value, so "adds_nothing -> 0.45" is the same hypothesis whatever it
was tried against). The incumbent it was tried against is stored beside it, and
`already_refuted(..., incumbent=...)` can scope a refutation to it: an edit that lost against
one incumbent may win against another, and whether to retry it is the loop's choice.

Recording the same trial twice is a no-op, so a loop that crashes and resumes does not
double-count. Nothing is ever rewritten or deleted.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .knobs import Edit, edits_hash

VERDICTS: frozenset[str] = frozenset({"admitted", "refuted", "leak", "invalid"})


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    hypothesis: str
    edits: tuple[Mapping[str, Any], ...]
    incumbent: str
    part: str
    candidate: float
    incumbent_score: float
    delta: float
    verdict: str
    reasons: tuple[str, ...]
    round: int | None = None
    ts: str = ""

    @property
    def identity(self) -> tuple[Any, ...]:
        return (
            self.hypothesis,
            self.incumbent,
            self.part,
            self.verdict,
            round(self.candidate, 9),
            round(self.incumbent_score, 9),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "edits": [dict(e) for e in self.edits],
            "incumbent": self.incumbent,
            "part": self.part,
            "candidate": self.candidate,
            "incumbent_score": self.incumbent_score,
            "delta": self.delta,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "round": self.round,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LedgerEntry:
        return cls(
            hypothesis=str(raw["hypothesis"]),
            edits=tuple(dict(e) for e in raw.get("edits") or ()),
            incumbent=str(raw.get("incumbent", "")),
            part=str(raw.get("part", "")),
            candidate=float(raw.get("candidate", 0.0)),
            incumbent_score=float(raw.get("incumbent_score", 0.0)),
            delta=float(raw.get("delta", 0.0)),
            verdict=str(raw.get("verdict", "")),
            reasons=tuple(raw.get("reasons") or ()),
            round=raw.get("round"),
            ts=str(raw.get("ts", "")),
        )


class Ledger:
    """In memory when `path` is None; otherwise backed by an append-only JSONL file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._entries: tuple[LedgerEntry, ...] = self._load()

    def _load(self) -> tuple[LedgerEntry, ...]:
        if self._path is None or not self._path.exists():
            return ()
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return tuple(LedgerEntry.from_dict(json.loads(line)) for line in lines if line.strip())

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return self._entries

    def record(
        self,
        edits: Iterable[Edit],
        *,
        incumbent: str,
        part: str,
        candidate: float,
        incumbent_score: float,
        delta: float,
        verdict: str,
        reasons: Iterable[str] = (),
        round: int | None = None,  # noqa: A002 - the loop's own word for it
    ) -> bool:
        """Append one trial. Returns False, writing nothing, if the same trial is on record."""
        if verdict not in VERDICTS:
            raise ValueError(f"unknown verdict {verdict!r}; expected one of {sorted(VERDICTS)}")
        edit_list = list(edits)
        entry = LedgerEntry(
            hypothesis=edits_hash(edit_list),
            edits=tuple(e.to_dict() for e in edit_list),
            incumbent=incumbent,
            part=part,
            candidate=candidate,
            incumbent_score=incumbent_score,
            delta=delta,
            verdict=verdict,
            reasons=tuple(reasons),
            round=round,
            ts=datetime.now(UTC).isoformat(),
        )
        if any(e.identity == entry.identity for e in self._entries):
            return False
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        self._entries = (*self._entries, entry)
        return True

    def already_refuted(self, edits: Iterable[Edit], *, incumbent: str | None = None) -> bool:
        """True if this edit set was refuted (or rejected as a leak), optionally against
        `incumbent` only."""
        hypothesis = edits_hash(edits)
        return any(
            e.hypothesis == hypothesis
            and e.verdict in ("refuted", "leak")
            and (incumbent is None or e.incumbent == incumbent)
            for e in self._entries
        )
