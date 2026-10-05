"""Browse, development: the selection pushback, typed candidates and one judgement per condition.

python benchmarks/browse/free_select_typed.py                       # free: cached Jev, baselines
python benchmarks/browse/free_select_typed.py --env-file PATH/.env  # asks Jev too, under 0.60 USD

The first pass (`free_select.py`) asked Jev, per candidate, whether a snippet supports "X is the
answer to <the whole question>": site names scored 0.9 and the agent's right answers scored low.
Two changes, offline on the same 65 sessions and the same candidate pool:

1. **Type first.** Jev reads the question and names the kind of answer it expects (a closed
   Choice, `points.entities.classification_questions`: person, place, organisation, title,
   number with unit, date, website, other). A figure is extracted as a figure; every name
   candidate is typed the same way from its evidence, and code drops the ones whose type is
   incompatible with the expected one (when both are said at p >= 0.5).
2. **One judgement per constraint.** The question is split into the conditions an answer must
   meet, and each surviving candidate gets one `points.citation` judgement per condition
   ("X <condition>", against the evidence windows that share most words with that condition).
   Code combines them: the candidate's score is the product of its P(supports).

The AssistantBench conditions are **written by hand** per task (`HAND_CONSTRAINTS`), which is
fine for an offline ceiling and is not a live mechanism. BrowseComp questions are never read
here: their conditions come from a mechanical clause split (`split_constraints`), in memory.

Two baselines on the same pool, no model: the top-ranked candidate (most occurrences near the
question's words, `free_select.candidates`), and the candidate the agent's own narration names
most. If neither Jev shape beats them, Jev adds nothing here.

Written: ids, counts, booleans, probabilities. Jev answers are cached by state hash.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import pathlib
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sel = _load("browse_free_select", HERE / "free_select.py")

from sanchopanza.points import entities  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

THRESHOLDS = (0.3, 0.5, 0.7, 0.9)
TYPE_CUT = 0.5  # both the expected type and a candidate's type must be said at least this firmly
MAX_CLAUSES = 5
TYPES: dict[str, str] = {
    "person": "A person or several people, by name",
    "place": "A location or venue: a city, street, park, restaurant, bar, shop, gym or attraction",
    "organisation": "A company, institution, platform, brand or team",
    "title": "The title of a creative work or the name of a product: film, series, book, game "
    "card, fund, ETF",
    "number_with_unit": "A figure: an amount of money, a percentage, a count, an area or another "
    "quantity",
    "date": "A date, a year or a time",
    "website": "A website or a web page",
}
# Types that name the same kind of answer here: a venue is also a business, a platform a site.
COMPATIBLE: dict[str, frozenset[str]] = {
    "place": frozenset({"place", "organisation"}),
    "organisation": frozenset({"organisation", "website", "place"}),
    "website": frozenset({"website", "organisation"}),
}
# Hand-written, per AssistantBench task: what an answer X must satisfy, as "X <condition>".
HAND_CONSTRAINTS: dict[str, tuple[str, ...]] = {
    "AB2aa5dd83": (
        "is the percentage of days in the first week of September, over 2020-2023, on which "
        "Seattle had at least 0.5 mm of precipitation",
    ),
    "ABe2dc3a6b": (
        "is the percentage of New Year's Eves from 2014 to 2023 on which it snowed in Chicago",
    ),
    "ABefc0f3a4": (
        "is a Fidelity international emerging markets equity mutual fund",
        "has no transaction fee",
        "had the lowest percentage increase from May 2019 to May 2024 among those funds",
    ),
    "AB9bdca867": (
        "is the price in USD of the cheapest way to mail a DVD from Hartford, Connecticut to "
        "Colombia with FedEx, DHL or USPS",
    ),
    "ABc7afe008": (
        "is a movie starring Daniel Craig",
        "is shorter than 150 minutes",
        "is available on Netflix in the US",
        "has the highest IMDb rating among those movies",
    ),
    "AB99da66d8": (
        "is the amount in USD that 4 adults and 1 student save by buying Philadelphia Museum of "
        "Art annual passes instead of daily tickets for 5 visits in a year",
    ),
    "AB6b06d186": (
        "is the floor area of the smallest house with at least 2 beds and 2 baths sold in "
        "Prince Edward Island between June 1, 2022 and May 15, 2024 according to Zillow",
    ),
    "ABccec2229": (
        "is an eatery",
        "is open at 11 pm on Wednesdays",
        "is the closest such eatery to Harkness Memorial State Park",
    ),
    "AB4e615af6": (
        "is a paintball place in Cologne, Germany",
        "is within a 10-minute walk of a karting track",
    ),
    "ABfb9ba3ab": (
        "is a social media platform",
        "is the platform on which Andrew Ng has the most followers",
    ),
    "AB3af8028c": (
        "is a Magic: The Gathering Standard card",
        "was banned at the same time as Oko, Thief of Crowns",
        "had the largest price decrease from its all-time high to its all-time low among those "
        "cards",
    ),
    "ABe6bc9808": (
        "is the sale price in USD of a high-rise apartment in Mission Bay, San Francisco, in 2021",
        "is the highest such sale price in 2021",
    ),
    "AB55f42584": (
        "is a TV series Ted Danson has starred in",
        "has more than one season",
        "is available on Amazon Prime Video in the US",
        "has the lowest Rotten Tomatoes rating among those series",
    ),
    "AB4dbedc5e": (
        "is the amount in USD saved by buying a 2024 season pass instead of daily tickets for "
        "one visit a month from June to September to California's Great America",
    ),
    "AB8ad84bd6": (
        "is a supermarket",
        "is within 2 blocks of Lincoln Park in Chicago",
        "sells ready-to-eat salad for under $15",
    ),
    "AB8fa42360": (
        "is one of the Vanguard ETFs VGT, MGK and VONG",
        "had the highest percentage increase between 2013 and 2023 of the three",
    ),
    "AB9e31099f": (
        "is a person in the monday.com C-suite",
        "did not hold a C-suite position at monday.com at the time of its IPO",
    ),
    "AB2ddae3b7": (
        "is the sale price in USD of a single-family house in Queen Anne, Seattle, sold in "
        "January 2023",
        "is the lowest such sale price that month",
    ),
    "AB57d9dc69": (
        "is the amount in USD a family of 2 adults and kids aged 5 and 2 saves by buying Seattle "
        "Children's Museum annual passes instead of daily tickets for 4 visits a year",
    ),
    "AB6e3be83d": (
        "offers martial arts classes",
        "is within a five-minute walk of the New York Stock Exchange",
        "has classes between 7 and 9 pm",
    ),
    "AB52f7224e": (
        "is a feature film starring Isabelle Adjani",
        "is shorter than 2 hours",
        "is available to buy or rent on Vudu (Fandango at Home)",
        "has the highest IMDb rating among those films",
    ),
    "AB557e78ec": (
        "is a bar",
        "is wheelchair accessible",
        "is the closest such bar to the Mummers Museum in Philadelphia",
    ),
    "AB797f7a5b": (
        "is a restaurant that is not takeaway only",
        "is within 1 block of Washington Square Park",
        "has vegan mains for under $15",
    ),
    "AB9baaa267": (
        "is the percentage of June days, over 2020-2023, on which Houston, Texas had a maximum "
        "temperature over 95 F",
    ),
    "AB6f224e77": (
        "is a member of Fubo's management team",
        "joined Fubo in the year of Fubo's IPO",
    ),
}
METHODS = ("typed", "typed_filters", "keywords", "keywords_typed", "narration")
_COMPARATIVE = re.compile(
    r"\b(among|closest|highest|lowest|largest|most|cheapest|smallest)\b", re.IGNORECASE
)


# --- pure -------------------------------------------------------------------------------------


def split_constraints(question: str, limit: int = MAX_CLAUSES) -> tuple[str, ...]:
    """A question's clauses, mechanically: sentences and semicolon parts of at least 20
    characters, the longest `limit` kept in their order."""
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+|;\s*", question) if p.strip()]
    parts = [p for p in parts if len(p) >= 20]
    keep = sorted(sorted(range(len(parts)), key=lambda i: -len(parts[i]))[:limit])
    return tuple(parts[i] for i in keep)


def constraint_claim(candidate: str, condition: str, hand: bool) -> str:
    """The citation claim for one condition: "X <condition>." for a hand-written one, and the
    clause quoted for a mechanical one (it is prose about the answer, not a predicate)."""
    if hand:
        return f"{candidate} {condition}."
    return f"{candidate} is what this describes: {condition}"


def top_type(dist: Mapping[str, float] | None) -> tuple[str | None, float]:
    if not dist:
        return None, 0.0
    best = max(dist, key=dist.__getitem__)
    return best, float(dist[best])


def kind_for(expected: str | None, p: float, agent_kind: str) -> str:
    """'number' when the question asks for a figure (said firmly), else the agent's answer's kind
    when the question's type is unclear, else 'name'."""
    if expected == "number_with_unit" and p >= TYPE_CUT:
        return "number"
    if p < TYPE_CUT:
        return agent_kind or "name"
    return "name"


