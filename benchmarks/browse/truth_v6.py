"""The answers to line v6's development tasks (F*), computed from the sites with no model.

python benchmarks/browse/truth_v6.py

Chosen on 2026-10-03, after confirmation 3's misses were read and before any session saw them,
over sites and pages no earlier phase used (every URL in `benchmarks/` was grepped first). Five
of the eight are shaped like those misses:

- F1 (scrapeme, 48 pages): its Store API gives prices in pence ("14900" for 149.00 pounds), so
  the data the page could load differs from the cards.
- F2 (scrapingcourse's pagination challenge, 13 pages): the pages live at `/pagination/N`; a
  guessed `?page=N` answers 200 with page 1 every time, the scheme confirmation 3's E4 invented.
- F3 and F7 (LambdaTest's OpenCart playground): 75 products with 18 names between them, each its
  own product id: merging by name counts a quarter of them, the dedupe E1 did unasked.
- F4 (the Toolshop, an Angular page over a JSON API): five products in the Pliers category and
  four with "Pliers" in their name, the field-against-text mistake of E6.
- F6 (DataTables, rows served by Ajax): four people hold the position Developer, seven have it
  somewhere in their title.
- F8 (the Rick and Morty API, 42 pages of JSON): the species Human against "Humanoid", and the
  API's own `?species=` filter, which may not mean what the question means.

F5 (DataTables, every row in the HTML, ten drawn at a time) is the plain one. Each answer is
checked by a second route in `second_route()`.
"""

from __future__ import annotations

import html as htmllib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

SCRAPEME = "https://scrapeme.live/shop/"
COURSE = "https://www.scrapingcourse.com"
LT = "https://ecommerce-playground.lambdatest.io/index.php?route=product/category&path="
TOOLSHOP_API = "https://api.practicesoftwaretesting.com"
DT = "https://datatables.net/examples"
RM = "https://rickandmortyapi.com/api/character"
F1_OVER, F2_UNDER, F3_UNDER, F7_OVER = Decimal(150), Decimal(50), Decimal(130), Decimal(150)

_SM_CARD = re.compile(
    r'<a href="(https://scrapeme\.live/shop/[^"]+/)" class="woocommerce-LoopProduct-link.*?'
    r'Price-currencySymbol"[^>]*>[^<]*</span>([0-9.,]+)<',
    re.S,
)
_COURSE_CARD = re.compile(
    r'<a href="(https://scrapingcourse\.com/ecommerce/product/[^"]+)">.*?'
    r'class="product-name">([^<]+)</span>.*?class="product-price[^"]*">\$([0-9.,]+)<',
    re.S,
)
_LT_PAGES = re.compile(r"\((\d+) Pages\)")
_LT_ID = re.compile(r"product_id=(\d+)")
_LT_PRICE = re.compile(r'class="price-new">\$([0-9.,]+)<')
_LT_BRAND = re.compile(r"Brand:\s*</span>\s*<a [^>]*>([^<]+)</a>", re.S)
_LT_DETAIL_PRICE = re.compile(r'<h3 data-update="price" class="price-new[^"]*">\$([0-9.,]+)</h3>')
_DT_ROW = re.compile(r"<tr>\s*" + r"<td>(.*?)</td>\s*" * 6 + r"</tr>", re.S)


def get(url: str, headers: dict[str, str] | None = None, tries: int = 4) -> str:
    """A page, retried: the Toolshop API answers 500 now and then, and the Rick and Morty API
    answers 429 after about thirty requests in ten seconds (Retry-After: 10)."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 sanchopanza-truth/1", **(headers or {})}
    )
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if (error.code != 429 and error.code < 500) or attempt == tries - 1:
                raise
            time.sleep(int(error.headers.get("Retry-After") or 3) + 1)
    raise RuntimeError("unreachable")


def money(text: str) -> Decimal:
    return Decimal(text.replace(",", "").replace("$", "").strip())


def scrapeme_cards() -> dict[str, Decimal]:
    """F1: every card's product URL and shown price, page by page until a 404."""
    out: dict[str, Decimal] = {}
    page = 1
    while True:
        url = SCRAPEME if page == 1 else f"{SCRAPEME}page/{page}/"
        try:
            html = get(url)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return out
            raise
        out.update({link: money(p) for link, p in _SM_CARD.findall(html)})
        page += 1


