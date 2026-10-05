"""`sanchopanza.webpage_v2`: passages by sections, the page's chrome stripped before cutting.

Version 1 (`sanchopanza.webpage`) stays as it was measured. These tests pin what version 2 adds:
no language lists, skip links, edit marks, navigation boxes or citation marks; a heading carries
its parents; a table cut in pieces repeats its header row; a section whose heading matches the
purpose is kept together, so a heading never stands in for its body; reference lists only when
the purpose asks for them; a disambiguation page is flagged. Code only, no model, no network."""

from __future__ import annotations

from sanchopanza import webpage, webpage_v2

LANGS = "".join(f'<li class="interlanguage-link"><a>Lang{i}</a></li>' for i in range(40))
FILMS = "".join(
    f"<tr><td>{1990 + i}</td><td>Film number {i}</td><td>Role {i}</td></tr>" for i in range(30)
)
SERIES = "".join(
    f"<tr><td>{2000 + i}</td><td>Series number {i}</td><td>Part {i}</td></tr>" for i in range(12)
)
CHATTER = " ".join(f"Career sentence {i} about stage work and touring." for i in range(60))
REFS = "".join(
    f'<li id="cite_note-{i}">Reference title {i}. Some Paper. 2001.</li>' for i in range(40)
)
CITE = '<sup class="reference">[1]</sup>'


def _h(level: int, name: str) -> str:
    edit = '<span class="mw-editsection">[<a>edit</a>]</span>'
    return f'<div class="mw-heading mw-heading{level}"><h{level}>{name}</h{level}>{edit}</div>'


WIKI = f"""<html><head><title>Jane Example - Wikipedia</title></head><body>
<a class="mw-jump-link" href="#content">Jump to content</a>
<header class="vector-header mw-header" role="banner"><div role="search">Search</div></header>
<div class="vector-page-titlebar"><h1>Jane Example</h1>
<div id="p-lang-btn" class="vector-dropdown mw-portlet mw-portlet-lang"><ul>{LANGS}</ul>
<a>Edit links</a></div></div>
<div id="siteSub">From Wikipedia, the free encyclopedia</div>
<table class="infobox"><tr><th colspan="2">Jane Example</th></tr>
<tr><th>Born</th><td>1 May 1970</td></tr><tr><th>Occupation</th><td>Actress</td></tr></table>
<p>Jane Example (born 1 May 1970) is an actress known for many films.{CITE}
She was born in a small town and studied drama at a well known school in the capital.</p>
{_h(2, "Career")}
<p>{CHATTER}</p>
{_h(2, "Filmography")}
{_h(3, "Film")}
<table class="wikitable"><tr><th>Year</th><th>Title</th><th>Role</th></tr>{FILMS}</table>
{_h(3, "Television")}
<table class="wikitable"><tr><th>Year</th><th>Title</th><th>Part</th></tr>{SERIES}</table>
{_h(2, "References")}
<div class="reflist"><ol class="references">{REFS}</ol></div>
<div class="navbox"><table><tr><td>v t e</td><td>Films: A (1990) B (1991)</td></tr></table></div>
<div id="catlinks" class="catlinks">Categories: 1970 births Living people</div>
<div class="printfooter">Retrieved from "https://en.wikipedia.org/w/index.php?title=Jane"</div>
</body></html>"""


def _all_text(page: webpage.Page) -> str:
    return "\n".join(f"{c.heading}\n{c.text}" for c in page.chunks)


def test_page_chrome_is_stripped_before_cutting() -> None:
    text = _all_text(webpage_v2.page_from_html(WIKI))
    for chrome in ("Lang7", "Jump to content", "[edit]", "Edit links", "From Wikipedia",
                   "Retrieved from", "Categories:", "v t e", "Search", "[1]"):  # fmt: skip
        assert chrome not in text, chrome
    assert "born 1 May 1970" in text and "Film number 29" in text and "Born | 1 May 1970" in text
    assert "many films. She was born" in text  # a citation mark does not cut its sentence


def test_version_one_is_left_as_it_was_measured() -> None:
    text = _all_text(webpage.page_from_html(WIKI))
    assert "[edit]" in text and "Lang7" in text


def test_a_heading_carries_its_parent_heading() -> None:
    page = webpage_v2.page_from_html(WIKI)
    tv = [c for c in page.chunks if "Series number 3" in c.text]
    assert tv and tv[0].heading == "Filmography > Television"


def test_a_table_cut_in_pieces_repeats_its_header_row() -> None:
    page = webpage_v2.page_from_html(WIKI, size=300)
    film = [c for c in page.chunks if c.heading == "Filmography > Film"]
    assert len(film) > 2
    assert all(c.text.splitlines()[0] == "Year | Title | Role" for c in film)


def test_a_section_named_by_the_purpose_is_kept_whole_with_its_rows() -> None:
    page = webpage_v2.page_from_html(WIKI)
    out = webpage_v2.passages(page, "Find her filmography and TV appearances", budget=3_500)
    assert out.shown < out.total
    for row in ("Film number 0", "Film number 29", "Series number 0", "Series number 11"):
        assert row in out.text, row
    assert "Reference title" not in out.text


def test_no_heading_is_rendered_without_its_body() -> None:
    page = webpage_v2.page_from_html(WIKI)
    out = webpage_v2.passages(page, "filmography", budget=2_500)
    lines = out.text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## "):
            assert i + 1 < len(lines) and not lines[i + 1].startswith(("## ", "[...]")), line


def test_a_section_larger_than_the_budget_keeps_its_header_and_the_best_rows() -> None:
    page = webpage_v2.page_from_html(WIKI, size=300)
    out = webpage_v2.passages(page, "film list: which film in 2017", budget=1_200)
    assert "Year | Title | Role" in out.text
    assert "2017 | Film number 27" in out.text


def test_reference_lists_only_when_the_purpose_asks_for_them() -> None:
    page = webpage_v2.page_from_html(WIKI)
    plain = webpage_v2.passages(page, "paper published 2001", budget=3_000)
    assert "Reference title" not in plain.text
    asked = webpage_v2.passages(page, "references cited: paper published 2001", budget=3_000)
    assert "Reference title" in asked.text


def test_a_page_under_the_budget_comes_back_whole_without_its_reference_list() -> None:
    page = webpage_v2.page_from_html(WIKI)
    out = webpage_v2.passages(page, "anything", budget=100_000)
    assert "Film number 29" in out.text and "Reference title" not in out.text
    assert out.shown == out.total


def test_the_lead_comes_first_and_the_purpose_still_ranks_the_rest() -> None:
    page = webpage_v2.page_from_html(WIKI)
    out = webpage_v2.passages(page, "stage work touring sentence 41", budget=1_500)
    assert "born 1 May 1970" in out.text
    assert "sentence 41" in out.text


def test_a_disambiguation_page_is_flagged() -> None:
    marked = '<div id="disambigbox" class="dmbox-disambig">x</div><p>Jumper may refer to:</p>'
    assert webpage_v2.page_from_html(
        f"<h1>Jumper</h1>{marked}<li>Jumper (2008 film)</li>"
    ).disambiguation
    by_text = "<h1>Jumper</h1><p>Jumper or Jumpers may refer to:</p><li>Jumper (novel)</li>"
    assert webpage_v2.page_from_html(by_text).disambiguation
    assert not webpage_v2.page_from_html(WIKI).disambiguation
