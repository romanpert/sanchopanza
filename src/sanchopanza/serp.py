"""A compact results page from free backends: code only, no model, no reader.

Claude Code's WebSearch bills a fixed 0.010 USD and a Haiku reader per call; on the FRAMES pilots
it was 36 % of a Sonnet session's spend and 73 % of a Haiku session's
(docs/results/2026-10-05-browse-frames/). Replaying the pilots' own 193 queries
(docs/results/2026-10-05-knowledge/), Wikipedia's search API put a task's gold article in its top
ten 58-60 % of the time against 44-48 % for WebSearch, and its union with a web chain 70-75 %.
This module is that union, made to be called by an agent:

- `Wikipedia`: the search API, one call a second, `Retry-After` honoured when short (else the
  backend is down until then); when the full query finds nothing, its content words OR-joined.
- The web chain, in order, the first that answers with results wins: `Ddgs("bing")`,
  `Ddgs("yahoo")` (the optional `sanchopanza[search]` extra), `SearXNG` at
  `SANCHOPANZA_SEARCH_SEARXNG_URL` or a local `http://127.0.0.1:8888` if one runs there.
- `merge` takes from each list in turn and drops a URL already given (`normalize_url`).
- `Searcher.search` caches a day by the normalised query (on disk, across sessions), says
  "already searched" when a session repeats a query, and gives every backend a circuit breaker
  that only real answers move: two failures in a row pause it `BREAKER_COOLDOWN_S`, a backend
  that is not there (not installed, connection refused) is paused `ABSENT_COOLDOWN_S`, and the
  first call after a pause is the probe. Nothing is decided by a flag that says a service exists.
- After each live search the chain's state is written (`chain.json`): `ok` when any backend
  answered. The WebSearch hook (`harness.knowledge_hook`) lets WebSearch run when the last real
  answer said the chain is down (`chain_down`).
"""

from __future__ import annotations

import contextlib
import hashlib
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from . import _env
from .text import STOPWORDS

DEFAULT_K = 8
MAX_K = 10
PER_BACKEND = 10
SNIPPET_MAX = 160
CACHE_TTL_S = 86_400
BREAKER_FAILS = 2
BREAKER_COOLDOWN_S = 600
ABSENT_COOLDOWN_S = 3_600
DOWN_FOR_S = 600  # how long a "down" state is believed by the hook
RETRY_WAIT_MAX_S = 5.0
WIKI_INTERVAL_S = 1.0
WEB_INTERVAL_S = 1.0
TIMEOUT_S = 12
SEARXNG_LOCAL = "http://127.0.0.1:8888"
USER_AGENT = "sanchopanza-knowledge/0.3 (https://github.com/romanpert/sanchopanza; agent search)"
ALREADY = "Already searched this session"
DOWN = "Search is down right now"
_TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|ref_src)$", re.IGNORECASE)
_ENGLISH_STOP = "the of an in at do how who to is and or for on by with from what which when where"
_STOP = STOPWORDS | frozenset(_ENGLISH_STOP.split())


class BackendDown(RuntimeError):
    """A backend failed this call; `retry_after` seconds when it said how long to wait."""

    def __init__(self, reason: str, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.retry_after = retry_after


class Unavailable(RuntimeError):
    """A backend that is not there at all: not installed, nothing listening."""


@dataclass(frozen=True)
class Hit:
    title: str
    url: str
    snippet: str
    source: str


class Backend(Protocol):
    name: str
    group: str

    def __call__(self, query: str, k: int) -> list[Hit]: ...


# --- normalising and rendering -------------------------------------------------------------------


def normalize_query(query: str) -> str:
    text = re.sub(r"[\"“”«»]", " ", (query or "").casefold())
    return re.sub(r"\s+", " ", text).strip().strip(" ?!.,;:'")


def normalize_url(url: str) -> str:
    """One key per page: no scheme, no `www.`, Wikipedia's mobile host folded, no fragment, no
    tracking parameters, no trailing slash, the path unquoted."""
    parts = urllib.parse.urlsplit((url or "").strip())
    host = (
        (parts.hostname or "").lower().removeprefix("www.").replace(".m.wikipedia.", ".wikipedia.")
    )
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if not _TRACKING.match(k)]
    )
    path = urllib.parse.unquote(parts.path).rstrip("/")
    return f"{host}{path}" + (f"?{query}" if query else "")


