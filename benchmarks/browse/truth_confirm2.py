"""The answers to the second confirmation's tasks (D*), computed from the sites with no model.

python benchmarks/browse/truth_confirm2.py

Chosen after strategy line v5 was written and before any session saw them, over mechanisms the
line was not developed on: data held back ten seconds in a script (D3), an ASP.NET form with
view state (D4), infinite scroll (D5), a "load more" button (D6), search results over many pages
(D7), plus two plain catalogues (D1, D2) and a sum (D8). Each answer is checked by a second
route in `second_route()`.
"""

from __future__ import annotations

import html as htmllib
import json
import re
import urllib.parse
import urllib.request
from decimal import Decimal

BOOKS = "https://books.toscrape.com/catalogue"
QUOTES = "https://quotes.toscrape.com"
SCROLL = "https://webscraper.io/test-sites/e-commerce/scroll/computers/laptops"
MORE_TABLETS = "https://webscraper.io/test-sites/e-commerce/more/computers/tablets"
STATIC = "https://webscraper.io/test-sites/e-commerce/static/computers"
HOCKEY = "https://www.scrapethissite.com/pages/forms/"

_BOOK = re.compile(r'<article class="product_pod">.*?</article>', re.S)
_STARS = re.compile(r'<p class="star-rating (\w+)">')
_PRICE = re.compile(r'<p class="price_color">[^0-9]*([0-9.]+)</p>')
_NEXT = re.compile(r'<li class="next">\s*<a href="([^"]+)"')
_JS_DATA = re.compile(r"var data = (\[.*?\]);", re.S)
_ITEMS = re.compile(r"data-items='([^']*)'")
_STATIC_PRICE = re.compile(r'<span itemprop="price">\$([0-9.,]+)</span>')
_TEAM = re.compile(r'<tr class="team">.*?</tr>', re.S)
_CELL = re.compile(r'<td class="(\w+)[^"]*">\s*(.*?)\s*</td>', re.S)
_QUOTE = re.compile(r'<div class="quote".*?</div>\s*</div>', re.S)
_AUTHOR = re.compile(r'<small class="author"[^>]*>([^<]+)</small>')
_TAG = re.compile(r'<a class="tag"[^>]*>([^<]+)</a>')
_VIEWSTATE = re.compile(r'name="__VIEWSTATE" id="__VIEWSTATE" value="([^"]*)"')
_RESULT = re.compile(r'<span class="content">(.*?)</span>', re.S)


def get(url: str, data: dict[str, str] | None = None) -> str:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={"User-Agent": "sanchopanza-truth/1"})
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


def delayed_quotes() -> list[dict]:
    out, page = [], 1
    while True:
        found = _JS_DATA.search(get(f"{QUOTES}/js-delayed/page/{page}/"))
        data = json.loads(found.group(1)) if found else []
        if not data:
            return out
        out += data
        page += 1


def static_quotes() -> list[tuple[str, list[str]]]:
    out, url = [], f"{QUOTES}/"
    while url:
        page = get(url)
        out += [(_AUTHOR.search(b).group(1), _TAG.findall(b)) for b in _QUOTE.findall(page)]
        nxt = _NEXT.search(page)
        url = f"{QUOTES}{nxt.group(1)}" if nxt else ""
    return out


def search_form(author: str, tag: str) -> int:
    """The form's own answer: choose the author (a postback), then the tag, then search."""
    first = get(f"{QUOTES}/search.aspx")
    state = _VIEWSTATE.search(first).group(1)
    second = get(f"{QUOTES}/filter.aspx", {"author": author, "__VIEWSTATE": state})
    state = _VIEWSTATE.search(second).group(1)
    form = {"author": author, "tag": tag, "submit_button": "Search", "__VIEWSTATE": state}
    final = get(f"{QUOTES}/filter.aspx", form)
    return len(_RESULT.findall(final))


def embedded(url: str) -> list[Decimal]:
    items = json.loads(htmllib.unescape(_ITEMS.search(get(url)).group(1)))
    return [Decimal(str(i["price"])) for i in items]


def static_prices(category: str) -> list[Decimal]:
    out, page = [], 1
    while True:
        found = _STATIC_PRICE.findall(get(f"{STATIC}/{category}?page={page}"))
        if not found:
            return out
        out += [Decimal(p.replace(",", "")) for p in found]
        page += 1


def hockey(query: str, per_page: int = 25) -> list[dict[str, str]]:
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({"q": query, "page_num": page, "per_page": per_page})
        found = _TEAM.findall(get(f"{HOCKEY}?{q}"))
        if not found:
            return rows
        rows += [dict(_CELL.findall(b)) for b in found]
        page += 1


def answers() -> dict[str, object]:
    catalogue = books(f"{BOOKS}/page-1.html", BOOKS)
    default = books(f"{BOOKS}/category/books/default_15/index.html",
                    f"{BOOKS}/category/books/default_15")  # fmt: skip
    fantasy = books(f"{BOOKS}/category/books/fantasy_19/index.html",
                    f"{BOOKS}/category/books/fantasy_19")  # fmt: skip
    delayed = delayed_quotes()
    laptops = embedded(SCROLL)
    tablets = embedded(MORE_TABLETS)
    new_york = hockey("New York")
    return {
        "D1_books": len(catalogue),
        "D1_under_11": sum(p < 11 for _, p in catalogue),
        "D2_default_books": len(default),
        "D2_three_stars": sum(s == "Three" for s, _ in default),
        "D3_delayed_quotes": len(delayed),
        "D3_tagged_life": sum("life" in q["tags"] for q in delayed),
        "D4_einstein_inspirational_by_form": search_form("Albert Einstein", "inspirational"),
        "D5_laptops": len(laptops),
        "D5_under_500": sum(p < 500 for p in laptops),
        "D6_tablets": len(tablets),
        "D6_over_500": sum(p > 500 for p in tablets),
        "D7_new_york_rows": len(new_york),
        "D7_won_40_or_more": sum(int(t["wins"]) >= 40 for t in new_york),
        "D8_fantasy_books": len(fantasy),
        "D8_fantasy_price_sum": str(sum((p for _, p in fantasy), Decimal(0))),
    }


def second_route() -> dict[str, object]:
    quotes = static_quotes()
    every = hockey("New York", per_page=100)
    return {
        "D3_tagged_life_static_site": sum("life" in tags for _, tags in quotes),
        "D4_einstein_inspirational_static_site": sum(
            a == "Albert Einstein" and "inspirational" in tags for a, tags in quotes
        ),
        "D5_under_500_static_copy": sum(p < 500 for p in static_prices("laptops")),
        "D6_over_500_static_copy": sum(p > 500 for p in static_prices("tablets")),
        "D7_won_40_or_more_100_a_page": sum(int(t["wins"]) >= 40 for t in every),
        "D7_rows_100_a_page": len(every),
    }


def main() -> int:
    print(json.dumps({"answers": answers(), "second_route": second_route()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