def keeps(expected: str | None, p_expected: float, found: str | None, p_found: float) -> bool:
    """Does a name candidate survive the type filter? It is dropped only when both types are
    said firmly and they do not name the same kind of answer."""
    if expected is None or found is None or p_expected < TYPE_CUT or p_found < TYPE_CUT:
        return True
    return found in COMPATIBLE.get(expected, frozenset({expected}))


def filters(conditions: Sequence[str]) -> list[int]:
    """Indices of the conditions that are not comparisons across candidates (closest, highest,
    lowest among...): those a snippet about one candidate can settle. All of them when every
    condition is a comparison."""
    keep = [i for i, c in enumerate(conditions) if not _COMPARATIVE.search(c)]
    return keep or list(range(len(conditions)))


def combine(probabilities: Sequence[float | None]) -> float | None:
    """A candidate's score: the product of its P(supports), None if any is missing."""
    if not probabilities or any(p is None for p in probabilities):
        return None
    return math.prod(probabilities)


def narration_pick(names: Sequence[str], narration: str, kind: str) -> tuple[str, float] | None:
    """The candidate the agent's own narration names most (ties to the earlier, higher-ranked
    candidate); None when it names none."""
    counts = [(len(sel.occurrences(narration, n, kind)), -i, n) for i, n in enumerate(names)]
    best = max(counts, default=(0, 0, ""))
    return (best[2], 1.0) if best[0] > 0 else None


