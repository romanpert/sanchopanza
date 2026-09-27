"""What an outer loop may tune, as data: `Knobs`, and the atomic `Edit`s between two of them.

Four kinds of knob, and the one property that separates them:

| kind      | what it is                                   | invalidates recordings |
|-----------|----------------------------------------------|------------------------|
| threshold | a `Thresholds` value                         | no                     |
| flag      | a `ToolWindow` switch                        | no                     |
| question  | the `instructions` of one question of a point | **yes**                |
| about     | the `about` text of one tool-catalog group   | **yes**                |

A threshold or a flag changes what code does with an answer; the request to the provider is
byte-identical, so a recording replays it for free. A question or an `about` text is part of
the request, so `providers.recorded.key_of` changes, the recording no longer answers, and the
only way to score the edit is a live re-ask - which costs money and is not reproducible (the
provider drifts up to 0.09 on identical input within a day).

Question texts are held as overrides only: an absent key means the wording shipped in
`points/*.py`. The package has no hook to change a question's text, so `QuestionOverrides`
(in `evaluator.py`) applies them at the one chokepoint every point already goes through, the
decider.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, Literal

from ..policy import Thresholds
from ..squire import Squire

EditKind = Literal["threshold", "question", "about", "flag"]
KINDS: tuple[EditKind, ...] = ("threshold", "question", "about", "flag")
INVALIDATING: frozenset[str] = frozenset({"question", "about"})
FLAGS: tuple[str, ...] = ("scan_untrusted", "wait_on_deferred")
THRESHOLD_NAMES: tuple[str, ...] = tuple(f.name for f in fields(Thresholds))

Value = float | int | bool | str | None
Pairs = tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class Edit:
    """One atomic change: one kind, one key, from `before` to `after`."""

    kind: EditKind
    key: str
    before: Value
    after: Value

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown edit kind {self.kind!r}; expected one of {KINDS}")
        if not self.key:
            raise ValueError("an edit needs a key")

    @property
    def invalidates_recordings(self) -> bool:
        """True when the edit changes the request, so no recording can score it."""
        return self.kind in INVALIDATING

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "before": self.before,
            "after": self.after,
            "invalidates_recordings": self.invalidates_recordings,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Edit:
        return cls(raw["kind"], str(raw["key"]), raw.get("before"), raw.get("after"))


def _pairs(mapping: Mapping[str, Any]) -> Pairs:
    return tuple(sorted(mapping.items()))


def _question_key(key: str) -> str:
    point, _, question = key.partition(":")
    if not point or not question:
        raise ValueError(f"a question key is 'point:question' (e.g. 'loop:goal_met'), not {key!r}")
    return key


def _threshold_values(raw: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(raw) - set(THRESHOLD_NAMES))
    if unknown:
        raise ValueError(f"unknown threshold name(s): {unknown}")
    coerced = Thresholds.from_mapping(raw)
    return {name: getattr(coerced, name) for name in THRESHOLD_NAMES}


def _flag_values(raw: Mapping[str, Any]) -> dict[str, bool]:
    unknown = sorted(set(raw) - set(FLAGS))
    if unknown:
        raise ValueError(f"unknown flag name(s): {unknown}; known flags are {FLAGS}")
    return {name: bool(raw.get(name, True)) for name in FLAGS}


@dataclass(frozen=True, slots=True)
class Knobs:
    """A frozen, JSON-serializable snapshot of everything an outer loop may tune."""

    thresholds: Pairs
    questions: Pairs = ()
    abouts: Pairs = ()
    flags: Pairs = field(default=(("scan_untrusted", True), ("wait_on_deferred", True)))

    # --- construction ----------------------------------------------------------------------

    @classmethod
    def from_thresholds(
        cls,
        thresholds: Thresholds,
        *,
        catalog: Sequence[Mapping[str, Any]] = (),
        wait_on_deferred: bool = True,
        scan_untrusted: bool = True,
    ) -> Knobs:
        values = {name: getattr(thresholds, name) for name in THRESHOLD_NAMES}
        abouts = {
            str(g.get("name", "")).strip(): str(g.get("about", "") or g.get("description", ""))
            for g in catalog
        }
        flags = {"scan_untrusted": scan_untrusted, "wait_on_deferred": wait_on_deferred}
        return cls(_pairs(values), (), _pairs(abouts), _pairs(flags))

    @classmethod
    def from_squire(
        cls,
        squire: Squire,
        *,
        catalog: Sequence[Mapping[str, Any]] = (),
        wait_on_deferred: bool = True,
        scan_untrusted: bool = True,
    ) -> Knobs:
        """The knobs a running squire holds. Window flags are passed in: read them from a live
        window as `window.wait_on_deferred` and `window.scan_untrusted`."""
        return cls.from_thresholds(
            squire.thresholds,
            catalog=catalog,
            wait_on_deferred=wait_on_deferred,
            scan_untrusted=scan_untrusted,
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Knobs:
        """Inverse of `to_dict`. Unknown names raise: a typo in a proposal must not vanish."""
        questions = {_question_key(k): str(v) for k, v in (raw.get("questions") or {}).items()}
        return cls(
            _pairs(_threshold_values(raw.get("thresholds") or {})),
            _pairs(questions),
            _pairs({str(k): str(v) for k, v in (raw.get("abouts") or {}).items()}),
            _pairs(_flag_values(raw.get("flags") or {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "thresholds": dict(self.thresholds),
            "questions": dict(self.questions),
            "abouts": dict(self.abouts),
            "flags": dict(self.flags),
        }

    def fingerprint(self) -> str:
        """Stable id of this exact configuration."""
        body = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    # --- reading -----------------------------------------------------------------------------

    def threshold(self, name: str) -> Any:
        return dict(self.thresholds)[name]

    @property
    def question(self) -> dict[str, str]:
        return dict(self.questions)

    @property
    def about(self) -> dict[str, str]:
        return dict(self.abouts)

    @property
    def flag(self) -> dict[str, bool]:
        return dict(self.flags)

    def to_thresholds(self) -> Thresholds:
        return Thresholds(**dict(self.thresholds))

    def catalog(self, base: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
        """`base` with this snapshot's `about` texts. Groups not in the snapshot are unchanged."""
        abouts = self.about
        return tuple(
            {**dict(g), "about": abouts[name]}
            if (name := str(g.get("name", "")).strip()) in abouts
            else dict(g)
            for g in base
        )

    # --- changing (always a new object) ------------------------------------------------------

    def with_threshold(self, name: str, value: Any) -> Knobs:
        values = _threshold_values({**dict(self.thresholds), name: value})
        return Knobs(_pairs(values), self.questions, self.abouts, self.flags)

    def with_question(self, key: str, text: str | None) -> Knobs:
        key = _question_key(key)
        current = {k: v for k, v in self.questions if k != key}
        updated = current if text is None else {**current, key: text}
        return Knobs(self.thresholds, _pairs(updated), self.abouts, self.flags)

    def with_about(self, group: str, text: str) -> Knobs:
        return Knobs(
            self.thresholds, self.questions, _pairs({**self.about, group: text}), self.flags
        )

    def with_flag(self, name: str, value: bool) -> Knobs:
        return Knobs(
            self.thresholds,
            self.questions,
            self.abouts,
            _pairs(_flag_values({**self.flag, name: value})),
        )

    def value(self, kind: EditKind, key: str) -> Value:
        source = {
            "threshold": self.thresholds,
            "question": self.questions,
            "about": self.abouts,
            "flag": self.flags,
        }[kind]
        return dict(source).get(key)

    def apply(self, edits: Iterable[Edit]) -> Knobs:
        """Apply edits in order. An edit whose `before` is not what this snapshot holds is
        stale - proposed against another incumbent - and raises instead of being forced."""
        knobs = self
        for edit in edits:
            current = knobs.value(edit.kind, edit.key)
            if current != edit.before:
                raise ValueError(
                    f"stale edit {edit.kind}:{edit.key}: expects {edit.before!r}, "
                    f"the incumbent holds {current!r}"
                )
            knobs = _set(knobs, edit)
        return knobs


