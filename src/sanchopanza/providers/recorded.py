"""Deciders that cost nothing: replay a recording, or record a real one.

- `RecordedDecider` answers from a file of recorded decisions. Dry runs and tests: no
  network call, deterministic.
- `RecordingDecider` wraps a real decider and appends every decision to a file, turning a
  real run into a reproducible fixture.

File format, one JSON object per line:

    {"key": "<sha256 prefix>", "point": "routing", "model": "jev-1.13.0", "default": false,
     "input_tokens": 812, "cost_usd": 0.000034, "latency_ms": 266,
     "answers": {"complexity": {"kind": "score", "score": 0.3, "confidence": 0.9, ...}}}

`key` identifies exactly (point, state, questions). Without an exact match, the first
entry flagged `default` for the same point is used; without that, no answer.

`order` is the fingerprint of the option order the model saw. `key` sorts keys, so two
Choices that differ only in the order of their options share a key; the order moved 3-4
labels of 50 on the facts point (2026-09-25), so a recording that carries `order` answers
only that order. A recording without it (everything before 2026-09-25) matches any order.

**Two Jev versions.** `key` had no model in it, and every fixture in this repository holds
jev-1.13.0 answers under such keys. Those keys never change: for 1.13, an alias, or another
provider's model, `key_of` is what it always was. From jev-1.14 on (`jev_models.KEYED_SINCE`)
the model the provider says answered goes into the key, so a 1.14 line can sit next to a
1.13 line for the same query. A replay names the model it stands for,
`RecordedDecider.from_file(path, model="jev-1.14.0")`, and then answers only from that model's
lines; one that names none (or 1.13) answers only from unkeyed lines, as before. Both a
`FallbackDecider([recorded, live])` and a `RecordingDecider` therefore need the model when the
live decider is 1.14. The recommended layout keeps the files apart as well:
`fixture_path("fixtures/chunks.jsonl", "jev-1.14.0")` is `fixtures/jev114/chunks.jsonl`, so a
1.14 run never appends to a 1.13 fixture. A Box answer is stored as `"box": [top, bottom,
left, right]` beside its confidence (`Answer.to_dict`).

**Keys from ids, opt in.** `key` signs the question text, so a translated or reworded question
misses every line recorded with the old text. `keys="id"` adds a second key, `id_key`
(`id_key_of`), that signs each question's versioned id from `sanchopanza.catalog`, its kind
and its option names (or its number of levels), and the state; not its instructions, criteria
or descriptions, except the options of a question whose caller writes them (`classify`). A
`RecordingDecider(..., keys="id")` writes both keys on each line, so a text replay still reads
it; a `RecordedDecider(..., keys="id")` answers by `key` first, exactly as a text replay does,
and by `id_key` only when the text misses (a translated or reworded question), so the wording
asked always gets its own answer even when several wordings share the ids; among those, the
last line written answers. The default is `keys="text"`, under which nothing is written or
read differently than before.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from .. import catalog
from ..contract import Answer, Decider, Decision, Question, State
from .jev_models import keyed_by_model, version_of

KeyScheme = Literal["text", "id"]
KEY_SCHEMES: tuple[KeyScheme, ...] = ("text", "id")
ID_SCHEME = "id/1"  # in every id key's body: a new way of signing gets a new tag


def _scheme(keys: str) -> KeyScheme:
    if keys not in KEY_SCHEMES:
        raise ValueError(f"keys must be one of {KEY_SCHEMES}, not {keys!r}")
    return keys  # type: ignore[return-value]


def key_of(
    point: str, state: State, questions: Mapping[str, Question], model: str | None = None
) -> str:
    """Stable fingerprint of one query. Same questions on the same state, same key. The model
    is part of it only from jev-1.14 on: every key recorded before then stays as it was."""
    body: dict[str, Any] = {
        "point": point,
        "state": state,
        "questions": {k: asdict(q) for k, q in questions.items()},
    }
    if keyed_by_model(model):
        body = {**body, "model": model}
    serialized = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _shape(question: Question, *, options_are_input: bool = False) -> dict[str, Any]:
    """What of a question is not wording: its kind and its option names in order (a Choice),
    or its number of levels (a Score). Option names are identifiers, and often inputs; where
    the caller writes the descriptions too (`QuestionSpec.options_are_input`) they are signed.

    The order of a Score's levels is not signed: levels have no names, only text, and signing
    the text would undo the point of the key. Inverting a scale changes what it asks, so it
    takes a new version; for the package's own levels the wording canary in
    `tests/test_catalog.py` fails until it does."""
    options = getattr(question, "options", None)
    levels = getattr(question, "levels", None)
    if options is not None and options_are_input:
        return {"kind": question.kind, "options": [[str(k), v] for k, v in options.items()]}
    if options is not None:
        return {"kind": question.kind, "options": [str(name) for name in options]}
    if levels is not None:
        return {"kind": question.kind, "levels": len(levels)}
    return {"kind": question.kind}


def id_key_of(
    point: str, state: State, questions: Mapping[str, Question], model: str | None = None
) -> str:
    """A fingerprint of one query that does not depend on the language of its questions.

    It signs, per question key, the question's versioned id (`catalog.ids_of`) and its shape
    (`_shape`), plus the state, and the model from jev-1.14 on as `key_of` does. When every
    question has an id the point name is left out: ids already name their point, so a
    consumer that traces the same query under its own point name gets the same key. A
    question without an id is signed whole, with the point, as `key_of` signs it.
    """
    ids = catalog.ids_of(point, questions)
    signed: dict[str, Any] = {}
    for key, question in questions.items():
        qid = ids.get(key)
        if qid is None:
            signed[key] = {"question": asdict(question)}
            continue
        spec = catalog.QUESTIONS.get(qid)
        as_input = spec is not None and spec.options_are_input
        signed[key] = {"id": qid, **_shape(question, options_are_input=as_input)}
    body: dict[str, Any] = {"scheme": ID_SCHEME, "state": state, "questions": signed}
    if any(qid is None for qid in ids.values()):
        body = {**body, "point": point}
    if keyed_by_model(model):
        body = {**body, "model": model}
    serialized = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def order_of(questions: Mapping[str, Question]) -> str:
    """Fingerprint of the order in which every question lists its options or levels."""
    sequence = []
    for name, question in questions.items():
        options = getattr(question, "options", None)
        levels = getattr(question, "levels", None)
        if options is not None:
            sequence.append([name, list(options)])
        elif levels is not None:
            sequence.append([name, [str(level) for level in levels]])
    serialized = json.dumps(sequence, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:8]


def fixture_path(path: Path | str, model: str | None) -> Path:
    """Where a fixture for `model` lives: the path itself for 1.13 (and anything unkeyed),
    `<dir>/jev114/<name>` for jev-1.14.x, so each version's recordings have their own file."""
    path = Path(path)
    version = version_of(model)
    if version is None or not keyed_by_model(model):
        return path
    return path.parent / f"jev{version[0]}{version[1]}" / path.name


