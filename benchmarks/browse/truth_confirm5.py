"""The answers to the fifth confirmation's crawls (H*), computed from the sites with no model.

python benchmarks/browse/truth_confirm5.py

Chosen on 2026-10-05, after v8.1's development round and before any session saw them, on hosts
no earlier phase used (H6 is a books.toscrape category never used, as G5 and G7 were). The mix is
confirmation 4's: five JSON APIs, paginated by a `Link` header (H1), by page number with a
declared total (H2), by `$offset` with no total at all (H4) and by `next` links with a declared
total (H5), and one (H3) whose list is whole but whose field lives on each item's own page; one
listing paginated server-side with a declared total (H6); a shop whose list is paged by a Next
button over an API (H7); and a table paged in the browser (H8). Two open pages are over 50 KB
(H4 about 785 KB, H5 about 74 KB), so a result that returns them whole is persisted by Claude
Code behind its 2 KB preview. Each answer is checked by a second route in `second_route()`; H8's
second route is the rendered table, page by page, in `check_tasks5.py`.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from decimal import Decimal
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


t4 = _load("browse_truth_confirm4_for_5", HERE / "truth_confirm4.py")
get = t4.get  # retries a 429 or a 5xx, honouring Retry-After

HOUSES = "https://anapioficeandfire.com/api/houses"
WB = "https://api.worldbank.org/v2"
DND = "https://www.dnd5eapi.co"
SQUIRRELS = "https://data.cityofnewyork.us/resource/vfnx-vebw.json"
POTTER = "https://api.potterdb.com/v1/characters"
YOUNG_ADULT = f"{t4.BOOKS}/young-adult_21"
BLAZE = "https://api.demoblaze.com"
PRACTICE = "https://testautomationpractice.blogspot.com/"
_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
_PRODUCT = re.compile(r'\{\s*id:\s*(\d+),\s*name:\s*"([^"]*)",\s*price:\s*([0-9.]+)\s*\}')


def get_with_headers(url: str) -> tuple[str, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 sanchopanza-truth/1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace"), dict(response.headers)


def post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"User-Agent": "Mozilla/5.0 sanchopanza-truth/1",
                 "Content-Type": "application/json"},
    )  # fmt: skip
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def by_link_header(url: str) -> list[dict]:
    """Every item of an API whose body is a bare array and whose next page is in `Link`."""
    out: list[dict] = []
    while url:
        body, headers = get_with_headers(url)
        out += json.loads(body)
        found = _NEXT.search(headers.get("Link", ""))
        url = found.group(1) if found else ""
    return out


def worldbank_by_page() -> tuple[int, list[dict]]:
    """(declared total, every economy) through `page`, at the API's default 50 a page."""
    first = json.loads(get(f"{WB}/country?format=json"))
    meta, out = first[0], list(first[1])
    for page in range(2, int(meta["pages"]) + 1):
        out += json.loads(get(f"{WB}/country?format=json&page={page}"))[1]
    return int(meta["total"]), out


def squirrels_by_offset() -> list[dict]:
    """Every row, 1,000 at a time in a fixed order (the open page has no total and no link)."""
    out: list[dict] = []
    while True:
        rows = json.loads(get(f"{SQUIRRELS}?$order=:id&$limit=1000&$offset={len(out)}"))
        out += rows
        if len(rows) < 1000:
            return out


def potter_by_next() -> tuple[int, list[dict]]:
    first = json.loads(get(POTTER))
    out, url = list(first["data"]), first["links"].get("next")
    while url:
        page = json.loads(get(url))
        out += page["data"]
        url = page["links"].get("next")
    return int(first["meta"]["pagination"]["records"]), out


def blaze_by_pagination() -> list[dict]:
    """The shop's own paging: `/entries`, then `/pagination` from each last key."""
    page = json.loads(get(f"{BLAZE}/entries"))
    out = list(page["Items"])
    while page.get("LastEvaluatedKey"):
        page = post(f"{BLAZE}/pagination", {"id": page["LastEvaluatedKey"]["id"]})
        fresh = [i for i in page["Items"] if i["id"] not in {o["id"] for o in out}]
        if not fresh:
            break
        out += fresh
    return out


def practice_products() -> list[tuple[int, str, Decimal]]:
    html = get(PRACTICE)
    start = html.find("var products = [")
    block = html[start : html.find("];", start)]
    return [(int(i), name, Decimal(p)) for i, name, p in _PRODUCT.findall(block)]


