"""Reading the context close-out (`benchmarks/adopt/long_compact.py`) as its prereg says: cost on
the calls both arms ran, quality on the bugs both ran, the unit is the chain, and the verdict by
the rule written before any run. Free: synthetic rows, no Docker, no model."""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

import pytest

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"


@pytest.fixture
def lc(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ADOPT))
    import long_compact

    yield long_compact
    for name in [n for n in sys.modules if n.startswith(("long_", "run", "docker_env", "meter"))]:
        sys.modules.pop(name, None)


def _calls(n: int, usd: float, stop_at: int | None = None,
           pres: tuple[int, ...] = ()) -> list[dict[str, Any]]:  # fmt: skip
    out = []
    for k in range(1, n + 1):
        ran = stop_at is None or k <= stop_at
        out.append({"request": k, "kind": "bug", "instance_id": f"b{k}",
                    "status": "ran" if ran else "NOT RUN (cap)", "owner_usd": usd if ran else 0.0,
                    "peak_context": 60_000, "result_tail": "Fixed.",
                    "compactions": [{"pre": p} for p in pres] if k == 2 and ran else []})
    return out


def _arm(root: pathlib.Path, chain: str, arm: str, calls: list[dict[str, Any]],
         resolved: list[bool], common: int | None = None) -> None:  # fmt: skip
    ev = root / "runs" / f"{chain}-sonnet" / arm
    ev.mkdir(parents=True)
    row = {"run": f"{chain}-sonnet", "arm": arm, "model": "claude-sonnet-5-5", "bugs": len(calls),
           "calls": calls, "stopped": "", "requests_planned": len(calls), "token": "t"}
    (ev / "row.json").write_text(json.dumps(row), encoding="utf-8")
    grade = {"resolved": sum(resolved), "bugs_total": len(resolved),
             "bugs": [{"instance_id": f"b{k}", "resolved": r}
                      for k, r in enumerate(resolved, start=1)]}  # fmt: skip
    (ev / "grade.json").write_text(json.dumps(grade), encoding="utf-8")
    if common is not None:  # what `long_compact grade` writes
        (ev / "grade-common.json").write_text(json.dumps({**grade, "common_calls": common}),
                                              encoding="utf-8")  # fmt: skip
    for k in range(1, len(calls) + 1):  # each call changes code: no give-up
        (ev / f"diff-{k}.patch").write_text(f"diff --git a/x{k}.py b/x{k}.py\n", encoding="utf-8")


def test_common_calls_stop_at_the_shorter_run(lc) -> None:
    long_run_row = {"calls": _calls(10, 1.0)}
    capped = {"calls": _calls(10, 1.0, stop_at=7)}
    assert lc.common_calls(long_run_row, capped) == 7
    assert lc.cost_upto(long_run_row, 7) == 7.0


@pytest.mark.parametrize(("cost", "low", "chains", "expected"), [
    ({"high": 0.9, "low": 0.7}, -0.05, 5, "wins"),
    ({"high": 0.9, "low": 0.7}, -0.12, 5, "cheaper, quality not shown"),
    ({"high": 1.1, "low": 0.7}, 0.0, 5, "no difference shown"),
    ({"high": 1.4, "low": 1.1}, 0.0, 5, "dearer"),
    ({"high": 0.9, "low": 0.7}, 0.0, 4, "no verdict"),
])  # fmt: skip
def test_the_rule(lc, cost, low, chains, expected) -> None:  # noqa: ANN001
    assert lc.verdict(cost, low, chains) == expected


