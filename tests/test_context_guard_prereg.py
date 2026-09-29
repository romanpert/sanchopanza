"""The compaction-guard registrations cannot move after the fact.

Each `.sha256` holds one line per version (the registration, then every amendment); the file as
it stands must hash to the last line. The files are stored byte for byte (`.gitattributes`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

RESULTS = Path(__file__).parents[1] / "docs" / "results" / "2026-09-29-context-guard"


@pytest.mark.parametrize("name", ["prereg", "prereg-prompt-recall"])
def test_the_registration_hashes_to_its_last_recorded_version(name):
    lines = (RESULTS / f"{name}.sha256").read_text("utf-8").split()
    assert hashlib.sha256((RESULTS / f"{name}.md").read_bytes()).hexdigest() == lines[-1]
