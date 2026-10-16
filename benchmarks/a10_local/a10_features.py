"""Features for the local check_done classifier (lot A10): TF-IDF over check_done's own state.

The classifier reads exactly what Jev reads for check_done: the `task` and `record` strings of
`points.completion.questions`. Nothing else reaches a feature: no probability, no answer of any
model, no benchmark field. Pure code and deterministic: the vocabulary is sorted, ties are
impossible, and the same text always gives the same vector.

Four token families, each prefixed so they never collide:

- `w:` word n-grams (1..`word_n`) over task and record, lower-cased `[a-z0-9_]+` words;
- `c:` character n-grams (3..5) inside word boundaries, over the same words;
- `l:` word 1- and 2-grams of the agent's LAST text line in the record (its final message);
- `s:` structure tokens counted from the record's lines (actions, errors, results at the cut,
  whether the last step is the agent asking a question, ...).

Each family is TF-IDF (sublinear tf, smoothed idf, as scikit-learn's defaults) and L2-normalised
on its own; the families are then scaled by 1/sqrt(k) so every vector has norm 1.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

WORD = re.compile(r"[a-z0-9_]+")
CHAR_MIN, CHAR_MAX = 3, 5
TOOL_HEAD = 1_500  # completion/run.py's TOOL_LIMIT: a result this long was cut
PREFIX = {"AGENT ACTION: ": "action", "TOOL RESULT: ": "tool", "AGENT: ": "agent"}
FAMILIES = ("w", "c", "l", "s")

Row = tuple[tuple[int, ...], tuple[float, ...]]


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def ngrams(items: Sequence[str], n_max: int) -> Iterable[str]:
    for n in range(1, n_max + 1):
        for i in range(len(items) - n + 1):
            yield " ".join(items[i : i + n])


def char_grams(items: Iterable[str]) -> Iterable[str]:
    for word in items:
        padded = f" {word} "
        for n in range(CHAR_MIN, CHAR_MAX + 1):
            for i in range(len(padded) - n + 1):
                yield padded[i : i + n]


def steps_of(record: str) -> list[tuple[str, str]]:
    """The record's steps, read back from its line prefixes (`done_evidence.PREFIX`). A line
    with no prefix continues the step before it (a multi-line tool result or message)."""
    out: list[tuple[str, str]] = []
    for line in record.split("\n"):
        match = next(((p, k) for p, k in PREFIX.items() if line.startswith(p)), None)
        if match is None:
            if out:
                out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
            continue
        out.append((match[1], line[len(match[0]) :]))
    return out


def _bucket(n: int) -> str:
    for top, name in ((0, "0"), (1, "1"), (2, "2"), (4, "3-4"), (8, "5-8"), (16, "9-16")):
        if n <= top:
            return name
    return "17+"


def structure(record: str) -> list[str]:
    """Counts and shapes of the record, as tokens. Read from the text only."""
    steps = steps_of(record)
    kinds = Counter(k for k, _ in steps)
    tools = [t for k, t in steps if k == "tool"]
    agent = [t for k, t in steps if k == "agent"]
    last_kind = steps[-1][0] if steps else "none"
    last_agent = agent[-1] if agent else ""
    out = [
        f"actions={_bucket(kinds['action'])}",
        f"results={_bucket(kinds['tool'])}",
        f"messages={_bucket(kinds['agent'])}",
        f"errors={_bucket(sum(t.startswith('ERROR:') for t in tools))}",
        f"cut={_bucket(sum(len(t) >= TOOL_HEAD for t in tools))}",
        f"last={last_kind}",
        f"record_at_limit={record.endswith(' [...]')}",
    ]
    if last_agent:
        out.append(f"last_asks={last_agent.rstrip().endswith('?')}")
        out.append(f"last_has_question_mark={'?' in last_agent}")
    else:
        out.append("no_agent_text")
    return out


def last_agent_text(record: str) -> str:
    agent = [t for k, t in steps_of(record) if k == "agent"]
    return agent[-1] if agent else ""


def tokens(task: str, record: str, families: Sequence[str], word_n: int) -> Counter[str]:
    """Every token of `families` in the state's two strings, with its count."""
    unknown = set(families) - set(FAMILIES)
    if unknown:
        raise ValueError(f"unknown families {sorted(unknown)}")
    counts: Counter[str] = Counter()
    both = words(task) + words(record)
    if "w" in families:
        counts.update("w:" + g for g in ngrams(both, word_n))
    if "c" in families:
        counts.update("c:" + g for g in char_grams(both))
    if "l" in families:
        counts.update("l:" + g for g in ngrams(words(last_agent_text(record)), 2))
    if "s" in families:
        counts.update("s:" + t for t in structure(record))
    return counts


@dataclass(frozen=True)
class Vectorizer:
    """A fitted vocabulary: term -> column (sorted terms), and each column's idf."""

    terms: tuple[str, ...]
    idf: tuple[float, ...]

    @property
    def index(self) -> dict[str, int]:
        return {t: i for i, t in enumerate(self.terms)}

    @classmethod
    def fit(cls, docs: Sequence[Mapping[str, int]], min_df: int) -> Vectorizer:
        df: Counter[str] = Counter()
        for doc in docs:
            df.update(doc.keys())
        terms = tuple(sorted(t for t, n in df.items() if n >= min_df))
        n = len(docs)
        idf = tuple(math.log((1 + n) / (1 + df[t])) + 1.0 for t in terms)
        return cls(terms, idf)

    def transform(self, doc: Mapping[str, int], index: Mapping[str, int] | None = None) -> Row:
        index = self.index if index is None else index
        groups: dict[str, list[tuple[int, float]]] = {}
        for term, count in doc.items():
            j = index.get(term)
            if j is None:
                continue
            value = (1.0 + math.log(count)) * self.idf[j]
            groups.setdefault(term[0], []).append((j, value))
        if not groups:
            return (), ()
        scale = 1.0 / math.sqrt(len(groups))
        cells: list[tuple[int, float]] = []
        for family in sorted(groups):
            part = groups[family]
            norm = math.sqrt(sum(v * v for _, v in part))
            cells.extend((j, scale * v / norm) for j, v in part)
        cells.sort()
        return tuple(j for j, _ in cells), tuple(v for _, v in cells)

    def transform_all(self, docs: Sequence[Mapping[str, int]]) -> list[Row]:
        index = self.index
        return [self.transform(d, index) for d in docs]
