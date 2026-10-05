"""Version 2 of `sanchopanza.webpage`: passages by sections, with the page's chrome stripped.

Switched on for `fetch_passages` by `SANCHOPANZA_FETCH_VERSION=2`; version 1 stays as it was
measured. What the fetch pilot's misses asked for (docs/results/2026-10-05-browse-frames/,
"fetch pilot"), each a rule here:

- Chrome goes before cutting: an element whose role, id or class names navigation, a menu, a
  language list, a skip link, an edit mark, a navigation box, a category list or a citation
  mark is dropped with everything inside it (`_is_chrome`); so are left-over `[edit]` and `[12]`
  marks in the text. Wikipedia pages under the budget came back with 40 language names.
- A heading carries its parents (`Filmography > Television`), so a section is found by any of
  its headings and its subsections come with it.
- A table cut into several chunks repeats its header row at the top of each.
- A section whose heading shares a word with the purpose is kept together, in page order, up to
  `SECTION_SHARE` of the budget; when it does not fit, its first chunk and its best chunks by
  BM25. On the pilot a purpose that named a section got its heading and a reference title, not
  the row that stated the fact.
- Back matter (references, notes, external links, further reading) is left out unless the
  purpose shares a word with its heading. "See also" stays: a short list of related titles,
  and on one replayed page the only place the answer was.
- `Page.disambiguation` says the page lists meanings of a name, so the tool can say so.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from html.parser import HTMLParser

from .text import BM25Index
from .webpage import (
    _BLOCK,
    _CELLS,
    _HEADINGS,
    _SKIP,
    CHUNK_CHARS,
    DEFAULT_BUDGET,
    LEAD_MIN,
    Block,
    Chunk,
    Page,
    Passages,
    _pieces,
    render,
)

SECTION_SHARE = 0.75  # the most of the budget sections named by the purpose may take
PATH_SEP = " > "
_VOID = frozenset(
    ["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"]
)
_CHROME_ROLES = frozenset(
    ["navigation", "banner", "contentinfo", "search", "menu", "menubar", "toolbar", "dialog"]
)
_CHROME_TOKENS = frozenset(
    [
        # MediaWiki
        "mw-editsection", "mw-jump-link", "navbox", "navbox-styles", "navbar", "catlinks",
        "mw-hidden-catlinks", "printfooter", "mw-indicators", "noprint", "sistersitebox",
        "authority-control", "mw-cite-backlink", "cite-bracket", "reference", "mw-ref", "ambox",
        "toc", "sitesub", "contentsub", "contentsub2", "mw-navigation", "mw-head", "mw-panel",
        "mw-footer", "p-lang-btn", "mw-portlet", "mw-portlet-lang", "interlanguage-link",
        "vector-header", "vector-header-container", "vector-main-menu", "vector-page-toolbar",
        "vector-column-start", "vector-column-end", "vector-dropdown", "vector-menu",
        "vector-toc", "vector-sticky-header", "vector-pinned-container",
        "vector-unpinned-container", "vector-settings", "vector-search-box",
        "vector-typeahead-search-container", "vector-user-links", "vector-page-tools",
        "vector-appearance", "mw-redirectedfrom", "sidebar",
        # elsewhere
        "nav", "menu", "navigation", "breadcrumb", "breadcrumbs", "skip-link",
        "skip-to-content", "sr-only", "visually-hidden", "screen-reader-text", "cookie-banner",
        "cookie-notice", "share", "sharing", "social-share", "newsletter", "advertisement",
        "site-header", "site-footer", "footer",
    ]
)  # fmt: skip
_CHROME_PREFIXES = ("cdx-", "interlanguage", "navbox", "uls-", "cookie")
_MARKS = re.compile(
    r"\[(?:\d{1,3}|[a-z]{1,2}|edit|citation needed|note \d+|nb \d+)\]|\[\s*\]", re.IGNORECASE
)
_MAY_REFER = re.compile(r"\bmay (?:also )?refer to:?\s*$", re.IGNORECASE)
_BACK_MATTER = (
    "references",
    "notes",
    "citations",
    "footnotes",
    "external links",
    "further reading",
    "works cited",
    "sources",
    "explanatory notes",
    "general and cited",
    "cited sources",
)
_HEADING_STOP = frozenset(
    [
        "the", "of", "and", "in", "a", "an", "to", "for", "on", "with", "by", "from", "at", "as",
        "is", "are", "was", "were", "be", "its", "it", "his", "her", "their", "this", "that",
        "what", "which", "who", "whom", "when", "where", "how", "why", "find", "check", "list",
        "page", "article", "about", "information", "details", "get", "see", "look", "more",
        "other", "all", "any", "some",
    ]
)  # fmt: skip


def _hides(name: str, value: str) -> bool:
    if name == "aria-hidden":
        return value.lower() == "true"
    if name == "style":
        return "display:none" in value.replace(" ", "").lower()
    return name == "hidden"


def _tokens(attrs: Sequence[tuple[str, str | None]]) -> tuple[set[str], str, bool]:
    found: set[str] = set()
    role, hidden = "", False
    for name, value in attrs:
        value = value or ""
        if name in ("class", "id"):
            found.update(value.lower().split())
        elif name == "role":
            role = value.lower().strip()
        hidden = hidden or _hides(name, value)
    return found, role, hidden


def _is_chrome(attrs: Sequence[tuple[str, str | None]]) -> bool:
    found, role, hidden = _tokens(attrs)
    if hidden or role in _CHROME_ROLES:
        return True
    return any(t in _CHROME_TOKENS or t.startswith(_CHROME_PREFIXES) for t in found)


def _is_disambiguation_mark(tag: str, attrs: Sequence[tuple[str, str | None]]) -> bool:
    found, _role, _hidden = _tokens(attrs)
    if any("disambig" in t for t in found):
        return True
    return tag == "link" and "disambiguation" in str(dict(attrs).get("rel") or "").lower()


class _Parser(HTMLParser):
    """Blocks as version 1 makes them, with chrome dropped, heading paths and table headers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.chrome: list[object] = []  # [tag, depth] while inside a chrome element
        self.buf: list[str] = []
        self.blocks: list[Block] = []
        self.stack: list[tuple[int, str]] = []  # open headings: (level, text)
        self.level = 0  # the heading being read, 0 outside one
        self.in_row = False
        self.row_th = self.row_td = 0
        self.tables: list[str] = []  # header row of each open table ("" until seen)
        self.in_title = False
        self.title = ""
        self.disambiguation = False

    def path(self) -> str:
        inner = [t for level, t in self.stack if level > 1]
        return PATH_SEP.join(inner) if inner else PATH_SEP.join(t for _l, t in self.stack)

    def flush(self) -> None:
        text = re.sub(r"\s+", " ", _MARKS.sub("", "".join(self.buf))).strip(" |")
        self.buf = []
        if not text:
            return
        if self.level:
            self.stack = [*(s for s in self.stack if s[0] < self.level), (self.level, text)]
            self.blocks.append(Block(text, self.path(), "h"))
            return
        if self.in_row:
            head = self.tables[-1] if self.tables else ""
            if self.row_th >= 2 and not self.row_td and self.tables and not head:
                self.tables = [*self.tables[:-1], text]
                head = ""
            self.blocks.append(Block(text, self.path(), "row", "" if head == text else head))
            return
        if len(self.blocks) < 12 and _MAY_REFER.search(text):
            self.disambiguation = True
        self.blocks.append(Block(text, self.path(), "text"))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True
        if _is_disambiguation_mark(tag, attrs):
            self.disambiguation = True
        if self.chrome:
            if tag == self.chrome[0]:
                self.chrome[1] = int(self.chrome[1]) + 1
            return
        if self.skip or tag in _SKIP:
            self.skip += tag in _SKIP
            return
        if tag not in _VOID and tag != "title" and _is_chrome(attrs):
            if tag in _BLOCK:  # an inline mark (a citation's sup) must not cut its sentence
                self.flush()
            self.chrome = [tag, 1]
            return
        self._open(tag)

    def _open(self, tag: str) -> None:
        if tag in _BLOCK:
            self.flush()
        if tag in _HEADINGS:
            self.level = int(tag[1])
        elif tag == "tr":
            self.in_row, self.row_th, self.row_td = True, 0, 0
        elif tag == "table":
            self.tables = [*self.tables, ""]
        elif tag in _CELLS:
            self.row_th += tag == "th"
            self.row_td += tag == "td"
            self.buf.append(" | ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.chrome and not self.skip and tag in _BLOCK:
            self.flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if self.chrome:
            if tag == self.chrome[0]:
                self.chrome[1] = int(self.chrome[1]) - 1
                if not self.chrome[1]:
                    self.chrome = []
            return
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _BLOCK:
            self.flush()
        if tag in _HEADINGS:
            self.level = 0
        elif tag == "tr":
            self.in_row = False
        elif tag == "table" and self.tables:
            self.tables = self.tables[:-1]

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        elif not self.skip and not self.chrome:
            self.buf.append(data)


def blocks_of(html: str) -> tuple[str, list[Block], bool]:
    """The title, the blocks and whether the page is a disambiguation page."""
    parser = _Parser()
    parser.feed(html)
    parser.close()
    parser.flush()
    title = re.sub(r"\s+", " ", parser.title).strip()
    return title, parser.blocks, parser.disambiguation


def chunks_of(blocks: Sequence[Block], size: int = CHUNK_CHARS) -> list[Chunk]:
    """As version 1, and a chunk that starts inside a table opens with the table's header row."""
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
            if not current and block.table_head:
                current, length = [block.table_head], len(block.table_head) + 1
            current.append(piece)
            length += len(piece) + 1
    if current:
        out.append(Chunk(heading, "\n".join(current)))
    return out


def page_from_html(html: str, size: int = CHUNK_CHARS) -> Page:
    title, blocks, disambiguation = blocks_of(html)
    return Page(title, tuple(chunks_of(blocks, size)), disambiguation)


def _words(text: str) -> set[str]:
    out = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) < 3 or word in _HEADING_STOP:
            continue
        out.add(word[:-1] if len(word) > 3 and word.endswith("s") else word)
    return out


