"""The answers to the strategy tasks (S*), computed from the sites' own pages with no model.

python benchmarks/browse/truth_strategy.py

`truth_hard.py`'s tasks were one or two pages each, except H1, and H1 was the only one where the
cheap model walked and the expensive one wrote a single extraction. These are long on purpose:
24 to 50 pages, where walking costs dozens of turns and an agent may stop early or sample. One of
them (S3) is rendered by JavaScript, so a `fetch` of its HTML finds nothing: it is where a
"extract it in one call" strategy can do harm, and it is here to catch that.
"""

from __future__ import annotations

import json
import re
import urllib.request
from decimal import Decimal

BOOKS = "https://books.toscrape.com/catalogue"
HOCKEY = "https://www.scrapethissite.com/pages/forms/"
QUOTES = "https://quotes.toscrape.com"
LAPTOPS = "https://webscraper.io/test-sites/e-commerce/static/computers/laptops"

_BOOK = re.compile(r'<article class="product_pod">.*?</article>', re.S)
_STARS = re.compile(r'<p class="star-rating (\w+)">')
_PRICE = re.compile(r'<p class="price_color">[^0-9]*([0-9.]+)</p>')
_NEXT = re.compile(r'<li class="next">\s*<a href="([^"]+)"')
_TEAM = re.compile(r'<tr class="team">.*?</tr>', re.S)
_CELL = re.compile(r'<td class="(\w+)[^"]*">\s*(.*?)\s*</td>', re.S)
_JS_DATA = re.compile(r"var data = (\[.*?\]);\s*\n", re.S)
_LAPTOP_PRICE = re.compile(r'<span itemprop="price">\$([0-9.,]+)</span>')
_LAST_PAGE = re.compile(r'\?page=(\d+)"')


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "sanchopanza-truth/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def catalogue() -> list[tuple[str, Decimal]]:
    """(star rating, price) of every book, following Next from page 1."""
    out, url = [], f"{BOOKS}/page-1.html"
    while url:
        html = get(url)
        for block in _BOOK.findall(html):
            out.append((_STARS.search(block).group(1), Decimal(_PRICE.search(block).group(1))))
        nxt = _NEXT.search(html)
        url = f"{BOOKS}/{nxt.group(1)}" if nxt else ""
    return out


def hockey() -> list[dict[str, str]]:
    """Every row of the table, following its pagination at the default 25 a page."""
    rows, page = [], 1
    while True:
        found = _TEAM.findall(get(f"{HOCKEY}?page_num={page}"))
        if not found:
            return rows
        rows += [dict(_CELL.findall(block)) for block in found]
        page += 1


def js_quotes() -> list[dict]:
    """The JavaScript-rendered site keeps its quotes in a `var data` array, ten a page."""
    out, page = [], 1
    while True:
        found = _JS_DATA.search(get(f"{QUOTES}/js/page/{page}/"))
        data = json.loads(found.group(1)) if found else []
        if not data:
            return out
        out += data
        page += 1


def api_quotes() -> list[dict]:
    """What the infinite-scroll page loads, page by page, from its own JSON endpoint."""
    out, page = [], 1
    while True:
        data = json.loads(get(f"{QUOTES}/api/quotes?page={page}"))
        out += data["quotes"]
        if not data["has_next"]:
            return out
        page += 1


def laptops() -> list[Decimal]:
    first = get(LAPTOPS)
    last = max(int(n) for n in _LAST_PAGE.findall(first))
    prices = []
    for page in range(1, last + 1):
        html = first if page == 1 else get(f"{LAPTOPS}?page={page}")
        prices += [Decimal(p.replace(",", "")) for p in _LAPTOP_PRICE.findall(html)]
    return prices


def main() -> int:
    books = catalogue()
    teams = hockey()
    js = js_quotes()
    scroll = api_quotes()
    prices = laptops()
    truth = {
        "S1_books": len(books),
        "S1_five_star_under_20": sum(s == "Five" and p < 20 for s, p in books),
        "S2_rows": len(teams),
        "S2_seasons_with_50_wins": sum(int(t["wins"]) >= 50 for t in teams),
        "S3_js_quotes": len(js),
        "S3_tagged_love": sum("love" in q["tags"] for q in js),
        "S4_laptops": len(prices),
        "S4_over_1000": sum(p > 1000 for p in prices),
        "S5_scroll_quotes": len(scroll),
        "S5_distinct_authors": len({q["author"]["name"] for q in scroll}),
    }
    print(json.dumps(truth, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