class RecordedDecider:
    name = "recorded"

    def __init__(
        self,
        entries: Sequence[Mapping[str, Any]],
        *,
        model: str | None = None,
        keys: KeyScheme = "text",
    ) -> None:
        """`model`: the Jev version this replay stands for. Keyed (1.14 on): only its own
        lines answer. Otherwise only unkeyed lines do, which is every recording before 1.14.
        `keys="id"`: answer by `key` as always, and by `id_key` (`id_key_of`) only when the
        text misses; among lines that share an `id_key`, the last one written answers."""
        self._model = model if keyed_by_model(model) else None
        self._keys = _scheme(keys)
        exact: dict[str, Mapping[str, Any]] = {}
        ordered: dict[tuple[str, str], Mapping[str, Any]] = {}
        defaults: dict[str, Mapping[str, Any]] = {}
        by_id: dict[str, Mapping[str, Any]] = {}
        for entry in entries:
            if not self._mine(entry):
                continue
            key = entry.get("key")
            point = str(entry.get("point", ""))
            if self._keys == "id" and entry.get("id_key"):
                by_id[str(entry["id_key"])] = entry
            if key and entry.get("order"):
                ordered[(str(key), str(entry["order"]))] = entry
            elif key:
                exact[str(key)] = entry
            if entry.get("default") and point not in defaults:
                defaults[point] = entry
        self._exact = exact
        self._ordered = ordered
        self._defaults = defaults
        self._by_id = by_id

    @property
    def model(self) -> str | None:
        """The keyed version this replay stands for (1.14 on); None for an unkeyed one."""
        return self._model

    def _mine(self, entry: Mapping[str, Any]) -> bool:
        recorded = str(entry.get("model") or "")
        if self._model is not None:
            return recorded == self._model
        return not keyed_by_model(recorded)

    @property
    def keys(self) -> KeyScheme:
        return self._keys

    @classmethod
    def from_file(
        cls, path: Path | str, *, model: str | None = None, keys: KeyScheme = "text"
    ) -> RecordedDecider:
        path = Path(path)
        if not path.exists():
            return cls((), model=model, keys=keys)
        lines = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(lines, model=model, keys=keys)

    def __len__(self) -> int:
        return len(self._exact) + len(self._ordered)

    def indexed_keys(self) -> frozenset[str]:
        """The text keys this replay answers from, whatever the option order."""
        return frozenset(self._exact) | frozenset(key for key, _ in self._ordered)

    def _by_id_entry(
        self, point: str, state: State, questions: Mapping[str, Question]
    ) -> Mapping[str, Any] | None:
        """The line recorded under this query's id key: the fallback when the text misses."""
        if not self._by_id:
            return None
        return self._by_id.get(id_key_of(point, state, questions, self._model))

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        key = key_of(point, state, questions, self._model)
        entry = (
            self._ordered.get((key, order_of(questions)))
            or self._exact.get(key)
            or self._by_id_entry(point, state, questions)
            or self._defaults.get(point)
        )
        if entry is None:
            return Decision(point=point, answers={}, provider=self.name, model="-")
        answers = {
            key: Answer.from_dict(value)
            for key, value in (entry.get("answers") or {}).items()
            if key in questions
        }
        return Decision(
            point=point,
            answers=answers,
            provider=self.name,
            model=str(entry.get("model") or "recorded"),
            input_tokens=int(entry.get("input_tokens") or 0),
            cost_usd=float(entry.get("cost_usd") or 0.0),
            latency_ms=int(entry.get("latency_ms") or 0),
        )


class RecordingDecider:
    """Wraps a real decider and writes each decision down, ready to be replayed."""

    def __init__(self, inner: Decider, path: Path | str, *, keys: KeyScheme = "text") -> None:
        """`keys="id"` also writes `id_key` (`id_key_of`) on every line; the default writes
        exactly the lines it always wrote."""
        self._inner = inner
        self._path = Path(path)
        self._keys = _scheme(keys)
        self.name = inner.name

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        decision = await self._inner.decide(point, state, questions)
        ids: dict[str, str] = {}
        if self._keys == "id":
            ids = {"id_key": id_key_of(point, state, questions, decision.model)}
        line = {
            "key": key_of(point, state, questions, decision.model),
            **ids,
            "order": order_of(questions),
            "point": point,
            "model": decision.model,
            "default": False,
            "input_tokens": decision.input_tokens,
            "cost_usd": decision.cost_usd,
            "latency_ms": decision.latency_ms,
            "answers": {k: a.to_dict() for k, a in decision.answers.items()},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        return decision
