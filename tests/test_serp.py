"""`sanchopanza.serp`: a compact results page from free backends, without a reader model.

Wikipedia's search API and a web chain (ddgs Bing, then Yahoo, then a local SearXNG), merged
without repeated URLs; cached a day by the normalised query; a repeat in the same session says
so; each backend paced and behind a circuit breaker that only real answers open and close; the
chain's last real state written for the WebSearch hook. No network here."""

from __future__ import annotations

import json
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from sanchopanza import serp


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class Fake:
    def __init__(self, name: str, hits=None, error: Exception | None = None, group: str = "web"):
        self.name, self.group, self.hits, self.error, self.calls = name, group, hits, error, []

    def __call__(self, query: str, k: int) -> list[serp.Hit]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return list(self.hits or [])[:k]


def _hits(source: str, *urls: str) -> list[serp.Hit]:
    return [serp.Hit(f"T {u}", u, f"snippet of {u}", source) for u in urls]


def _searcher(tmp_path: Path, wiki, web, clock: Clock | None = None) -> serp.Searcher:
    clock = clock or Clock()
    return serp.Searcher(wiki, web, cache_dir=tmp_path / "cache",
                         state_path=tmp_path / "chain.json", clock=clock)  # fmt: skip


# --- normalising -------------------------------------------------------------------------------


def test_queries_normalise_case_space_and_outer_punctuation() -> None:
    assert serp.normalize_query('  "Lake  Example"  history? ') == "lake example history"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://en.wikipedia.org/wiki/Lake", "http://en.wikipedia.org/wiki/Lake#History"),
        ("https://www.example.com/a/", "https://example.com/a"),
        ("https://example.com/a?utm_source=x&id=3", "https://example.com/a?id=3"),
        ("https://en.m.wikipedia.org/wiki/Lake", "https://en.wikipedia.org/wiki/Lake"),
    ],
)
def test_urls_normalise_to_one_key(a: str, b: str) -> None:
    assert serp.normalize_url(a) == serp.normalize_url(b)


def test_merge_alternates_groups_and_drops_repeated_urls() -> None:
    wiki = _hits("wikipedia", "https://en.wikipedia.org/wiki/A", "https://en.wikipedia.org/wiki/B")
    web = _hits("bing", "https://en.wikipedia.org/wiki/A#x", "https://site.org/c", "https://d.org")
    merged = serp.merge([wiki, web], 4)
    assert [h.url for h in merged] == [
        "https://en.wikipedia.org/wiki/A",
        "https://site.org/c",
        "https://en.wikipedia.org/wiki/B",
        "https://d.org",
    ]


def test_render_is_compact_and_cuts_snippets() -> None:
    hit = serp.Hit("Title", "https://a.org", "word " * 100, "bing")
    out = serp.render("q", [hit])
    line = [x for x in out.splitlines() if x.strip().startswith("word")][0]
    assert len(line.strip()) <= serp.SNIPPET_MAX
    assert "1. Title - https://a.org" in out


# --- the searcher ------------------------------------------------------------------------------


def test_search_merges_wikipedia_and_the_first_web_backend_with_results(tmp_path: Path) -> None:
    wiki = Fake("wikipedia", _hits("wikipedia", "https://en.wikipedia.org/wiki/A"), group="wiki")
    bing = Fake("bing", [])  # answered, nothing found: not a failure, the next one is asked
    yahoo = Fake("yahoo", _hits("yahoo", "https://y.org"))
    out = _searcher(tmp_path, wiki, [bing, yahoo]).search("lake", 8)
    assert "https://en.wikipedia.org/wiki/A" in out and "https://y.org" in out
    assert bing.calls == ["lake"] and yahoo.calls == ["lake"]
    state = json.loads((tmp_path / "chain.json").read_text("utf-8"))
    assert state["ok"] is True


def test_the_web_chain_stops_at_the_first_backend_with_results(tmp_path: Path) -> None:
    bing = Fake("bing", _hits("bing", "https://b.org"))
    yahoo = Fake("yahoo", _hits("yahoo", "https://y.org"))
    _searcher(tmp_path, None, [bing, yahoo]).search("lake", 8)
    assert yahoo.calls == []


