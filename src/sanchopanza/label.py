"""Label a corpus: one closed question applied to every row, as columns code can use.

The judgment is `Squire.classify`, the measured closed-vocabulary point: one Choice per item
over the rubric's options, accepted at `Thresholds.classify` on the chosen option's
probability. This module adds what a corpus needs around it:

- **Files in, files out.** `.jsonl` (`key`/`id`, `text`, optional `context`), `.csv` (the same
  columns) or `.txt` (one item per line). Out: `.jsonl` or `.csv` with `label` (empty when the
  item abstained), `p` (probability of the chosen option), `margin` (its lead over the
  runner-up), `provider` and `reason`.
- **A cache with an age.** The same text under the same rubric and provider is not paid twice
  within `max_age_days` (default 30). The key covers the rubric's fingerprint, so editing an
  option is a new cache.
- **A budget.** The squire's meter (`Thresholds.max_usd`, `max_decisions`) stops spending; the
  rows it could not pay for come back unlabelled with `reason: budget`, never guessed.
- **Escalation, optional.** Put a `providers.chain.CascadeDecider` behind the squire and the
  items the cheap model is unsure of go to the expensive one; `provider` says which paid.

Measured on public labelled sets in `docs/results/2026-09-30-label/`.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .points import entities

DAY_S = 86_400.0


@dataclass(frozen=True, slots=True)
class Rubric:
    """What is labelled and the closed set of labels, each with its description."""

    field: str
    options: Mapping[str, str]
    context: str = ""
    add_other: bool = True

    def __post_init__(self) -> None:
        if not self.field.strip():
            raise ValueError("a rubric needs a field: what is being labelled")
        if len(self.options) < 2:
            raise ValueError("a rubric needs at least two labels")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Rubric:
        options = raw.get("options") or raw.get("labels")
        if isinstance(options, Sequence) and not isinstance(options, str | Mapping):
            options = {str(o): str(o) for o in options}
        if not isinstance(options, Mapping):
            raise ValueError("rubric options must be a mapping of label to description")
        return cls(
            field=str(raw.get("field", "")),
            options={str(k): str(v) for k, v in options.items()},
            context=str(raw.get("context", "")),
            add_other=bool(raw.get("add_other", True)),
        )

    @classmethod
    def load(cls, path: str | Path) -> Rubric:
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))

    def fingerprint(self) -> str:
        blob = json.dumps(
            [self.field, dict(self.options), self.context, self.add_other],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Item:
    key: str
    text: str
    context: str = ""


@dataclass(frozen=True, slots=True)
class Row:
    key: str
    label: str | None
    p: float
    margin: float
    provider: str
    reason: str = ""
    probabilities: Mapping[str, float] = field(default_factory=dict)
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["probabilities"] = dict(self.probabilities)
        return out


def margin_of(probabilities: Mapping[str, float]) -> float:
    """The winning option's lead over the runner-up. 0 with fewer than two options."""
    ranked = sorted(probabilities.values(), reverse=True)
    return ranked[0] - ranked[1] if len(ranked) > 1 else 0.0


# --- the cache ------------------------------------------------------------------------------


class LabelCache:
    """Answered items on disk, one JSON line each; an entry older than `max_age_days` is stale."""

    def __init__(self, path: str | Path, *, max_age_days: float = 30.0) -> None:
        self.path = Path(path)
        self.max_age_s = max_age_days * DAY_S
        self._rows: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    self._rows[row["key"]] = row
                except (ValueError, KeyError, TypeError):
                    continue  # a torn line loses one answer, never the file

    @staticmethod
    def key(provider: str, rubric: Rubric, item: Item) -> str:
        blob = json.dumps([provider, rubric.fingerprint(), item.text, item.context])
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str, *, now: float | None = None) -> Row | None:
        row = self._rows.get(key)
        if row is None:
            return None
        if (now if now is not None else time.time()) - float(row.get("at", 0)) > self.max_age_s:
            return None
        return Row(**{**row["row"], "cached": True})

    def put(self, key: str, row: Row, *, now: float | None = None) -> None:
        entry = {"key": key, "at": now if now is not None else time.time(), "row": row.to_dict()}
        self._rows[key] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- labelling ------------------------------------------------------------------------------


