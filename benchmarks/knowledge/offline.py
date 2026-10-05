"""The knowledge layer, development: search, read and long documents, replayed for free.

python benchmarks/knowledge/offline.py search [--live-sample 30]   # backend answers cached
python benchmarks/knowledge/offline.py read                        # FRAMES pages cached
python benchmarks/knowledge/offline.py longdocs --qasper PATH      # QASPER test split (JSONL)
python benchmarks/knowledge/offline.py pick                        # FRAMES pages as one corpus
python benchmarks/knowledge/offline.py sessions                    # parts 1 and 2 per session
python benchmarks/knowledge/offline.py guess                       # the fetch v2 confirmation

No model and no money. What each part measures:

1. `search`: the WebSearch queries of the first FRAMES pilot's base sessions (SONNET, HAIKU; 193
   distinct), each replayed through the backends' cached top-ten answers (Wikipedia's search API
   with the OR fallback, ddgs Bing, ddgs Yahoo; collected on 2026-10-05, private cache). Per
   session, the share of the task's gold Wikipedia articles any of its searches returned, for
   WebSearch (its own results in the transcript) and for `serp.merge` of Wikipedia and the web
   chain at k=8 and k=10. Tokens: WebSearch's result as the transcript holds it, against
   `search`'s rendered page on a live sample of the same queries (`--live-sample`; Wikipedia and
   Bing answer for free, the answers then cached). The gold is Wikipedia articles, which favours
   a Wikipedia backend: read the recall as "the article the task needs", not as web search.
2. `read`: every WebFetch of both FRAMES pilots that returned 200 and whose page is cached as
   HTML (as in `browse/free_fetch_offline.py`), with the agent's WebFetch prompt as purpose:
   WebFetch's summary, fetch v2's passages, and `read` (fetch v2 under `knowledge.LONG_CHARS`,
   the cascade past it), at the default budget and at 4,000 characters. Gold: the task's
   answer under the grader's rule; tokens: characters / 4 of what the agent receives.
3. `longdocs`: one question per QASPER test paper (the 300 of `longdocs/run.py`, its seed),
   each paper as one document (sections as places, paragraphs as blocks, cut as `read` cuts),
   the question as purpose. Recall of the answer sentences (QASPER's highlighted evidence, each
   found whole in what is returned, whitespace folded) and tokens, for the whole paper, fetch
   v2's passages and `read`'s cascade (BM25: a key is never used here) at three budgets.

4. `pick`: every page of part 2 (both pilots' WebFetch pages, unique URLs) as one knowledge base;
   each FRAMES task whose answer is on at least one of them asks `pick` with its question as
   purpose (BM25: no key). Whether a chosen document holds the answer, whether the returned
   passages do, and tokens. The pool holds the pages the agents found for their own tasks.

5. `sessions`: the first pilot's base sessions, what their WebSearch and WebFetch calls put in
   the context and what their readers cost (the fitted 0.0227 USD a search, 0.0241 a fetch, of
   `browse/free_fetch_offline.py`), against the same calls through `search` (the live sample's
   mean page) and `read` (each page replayed for the WebFetch prompt). Calls as the sessions
   made them: whether an agent would search or open pages differently is not measured.

6. `guess`: the guessed-address rule of `read` (`knowledge_tool.GUESS_LIMIT`) replayed on the 120
   -FETCH2 sessions of the fetch v2 confirmation. Every page call and search of a session in
   time order (subagents included: one server serves the whole session); a page call that came
   back 404 or with the disambiguation note is a miss, a search starts the count again, and at
   the limit the next page call is the substituted search. Reported: where it fires, the page
   calls and misses after its first firing, and the spend after it (cumulative list price per
   API call): the most the rule could save, since the agent would then read from the results.

Nothing from a task, a query, a page or a paper is written: the reports hold counts and sizes.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib.util
import json
import pathlib
import random
import re
import statistics
import sys
import time
import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza import knowledge, serp, webpage, webpage_v2  # noqa: E402
from sanchopanza.text import BM25Index, split_sentences  # noqa: E402
from sanchopanza.webpage import Block, Page  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fo = _load("knowledge_fetch_offline", ROOT / "benchmarks" / "browse" / "free_fetch_offline.py")
trace, frames = fo.trace, fo.frames
CACHE = fo.CACHE / "knowledge"  # backend answers and the live sample's search cache: private
RESULTS = ROOT / "docs" / "results" / "2026-10-05-knowledge"
P1 = fo.CACHE / "frames-pilot" / "sessions.jsonl"
BASE_ARMS = ("SONNET", "HAIKU")
URL = re.compile(r"https?://[^\s\"'\)\]\\]+")
CPT = 4.0  # characters per token, as every earlier replay
BACKENDS = ("wikipedia-or", "ddgs_bing", "ddgs_yahoo")
SEED = 20261005


def _q(values: Sequence[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[int(p * (len(ordered) - 1))] if ordered else 0.0


def _tokens(values: Sequence[float]) -> dict[str, float]:
    return {"mean": round(statistics.mean(values)) if values else 0,
            "median": round(_q(values, 0.5)), "p90": round(_q(values, 0.9))}  # fmt: skip


def wiki_title(url: str) -> str | None:
    parts = urllib.parse.urlparse(url.strip())
    host = parts.netloc.lower().replace("en.m.wikipedia", "en.wikipedia")
    if "en.wikipedia.org" not in host or not parts.path.startswith("/wiki/"):
        return None
    title = urllib.parse.unquote(parts.path[6:]).replace(" ", "_").split("#")[0]
    return title[:1].upper() + title[1:] if title else None


def _titles(urls: Sequence[str]) -> set[str]:
    return {t for t in (wiki_title(u) for u in urls) if t}


# --- 1. search -----------------------------------------------------------------------------------


def websearch_calls() -> list[dict[str, Any]]:
    """Every WebSearch of the first pilot's base sessions: its query, result size and links."""
    out = []
    for line in P1.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        if row.get("arm") not in BASE_ARMS:
            continue
        uses: dict[str, str] = {}
        results: dict[str, str] = {}
        for path in sorted(trace.folder_of(row["workdir"]).rglob("*.jsonl")):
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                entry = json.loads(raw) if raw.strip() else {}
                content = (entry.get("message") or {}).get("content")
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use" and block.get("name") == "WebSearch":
                        uses[str(block["id"])] = str((block.get("input") or {}).get("query", ""))
                    elif block.get("type") == "tool_result":
                        text = trace._result_text(block.get("content"))
                        results[str(block.get("tool_use_id"))] = text
        for use_id, query in uses.items():
            text = results.get(use_id, "")
            out.append({"task": row["task"], "arm": row["arm"], "query": query,
                        "chars": len(text), "links": URL.findall(text)})  # fmt: skip
    return out


