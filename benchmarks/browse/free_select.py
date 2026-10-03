"""Browse, development: would a Stop-hook "another candidate fits" pushback have fixed a session?

python benchmarks/browse/free_select.py                       # free: candidate recall, cached Jev
python benchmarks/browse/free_select.py --env-file PATH/.env  # asks Jev too, under 0.60 USD

The calibration (`free_cut.py`) found 14 wrong AssistantBench sessions in which the gold answer
reached the agent in a tool result and the agent answered something else: a failure of
selection, not of search. This is the one place a decision could raise answers rather than cut
spend. The bet, offline, on the same 65 recorded sessions:

1. At the end of a session, collect the candidate answers in its tool results, mechanically (no
   model): spans of the same kind as the agent's own ANSWER - numbers, or capitalised names and
   tickers - ranked by how often they occur near the question's words. `candidates` is pure.
2. Ask Jev, per candidate, the citation point's own question (`points.citation`, Choice
   supports / contradicts / says_nothing) on the claim "the answer to the question is X" and a
   short evidence snippet around X's occurrences. The candidate with the highest P(supports) is
   Jev's pick; the agent's own answer is scored the same way when it occurs in the results.
   A second shape, `set`, asks `points.triage.set_questions` once over all of them (a Choice,
   the candidate as the page title and its evidence as the text) and picks the largest share.
3. The pushback would fire when Jev's pick differs from the agent's answer at P(supports) >= t.
   A fired wrong session whose pick is the gold is a possible fix (if the agent switches); a
   fired right session is a risk (if it switches away).

BrowseComp text stays in memory: what is written is task ids, counts, booleans and
probabilities, never a question, a candidate or an answer. Jev answers are cached by the hash of
the state (`calib-select-jev.jsonl`, numbers only), so a re-run is free.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import re
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.points import citation, triage  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

TOP_K = 30  # candidates per session sent to Jev, besides the agent's own answer
WINDOW = 150  # characters each side of an occurrence, for ranking
SNIPPET = 220  # characters each side of an occurrence, for the evidence Jev reads
SNIPPETS = 3
MAX_TOKENS = 8
THRESHOLDS = (0.5, 0.7, 0.9)
JEV_CEILING_USD = 0.60
JEV_CONCURRENCY = 6
EXTRA_CALLS = (1, 5)  # a pushback buys at least one more call; checking a candidate, about five


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


STOP = _words(
    """
    a an the and or of for to in on at by with from as is are was were be been it its this that
    these those which what who whom whose where when how why than then there their they them he
    she his her i you we our your my me us not no yes do does did done can could will would
    should may might must shall have has had having if but so such any all each every more most
    less least many much some other another only also very just about into over under after
    before between during within without based according provide answer percentage
    """
)
# Lower-case words allowed inside a capitalised name: "Oko, Thief of Crowns", "Glass Onion:
# A Knives Out Mystery", "Nosferatu the Vampyre", "Potash Markets - Clark Street".
CONNECT = _words(
    """
    of the a an and de la le du des del da di y for on in at to von van
    """
)
# A word that starts a sentence or labels a page, not a name.
GENERIC = _words(
    """
    The This That These Those There Here It Its He She They We You I A An In On At For To Of And
    Or But If When Where What Which Who How Why Based According Search Web Links Title Results
    Result Note Notes Source Sources Page Home Menu Login Sign Read More See Also Yes No However
    Image Images Video Videos News Click Learn About Contact Privacy Terms Cookie Cookies
    Copyright Skip Main Content Share Back Next Previous Top Bottom Open Close Show Hide Hours
    Map Reviews Review Photos Price Prices Website Phone Address Directions Overview Jan Feb Mar
    Apr Jun Jul Aug Sep Sept Oct Nov Dec January February March April May June July August
    September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday
    REMINDER
    """
)
_URL = re.compile(r"https?://\S+|www\.\S+")
_REMINDER = re.compile(r"^REMINDER:.*$", re.MULTILINE)  # WebSearch's own trailer, every time
_JSON_KEYS = re.compile(r'"(?:title|url)":"')
_WORD = re.compile(r"[\w'’®&]+(?:[.\-][\w'’®&]+)*")
_GAP = re.compile(r"(?: |\s?:\s|\s[-–]\s)")
_NUMBER = re.compile(
    r"(?<![\w.])(\$|€|£)?\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?"
    r"(%|percent\b|million\b|m\b|k\b|sq\.?\s?ft\b|sqft\b|square feet\b)?",
    re.IGNORECASE,
)
_MULT = {"million": 1e6, "m": 1e6, "k": 1e3}


# --- pure: answers, candidates, matching ------------------------------------------------------


def norm(text: str) -> str:
    """Lower case, letters and digits only (accents kept), single spaces."""
    return re.sub(r"[^\w.]+|_", " ", text.lower().replace(",", "")).strip(" .")


def answer_head(answer: str) -> str:
    """The answer itself, without the explanation agents append: up to the first dash, bracket,
    semicolon, sentence end or comma followed by a lower-case word."""
    head = re.split(r"\s[—–-]\s|\s\(|;|\.\s|\n|,\s(?=[a-z])", (answer or "").strip(), maxsplit=1)
    return head[0].strip().strip("*").strip(" .~")


def answer_kind(head: str) -> str:
    """'number' when the head is a figure (with its unit or currency), 'name' when it has words,
    '' when there is no answer."""
    if not head.strip():
        return ""
    words = [w for w in re.findall(r"[^\W\d_]+", head) if w.lower() not in _MULT]
    unit = {"usd", "percent", "sqft", "sq", "ft", "square", "feet", "about", "approximately"}
    if re.search(r"\d", head) and all(w.lower() in unit for w in words):
        return "number"
    return "name"


def clean(text: str) -> str:
    """Tool results without URLs or the JSON keys of a search result list."""
    return _JSON_KEYS.sub(" ", _URL.sub(" ", _REMINDER.sub(" ", text or "")))


def keywords(question: str) -> frozenset[str]:
    """The question's content words, cut to five letters so plurals and inflections match."""
    words = re.findall(r"[^\W_]+", question.lower())
    return frozenset(w[:5] for w in words if len(w) >= 3 and w not in STOP)


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[^\W_]+", text.lower()) if len(w) >= 3}