def fires(view: Mapping[str, Any], method: str, t: float) -> bool:
    top = view.get(f"{method}_pick")
    return bool(view["answered"] and top and not view[f"{method}_is_own"] and top[1] >= t)


def outcome(views: Sequence[Mapping[str, Any]], method: str, t: float) -> dict[str, Any]:
    fired = [v for v in views if fires(v, method, t)]
    wrong = [v for v in fired if not v["success"]]
    in_set = [v for v in views if v["gold_in_set"]]
    return {
        "method": method,
        "t": t,
        "fires": len(fired),
        "fires_on_wrong": len(wrong),
        "would_fix_upper_bound": sum(v[f"{method}_is_gold"] for v in wrong),
        "fires_on_right_risk": len(fired) - len(wrong),
        "pick_is_gold_when_gold_in_set": f"{sum(v[f'{method}_is_gold'] for v in in_set)}/"
        f"{len(in_set)}",
        "extra_usd": {
            f"{n}_calls": round(sum(n * v["mean_call_usd"] for v in fired), 3)
            for n in sel.EXTRA_CALLS
        },
    }


# --- Jev, cached ------------------------------------------------------------------------------


async def classify(
    text: str, context: str, field: str, squire: Squire | None, cache: Any
) -> dict[str, float] | None:
    state, qs = entities.classification_questions(
        field=field, text=text, options=TYPES, context=context
    )
    key = sel._key(state)
    if key not in cache.rows:
        decision = await sel._decide(squire, "classify", state, qs)
        answer = decision.answer("category") if decision else None
        if answer is None or answer.empty:
            return None
        cache.put(key, {k: round(float(v), 5) for k, v in answer.probabilities.items()})
    return cache.rows[key]