def scrapeme_store_api() -> dict[str, Decimal]:
    """F1 again: WooCommerce's Store API, which gives prices in minor units."""
    out: dict[str, Decimal] = {}
    page = 1
    while True:
        rows = json.loads(
            get(f"https://scrapeme.live/wp-json/wc/store/products?per_page=100&page={page}")
        )
        if not rows:
            return out
        for row in rows:
            minor = int(row["prices"]["currency_minor_unit"])
            out[row["permalink"]] = Decimal(row["prices"]["price"]) / (10**minor)
        page += 1


def course_pages(scheme: str = "/pagination/{n}") -> list[tuple[str, str, Decimal]]:
    """F2: (product URL, name, price) on every page of the pagination challenge."""
    out, page = [], 1
    while True:
        url = f"{COURSE}/pagination" if page == 1 else COURSE + scheme.format(n=page)
        try:
            html = get(url)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return out
            raise
        cards = [(u, n.strip(), money(p)) for u, n, p in _COURSE_CARD.findall(html)]
        if not cards or page > 60:
            return out
        out += cards
        page += 1


def lt_cards(path: str, query: str = "") -> list[tuple[str, Decimal]]:
    """F3, F7: (product id, shown price) for every card of a category, each card on its own."""
    first = get(LT + path + query)
    pages = int(_LT_PAGES.search(first).group(1))
    out = []
    for page in range(1, pages + 1):
        html = first if page == 1 else get(f"{LT}{path}{query}&page={page}")
        for card in html.split('<div class="product-thumb">')[1:]:
            ids, prices = _LT_ID.findall(card), _LT_PRICE.findall(card)
            if ids and prices:
                out.append((ids[0], money(prices[0])))
    return out


def lt_brand(product_id: str) -> tuple[str, Decimal]:
    html = get(
        f"https://ecommerce-playground.lambdatest.io/index.php?route=product/product&product_id={product_id}"
    )
    brand = _LT_BRAND.search(html)
    price = _LT_DETAIL_PRICE.search(html)
    return (brand.group(1).strip() if brand else ""), (
        money(price.group(1)) if price else Decimal(-1)
    )


def toolshop() -> list[dict]:
    out, page, last = [], 1, 1
    while page <= last:
        data = json.loads(get(f"{TOOLSHOP_API}/products?page={page}"))
        last = int(data["last_page"])
        out += data["data"]
        page += 1
    return out


def dt_html_rows() -> list[tuple[str, ...]]:
    """F5: the zero-configuration table's rows, all of them in the HTML."""
    html = get(f"{DT}/basic_init/zero_configuration.html")
    return [tuple(htmllib.unescape(c).strip() for c in row) for row in _DT_ROW.findall(html)]


def dt_server_rows() -> list[list[str]]:
    """F6: the server-side example's rows, asked of its script all at once."""
    query = urllib.parse.urlencode({"draw": 1, "start": 0, "length": -1})
    return json.loads(get(f"{DT}/server_side/scripts/server_processing.php?{query}"))["data"]


def rick_and_morty() -> list[dict]:
    out, url = [], RM
    while url:
        data = json.loads(get(url))
        out += data["results"]
        url = data["info"]["next"]
    return out


