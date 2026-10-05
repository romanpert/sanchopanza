"""Documents to pages whose chunks carry their place: code only, no model, no network.

`webpage` and `webpage_v2` cut web pages. An agent working over a knowledge base also meets
PDFs, Word documents, spreadsheets, CSV and plain text, and a passage it is handed has to say
where it stands so it can be cited. Here every chunk's heading is that place:

- PDF (`pypdf`, the optional `sanchopanza[documents]` extra): `p. N`. Line-end hyphens are
  joined and a page's lines become paragraphs.
- DOCX (standard library: it is a zip of XML): the heading path from the paragraph styles
  (`Results > By region`); table rows with cells joined by ` | `, the table's first row
  repeated at the top of every chunk it is cut into.
- XLSX (standard library) and CSV/TSV: `Sheet > rows 2-21`, groups of `ROWS_PER_PLACE` rows,
  the header row at the top of every chunk.
- Markdown and plain text: the `#` heading path, or `lines 1-40` when there are no headings.
- HTML: `webpage_v2` (chrome stripped, heading paths).

`kind_of` reads the kind from the bytes first (a PDF's magic, an HTML doctype), then the
content type, then the extension; `page_from_bytes` raises `Unreadable` with a reason for
anything else.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from . import webpage, webpage_v2
from .webpage import CHUNK_CHARS, Block, Page

MAX_FILE_BYTES = 60_000_000
MAX_ROWS = 50_000
MAX_PART_BYTES = 200_000_000  # one XML part of a docx or xlsx, uncompressed (a zip bomb stops here)
ROWS_PER_PLACE = 20
LINES_PER_PLACE = 40
PATH_SEP = webpage_v2.PATH_SEP

_EXT = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".tsv": "tsv",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    **dict.fromkeys(
        (".txt", ".md", ".markdown", ".rst", ".json", ".jsonl", ".xml", ".log", ".yaml", ".yml"),
        "text",
    ),
}
_TYPES = (
    ("application/pdf", "pdf"),
    ("wordprocessingml", "docx"),
    ("spreadsheetml", "xlsx"),
    ("text/csv", "csv"),
    ("text/tab-separated-values", "tsv"),
    ("html", "html"),
    ("text/", "text"),
    ("json", "text"),
    ("xml", "text"),
)
SUFFIXES = frozenset(_EXT)
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_HEADING_STYLE = re.compile(r"(?:heading|t[ií]?tulo|berschrift|titre)\s*(\d)", re.IGNORECASE)
_MD_HEADING = re.compile(r"^(#{1,6})\s+(\S.*?)\s*#*\s*$")
_HYPHEN = re.compile(r"(\w)-\n(\w)")


class Unreadable(ValueError):
    """The document is not one this module reads, with the reason."""


def kind_of(name: str = "", content_type: str = "", head: bytes = b"") -> str:
    """`pdf`, `docx`, `xlsx`, `csv`, `tsv`, `html`, `text`, or "" for anything else."""
    start = head[:512].lstrip().lower()
    if start.startswith(b"%pdf"):
        return "pdf"
    if start.startswith((b"<!doctype html", b"<html")):
        return "html"
    ctype = (content_type or "").split(";")[0].strip().lower()
    for marker, kind in _TYPES if ctype and ctype != "application/octet-stream" else ():
        if marker in ctype:
            return kind
    return _EXT.get(Path(name.split("?", 1)[0]).suffix.lower(), "")


def _pypdf() -> Any:
    try:
        import pypdf
    except ImportError:
        return None
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings, one per font, on stderr
    return pypdf


def pdf_text_blocks(text: str) -> list[str]:
    """A PDF page's extracted text to paragraphs: hyphens at line ends joined, lines of one
    paragraph (no blank line between them) joined with spaces."""
    joined = _HYPHEN.sub(r"\1\2", text.replace("\r\n", "\n"))
    paragraphs = re.split(r"\n\s*\n", joined)
    out = [re.sub(r"\s+", " ", p).strip() for p in paragraphs]
    return [p for p in out if p]


def _pdf(body: bytes, name: str) -> tuple[str, list[Block]]:
    pypdf = _pypdf()
    if pypdf is None:
        raise Unreadable(
            f"{name or 'the PDF'}: reading PDFs needs pip install sanchopanza[documents]"
        )
    try:
        reader = pypdf.PdfReader(io.BytesIO(body))
        title = str((reader.metadata or {}).get("/Title") or "").strip()
        blocks = [
            Block(text, f"p. {number}", "text")
            for number, sheet in enumerate(reader.pages, start=1)
            for text in pdf_text_blocks(sheet.extract_text() or "")
        ]
    except Exception as error:  # noqa: BLE001 - a broken PDF is a reason, not a crash
        raise Unreadable(
            f"{name or 'the PDF'} could not be read ({error.__class__.__name__})"
        ) from error
    return title, blocks


def _part(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    """One XML part of an Office file, refused past `MAX_PART_BYTES` uncompressed. The standard
    library's expat resolves no external entity and caps entity expansion (Python >= 3.11)."""
    if archive.getinfo(name).file_size > MAX_PART_BYTES:
        raise Unreadable(f"{name} is larger than {MAX_PART_BYTES:,} bytes uncompressed")
    return ElementTree.fromstring(archive.read(name))


