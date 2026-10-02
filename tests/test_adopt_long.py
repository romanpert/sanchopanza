"""Long chains (`benchmarks/adopt/long.py`): a second chain of one repository leaves the first as
drawn and shares no bug or spare with it (memory amendment 6, part A, needs a new Sonnet 5.5
chain: `pydantic__pydantic-long40-1` was spent in B2, and pydantic has too few bugs left)."""

from __future__ import annotations

import pathlib
import sys
from typing import Any

import pytest

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"


@pytest.fixture
def long(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(ADOPT))
    for name in ("long", "chains", "related"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import chains
    import long as module
    import related

    rows = [{"instance_id": f"b{i}", "patch": "", "FAIL_TO_PASS": [f"t{i}"], "image_name": "img"}
            for i in range(40)]  # fmt: skip
    monkeypatch.setattr(chains, "load", lambda: {"repo": rows})
    monkeypatch.setattr(chains, "full", lambda: [])
    monkeypatch.setattr(chains, "usable", lambda row: True)
    monkeypatch.setattr(related, "full", lambda: [])
    monkeypatch.setattr(related, "normalized", lambda row: row)
    monkeypatch.setattr(related, "code_files", lambda row: ["pkg/a.py"])
    monkeypatch.setattr(related, "spans", lambda patch: {})
    monkeypatch.setattr(related, "overlaps", lambda a, b: False)
    monkeypatch.setattr(module, "SIZE", 6)
    monkeypatch.setattr(module, "SPARES", 2)
    yield module
    for name in ("long", "chains", "related"):
        sys.modules.pop(name, None)


def ids(chain: dict[str, Any], key: str) -> list[str]:
    return [b["instance_id"] for b in chain[key]]


def test_a_second_chain_leaves_the_first_as_drawn_and_shares_nothing(long) -> None:  # type: ignore[no-untyped-def]
    first = ("repo", "c-1", "dev")
    alone = long.select((first,))
    both = long.select((first, ("repo", "c-2", "dev")))
    assert both[0] == alone[0]
    taken = set(ids(both[0], "bugs")) | set(ids(both[0], "spares"))
    second = set(ids(both[1], "bugs")) | set(ids(both[1], "spares"))
    assert len(ids(both[1], "bugs")) == 6 and not taken & second


def test_the_plan_keeps_pydantic_long40_1_first_and_adds_conan() -> None:
    sys.path.insert(0, str(ADOPT))
    try:
        for name in ("long", "chains", "related"):
            sys.modules.pop(name, None)
        import long as module

        names = [name for _, name, _ in module.PLAN]
    finally:
        sys.path.remove(str(ADOPT))
        for name in ("long", "chains", "related"):
            sys.modules.pop(name, None)
    assert names == ["pydantic__pydantic-long40-1", "conan-io__conan-long40-1"]
