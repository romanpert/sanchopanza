"""check_done's record: each tool result's head, and past it the part the answer rests on.

The record check_done reads keeps the first `HEAD` characters of each tool result. On 950
unseen AgentDojo stops that cut was behind most false blocks (docs/results/
2026-10-16-checkdone114/): 115 of Jev 1.14's 150 had a tool result longer than the head, and in
87 of them a value the agent wrote afterwards (a file name, a size, an id, a time, a name) was
in a result only past the cut and nowhere the record showed. The judge saw an answer it could
not check and called it unsupported. Whether keeping it helps is measured, not assumed
(docs/results/2026-10-16-checkdone-w17/prereg.md); until then the Stop hook uses it only when
asked (`SANCHOPANZA_DONE_EVIDENCE=1`).

`kept` leaves a result that fits as it is, and a longer one as its head when nothing the agent
wrote afterwards is found past the head, so those records are the old ones byte for byte. When
something is, it adds short windows around the first place each such value occurs past the
head, rarest values first, inside `EXTRA` more characters. Pure code: deterministic, no model.

`record` is the one builder of the record the Stop hook and the bench both use: steps in order,
("agent", text), ("action", "name(arguments)") or ("tool", result), rendered as the lines
check_done has always read. With `evidence=False` it is the old record.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

HEAD = 1_500  # what the record always kept of a tool result (`claude_code.TOOL_RESULT_LIMIT`)
EXTRA = 1_500  # at most this much more per result: windows and their markers
RADIUS = 160  # characters kept on each side of a value: its line and the lines around it
MARK = " [...] "  # `text.truncate`'s marker, between the head and each window
MAX_ANCHORS = 100  # values looked for per result, in the order the agent wrote them
MAX_HITS = 50  # places counted per value: enough to rank by rarity, and the cost stays linear

_ALNUM = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
_DIGIT = frozenset("0123456789")
_URL = re.compile(r"https?://[^\s)\]>'\"`]+")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")  # from a word's start only
_FILE = re.compile(r"(?<![\w.-])[\w-]+(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]{1,4}(?![\w])")
_DIGITS = re.compile(r"(?<![\w.,:/-])[A-Za-z_]*\d[\w.,:/-]*")
_QUOTED = re.compile(r"(?:^|(?<=[\s(:\[]))[\"'`“‘]([^\"'`”’\n]{3,80})[\"'`”’](?!\w)")
_NAME = re.compile(r"[A-Z][\w'&-]*(?: [A-Z][\w'&-]*)*")
_IDENTIFIER = re.compile(r"[a-z_]+")
_EDGE = ".,:;/-"
# Capitalised words that start sentences, not names. A name of one word needs four letters.
_COMMON = frozenset(
    [
        "the",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "based",
        "however",
        "now",
        "let",
        "please",
        "would",
        "could",
        "you",
        "your",
        "great",
        "sure",
        "thank",
        "thanks",
        "first",
        "next",
        "then",
        "also",
        "after",
        "before",
        "finally",
        "done",
        "since",
        "note",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "how",
        "yes",
        "sorry",
        "okay",
        "perfect",
        "excellent",
        "looking",
        "summary",
        "today",
        "unfortunately",
        "successfully",
        "additionally",
        "lastly",
        "all",
        "each",
        "every",
        "some",
        "none",
        "and",
        "but",
        "for",
    ]
)


def _names(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in _NAME.finditer(text):
        if m.start() and (text[m.start() - 1].isalnum() or text[m.start() - 1] in "_'"):
            continue  # inside a word: "McDonald" is found from its "M", not its "D"
        words, start = m.group(0).split(" "), m.start()
        while words and words[0].lower() in _COMMON:
            start += len(words.pop(0)) + 1
        if len(words) > 1 or (words and len(words[0]) >= 4 and words[0].lower() not in _COMMON):
            spans.append((start, start + len(" ".join(words))))
    return spans


def _spans(text: str) -> list[tuple[int, int]]:
    out = []
    for pattern, shortest in ((_URL, 1), (_EMAIL, 1), (_FILE, 1), (_DIGITS, 2)):
        for m in pattern.finditer(text):
            token = m.group(0).rstrip(_EDGE)  # the full stop after it is not part of it
            if len(token) >= shortest:
                out.append((m.start(), m.start() + len(token)))
    for m in _QUOTED.finditer(text):
        inner = m.group(1).strip()
        if inner and not _IDENTIFIER.fullmatch(inner):
            out.append((m.start(1), m.start(1) + len(m.group(1).rstrip())))
    out.extend(_names(text))
    return out


def anchors(text: str) -> list[str]:
    """The values in `text` a tool result can back: numbers of two characters or more and
    ids holding a digit, dates and times, e-mail addresses, URLs, file names, quoted strings
    that are not bare identifiers, and capitalised names. In order of first appearance, each
    once; a value inside a longer one at the same place (the domain of an address) is not
    counted again."""
    out: list[str] = []
    seen: set[str] = set()
    reach = -1  # the furthest end of a value taken: one ending before it lies inside that one
    for start, end in sorted(_spans(text), key=lambda s: (s[0], -(s[1] - s[0]))):
        if end <= reach:
            continue
        reach = end
        token = text[start:end].strip()
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _whole(text: str, at: int, size: int) -> bool:
    """A whole value: not inside a word, not the middle of a date or a number ("11" is not
    found in 2023-11-15 or 1.11), not the head of a longer number ("98" in 98.70); a time is
    found at the head of a timestamp's time ("12:30" in 12:30:00)."""
    end = at + size
    before, after = text[at - 1 : at], text[end : end + 1]
    if before in _ALNUM or after in _ALNUM:
        return False
    if before and before in "-.,:/" and text[at - 2 : at - 1] in _DIGIT:
        return False
    return not (after and after in ".," and text[end + 1 : end + 2] in _DIGIT)