def _capital(word: str) -> bool:
    return word[:1].isupper() or (word.isupper() and len(word) >= 2)


def name_spans(text: str) -> list[tuple[str, int]]:
    """(span, start) for every capitalised name in `text`: maximal runs of capitalised words
    joined by spaces, a colon or a spaced dash, with lower-case connectors inside. Each run also
    yields its parts at a colon or dash, so "Glass Onion: A Knives Out Mystery" gives both."""
    words = list(_WORD.finditer(text))
    out: list[tuple[str, int]] = []
    last: tuple[int, int, list[re.Match[str]]] | None = None
    i = 0
    while i < len(words):
        if not _capital(words[i].group()):
            i += 1
            continue
        run = [words[i]]
        j = i + 1
        while j < len(words) and len(run) < MAX_TOKENS:
            gap = text[words[j - 1].end() : words[j].start()]
            word = words[j].group()
            if not _GAP.fullmatch(gap):
                break
            if _capital(word) or word.lower() in CONNECT and gap == " ":
                run.append(words[j])
            else:
                break
            j += 1
        while run and not _capital(run[-1].group()):
            run.pop()
        if run:
            start, end = run[0].start(), run[-1].end()
            out.append((text[start:end], start))
            pieces = re.split(r"\s?:\s|\s[-–]\s", text[start:end])
            offset = start
            for piece in pieces if len(pieces) > 1 else []:
                at = text.find(piece, offset)
                if piece and _capital(piece):
                    out.append((piece, at))
                offset = at + len(piece)
            # A one-word name and the run after its comma: "Oko, Thief of Crowns".
            joins = last and len(last[2]) == 1 and text[last[1] : start] == ", "
            if joins and len(run) + 1 <= MAX_TOKENS:
                out.append((text[last[0] : end], last[0]))
            last = (start, end, run)
        i = max(j, i + 1)
    return out


