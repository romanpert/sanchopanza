"""`fetch_passages`: a web page's passages for a purpose, as an MCP tool. No model.

The substitute for WebFetch's reader (`sanchopanza.webpage` says why and what was measured).
The tool downloads the page itself (standard library, http and https only, public addresses
only, every redirect checked again), keeps it in memory for `CACHE_S` so another purpose on the
same page costs no second download, and returns the title, the URL, one line on how much was
shown, and the passages. A PDF or other binary page is not read: the reply says to WebFetch it
(the `fetch_hook` lets a second WebFetch of a URL through).

The page text reaches the model that asked with no reader in between: what a page says to the
model arrives as it is. `install --scan-content` with this tool among the content tools scans it.

Environment: `SANCHOPANZA_FETCH_DENY_HOSTS` (comma-separated hosts; each also denies its
subdomains) for hosts the tool must never fetch, as WebFetch deny rules do for WebFetch.
`SANCHOPANZA_FETCH_VERSION=2` cuts pages with `webpage_v2` (chrome stripped, sections kept
together) and answers a 404 or a disambiguation page with one line saying to search first;
version 1 is the default and stays as measured.

    sanchopanza fetch-mcp                      # stdio server `sanchopanza-fetch`
    claude mcp add --scope user sanchopanza-fetch -- sanchopanza fetch-mcp
"""

from __future__ import annotations

import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .. import _env, webpage, webpage_v2

SERVER = "sanchopanza-fetch"
TOOL = "fetch_passages"
DESCRIPTION = (
    "Fetch a web page and return only the passages relevant to purpose (title, section headings, "
    "matching chunks; no summary). Use instead of WebFetch. Ask again with another purpose for "
    "other passages; budget is in characters."
)
MIN_BUDGET = 1_000
MAX_BUDGET = 40_000
MAX_BYTES = 6_000_000
TIMEOUT_S = 20
CACHE_S = 900
CACHE_PAGES = 64
USER_AGENT = (
    "Mozilla/5.0 (compatible; sanchopanza-fetch/0.3; +https://github.com/romanpert/sanchopanza)"
)
_TEXT_TYPES = ("text/plain", "application/json", "text/csv", "application/xml", "text/xml")
GUESSED = "The address may be a guess: search for the page first."
DISAMBIGUATION = (
    "Note: a disambiguation page (the name has several meanings). Fetch the exact title below, "
    "or search first."
)


class Refused(ValueError):
    """The URL is not one the tool fetches."""


@dataclass(frozen=True)
class Response:
    url: str
    content_type: str
    body: bytes


def _denied_hosts(env: Mapping[str, str] | None) -> tuple[str, ...]:
    raw = _env.get("FETCH_DENY_HOSTS", "", env)
    return tuple(h.strip().lower().strip(".") for h in raw.split(",") if h.strip())


def _public(ip: str) -> bool:
    address = ipaddress.ip_address(ip.split("%", 1)[0])
    mapped = getattr(address, "ipv4_mapped", None)
    address = mapped or address
    return address.is_global and not address.is_multicast