def _hits(
    low: str, needle: str, limit: int = MAX_HITS, *, start: int = 0, stop: int | None = None
) -> list[int]:
    """Where `needle` occurs in `low` as a whole value, the first `limit` places, starting at
    `start` and ending by `stop`. The neighbours are read in the whole text, so a value cut by
    `start` or `stop` is not taken for a shorter one. Both strings are lowered by the caller;
    `str.find` keeps this linear in the text."""
    out: list[int] = []
    end = len(low) if stop is None else stop
    at = low.find(needle, start, end) if needle else -1
    while at != -1 and len(out) < limit:
        if _whole(low, at, len(needle)):
            out.append(at)
        at = low.find(needle, at + 1, end)
    return out


def _lowered(text: str) -> str:
    low = text.lower()
    return low if len(low) == len(text) else text  # a letter whose lower case is longer


def find(text: str, anchor: str) -> int | None:
    """Where `anchor` first occurs in `text` as a whole value, ignoring case; None if not."""
    low = _lowered(text)
    hits = _hits(low, anchor.lower() if low is not text else anchor, limit=1)
    return hits[0] if hits else None


def _merged(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def kept_for(
    result: str, wanted: Sequence[str], *, head: int = HEAD, extra: int = EXTRA,
    radius: int = RADIUS,
) -> str:  # fmt: skip
    """`result`'s head, plus windows around the values in `wanted` found only past it."""
    if len(result) <= head:
        return result
    first, rest = result[:head], result[head:]
    low = _lowered(result)
    candidates = []
    for order, anchor in enumerate(wanted[:MAX_ANCHORS]):
        needle = anchor.lower() if low is not result else anchor
        if _hits(low, needle, limit=1, stop=head):
            continue  # the judge already sees it, whole, inside the head
        hits = _hits(low, needle, start=head)
        if hits:
            candidates.append((len(hits), -len(anchor), order, anchor, hits[0] - head))
    spans: list[tuple[int, int]] = []
    for _, _, _, anchor, at in sorted(candidates):
        window = (max(0, at - radius), min(len(rest), at + len(anchor) + radius))
        trial = _merged([*spans, window])
        if sum(end - start + len(MARK) for start, end in trial) <= extra:
            spans = trial
    return first + "".join(MARK + rest[start:end] for start, end in spans)


def kept(result: str, later: str, **limits: int) -> str:
    """`result` as the record keeps it, given what the agent wrote after it (`later`)."""
    return kept_for(result, anchors(later), **limits)


PREFIX = {"agent": "AGENT: ", "action": "AGENT ACTION: ", "tool": "TOOL RESULT: "}


def _rendered(steps: Sequence[tuple[str, str]], results: Sequence[str]) -> str:
    texts = iter(results)
    return "\n".join(PREFIX[kind] + (next(texts) if kind == "tool" else text)
                     for kind, text in steps)  # fmt: skip


def record(
    steps: Sequence[tuple[str, str]],
    *,
    evidence: bool,
    head: int = HEAD,
    extra: int = EXTRA,
    limit: int | None = None,
) -> str:
    """check_done's record from the steps after the request. Without `evidence` each tool
    result is cut to its head, as the record always was; with it, `kept` looks for what each
    result backs in the agent's text and actions after that result.

    `limit` is the record's own cut (`completion.RECORD_LIMIT`): when the old record fits it
    and the one with evidence would not, the old one is returned, so the windows never push the
    request or the final answer out of what the judge reads."""
    old = _rendered(steps, [text[:head] for kind, text in steps if kind == "tool"])
    if not evidence:
        return old
    new = _rendered(steps, kept_results(steps, head=head, extra=extra))
    if limit is not None and len(new) > limit >= len(old):
        return old
    return new


def kept_results(
    steps: Sequence[tuple[str, str]], *, head: int = HEAD, extra: int = EXTRA
) -> list[str]:
    """Each tool result in `steps`, in order, as the record with evidence keeps it: `kept_for`
    over the values the agent wrote after that result, at most `MAX_ANCHORS` of them. What it
    said comes before what it passed to tools, the final answer first: an action full of
    values (a file it wrote) never crowds out the answer the judge has to check."""
    after: list[list[str]] = [[] for _ in steps]
    said: list[str] = []  # from the last text back
    passed: list[str] = []  # from the last action back
    seen: set[str] = set()
    for index in range(len(steps) - 1, -1, -1):
        after[index] = (said + passed)[:MAX_ANCHORS]
        kind, text = steps[index]
        bucket = said if kind == "agent" else passed
        if kind == "tool" or len(bucket) >= MAX_ANCHORS:
            continue  # each list holds at most what can be looked for
        fresh = [a for a in anchors(text) if a not in seen]
        seen.update(fresh)
        bucket.extend(fresh[: MAX_ANCHORS - len(bucket)])
    return [kept_for(text, after[index], head=head, extra=extra)
            for index, (kind, text) in enumerate(steps) if kind == "tool"]  # fmt: skip