def test_a_day_of_cache_by_normalised_query(tmp_path: Path) -> None:
    clock = Clock()
    bing = Fake("bing", _hits("bing", "https://b.org"))
    first = _searcher(tmp_path, None, [bing], clock)
    first.search("Lake history", 8)
    second = _searcher(tmp_path, None, [bing], clock)  # a new session, the same disk cache
    out = second.search("lake  HISTORY", 8)
    assert "https://b.org" in out and len(bing.calls) == 1
    clock.now += serp.CACHE_TTL_S + 1
    _searcher(tmp_path, None, [bing], clock).search("lake history", 8)
    assert len(bing.calls) == 2


def test_an_empty_answer_is_not_cached(tmp_path: Path) -> None:
    bing = Fake("bing", [])
    _searcher(tmp_path, None, [bing]).search("nothing", 8)
    _searcher(tmp_path, None, [bing]).search("nothing", 8)
    assert len(bing.calls) == 2


def test_a_repeat_in_the_session_says_already_searched(tmp_path: Path) -> None:
    bing = Fake("bing", _hits("bing", "https://b.org"))
    searcher = _searcher(tmp_path, None, [bing])
    searcher.search("lake", 8)
    again = searcher.search("Lake?", 8)
    assert again.startswith(serp.ALREADY)
    assert "https://b.org" in again and "snippet" not in again
    assert len(bing.calls) == 1


def test_two_failures_open_the_breaker_until_the_cooldown_then_one_probe(tmp_path: Path) -> None:
    clock = Clock()
    bing = Fake("bing", error=RuntimeError("blocked"))
    yahoo = Fake("yahoo", _hits("yahoo", "https://y.org"))
    searcher = _searcher(tmp_path, None, [bing, yahoo], clock)
    searcher.search("a", 8)
    searcher.search("b", 8)
    searcher.search("c", 8)
    assert bing.calls == ["a", "b"]  # open after two failures: skipped on the third
    clock.now += serp.BREAKER_COOLDOWN_S + 1
    bing.error, bing.hits = None, _hits("bing", "https://b.org")
    searcher.search("d", 8)
    assert bing.calls == ["a", "b", "d"]


def test_everything_down_says_so_and_marks_the_chain_down(tmp_path: Path) -> None:
    wiki = Fake("wikipedia", error=serp.BackendDown("HTTP 429"), group="wiki")
    bing = Fake("bing", error=RuntimeError("blocked"))
    out = _searcher(tmp_path, wiki, [bing]).search("lake", 8)
    assert out.startswith(serp.DOWN)
    assert json.loads((tmp_path / "chain.json").read_text("utf-8"))["ok"] is False


def test_a_cache_hit_does_not_touch_the_chain_state(tmp_path: Path) -> None:
    bing = Fake("bing", _hits("bing", "https://b.org"))
    _searcher(tmp_path, None, [bing]).search("lake", 8)
    (tmp_path / "chain.json").write_text(json.dumps({"ok": False, "at": 1}), "utf-8")
    _searcher(tmp_path, None, [bing]).search("lake", 8)
    assert json.loads((tmp_path / "chain.json").read_text("utf-8"))["ok"] is False


def test_chain_down_reads_the_last_real_state(tmp_path: Path) -> None:
    path = tmp_path / "chain.json"
    assert serp.chain_down(path, now=10.0) is False  # never searched: not known to be down
    path.write_text(json.dumps({"ok": False, "at": 5.0}), "utf-8")
    assert serp.chain_down(path, now=10.0) is True
    assert serp.chain_down(path, now=5.0 + serp.DOWN_FOR_S + 1) is False


# --- Wikipedia ---------------------------------------------------------------------------------


class Http:
    def __init__(self, replies) -> None:
        self.replies, self.urls = list(replies), []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply).encode()


def _wiki_reply(*titles: str) -> dict:
    return {"query": {"search": [{"title": t, "snippet": f'<span class="m">{t}</span> &amp; more'}
                                 for t in titles]}}  # fmt: skip