def answers() -> dict[str, object]:
    houses = by_link_header(HOUSES)
    wb_total, economies = worldbank_by_page()
    monsters = json.loads(get(f"{DND}/api/2014/monsters"))
    ratings = [json.loads(get(DND + m["url"]))["challenge_rating"] for m in monsters["results"]]
    squirrels = squirrels_by_offset()
    potter_total, characters = potter_by_next()
    young = t4.books(YOUNG_ADULT)
    blaze = blaze_by_pagination()
    products = practice_products()
    return {
        "H1_houses": len(houses),
        "H1_region_the_reach": sum(h["region"] == "The Reach" for h in houses),
        "H2_declared_total": wb_total,
        "H2_economies": len(economies),
        "H2_high_income": sum(e["incomeLevel"]["value"] == "High income" for e in economies),
        "H2_aggregates": sum(e["incomeLevel"]["value"] == "Aggregates" for e in economies),
        "H3_monsters": len(ratings),
        "H3_challenge_10_or_more": sum(r >= 10 for r in ratings),
        "H4_rows": len(squirrels),
        "H4_distinct_ids": len({s["unique_squirrel_id"] for s in squirrels}),
        "H4_cinnamon": sum(s.get("primary_fur_color") == "Cinnamon" for s in squirrels),
        "H4_cinnamon_in_the_open_page": sum(
            s.get("primary_fur_color") == "Cinnamon" for s in json.loads(get(SQUIRRELS))
        ),  # fmt: skip
        "H5_declared_total": potter_total,
        "H5_characters": len(characters),
        "H5_house_exactly_ravenclaw": sum(
            c["attributes"]["house"] == "Ravenclaw" for c in characters
        ),  # fmt: skip
        "H5_house_naming_ravenclaw": sum(
            "Ravenclaw" in (c["attributes"]["house"] or "") for c in characters
        ),  # fmt: skip
        "H6_books": len(young),
        "H6_over_35": sum(p > 35 for _, _, p in young),
        "H7_products": len(blaze),
        "H7_over_700": sum(float(i["price"]) > 700 for i in blaze),
        "H7_700_or_more": sum(float(i["price"]) >= 700 for i in blaze),
        "H8_products": len(products),
        "H8_over_15": sum(p > 15 for _, _, p in products),
    }


def second_route() -> dict[str, object]:
    reach = by_link_header(f"{HOUSES}?region={urllib.parse.quote('The Reach')}&pageSize=50")
    high = json.loads(get(f"{WB}/incomelevel/HIC/country?format=json&per_page=500"))
    ratings = ",".join(str(r) for r in range(10, 31))
    strong = json.loads(get(f"{DND}/api/2014/monsters?challenge_rating={ratings}"))
    where = urllib.parse.quote("primary_fur_color='Cinnamon'")
    cinnamon = json.loads(get(f"{SQUIRRELS}?$select=count(*)&$where={where}"))
    ravenclaw = json.loads(get(f"{POTTER}?filter%5Bhouse_eq%5D=Ravenclaw"))
    young_prices = []
    for _, link, _ in t4.books(YOUNG_ADULT):
        page = get(f"{YOUNG_ADULT}/{link}")
        row = re.search(r"<th>Price \(incl. tax\)</th>\s*<td>\D*([0-9.]+)</td>", page)
        young_prices.append(Decimal(row.group(1)))
    by_category = [
        i for cat in ("phone", "notebook", "monitor")
        for i in post(f"{BLAZE}/bycat", {"cat": cat})["Items"]
    ]  # fmt: skip
    return {
        "H1_region_the_reach_by_filter": len(reach),
        "H2_high_income_by_income_level": int(high[0]["total"]),
        "H3_challenge_10_or_more_by_filter": int(strong["count"]),
        "H4_cinnamon_by_count": int(cinnamon[0]["count"]),
        "H5_house_exactly_ravenclaw_by_filter": int(ravenclaw["meta"]["pagination"]["records"]),
        "H6_over_35_by_book_page": sum(p > 35 for p in young_prices),
        "H7_over_700_by_category": sum(float(i["price"]) > 700 for i in by_category),
        "H7_products_by_category": len(by_category),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"answers": answers(), "second_route": second_route()}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