async def view_session(
    row: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
    question: str,
    gold: str,
    squire: Squire | None,
    caches: Mapping[str, Any],
    cut: Any,
) -> dict[str, Any]:
    final = next((c["text"] for c in reversed(calls) if not c["sidechain"] and c["text"]), "")
    own = cut.nav.answer_line(final)
    head = sel.answer_head(own)
    text = sel.clean("\n".join(c["results"] for c in calls))
    narration = "\n".join(c["text"] for c in calls if c["text"] != final)
    expected_dist = await classify(
        question, "", "expected answer type of a question", squire, caches["type"]
    )
    expected, p_expected = top_type(expected_dist)
    kind = kind_for(expected, p_expected, sel.answer_kind(head))
    gold_in = cut.matcher(gold)

    def is_gold(name: str) -> bool:
        return gold_in(name) or sel.same(name, gold, kind)

    pool = sel.candidates(text, question, kind, k=sel.TOP_K)
    own_at = sel.occurrences(text, head, kind) if own else ()
    entries = [(c.text, c.starts) for c in pool]
    if own and own_at and not any(sel.same(n, head, kind) for n, _s in entries):
        entries.append((head, own_at))
    gate = asyncio.Semaphore(sel.JEV_CONCURRENCY)

    async def typed_ok(name: str, starts: Sequence[int]) -> bool:
        if kind != "name" or (own and sel.same(name, head, kind)):
            return True  # a figure is typed by code; the agent's own answer is never dropped
        async with gate:
            dist = await classify(
                name,
                sel.evidence(text, starts, question),
                "kind of thing the candidate names",
                squire,
                caches["type"],
            )
        return keeps(expected, p_expected, *top_type(dist))

    kept = await asyncio.gather(*(typed_ok(n, s) for n, s in entries))
    survivors = [e for e, ok in zip(entries, kept, strict=True) if ok]
    hand = row["task"] in HAND_CONSTRAINTS
    conditions = HAND_CONSTRAINTS.get(row["task"]) or split_constraints(question)
    items = [
        (constraint_claim(n, c, hand), sel.evidence(text, s, c))
        for n, s in survivors
        for c in conditions
    ]
    probs = await sel.score_claims(items, squire, caches["constraint"])
    width = len(conditions)
    typed = [
        (n, combine(probs[i * width : (i + 1) * width])) for i, (n, _s) in enumerate(survivors)
    ]
    kept = filters(conditions)
    only_filters = [
        (n, combine([probs[i * width + j] for j in kept])) for i, (n, _s) in enumerate(survivors)
    ]
    picks = {
        "typed": sel.pick(typed),
        "typed_filters": sel.pick(only_filters),
        "keywords": (pool[0].text, 1.0) if pool else None,
        "keywords_typed": next(((n, 1.0) for n, _s in survivors), None),
        "narration": narration_pick([n for n, _s in entries], narration, kind),
    }
    names = [n for n, _s in entries]
    view = {
        "task": row["task"],
        "set": row["task"][:2],
        "arm": row["arm"],
        "success": bool(row["success"]),
        "answered": bool(own),
        "expected_type": expected,
        "p_expected_type": round(p_expected, 3),
        "kind": kind,
        "conditions": width,
        "conditions_by_hand": hand,
        "asked": len(entries),
        "survived_type": len(survivors),
        "gold_in_set": any(is_gold(n) for n in names),
        "gold_survived_type": any(is_gold(n) for n, _s in survivors),
        "judged": sum(p is not None for p in probs),
        "items": len(items),
        "typed_p_gold": max((p for n, p in typed if p is not None and is_gold(n)), default=None),
        "typed_p_own": next(
            (p for n, p in typed if p is not None and own and sel.same(n, head, kind)), None
        ),
        # P(supports) per condition for the gold, in order: which condition sinks it.
        "gold_parts": next(
            (
                [round(p, 3) if p is not None else None for p in probs[i * width : (i + 1) * width]]
                for i, (n, _s) in enumerate(survivors)
                if is_gold(n)
            ),
            None,
        ),
        "mean_call_usd": float(row["list_usd"]) / max(1, len(calls)),
    }
    for method, chosen in picks.items():
        view[f"{method}_pick"] = (chosen[0], round(chosen[1], 4)) if chosen else None
        view[f"{method}_is_own"] = bool(chosen and own and sel.same(chosen[0], head, kind))
        view[f"{method}_is_gold"] = bool(chosen and is_gold(chosen[0]))
    return view


