"""One registry of candidate sources behind `find` (`context.sources`), one `select` over all."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sanchopanza.context import sources
from sanchopanza.context.repo import find
from sanchopanza.select import Candidate


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "billing.py").write_text(
        "class Invoice:\n    def total(self):\n        return 1\n\n\n"
        "def refund_payment(order):\n    return order\n",
        encoding="utf-8",
    )
    skill = root / ".claude" / "skills" / "pdf-reports"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: pdf-reports\ndescription: Build PDF reports from tables\n---\n# PDF\n",
        encoding="utf-8",
    )
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "db-migrator.md").write_text(
        "---\nname: db-migrator\ndescription: Writes and checks database migrations\n---\n",
        encoding="utf-8",
    )
    memory = root / ".claude" / "memory"
    memory.mkdir(parents=True)
    (memory / "refunds.md").write_text("Refunds go through the payments queue.\n", "utf-8")
    catalog = tmp_path / "tools.json"
    catalog.write_text(
        json.dumps(
            [
                {"name": "send_invoice", "description": "Email an invoice"},
                {"name": "get_weather", "description": "Weather"},
            ]
        ),
        "utf-8",
    )
    monkeypatch.setenv("SANCHOPANZA_TOOL_CATALOG", str(catalog))
    return root


def test_every_builtin_kind_is_registered() -> None:
    expected = {"code", "symbol", "file", "skill", "agent", "memory", "archive", "tool"}
    assert expected <= set(sources.kinds())


def test_symbols_carry_qualified_names_and_line_ranges(project: Path) -> None:
    found, _ = sources.indexed("symbol", project)
    titles = {c.title.split(" ", 1)[1].split(":")[0] for c in found}
    assert {"Invoice", "Invoice.total", "refund_payment"} <= titles
    assert any(c.key == "src/billing.py:6-7" for c in found)


@pytest.mark.parametrize(
    ("kind", "query", "key"),
    [
        ("skill", "make a pdf report of the table", ".claude/skills/pdf-reports/SKILL.md"),
        ("agent", "database migration", ".claude/agents/db-migrator.md"),
        ("memory", "how do refunds work", ".claude/memory/refunds.md"),
        ("tool", "email the invoice", "send_invoice"),
        ("symbol", "refund a payment", "src/billing.py:6-7"),
        ("file", "invoice total", "src/billing.py"),
    ],
)
def test_find_by_kind(project: Path, kind: str, query: str, key: str) -> None:
    out = asyncio.run(find(query, project, kind=kind))
    assert key in out


def test_an_unknown_kind_names_the_known_ones(project: Path) -> None:
    out = asyncio.run(find("x y z", project, kind="nope"))
    assert "skill" in out and "symbol" in out


def test_a_registered_source_is_searched_like_any_other(project: Path) -> None:
    source = sources.Source(
        "fruit",
        "Find the fruit for: {query}",
        lambda root: [],
        lambda root, paths: [Candidate("apple", "apple: red", "a red apple")],
    )
    sources.register(source)
    try:
        assert "apple" in asyncio.run(find("red fruit", project, kind="fruit"))
    finally:
        sources.SOURCES.pop("fruit")


def test_the_index_is_rebuilt_when_a_file_changes(project: Path) -> None:
    before, _ = sources.indexed("memory", project)
    (project / ".claude" / "memory" / "shipping.md").write_text("Ships on Mondays.\n", "utf-8")
    after, _ = sources.indexed("memory", project)
    assert len(after) == len(before) + 1