def check_url(url: str, env: Mapping[str, str] | None = None) -> None:
    """Raise `Refused` unless `url` is http(s), its host is not denied, and every address it
    resolves to is public (no loopback, private, link-local or metadata address)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Refused(f"only http and https URLs are fetched, not {url[:80]!r}")
    host = parts.hostname.lower().strip(".")
    if any(host == d or host.endswith("." + d) for d in _denied_hosts(env)):
        raise Refused(f"{host} is on SANCHOPANZA_FETCH_DENY_HOSTS")
    try:
        infos = socket.getaddrinfo(host, parts.port or None, proto=socket.IPPROTO_TCP)
    except OSError as error:
        raise Refused(f"{host} does not resolve ({error.__class__.__name__})") from error
    if not infos or not all(_public(str(info[4][0])) for info in infos):
        raise Refused(f"{host} resolves to an address that is not public")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, env: Mapping[str, str] | None) -> None:
        super().__init__()
        self.env = env

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        check_url(newurl, self.env)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_opener(
    env: Mapping[str, str] | None = None, max_bytes: int = MAX_BYTES
) -> Callable[[str], Response]:
    """The real download: checked URL, checked redirects, a size and a time limit."""
    opener = urllib.request.build_opener(_CheckedRedirects(env))

    def open_url(url: str) -> Response:
        check_url(url, env)
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,*/*;q=0.5"}
        )
        with opener.open(request, timeout=TIMEOUT_S) as reply:
            body = reply.read(max_bytes + 1)
            return Response(reply.geturl(), reply.headers.get("Content-Type", ""), body)

    return open_url


def version(env: Mapping[str, str] | None = None) -> int:
    return 2 if _env.get("FETCH_VERSION", "1", env).strip() == "2" else 1


def _page_of(response: Response, cut: int = 1) -> webpage.Page | str:
    """The page, or the reason it is not read."""
    ctype = (response.content_type or "").split(";")[0].strip().lower()
    head = response.body[:512].lstrip().lower()
    if ctype == "application/pdf" or head.startswith(b"%pdf"):
        return f"{response.url} is application/pdf: not read here. WebFetch this URL instead."
    text = webpage.decode(response.body[:MAX_BYTES], response.content_type)
    if "html" in ctype or head.startswith((b"<!doctype html", b"<html")):
        return (webpage_v2 if cut == 2 else webpage).page_from_html(text)
    if ctype.startswith("text/") or ctype in _TEXT_TYPES or ctype.endswith("+json"):
        return webpage.page_from_text(text)
    return f"{response.url} is {ctype or 'of unknown type'}: not read here. WebFetch it instead."


class PageFetcher:
    """Downloads once per URL (kept `CACHE_S`), then cuts the page for each purpose asked."""

    def __init__(
        self,
        opener: Callable[[str], Response] | None = None,
        env: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        parse: Callable[[Response], webpage.Page | str] | None = None,
    ) -> None:
        self.env = env
        self.version = version(env)
        self.opener = opener or http_opener(env)
        self.clock = clock
        self.parse = parse or (lambda response: _page_of(response, self.version))
        self.pages: dict[str, tuple[float, str, webpage.Page | str]] = {}

    def _get(self, url: str) -> tuple[str, webpage.Page | str]:
        now = self.clock()
        kept = self.pages.get(url)
        if kept and now - kept[0] < CACHE_S:
            return kept[1], kept[2]
        response = self.opener(url)
        page = self.parse(response)
        fresh = {u: v for u, v in self.pages.items() if now - v[0] < CACHE_S}
        if len(fresh) >= CACHE_PAGES:
            oldest = min(fresh, key=lambda u: fresh[u][0])
            fresh = {u: v for u, v in fresh.items() if u != oldest}
        self.pages = {**fresh, url: (now, response.url, page)}
        return response.url, page

    def load(self, url: str, *, guessed: bool | None = None) -> tuple[str, webpage.Page | str]:
        """(final URL, page), or (url, the reason it was not read) on a refusal or a failure.
        `guessed` adds the 404 line (default: version 2)."""
        guessed = self.version == 2 if guessed is None else guessed
        try:
            check_url(url, self.env)
            return self._get(url)
        except Refused as error:
            return url, f"Refused: {error}."
        except urllib.error.HTTPError as error:
            note = f" {GUESSED}" if guessed and error.code == 404 else ""
            return url, f"Could not fetch {url}: HTTP {error.code}.{note}"
        except (OSError, ValueError) as error:
            return url, f"Could not fetch {url}: {error.__class__.__name__}."

    def fetch(self, url: str, purpose: str, budget: int = webpage.DEFAULT_BUDGET) -> str:
        budget = max(MIN_BUDGET, min(MAX_BUDGET, int(budget or webpage.DEFAULT_BUDGET)))
        final, page = self.load(url)
        if isinstance(page, str):
            return page
        named = f"{page.title}\n{final}" if page.title else final
        if not page.chunks:
            return f"{named}\nNo text on the page (it may need a browser)."
        if self.version == 2:
            out = webpage_v2.passages(page, purpose, budget)
            note = f"{DISAMBIGUATION}\n" if page.disambiguation else ""
            return f"{named}\n{note}{out.header()}\n\n{out.text}"
        out = webpage.passages(page, purpose, budget)
        return f"{named}\n{out.header()}\n\n{out.text}"


def add_fetch(server: Any, fetcher: PageFetcher | None = None) -> Any:
    """Register `fetch_passages` on an MCP server."""
    tool = fetcher or PageFetcher()

    @server.tool(name=TOOL, description=DESCRIPTION)
    def fetch_passages(url: str, purpose: str, budget: int = webpage.DEFAULT_BUDGET) -> str:
        return tool.fetch(url, purpose, budget)

    return server


def main(argv: list[str] | None = None) -> int:
    """`sanchopanza fetch-mcp`: a stdio server with the one tool."""
    del argv
    from .mcp import _server

    add_fetch(_server(SERVER)).run()
    return 0
