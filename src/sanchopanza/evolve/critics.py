"""Two critics that run before or beside evaluation, not after it.

- `leak_check`: RRSI's leak critic. A reworded question or `about` text that carries a phrase,
  a number, a name or a case id from the bench scores well for the wrong reason: it encodes
  the answers. Rejected before any score is computed, so it cannot be admitted on merit.
- `dormant_gates`: RRSI's pruning signal, as a report only. A gate whose outcome never moved
  over N real decisions is a candidate to question, never to remove automatically: a guard
  that never fired on benign traffic may be exactly the guard that matters on the one bad day.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .knobs import Edit

WORD = re.compile(r"\w+")
NUMBER = re.compile(r"\d[\d.,/:-]*\d")  # two digits or more, separators allowed inside
NAME_STOP = frozenset({"the", "a", "an", "in", "on", "el", "la", "los", "las", "un", "una"})


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _ngrams(text: str, n: int) -> set[str]:
    tokens = WORD.findall(text.lower())
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _names(text: str) -> set[str]:
    """Runs of two or more capitalised words: 'Inversiones Delta', 'Audiencia Nacional'."""
    found: set[str] = set()
    run: tuple[str, ...] = ()
    for word in [*WORD.findall(text), ""]:
        capital = len(word) >= 2 and word[0].isupper() and word.isalpha()
        if capital and (run or word.lower() not in NAME_STOP):
            run = (*run, word)
            continue
        if len(run) >= 2:
            found = {*found, " ".join(run)}
        run = ()
    return found


def _present(literal: str, text: str, *, fold: bool) -> bool:
    haystack, needle = (text.lower(), literal.lower()) if fold else (text, literal)
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


@dataclass(frozen=True, slots=True)
class LeakCheck:
    ok: bool
    ngrams: tuple[str, ...]  # word n-grams shared with the bench that the edit introduced
    literals: tuple[str, ...]  # numbers, names and case ids from the bench it introduced


def leak_check(edit: Edit, cases: Iterable[Mapping[str, Any]], *, n: int = 4) -> LeakCheck:
    """Reject a question or `about` edit whose new text quotes the bench.

    Anything already in `before` is not counted: the edit did not introduce it.
    """
    if n < 4:
        raise ValueError("n-grams shorter than four words match ordinary prose")
    if edit.kind not in ("question", "about"):
        return LeakCheck(True, (), ())
    after = " ".join(_strings(edit.after))
    before = " ".join(_strings(edit.before))
    case_list = list(cases)
    corpus = [s for c in case_list for s in _strings([c.get("input"), c.get("expected")])]
    shared = set().union(*(_ngrams(s, n) for s in corpus)) if corpus else set()
    ngrams = (_ngrams(after, n) - _ngrams(before, n)) & shared

    numbers = {m for s in corpus for m in NUMBER.findall(s)}
    names = set().union(*(_names(s) for s in corpus)) if corpus else set()
    ids = {str(c["id"]) for c in case_list if c.get("id")}
    literals = {
        *(
            x
            for x in numbers
            if _present(x, after, fold=False) and not _present(x, before, fold=False)
        ),
        *(
            x
            for x in names
            if _present(x, after, fold=False) and not _present(x, before, fold=False)
        ),
        *(x for x in ids if _present(x, after, fold=True) and not _present(x, before, fold=True)),
    }
    return LeakCheck(not ngrams and not literals, tuple(sorted(ngrams)), tuple(sorted(literals)))


# --- dormant gates -----------------------------------------------------------------------------

GateKind = Literal["never_acts", "always_acts", "constant"]

# point -> (outcome field, value when the gate does not act or None if there is no such value,
#           normaliser). The fields are the ones `Squire` writes with `record(...)`.
_as_bool: Callable[[Any], Any] = lambda v: bool(v)  # noqa: E731
_same: Callable[[Any], Any] = lambda v: v  # noqa: E731
OUTCOME: dict[str, tuple[str, Any, Callable[[Any], Any]]] = {
    "routing": ("chosen", None, _same),
    "search": ("route", "full", _same),
    "triage": ("keep", True, _same),
    "tools": ("dropped", False, _as_bool),
    "tool_window": ("added", False, _as_bool),
    "citation": ("verdict", None, _same),
    "guard": ("denied", False, _same),
    "injection": ("flagged", False, _same),
    "review": ("message", False, _as_bool),
    "loop": ("message", False, _as_bool),
    "entity": ("same", None, _same),
    "facts": ("relation", None, _same),
    "classify": ("category", None, _same),
    "memory_write": ("store", False, _same),
    "memory_collision": ("action", None, _same),
    "recall": ("look", True, _same),
    "extract_gate": ("extract", True, _same),
    "edge": ("verdict", None, _same),
    "redundant_page": ("drop", False, _same),
}


@dataclass(frozen=True, slots=True)
class DormantGate:
    point: str
    field: str
    value: Any
    decisions: int
    kind: GateKind  # never_acts: always the default; always_acts: never the default


def _decision_data(records: Any) -> Iterable[Mapping[str, Any]]:
    if hasattr(records, "events"):
        records = records.events
    elif hasattr(records, "read"):
        records = records.read()
    for record in records:
        if "kind" in record and "data" in record:
            if record["kind"] == "decision":
                yield record["data"]
        else:
            yield record


def _evidence(data: Mapping[str, Any]) -> bool:
    """A decision the model actually answered, without error, outside the code layer."""
    if data.get("error") or data.get("provider") in ("code", "budget"):
        return False
    return not ("answers" in data and not data["answers"])


def dormant_gates(records: Any, *, min_decisions: int = 50) -> tuple[DormantGate, ...]:
    """Points whose outcome never changed over at least `min_decisions` answered decisions.

    `records` is a journal (`MemoryJournal`, `JsonlJournal`), its events, or decision `data`
    dicts. Reported, never removed.
    """
    values: dict[str, list[Any]] = defaultdict(list)
    for data in _decision_data(records):
        point = str(data.get("point", ""))
        if point not in OUTCOME or not _evidence(data):
            continue
        name, _, normalise = OUTCOME[point]
        values[point].append(normalise((data.get("outcome") or {}).get(name)))
    gates: list[DormantGate] = []
    for point, seen in sorted(values.items()):
        if len(seen) < min_decisions or any(v != seen[0] for v in seen):
            continue
        name, default, _ = OUTCOME[point]
        kind: GateKind = (
            "constant"
            if default is None
            else ("never_acts" if seen[0] == default else "always_acts")
        )
        gates.append(DormantGate(point, name, seen[0], len(seen), kind))
    return tuple(gates)
