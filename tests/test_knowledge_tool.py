"""`sanchopanza knowledge-mcp`: search, read and pick as one MCP server.

`read` is fetch v2 for a URL and also opens local files (PDF, DOCX, XLSX, CSV, text, HTML) under
the server's roots; `pick` chooses among many documents (a folder, files, URLs); `search` is
`serp.Searcher`. No network and no model here."""

from __future__ import annotations

import asyncio
import socket
import urllib.error
from pathlib import Path

import pytest

from sanchopanza.harness import fetch_tool, knowledge_tool

PAGE = (
    b"<html><head><title>Lake Example</title></head><body><h1>Lake Example</h1>"
    b"<p>Lake Example is a lake in the hills.</p><h2>History</h2>"
    b"<p>The first survey of the lake was carried out in 1873.</p></body></html>"
)


class Opener:
    def __init__(self, pages: dict[str, tuple[str, bytes]]) -> None:
        self.pages, self.calls = pages, []

    def __call__(self, url: str) -> fetch_tool.Response:
        self.calls.append(url)
        if url not in self.pages:
            raise urllib.error.URLError("unreachable")
        ctype, body = self.pages[url]
        return fetch_tool.Response(url, ctype, body)


class Searcher:
    def __init__(self) -> None:
        self.asked: list[tuple[str, int]] = []

    def search(self, query: str, k: int = 8) -> str:
        self.asked.append((query, k))
        return f"results for {query}"


@pytest.fixture(autouse=True)
def _public(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(fetch_tool.socket, "getaddrinfo", fake)


def _tool(tmp_path: Path, pages: dict | None = None, **kwargs) -> knowledge_tool.Knowledge:
    opener = Opener(pages or {"https://lake.example/": ("text/html", PAGE)})
    fetcher = knowledge_tool.page_fetcher(opener=opener)
    return knowledge_tool.Knowledge(fetcher=fetcher, searcher=Searcher(), squire=None,
                                    roots=[tmp_path], **kwargs)  # fmt: skip


def _run(coro):
    return asyncio.run(coro)


def test_read_a_url_gives_title_url_and_passages(tmp_path: Path) -> None:
    out = _run(_tool(tmp_path).read("https://lake.example/", "first survey year"))
    lines = out.splitlines()
    assert lines[0] == "Lake Example" and lines[1] == "https://lake.example/"
    assert "1873" in out


def test_read_a_local_csv_under_the_roots(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "people.csv").write_text("name,city\nAna,Vigo\nLuis,Lugo\n", "utf-8")
    out = _run(_tool(tmp_path).read(str(tmp_path / "data" / "people.csv"), "where does Luis live"))
    assert "Luis | Lugo" in out and "people.csv" in out.splitlines()[0]


def test_a_relative_path_is_read_from_the_first_root(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# Notes\n\nThe key is under the mat.\n", "utf-8")
    out = _run(_tool(tmp_path).read("notes.md", "where is the key"))
    assert "under the mat" in out


@pytest.mark.parametrize("name", ["outside", "hidden"])
def test_paths_outside_the_roots_or_hidden_are_refused(tmp_path: Path, name: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    if name == "outside":
        target = tmp_path / "secret.txt"
    else:
        (root / ".env").mkdir()
        target = root / ".env" / "keys.txt"
    target.write_text("token", "utf-8")
    tool = knowledge_tool.Knowledge(fetcher=knowledge_tool.page_fetcher(opener=Opener({})),
                                    searcher=Searcher(), squire=None, roots=[root])  # fmt: skip
    out = _run(tool.read(str(target), "token"))
    assert out.startswith("Refused") and "token\n" not in out


def test_a_missing_file_says_so(tmp_path: Path) -> None:
    out = _run(_tool(tmp_path).read(str(tmp_path / "nope.pdf"), "x"))
    assert out.startswith("No such file")


def test_read_a_pdf_url_through_the_documents_module(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    from tests.test_documents import _pdf

    pages = {"https://x.example/r.pdf": ("application/pdf", _pdf(["Water use fell by 9 percent."]))}
    out = _run(_tool(tmp_path, pages).read("https://x.example/r.pdf", "water use"))
    assert "## p. 1" in out and "9 percent" in out


def test_pick_over_a_folder_chooses_the_matching_file(tmp_path: Path) -> None:
    folder = tmp_path / "kb"
    (folder / "sub").mkdir(parents=True)
    (folder / "roads.txt").write_text("The road budget rose by ten percent.", "utf-8")
    (folder / "sub" / "water.md").write_text("# Water\n\nThe reservoir holds 4,200 hm3.", "utf-8")
    (folder / "image.png").write_bytes(b"\x89PNG")
    (folder / ".hidden.txt").write_text("reservoir reservoir reservoir", "utf-8")
    out = _run(_tool(tmp_path).pick("reservoir capacity", [str(folder)]))
    assert out.splitlines()[0].startswith("Picked 1 of 2 documents")
    assert "4,200 hm3" in out and ".hidden" not in out


def test_pick_mixes_urls_and_files_and_counts_what_could_not_be_read(tmp_path: Path) -> None:
    (tmp_path / "survey.txt").write_text("No survey was done in the valley.", "utf-8")
    tool = _tool(tmp_path)
    out = _run(tool.pick("lake survey year", ["https://lake.example/", "survey.txt",
                                              "https://gone.example/x"]))  # fmt: skip
    assert "1873" in out and "1 could not be read" in out


def test_search_goes_to_the_searcher(tmp_path: Path) -> None:
    tool = _tool(tmp_path)
    assert tool.search("lake", 5) == "results for lake"
    assert tool.searcher.asked == [("lake", 5)]


class Server:
    def __init__(self) -> None:
        self.tools: dict[str, tuple[str, object]] = {}

    def tool(self, name: str | None = None, description: str | None = None):
        def register(fn):
            self.tools[name or fn.__name__] = (description or "", fn)
            return fn

        return register


def test_the_server_offers_three_tools_with_short_descriptions(tmp_path: Path) -> None:
    server = knowledge_tool.add_knowledge(Server(), _tool(tmp_path))
    assert set(server.tools) == {"search", "read", "pick"}
    assert all(len(d) < 300 for d, _fn in server.tools.values())


def test_the_registered_read_and_pick_run(tmp_path: Path) -> None:
    server = knowledge_tool.add_knowledge(Server(), _tool(tmp_path))
    read = server.tools["read"][1]
    out = _run(read(url_or_path="https://lake.example/", purpose="survey"))
    assert "1873" in out