def gold_links() -> dict[str, set[str]]:
    out = {}
    for row in frames.read_frames():
        try:
            links = ast.literal_eval(row.get("wiki_links") or "[]")
        except (ValueError, SyntaxError):
            links = []
        out[frames.tid_of(row)] = _titles([str(u) for u in links])
    return out


def _backend(name: str) -> dict[str, list[str]]:
    data = json.loads((CACHE / f"cache_{name}.json").read_text(encoding="utf-8"))
    return {q: list(v.get("urls") or []) for q, v in data.items()}


def _hits(urls: Sequence[str], source: str) -> list[serp.Hit]:
    return [serp.Hit("", u, "", source) for u in urls]


def ours(query: str, cached: Mapping[str, Mapping[str, list[str]]], k: int, web: bool) -> list[str]:
    """`Searcher`'s merge on cached answers: Wikipedia, and the first web backend with results."""
    wiki = _hits(cached["wikipedia-or"].get(query, []), "wikipedia")
    chain = cached["ddgs_bing"].get(query, []) or cached["ddgs_yahoo"].get(query, [])
    groups = [wiki, _hits(chain, "web")] if web else [wiki]
    return [h.url for h in serp.merge(groups, k)]


def session_recall(calls: Sequence[Mapping[str, Any]], gold: Mapping[str, set[str]], found) -> dict:
    out = {}
    for arm in BASE_ARMS:
        hits = total = tasks = 0
        for task in sorted({c["task"] for c in calls if c["arm"] == arm}):
            got: set[str] = set()
            for call in calls:
                if call["task"] == task and call["arm"] == arm:
                    got |= found(call)
            hit = len(gold[task] & got)
            hits, total, tasks = hits + hit, total + len(gold[task]), tasks + (hit > 0)
        out[arm] = {"gold_found": hits, "gold": total, "recall": round(hits / total, 3),
                    "tasks_with_one": tasks}  # fmt: skip
    return out