def number_value(match: re.Match[str]) -> float:
    whole = float(match.group(2).replace(",", ""))
    value = whole + (float(match.group(3)) if match.group(3) else 0.0)
    unit = (match.group(4) or "").lower()
    return value * _MULT.get(unit, 1.0)


def number_spans(text: str) -> list[tuple[str, float, int]]:
    """(surface, value, start) for every figure; bare four-digit years are left out."""
    out = []
    for match in _NUMBER.finditer(text):
        value = number_value(match)
        bare = not match.group(1) and not match.group(3) and not match.group(4)
        if bare and value.is_integer() and 1900 <= value <= 2100:
            continue
        out.append((match.group().strip(), value, match.start()))
    return out


@dataclass(frozen=True, slots=True)
class Candidate:
    text: str  # the most frequent surface form
    key: str  # what two occurrences share: the normalised name, or the value
    count: int
    score: float
    starts: tuple[int, ...]


def _question_numbers(question: str) -> set[float]:
    return {round(v, 6) for _s, v, _p in number_spans(question)} | {
        float(y) for y in re.findall(r"\b(?:19|20)\d\d\b", question)
    }


def candidates(text: str, question: str, kind: str, k: int = TOP_K) -> list[Candidate]:
    """The top `k` candidate answers of `kind` in `text` (already `clean`ed), ranked by the sum
    over occurrences of 1 + the number of the question's words within `WINDOW` characters.
    A candidate made only of the question's own words, or a generic word, is dropped."""
    want = keywords(question)
    asked = _stems(question)
    groups: dict[str, list[tuple[str, int]]] = {}
    if kind == "number":
        known = _question_numbers(question)
        for surface, value, start in number_spans(text):
            if round(value, 6) in known:
                continue
            groups.setdefault(f"{value:g}", []).append((surface, start))
    elif kind == "name":
        for span, start in name_spans(text):
            key = norm(span)
            tokens = key.split()
            if not tokens or (len(tokens) == 1 and span in GENERIC) or len(key) < 2:
                continue
            if all(t[:5] in asked or t in STOP for t in tokens):
                continue
            groups.setdefault(key, []).append((span, start))
    out = []
    for key, seen in groups.items():
        score = 0.0
        for _surface, start in seen:
            window = text[max(0, start - WINDOW) : start + WINDOW]
            score += 1 + len(want & _stems(window))
        forms: dict[str, int] = {}
        for surface, _start in seen:
            forms[surface] = forms.get(surface, 0) + 1
        surface = max(forms, key=lambda f: (forms[f], len(f)))
        out.append(Candidate(surface, key, len(seen), score, tuple(s for _f, s in seen)))
    return sorted(out, key=lambda c: (-c.score, -c.count, c.key))[:k]


def occurrences(text: str, head: str, kind: str) -> tuple[int, ...]:
    """Where the agent's own answer occurs in `text`: by value for a figure, as a
    case-insensitive literal otherwise."""
    if kind == "number":
        found = number_spans(head)
        if not found:
            return ()
        target = found[0][1]
        return tuple(
            p for _s, v, p in number_spans(text) if abs(v - target) <= max(abs(target) * 0.01, 1e-9)
        )
    if len(head) < 2:
        return ()
    return tuple(m.start() for m in re.finditer(re.escape(head), text, re.IGNORECASE))


def evidence(text: str, starts: Sequence[int], question: str, limit: int = SNIPPETS) -> str:
    """Up to `limit` non-overlapping windows around the occurrences, the ones sharing most of the
    question's words first, joined in text order."""
    want = keywords(question)
    ranked = sorted(
        starts,
        key=lambda s: (-len(want & _stems(text[max(0, s - SNIPPET) : s + SNIPPET])), s),
    )
    picked: list[int] = []
    for start in ranked:
        if all(abs(start - other) > 2 * SNIPPET for other in picked):
            picked.append(start)
        if len(picked) == limit:
            break
    parts = [
        re.sub(r"\s+", " ", text[max(0, s - SNIPPET) : s + SNIPPET]).strip() for s in sorted(picked)
    ]
    return " ... ".join(parts)


