"""A free, deterministic index of what a tool result holds: the tokens a later step looks for.

    index_of(text)   # "PRB-4821; RT-8KX2; TIMEOUT=30s; ERROR: disk full on /var/log/app.log"

Used where a result leaves the context without a decider: the `index` stub style of
compaction (the stub says what the archived text holds, so the agent knows to `Read` it) and
the `free` arrival mode (lines holding a code or an identifier are kept). No model, no network.

What counts. Error lines come first (the failing line of a long log is the thing a later step
most often needs, and the one a summary drops most: docs/results/2026-09-28-context-e2e), then
everything else in order of first appearance:

- codes and identifiers: a token with both letters and digits (`RT-8KX2`, `a1b32c8c7d`), or
  with a digit and an internal `-` or `_` (`PRB-4821`, `4821_17`); an ISO date alone is not one;
- `KEY=value` and `key: value` pairs whose value holds a digit;
- error lines: a line containing error, fail, exception or traceback, trimmed to 80 characters;
- file paths: a letter and either an extension, a root (`/`, `~`, `.`, a drive) or two
  separators, so `and/or` is not one.

An item already contained in an earlier one is not repeated (a code inside an error line
comes with the line); items longer than 40 characters are cut to 40.
"""

from __future__ import annotations

import heapq
import itertools
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ..text import STOPWORDS

LIMIT = 240
ITEM_MAX = 40
ERROR_LINE_MAX = 80
SEPARATOR = "; "
CANDIDATES_MAX = 5_000  # candidates looked at, in ranked order; bounds the work on a huge result

ERROR = re.compile(r"error|fail|exception|traceback", re.I)
_CODE = re.compile(r"(?<![\w-])[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?(?![\w-])")
_PAIR = re.compile(r"(?<![\w.-])([A-Za-z_][\w.-]{0,40})(=|:[ \t]+)([^\s,;]+)")
_PATH = re.compile(r"(?<![\w.\\/-])(?:[A-Za-z]:|~|\.{1,2})?(?:[\\/]?[\w.-]+)(?:[\\/][\w.-]+)+")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SEP = re.compile(r"[\\/]")


@dataclass(frozen=True, slots=True)
class Item:
    position: int
    kind: str  # "code" | "pair" | "error" | "path"
    text: str


def is_code(token: str) -> bool:
    """A code or identifier: letters and digits, or a digit with an internal `-`/`_`."""
    if not any(c.isdigit() for c in token) or _DATE.fullmatch(token):
        return False
    has_letter = any(c.isalpha() for c in token)
    return has_letter or any(sep in token.strip("-_") for sep in "-_")


def codes_of(text: str) -> tuple[str, ...]:
    """Every distinct code or identifier in `text`, in order of first appearance."""
    seen: dict[str, None] = {}
    for match in _CODE.finditer(text):
        token = match.group(0)
        if is_code(token):
            seen.setdefault(token, None)
    return tuple(seen)


def _codes(text: str) -> Iterator[Item]:
    for match in _CODE.finditer(text):
        if is_code(match.group(0)):
            yield Item(match.start(), "code", match.group(0))


def _pairs(text: str) -> Iterator[Item]:
    for match in _PAIR.finditer(text):
        if any(c.isdigit() for c in match.group(3)):
            sep = "=" if match.group(2) == "=" else ": "
            yield Item(match.start(), "pair", f"{match.group(1)}{sep}{match.group(3)}")


def _errors(text: str) -> Iterator[Item]:
    offset = 0
    for line in text.splitlines(keepends=True):
        if ERROR.search(line):
            yield Item(offset, "error", line.strip()[:ERROR_LINE_MAX])
        offset += len(line)


def _is_path(path: str) -> bool:
    if not any(c.isalpha() for c in path) or path.startswith("//"):
        return False
    rooted = path[0] in "/\\~." or path[1:2] == ":"
    last = _SEP.split(path)[-1]
    return rooted or "." in last.strip(".") or len(_SEP.findall(path)) >= 2


def _paths(text: str) -> Iterator[Item]:
    for match in _PATH.finditer(text):
        path = match.group(0).rstrip(".")
        if _is_path(path):
            yield Item(match.start(), "path", path)


_ORDER = {"error": 0, "pair": 1, "path": 2, "code": 3}


def _ranked(text: str) -> Iterator[Item]:
    """Error lines first, then pairs, paths and codes merged by first appearance. Lazy."""
    yield from _errors(text)
    yield from heapq.merge(
        _pairs(text),
        _paths(text),
        _codes(text),
        key=lambda item: (item.position, _ORDER[item.kind]),
    )


def items_of(text: str) -> tuple[Item, ...]:
    """Every candidate, error lines first, then by first appearance; before dedup and limit."""
    return tuple(_ranked(text))


def _kept(items: Iterable[Item], limit: int) -> tuple[str, ...]:
    """The items that fit in `limit` once joined, deduplicated; stops at the first that does not.

    Linear in the input: at most `CANDIDATES_MAX` candidates are looked at, and the substring
    rule only runs against the items already kept, which `limit` keeps to a handful.
    """
    kept: list[str] = []
    seen: set[str] = set()
    length = 0
    for item in itertools.islice(items, CANDIDATES_MAX):
        text = item.text if item.kind == "error" else item.text[:ITEM_MAX]
        if not text or text in seen or text.lower() in STOPWORDS:
            continue
        if any(text in earlier for earlier in kept):
            continue
        added = len(text) + (len(SEPARATOR) if kept else 0)
        if length + added > limit:
            break
        kept.append(text)
        seen.add(text)
        length += added
    return tuple(kept)


def index_of(text: str, limit: int = LIMIT) -> str:
    """The distinctive tokens of `text`, joined by `; `, cut at a separator to `limit`. Pure."""
    return SEPARATOR.join(_kept(_ranked(text or ""), limit))
