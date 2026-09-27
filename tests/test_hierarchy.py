"""The tournament over more pages than one call holds: grouping, rounds, fail-open, the blend."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from sanchopanza.points.hierarchy import groups, tournament


def test_groups_are_balanced_and_keep_order() -> None:
    assert groups(10, 30) == [list(range(10))]
    split = groups(100, 30)
    assert [len(g) for g in split] == [25, 25, 25, 25]
    assert [i for g in split for i in g] == list(range(100))
    assert [len(g) for g in groups(61, 30)] == [21, 20, 20]
    assert groups(0, 30) == []


def test_groups_need_a_positive_size() -> None:
    with pytest.raises(ValueError):
        groups(5, 0)


class Judge:
    """p for each page from a fixed table; records every call's page ids."""

    def __init__(self, table: dict[int, float | None]) -> None:
        self.table = table
        self.calls: list[list[int]] = []

    async def __call__(self, ids: Sequence[int]) -> list[float | None]:
        self.calls.append(list(ids))
        return [self.table[i] for i in ids]


def test_small_sets_take_one_call() -> None:
    judge = Judge({i: 0.9 if i == 3 else 0.1 for i in range(10)})
    result = asyncio.run(tournament(10, judge, size=30, first_cut=0.2, final_cut=0.4))
    assert judge.calls == [list(range(10))]
    assert [v.keep for v in result.pages] == [i == 3 for i in range(10)]
    assert result.calls == 1


def test_survivors_are_judged_together() -> None:
    table = {i: 0.05 for i in range(100)}
    table.update({7: 0.9, 55: 0.3, 90: 0.25})
    judge = Judge(table)
    result = asyncio.run(tournament(100, judge, size=30, first_cut=0.2, final_cut=0.4))
    assert len(judge.calls) == 5
    assert judge.calls[-1] == [7, 55, 90]
    assert {i for i, v in enumerate(result.pages) if v.keep} == {7}
    assert result.pages[55].first == 0.3 and result.pages[55].final == 0.3
    assert result.pages[0].final is None and not result.pages[0].keep


def test_unanswered_pages_enter_and_stay() -> None:
    table: dict[int, float | None] = {i: 0.0 for i in range(60)}
    table[12] = None
    judge = Judge(table)
    result = asyncio.run(tournament(60, judge, size=30, first_cut=0.2, final_cut=0.4))
    assert judge.calls[-1] == [12]
    assert result.pages[12].keep


def test_a_round_that_prunes_nothing_stops_the_rounds() -> None:
    judge = Judge({i: 0.9 for i in range(70)})
    result = asyncio.run(tournament(70, judge, size=30, first_cut=0.2, final_cut=0.4))
    assert result.rounds == 1
    assert all(v.keep for v in result.pages)
    # The round already judged every candidate: asking the same groups again would only buy
    # the decider's noise (Jev is not deterministic), and it broke replay on 2026-09-27.
    assert len(judge.calls) == 3
    assert result.calls == 3


class Sequenced:
    """Each page answers from its own list, one value per time it is asked."""

    def __init__(self, values: dict[int, list[float]]) -> None:
        self.values = {i: list(v) for i, v in values.items()}
        self.calls: list[list[int]] = []

    async def __call__(self, ids: Sequence[int]) -> list[float | None]:
        self.calls.append(list(ids))
        return [self.values[i].pop(0) for i in ids]


def test_each_page_reports_the_last_probability_it_got() -> None:
    values = {i: [0.5, 0.5, 0.5] for i in range(80)}
    values.update({i: [0.1] for i in range(80, 100)})
    values[5] = [0.5, 0.05]  # survives round one, falls in round two
    values[7] = [0.5, 0.9, 0.9]
    judge = Sequenced(values)
    result = asyncio.run(tournament(100, judge, size=30, first_cut=0.2, final_cut=0.4))
    # Round one prunes 20, round two prunes page 5, round three prunes nothing and its answers
    # are the final ones. Round three regroups the 79 survivors and its last group, pages
    # 54-79, is round two's last group: its answers are reused, 4 + 3 + 2 calls.
    assert result.rounds == 3
    assert result.calls == 9
    assert result.pages[90].last == 0.1 and not result.pages[90].keep
    assert result.pages[5].last == 0.05 and not result.pages[5].keep
    assert result.pages[7].last == 0.9 and result.pages[7].keep


def test_blend_mixes_both_rounds() -> None:
    table = {i: 0.05 for i in range(40)}
    table.update({1: 0.3, 2: 0.9})
    judge = Judge(table)
    result = asyncio.run(tournament(40, judge, size=30, first_cut=0.2, final_cut=0.4, blend=0.5))
    assert result.pages[1].score == pytest.approx(0.3)
    assert result.pages[2].keep
