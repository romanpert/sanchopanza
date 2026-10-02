"""The answers to the aggregation tasks, computed from the sites' own HTML with no model.

python benchmarks/browse/truth_hard.py

Each task asks for a count or a sum over many pages, which is where a browsing agent goes wrong
in a way that is not luck: it stops early, double-counts a page, or misreads one price among
thirty. The answer has to come from somewhere other than a model, so it comes from here, and
the script stays in the repo so anyone can check that the sites still say the same thing.
"""

from __future__ import annotations

import collections
import json
import re
import urllib.request
from decimal import Decimal

QUOTES = "https://quotes.toscrape.com"
BOOKS = "https://books.toscrape.com/catalogue/category/books"
_QUOTE = re.compile(r'<div class="quote".*?</div>\s*</div>', re.S)
_AUTHOR = re.compile(r'<small class="author"[^>]*>([^<]+)</small>')
_TAG = re.compile(r'<a class="tag"[^>]*>([^<]+)</a>')
_PRICE = re.compile(r'<p class="price_color">[^0-9]*([0-9.]+)</p>')
_TITLE = re.compile(r'<h3><a href="[^"]+" title="([^"]+)"')
_NEXT = re.compile(r'<li class="next">\s*<a href="([^"]+)"')


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "sanchopanza-truth/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def quote_pages(start: str) -> list[str]:
    """Every page reached by following "Next" from `start`."""
    pages, url = [], start
    while url:
        html = get(url)
        pages.append(html)
        nxt = _NEXT.search(html)
        url = (QUOTES + nxt.group(1)) if nxt else ""
    return pages


def quotes(start: str) -> list[tuple[str, list[str]]]:
    out = []
    for html in quote_pages(start):
        for block in _QUOTE.findall(html):
            author = _AUTHOR.search(block)
            out.append((author.group(1).strip() if author else "?", _TAG.findall(block)))
    return out


def book_pages(slug: str) -> list[str]:
    pages, url = [], f"{BOOKS}/{slug}/index.html"
    while url:
        html = get(url)
        pages.append(html)
        nxt = _NEXT.search(html)
        url = f"{BOOKS}/{slug}/{nxt.group(1)}" if nxt else ""
    return pages


def books(slug: str) -> list[tuple[str, Decimal]]:
    out = []
    for html in book_pages(slug):
        titles, prices = _TITLE.findall(html), _PRICE.findall(html)
        assert len(titles) == len(prices), f"{slug}: {len(titles)} titles, {len(prices)} prices"
        out += [(t, Decimal(p)) for t, p in zip(titles, prices, strict=True)]
    return out


def main() -> int:
    every = quotes(QUOTES + "/")
    einstein = sum(a == "Albert Einstein" for a, _ in every)
    inspirational = quotes(QUOTES + "/tag/inspirational/")
    by_author = collections.Counter(a for a, _ in inspirational)
    mystery = books("mystery_3")
    over_40 = [t for t, p in mystery if p > 40]
    travel = books("travel_2")
    poetry = books("poetry_23")
    truth = {
        "H1_einstein_quotes_on_the_site": einstein,
        "H1_pages_walked": len(quote_pages(QUOTES + "/")),
        "H2_mystery_books": len(mystery),
        "H2_mystery_over_40": len(over_40),
        "H2_mystery_pages": len(book_pages("mystery_3")),
        "H3_inspirational_quotes": len(inspirational),
        "H3_inspirational_top_author": by_author.most_common(3),
        "H4_travel_books": len(travel),
        "H4_travel_price_sum": str(sum((p for _, p in travel), Decimal(0))),
        "H5_poetry_books": len(poetry),
        "H5_poetry_cheapest": min(poetry, key=lambda b: b[1])[0],
        "H5_poetry_cheapest_price": str(min(p for _, p in poetry)),
    }
    print(json.dumps(truth, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