def same(a: str, b: str, kind: str) -> bool:
    """Do two answers name the same thing? Figures within 1 %; names equal after normalising, or
    one inside the other covering at least half of the longer's words."""
    if kind == "number":
        x, y = number_spans(a), number_spans(b)
        return bool(x and y) and abs(x[0][1] - y[0][1]) <= max(abs(y[0][1]) * 0.01, 1e-9)
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long = sorted((na, nb), key=len)
    inside = f" {short} " in f" {long} "
    return inside and len(short.split()) * 2 >= len(long.split())


def claim(candidate: str, question: str) -> str:
    """The citation point's claim; the candidate first so a long question truncates, not it."""
    return f"{candidate} is the answer to this question: {question}"


def pick(scored: Sequence[tuple[str, float | None]]) -> tuple[str, float] | None:
    """The candidate with the highest P(supports), or None when nothing was scored."""
    known = [(c, p) for c, p in scored if p is not None]
    return max(known, key=lambda cp: cp[1]) if known else None


SHAPES = ("claim", "set")  # per-candidate citation Choice; one Choice over all candidates


def fires(view: Mapping[str, Any], t: float, shape: str = "claim") -> bool:
    """The pushback rule: the session gave an answer, Jev's pick is a different candidate, and
    its probability (P(supports), or its share of the set Choice) is at least `t`."""
    top = view.get(f"{shape}_pick")
    return bool(view["answered"] and top and not view[f"{shape}_pick_is_own"] and top[1] >= t)


def outcome(views: Sequence[Mapping[str, Any]], t: float, shape: str = "claim") -> dict[str, Any]:
    """What the rule at `t` would do: fires, possible fixes (wrong session, pick is the gold),
    risks (right session), and the cost of the extra turn at each session's mean call cost."""
    fired = [v for v in views if fires(v, t, shape)]
    wrong = [v for v in fired if not v["success"]]
    return {
        "t": t,
        "fires": len(fired),
        "fires_on_wrong": len(wrong),
        "would_fix_upper_bound": sum(v[f"{shape}_pick_is_gold"] for v in wrong),
        "fires_on_right_risk": len(fired) - len(wrong),
        "extra_usd": {
            f"{n}_calls": round(sum(n * v["mean_call_usd"] for v in fired), 3) for n in EXTRA_CALLS
        },
    }


# --- reading the sessions (local only) --------------------------------------------------------


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Cache:
    """state hash -> Jev's numbers (P(supports), or the set Choice's shares); no text."""

    def __init__(self, path: pathlib.Path, field: str) -> None:
        self.path, self.field, self.rows = path, field, {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row[field]

    def put(self, key: str, value: Any) -> None:
        self.rows[key] = value
        with self.path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"key": key, self.field: value}) + "\n")