def _set(knobs: Knobs, edit: Edit) -> Knobs:
    if edit.kind == "threshold":
        return knobs.with_threshold(edit.key, edit.after)
    if edit.kind == "question":
        return knobs.with_question(edit.key, None if edit.after is None else str(edit.after))
    if edit.kind == "about":
        return knobs.with_about(edit.key, str(edit.after))
    return knobs.with_flag(edit.key, bool(edit.after))


def diff(a: Knobs, b: Knobs) -> tuple[Edit, ...]:
    """The atomic edits that turn `a` into `b`, one per changed key, in kind order."""
    edits: list[Edit] = []
    for kind, left, right in (
        ("threshold", a.thresholds, b.thresholds),
        ("question", a.questions, b.questions),
        ("about", a.abouts, b.abouts),
        ("flag", a.flags, b.flags),
    ):
        la, rb = dict(left), dict(right)
        for key in sorted(set(la) | set(rb)):
            if la.get(key) != rb.get(key):
                edits.append(Edit(kind, key, la.get(key), rb.get(key)))  # type: ignore[arg-type]
    return tuple(edits)


def edits_hash(edits: Iterable[Edit]) -> str:
    """Id of a hypothesis: the set of (kind, key, after), order-free and incumbent-free."""
    body = sorted(
        json.dumps([e.kind, e.key, e.after], ensure_ascii=False, default=str) for e in edits
    )
    return hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()[:16]