def _http_error(code: int, retry_after: str | None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://x", code, "err", headers, None)


def test_wikipedia_hits_are_clean_and_link_to_the_article() -> None:
    clock = Clock()
    wiki = serp.Wikipedia(http=Http([_wiki_reply("Lake Example")]), clock=clock, sleep=clock.sleep)
    hits = wiki("lake", 5)
    assert hits == [serp.Hit("Lake Example", "https://en.wikipedia.org/wiki/Lake_Example",
                             "Lake Example & more", "wikipedia")]  # fmt: skip


def test_wikipedia_falls_back_to_the_content_words_or_joined() -> None:
    clock = Clock()
    http = Http([_wiki_reply(), _wiki_reply("Danon The Kid")])
    hits = serp.Wikipedia(http=http, clock=clock, sleep=clock.sleep)("the debut of Danon Kid", 5)
    assert [h.title for h in hits] == ["Danon The Kid"]
    assert "OR" in http.urls[1]


def test_wikipedia_is_paced_to_one_call_a_second() -> None:
    clock = Clock()
    wiki = serp.Wikipedia(http=Http([_wiki_reply("A"), _wiki_reply("B")]), clock=clock,
                          sleep=clock.sleep)  # fmt: skip
    wiki("a", 5)
    clock.now += 0.25
    wiki("b", 5)
    assert clock.slept and abs(clock.slept[-1] - 0.75) < 1e-6


def test_wikipedia_waits_a_short_retry_after_and_retries_once() -> None:
    clock = Clock()
    http = Http([_http_error(429, "2"), _wiki_reply("A")])
    hits = serp.Wikipedia(http=http, clock=clock, sleep=clock.sleep)("a", 5)
    assert [h.title for h in hits] == ["A"] and 2.0 in clock.slept


def test_wikipedia_a_long_retry_after_is_a_down_backend() -> None:
    clock = Clock()
    wiki = serp.Wikipedia(http=Http([_http_error(429, "120")]), clock=clock, sleep=clock.sleep)
    with pytest.raises(serp.BackendDown):
        wiki("a", 5)
    assert not any(s >= 120 for s in clock.slept)


# --- ddgs and SearXNG --------------------------------------------------------------------------


def test_ddgs_missing_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serp, "_ddgs", lambda: None)
    with pytest.raises(serp.Unavailable, match="sanchopanza\\[search\\]"):
        serp.Ddgs("bing")("lake", 5)


def test_ddgs_no_results_is_an_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoResults(Exception):
        pass

    class Client:
        def __init__(self, **kwargs) -> None:
            pass

        def text(self, query, **kwargs):
            raise NoResults("No results found.")

    module = type(
        "M", (), {"DDGS": Client, "exceptions": type("E", (), {"DDGSException": NoResults})}
    )
    monkeypatch.setattr(serp, "_ddgs", lambda: module)
    assert serp.Ddgs("bing")("lake", 5) == []


def test_searxng_with_no_results_and_engines_down_is_a_failure() -> None:
    reply = {"results": [], "unresponsive_engines": [["bing", "CAPTCHA"]]}
    backend = serp.SearXNG("http://127.0.0.1:8888", http=lambda url: json.dumps(reply).encode())
    with pytest.raises(serp.BackendDown):
        backend("lake", 5)


def test_an_unavailable_backend_opens_its_breaker_for_long(tmp_path: Path) -> None:
    clock = Clock()
    gone = Fake("searxng", error=serp.Unavailable("connection refused"))
    searcher = _searcher(tmp_path, None, [gone], clock)
    searcher.search("a", 8)
    clock.now += serp.BREAKER_COOLDOWN_S + 1
    searcher.search("b", 8)
    assert gone.calls == ["a"]


def test_something_else_listening_is_not_a_searxng() -> None:
    backend = serp.SearXNG("http://127.0.0.1:8888", http=lambda url: b"<html>a notebook</html>")
    with pytest.raises(serp.Unavailable):
        backend("lake", 5)