def live_sample(queries: Sequence[str], n: int) -> dict[str, Any]:
    """`search` as an agent gets it, on `n` of the queries: size, results, errors, latency."""
    import os

    os.environ["SANCHOPANZA_KNOWLEDGE_DIR"] = str(CACHE / "live")
    searcher = serp.default_searcher()
    sizes, counts, seconds, down = [], [], [], 0
    for query in random.Random(SEED).sample(sorted(queries), min(n, len(queries))):
        start = time.time()
        text = searcher.search(query, serp.DEFAULT_K)
        seconds.append(time.time() - start)
        if text.startswith(serp.DOWN):
            down += 1
            continue
        sizes.append(len(text) / CPT)
        counts.append(int(text.split(" ", 1)[0]) if text[:1].isdigit() else 0)
    return {"queries": len(seconds), "down": down, "tokens": _tokens(sizes),
            "results_mean": round(statistics.mean(counts), 2) if counts else 0,
            "empty": sum(c == 0 for c in counts), "seconds_median": round(_q(seconds, 0.5), 2),
            "breakers": {k: v.fails for k, v in searcher.breakers.items()}}  # fmt: skip


def search_report(sample: int) -> dict[str, Any]:
    calls = websearch_calls()
    gold = gold_links()
    cached = {name: _backend(name) for name in BACKENDS}
    queries = sorted({c["query"] for c in calls})
    missing = [q for q in queries if any(q not in cached[b] for b in BACKENDS)]
    arms = {
        "WebSearch": lambda c: _titles(c["links"]),
        "search k=8 (wikipedia + web chain)": lambda c: _titles(ours(c["query"], cached, 8, True)),
        "search k=10 (wikipedia + web chain)": lambda c: _titles(
            ours(c["query"], cached, 10, True)
        ),
        "wikipedia alone k=8": lambda c: _titles(ours(c["query"], cached, 8, False)),
        "search k=8 or WebSearch's (union)": lambda c: (
            _titles(ours(c["query"], cached, 8, True)) | _titles(c["links"])
        ),
    }
    empty = sum(not ours(q, cached, 8, True) for q in queries)
    report = {
        "calls": len(calls),
        "queries": len(queries),
        "queries_without_cached_answers": len(missing),
        "sessions": len({(c["task"], c["arm"]) for c in calls}),
        "search_empty_queries": empty,
        "recall": {name: session_recall(calls, gold, f) for name, f in arms.items()},
        "websearch_tokens": _tokens([c["chars"] / CPT for c in calls if c["chars"]]),
    }
    if sample:
        report["search_live_sample"] = live_sample(queries, sample)
    return report


# --- 2. read -------------------------------------------------------------------------------------


def _v2_text(page: Page, url: str, purpose: str, budget: int) -> str:
    out = webpage_v2.passages(page, purpose, budget)
    return f"{page.title}\n{url}\n{out.header()}\n\n{out.text}"


def _read_text(page: Page, url: str, purpose: str, budget: int) -> str:
    out = asyncio.run(knowledge.read_page(page, purpose, budget))
    return f"{page.title}\n{url}\n{out}"