def public(view: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in view.items() if not k.endswith("_pick")}
    for method in METHODS:
        top = view[f"{method}_pick"]
        out[f"{method}_p_pick"] = top[1] if top else None
    out["mean_call_usd"] = round(view["mean_call_usd"], 4)
    for key in ("typed_p_gold", "typed_p_own"):
        out[key] = round(out[key], 4) if out[key] is not None else None
    return out


async def main_async(key: str) -> dict[str, Any]:
    cut = _load("browse_free_cut", HERE / "free_cut.py")
    known = cut.golds()
    limits = Thresholds(max_usd=sel.JEV_CEILING_USD, max_decisions=20_000)
    squire = Squire(create("jev", api_key=key), thresholds=limits) if key else None
    results = cut.free.RESULTS
    caches = {
        "type": sel.Cache(results / "calib-select-type-jev.jsonl", "probabilities"),
        "constraint": sel.Cache(results / "calib-select-constraint-jev.jsonl", "supports"),
    }
    views = []
    for row in cut.sessions():
        question, gold = known[row["task"]]
        calls = cut.trace.load_calls(cut.trace.folder_of(row["workdir"]))
        if calls:
            views.append(await view_session(row, calls, question, gold, squire, caches, cut))
    subsets = {
        "all": views,
        "AB": [v for v in views if v["set"] == "AB"],
        "BC": [v for v in views if v["set"] == "BC"],
    }
    report = {
        "sessions": len(views),
        "jev_usd_this_run": round(squire.meter.cost_usd, 5) if squire else 0.0,
        "jev_decisions_cached": {k: len(c.rows) for k, c in caches.items()},
        "jev_complete": all(v["judged"] == v["items"] for v in views),
        "type_filter": {
            name: {
                "asked": sum(v["asked"] for v in g),
                "survived": sum(v["survived_type"] for v in g),
                "gold_in_set": sum(v["gold_in_set"] for v in g),
                "gold_survived": sum(v["gold_survived_type"] for v in g),
            }
            for name, g in subsets.items()
        },
        "rule": {
            name: [outcome(g, "typed", t) for t in THRESHOLDS]
            + [outcome(g, "typed_filters", t) for t in THRESHOLDS]
            + [outcome(g, m, 1.0) for m in METHODS[2:]]
            for name, g in subsets.items()
        },
        "per_session": [public(v) for v in views],
    }
    (results / "calib-select-typed.json").write_text(json.dumps(report, indent=1), "utf-8")
    return {"report": report, "views": views}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    nav = _load("browse_nav_key", HERE / "nav_e2e.py")
    report = asyncio.run(main_async(nav.mcp.key_from(args.env_file)))["report"]
    print(json.dumps({k: v for k, v in report.items() if k != "per_session"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
