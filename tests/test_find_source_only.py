"""`find_in_repo(kind="code")` ranks source files only; docs, config and tests stay reachable.

Measured offline (benchmarks/find_auto, f1ef58e): on 35 hard SWE-bench sessions a gold file was
in the free top 5 in 4/35 as shipped and in 13/35 with source files only, because issue texts
match docs pages and issue templates (xarray's template repeats the issue's own headings) better
than the code that has to change.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sanchopanza.context.repo import find, hint, is_source, is_test

QUERY = "the export drops the last row when the header row repeats"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A source file that holds the fix, and a docs page, an issue template and a test that all
    repeat the request's words more often than the source does."""
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "export.py").write_text(
        "def write_rows(rows, header):\n"
        "    out = [header]\n"
        "    for row in rows[:-1]:\n"
        "        out.append(row)\n"
        "    return out\n",
        encoding="utf-8",
    )
    (root / "pkg" / "slug.py").write_text("def slugify(title):\n    return title\n", "utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "export.md").write_text(
        "# Export\n\nThe export writes every row. The export keeps the last row. When the header "
        "row repeats, the export drops the repeated header row, never the last row.\n",
        encoding="utf-8",
    )
    template = root / ".github" / "ISSUE_TEMPLATE"
    template.mkdir(parents=True)
    (template / "bug.yml").write_text(
        "name: Bug report\nbody:\n  - label: What happened when the export drops the last row?\n"
        "  - label: Does the header row repeat? Which row does the export drop?\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_export.py").write_text(
        "def test_export_keeps_the_last_row_when_the_header_row_repeats():\n"
        "    assert export_last_row_header_row_repeats()\n",
        encoding="utf-8",
    )
    return root


def _keys(text: str) -> list[str]:
    return [line.split("] ", 1)[1].split(" ")[0] for line in text.splitlines() if line[:1] == "["]


def test_the_fixture_is_hard_every_text_outranks_the_source(repo: Path) -> None:
    keys = _keys(asyncio.run(find(QUERY, repo, k=8, kind="all")))
    assert keys.index(next(k for k in keys if k.startswith("pkg/export.py"))) >= 2


def test_kind_code_returns_the_source_file_first_and_no_template(repo: Path) -> None:
    text = asyncio.run(find(QUERY, repo, k=8))  # kind="code" is the default
    keys = _keys(text)
    assert keys and keys[0].startswith("pkg/export.py")
    assert not any(k.startswith((".github/", "docs/", "tests/")) for k in keys)


def test_kind_all_still_finds_the_docs_and_the_template(repo: Path) -> None:
    keys = _keys(asyncio.run(find(QUERY, repo, k=8, kind="all")))
    assert any(k.startswith("docs/export.md") for k in keys)
    assert any(k.startswith(".github/ISSUE_TEMPLATE/bug.yml") for k in keys)


def test_kind_code_falls_back_to_every_text_when_no_source_matches(repo: Path) -> None:
    text = asyncio.run(find("never the repeated one", repo, k=3))  # words of the docs page only
    assert any(k.startswith("docs/export.md") for k in _keys(text))
    assert "no source" in text.lower()  # says that what it shows is not code


def test_the_prompt_hint_names_source_files_only(repo: Path) -> None:
    text = hint(QUERY, repo, k=3)
    assert "pkg/export.py" in text
    assert ".github" not in text and "docs/" not in text


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("xarray/core/dataset.py", True),
        ("src/app/view.tsx", True),
        ("scripts/release.sh", True),
        ("doc/whats-new.rst", False),
        ("docs/api.py", False),
        (".github/ISSUE_TEMPLATE/bugreport.yml", False),
        ("pkg/settings.yaml", False),
        ("setup.cfg", False),
        ("pyproject.toml", False),
        ("tests/test_dataset.py", False),
        ("pkg/conftest.py", False),
        ("web/button.spec.ts", False),
        ("examples/demo.py", False),
        ("asv_bench/benchmarks/io.py", False),
        ("Makefile", False),
    ],
)
def test_is_source_is_the_measured_filter(path: str, expected: bool) -> None:
    assert is_source(path) is expected


def test_is_test_matches_folders_prefixes_and_infixes() -> None:
    assert is_test("pkg/testing/x.py") and is_test("pkg/test_x.py") and is_test("a/b_test.go")
    assert not is_test("pkg/contest.py")