async def label_one(squire: Any, rubric: Rubric, item: Item) -> Row:
    """One item, `Squire.classify`'s question and policy, keeping which provider answered (in
    a cascade, the stage that paid). Never raises: a failure is an unlabelled row."""
    if squire.exhausted:
        return Row(item.key, None, 0.0, 0.0, "budget", "budget")
    try:
        state, qs = entities.classification_questions(
            field=rubric.field,
            text=item.text,
            options=rubric.options,
            context=" ".join(part for part in (rubric.context, item.context) if part),
            add_other=rubric.add_other,
        )
        decision = await squire.decide("classify", state, qs)
        category, p, dist = entities.decide_classification(
            decision, squire.thresholds, options=rubric.options
        )
        squire.record(decision, field=rubric.field, category=category, probability=p)
    except Exception as error:  # noqa: BLE001 - one bad item must not stop a corpus
        return Row(item.key, None, 0.0, 0.0, "error", f"error: {error.__class__.__name__}")
    provider = decision.provider
    if decision.error == "budget exhausted":
        return Row(item.key, None, 0.0, 0.0, "budget", "budget")
    if not dist:
        return Row(item.key, None, 0.0, 0.0, provider, "no answer")
    margin = margin_of(dist)
    if category is None:
        top = max(dist, key=lambda k: dist[k])
        reason = "other" if top not in rubric.options else "below threshold"
        return Row(item.key, None, p, margin, provider, reason, dist)
    return Row(item.key, category, p, margin, provider, "", dist)


async def label(
    items: Sequence[Item],
    rubric: Rubric,
    *,
    squire: Any,
    concurrency: int = 16,
    cache: LabelCache | None = None,
    on_row: Callable[[Row], None] | None = None,
) -> list[Row]:
    """Every item labelled, in input order. Cached items cost nothing; spent ones are cached."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    gate = asyncio.Semaphore(concurrency)
    provider = squire.provider

    async def one(item: Item) -> Row:
        key = LabelCache.key(provider, rubric, item)
        if cache is not None and (hit := cache.get(key)) is not None:
            row = Row(**{**asdict(hit), "key": item.key})
        else:
            async with gate:
                row = await label_one(squire, rubric, item)
            if cache is not None and row.provider not in ("budget", "error") and row.probabilities:
                cache.put(key, row)
        if on_row is not None:
            on_row(row)
        return row

    return list(await asyncio.gather(*(one(item) for item in items)))


# --- files ----------------------------------------------------------------------------------


def _item_of(raw: Mapping[str, Any], index: int) -> Item:
    key = raw.get("key", raw.get("id", index))
    return Item(str(key), str(raw.get("text", "")), str(raw.get("context", "") or ""))


def read_items(path: str | Path) -> list[Item]:
    """Items from `.jsonl`, `.csv` (columns key or id, text, context) or `.txt` (one per line)."""
    path = Path(path)
    body = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        rows = [json.loads(line) for line in body.splitlines() if line.strip()]
        return [_item_of(r, i) for i, r in enumerate(rows)]
    if suffix == ".csv":
        return [_item_of(r, i) for i, r in enumerate(csv.DictReader(io.StringIO(body)))]
    return [Item(str(i), line) for i, line in enumerate(body.splitlines()) if line.strip()]


COLUMNS = ("key", "label", "p", "margin", "provider", "reason")


def write_rows(path: str | Path, rows: Iterable[Row]) -> None:
    """`.csv` gets the columns in `COLUMNS`; anything else is JSON lines with probabilities."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if path.suffix.lower() == ".csv":
        with path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(COLUMNS)
            for r in rows:
                writer.writerow([r.key, r.label or "", f"{r.p:.4f}", f"{r.margin:.4f}",
                                 r.provider, r.reason])  # fmt: skip
        return
    with path.open("w", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")


def summary(rows: Sequence[Row]) -> dict[str, Any]:
    """Counts a caller can print: labelled, abstained by reason, cached, labels."""
    reasons: dict[str, int] = {}
    labels: dict[str, int] = {}
    for r in rows:
        if r.label is None:
            reasons[r.reason or "none"] = reasons.get(r.reason or "none", 0) + 1
        else:
            labels[r.label] = labels.get(r.label, 0) + 1
    return {
        "items": len(rows),
        "labelled": sum(labels.values()),
        "abstained": reasons,
        "cached": sum(r.cached for r in rows),
        "labels": dict(sorted(labels.items(), key=lambda kv: -kv[1])),
    }
