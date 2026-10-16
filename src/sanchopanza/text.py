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
# splitter the long-document runs used (benchmarks/longdocs/sentences.py). Spanish also opens a
# sentence with an accented capital (`À-Ö`, `Ø-Þ`: Á É Í Ó Ú Ñ Ü...), `¿`, `¡` or `«`; none of
# them changed a split over QASPER, HotpotQA or any string in `fixtures/` (CHANGELOG).
# Quotes are left out: English text has `. "` and a cut there would change its sentences.
_OPENS = r"A-Z0-9(\[À-ÖØ-Þ¿¡«"
SENTENCE_BREAK = re.compile(rf"(?<=[.!?])\s+(?=[{_OPENS}])")

# Zero-width characters are not whitespace to `\s`, and Spanish Wikipedia writes a zero-width
# space after every footnote mark (58 % of its paragraphs on the B6 bench): "1900.[12]\u200b La".
# Where one stands between an end mark and the next sentence, it and the footnote marks before
# it are transparent to the cut and stay in the text, on the side they were written. A text
# with none splits exactly as before (`SENTENCE_BREAK`), and so does a footnote mark alone:
# English "2009.[12] Then" is still one piece. `[n. 3]` is no mark here: its `. 3` is a cut.
ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_FOOTNOTE = r"\[(?:\d{1,3}|nota \d{1,3})\]"
_HIDDEN_BREAK = re.compile(
    rf"[.!?](?P<tail>(?:{_FOOTNOTE}|[{ZERO_WIDTH}])*)(?P<gap>[\s{ZERO_WIDTH}]*)(?=[{_OPENS}])"
)

# Spanish abbreviations a capital follows without a new sentence: titles before a name, "p. ej.",
# page and number references, "EE. UU.". None is an English word; "Sr" is held only where it is
# a title, not after a name or a comma (English "Ben Douglas, Sr." still ends a sentence).
_HELD = "Sra|Srta|Sres|Sras|Srs|Dña|Dra|Ud|Uds|Vd|Vds|ej|pág|págs|núm|Avda|Excmo|Excma|Ilmo|Ilma|EE"
_HELD_END = re.compile(rf"(?:^|[\s(¿¡«])(?:{_HELD})\.$")
_TITLE_END = re.compile(r"(?:^|(?<=[\s(¿¡«]))Sr\.$")


def _holds(piece: str) -> bool:
    """Whether `piece` ends on an abbreviation, so the cut after it is not a sentence end."""
    if _HELD_END.search(piece):
        return True
    title = _TITLE_END.search(piece)
    if not title:
        return False
    before = piece[: title.start()].split()
    return not before or not (before[-1][0].isupper() or before[-1].endswith(","))


def _pieces(flat: str) -> list[tuple[str, str]]:
    """`(separator, piece)` at each cut of collapsed text; the separator is what the cut took
    (one space, or nothing between a zero-width character and a capital)."""
    if not any(c in flat for c in ZERO_WIDTH):
        parts = SENTENCE_BREAK.split(flat)
        return [("" if i == 0 else " ", part) for i, part in enumerate(parts)]
    out: list[tuple[str, str]] = []
    start, sep = 0, ""
    for m in _HIDDEN_BREAK.finditer(flat):
        tail, gap = m["tail"], m["gap"]
        hidden = any(c in ZERO_WIDTH for c in tail + gap)
        if not hidden and (tail or not gap):  # what SENTENCE_BREAK would not cut either
            continue
        rest = gap.lstrip(ZERO_WIDTH)  # zero-width characters right after the end stay with it
        left = m.end("gap") - len(rest)
        right = left + len(rest) - len(rest.lstrip(" "))
        out.append((sep, flat[start:left]))
        sep, start = flat[left:right], right
    out.append((sep, flat[start:]))
    return out


