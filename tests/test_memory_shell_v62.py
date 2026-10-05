"""Memory v6.2: the shell touch acts on what a command writes, not on what it reads.

Amendment 5 (2026-10-01) did not confirm v6.1: on the maintainer's own sessions, agents in auto
mode read through `sed -n` and `grep -n` about 38 times per request, and 196 of the 258 records
the shell touch gave were unrelated, all of them from reads. With shell reads off, B2's fresh
requests kept recall 0.941 (Sonnet's records arrive at its `python - <<E` edits) and every
record a shell write gave on the local sessions was of a file the request wrote.
"""

# ruff: noqa: F811  (tests take the imported `store` fixture as a parameter)
from __future__ import annotations

from pathlib import Path

import pytest

from sanchopanza.harness import memory_hook as mh

from .test_memory_hook import (
    HEX_LINE,
    _bash_setup,
    bash_event,
    context_of,
    store,  # noqa: F401  (the fixture)
)

CARBON = "pygments/lexers/carbon.py"


def test_by_default_a_shell_read_gives_nothing(store: Path) -> None:
    new = _bash_setup(store)
    assert mh.handle(bash_event(new, "s2", f"sed -n 1,40p {CARBON}", HEX_LINE)) == {}
    assert mh.handle(bash_event(new, "s2", f'grep -n "Number.Hex" {CARBON}', HEX_LINE)) == {}


def test_a_shell_write_still_gives_the_record(store: Path) -> None:
    new = _bash_setup(store)
    out = mh.handle(bash_event(new, "s2", f"sed -i 's/Hex/Hexadecimal/' {CARBON}"))
    assert "request 1 of session s1" in context_of(out)


def test_an_interpreter_edit_gives_the_record_whose_lines_it_replaces(store: Path) -> None:
    new = _bash_setup(store)
    command = (f"python - <<'E'\np='{CARBON}'\ns=open(p).read()\n"
               f's=s.replace("""{HEX_LINE}""", "x")\nopen(p,\'w\').write(s)\nE')  # fmt: skip
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", command)))


def test_reads_can_be_turned_back_on(store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mh, "SHELL_READS", True)
    new = _bash_setup(store)
    out = mh.handle(bash_event(new, "s2", f"sed -n 1,40p {CARBON}", HEX_LINE))
    assert "session s1" in context_of(out)
