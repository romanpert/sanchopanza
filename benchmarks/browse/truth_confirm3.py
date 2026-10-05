"""The answers to the third confirmation's tasks (E*, I*), computed from the sites with no model.

python benchmarks/browse/truth_confirm3.py

Chosen after the crawl hook was packaged (`sanchopanza.harness.crawl_hook`) and before any
session saw them, over sites and mechanisms no line or arm has met: a short paginated listing
(E1), testimonials that htmx loads as you scroll (E2), reviews behind a GraphQL cursor and a
"load more" button (E3), a WooCommerce catalogue of twelve pages (E4), products that an AJAX
offset loads on scroll (E5), a catalogue of 94 pages built by Next.js (E6), a list inside an
iframe whose answer sits on each item's own page (E7), and nineteen detail pages behind one
category (E8). Each answer is checked by a second route in `second_route()`.
"""

from __future__ import annotations

import ast
import html as htmllib
import json
import re
import urllib.parse
import urllib.request
from decimal import Decimal

WSD = "https://web-scraping.dev"
COURSE = "https://www.scrapingcourse.com"
OXY = "https://sandbox.oxylabs.io/products"
FRAMES = "https://www.scrapethissite.com/pages/frames/"
BOOKS = "https://books.toscrape.com/catalogue"
POETRY = f"{BOOKS}/category/books/poetry_23"

_WSD_PRODUCT = re.compile(r'<div class="row product">.*?<div class="price">([0-9.]+)</div>', re.S)
_WSD_NAME = re.compile(r'<h3 class="mb-0"><a href="[^"]+">([^<]+)</a>')
_RATING = re.compile(r'<span class="rating">(.*?)</span>', re.S)
_HX_NEXT = re.compile(r'hx-get="([^"]+)"')
_GQL = re.compile(r'<script id="reviewsGQL"[^>]*>(.*?)</script>', re.S)
_WOO = re.compile(r'<li data-products="item".*?</li>', re.S)
_WOO_PRICE = re.compile(r'woocommerce-Price-amount amount"><bdi><span[^>]*>[^<]*</span>([0-9.,]+)')
_WOO_NAME = re.compile(r'woocommerce-loop-product__title">([^<]+)<')
_COURSE_NAME = re.compile(r'class="product-name"[^>]*>([^<]+)<')
_COURSE_PRICE = re.compile(r'class="product-price[^"]*"[^>]*>\s*\$?([0-9.,]+)')
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_OXY_PRICE = re.compile(r"price-wrapper[^>]*>([0-9.,]+)\s*€<")
_FAMILY = re.compile(r'href="(/pages/frames/\?frame=i&(?:amp;)?family=[^"]+)"')
_DISCOVERED = re.compile(r"first discovered in\s+(\d{4})\s+by", re.S)
_BOOK_LINK = re.compile(r'<h3><a href="([^"]+)"')
_AVAILABLE = re.compile(r"In stock \((\d+) available\)")


