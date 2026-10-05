"""Browse, development: the extraction check again, now told the size the site declares.

python benchmarks/browse/extract_replay2.py --env-file PATH/.env    # asks Jev, under a ceiling
python benchmarks/browse/extract_replay2.py                         # free: re-scores the cache

`extract_replay.py` asked Jev whether an extraction's result looked complete, from the request,
the code and the result alone: AUC 0.602, not usable. Read by hand, 10 of its 17 wrong results
sat beside a page that said how big it was ("117 items" against 81 laptops read, "Page 1 of 50"
against 3 pages, "87 items" against 74 films), and the question never saw that page. So this
version adds what the first snapshot of the session declares (`declared_size`: item totals,
"page x of y", the last numbered pagination link, a Next or load-more control) and asks whether
the result's coverage agrees with it.

The same cases as the first version plus confirmation 2's sessions (read after its verdict):
exploratory, post hoc, it confirms nothing. It is a cheap filter that decides whether the check
goes into the "with sanchopanza" arm of a registered confirmation, not a result.

Fixed before the first call to Jev (this file is committed first): a result is flagged when
`extract_ok` < 0.5. The check passes the filter only if, over every case judged, AUC >= 0.80,
the cut catches at least half of the wrong results and flags at most 10 % of the right ones.
The rule with no model (`size_rule`: the site declares a size and no number in the result equals
it) is reported beside it; if the rule alone does as well, the check goes in as code, not Jev.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import hashlib
import json
import os
import pathlib
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import extract_replay as first  # noqa: E402

from sanchopanza.contract import Truth  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402
from sanchopanza.text import truncate  # noqa: E402

nav = first.nav
RESULTS = nav.RESULTS
CACHE = RESULTS / "extract-replay2-cache.jsonl"
REPORT = RESULTS / "extract-replay2.json"
SOURCES = (*first.SOURCES, "nav-confirm2")
CEILING_USD = 0.10
CUT = 0.5
PASS_AUC = 0.80

_TOTAL = re.compile(
    r"\b(\d[\d,]*)\s+(items|results|products|records|entries|books|quotes|rows)\b", re.I
)
_PAGE_OF = re.compile(r"\bpage\s+\d+\s+of\s+(\d[\d,]*)", re.I)
_SHOWING = re.compile(r"\bshowing\s+\d+\s*(?:-|to|–)\s*\d+\s+of\s+(\d[\d,]*)", re.I)
_PAGE_LINK = re.compile(r'link "(\d{1,4})"')
_NEXT = re.compile(r'(?:link|button) "(?:next|more|load more|show more)\b', re.I)

QUESTION = Truth(
    "`result` is what a piece of code returned after collecting data across a website to "
    "answer `request`. `site_declares` is what the site's first page says about how much there "
    "is (item totals, page counts, a Next control), or nothing if it says nothing. Does the "
    "result's coverage agree with what the site declares, and is it complete and internally "
    "consistent, so that an answer built on it can be trusted?",
    criteria={
        "true": {
            "what": "The pages and items it read agree with the size the site declares (or the "
            "site declares none and nothing in the result suggests a part), nothing is "
            "duplicated, and the figure asked for follows from them",
            "examples": [
                "the site says 'Page 1 of 50' and the result read 50 pages and 1,000 books",
                "the site says '117 items' and the result counted over 117 laptops",
            ],
        },
        "false": {
            "what": "It read fewer pages or items than the site declares, counts the same items "
            "more than once, reports totals that cannot be right, found nothing, or returned "
            "an error instead of data",
            "examples": [
                "the site says '117 items' and the result counted 81 laptops",
                "the site says 'Page 1 of 50' and the result processed 3 pages",
                "the same 6 tablets on each of 4 pages, counted as 24",
                "an error: execution context was destroyed",
            ],
        },
    },
)


def _number(text: str) -> int:
    return int(text.replace(",", ""))


def declared_size(snapshot: str) -> list[str]:
    """What a page's snapshot says about the site's size, as short lines; [] if nothing."""
    out: list[str] = []
    totals = sorted({_number(m.group(1)) for m in _TOTAL.finditer(snapshot)})
    out += [f"{n} {m}" for n, m in _first_noun(snapshot, totals)]
    pages = {_number(m.group(1)) for m in _PAGE_OF.finditer(snapshot)}
    out += [f"page 1 of {n}" for n in sorted(pages)]
    out += [f"showing results of {_number(m.group(1))}" for m in _SHOWING.finditer(snapshot)][:1]
    links = [int(n) for n in _PAGE_LINK.findall(snapshot) if int(n) < 1900]
    if len(links) >= 2:
        out.append(f"numbered pagination links up to {max(links)}")
    if _NEXT.search(snapshot):
        out.append("a Next or load-more control")
    return out[:6]


def _first_noun(snapshot: str, totals: list[int]) -> list[tuple[int, str]]:
    nouns: dict[int, str] = {}
    for m in _TOTAL.finditer(snapshot):
        nouns.setdefault(_number(m.group(1)), m.group(2).lower())
    return [(n, nouns[n]) for n in totals if n > 1][:3]


def declared_numbers(lines: list[str]) -> set[int]:
    """The sizes in `declared_size`'s lines that a complete result would mention."""
    return {
        int(m.group(1))
        for line in lines
        if "control" not in line
        for m in [re.search(r"(\d+)\D*$", line) or re.match(r"(\d+)", line)]
        if m
    }


