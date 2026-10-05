"""Can a harness tell a repeated page from a real next page without a model? Free, no browser.

python benchmarks/browse/repeat_fingerprint.py

Line v6's development round (`docs/results/2026-10-03-browse-v6/`) found that most guessed URLs
(`?page=N`) are answered with page 1 again. A note in the evaluate wrapper could say so if two
fetched bodies are "the same page". Two fingerprints are compared on pairs of real next pages, of
guessed pages and of pages past the end: the set of links, and the visible text (a stand-in for
`DOMParser`'s `body.textContent`).
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request

LT = "https://ecommerce-playground.lambdatest.io/index.php?route=product/category&path=57"
QUOTES = "https://quotes.toscrape.com/page"
PAIRS = [
    ("scrapeme, real", "https://scrapeme.live/shop/", "https://scrapeme.live/shop/page/2/"),
    ("scrapeme, guessed", "https://scrapeme.live/shop/", "https://scrapeme.live/shop/?page=2"),
    ("scrapeme, past the end", "https://scrapeme.live/shop/page/48/",
     "https://scrapeme.live/shop/page/49/"),
    ("course, real", "https://www.scrapingcourse.com/pagination",
     "https://www.scrapingcourse.com/pagination/2"),
    ("course, guessed", "https://www.scrapingcourse.com/pagination?page=2",
     "https://www.scrapingcourse.com/pagination?page=3"),
    ("lambdatest, real", LT, LT + "&page=2"),
    ("lambdatest, past the end", LT + "&page=6", LT + "&page=7"),
    ("books, real", "https://books.toscrape.com/catalogue/page-1.html",
     "https://books.toscrape.com/catalogue/page-2.html"),
    ("quotes, real", f"{QUOTES}/1/", f"{QUOTES}/2/"),
    ("quotes, past the end", f"{QUOTES}/11/", f"{QUOTES}/12/"),
    ("web-scraping.dev, real", "https://web-scraping.dev/products?page=1",
     "https://web-scraping.dev/products?page=2"),
    ("hockey, real", "https://www.scrapethissite.com/pages/forms/?page_num=1",
     "https://www.scrapethissite.com/pages/forms/?page_num=2"),
]  # fmt: skip


def get(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 sanchopanza/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def links(html: str) -> frozenset[str]:
    return frozenset(re.findall(r'href="([^"#]+)"', html))


def visible_text(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    for name, first, second in PAIRS:
        (status_a, a), (status_b, b) = get(first), get(second)
        print(f"{name:26s} {status_a}/{status_b}  same links: {links(a) == links(b)!s:5s}  "
              f"same text: {visible_text(a) == visible_text(b)}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