def _is_back_matter(heading: str) -> bool:
    return any(part.lower().startswith(_BACK_MATTER) for part in heading.split(PATH_SEP) if part)


def eligible(purpose: str, chunks: Sequence[Chunk]) -> list[int]:
    """Chunks that are not back matter, or whose back-matter heading the purpose names."""
    wanted = _words(purpose)
    return [
        i
        for i, c in enumerate(chunks)
        if not _is_back_matter(c.heading) or _words(c.heading) & wanted
    ]


def _sections(purpose: str, chunks: Sequence[Chunk], allowed: Sequence[int]) -> list[list[int]]:
    """Groups of chunk indices under the outermost heading that shares a word with the purpose,
    the heading with most shared words first, then page order."""
    wanted = _words(purpose)
    groups: dict[tuple[str, ...], list[int]] = {}
    hits: dict[tuple[str, ...], int] = {}
    for i in allowed:
        path = tuple(p for p in chunks[i].heading.split(PATH_SEP) if p)
        for depth, part in enumerate(path):
            shared = _words(part) & wanted
            if shared:
                key = path[: depth + 1]
                groups.setdefault(key, []).append(i)
                hits[key] = len(shared)
                break
    order = sorted(groups, key=lambda k: (-hits[k], groups[k][0]))
    return [groups[k] for k in order]