def _text_of(element: ElementTree.Element, tag: str) -> str:
    return "".join(t.text or "" for t in element.iter(tag)).strip()


def _docx(body: bytes) -> tuple[str, list[Block]]:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        root = _part(archive, "word/document.xml")
    blocks: list[Block] = []
    stack: list[tuple[int, str]] = []
    title = ""
    body_node = root.find(f"{_W}body")
    for node in list(body_node) if body_node is not None else []:
        path = PATH_SEP.join(t for _level, t in stack)
        if node.tag == f"{_W}tbl":
            head = ""
            for row in node.iter(f"{_W}tr"):
                cells = [_text_of(cell, f"{_W}t") for cell in row.iter(f"{_W}tc")]
                text = " | ".join(cells).strip(" |")
                if text:
                    blocks.append(Block(text, path, "row", head))
                    head = head or text
            continue
        if node.tag != f"{_W}p":
            continue
        text = _text_of(node, f"{_W}t")
        style = node.find(f"{_W}pPr/{_W}pStyle")
        value = style.get(f"{_W}val", "") if style is not None else ""
        level = _HEADING_STYLE.search(value)
        if not text:
            continue
        if value.lower() == "title" and not title:
            title = text
        elif level:
            depth = int(level.group(1))
            stack = [*(s for s in stack if s[0] < depth), (depth, text)]
        else:
            blocks.append(Block(text, path, "text"))
    return title, blocks


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _part(archive, "xl/sharedStrings.xml")
    return [_text_of(si, f"{_S}t") for si in root.iter(f"{_S}si")]


def _sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    book = _part(archive, "xl/workbook.xml")
    rels = _part(archive, "xl/_rels/workbook.xml.rels")
    targets = {r.get("Id"): str(r.get("Target") or "") for r in rels}
    out = []
    for sheet in book.iter(f"{_S}sheet"):
        target = targets.get(sheet.get(_REL), "").lstrip("/")
        out.append(
            (str(sheet.get("name") or ""), target if target.startswith("xl/") else f"xl/{target}")
        )
    return out


def _cell(cell: ElementTree.Element, shared: Sequence[str]) -> str:
    kind = cell.get("t", "")
    if kind == "inlineStr":
        return _text_of(cell, f"{_S}t")
    value = cell.find(f"{_S}v")
    raw = (value.text or "").strip() if value is not None else ""
    if kind == "s" and raw.isdigit() and int(raw) < len(shared):
        return shared[int(raw)]
    return raw


