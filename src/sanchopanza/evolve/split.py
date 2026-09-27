"""Three disjoint case sets, fixed by a hash of each case id before anything is scored.

- `evolve`: what the outer loop may read as often as it likes. It will overfit it.
- `holdout`: read to confirm an admitted candidate. Every read is counted and journaled by the
  `Evaluator`, because re-reading a holdout to choose between candidates turns it into a second
  evolution set (adaptive reuse) - which is how a loop overfits while "validating".
- `fresh`: read once, at the end, for the number that gets published. The `Evaluator` refuses a
  second read.

The assignment is a hash of the case id with a salt, so it is reproducible, independent of
file order, and decided before anyone has seen an outcome: the same property
`Squire._sampled_for_audit` gives the audit sample. It does not stratify by point, so on a
bench of a few hundred cases a small point can land unevenly; `sizes_by_point` says so.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

Part = Literal["evolve", "holdout", "fresh"]
PARTS: tuple[Part, ...] = ("evolve", "holdout", "fresh")
DEFAULT_SALT = "sanchopanza-evolve-v1"
Case = Mapping[str, Any]


def _unit(case_id: str, salt: str) -> float:
    digest = hashlib.blake2b(f"{salt}|{case_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


@dataclass(frozen=True, slots=True)
class Split:
    evolve: tuple[Case, ...]
    holdout: tuple[Case, ...]
    fresh: tuple[Case, ...]

    @classmethod
    def by_hash(
        cls,
        cases: Iterable[Case],
        *,
        holdout: float = 0.25,
        fresh: float = 0.25,
        salt: str = DEFAULT_SALT,
    ) -> Split:
        """Assign each case by `hash(salt, id)`: [0, evolve) | [evolve, +holdout) | rest."""
        if holdout < 0 or fresh < 0 or holdout + fresh >= 1.0:
            raise ValueError("holdout and fresh must be >= 0 and leave a non-empty evolve share")
        cut_evolve = 1.0 - holdout - fresh
        cut_holdout = cut_evolve + holdout
        parts: dict[str, list[Case]] = {p: [] for p in PARTS}
        for case in sorted(cases, key=lambda c: str(c["id"])):
            u = _unit(str(case["id"]), salt)
            part = "evolve" if u < cut_evolve else ("holdout" if u < cut_holdout else "fresh")
            parts[part].append(case)
        return cls(tuple(parts["evolve"]), tuple(parts["holdout"]), tuple(parts["fresh"]))

    def part(self, name: Part) -> tuple[Case, ...]:
        if name not in PARTS:
            raise ValueError(f"unknown split part {name!r}; expected one of {PARTS}")
        return getattr(self, name)

    @property
    def sizes(self) -> tuple[int, int, int]:
        return len(self.evolve), len(self.holdout), len(self.fresh)

    def sizes_by_point(self) -> dict[str, dict[str, int]]:
        return {
            name: dict(Counter(str(c.get("point", "?")) for c in self.part(name))) for name in PARTS
        }
