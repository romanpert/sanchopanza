"""Selecting a few among many: the shared BM25 index, the generic select, and repository search."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pytest

from sanchopanza.contract import Answer, Decision
from sanchopanza.text import BM25Index, bm25_scores

DOCS = [
    "The pager returns one page of items; page numbers are 1-based.",
    "Slugify lowercases the title and joins words with hyphens.",
    "Configuration defaults: timeout seconds and retries.",
    "",
    "El paginador devuelve una página de elementos.",
]


def test_the_index_scores_exactly_like_bm25_scores() -> None:
    index = BM25Index(DOCS)
    for query in ("page items pager", "slugify title", "timeout", "página", "nothing matches"):
        got, want = index.scores(query), bm25_scores(query, DOCS)
        assert all(
            math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(got, want, strict=True)
        )


def test_the_index_ranks_and_handles_empty_input() -> None:
    assert BM25Index([]).scores("x") == []
    assert BM25Index(DOCS).top("pager page", 2)[0][0] == 0


class _Keeper:
    """A decider stub for `triage_pages`: keeps the pages whose text holds `word`."""

    def __init__(self, word: str) -> None:
        self.word = word
        self.calls = 0

    async def decide(self, point, state, questions):  # noqa: ANN001, ANN201
        self.calls += 1
        answers = {}
        lines = state["pages"].splitlines()
        for key in questions:
            page = next((line for line in lines if line.startswith(f"{key}|")), "")
            keep = self.word in page
            answers[key] = Answer("truth", truth=0.9 if keep else 0.1, confidence=0.8)
        return Decision(point, answers, "stub", "stub-1")


def _candidates():  # noqa: ANN202
    from sanchopanza.select import Candidate

    return [Candidate(f"k{i}", f"doc {i}", text) for i, text in enumerate(DOCS) if text]


def test_select_without_a_decider_is_the_bm25_order() -> None:
    from sanchopanza.select import select

    picks = asyncio.run(select("pager page", _candidates(), keep=2))
    assert [p.candidate.key for p in picks] == ["k0", "k4"] or picks[0].candidate.key == "k0"
    assert all(p.p is None for p in picks)


def test_select_with_a_decider_keeps_what_it_judges_relevant() -> None:
    from sanchopanza import Squire
    from sanchopanza.select import select

    decider = _Keeper("Slugify")
    picks = asyncio.run(select("title", _candidates(), squire=Squire(decider), keep=3))
    assert [p.candidate.key for p in picks] == ["k1"]
    assert picks[0].p == pytest.approx(0.9) and decider.calls == 1


def test_repository_chunks_carry_path_and_lines(tmp_path: Path) -> None:
    from sanchopanza.context.repo import chunks

    (tmp_path / "src").mkdir()
    body = "".join(f"def f{i}():\n    return {i}\n\n\n" for i in range(200))
    (tmp_path / "src" / "many.py").write_text(body, encoding="utf-8")
    (tmp_path / "README.md").write_text("# Title\n\nHow to page results.\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("var paging = 1;", encoding="utf-8")
    found = chunks(tmp_path)
    paths = {c.key.split(":")[0] for c in found}
    assert paths == {"src/many.py", "README.md"}
    first = next(c for c in found if c.key.startswith("src/many.py:1-"))
    assert first.title.startswith("src/many.py:1-") and "def f0" in first.text


def test_find_in_a_repository_renders_paths_lines_and_excerpts(tmp_path: Path) -> None:
    from sanchopanza.context.repo import find

    (tmp_path / "pager.py").write_text(
        "def paginate(items, page, size):\n    start = (page - 1) * size\n"
        "    return items[start:start + size]\n",
        encoding="utf-8",
    )
    (tmp_path / "slug.py").write_text("def slugify(title):\n    return title.lower()\n", "utf-8")
    text = asyncio.run(find("page size paginate", tmp_path, k=1))
    assert "pager.py:1-3" in text and "paginate" in text and "slug.py" not in text
    assert "nothing" in asyncio.run(find("zebra quantum", tmp_path)).lower()


def test_the_archive_server_offers_repository_search_when_asked(tmp_path: Path) -> None:
    from sanchopanza.harness.mcp import build_archive_server

    (tmp_path / "pager.py").write_text("def paginate(items, page):\n    return items\n", "utf-8")
    lean = build_archive_server(tmp_path / "archive", find=False)
    assert [t.name for t in asyncio.run(lean.list_tools())] == ["search_archive"]
    server = build_archive_server(tmp_path / "archive", find=True, repo=tmp_path)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"search_archive", "find_in_repo"}
    assert len(tools["find_in_repo"].description) < 200
    result = asyncio.run(server.call_tool("find_in_repo", {"query": "paginate page", "k": 2}))
    assert "pager.py:1-2" in str(result)


def test_one_mcp_server_composes_the_tool_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    from sanchopanza.harness import mcp

    built = {}

    class Fake:
        def __init__(self) -> None:
            self.names: list[str] = []

        def tool(self, description: str | None = None):  # noqa: ANN201
            def register(fn):  # noqa: ANN001, ANN202
                self.names.append(fn.__name__)
                return fn

            return register

        def run(self) -> None:
            built["names"] = self.names

    monkeypatch.setattr(mcp, "_server", lambda name: Fake())
    mcp.main(["--tools", "archive,find,decisions"])
    assert built["names"] == [
        "search_archive",
        "find_in_repo",
        "verify_citation",
        "evaluate_plan",
        "align_entities",
        "classify_field",
        "triage_text",
    ]
    with pytest.raises(SystemExit):
        mcp.main(["--tools", "nope"])


def test_codex_config_offers_repository_search_when_asked() -> None:
    from sanchopanza.harness.codex import config_toml

    assert "find_in_repo" not in config_toml(python="py")
    text = config_toml(python="py", find=True)
    assert 'env = { SANCHOPANZA_FIND = "1" }' in text
    assert "[mcp_servers.sanchopanza_archive.tools.find_in_repo]" in text