def read_report() -> dict[str, Any]:
    data = json.loads(fo.RECORDS.read_text(encoding="utf-8"))
    golds = fo.gold_map()
    pages: dict[str, Page | None] = {}
    rows = []
    for f in data["fetches"]:
        if f["src"] == "CAL" or f["code"] != 200 or not f["url"]:
            continue
        if f["url"] not in pages:
            html = fo._html_of(f["url"])
            pages[f["url"]] = webpage_v2.page_from_html(html) if html is not None else None
        page = pages[f["url"]]
        if page is None:
            continue
        gold = golds.get(f["task"], "")
        whole = "\n".join(c.text for c in page.chunks)
        row = {
            "gold_on_page": fo.present(gold, whole) if gold else False,
            "summary_tok": len(f["summary"]) / CPT,
            "gold_summary": fo.present(gold, f["summary"]) if gold else False,
            "long": knowledge._eligible_total(page, f["prompt"]) > knowledge.LONG_CHARS,
        }
        for budget in (4_000, webpage.DEFAULT_BUDGET):
            for name, make in (("v2", _v2_text), ("read", _read_text)):
                text = make(page, f["url"], f["prompt"], budget)
                row[f"{name}_{budget}_tok"] = len(text) / CPT
                row[f"{name}_{budget}_gold"] = fo.present(gold, text) if gold else False
        rows.append(row)
    return {"fetches": len(rows), **_read_summary(rows),
            "long_pages": _read_summary([r for r in rows if r["long"]])}  # fmt: skip


def _read_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    with_gold = [r for r in rows if r["gold_on_page"]]
    out: dict[str, Any] = {
        "calls": len(rows),
        "gold_on_page": len(with_gold),
        "summary": {
            "gold": sum(r["gold_summary"] for r in with_gold),
            "tokens": _tokens([r["summary_tok"] for r in rows]),
        },  # fmt: skip
    }
    for budget in (4_000, webpage.DEFAULT_BUDGET):
        for name in ("v2", "read"):
            out[f"{name}_{budget}"] = {
                "gold": sum(r[f"{name}_{budget}_gold"] for r in with_gold),
                "tokens": _tokens([r[f"{name}_{budget}_tok"] for r in rows]),
            }
    return out


