"""No tracked file names the owner's other projects: not in its path, not in its bytes.

The first name is built here so that this file does not hold it either. The others are kept only
as sha256 digests of their lowercased form, compared with every word of every tracked path and
file (and with every two adjacent words joined, so a spelling with a hyphen, an underscore, a
space or a capital is caught too). More names can be given, never committed, as a
comma-separated list in SANCHOPANZA_PRIVATE_NAMES.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PRIVATE = ("inda" + "gis",)
HASHED = frozenset({
    "871218d9cd73fe0c69c22f890eab7411278e7bef7affd5e3fefde347df3644ec",
    "216bda9c86fdb3c9effef948a05b377afa54e19e32d2dc3ddca0cd97605c7993",
})  # fmt: skip
EXTRA_ENV = "SANCHOPANZA_PRIVATE_NAMES"
WORD = re.compile(rb"[a-z]+")


def _tracked() -> list[str]:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True,
                         check=True).stdout  # fmt: skip
    return [p for p in out.decode("utf-8").split("\0") if p]


def _digest(word: bytes) -> str:
    return hashlib.sha256(word).hexdigest()


def hashed_names(environ: Mapping[str, str] = os.environ) -> frozenset[str]:
    extra = environ.get(EXTRA_ENV, "")
    words = (w.strip().lower().encode("utf-8") for w in extra.split(","))
    return HASHED | {_digest(re.sub(rb"[^a-z]", b"", w)) for w in words if w}


def hits(blob: bytes, digests: Iterable[str]) -> bool:
    """Whether a word of `blob`, or two adjacent words joined, hashes to one of `digests`."""
    wanted = frozenset(digests)
    words = WORD.findall(blob.lower())
    candidates = {*words, *(a + b for a, b in zip(words, words[1:], strict=False))}
    return any(_digest(w) in wanted for w in candidates)


def test_no_tracked_path_or_file_holds_a_private_name() -> None:
    found = []
    for rel in _tracked():
        path = REPO / rel
        if not path.is_file():
            continue  # deleted in the work tree, not yet staged
        body = path.read_bytes().lower()
        for name in PRIVATE:
            if name in rel.lower() or name.encode() in body:
                found.append(rel)
    assert found == []


def test_no_tracked_path_or_file_holds_a_hashed_private_name() -> None:
    digests = hashed_names()
    found = []
    for rel in _tracked():
        path = REPO / rel
        if not path.is_file():
            continue  # deleted in the work tree, not yet staged
        if hits(rel.encode("utf-8"), digests) or hits(path.read_bytes(), digests):
            found.append(rel)
    assert found == []


def test_the_hashed_check_catches_case_and_separator_variants() -> None:
    digests = {_digest(b"projecta")}
    variants = (b"x projecta y", b"C--x-ProjectA-sancho", b"project-a", b"Project_A", b"PROJECT A")
    for text in variants:
        assert hits(text, digests), text
    assert not hits(b"project-b and a project", digests)


def test_extra_names_come_from_the_environment_only() -> None:
    assert hashed_names({}) == HASHED
    extra = hashed_names({EXTRA_ENV: " Project-A , ,other"})
    assert extra == HASHED | {_digest(b"projecta"), _digest(b"other")}
