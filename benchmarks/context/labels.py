"""Which history tool results the rest of the session used: a lexical proxy, stated as one.

A history tool result is NEEDED when the future (assistant text and tool inputs after the
cut; never tool results) contains at least one distinctive token that appears in that result
and nowhere in the history outside tool results. Distinctive tokens:

- code-shaped identifiers of 6+ characters: with an underscore, a digit, an inner capital
  (camelCase) or all capitals. Plain lowercase or Capitalized words are left out: in two
  languages they are prose, and prose words are the proxy's worst false positives;
- file paths (normalized to forward slashes), and each path's last two components;
- numbers of 4+ digits and hex strings of 7-40 characters with a digit and a letter;
- quoted strings of 8-120 characters on a line that names an error (matched as substrings).

A history-built stoplist removes any token found in more than `max(3, 5 %)` of the history's
tool results: those are the codebase's common words, not something one result supplied.

Token coverage (Amendment 1): `hits` lists every used token of a result, so a metric can ask
whether each token the future used survives in at least one kept result. A stubbed read whose
lines are still in a later, kept read of the same file loses nothing at that level.

Two further signals, reported beside the primary label and never mixed into it:

- `needed_before_refetch`: a needed token is used in the future before any future tool
  result shows it again. When the agent re-reads a file and then uses a name from it, the
  history copy was not what it used.
- `reread`: the future repeats the same tool with the same input.

It is neither a lower nor an upper bound: it misses a result that informed a decision
without leaving a token in the future (false negatives), and it can credit a result for a
token the model would have written anyway (false positives). It is a lexical proxy, not a
measure of what the model needed.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{5,}\b")
PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\w.\-~@]+[/\\]{1,2})+[\w.\-@]+")
NUMBER = re.compile(r"\b\d{4,}\b")
HEX = re.compile(r"\b[0-9a-f]{7,40}\b")
QUOTED = re.compile(r"\"([^\"\n]{8,120})\"|'([^'\n]{8,120})'")
ERROR_LINE = re.compile(r"(?i)error|exception|traceback|failed|not found|denied|invalid")
INNER_CAPITAL = re.compile(r"[a-z][A-Z]")
STOP_SHARE = 0.05
STOP_MIN = 3


def code_shaped(word: str) -> bool:
    if "_" in word or any(c.isdigit() for c in word):
        return True
    if INNER_CAPITAL.search(word):
        return True
    return word.isupper()


def _path_tokens(text: str) -> set[str]:
    out = set()
    for match in PATH.findall(text):
        path = re.sub(r"[/\\]+", "/", match).strip("./")
        if len(path) < 6 or "/" not in path:
            continue
        out.add(path)
        tail = "/".join(path.split("/")[-2:])
        if len(tail) >= 6:
            out.add(tail)
    return out


def tokens(text: str) -> set[str]:
    """The distinctive tokens of a text (before the stoplist)."""
    found = {w for w in IDENT.findall(text) if code_shaped(w)}
    found |= _path_tokens(text)
    found |= set(NUMBER.findall(text))
    found |= {h for h in HEX.findall(text) if re.search(r"\d", h) and re.search(r"[a-f]", h)}
    return found


def error_strings(text: str) -> set[str]:
    out = set()
    for line in text.splitlines():
        if ERROR_LINE.search(line):
            for a, b in QUOTED.findall(line):
                out.add(a or b)
    return out


def strings_of(value: Any) -> Iterable[str]:
    """Every string leaf of a tool input, so paths are not JSON-escaped."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from strings_of(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from strings_of(v)
    elif value is not None:
        yield str(value)


def _outside_results(messages: Sequence[Mapping[str, Any]], *, assistant_only: bool) -> list[str]:
    """Texts in order: text blocks and tool inputs (not tool results)."""
    out = []
    for message in messages:
        if assistant_only and message.get("role") != "assistant":
            continue
        for block in message.get("content", []):
            if block.get("type") == "text":
                out.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                out.append("\n".join(strings_of(block.get("input"))))
    return out


def call_key(tool: str, value: Any) -> str:
    return tool + "\x00" + json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _future_order(future: Sequence[Mapping[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    """First position of each token in a future use, and in a future tool result."""
    used: dict[str, int] = {}
    shown: dict[str, int] = {}
    position = 0
    for message in future:
        for block in message.get("content", []):
            position += 1
            kind = block.get("type")
            if kind == "tool_result":
                for t in tokens(str(block.get("content", ""))):
                    shown.setdefault(t, position)
            elif message.get("role") == "assistant" and kind in ("text", "tool_use"):
                text = block.get("text", "") if kind == "text" else ""
                if kind == "tool_use":
                    text = "\n".join(strings_of(block.get("input")))
                for t in tokens(text):
                    used.setdefault(t, position)
    return used, shown


def label(
    history: Sequence[Mapping[str, Any]],
    future: Sequence[Mapping[str, Any]],
    history_calls: Sequence[Any],
) -> dict[str, dict[str, Any]]:
    """Per history call id: needed, needed_before_refetch, needed_sole, reread, tokens."""
    outside_texts = _outside_results(history, assistant_only=False)
    outside_blob = "\n".join(outside_texts)
    outside = set()
    for text in outside_texts:
        outside |= tokens(text)
    per_call = {c.id: tokens(c.result) - outside for c in history_calls}
    df = Counter(t for toks in per_call.values() for t in toks)
    limit = max(STOP_MIN, math.ceil(STOP_SHARE * len(history_calls)))
    stop = {t for t, n in df.items() if n > limit}

    future_texts = _outside_results(future, assistant_only=True)
    future_blob = "\n".join(future_texts)
    used, shown = _future_order(future)
    future_calls = {
        call_key(b.get("name", ""), b.get("input"))
        for m in future
        if m.get("role") == "assistant"
        for b in m.get("content", [])
        if b.get("type") == "tool_use"
    }

    out: dict[str, dict[str, Any]] = {}
    for c in history_calls:
        hits = sorted(t for t in per_call[c.id] - stop if t in used)
        errors = sorted(
            s for s in error_strings(c.result) if s in future_blob and s not in outside_blob
        )
        early = [t for t in hits if used[t] < shown.get(t, math.inf)]
        out[c.id] = {
            "tool": c.tool,
            "chars": len(c.result),
            "is_error": c.is_error,
            "needed": bool(hits or errors),
            "needed_before_refetch": bool(early or errors),
            "needed_sole": any(df[t] == 1 for t in hits) or bool(errors),
            "reread": call_key(c.tool, c.input) in future_calls,
            "n_tokens": len(hits) + len(errors),
            "tokens": (hits + errors)[:12],
            "hits": hits + errors,
        }
    return out