def test_five_cheaper_chains_with_the_same_bugs_win(lc, tmp_path: pathlib.Path) -> None:
    chains = [f"c{i}" for i in range(5)]
    for i, chain in enumerate(chains):
        same = [k % 4 != 0 for k in range(40)]
        _arm(tmp_path, chain, "Ne", _calls(40, 0.50), same, common=40)
        _arm(tmp_path, chain, "Nl", _calls(40, 0.40 + 0.01 * i, pres=(67_000,)), same, common=40)
    data = lc.read(tmp_path, chains)
    assert data["chains_counted"] == chains
    assert data["cost"]["n"] == 5 and data["cost"]["high"] < 1.0
    assert data["quality"]["difference"] == 0.0
    assert data["verdict"] == "wins"
    assert data["chains"]["c0"]["arms"]["Nl"]["compactions"] == [67_000]


def test_a_capped_run_is_compared_on_its_common_calls(lc, tmp_path: pathlib.Path) -> None:
    _arm(tmp_path, "c", "Ne", _calls(40, 0.50, stop_at=32), [True] * 40, common=32)
    _arm(tmp_path, "c", "Nl", _calls(40, 0.40), [True] * 40, common=32)
    line = lc.read(tmp_path, ["c"])["chains"]["c"]
    assert line["common_calls"] == 32 and line["common_bugs"] == 32
    assert line["arms"]["Ne"]["cost_common"] == 16.0 and line["arms"]["Nl"]["cost_common"] == 12.8
    assert line["ratio"] == 0.8


def test_fewer_than_five_chains_give_no_verdict(lc, tmp_path: pathlib.Path) -> None:
    for chain in ("a", "b"):
        _arm(tmp_path, chain, "Ne", _calls(40, 0.5), [True] * 40, common=40)
        _arm(tmp_path, chain, "Nl", _calls(40, 0.4), [True] * 40, common=40)
    assert lc.read(tmp_path, ["a", "b", "missing"])["verdict"] == "no verdict"


def test_a_call_asked_again_does_not_cut_the_common_calls(lc) -> None:
    calls = _calls(40, 1.0)
    again = [*calls[:10], {**calls[10], "superseded": True, "owner_usd": 0.3}, *calls[10:]]
    assert lc.common_calls({"calls": again}, {"calls": calls}) == 40
    assert lc.cost_upto({"calls": again}, 40) == 40.3  # the first try was paid too


def test_a_chain_without_its_common_grade_counts_for_nothing(lc, tmp_path: pathlib.Path) -> None:
    chains = [f"c{i}" for i in range(5)]
    for i, chain in enumerate(chains):
        common = None if i == 0 else 40
        _arm(tmp_path, chain, "Ne", _calls(40, 0.50), [True] * 40, common=common)
        _arm(tmp_path, chain, "Nl", _calls(40, 0.40 + 0.01 * i), [True] * 40, common=common)
    data = lc.read(tmp_path, chains)
    assert data["chains_counted"] == chains[1:] and data["verdict"] == "no verdict"
    assert data["chains"]["c0"]["graded_common"] is False


def test_both_arms_are_graded_at_the_last_common_call(lc, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    import perbug

    _arm(tmp_path, "c", "Ne", _calls(40, 0.50, stop_at=32), [True] * 40)
    _arm(tmp_path, "c", "Nl", _calls(40, 0.40), [True] * 40)
    graded: list[str] = []

    def fake_grade(chain, patch):  # noqa: ANN001, ANN202
        graded.append(patch)
        return {"resolved": 1, "bugs": [{"instance_id": "b1", "resolved": True}]}

    monkeypatch.setattr(perbug, "grade", fake_grade)
    known = {"c": {"chain": "c", "bugs": [{}] * 40, "split": "dev"}}
    lines = lc.grade_common(tmp_path, "c", known)
    assert len(lines) == 2 and all("call 32" in x for x in lines)
    assert graded == ["diff --git a/x32.py b/x32.py\n"] * 2
    for arm in ("Ne", "Nl"):
        out = json.loads((tmp_path / "runs" / "c-sonnet" / arm / "grade-common.json")
                         .read_text(encoding="utf-8"))  # fmt: skip
        assert out["common_calls"] == 32 and out["snapshot"] == "diff-32.patch"