def merge(groups: Sequence[Sequence[Hit]], k: int) -> list[Hit]:
    """Each list in turn gives its next hit not given yet, until `k`."""
    seen: set[str] = set()
    out: list[Hit] = []
    iterators: list[Iterator[Hit]] = [iter(g) for g in groups]
    while iterators and len(out) < k:
        alive: list[Iterator[Hit]] = []
        for it in iterators:
            for hit in it:
                key = normalize_url(hit.url)
                if key and key not in seen:
                    seen.add(key)
                    out.append(hit)
                    alive.append(it)
                    break
            if len(out) >= k:
                break
        iterators = alive
    return out


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def cut(text: str, limit: int = SNIPPET_MAX) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    head = text[: limit - 3]
    return (head.rsplit(" ", 1)[0] if " " in head else head) + "..."


def render(query: str, hits: Sequence[Hit]) -> str:
    lines = [f"{len(hits)} results for: {query}"]
    for i, hit in enumerate(hits, start=1):
        lines.append(f"{i}. {clean(hit.title) or hit.url} - {hit.url}")
        snippet = cut(hit.snippet)
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


# --- backends ------------------------------------------------------------------------------------


def http_get(url: str, timeout: float = TIMEOUT_S) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})  # fmt: skip
    with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310 - fixed hosts
        return reply.read(4_000_000)


class Pacer:
    """At most one call per `interval` seconds, across threads."""

    def __init__(self, interval: float, clock: Callable[[], float], sleep: Callable[[float], None]):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.last: float | None = None
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = self.clock()
            if self.last is not None and now < self.last + self.interval:
                self.sleep(self.last + self.interval - now)
            self.last = self.clock()


def _retry_after(error: urllib.error.HTTPError) -> float:
    raw = (error.headers.get("Retry-After") if error.headers else None) or ""
    try:
        return max(0.0, float(raw))
    except ValueError:
        return RETRY_WAIT_MAX_S


class Wikipedia:
    name = "wikipedia"
    group = "wiki"

    def __init__(
        self,
        lang: str = "en",
        http: Callable[[str], bytes] = http_get,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.lang, self.http, self.sleep = lang, http, sleep
        self.pacer = Pacer(WIKI_INTERVAL_S, clock, sleep)

    def _call(self, srsearch: str, k: int) -> list[dict[str, Any]]:
        url = f"https://{self.lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": srsearch, "srlimit": k,
             "format": "json"})  # fmt: skip
        for attempt in range(2):
            self.pacer.wait()
            try:
                return list(json.loads(self.http(url)).get("query", {}).get("search", []))
            except urllib.error.HTTPError as error:
                if error.code not in (429, 503):
                    raise BackendDown(f"HTTP {error.code}") from error
                wait = _retry_after(error)
                if attempt or wait > RETRY_WAIT_MAX_S:
                    raise BackendDown(f"HTTP {error.code}", retry_after=wait) from error
                self.sleep(wait)
        return []

    def __call__(self, query: str, k: int) -> list[Hit]:
        found = self._call(query, k)
        if not found:
            words = [w for w in re.findall(r"\w+", query) if w.lower() not in _STOP and len(w) > 2]
            if len(words) > 1:
                found = self._call(" OR ".join(words[:12]), k)
        base = f"https://{self.lang}.wikipedia.org/wiki/"
        return [
            Hit(
                str(h.get("title", "")),
                base
                + urllib.parse.quote(str(h.get("title", "")).replace(" ", "_"), safe="_(),'!-.~:/"),
                clean(str(h.get("snippet", ""))),
                self.name,
            )  # fmt: skip
            for h in found
            if h.get("title")
        ]


