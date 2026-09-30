"""The workspace snapshot hashes only what changed since the last one (11.9 s to 0.3 s, Indagis)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sanchopanza.harness import candor_hook


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_CANDOR_DIR", str(tmp_path / "state"))
    work = tmp_path / "work"
    (work / "src").mkdir(parents=True)
    (work / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
    (work / "b.txt").write_text("b\n", encoding="utf-8")
    return work


def _count_reads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    seen: list[Path] = []
    original = Path.read_bytes

    def counting(self: Path) -> bytes:
        seen.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", counting)
    return seen


def test_an_unchanged_tree_is_not_read_again(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = candor_hook.snapshot(root)
    reads = _count_reads(monkeypatch)
    assert candor_hook.snapshot(root) == first
    assert reads == []


def test_a_change_is_seen_and_only_it_is_read(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = candor_hook.snapshot(root)
    target = root / "src" / "a.py"
    target.write_text("a = 2\n", encoding="utf-8")
    stamp = target.stat().st_mtime_ns + 10_000_000
    os.utime(target, ns=(stamp, stamp))  # coarse clocks: make sure the mtime moved
    reads = _count_reads(monkeypatch)
    after = candor_hook.snapshot(root)
    assert candor_hook.diff(before, after) == ["src/a.py"]
    assert [p.name for p in reads] == ["a.py"]


def test_a_new_and_a_removed_file_are_seen(root: Path) -> None:
    before = candor_hook.snapshot(root)
    (root / "b.txt").unlink()
    (root / "c.txt").write_text("c\n", encoding="utf-8")
    assert candor_hook.diff(before, candor_hook.snapshot(root)) == ["b.txt", "c.txt"]


def test_a_corrupt_cache_costs_a_rehash_not_a_wrong_answer(root: Path) -> None:
    first = candor_hook.snapshot(root)
    cache = candor_hook._stat_cache_path(root)
    cache.write_text("{not json", encoding="utf-8")
    assert candor_hook.snapshot(root) == first
    cache.write_text('{"src/a.py": [6, 0, "stale"]}', encoding="utf-8")  # wrong mtime: rehashed
    assert candor_hook.snapshot(root) == first
