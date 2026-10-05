"""`sanchopanza.webpage`: a page to its text, the text to chunks under its headings, and the
chunks a purpose needs under a character budget. Code only, no model and no network."""

from __future__ import annotations

from sanchopanza import webpage

PAGE = """<html><head><title>Lake Example - Wiki</title><style>.x{color:red}</style>
<script>var tracking = "do not keep";</script></head>
<body><nav>Main menu Random page</nav>
<h1>Lake Example</h1>
<p>Lake Example is a freshwater lake in the north of the country.</p>
<h2>Geography</h2>
<p>The lake covers 42 square kilometres and reaches a depth of 310 metres.</p>
<h2>History</h2>
<p>The first survey of the lake was carried out in 1873 by a naval team.</p>
<h2>Fishing records</h2>
<table><tr><th>Year</th><th>Catch (tonnes)</th></tr>
<tr><td>1990</td><td>1,200</td></tr><tr><td>2000</td><td>950</td></tr></table>
<footer>Privacy policy</footer></body></html>"""


def test_the_text_keeps_content_and_drops_scripts_styles_and_chrome() -> None:
    title, blocks = webpage.blocks_of(PAGE)
    text = "\n".join(b.text for b in blocks)
    assert title == "Lake Example - Wiki"
    assert "310 metres" in text and "1873" in text
    assert "tracking" not in text and "color:red" not in text
    assert "Main menu" not in text and "Privacy policy" not in text


def test_table_rows_keep_their_cells_apart() -> None:
    _title, blocks = webpage.blocks_of(PAGE)
    rows = [b.text for b in blocks if b.kind == "row"]
    assert any("1990" in r and "1,200" in r and "|" in r for r in rows)


def test_chunks_carry_their_section_heading() -> None:
    _title, blocks = webpage.blocks_of(PAGE)
    chunks = webpage.chunks_of(blocks, size=700)
    by_text = {c.text: c.heading for c in chunks}
    assert any("1873" in t and h == "History" for t, h in by_text.items())
    assert any("310 metres" in t and h == "Geography" for t, h in by_text.items())


def test_a_long_paragraph_is_split_by_sentences_under_the_size() -> None:
    body = " ".join(f"Sentence number {i} says something about the lake." for i in range(200))
    _title, blocks = webpage.blocks_of(f"<p>{body}</p>")
    chunks = webpage.chunks_of(blocks, size=300)
    assert len(chunks) > 5
    assert all(len(c.text) <= 300 + 60 for c in chunks)


def test_the_purpose_picks_the_section_that_answers_it() -> None:
    page = webpage.page_from_html(PAGE)
    picked = webpage.pick("when was the first survey of the lake", page.chunks, budget=300)
    assert any("1873" in page.chunks[i].text for i in picked)
    assert not any("1,200" in page.chunks[i].text for i in picked)


def test_the_lead_is_the_first_long_chunk_not_a_menu() -> None:
    lead = "Lake Example is a freshwater lake. " * 8
    html = (
        "<div><a>Jump to content</a></div><h1>Lake</h1>"
        f"<p>{lead}</p><h2>Birds</h2><p>Herons nest on the shore.</p>"
        "<h2>Fish</h2><p>Trout and pike are caught in winter.</p>"
    )
    page = webpage.page_from_html(html)
    picked = webpage.pick("trout pike", page.chunks, budget=1_400)
    texts = [page.chunks[i].text for i in picked]
    assert any(t.startswith("Lake Example") for t in texts)
    assert not any("Jump to content" in t for t in texts)
    assert any("Trout" in t for t in texts)


def test_a_page_under_the_budget_is_returned_whole() -> None:
    page = webpage.page_from_html(PAGE)
    out = webpage.passages(page, "anything at all", budget=100_000)
    assert out.shown == out.total
    assert all(c.text in out.text for c in page.chunks)


def test_the_rendered_passages_mark_gaps_and_headings_and_say_how_much_was_left() -> None:
    page = webpage.page_from_html(PAGE)
    out = webpage.passages(page, "fishing catch tonnes by year", budget=150)
    assert "## Fishing records" in out.text
    assert "[...]" in out.text
    assert out.shown < out.total
    assert f"{out.shown:,} of {out.total:,} characters" in out.header()


def test_plain_text_and_json_are_cut_into_line_chunks() -> None:
    text = "\n".join(f'{{"day": {i}, "temp": {10 + i}}}' for i in range(500))
    page = webpage.page_from_text(text, title="data")
    assert len(page.chunks) > 1
    out = webpage.passages(page, "day 321 temp", budget=1_500)
    assert out.shown < out.total
    assert '"day": 321' in out.text


def test_charset_comes_from_the_header_then_the_meta_then_utf8() -> None:
    latin = "<meta charset='iso-8859-1'><p>caf\xe9</p>".encode("latin-1")
    assert "café" in webpage.decode(latin, "text/html")
    assert "café" in webpage.decode("<p>café</p>".encode("cp1252"), "text/html; charset=cp1252")
    assert "café" in webpage.decode("<p>café</p>".encode(), "text/html")


def test_nothing_on_the_page_yields_an_empty_result_not_an_error() -> None:
    page = webpage.page_from_html("<html><body><script>x()</script></body></html>")
    out = webpage.passages(page, "anything", budget=1000)
    assert out.total == 0 and out.shown == 0