def _ddgs() -> Any:
    try:
        import ddgs
        import ddgs.exceptions  # noqa: F401 - makes `ddgs.exceptions` an attribute
    except ImportError:
        return None
    return ddgs


class Ddgs:
    """One engine through the `ddgs` package (scraped results pages, no key)."""

    group = "web"

    def __init__(
        self,
        engine: str,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = self.engine = engine
        self.pacer = Pacer(WEB_INTERVAL_S, clock, sleep)

    def __call__(self, query: str, k: int) -> list[Hit]:
        module = _ddgs()
        if module is None:
            raise Unavailable("ddgs is not installed: pip install sanchopanza[search]")
        self.pacer.wait()
        try:
            rows = module.DDGS(timeout=TIMEOUT_S).text(query, max_results=k, backend=self.engine)
        except module.exceptions.DDGSException as error:
            if "no results" in str(error).lower():
                return []
            raise BackendDown(str(error)[:80]) from error
        return [Hit(str(r.get("title", "")), str(r.get("href", "")), str(r.get("body", "")),
                    self.name) for r in rows or [] if r.get("href")]  # fmt: skip


class SearXNG:
    name = "searxng"
    group = "web"

    def __init__(self, url: str, http: Callable[[str], bytes] = http_get) -> None:
        self.url, self.http = url.rstrip("/"), http

    def __call__(self, query: str, k: int) -> list[Hit]:
        address = f"{self.url}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
        try:
            data = json.loads(self.http(address))
        except urllib.error.HTTPError as error:
            raise BackendDown(f"HTTP {error.code}") from error
        except (urllib.error.URLError, ConnectionError) as error:
            raise Unavailable(f"nothing answers at {self.url}") from error
        except ValueError as error:  # something else listens there
            raise Unavailable(f"{self.url} does not answer as SearXNG") from error
        results = list(data.get("results") or [])
        if not results and data.get("unresponsive_engines"):
            raise BackendDown("its engines did not answer")
        return [Hit(str(r.get("title", "")), str(r["url"]), str(r.get("content", "")), self.name)
                for r in results[:k] if r.get("url")]  # fmt: skip


# --- the searcher --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Breaker:
    fails: int = 0
    open_until: float = 0.0


def chain_down(path: Path, now: float | None = None) -> bool:
    """Whether the last real search found every backend down, within `DOWN_FOR_S`."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        at, ok = float(state["at"]), bool(state["ok"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    now = time.time() if now is None else now
    return not ok and now - at < DOWN_FOR_S


class Searcher:
    def __init__(
        self,
        wiki: Backend | None,
        web: Sequence[Backend],
        *,
        cache_dir: Path | None = None,
        state_path: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.wiki, self.web = wiki, list(web)
        self.cache_dir, self.state_path, self.clock = cache_dir, state_path, clock
        self.breakers: dict[str, Breaker] = {}
        self.seen: dict[str, list[Hit]] = {}
        self.lock = threading.Lock()

    # breakers
    def _allowed(self, name: str) -> bool:
        return self.breakers.get(name, Breaker()).open_until <= self.clock()

    def _record(self, name: str, error: Exception | None) -> None:
        with self.lock:
            now, old = self.clock(), self.breakers.get(name, Breaker())
            if error is None:
                self.breakers = {**self.breakers, name: Breaker()}
                return
            fails = old.fails + 1
            if isinstance(error, Unavailable):
                until = now + ABSENT_COOLDOWN_S
            elif isinstance(error, BackendDown) and error.retry_after:
                until = now + error.retry_after
            else:
                until = now + BREAKER_COOLDOWN_S if fails >= BREAKER_FAILS else 0.0
            self.breakers = {**self.breakers, name: Breaker(fails, until)}

    def _ask(self, backend: Backend, query: str) -> tuple[list[Hit] | None, str]:
        if not self._allowed(backend.name):
            return None, f"{backend.name}: paused"
        try:
            hits = backend(query, PER_BACKEND)
        except Exception as error:  # noqa: BLE001 - a backend's failure is a breaker's business
            self._record(backend.name, error)
            return None, f"{backend.name}: {str(error)[:60] or error.__class__.__name__}"
        self._record(backend.name, None)
        return hits, ""

    def _chain(self, backends: Sequence[Backend], query: str) -> tuple[list[Hit], bool, list[str]]:
        answered, errors = False, []
        for backend in backends:
            hits, error = self._ask(backend, query)
            if hits is None:
                errors.append(error)
                continue
            answered = True
            if hits:
                return hits, True, errors
        return [], answered, errors

    def _live(self, query: str) -> tuple[list[Hit], bool, list[str]]:
        chains = [[self.wiki]] if self.wiki is not None else []
        chains.append(self.web)
        with ThreadPoolExecutor(max_workers=len(chains)) as pool:
            done = list(pool.map(lambda chain: self._chain(chain, query), chains))
        hits = merge([d[0] for d in done], PER_BACKEND * 2)
        return hits, any(d[1] for d in done), [e for d in done for e in d[2]]

    # cache and state
    def _cache_path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}.json"

    def _cached(self, key: str) -> list[Hit] | None:
        path = self._cache_path(key)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path else None
        except (OSError, ValueError):
            return None
        if not isinstance(data, Mapping) or self.clock() - float(data.get("at", 0)) > CACHE_TTL_S:
            return None
        return [Hit(*row) for row in data.get("hits", []) if len(row) == 4]

    def _store(self, key: str, hits: Sequence[Hit]) -> None:
        path = self._cache_path(key)
        if path is None or not hits:
            return
        rows = [[h.title, h.url, h.snippet, h.source] for h in hits]
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"at": self.clock(), "query": key, "hits": rows}), "utf-8")

    def _state(self, ok: bool, errors: Sequence[str]) -> None:
        if self.state_path is None:
            return
        with contextlib.suppress(OSError):
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {"ok": ok, "at": self.clock(), "errors": list(errors)[:6]}
            self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def search(self, query: str, k: int = DEFAULT_K) -> str:
        k = max(1, min(MAX_K, int(k or DEFAULT_K)))
        key = normalize_query(query)
        if not key:
            return "Empty query: say what to search for."
        if key in self.seen:
            urls = "\n".join(h.url for h in self.seen[key])
            return (f"{ALREADY}: the same {len(self.seen[key])} results as before. Search with "
                    f"other words, or read one of them:\n{urls}")  # fmt: skip
        hits = self._cached(key)
        if hits is None:
            hits, ok, errors = self._live(query)
            self._state(ok, errors)
            if not ok:
                return (
                    f"{DOWN} ({'; '.join(errors) or 'no backend'}). Use WebSearch for this query."
                )
            self._store(key, hits)
        self.seen = {**self.seen, key: hits[:k]}
        return render(query, hits[:k])


def state_dir(env: Mapping[str, str] | None = None) -> Path:
    override = _env.get("KNOWLEDGE_DIR", "", env).strip()
    return Path(override) if override else _env.home_dir() / "knowledge"


def chain_path(env: Mapping[str, str] | None = None) -> Path:
    return state_dir(env) / "chain.json"


def default_searcher(env: Mapping[str, str] | None = None) -> Searcher:
    """Wikipedia (`SANCHOPANZA_SEARCH_WIKI_LANG`, default en) and the web chain."""
    lang = _env.get("SEARCH_WIKI_LANG", "en", env).strip() or "en"
    searxng = _env.get("SEARCH_SEARXNG_URL", "", env).strip() or SEARXNG_LOCAL
    web: list[Backend] = [Ddgs("bing"), Ddgs("yahoo"), SearXNG(searxng)]
    return Searcher(Wikipedia(lang), web, cache_dir=state_dir(env) / "search",
                    state_path=chain_path(env))  # fmt: skip
