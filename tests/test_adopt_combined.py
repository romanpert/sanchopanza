"""Combined chains of the adoption benchmark (two chains in one session): which pairs fit, the
swap rule, the report split per chain, and the run's caps. No Docker, no network."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

import pytest

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"
sys.path.append(str(ADOPT))


def _purge() -> None:
    """Drop the bench's own modules registered under their bare names (`run`, `validate`...):
    other benchmarks have modules of the same names and would import these instead."""
    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None) or ""
        if not name.startswith("adopt_") and pathlib.Path(where).parent == ADOPT:
            del sys.modules[name]


def _load(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ADOPT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


combined = _load("adopt_combined", "combined.py")
run = _load("adopt_run_caps", "run.py")
_purge()


def hunk(start: int) -> str:
    body = "     a = 1\n-    b = a + 1\n+    b = a - 1\n     return b\n"
    return f"@@ -{start},3 +{start},3 @@ def g():\n{body}"


def patch(path: str, start: int) -> str:
    head = f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n"
    return head + hunk(start)


def bug(name: str, path: str, start: int, *tests: str) -> dict:
    return {"instance_id": f"repo.x.{name}", "patch": patch(path, start),
            "FAIL_TO_PASS": list(tests)}  # fmt: skip


def chain(name: str, *bugs: dict, kind: str | None = None) -> dict:
    return {"chain": name, "bugs": list(bugs), **({"kind": kind} if kind else {})}


FIRST = chain("r-1", bug("a", "p/a.py", 10, "t1"), bug("b", "p/b.py", 10, "t2"))


def test_a_pair_with_nothing_in_common_fits_as_it_is() -> None:
    second = chain("r-rel-1", bug("c", "p/a.py", 80, "t3"), bug("d", "p/a.py", 120, "t4"),
                   kind="related")  # fmt: skip
    out = combined.combine(FIRST, second, [], may_swap=False)
    assert [combined.short(b) for b in out["bugs"]] == ["a", "b", "c", "d"]
    assert [b["part"] for b in out["bugs"]] == ["r-1", "r-1", "r-rel-1", "r-rel-1"]
    assert out["swaps"] == [] and out["why"] == []


def test_a_held_out_pair_that_conflicts_is_not_used() -> None:
    overlap = chain("r-rel-1", bug("c", "p/a.py", 11, "t3"), kind="related")
    shared = chain("r-rel-1", bug("c", "p/c.py", 10, "t1"), kind="related")
    for second in (overlap, shared):
        out = combined.combine(FIRST, second, [bug("s", "p/a.py", 90, "t9")], may_swap=False)
        assert out["bugs"] is None and out["why"]


def test_a_development_pair_swaps_for_the_first_spare_that_fits_and_shares_a_file() -> None:
    second = chain("r-rel-1", bug("c", "p/a.py", 11, "t3"), bug("d", "p/a.py", 200, "t4"),
                   kind="related")  # fmt: skip
    spares = [bug("s1", "p/b.py", 11, "t5"),  # overlaps b
              bug("s2", "p/z.py", 10, "t6"),  # fits, shares no code file
              bug("s3", "p/b.py", 90, "t7")]  # fits and shares p/b.py  # fmt: skip
    out = combined.combine(FIRST, second, spares, may_swap=True)
    assert [combined.short(b) for b in out["bugs"]] == ["a", "b", "s3", "d"]
    assert out["swaps"] == ["c -> s3"] and out["bugs"][2]["part"] == "r-rel-1"


def test_a_conflict_inside_the_first_chain_ends_the_pair() -> None:
    bad = chain("r-1", bug("a", "p/a.py", 10, "t1"), bug("b", "p/a.py", 11, "t2"))
    out = combined.combine(bad, chain("r-rel-1", bug("c", "p/c.py", 10, "t3")), [], may_swap=True)
    assert out["bugs"] is None


def test_patches_are_normalised_and_keep_their_original() -> None:
    eol = ("@@ -40,2 +40,2 @@ def f():\n     x = 1\n-    return x\n+    return x\n"
           "\\ No newline at end of file\n")  # fmt: skip
    with_eol = {**bug("a", "p/a.py", 10, "t1")}
    with_eol["patch"] = with_eol["patch"] + eol
    out = combined.normed(with_eol, "r-1")
    assert "No newline" not in out["patch"] and out["patch_original"] == with_eol["patch"]


def test_unlinked_skips_the_seed_of_the_related_part() -> None:
    bugs = [{**combined.normed(bug("a", "p/a.py", 10, "t1"), "r-1")},
            {**combined.normed(bug("c", "p/c.py", 10, "t3"), "r-rel-1")},
            {**combined.normed(bug("d", "p/c.py", 90, "t4"), "r-rel-1")},
            {**combined.normed(bug("e", "p/e.py", 10, "t5"), "r-rel-1")}]  # fmt: skip
    assert combined.unlinked(bugs, "r-rel-1") == ["e"]


def test_report_splits_grade_and_cost_by_the_chain_each_bug_came_from() -> None:
    parts = ["r-1", "r-1", "r-rel-1"]
    ids = ["x.a", "x.b", "x.c"]
    ch = {"parts": ["r-1", "r-rel-1"],
          "bugs": [{"instance_id": i, "part": p}
                   for i, p in zip(ids, parts, strict=True)]}  # fmt: skip
    grade = {"bugs": [{"instance_id": i, "resolved": r} for i, r in zip(ids, (True, False, True),
                                                                        strict=True)]}  # fmt: skip
    row = {"calls": [{"request": 1, "instance_id": "x.a", "cost_usd": 1.0},
                     {"request": 2, "instance_id": "x.b", "cost_usd": 2.0,
                      "compactions": [{"pre_tokens": 1}]},
                     {"request": 3, "status": "NOT RUN (cap)", "cost_usd": 0.0}]}  # fmt: skip
    first, second = combined.split_by_part(ch, grade, row)
    assert first == {"part": "r-1", "resolved": 1, "bugs": 2, "cost_usd": 3.0, "compactions": 1,
                     "not_run": 0}  # fmt: skip
    assert second["resolved"] == 1 and second["not_run"] == 1 and second["cost_usd"] == 0.0


def test_held_out_pairs_are_listed_in_plan_order_independent_before_related() -> None:
    star, pyd = "swesmith/encode__starlette.db5063c2", "swesmith/pydantic__pydantic.acb0f10f"
    rows = [("encode__starlette-2", star, "held", None),
            ("encode__starlette-rel-2", star, "held", "related"),
            ("pydantic__pydantic-1", pyd, "held", None),
            ("pydantic__pydantic-rel-1", pyd, "held", "related"),
            ("encode__starlette-1", star, "dev", None)]  # fmt: skip
    picked = {n: {"chain": n, "repo": r, "split": s, **({"kind": k} if k else {})}
              for n, r, s, k in rows}  # fmt: skip
    names = [n for n, _, _ in combined.held_candidates(picked)]
    assert names == ["encode__starlette-long-2r2", "pydantic__pydantic-long-1r1"]


def test_caps_come_from_the_command_line_and_a_call_cap_above_the_chain_cap_is_refused() -> None:
    before = (run.CALL_CAP_USD, run.CHAIN_CAP_USD)
    try:
        run.set_caps(5.0, 15.0)
        assert (run.CALL_CAP_USD, run.CHAIN_CAP_USD) == (5.0, 15.0)
        assert run.call_cost({"cost_usd": 0.0}, [], fresh=True, code=-9)["cost_usd"] == 5.0
        with pytest.raises(SystemExit):
            run.set_caps(20.0, 15.0)
    finally:
        run.set_caps(*before)


def test_report_refuses_a_grade_whose_bugs_are_not_the_chains() -> None:
    ch = {"chain": "c", "parts": ["r-1"], "bugs": [{"instance_id": "x.a", "part": "r-1"}]}
    other = {"bugs": [{"instance_id": "x.z", "resolved": True}]}
    with pytest.raises(SystemExit, match="not the chain's"):
        combined.split_by_part(ch, other, {"calls": []})