def split_sentences(text: str) -> list[str]:
    """Sentences of a paragraph, whitespace collapsed; nothing clever, and that is measured.

    A cut right after a held Spanish abbreviation (`_holds`) is undone: "el Sr. Pérez" is one
    sentence. Zero-width characters after the end mark do not hide the cut and are kept.
    English with no accented capital and no zero-width character splits exactly as before."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    out: list[str] = []
    for sep, part in _pieces(flat) if flat else []:
        if not part:
            continue
        if out and _holds(out[-1].rstrip(ZERO_WIDTH)):
            out[-1] = f"{out[-1]}{sep}{part}"  # put back what the cut took
        else:
            out.append(part)
    return out


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


def match_window(text: object, purpose: str, limit: int) -> str:
    """The head of a page, unless its best match to `purpose` lies past it (roadmap C6).

    `truncate(text, limit)` while the sentence sharing the most distinct words with `purpose`
    (accent-folded, stopwords out, earliest on a tie, as `_bm25_words` reads them) ends inside
    what that head shows, or no sentence shares one: then nothing changes. Past the head, the
    sentences around that match instead, whole, alternately one after and one before, with
    `[...]` where text is left out on either side; the window and its markers are no longer
    than the head and its marker (`limit` + 6 characters of whitespace-collapsed text). Unlike
    `excerpt` it keeps no head beside the window and never cuts a sentence that fits: on B6's
    Spanish articles `excerpt` put fewer answer sentences in view than the head did. Words are
    Latin-script letters and digits (`_bm25_words`), no stemming: text in other scripts finds
    no shared word and keeps the head. No model call.
    """
    if limit <= 0:
        raise ValueError("limit must be a positive number of characters")
    text = str(text or "")
    if len(text) <= limit:
        return text
    head = truncate(text, limit)
    words = set(_bm25_words(purpose))
    flat = re.sub(r"\s+", " ", text).strip()
    spans = _sentence_spans(flat)
    if not words or not spans:
        return head
    shared = [len(words & set(_bm25_words(flat[a:b]))) for a, b in spans]
    best = max(range(len(spans)), key=lambda i: (shared[i], -i))
    shown = len(re.sub(r"\s+", " ", text[:limit]).lstrip())  # the head, collapsed as `flat`
    if shared[best] == 0 or spans[best][1] <= shown:
        return head
    start, end = _grow(spans, best, max(1, limit - len(WINDOW_MARK)))
    body = flat[start:end].strip()
    return (WINDOW_MARK if start > 0 else "") + body + (" [...]" if end < len(flat) else "")


WINDOW_MARK = "[...] "  # before a window that does not start the page; " [...]" after one


def _sentence_spans(flat: str) -> list[tuple[int, int]]:
    """Character spans of `split_sentences(flat)` in whitespace-collapsed `flat`."""
    spans: list[tuple[int, int]] = []
    start = 0
    for sentence in split_sentences(flat):
        at = flat.find(sentence, start)
        if at < 0:  # the splitter changed the text: no spans, the caller keeps the head
            return []
        spans.append((at, at + len(sentence)))
        start = at + len(sentence)
    return spans


def _grow(spans: Sequence[tuple[int, int]], best: int, limit: int) -> tuple[int, int]:
    """From sentence `best`, add whole neighbours, after then before in turn (the side that
    went second goes first on the next turn), while the span stays within `limit`."""
    lo = hi = best
    size = spans[best][1] - spans[best][0]
    turn = 0
    while True:
        moved = False
        for side in (1, -1) if turn % 2 == 0 else (-1, 1):
            if side == 1 and hi + 1 < len(spans):
                add = spans[hi + 1][1] - spans[hi][1]
                if size + add <= limit:
                    hi, size, moved = hi + 1, size + add, True
                    break
            if side == -1 and lo > 0:
                add = spans[lo][0] - spans[lo - 1][0]
                if size + add <= limit:
                    lo, size, moved = lo - 1, size + add, True
                    break
        turn += 1
        if not moved:
            break
    start, end = spans[lo][0], spans[hi][1]
    return start, min(end, start + limit)


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
    plain = (text or "").lower()
    if not plain.isascii():  # ASCII has no decomposition and no combining mark: same words
        plain = unicodedata.normalize("NFKD", plain)
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
