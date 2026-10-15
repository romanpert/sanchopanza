"""A Wikipedia article as paragraphs, at a pinned revision, for the B6 long-document bench.

The article comes from the MediaWiki parse API (`action=parse`), by title the first time and by
revision id (`oldid`) after that, so a rebuild reads the same text. Each raw response is cached
on disk under the data directory, outside the repository, and never committed: Wikipedia text is
CC BY-SA 4.0, and the builder downloads it again from the revision ids in the manifest.

Only `<p>` elements outside tables, figures, navigation boxes and reference lists are paragraphs;
footnote markers, edit links, styles and maths markup are dropped. Text is whitespace-collapsed,
the same normalisation the bench applies to MLQA contexts.

Downloaded HTML is untrusted data: it is parsed with the standard library's tokenizer into plain
strings and nothing in it is executed or followed.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

# A contact Wikimedia asks for: the project, never a person.
USER_AGENT = "sanchopanza-b6-bench/0.1 (+https://github.com/romanpert/sanchopanza)"
API = "https://{lang}.wikipedia.org/w/api.php"
PAUSE_S = 1.0  # one request a second, Wikimedia's polite rate for an unauthenticated client
TIMEOUT_S = 30
MAX_BYTES = 8_000_000  # an article response over this is refused, not parsed

VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
     "source", "track", "wbr"}
)  # fmt: skip
SKIP_TAGS = frozenset({"table", "figure", "style", "script", "math", "noscript", "audio"})
SKIP_CLASSES = (
    "mw-editsection", "navbox", "reflist", "reference", "mw-references-wrap", "noprint",
    "metadata", "mwe-math", "hatnote", "infobox", "thumb", "gallery",
)  # fmt: skip
HEADINGS = frozenset({"h2", "h3", "h4"})


# Spanish Wikipedia writes a zero-width space after every footnote mark (58 % of the Spanish
# paragraphs of this bench, 72 of 28,681 English ones). It is not whitespace to `\s`, so
# `text.split_sentences` does not break at ".​ " and glues the sentences around it
# (68,479 Spanish sentences with them, 83,616 without). Dropped here, so the bench compares
# languages and not this mark; the package itself is unchanged.
ZERO_WIDTH = "​‌‍⁠﻿"
_DROP = str.maketrans("", "", ZERO_WIDTH)
# A footnote mark left in the text: MLQA's Spanish paragraphs keep them (1,409 of 3,000 pages
# of this bench, 81 of the English ones), today's HTML holds them in `<sup>`. Narrow on purpose:
# a number, "n." or "nota" and a number, in brackets; other bracketed text is left alone.
MARK = re.compile(r"\[(?:\d{1,3}|n\. ?\d{1,3}|nota \d{1,3})\]")


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", MARK.sub("", (text or "").translate(_DROP))).strip()


@dataclass(frozen=True, slots=True)
class Article:
    lang: str
    title: str
    revid: int
    paragraphs: tuple[tuple[str, str], ...]  # (section, text)


class _Paragraphs(HTMLParser):
    """Collects `(section, text)` for each `<p>` that is not inside a skipped element."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str]] = []  # (tag, role): "skip", "p", "h" or ""
        self.skip = 0
        self.section = ""
        self.buffer: list[str] = []
        self.heading: list[str] = []
        self.out: list[tuple[str, str]] = []

    def _open(self, role: str) -> bool:
        return any(r == role for _, r in self.stack)

    @staticmethod
    def _skipped(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        classes = " ".join(v or "" for k, v in attrs if k == "class")
        return tag in SKIP_TAGS or any(name in classes for name in SKIP_CLASSES)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            if tag == "br":
                self.handle_data(" ")
            return
        if tag == "p" and self._open("p"):
            self.handle_endtag("p")  # a new paragraph closes the open one, as in HTML
        role = ""
        if self._skipped(tag, attrs):
            role = "skip"
            self.skip += 1
        elif not self.skip and tag == "p" and not self._open("p"):
            role, self.buffer = "p", []
        elif not self.skip and tag in HEADINGS and not self._open("h"):
            role, self.heading = "h", []
        self.stack.append((tag, role))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":  # a self-closing tag holds no text; a line break reads as a space
            self.handle_data(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID or not any(t == tag for t, _ in self.stack):
            return
        while self.stack:  # close up to the matching tag: HTML may leave some unclosed
            open_tag, role = self.stack.pop()
            if role == "skip":
                self.skip -= 1
            elif role == "p":
                text = collapse("".join(self.buffer))
                if text:
                    self.out.append((self.section, text))
            elif role == "h":
                self.section = collapse("".join(self.heading))
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self._open("h"):
            self.heading.append(data)
        elif self._open("p"):
            self.buffer.append(data)


def paragraphs(html: str) -> list[tuple[str, str]]:
    """The article's paragraphs as `(section, text)`, in page order. Pure: no network."""
    parser = _Paragraphs()
    parser.feed(html)
    parser.close()
    return parser.out


def _get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 - fixed https host
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError(f"response over {MAX_BYTES} bytes: refused")
    return json.loads(body.decode("utf-8"))


def _url(lang: str, *, title: str | None = None, revid: int | None = None) -> str:
    params = {"action": "parse", "prop": "revid|text", "format": "json", "formatversion": "2",
              "disabletoc": "1", "disableeditsection": "1", "redirects": "1"}  # fmt: skip
    if revid is not None:
        params["oldid"] = str(revid)
        params.pop("redirects")
    else:
        params["page"] = str(title)
    if lang not in ("es", "en"):
        raise ValueError(f"language {lang!r} is not one of this bench's")
    return API.format(lang=lang) + "?" + urllib.parse.urlencode(params)


class Fetcher:
    """Parse-API responses cached under `cache`: a cached revision is never fetched again."""

    def __init__(self, cache: Path, *, offline: bool = False) -> None:
        self.cache = Path(cache)
        self.offline = offline
        self._last = 0.0
        self.fetched = 0

    def _path(self, lang: str, revid: int) -> Path:
        return self.cache / lang / f"{revid}.json.gz"

    def _fetch(self, url: str) -> dict:
        if self.offline:
            raise LookupError("offline: not in the cache")
        wait = self._last + PAUSE_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.fetched += 1
        return _get(url)

    def _titles(self, lang: str) -> dict[str, int]:
        path = self.cache / lang / "titles.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _remember(self, lang: str, title: str, revid: int) -> None:
        titles = {**self._titles(lang), title: revid}
        path = self.cache / lang / "titles.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(titles, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def article(self, lang: str, *, title: str | None = None, revid: int | None = None) -> Article:
        """By `revid` when given, else the revision of `title` first fetched (the current one
        then); a cached revision is read from disk."""
        if revid is None and title is not None:
            revid = self._titles(lang).get(title)
            if revid is None:
                found = self._article(lang, title=title, revid=None)
                self._remember(lang, title, found.revid)
                return found
        return self._article(lang, title=title, revid=revid)

    def _article(self, lang: str, *, title: str | None, revid: int | None) -> Article:
        if revid is not None and self._path(lang, revid).exists():
            data = json.loads(gzip.decompress(self._path(lang, revid).read_bytes()))
        else:
            data = self._fetch(_url(lang, title=title, revid=revid))
            if "parse" not in data:
                code = (data.get("error") or {}).get("code", "no parse")
                raise LookupError(f"{lang}:{title or revid}: {code}")
            target = self._path(lang, int(data["parse"]["revid"]))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode()))
        parse = data["parse"]
        return Article(
            lang=lang,
            title=str(parse["title"]),
            revid=int(parse["revid"]),
            paragraphs=tuple(paragraphs(str(parse["text"]))),
        )