def get(url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(
        url, data=data, headers={"User-Agent": "sanchopanza-truth/1", **(headers or {})}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def wsd_products(query: str = "") -> list[tuple[str, Decimal]]:
    out, page = [], 1
    while True:
        html = get(f"{WSD}/products?page={page}{query}")
        prices = _WSD_PRODUCT.findall(html)
        if not prices:
            return out
        out += list(zip(_WSD_NAME.findall(html), (Decimal(p) for p in prices), strict=True))
        page += 1


def testimonials() -> list[int]:
    """Each testimonial's star count, following htmx's next-page links to the end."""
    out, html = [], get(f"{WSD}/testimonials")
    while True:
        out += [r.count("<svg") for r in _RATING.findall(html)]
        nxt = _HX_NEXT.search(html)
        if not nxt:
            return out
        html = get(htmllib.unescape(nxt.group(1)), headers={"Referer": f"{WSD}/testimonials"})


def reviews(first: int) -> list[dict]:
    """Every review through the page's own GraphQL query, `first` at a time."""
    query = htmllib.unescape(_GQL.search(get(f"{WSD}/reviews")).group(1))
    out, after = [], None
    while True:
        body = json.dumps({"query": query, "variables": {"first": first, "after": after}})
        data = json.loads(get(f"{WSD}/api/graphql", body.encode(),
                              {"Content-Type": "application/json"}))["data"]["reviews"]  # fmt: skip
        out += [edge["node"] for edge in data["edges"]]
        if not data["pageInfo"]["hasNextPage"]:
            return out
        after = data["edges"][-1]["cursor"]


def woo(query: str = "") -> list[tuple[str, list[Decimal]]]:
    """Every product's name and the amounts its card shows (two when it is on sale)."""
    out, page = [], 1
    while True:
        try:
            html = get(f"{COURSE}/ecommerce/page/{page}/{query}")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return out
            raise
        blocks = _WOO.findall(html)
        if not blocks:
            return out
        for block in blocks:
            amounts = [Decimal(p.replace(",", "")) for p in _WOO_PRICE.findall(block)]
            out.append((_WOO_NAME.search(block).group(1).strip(), amounts))
        page += 1


def course_ajax_named() -> list[tuple[str, Decimal]]:
    out, offset = [], 0
    while True:
        html = get(f"{COURSE}/ajax/products?offset={offset}")
        names = [n.strip() for n in _COURSE_NAME.findall(html)]
        if not names:
            return out
        prices = [Decimal(p.replace(",", "")) for p in _COURSE_PRICE.findall(html)]
        out += list(zip(names, prices, strict=True))
        offset += len(names)


def course_ajax() -> list[Decimal]:
    out, offset = [], 0
    while True:
        found = _COURSE_PRICE.findall(get(f"{COURSE}/ajax/products?offset={offset}"))
        if not found:
            return out
        out += [Decimal(p.replace(",", "")) for p in found]
        offset += len(found)


def _card_texts(html: str) -> list[list[str]]:
    """Each product card's visible strings, in order: name, genres..., description, price."""
    cards = re.findall(r'class="product-card.*?(?=class="product-card|</main>|$)', html, re.S)
    out = []
    for card in cards:
        text = re.sub(r"<style.*?</style>", "", card, flags=re.S)
        out.append(
            [htmllib.unescape(t.strip()) for t in re.split(r"<[^>]+>", text)[1:] if t.strip()]
        )
    return out


def oxylabs() -> list[dict]:
    """Every game, from each page's Next.js data, with what its card shows beside it."""
    out, page, pages = [], 1, 1
    while page <= pages:
        html = get(f"{OXY}?page={page}")
        props = json.loads(_NEXT_DATA.search(html).group(1))["props"]["pageProps"]
        pages = int(props["pageCount"])
        games, cards = props["products"], _card_texts(html)
        if len(cards) != len(games):
            raise SystemExit(f"page {page}: {len(cards)} cards for {len(games)} games")
        out += [{**g, "card": c} for g, c in zip(games, cards, strict=True)]
        page += 1
    return out


def data_genres(game: dict) -> list[str]:
    """The genres in the page's data (a Python-style list in a string; a genre may hold a quote,
    as "Shoot-'Em-Up" does, which a regex over quotes splits)."""
    return [str(g) for g in ast.literal_eval(str(game.get("genre") or "[]"))]


def turtles() -> dict[str, int]:
    listing = get(f"{FRAMES}?frame=i")
    out = {}
    for link in dict.fromkeys(htmllib.unescape(href) for href in _FAMILY.findall(listing)):
        family = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)["family"][0]
        text = re.sub(
            r"\s+", " ", re.sub(r"<[^>]+>", " ", get(f"https://www.scrapethissite.com{link}"))
        )
        out[family] = int(_DISCOVERED.search(text).group(1))
    return out


def poetry_stock() -> list[int]:
    listing = get(f"{POETRY}/index.html")
    links = _BOOK_LINK.findall(listing)
    return [int(_AVAILABLE.search(get(urllib.parse.urljoin(f"{POETRY}/index.html", h))).group(1))
            for h in links]  # fmt: skip


def answers() -> dict[str, object]:
    products = wsd_products()
    stars = testimonials()
    every_review = reviews(20)
    woo_prices = woo()
    ajax = course_ajax()
    games = oxylabs()
    years = turtles()
    stock = poetry_stock()
    return {
        "E1_products": len(products),
        "E1_under_10": sum(p < 10 for _, p in products),
        "E2_testimonials": len(stars),
        "E2_five_stars": sum(s == 5 for s in stars),
        "E2_star_histogram": {n: stars.count(n) for n in sorted(set(stars))},
        "E3_reviews": len(every_review),
        "E3_five_stars": sum(r["rating"] == 5 for r in every_review),
        "E3_rating_histogram": {
            n: [r["rating"] for r in every_review].count(n)
            for n in sorted({r["rating"] for r in every_review})
        },  # fmt: skip
        "E4_products": len(woo_prices),
        "E4_over_50": sum(max(p) > 50 for _, p in woo_prices),
        "E4_over_50_by_lowest_amount": sum(min(p) > 50 for _, p in woo_prices),
        "E4_more_than_one_amount": [(n, [str(x) for x in p]) for n, p in woo_prices if len(p) > 1],
        "E5_products": len(ajax),
        "E5_over_60": sum(p > 60 for p in ajax),
        "E6_games": len(games),
        "E6_fantasy_by_card": sum("Fantasy" in g["card"][1:-3] for g in games),
        "E6_genre_counts_by_card": dict(
            sorted(
                (
                    (genre, sum(genre in g["card"][1:-3] for g in games))
                    for genre in ("Fantasy", "Puzzle", "Racing", "Horror", "Sci-Fi")
                ),
                key=lambda kv: kv[0],
            )
        ),  # fmt: skip
        "E7_families": len(years),
        "E7_before_1850": sum(y < 1850 for y in years.values()),
        "E7_years": years,
        "E8_books": len(stock),
        "E8_total_available": sum(stock),
    }


def _api_testimonials() -> list[int]:
    """E2 again: the API's pages by number, not by following the links, stars by their colour."""
    out, page = [], 1
    while True:
        url = f"{WSD}/testimonials" if page == 1 else f"{WSD}/api/testimonials?page={page}"
        try:
            html = get(url, headers={"Referer": f"{WSD}/testimonials"})
        except urllib.error.HTTPError:
            return out
        found = _RATING.findall(html)
        if not found:
            return out
        out += [r.count('fill="#ffce31"') for r in found]
        page += 1


def _wsd_prices_by_text() -> list[Decimal]:
    """E1 again: each listing page as plain text, a price being the number after a product's
    description, read between one product link and the next (the category filter repeats pages
    and the detail pages show variant prices, so neither is a second route)."""
    out, page = [], 1
    while True:
        html = get(f"{WSD}/products?page={page}")
        rows = re.split(r'href="https://web-scraping.dev/product/\d+"', html)[1:]
        if not rows:
            return out
        for row in rows:
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row))
            out.append(Decimal(re.findall(r"\b(\d+\.\d\d)\b", text)[0]))
        page += 1


