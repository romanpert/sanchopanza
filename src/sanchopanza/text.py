"""What code can decide, code decides. Cheap deterministic checks that run before any model.

- `truncate`: state sent to a decider is trimmed; more text is more noise, not more signal.
- `quote_present`: a quotation that is not in the source is fabricated. No model call.
- `is_repeat`: two queries that share most tokens are the same query. The model only has
  to catch synonyms.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence

STOPWORDS = frozenset(
    [
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "y",
        "o",
        "en",
        "a",
        "con",
        "por",
        "para",
        "un",
        "una",
        "sobre",
        "al",
        "que",
        "se",
        "su",
        "sus",
        "segun",
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "or",
        "with",
        "by",
        "from",
        "at",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
    ]
)
JACCARD_REPEAT = 0.7


# After `.`, `!` or `?` and whitespace, before an upper-case letter, a digit, `(` or `[`: the
# splitter the long-document runs used (benchmarks/longdocs/sentences.py).
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


def split_sentences(text: str) -> list[str]:
    """Sentences of a paragraph, whitespace collapsed; nothing clever, and that is measured."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    return [part for part in SENTENCE_BREAK.split(flat) if part] if flat else []


def truncate(text: object, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + " [...]"


def excerpt(text: object, purpose: str, limit: int) -> str:
    """A representative slice of a long document, for a decision about its relevance.

    Cutting from the head is wrong on a long document: the part that answers the purpose is
    often in the middle, and the decider then judges relevance on a preamble that genuinely
    does not mention it. The end-to-end benchmark caught exactly that (`benchmarks/ab`): on a
    10,000-character document triage dropped the one page holding the answer, the agent
    re-fetched it, hit its turn cap and the run cost twice as much for no answer.

    So a document longer than the limit is sent as its head plus the window with the most
    hits for the words of the purpose, joined by the same `[...]` marker `truncate` uses.
    Deterministic, no model call, no extra tokens. A document that already fits is returned
    unchanged, so nothing that fit before changes behaviour, including every bench case.
    """
    text = str(text or "")
    if len(text) <= limit:
        return text
    marker = " [...] "
    head_len = limit // 3
    window_len = max(1, limit - head_len - len(marker))
    head, rest = text[:head_len], text[head_len:]
    words = tokens(purpose)
    if not words or len(rest) <= window_len:
        return head + marker + rest[-window_len:]

    lowered = rest.lower()
    step = max(1, window_len // 4)
    best_start, best_score = 0, -1
    for start in range(0, len(rest) - window_len + 1, step):
        chunk = lowered[start : start + window_len]
        score = sum(chunk.count(w) for w in words)
        if score > best_score:
            best_start, best_score = start, score
    return head + marker + rest[best_start : best_start + window_len]


def normalize(text: str) -> str:
    """Collapse whitespace and straighten typographic quotes: the only tolerated edits."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    return flat.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))


def quote_present(quote: str, source: str) -> bool:
    quote_n, source_n = normalize(quote), normalize(source)
    return bool(quote_n) and quote_n.lower() in source_n.lower()


def tokens(text: str) -> frozenset[str]:
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return frozenset(t for t in re.findall(r"[a-z0-9/-]+", plain) if t not in STOPWORDS)


def is_repeat(query: str, previous: Iterable[str], *, threshold: float = JACCARD_REPEAT) -> bool:
    """True when the query shares almost all its tokens with an earlier one."""
    current = tokens(query)
    if not current:
        return False
    for earlier in previous:
        other = tokens(earlier)
        if other and len(current & other) / len(current | other) >= threshold:
            return True
    return False


def mention_present(mention: str, source: str, *, ratio: float = 0.5) -> bool:
    """Is this entity mention in the text at all? Deterministic, before any model call.

    A triple whose subject or object does not appear in the chunk it was extracted from was
    invented by the extractor, and no decider has to be asked about it. The check is looser
    than `quote_present` because extractors canonicalize: `Inversiones Delta S.A.` may be
    written `Inversiones Delta` in the text. The whole normalized string counts as present,
    and so does any mention at least `ratio` of whose content tokens appear.
    """
    mention_n, source_n = normalize(mention), normalize(source)
    if not mention_n:
        return False
    if mention_n.lower() in source_n.lower():
        return True
    wanted = tokens(mention_n)
    if not wanted:
        return False
    have = tokens(source_n)
    return len(wanted & have) / len(wanted) >= ratio


def _bm25_words(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", (text or "").lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9_]+", plain) if t not in STOPWORDS and len(t) > 1]


class BM25Index:
    """Okapi BM25 over documents tokenised once, then asked any number of queries.

    The package's one BM25: `bm25_scores` is a one-query wrapper over it, and archive search,
    memory recall, the free arrival cut and repository search all go through it. Postings keep
    a query over a large repository to the documents that hold its words.
    """

    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.lengths: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = {}
        for i, doc in enumerate(docs):
            words = _bm25_words(doc)
            self.lengths.append(len(words))
            counts: dict[str, int] = {}
            for word in words:
                counts[word] = counts.get(word, 0) + 1
            for word, count in counts.items():
                self.postings.setdefault(word, []).append((i, count))
        self.n = len(self.lengths)
        self.average = (sum(self.lengths) / self.n) if self.n else 1.0
        self.average = self.average or 1.0

    def scores(self, query: str) -> list[float]:
        out = [0.0] * self.n
        k1, b = self.k1, self.b
        for word in set(_bm25_words(query)):
            posting = self.postings.get(word)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for i, tf in posting:
                norm = 1 - b + b * self.lengths[i] / self.average
                out[i] += idf * tf * (k1 + 1) / (tf + k1 * norm)
        return out

    def top(self, query: str, k: int) -> list[tuple[int, float]]:
        """The `k` best documents with a score above zero, best first."""
        scores = self.scores(query)
        ranked = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: -scores[i])
        return [(i, scores[i]) for i in ranked[: max(0, k)]]


def bm25_scores(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Okapi BM25 of each document against the query. Code, no model: it proposes candidates.

    The same formula as the benches' (`benchmarks/triage_sets/run.py`), with the package's
    accent-folding tokenizer, so Spanish and English memories score alike.
    """
    return BM25Index(docs, k1=k1, b=b).scores(query) if docs else []