def pick(purpose: str, chunks: Sequence[Chunk], budget: int, lead: int = 1) -> list[int]:
    """Indices in page order: the lead (as version 1), the sections the purpose names, then the
    best BM25 chunks that fit; back matter only when the purpose names it."""
    allowed = eligible(purpose, chunks)
    if not allowed:
        return []
    picked: list[int] = []
    for i in [i for i in allowed if len(chunks[i].text) >= LEAD_MIN][: max(0, lead)]:
        if sum(len(chunks[j].text) for j in [*picked, i]) <= budget // 4:
            picked.append(i)
    used = sum(len(chunks[i].text) for i in picked)
    index = BM25Index([f"{c.heading}\n{c.text}" for c in chunks])
    ranked = [i for i, _s in index.top(purpose, len(chunks)) if i in set(allowed)]
    cap = int(budget * SECTION_SHARE)
    for section in _sections(purpose, chunks, allowed):
        rest = [i for i in section if i not in picked]
        if used + sum(len(chunks[i].text) for i in rest) <= cap:
            picked, used = [*picked, *rest], used + sum(len(chunks[i].text) for i in rest)
            continue
        inside = [rest[0], *(i for i in ranked if i in rest and i != rest[0])] if rest else []
        for i in inside:
            if used + len(chunks[i].text) <= cap:
                picked.append(i)
                used += len(chunks[i].text)
    for i in ranked:
        if i in picked:
            continue
        if used + len(chunks[i].text) <= budget:
            picked.append(i)
            used += len(chunks[i].text)
        elif used >= budget * 0.8:
            break
    return sorted(picked)


def passages(page: Page, purpose: str, budget: int = DEFAULT_BUDGET) -> Passages:
    """The chunks `purpose` needs under `budget` characters, or every eligible chunk if they fit."""
    allowed = eligible(purpose, page.chunks)
    total = sum(len(page.chunks[i].text) for i in allowed)
    picked = allowed if total <= budget else pick(purpose, page.chunks, budget)
    shown = sum(len(page.chunks[i].text) for i in picked)
    return Passages(page.title, render(page, picked), shown, total, len(picked), len(allowed))
