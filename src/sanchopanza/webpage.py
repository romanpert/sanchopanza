"""A web page to the passages a purpose needs: code only, no model, no network.

Claude Code's WebFetch hands every page to a Haiku reader that writes a summary; on free FRAMES
sessions that reader costs about 0.024 USD a page, and its summary held the task's answer in 22
of the 71 pages that had it. The same pages cut here into chunks under their headings and ranked
by BM25 against the purpose the agent declares held it in 66 of 71 at about 1,350 tokens a page
(docs/results/2026-10-05-browse-frames/, "substitution: fetch by passages"). The model that asked
reads the passages itself, so they must be few: the budget is in characters and the page's first
chunk (its lead) is always kept.

- `blocks_of` parses HTML with the standard library: scripts, styles and page chrome (`nav`,
  `footer`, forms) dropped, one block per paragraph, list item, table row (cells joined by
  ` | `) or heading.
- `chunks_of` joins consecutive blocks of one section up to `size` characters, each chunk
  carrying its heading; a paragraph longer than twice that is cut by sentences.
- `pick` keeps the lead (when it fits a quarter of the budget), then the best BM25 chunks
  (heading and text) that fit the budget.
- `passages` renders them in page order, `[...]` over each gap, headings once.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser

from .text import BM25Index, split_sentences

CHUNK_CHARS = 700
DEFAULT_BUDGET = 8_000
LEAD_MIN = 200  # a page's first chunk this long is its lead; shorter ones are menus and links
GAP = "[...]"

_SKIP = frozenset(
    [
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "head",
        "nav",
        "footer",
        "form",
        "button",
        "select",
        "iframe",
        "object",
        "canvas",
        "math",
    ]
)
_BLOCK = frozenset(
    [
        "p",
        "div",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "ul",
        "ol",
        "dl",
        "dt",
        "dd",
        "section",
        "article",
        "br",
        "blockquote",
        "pre",
        "figcaption",
        "caption",
        "header",
        "main",
        "aside",
        "tbody",
        "thead",
        "hr",
    ]
)
_HEADINGS = frozenset(["h1", "h2", "h3", "h4", "h5", "h6"])
_CELLS = frozenset(("td", "th"))
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_.:-]+)""", re.I)
_HEADER_CHARSET = re.compile(r"charset\s*=\s*([A-Za-z0-9_.:-]+)", re.I)


@dataclass(frozen=True)
class Block:
    text: str
    heading: str
    kind: str  # "h", "row" or "text"
    table_head: str = ""  # version 2: the header row of the table a row belongs to


@dataclass(frozen=True)
class Chunk:
    heading: str
    text: str


@dataclass(frozen=True)
class Page:
    title: str
    chunks: tuple[Chunk, ...]
    disambiguation: bool = False  # version 2: the page lists meanings of a name

    @property
    def total(self) -> int:
        return sum(len(c.text) for c in self.chunks)