def size_rule(result: str, declared: list[str]) -> bool:
    """Flag with no model: the site declares a size and no number in the result equals it."""
    sizes = declared_numbers(declared)
    if not sizes:
        return False
    found = {_number(n) for n in re.findall(r"\d[\d,]*", result) if len(n) < 9}
    return not (sizes & found)


def first_snapshot(workdir: str) -> str:
    """The session's first saved page snapshot (Playwright MCP writes one per navigation)."""
    found = sorted(
        glob.glob(os.path.join(workdir, ".playwright-mcp", "page-*.yml")), key=os.path.getmtime
    )
    if not found:
        return ""
    return pathlib.Path(found[0]).read_text(encoding="utf-8", errors="replace")


def _questions() -> dict[str, str]:
    questions = {t[0]: t[2] for t in nav.EVERY_TASK}
    for name, file in (("browse_nav_confirm", "nav_confirm.py"),
                       ("browse_nav_confirm2", "nav_confirm2.py")):  # fmt: skip
        module = first._load(name, HERE / file)
        tasks = getattr(module, "confirmation", module).TASKS
        questions.update({t[0]: t[2] for t in tasks})
    return questions


def cases() -> list[dict[str, Any]]:
    questions = _questions()
    out = []
    for source in SOURCES:
        for row in nav.done_sessions(RESULTS / f"{source}-sessions.jsonl"):
            navs = row.get("tools", {}).get("mcp__playwright__browser_navigate", 0)
            if row.get("not_run") or navs > first.MAX_NAVIGATIONS or row["task"] not in questions:
                continue
            path = first.transcript_of(row.get("workdir", ""))
            found = first.last_extraction(path) if path else None
            if not found:
                continue
            declared = declared_size(first_snapshot(row.get("workdir", "")))
            out.append({"source": source, "task": row["task"], "arm": row["arm"],
                        "run": row["run"], "right": bool(row["success"]),
                        "request": questions[row["task"]], "declared": declared,
                        **found})  # fmt: skip
    return out


def state_of(case: dict[str, Any]) -> dict[str, str]:
    return {
        "request": truncate(case["request"], 500),
        "site_declares": "; ".join(case["declared"]) or "nothing",
        "result": truncate(case["result"], 1600),
        "code": truncate(case["code"], 600),
    }


async def judge(case: dict[str, Any], squire: Squire | None, cache: dict[str, Any]) -> float | None:
    state = state_of(case)
    key = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    if key in cache:
        return cache[key]
    if squire is None or squire.meter.cost_usd >= CEILING_USD:
        return None
    decision = await squire.decide("extract_check", state, {"extract_ok": QUESTION})
    value = decision.answer("extract_ok").truth
    if value is not None:
        cache[key] = value
        with CACHE.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"key": key, "extract_ok": value}) + "\n")
    return value


def _share(flags: list[bool]) -> str:
    return f"{sum(flags)}/{len(flags)}"


def verdict(right: list[float], wrong: list[float]) -> dict[str, Any]:
    """The filter fixed in the docstring, applied as written."""
    area = first.auc(right, wrong)
    caught = sum(v < CUT for v in wrong)
    flagged = sum(v < CUT for v in right)
    passes = bool(
        area is not None
        and area >= PASS_AUC
        and wrong
        and caught * 2 >= len(wrong)
        and flagged <= 0.10 * len(right)
    )
    return {"auc": area, "wrong_caught": f"{caught}/{len(wrong)}",
            "right_flagged": f"{flagged}/{len(right)}", "passes": passes}  # fmt: skip


def _load_cache() -> dict[str, Any]:
    if not CACHE.exists():
        return {}
    rows = (json.loads(line) for line in CACHE.read_text(encoding="utf-8").splitlines())
    return {row["key"]: row["extract_ok"] for row in rows}


async def main_async(key: str) -> dict[str, Any]:
    cache = _load_cache()
    squire = (
        Squire(create("jev", api_key=key), thresholds=Thresholds(max_usd=CEILING_USD))
        if key
        else None
    )
    rows = cases()
    for case in rows:
        case["extract_ok"] = await judge(case, squire, cache)
        case["size_rule"] = size_rule(case["result"], case["declared"])
    judged = [c for c in rows if c["extract_ok"] is not None]
    declared = [c for c in judged if c["declared"]]
    report = {
        "cases": len(rows), "judged": len(judged),
        "right": sum(c["right"] for c in rows), "wrong": sum(not c["right"] for c in rows),
        "with_declared_size": len([c for c in rows if declared_numbers(c["declared"])]),
        "jev_usd_this_run": round(squire.meter.cost_usd, 5) if squire else 0.0,
        "jev": verdict([c["extract_ok"] for c in judged if c["right"]],
                       [c["extract_ok"] for c in judged if not c["right"]]),
        "jev_where_site_declares": verdict(
            [c["extract_ok"] for c in declared if c["right"]],
            [c["extract_ok"] for c in declared if not c["right"]]),
        "size_rule": {"wrong_caught": _share([c["size_rule"] for c in rows if not c["right"]]),
                      "right_flagged": _share([c["size_rule"] for c in rows if c["right"]])},
        "detail": [{k: c[k] for k in ("source", "task", "arm", "run", "right", "extract_ok",
                                      "size_rule", "declared")} | {"result": c["result"][:200]}
                   for c in rows],
    }  # fmt: skip
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    key = nav.mcp.key_from(args.env_file) if args.env_file else ""
    report = asyncio.run(main_async(key))
    print(json.dumps({k: v for k, v in report.items() if k != "detail"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