# --- 3. long documents ---------------------------------------------------------------------------


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def qasper_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    ld = _load("knowledge_longdocs_run", ROOT / "benchmarks" / "longdocs" / "run.py")
    papers = {p["id"]: p for p in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
    rows = []
    for row in ld.build(path):
        paper = papers[row["id"]]
        asked = [q.strip() for q in paper["qas"]["question"]]
        first = paper["qas"]["answers"][asked.index(row["question"])]["answer"][0]
        spans = [_fold(h).rstrip(".") for h in first.get("highlighted_evidence") or [] if h]
        whole = _fold(" ".join(x for _, x in row["pages"]))
        if not spans or not all(s in whole for s in spans):
            continue
        blocks = [Block(x, " > ".join(p.strip() for p in s.split(":::") if p.strip()), "text")
                  for s, x in row["pages"]]  # fmt: skip
        page = Page(str(paper.get("title") or ""), tuple(webpage_v2.chunks_of(blocks)))
        rows.append({"question": row["question"], "spans": spans, "page": page,
                     "pages": row["pages"]})  # fmt: skip
    return rows


FIXTURES = ("longdocs.jsonl", "longdocs-sentences.jsonl", "lateral-wholedocs.jsonl")


class _Counting:
    """The recorded decider, counting the calls it had no recording for."""

    name = "recorded"

    def __init__(self, inner: Any) -> None:
        self.inner, self.misses, self.calls, self.usd = inner, 0, 0, 0.0

    async def decide(self, point: str, state: Any, questions: Any) -> Any:
        decision = await self.inner.decide(point, state, questions)
        self.calls += 1
        self.misses += decision.model == "-"
        self.usd += decision.cost_usd
        return decision


def judged_arm(rows: Sequence[Mapping[str, Any]], budgets: Sequence[int]) -> dict[str, Any]:
    """`knowledge.long_judged` with Jev's recorded answers (2026-09-27/28 QASPER runs), on the
    papers whose every call was recorded: one paragraph per passage, as those runs asked."""
    from dataclasses import replace

    from sanchopanza import Squire, Thresholds
    from sanchopanza.providers.recorded import RecordedDecider
    from sanchopanza.webpage import Chunk

    entries = [
        json.loads(x)
        for name in FIXTURES
        for x in (ROOT / "fixtures" / name).read_text(encoding="utf-8").splitlines()
        if x
    ]
    recorded = RecordedDecider(entries)
    covered, judged, usd, calls = [], {b: [] for b in budgets}, [], []
    for row in rows:
        page = Page(row["page"].title, tuple(Chunk(s, x) for s, x in row["pages"]))
        if len(page.chunks) > knowledge.JUDGE_MAX:
            continue
        texts, spent, ok, n_calls = {}, 0.0, True, 0
        for budget in budgets:
            counting = _Counting(recorded)
            squire = Squire(counting, thresholds=replace(Thresholds(), max_decisions=10_000))
            got = asyncio.run(knowledge.long_judged(page, row["question"], budget, squire))
            if counting.misses or got is None:
                ok = False
                break
            texts[budget] = knowledge.render_excerpts(page, got)
            n_calls = counting.calls
            spent = max(spent, counting.usd)
        if ok:
            covered.append(row)
            usd.append(spent)
            calls.append(n_calls)
            for budget in budgets:
                judged[budget].append(texts[budget])
    out: dict[str, Any] = {
        "questions_covered": len(covered),
        "usd_per_read_mean": round(statistics.mean(usd), 5) if usd else 0,
        "calls_per_read_mean": round(statistics.mean(calls), 1) if calls else 0,
    }
    for budget in budgets:
        if covered:
            out[f"judged (recorded Jev), {budget:,}"] = _scored(covered, judged[budget])
            v2 = [webpage_v2.passages(r["page"], r["question"], budget).text for r in covered]
            out[f"fetch v2 passages on the same papers, {budget:,}"] = _scored(covered, v2)
    return out


# The BM25 cascade measured here and not shipped: places (top-level sections or pages) ranked by
# BM25 up to SECTION_POOL budgets of text, their passages by BM25 up to PASSAGE_POOL budgets, then
# each passage cut to its matching sentences with WINDOW neighbours.
SECTION_POOL, PASSAGE_POOL, WINDOW = 4, 2, 1


def _place(heading: str) -> str:
    return heading.split(knowledge.PATH_SEP, 1)[0] if heading else ""


def bm25_cascade(page: Page, purpose: str, budget: int) -> list[knowledge.Excerpt]:
    allowed = knowledge.eligible(purpose, page.chunks)
    groups: list[list[int]] = []
    for i in allowed:
        same = groups and groups[-1][-1] == i - 1 and _place(page.chunks[i].heading) == _place(
            page.chunks[groups[-1][-1]].heading)  # fmt: skip
        groups = [*groups[:-1], [*groups[-1], i]] if same else [*groups, [i]]
    texts = [page.chunks[g[0]].heading + "\n" + "\n".join(page.chunks[i].text for i in g)
             for g in groups]  # fmt: skip
    kept: set[int] = set()
    used = 0
    for g, _score in BM25Index(texts).top(purpose, len(groups)):
        kept |= set(groups[g])
        used += sum(len(page.chunks[i].text) for i in groups[g])
        if used >= SECTION_POOL * budget:
            break
    ranked = [i for i in knowledge._ranked_chunks(page, purpose, allowed) if i in kept]
    if not ranked:
        return []
    pool, size = [], 0
    for i in ranked:
        pool, size = [*pool, i], size + len(page.chunks[i].text)
        if size >= PASSAGE_POOL * budget:
            break
    sentences = {i: split_sentences(page.chunks[i].text) or [page.chunks[i].text] for i in pool}
    flat = [(i, j) for i in pool for j in range(len(sentences[i]))]
    scores = BM25Index([sentences[i][j] for i, j in flat]).scores(purpose)
    by_chunk: dict[int, list[float]] = {i: [] for i in pool}
    for (i, _j), score in zip(flat, scores, strict=True):
        by_chunk[i].append(score)
    candidates = []
    for i in pool:
        n = len(by_chunk[i])
        hits = [j for j, x in enumerate(by_chunk[i]) if x > 0]
        ids = sorted({k for j in hits for k in range(max(0, j - WINDOW), min(n, j + WINDOW + 1))})
        text = knowledge._join(sentences[i], ids or [0])
        if len(text) > budget // 2:
            text = sentences[i][max(ids or [0], key=lambda j: by_chunk[i][j])]
        candidates.append((i, page.chunks[i].heading, text))
    return knowledge._fill(candidates, budget)


def _scored(rows: Sequence[Mapping[str, Any]], texts: Sequence[str]) -> dict[str, Any]:
    every = any_ = 0
    shares = []
    for row, text in zip(rows, texts, strict=True):
        folded = _fold(text)
        found = [s in folded for s in row["spans"]]
        every += all(found)
        any_ += any(found)
        shares.append(len(text) / max(1, sum(len(c.text) for c in row["page"].chunks)))
    n = len(rows)
    return {"all_answer_sentences": round(every / n, 3), "any": round(any_ / n, 3),
            "tokens": _tokens([len(t) / CPT for t in texts]),
            "text_share_mean": round(statistics.mean(shares), 3)}  # fmt: skip


def longdocs_report(path: pathlib.Path) -> dict[str, Any]:
    rows = qasper_rows(path)
    whole = ["\n".join(c.text for c in r["page"].chunks) for r in rows]
    report: dict[str, Any] = {
        "questions": len(rows),
        "papers_past_long_chars": sum(
            knowledge._eligible_total(r["page"], r["question"]) > knowledge.LONG_CHARS for r in rows
        ),  # fmt: skip
        "paper_tokens": _tokens([len(t) / CPT for t in whole]),
        "whole paper": _scored(rows, whole),
    }
    for budget in (4_000, 8_000, 16_000):
        v2 = [webpage_v2.passages(r["page"], r["question"], budget).text for r in rows]
        report[f"fetch v2 passages, {budget:,}"] = _scored(rows, v2)
        cascade = [
            knowledge.render_excerpts(r["page"], bm25_cascade(r["page"], r["question"], budget))
            for r in rows
        ]
        report[f"BM25 cascade, not shipped, {budget:,}"] = _scored(rows, cascade)
        read = [asyncio.run(knowledge.read_page(r["page"], r["question"], budget)) for r in rows]
        report[f"read as shipped, {budget:,}"] = _scored(rows, read)
    report["judged"] = judged_arm(rows, (4_000, 8_000, 16_000))
    return report


# --- 4. pick ------------------------------------------------------------------------------------


def pick_report() -> dict[str, Any]:
    data = json.loads(fo.RECORDS.read_text(encoding="utf-8"))
    golds = fo.gold_map()
    prompts = {frames.tid_of(r): r["Prompt"] for r in frames.read_frames()}
    fetched = [f for f in data["fetches"] if f["src"] != "CAL" and f["code"] == 200 and f["url"]]
    docs = []
    for url in sorted({f["url"] for f in fetched}):
        html = fo._html_of(url)
        page = webpage_v2.page_from_html(html) if html is not None else None
        if page is not None and page.chunks:
            docs.append(knowledge.Doc(url, page))
    text_of = {d.source: "\n".join(c.text for c in d.page.chunks) for d in docs}
    rows = []
    for task in sorted({f["task"] for f in fetched}):
        gold = golds.get(task, "")
        own = {f["url"] for f in fetched if f["task"] == task} & set(text_of)
        holders = {u for u in own if gold and fo.present(gold, text_of[u])}
        if not holders:
            continue
        text = asyncio.run(knowledge.pick_docs(docs, prompts[task], webpage.DEFAULT_BUDGET))
        chosen = {d.source for d in docs if f"\n{d.source}\n" in text}
        rows.append({"holder_chosen": bool(holders & chosen), "own_chosen": len(own & chosen),
                     "chosen": len(chosen), "gold_in_text": fo.present(gold, text),
                     "tokens": len(text) / CPT})  # fmt: skip
    n = len(rows)
    return {
        "documents": len(docs),
        "tasks": n,
        "a_chosen_document_is_one_of_the_tasks_own_answer_pages": sum(
            r["holder_chosen"] for r in rows
        ),
        "chosen_from_the_tasks_own_pages_mean": round(
            statistics.mean(r["own_chosen"] for r in rows), 2
        ),
        "chosen_mean": round(statistics.mean(r["chosen"] for r in rows), 2),
        "answer_in_returned_passages": sum(r["gold_in_text"] for r in rows),
        "tokens": _tokens([r["tokens"] for r in rows]),
    }


# --- 5. per session -------------------------------------------------------------------------------


def sessions_report() -> dict[str, Any]:
    searched = json.loads((RESULTS / "search.json").read_text(encoding="utf-8"))
    serp_tokens = searched["search_live_sample"]["tokens"]["mean"]
    fits = json.loads((fo.frames.RESULTS / "fetch-offline.json").read_text(encoding="utf-8"))
    per_search = fits["fit_usd_per_call"]["frames"]["search"]
    per_fetch = fits["fit_usd_per_call"]["frames"]["fetch"]
    calls = websearch_calls()
    data = json.loads(fo.RECORDS.read_text(encoding="utf-8"))
    pages: dict[str, Page | None] = {}
    out: dict[str, Any] = {
        "serp_tokens_per_search": serp_tokens,
        "reader_usd_per_search": per_search,
        "reader_usd_per_fetch": per_fetch,
    }
    for arm in BASE_ARMS:
        mine = [c for c in calls if c["arm"] == arm]
        fetched = [f for f in data["fetches"] if f["src"] == "P1" and f["arm"] == arm]
        base_tokens = sum(c["chars"] for c in mine) / CPT
        ours_tokens = len(mine) * serp_tokens
        opened = 0
        for f in fetched:
            if f["code"] != 200 or not f["url"]:
                continue
            if f["url"] not in pages:
                html = fo._html_of(f["url"])
                pages[f["url"]] = webpage_v2.page_from_html(html) if html is not None else None
            page = pages[f["url"]]
            base_tokens += len(f["summary"]) / CPT
            opened += 1
            if page is not None:
                ours_tokens += len(_read_text(page, f["url"], f["prompt"], 8_000)) / CPT
            else:  # not HTML today: the second WebFetch runs, at WebFetch's size
                ours_tokens += len(f["summary"]) / CPT
        sessions = len({c["task"] for c in mine})
        out[arm] = {
            "sessions": sessions,
            "searches": len(mine),
            "fetches_200": opened,
            "context_tokens_per_session": {
                "WebSearch+WebFetch": round(base_tokens / sessions),
                "search+read": round(ours_tokens / sessions),
            },
            "reader_usd_per_session_avoided": round(
                (len(mine) * per_search + opened * per_fetch) / sessions, 4
            ),
        }
    return out


# --- 6. guessed addresses -------------------------------------------------------------------------

CONFIRM = fo.CACHE / "frames-fetch-confirm" / "sessions.jsonl"
SEARCH_TOOLS = frozenset({"WebSearch", "mcp__sanchopanza-knowledge__search"})
_MISS = ("HTTP 404", "Note: a disambiguation page")


def _events(row: Mapping[str, Any]) -> tuple[list[tuple[str, str, str, int]], int]:
    """(timestamp, tool, result text, API calls before it) for every page call and search of a
    session, in time order, and the session's API call count."""
    uses, results, messages = {}, {}, {}
    for path in sorted(trace.folder_of(row["workdir"]).rglob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            entry = json.loads(raw) if raw.strip() else {}
            message = entry.get("message") or {}
            stamp = str(entry.get("timestamp") or "")
            if entry.get("type") == "assistant" and message.get("id"):
                messages.setdefault(message["id"], stamp)
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    uses[str(block["id"])] = (stamp, str(block.get("name")))
                elif block.get("type") == "tool_result":
                    results[str(block.get("tool_use_id"))] = fo._unwrap(
                        trace._result_text(block.get("content"))
                    )
    stamps = sorted(messages.values())
    wanted = SEARCH_TOOLS | {fo.PASSAGES_TOOL}
    out = [(stamp, name, results.get(i, ""), sum(t <= stamp for t in stamps))
           for i, (stamp, name) in uses.items() if name in wanted]  # fmt: skip
    return sorted(out), len(stamps)


def guess_replay(events: Sequence[tuple[str, str, str, int]], limit: int) -> dict[str, Any]:
    misses, fires, first = 0, 0, None
    for k, (_stamp, name, text, _api) in enumerate(events):
        if name in SEARCH_TOOLS:
            misses = 0
            continue
        if misses >= limit:
            fires, misses = fires + 1, 0
            first = k if first is None else first
            continue
        misses = misses + 1 if any(m in text for m in _MISS) else 0
    return {"fires": fires, "first": first}


def guess_report() -> dict[str, Any]:
    from sanchopanza.harness.knowledge_tool import GUESS_LIMIT

    rows = [json.loads(x) for x in CONFIRM.read_text(encoding="utf-8").splitlines() if x.strip()]
    out: dict[str, Any] = {"limit": GUESS_LIMIT}
    for arm in ("HAIKU-FETCH2", "SONNET-FETCH2"):
        mine = [r for r in rows if r["arm"] == arm]
        fired, pages_after, misses_after, usd_after, page_calls, missed = [], 0, 0, 0.0, 0, 0
        for row in mine:
            events, _calls = _events(row)
            pages = [e for e in events if e[1] == fo.PASSAGES_TOOL]
            page_calls += len(pages)
            missed += sum(any(m in e[2] for m in _MISS) for e in pages)
            got = guess_replay(events, GUESS_LIMIT)
            if got["first"] is None:
                continue
            after = [e for e in events[got["first"] :] if e[1] == fo.PASSAGES_TOOL]
            api = events[got["first"]][3]
            trajectory = row.get("trajectory") or [row["list_usd"]]
            spent_before = trajectory[min(api, len(trajectory)) - 1] if api else 0.0
            fired.append({"fires": got["fires"], "page_calls_after": len(after),
                          "usd_after": row["list_usd"] - spent_before})  # fmt: skip
            pages_after += len(after)
            misses_after += sum(any(m in e[2] for m in _MISS) for e in after)
            usd_after += row["list_usd"] - spent_before
        total = sum(r["list_usd"] for r in mine)
        out[arm] = {
            "sessions": len(mine),
            "page_calls": page_calls,
            "page_calls_missed": missed,
            "sessions_where_it_fires": len(fired),
            "fires": sum(f["fires"] for f in fired),
            "page_calls_after_first_fire": pages_after,
            "misses_after_first_fire": misses_after,
            "usd_after_first_fire": round(usd_after, 3),
            "arm_usd": round(total, 3),
            "most_saved_share_of_arm": round(usd_after / total, 3) if total else 0,
            "per_session": sorted(
                (
                    {k: round(v, 3) if isinstance(v, float) else v for k, v in f.items()}
                    for f in fired
                ),
                key=lambda f: -f["usd_after"],
            ),  # fmt: skip
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parts = ("search", "read", "longdocs", "pick", "sessions", "guess")
    parser.add_argument("part", choices=parts)
    parser.add_argument("--live-sample", type=int, default=0)
    parser.add_argument("--qasper", default=str(pathlib.Path.home() / ".cache" / "sancho" /
                                                "qasper-test.jsonl"))  # fmt: skip
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.part == "search":
        report = search_report(args.live_sample)
    elif args.part == "read":
        report = read_report()
    elif args.part == "pick":
        report = pick_report()
    elif args.part == "sessions":
        report = sessions_report()
    elif args.part == "guess":
        report = guess_report()
    else:
        report = longdocs_report(pathlib.Path(args.qasper))
    target = RESULTS / f"{args.part}.json"
    target.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