@dataclass(frozen=True)
class Passages:
    title: str
    text: str
    shown: int
    total: int
    picked: int
    chunks: int

    def header(self) -> str:
        if self.shown >= self.total:
            return f"Whole page: {self.total:,} characters."
        return (
            f"Passages for the purpose: {self.picked} of {self.chunks} chunks, "
            f"{self.shown:,} of {self.total:,} characters. Ask again with another purpose "
            "for other passages."
        )


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.buf: list[str] = []
        self.blocks: list[Block] = []
        self.heading = ""
        self.in_heading = False
        self.in_row = False
        self.in_title = False
        self.title = ""

    def flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip(" |")
        self.buf = []
        if not text:
            return
        if self.in_heading:
            self.heading = text
            self.blocks.append(Block(text, text, "h"))
        else:
            self.blocks.append(Block(text, self.heading, "row" if self.in_row else "text"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in _BLOCK:
            self.flush()
        if tag in _HEADINGS:
            self.in_heading = True
        elif tag == "tr":
            self.in_row = True
        elif tag in _CELLS:
            self.buf.append(" | ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.skip and tag in _BLOCK:
            self.flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _BLOCK:
            self.flush()
        if tag in _HEADINGS:
            self.in_heading = False
        elif tag == "tr":
            self.in_row = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        elif not self.skip:
            self.buf.append(data)


def decode(body: bytes, content_type: str = "") -> str:
    """Bytes to text: the charset of the header, else of a `<meta>`, else UTF-8 (replacing)."""
    for found in (_HEADER_CHARSET.search(content_type or ""), _META_CHARSET.search(body[:4096])):
        if found:
            name = found.group(1)
            name = name.decode("ascii", "replace") if isinstance(name, bytes) else name
            try:
                return body.decode(name, errors="replace")
            except LookupError:
                continue
    return body.decode("utf-8", errors="replace")


def blocks_of(html: str) -> tuple[str, list[Block]]:
    parser = _Parser()
    parser.feed(html)
    parser.close()
    parser.flush()
    return re.sub(r"\s+", " ", parser.title).strip(), parser.blocks


def _pieces(text: str, size: int) -> list[str]:
    if len(text) <= size * 2:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in split_sentences(text) or [text]:
        while len(sentence) > size * 2:  # no sentence break at all: cut it
            pieces, current = [*pieces, *([current] if current else [])], ""
            pieces.append(sentence[:size])
            sentence = sentence[size:]
        if current and len(current) + len(sentence) > size:
            pieces.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    return [*pieces, current] if current else pieces


def chunks_of(blocks: Sequence[Block], size: int = CHUNK_CHARS) -> list[Chunk]:
    """Consecutive blocks of one section joined up to `size` characters, under their heading."""
    out: list[Chunk] = []
    current: list[str] = []
    heading = ""
    length = 0
    for block in blocks:
        if block.kind == "h" or block.heading != heading:
            if current:
                out.append(Chunk(heading, "\n".join(current)))
            current, length = [], 0
            heading = block.heading
            if block.kind == "h":
                continue
        for piece in _pieces(block.text, size):
            if length and length + len(piece) > size:
                out.append(Chunk(heading, "\n".join(current)))
                current, length = [], 0
            current.append(piece)
            length += len(piece) + 1
    if current:
        out.append(Chunk(heading, "\n".join(current)))
    return out


def page_from_html(html: str, size: int = CHUNK_CHARS) -> Page:
    title, blocks = blocks_of(html)
    return Page(title, tuple(chunks_of(blocks, size)))


def page_from_text(text: str, *, title: str = "", size: int = CHUNK_CHARS) -> Page:
    """Plain text, JSON or CSV: one block per non-empty line, joined into chunks."""
    blocks = [Block(line.strip(), "", "text") for line in text.splitlines() if line.strip()]
    return Page(title, tuple(chunks_of(blocks, size)))


def pick(purpose: str, chunks: Sequence[Chunk], budget: int, lead: int = 1) -> list[int]:
    """Indices, in page order: the first `lead` chunks of at least `LEAD_MIN` characters (not a
    menu or a skip link; each only while the lead stays within a quarter of the budget), then
    the best BM25 chunks that fit."""
    if not chunks:
        return []
    picked: list[int] = []
    firsts = [i for i, c in enumerate(chunks) if len(c.text) >= LEAD_MIN][: max(0, lead)]
    for i in firsts:
        if sum(len(chunks[j].text) for j in [*picked, i]) <= budget // 4:
            picked.append(i)
    used = sum(len(chunks[i].text) for i in picked)
    index = BM25Index([f"{c.heading}\n{c.text}" for c in chunks])
    for i, _score in index.top(purpose, len(chunks)):
        if i in picked:
            continue
        cost = len(chunks[i].text)
        if used + cost <= budget:
            picked.append(i)
            used += cost
        elif used >= budget * 0.8:
            break
    return sorted(picked)


def render(page: Page, picked: Sequence[int]) -> str:
    lines: list[str] = []
    last_heading, previous = None, -1
    for i in picked:
        chunk = page.chunks[i]
        if i != previous + 1:
            lines.append(GAP)
        if chunk.heading and chunk.heading != last_heading:
            lines.append(f"## {chunk.heading}")
            last_heading = chunk.heading
        lines.append(chunk.text)
        previous = i
    if picked and previous != len(page.chunks) - 1:
        lines.append(GAP)
    return "\n".join(lines)


def passages(page: Page, purpose: str, budget: int = DEFAULT_BUDGET) -> Passages:
    """The chunks `purpose` needs under `budget` characters, or the whole page if it fits."""
    total = page.total
    whole = total <= budget
    picked = list(range(len(page.chunks))) if whole else pick(purpose, page.chunks, budget)
    shown = sum(len(page.chunks[i].text) for i in picked)
    return Passages(page.title, render(page, picked), shown, total, len(picked), len(page.chunks))
