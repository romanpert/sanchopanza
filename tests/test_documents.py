"""`sanchopanza.documents`: files and downloaded bytes to pages whose chunks carry their place.

A passage handed to an agent must say where it stands so it can be cited: a PDF's page, a
document's section path, a sheet and its rows. No network, no model; the PDF tests need the
optional `pypdf`."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from sanchopanza import documents


def _pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF, one text line per page (Helvetica), with a correct xref."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
              .encode())  # fmt: skip
    return out.getvalue()


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(body: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", f"<w:document {W}><w:body>{body}</w:body></w:document>")
    return out.getvalue()


def _para(text: str, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"


def _row(*cells: str) -> str:
    return "<w:tr>" + "".join(f"<w:tc>{_para(c)}</w:tc>" for c in cells) + "</w:tr>"


S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def _xlsx(rows: list[list[str]], name: str = "Budget") -> bytes:
    strings = sorted({c for row in rows for c in row if not c.isdigit()})
    shared = "".join(f"<si><t>{s}</t></si>" for s in strings)

    def cell(value: str) -> str:
        if value.isdigit():
            return f"<c><v>{value}</v></c>"
        return f'<c t="s"><v>{strings.index(value)}</v></c>'

    sheet = "".join(f"<row>{''.join(cell(c) for c in row)}</row>" for row in rows)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {S} {R}><sheets><sheet name="{name}" '
                                      'sheetId="1" r:id="rId1"/></sheets></workbook>')  # fmt: skip
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                   'relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" '
                   'Type="x"/></Relationships>')  # fmt: skip
        z.writestr("xl/sharedStrings.xml", f"<sst {S}>{shared}</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {S}><sheetData>{sheet}</sheetData>"
                                               "</worksheet>")  # fmt: skip
    return out.getvalue()


def _texts(page) -> list[tuple[str, str]]:
    return [(c.heading, c.text) for c in page.chunks]


# --- kinds ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "ctype", "head", "kind"),
    [
        ("report.pdf", "", b"", "pdf"),
        ("x", "application/pdf", b"", "pdf"),
        ("x.bin", "", b"%PDF-1.7", "pdf"),
        ("memo.docx", "", b"PK", "docx"),
        ("book.xlsx", "", b"PK", "xlsx"),
        ("data.csv", "", b"", "csv"),
        ("data.tsv", "", b"", "tsv"),
        ("page.html", "", b"", "html"),
        ("x", "text/html; charset=utf-8", b"", "html"),
        ("notes.md", "", b"", "text"),
        ("notes.txt", "", b"", "text"),
        ("x", "text/plain", b"", "text"),
        ("x", "", b"<!doctype html><html>", "html"),
    ],
)
def test_kind_of_reads_extension_type_and_magic(name: str, ctype: str, head: bytes, kind: str):
    assert documents.kind_of(name, ctype, head) == kind


def test_an_unknown_binary_is_unreadable() -> None:
    with pytest.raises(documents.Unreadable):
        documents.page_from_bytes(b"\x00\x01\x02", name="blob.bin", content_type="image/png")


# --- PDF -----------------------------------------------------------------------------------------


def test_a_pdf_page_is_the_place_of_its_chunks() -> None:
    pytest.importorskip("pypdf")
    page = documents.page_from_bytes(
        _pdf(["The audit found 42 contracts.", "Spending rose by 12 percent in 2023."]),
        name="audit.pdf",
    )
    chunks = _texts(page)
    assert ("p. 1", "The audit found 42 contracts.") in chunks
    assert any(h == "p. 2" and "12 percent" in t for h, t in chunks)
    assert page.title == "audit.pdf"


def test_a_pdf_without_pypdf_says_how_to_read_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "_pypdf", lambda: None)
    with pytest.raises(documents.Unreadable, match="sanchopanza\\[documents\\]"):
        documents.page_from_bytes(_pdf(["x"]), name="a.pdf")


def test_hyphenated_line_ends_are_joined() -> None:
    assert documents.pdf_text_blocks("The commit-\nment was met.\nNext line.") == [
        "The commitment was met. Next line."
    ]


# --- DOCX ----------------------------------------------------------------------------------------


def test_docx_headings_become_the_section_path_and_tables_keep_their_header() -> None:
    body = (
        _para("Annual report", "Title")
        + _para("Results", "Heading1")
        + _para("Revenue grew.")
        + _para("By region", "Heading2")
        + "<w:tbl>"
        + _row("Region", "Revenue")
        + _row("North", "10")
        + "</w:tbl>"
    )
    page = documents.page_from_bytes(_docx(body), name="report.docx")
    chunks = _texts(page)
    assert ("Results", "Revenue grew.") in chunks
    assert any(h == "Results > By region" and "North | 10" in t for h, t in chunks)
    assert any("Region | Revenue" in t for _, t in chunks)
    assert page.title == "Annual report"


# --- XLSX, CSV -----------------------------------------------------------------------------------


def test_xlsx_rows_carry_the_sheet_the_rows_and_the_header() -> None:
    rows = [["Item", "Cost"]] + [[f"item{i}", str(i)] for i in range(1, 46)]
    page = documents.page_from_bytes(_xlsx(rows), name="book.xlsx")
    chunks = _texts(page)
    assert any(h.startswith("Budget > rows 2-") for h, _ in chunks)
    last = [t for h, t in chunks if "item45" in t]
    assert last and last[0].startswith("Item | Cost")


def test_csv_rows_carry_their_numbers_and_header(tmp_path: Path) -> None:
    path = tmp_path / "people.csv"
    path.write_text("name,city\n" + "".join(f"p{i},c{i}\n" for i in range(1, 31)), "utf-8")
    page = documents.page_from_path(path)
    chunks = _texts(page)
    assert chunks[0][0] == "rows 2-21"
    assert chunks[0][1].startswith("name | city\np1 | c1")
    assert any(h == "rows 22-31" for h, _ in chunks)


# --- text ----------------------------------------------------------------------------------------


def test_markdown_headings_become_the_path(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Guide\n\nIntro text.\n\n## Install\n\nRun the installer.\n", "utf-8")
    chunks = _texts(documents.page_from_path(path))
    assert ("Guide", "Intro text.") in chunks
    assert ("Guide > Install", "Run the installer.") in chunks


def test_plain_text_without_headings_is_placed_by_lines(tmp_path: Path) -> None:
    path = tmp_path / "log.txt"
    path.write_text("\n".join(f"line number {i}" for i in range(1, 101)), "utf-8")
    chunks = _texts(documents.page_from_path(path))
    assert chunks[0][0] == "lines 1-40"
    assert any(h == "lines 81-100" for h, _ in chunks)


def test_html_files_are_cut_as_web_pages(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text(
        "<html><title>T</title><nav>menu</nav><h2>Part</h2><p>Body.</p></html>", "utf-8"
    )
    page = documents.page_from_path(path)
    assert page.title == "T" and _texts(page) == [("Part", "Body.")]


def test_a_file_too_large_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "MAX_FILE_BYTES", 10)
    path = tmp_path / "big.txt"
    path.write_text("x" * 50, "utf-8")
    with pytest.raises(documents.Unreadable, match="larger"):
        documents.page_from_path(path)