def answers() -> dict[str, object]:
    sm = scrapeme_cards()
    course = course_pages()
    tablets = lt_cards("57")
    cameras = lt_cards("33")
    brands = {pid: lt_brand(pid) for pid, _ in cameras}
    tools = toolshop()
    dt = dt_html_rows()
    server = dt_server_rows()
    rm = rick_and_morty()
    return {
        "F1_products": len(sm),
        "F1_over_150": sum(p > F1_OVER for p in sm.values()),
        "F2_products": len(course),
        "F2_distinct_urls": len({u for u, _, _ in course}),
        "F2_under_50": sum(p < F2_UNDER for _, _, p in course),
        "F2_under_50_page_1_thirteen_times": 13 * sum(p < F2_UNDER for _, _, p in course[:12]),
        "F3_cards": len(tablets),
        "F3_distinct_ids": len({i for i, _ in tablets}),
        "F3_under_130": sum(p < F3_UNDER for _, p in tablets),
        "F4_products": len(tools),
        "F4_pliers_by_category": sum(t["category"]["name"] == "Pliers" for t in tools),
        "F4_pliers_in_name": sum("pliers" in t["name"].lower() for t in tools),
        "F5_rows": len(dt),
        "F5_london_over_100k": sum(r[2] == "London" and money(r[5]) > 100000 for r in dt),
        "F6_rows": len(server),
        "F6_developer_exact": sum(r[2] == "Developer" for r in server),
        "F6_developer_substring": sum("developer" in r[2].lower() for r in server),
        "F7_cards": len(cameras),
        "F7_brands": dict(sorted(_count(b for b, _ in brands.values()).items())),
        "F7_apple_over_150": sum(b == "Apple" and p > F7_OVER for b, p in brands.values()),
        "F7_apple_over_150_card_price": sum(
            brands[i][0] == "Apple" and p > F7_OVER for i, p in cameras
        ),  # fmt: skip
        "F8_characters": len(rm),
        "F8_human": sum(c["species"] == "Human" for c in rm),
        "F8_human_substring": sum("human" in c["species"].lower() for c in rm),
        "F8_species": dict(sorted(_count(c["species"] for c in rm).items())),
    }


def _count(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out = {**out, value: out.get(value, 0) + 1}
    return out


def second_route() -> dict[str, object]:
    api = scrapeme_store_api()
    cards = scrapeme_cards()
    course = course_pages()
    by_query = course_pages("/pagination?page={n}")
    woo = {}
    for link, _, price in course:
        slug = link.rstrip("/").rsplit("/", 1)[-1]
        woo[slug] = price
    tablets_sorted = lt_cards("57", "&sort=p.price&order=ASC&limit=100")
    names = {}
    for card in get(LT + "57" + "&limit=100").split('<div class="product-thumb">')[1:]:
        title = re.search(r'title="([^"]+)"', card)
        price = _LT_PRICE.search(card)
        if title and price:
            names[htmllib.unescape(title.group(1))] = money(price.group(1))
    tools = toolshop()
    pliers = next(t["category"]["id"] for t in tools if t["category"]["name"] == "Pliers")
    by_category = json.loads(get(f"{TOOLSHOP_API}/products?by_category={pliers}"))
    server = dt_server_rows()
    html_rows = dt_html_rows()
    ids = ",".join(str(i) for i in range(1, 827))
    rm = json.loads(get(f"{RM}/{ids}"))
    filtered = json.loads(get(f"{RM}/?species=human"))["info"]["count"]
    cameras = lt_cards("33", "&limit=100")
    brands = {pid: lt_brand(pid) for pid, _ in cameras}
    return {
        "F1_store_api_products": len(api),
        "F1_store_api_over_150": sum(p > F1_OVER for p in api.values()),
        "F1_prices_that_agree": sum(api.get(u) == p for u, p in cards.items()),
        "F2_with_a_guessed_query_scheme": f"{len(by_query)} cards, "
        f"{len({u for u, _, _ in by_query})} distinct",
        "F2_under_50_by_distinct_url": sum(p < F2_UNDER for p in woo.values()),
        "F3_sorted_by_price_one_page": f"{len(tablets_sorted)} cards",
        "F3_under_130_sorted": sum(p < F3_UNDER for _, p in tablets_sorted),
        "F3_under_130_merged_by_name": sum(p < F3_UNDER for p in names.values()),
        "F4_pliers_by_the_api_filter": len(by_category["data"]),
        "F5_london_over_100k_from_the_server_script": sum(
            r[3] == "London" and money(r[5]) > 100000 for r in server
        ),  # fmt: skip
        "F6_developer_exact_from_the_html_table": sum(r[1] == "Developer" for r in html_rows),
        "F7_apple_over_150_one_page": sum(b == "Apple" and p > F7_OVER for b, p in brands.values()),
        "F8_human_by_ids": sum(c["species"] == "Human" for c in rm),
        "F8_the_api_filter_species_human": filtered,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"answers": answers(), "second_route": second_route()}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