def second_route() -> dict[str, object]:
    by_text = _wsd_prices_by_text()
    one_call = reviews(1000)
    woo_by_name = {n: p for n, p in woo()}
    ajax = course_ajax_named()
    in_woo = [(n, p) for n, p in ajax if n in woo_by_name]
    games = oxylabs()
    listing = get(f"{FRAMES}?frame=i")
    years = []
    for href in dict.fromkeys(htmllib.unescape(h) for h in _FAMILY.findall(listing)):
        text = re.sub(r"<[^>]+>", " ", get(f"https://www.scrapethissite.com{href}"))
        years.append(int(re.search(r"\b(1[5-9]\d\d)\b", text).group(1)))
    table = []
    for link in _BOOK_LINK.findall(get(f"{POETRY}/index.html")):
        page = get(urllib.parse.urljoin(f"{POETRY}/index.html", link))
        row = re.search(r"<th>Availability</th>\s*<td>In stock \((\d+) available\)</td>", page)
        table.append(int(row.group(1)))
    return {
        "E1_products_by_text": len(by_text),
        "E1_under_10_by_text": sum(p < 10 for p in by_text),
        "E2_by_page_number_and_colour": len(_api_testimonials()),
        "E2_five_stars_by_page_number_and_colour": sum(s == 5 for s in _api_testimonials()),
        "E3_reviews_in_one_call": len(one_call),
        "E3_five_stars_in_one_call": sum(r["rating"] == 5 for r in one_call),
        "E4_products_sorted_by_price": len(woo("?orderby=price")),
        "E4_over_50_sorted_by_price": sum(max(p) > 50 for _, p in woo("?orderby=price")),
        "E5_found_in_the_catalogue": f"{len(in_woo)}/{len(ajax)}",
        "E5_prices_that_agree": sum(woo_by_name[n] == [p] for n, p in in_woo),
        "E6_total_count_declared": json.loads(_NEXT_DATA.search(get(OXY)).group(1))["props"][
            "pageProps"
        ]["totalCount"],  # fmt: skip
        "E6_fantasy_by_page_data": sum("Fantasy" in data_genres(g) for g in games),
        "E7_before_1850_any_year_on_the_page": sum(y < 1850 for y in years),
        "E8_total_available_from_the_table": sum(table),
    }


def main() -> int:
    print(json.dumps({"answers": answers(), "second_route": second_route()}, indent=1,
                     default=str))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
