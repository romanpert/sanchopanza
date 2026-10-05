"""The answers to the fourth confirmation's crawls (G*), computed from the sites with no model.

python benchmarks/browse/truth_confirm4.py

Chosen on 2026-10-03, after v7's development round and before any session saw them, on pages no
earlier phase used. They are of the kind the crawl notes were built for: the first page states
how big the whole is, and most of it lies beyond the open page. JSON APIs paginated by `next`
links, by `skip`/`limit` or by page number (G1-G4, G8), two listings paginated server-side (G5,
G7), and one table paginated in the browser (G6). G3's API declares a rate limit in its headers.
Each answer is checked by a second route in `second_route()`.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal

DUMMY = "https://dummyjson.com/products"
SWAPI = "https://swapi.dev/api"
CATS = "https://catfact.ninja/facts"
POKE = "https://pokeapi.co/api/v2/pokemon"
BOOKS = "https://books.toscrape.com/catalogue/category/books"
FANTASY = f"{BOOKS}/fantasy_19"
SEQUENTIAL = f"{BOOKS}/sequential-art_5"
LT_TABLE = "https://www.lambdatest.com/selenium-playground/table-pagination-demo"
STARS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

_BOOK = re.compile(
    r'<p class="star-rating (\w+)">.*?<h3><a href="([^"]+)"[^>]*>.*?'
    r'<p class="price_color">\D*([0-9.]+)</p>',
    re.S,
)
_ROW = re.compile(r"<tr[^>]*>\s*(<td.*?)</tr>", re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def get(url: str, tries: int = 4) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 sanchopanza-truth/1"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if (error.code != 429 and error.code < 500) or attempt == tries - 1:
                raise
            time.sleep(int(error.headers.get("Retry-After") or 5) + 1)
    raise RuntimeError("unreachable")


def follow(url: str, key: str = "results") -> list[dict]:
    """Every item of an API that links its next page."""
    out = []
    while url:
        data = json.loads(get(url))
        out += data[key]
        url = data.get("next")
    return out


def dummy_by_skip() -> list[dict]:
    out, skip = [], 0
    while True:
        data = json.loads(get(f"{DUMMY}?limit=30&skip={skip}"))
        out += data["products"]
        skip += len(data["products"])
        if not data["products"] or skip >= data["total"]:
            return out


def cats_by_page() -> list[dict]:
    out, page, last = [], 1, 1
    while page <= last:
        data = json.loads(get(f"{CATS}?page={page}"))
        last = int(data["last_page"])
        out += data["data"]
        page += 1
    return out


def books(base: str) -> list[tuple[int, str, Decimal]]:
    """(stars, link, price) on every page of a category, following its numbered pages."""
    out, page = [], 1
    while True:
        url = f"{base}/index.html" if page == 1 else f"{base}/page-{page}.html"
        try:
            html = get(url)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return out
            raise
        out += [(STARS[s], link, Decimal(p)) for s, link, p in _BOOK.findall(html)]
        page += 1


def lt_rows() -> list[list[str]]:
    html = get(LT_TABLE)
    table = html[html.find("<table") : html.find("</table>")]
    rows = [
        [re.sub(r"<[^>]+>", "", c).strip() for c in _CELL.findall(r)] for r in _ROW.findall(table)
    ]
    return [r for r in rows if r]


def population(value: str) -> int:
    return int(value) if value.isdigit() else -1


def answers() -> dict[str, object]:
    dummy = dummy_by_skip()
    people = follow(f"{SWAPI}/people/")
    cats = cats_by_page()
    poke = follow(POKE)
    fantasy = books(FANTASY)
    rows = lt_rows()
    sequential = books(SEQUENTIAL)
    planets = follow(f"{SWAPI}/planets/")
    return {
        "G1_products": len(dummy),
        "G1_rated_4_5_or_more": sum(p["rating"] >= 4.5 for p in dummy),
        "G1_page_2_by_a_guessed_page_param_is_page_1": json.loads(get(f"{DUMMY}?page=2"))[
            "products"
        ][0]["id"],
        "G2_people": len(people),
        "G2_eyes_blue": sum(p["eye_color"] == "blue" for p in people),
        "G2_eyes_with_blue_in_them": sum("blue" in p["eye_color"] for p in people),
        "G3_facts": len(cats),
        "G3_longer_than_150": sum(int(c["length"]) > 150 for c in cats),
        "G4_pokemon": len(poke),
        "G4_ending_mega": sum(p["name"].endswith("-mega") for p in poke),
        "G4_with_mega_anywhere": sum("mega" in p["name"] for p in poke),
        "G5_books": len(fantasy),
        "G5_four_stars_or_more": sum(s >= 4 for s, _, _ in fantasy),
        "G6_rows": len(rows),
        "G6_last_name_m": sum(r[2].startswith("M") for r in rows),
        "G7_books": len(sequential),
        "G7_under_20": sum(p < 20 for _, _, p in sequential),
        "G8_planets": len(planets),
        "G8_population_over_1e9": sum(population(p["population"]) > 10**9 for p in planets),
    }


def second_route() -> dict[str, object]:
    dummy = json.loads(get(f"{DUMMY}?limit=0&select=rating"))["products"]
    people = [json.loads(get(f"{SWAPI}/people/{i}/")) for i in range(1, 84) if i != 17]
    cats = json.loads(get(f"{CATS}?limit=1000"))["data"]
    poke = json.loads(get(f"{POKE}?limit=5000"))["results"]
    fantasy_stars = []
    for _, link, _ in books(FANTASY):
        page = get(f"{FANTASY}/{link}")
        fantasy_stars.append(STARS[re.search(r'star-rating (\w+)"', page).group(1)])
    sequential = []
    for _, link, _ in books(SEQUENTIAL):
        page = get(f"{SEQUENTIAL}/{link}")
        row = re.search(r"<th>Price \(incl. tax\)</th>\s*<td>\D*([0-9.]+)</td>", page)
        sequential.append(Decimal(row.group(1)))
    table = lt_rows()
    planets = [json.loads(get(f"{SWAPI}/planets/{i}/")) for i in range(1, 61)]
    return {
        "G1_rated_4_5_or_more_in_one_call": sum(p["rating"] >= 4.5 for p in dummy),
        "G2_eyes_blue_by_id": sum(p["eye_color"] == "blue" for p in people),
        "G3_longer_than_150_by_text": sum(len(c["fact"]) > 150 for c in cats),
        "G3_longer_than_150_in_one_call": sum(int(c["length"]) > 150 for c in cats),
        "G4_ending_mega_in_one_call": sum(p["name"].endswith("-mega") for p in poke),
        "G5_four_stars_or_more_by_book_page": sum(s >= 4 for s in fantasy_stars),
        "G6_last_name_m_by_email": sum(
            r[3].split("@")[0].split(".")[-1].startswith("m") for r in table
        ),  # fmt: skip
        "G7_under_20_by_book_page": sum(p < 20 for p in sequential),
        "G8_population_over_1e9_by_id": sum(population(p["population"]) > 10**9 for p in planets),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"answers": answers(), "second_route": second_route()}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