def rows_to_blocks(rows: Iterable[Sequence[str]], place: str = "") -> list[Block]:
    """Table rows to blocks: the first non-empty row is the header, placed with every later
    row, and rows are grouped `ROWS_PER_PLACE` to a place (`rows 2-21`, row 1 the header)."""
    numbered = []
    for number, row in enumerate(rows, start=1):
        if number > MAX_ROWS:
            break
        text = " | ".join(str(c).strip() for c in row).strip(" |")
        if text:
            numbered.append((number, text))
    if not numbered:
        return []
    (head_number, head), body = numbered[0], numbered[1:]
    last = body[-1][0] if body else head_number
    prefix = f"{place}{PATH_SEP}" if place else ""
    blocks = [Block(head, f"{prefix}rows {head_number}-{head_number}", "row")]
    for number, text in body:
        start = head_number + 1 + (number - head_number - 1) // ROWS_PER_PLACE * ROWS_PER_PLACE
        where = f"{prefix}rows {start}-{min(start + ROWS_PER_PLACE - 1, last)}"
        blocks.append(Block(text, where, "row", head))
    return blocks[1:] if body else blocks


def _xlsx(body: bytes) -> list[Block]:
    blocks: list[Block] = []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        shared = _shared_strings(archive)
        for name, target in _sheets(archive):
            if target not in archive.namelist():
                continue
            root = _part(archive, target)
            rows = ([_cell(c, shared) for c in row.iter(f"{_S}c")] for row in root.iter(f"{_S}row"))
            blocks.extend(rows_to_blocks(rows, name))
    return blocks


def text_blocks(text: str) -> list[Block]:
    """Markdown headings to a heading path; with none, places of `LINES_PER_PLACE` lines."""
    lines = text.replace("\r\n", "\n").split("\n")
    marked = any(_MD_HEADING.match(line) for line in lines)
    blocks: list[Block] = []
    stack: list[tuple[int, str]] = []
    total = len(lines)
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        heading = _MD_HEADING.match(stripped) if marked else None
        if heading:
            depth = len(heading.group(1))
            stack = [*(s for s in stack if s[0] < depth), (depth, heading.group(2))]
            continue
        if marked:
            place = PATH_SEP.join(t for _level, t in stack)
        else:
            start = (number - 1) // LINES_PER_PLACE * LINES_PER_PLACE + 1
            place = f"lines {start}-{min(start + LINES_PER_PLACE - 1, total)}"
        blocks.append(Block(stripped, place, "text"))
    return blocks


def _decoded(body: bytes, content_type: str) -> str:
    return webpage.decode(body, content_type).lstrip("﻿")


def page_from_bytes(
    body: bytes, *, name: str = "", content_type: str = "", size: int = CHUNK_CHARS
) -> Page:
    """The document as a page, or `Unreadable` with the reason."""
    kind = kind_of(name, content_type, body[:512])
    title = name
    try:
        if kind == "html":
            page = webpage_v2.page_from_html(_decoded(body, content_type), size)
            return page if page.title else Page(name, page.chunks, page.disambiguation)
        if kind == "pdf":
            found, blocks = _pdf(body, name)
            title = found or name
        elif kind == "docx":
            found, blocks = _docx(body)
            title = found or name
        elif kind == "xlsx":
            blocks = _xlsx(body)
        elif kind in ("csv", "tsv"):
            text = _decoded(body, content_type)
            blocks = rows_to_blocks(
                csv.reader(io.StringIO(text), delimiter="\t" if kind == "tsv" else ",")
            )
        elif kind == "text":
            blocks = text_blocks(_decoded(body, content_type))
        else:
            what = (content_type or "").split(";")[0].strip() or "of an unknown type"
            raise Unreadable(f"{name or 'the document'} is {what}: not readable here")
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, csv.Error) as error:
        raise Unreadable(f"{name or 'the document'} could not be read as {kind} "
                         f"({error.__class__.__name__})") from error  # fmt: skip
    return Page(title, tuple(webpage_v2.chunks_of(blocks, size)))


def page_from_path(path: Path, size: int = CHUNK_CHARS) -> Page:
    """A local file as a page; refused past `MAX_FILE_BYTES`."""
    length = path.stat().st_size
    if length > MAX_FILE_BYTES:
        raise Unreadable(f"{path.name} is larger than {MAX_FILE_BYTES:,} bytes")
    return page_from_bytes(path.read_bytes(), name=path.name, size=size)
