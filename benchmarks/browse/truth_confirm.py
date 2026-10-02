"""The answers to the confirmation tasks (C*), computed from the sites with no model.

python benchmarks/browse/truth_confirm.py

These tasks were chosen after the strategy line was written and before any session saw them.
They spread over the mechanisms a crawl meets: plain pagination (C1, C2, C7, C8), one large page
(C3), tabs filled by JavaScript from a JSON endpoint (C4), pagination done in the browser over
data embedded in the page (C5), and a "load more" button (C6). Each answer is computed here
and checked by a second route in `second_route()`.
"""

from __future__ import annotations

import html as htmllib
import json
import re
import urllib.request
from decimal import Decimal

BOOKS = "https://books.toscrape.com/catalogue"
SIMPLE = "https://www.scrapethissite.com/pages/simple/"
OSCARS = "https://www.scrapethissite.com/pages/ajax-javascript/"
TABLETS = "https://webscraper.io/test-sites/e-commerce/ajax/computers/tablets"
MORE = "https://webscraper.io/test-sites/e-commerce/more/computers/laptops"
TABLEFUL = "https://quotes.toscrape.com/tableful"
HOCKEY = "https://www.scrapethissite.com/pages/forms/"

_BOOK = re.compile(r'<article class="product_pod">.*?</article>', re.S)
_STARS = re.compile(r'<p class="star-rating (\w+)">')
_PRICE = re.compile(r'<p class="price_color">[^0-9]*([0-9.]+)</p>')
_NEXT = re.compile(r'<li class="next">\s*<a href="([^"]+)"')
_AREA = re.compile(r'<span class="country-area">([0-9.eE+-]+)</span>')
_ITEMS = re.compile(r"data-items='([^']*)'")
_TAGS_ROW = re.compile(r"Tags:(.*?)</td>", re.S)
_TAG = re.compile(r'<a href="/tableful/tag/[^"]+">([^<]+)</a>')
_TEAM = re.compile(r'<tr class="team">.*?</tr>', re.S)
_CELL = re.compile(r'<td class="(\w+)[^"]*">\s*(.*?)\s*</td>', re.S)


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "sanchopanza-truth/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def books(start: str, base: str) -> list[tuple[str, Decimal]]:
    out, url = [], start
    while url:
        page = get(url)
        for block in _BOOK.findall(page):
            out.append((_STARS.search(block).group(1), Decimal(_PRICE.search(block).group(1))))
        nxt = _NEXT.search(page)
        url = f"{base}/{nxt.group(1)}" if nxt else ""
    return out


def embedded_items(url: str) -> list[dict]:
    return json.loads(htmllib.unescape(_ITEMS.search(get(url)).group(1)))


def tableful_tags() -> list[list[str]]:
    out, page = [], 1
    while True:
        rows = _TAGS_ROW.findall(get(f"{TABLEFUL}/page/{page}/"))
        if not rows:
            return out
        out += [_TAG.findall(row) for row in rows]
        page += 1


def hockey() -> list[dict[str, str]]:
    rows, page = [], 1
    while True:
        found = _TEAM.findall(get(f"{HOCKEY}?page_num={page}"))
        if not found:
            return rows
        rows += [dict(_CELL.findall(block)) for block in found]
        page += 1


def oscars() -> list[dict]:
    return [
        f for year in range(2010, 2016) for f in json.loads(get(f"{OSCARS}?ajax=true&year={year}"))
    ]


def answers() -> dict[str, object]:
    nonfiction = books(f"{BOOKS}/category/books/nonfiction_13/index.html",
                       f"{BOOKS}/category/books/nonfiction_13")  # fmt: skip
    catalogue = books(f"{BOOKS}/page-1.html", BOOKS)
    areas = [Decimal(a) for a in _AREA.findall(get(SIMPLE))]
    films = oscars()
    tablets = embedded_items(TABLETS)
    laptops = embedded_items(MORE)
    tags = tableful_tags()
    teams = hockey()
    return {
        "C1_nonfiction_books": len(nonfiction),
        "C1_under_20": sum(p < 20 for _, p in nonfiction),
        "C2_books": len(catalogue),
        "C2_one_star_over_50": sum(s == "One" and p > 50 for s, p in catalogue),
        "C3_countries": len(areas),
        "C3_area_over_1e6": sum(a > 1_000_000 for a in areas),
        "C4_films_2010_2015": len(films),
        "C4_at_least_3_awards": sum(int(f["awards"]) >= 3 for f in films),
        "C5_tablets": len(tablets),
        "C5_under_300": sum(Decimal(str(t["price"])) < 300 for t in tablets),
        "C6_laptops": len(laptops),
        "C6_over_1500": sum(Decimal(str(t["price"])) > 1500 for t in laptops),
        "C7_quotes": len(tags),
        "C7_tagged_humor": sum("humor" in t for t in tags),
        "C8_rows": len(teams),
        "C8_lost_40_or_more": sum(int(t["losses"]) >= 40 for t in teams),
    }


def second_route() -> dict[str, object]:
    """The same counts by another way in, where the site offers one."""
    humor, page = 0, 1
    while True:
        rows = _TAGS_ROW.findall(get(f"{TABLEFUL}/tag/humor/page/{page}/"))
        if not rows:
            break
        humor += len(rows)
        page += 1
    every = get(f"{HOCKEY}?per_page=600")
    big = [dict(_CELL.findall(b)) for b in _TEAM.findall(every)]
    return {
        "C7_tagged_humor_by_tag_pages": humor,
        "C8_rows_one_page": len(big),
        "C8_lost_40_or_more_one_page": sum(int(t["losses"]) >= 40 for t in big),
    }


def main() -> int:
    print(json.dumps({"answers": answers(), "second_route": second_route()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