def _key(state: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


async def _decide(squire: Squire | None, point: str, state: Any, qs: Any) -> Any:
    if squire is None or squire.meter.cost_usd >= JEV_CEILING_USD * 0.98:
        return None
    decision = await squire.decide(point, state, qs)
    return None if decision.failed else decision


async def score_claims(
    items: Sequence[tuple[str, str]], squire: Squire | None, cache: Cache
) -> list[float | None]:
    """P(supports) for each (claim, section), from the cache or Jev, under the ceiling."""
    gate = asyncio.Semaphore(JEV_CONCURRENCY)

    async def one(item: tuple[str, str]) -> float | None:
        state, qs = citation.questions(*item)
        key = _key(state)
        if key in cache.rows:
            return cache.rows[key]
        async with gate:
            decision = await _decide(squire, "citation", state, qs)
        answer = decision.answer("relation") if decision else None
        if answer is None or answer.empty:
            return None
        supports = float(answer.probabilities.get("supports", 0.0))
        cache.put(key, supports)
        return supports

    return list(await asyncio.gather(*(one(i) for i in items)))


async def score_set(
    pages: Sequence[tuple[str, str]], question: str, squire: Squire | None, cache: Cache
) -> list[float | None]:
    """Each candidate's share of one Choice over all of them (`triage.set_questions`, the
    candidate as the page title and its evidence as the text)."""
    if not pages:
        return []
    state, qs = triage.set_questions(purpose=question, pages=list(pages))
    key = _key(state)
    if key not in cache.rows:
        decision = await _decide(squire, "triage_set", state, qs)
        answer = decision.answer("needed") if decision else None
        if answer is None or answer.empty:
            return [None] * len(pages)
        ids = [triage.page_id(i) for i in range(len(pages))]
        cache.put(key, [float(answer.probabilities.get(i, 0.0)) for i in ids])
    shares = cache.rows[key]
    return [shares[i] if i < len(shares) else None for i in range(len(pages))]


def session_items(
    calls: Sequence[Mapping[str, Any]], question: str, final: str
) -> tuple[str, str, list[Candidate], tuple[int, ...], str]:
    """(head, kind, candidates, own occurrences, cleaned text) of one session."""
    text = clean("\n".join(c["results"] for c in calls))
    head = answer_head(final)
    kind = answer_kind(head)
    pool = candidates(text, question, kind or "name", k=10_000)
    return head, kind or "name", pool, occurrences(text, head, kind), text


def verdict(
    shape: str,
    scored: Sequence[tuple[str, float | None]],
    head: str,
    kind: str,
    is_gold: Any,
) -> dict[str, Any]:
    """Jev's pick under one shape, and whether it is the agent's own answer or the gold."""
    chosen = pick(scored)
    return {
        f"{shape}_pick": (chosen[0], round(chosen[1], 4)) if chosen else None,
        f"{shape}_pick_is_own": bool(chosen and head and same(chosen[0], head, kind)),
        f"{shape}_pick_is_gold": bool(chosen and is_gold(chosen[0])),
        f"{shape}_p_own": next(
            (round(p, 4) for n, p in scored if p is not None and same(n, head, kind)), None
        ),
        f"{shape}_p_gold": max(
            (round(p, 4) for n, p in scored if p is not None and is_gold(n)), default=None
        ),
        f"{shape}_scored": sum(p is not None for _n, p in scored),
    }


async def view_session(
    row: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
    question: str,
    gold: str,
    squire: Squire | None,
    caches: Mapping[str, Cache],
    tools: Any,
) -> tuple[dict[str, Any], dict[str, list[tuple[str, float | None]]]]:
    """One session: its candidates, Jev's numbers under both shapes, and no text that leaves
    the process except through `public`. `tools` is the `free_cut` module (matcher, nav)."""
    final = next((c["text"] for c in reversed(calls) if not c["sidechain"] and c["text"]), "")
    own = tools.nav.answer_line(final)
    head, kind, pool, own_at, text = session_items(calls, question, own)
    gold_in = tools.matcher(gold)

    def is_gold(text_: str) -> bool:
        return gold_in(text_) or same(text_, gold, kind)

    asked = [(c.text, evidence(text, c.starts, question)) for c in pool[:TOP_K]]
    if own and own_at and not any(same(n, head, kind) for n, _e in asked):
        asked.append((head, evidence(text, own_at, question)))
    names = [n for n, _e in asked]
    claims = await score_claims(
        [(claim(n, question), e) for n, e in asked], squire, caches["claim"]
    )
    shares = await score_set(asked, question, squire, caches["set"])
    scored = {
        "claim": list(zip(names, claims, strict=True)),
        "set": list(zip(names, shares, strict=True)),
    }
    gold_rank = next((i for i, c in enumerate(pool) if is_gold(c.text)), None)
    view = {
        "task": row["task"],
        "set": row["task"][:2],
        "arm": row["arm"],
        "source": row["_source"],
        "success": bool(row["success"]),
        "drift": bool(row.get("drift")),
        "answered": bool(own),
        "kind": kind,
        "gold_reached_agent": gold_in(text),
        "candidates": len(pool),
        "gold_rank_in_pool": gold_rank,
        "gold_in_top_k": gold_rank is not None and gold_rank < TOP_K,
        "own_in_results": bool(own_at),
        "asked": len(asked),
        "mean_call_usd": float(row["list_usd"]) / max(1, len(calls)),
    }
    for shape in SHAPES:
        view |= verdict(shape, scored[shape], head if own else "", kind, is_gold)
    return view, scored


def public(view: Mapping[str, Any]) -> dict[str, Any]:
    """A view without any text: ids, counts, booleans and probabilities."""
    out = {k: v for k, v in view.items() if not k.endswith("_pick")}
    for shape in SHAPES:
        top = view[f"{shape}_pick"]
        out[f"{shape}_p_pick"] = top[1] if top else None
    out["mean_call_usd"] = round(view["mean_call_usd"], 4)
    return out


def recall(views: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def med(xs: list[float]) -> float | None:
        return statistics.median(xs) if xs else None

    in_top = [v for v in views if v["gold_in_top_k"]]
    return {
        "sessions": len(views),
        "gold_reached_agent": sum(v["gold_reached_agent"] for v in views),
        "gold_in_candidate_pool": sum(v["gold_rank_in_pool"] is not None for v in views),
        "gold_in_top_k": len(in_top),
        "median_pool_size": med([v["candidates"] for v in views]),
        "median_gold_rank_when_in_pool": med(
            [v["gold_rank_in_pool"] + 1 for v in views if v["gold_rank_in_pool"] is not None]
        ),
        **{
            f"{shape}_pick_is_gold_when_gold_in_top_k": sum(
                v[f"{shape}_pick_is_gold"] for v in in_top
            )
            for shape in SHAPES
        },
    }


def groups_of(views: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    ab = [v for v in views if v["set"] == "AB"]
    return {
        "AB right": [v for v in ab if v["success"]],
        "AB wrong, gold reached": [v for v in ab if not v["success"] and v["gold_reached_agent"]],
        "AB wrong, gold not reached": [
            v for v in ab if not v["success"] and not v["gold_reached_agent"]
        ],
        "BC": [v for v in views if v["set"] == "BC"],
    }


def rules(views: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    subsets = {
        "all": list(views),
        "AB": [v for v in views if v["set"] == "AB"],
        "BC": [v for v in views if v["set"] == "BC"],
    }
    return {
        shape: {name: [outcome(g, t, shape) for t in THRESHOLDS] for name, g in subsets.items()}
        for shape in SHAPES
    }


async def main_async(key: str) -> dict[str, Any]:
    cut = _load("browse_free_cut", HERE / "free_cut.py")
    known = cut.golds()
    limits = Thresholds(max_usd=JEV_CEILING_USD, max_decisions=20_000)
    squire = Squire(create("jev", api_key=key), thresholds=limits) if key else None
    caches = {
        "claim": Cache(cut.free.RESULTS / "calib-select-jev.jsonl", "supports"),
        "set": Cache(cut.free.RESULTS / "calib-select-set-jev.jsonl", "shares"),
    }
    views, texts = [], {}
    for row in cut.sessions():
        question, gold = known[row["task"]]
        calls = cut.trace.load_calls(cut.trace.folder_of(row["workdir"]))
        if not calls:
            continue
        view, scored = await view_session(row, calls, question, gold, squire, caches, cut)
        views.append(view)
        texts[(row["task"], row["arm"])] = scored
    report = {
        "sessions": len(views),
        "top_k": TOP_K,
        "jev_usd_this_run": round(squire.meter.cost_usd, 5) if squire else 0.0,
        "jev_decisions_cached": {k: len(c.rows) for k, c in caches.items()},
        "jev_complete": all(v[f"{s}_scored"] == v["asked"] for v in views for s in SHAPES),
        "recall": {k: recall(g) for k, g in groups_of(views).items()},
        "answered": {k: sum(v["answered"] for v in g) for k, g in groups_of(views).items()},
        "rule": rules(views),
        "per_session": [public(v) for v in views],
    }
    (cut.free.RESULTS / "calib-select.json").write_text(
        json.dumps(report, indent=1), encoding="utf-8"
    )
    return {"report": report, "views": views, "texts": texts, "cut": cut}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    nav = _load("browse_nav_key", HERE / "nav_e2e.py")
    key = nav.mcp.key_from(args.env_file)
    report = asyncio.run(main_async(key))["report"]
    print(json.dumps({k: v for k, v in report.items() if k != "per_session"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
