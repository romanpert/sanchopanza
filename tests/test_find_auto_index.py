"""What the find-auto hook needs from the index: built in the background when the server starts,
read without a rebuild when the hook fires, and nothing (not a 35-second build) when it is not
there yet. Plus the tokeniser's ASCII path, which made the build 4x faster without changing a
single token."""

from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path

import pytest

from sanchopanza import text
from sanchopanza.context import repo


def _slow_words(value: str) -> list[str]:
    """The tokeniser before the ASCII path, kept here as the reference."""
    plain = unicodedata.normalize("NFKD", (value or "").lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return [t for t in text.re.findall(r"[a-z0-9_]+", plain)
            if t not in text.STOPWORDS and len(t) > 1]  # fmt: skip


@pytest.mark.parametrize("value", [
    "def get_queryset(self):\n    return Foo.objects.filter(pk=1)",
    "Ñandú café naïve ÉCOLE ﬁne Ⅻ ２０２６ résumé_x",
    "", "a b c de la", "\t\x00\x7f mixed ascii and ü",
])  # fmt: skip
def test_the_ascii_path_gives_the_same_words(value: str) -> None:
    assert text._bm25_words(value) == _slow_words(value)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "compiler.py").write_text(
        "def returning_fields(rows):\n    return converters(rows)\n", "utf-8"
    )
    (root / "docs").mkdir()
    (root / "docs" / "notes.md").write_text("returning fields converters\n", "utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_ready_index_is_none_before_any_build_and_never_builds(tmp_path: Path) -> None:
    root = _project(tmp_path)
    repo._CACHE.pop(str(root.resolve()), None)
    assert repo.ready_index(root) is None
    assert str(root.resolve()) not in repo._CACHE  # asking did not build it


def test_warm_builds_in_the_background_and_ready_index_ranks_source_only(tmp_path: Path) -> None:
    root = _project(tmp_path)
    repo._CACHE.pop(str(root.resolve()), None)
    thread = repo.warm(root)
    thread.join(timeout=60)
    got = repo.ready_index(root)
    assert got is not None
    candidates, ranked = got
    keys = [candidates[i].key for i, _ in ranked.top("returning fields converters", 5)]
    assert keys == ["pkg/compiler.py:1-2"]  # the doc matches too, and is left out


def test_ready_index_keeps_the_warm_tree_after_a_file_changes(tmp_path: Path) -> None:
    """The hook fires before any source file is edited; a new scratch file the agent wrote
    must not cost a rebuild at fire time."""
    root = _project(tmp_path)
    repo._CACHE.pop(str(root.resolve()), None)
    repo.warm(root).join(timeout=60)
    (root / "reproduce.py").write_text("print('x')\n", "utf-8")
    got = repo.ready_index(root)
    assert got is not None and all("reproduce" not in c.key for c in got[0])


def test_a_failed_warm_leaves_nothing_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                                           ) -> None:  # fmt: skip
    root = _project(tmp_path)
    repo._CACHE.pop(str(root.resolve()), None)

    def boom(_root: Path) -> None:
        raise OSError("disk")

    monkeypatch.setattr(repo, "source_first", boom)
    repo.warm(root).join(timeout=60)
    assert repo.ready_index(root) is None
