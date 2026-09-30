"""The adoption benchmark's pure parts: the arms, per-call cost accounting, and the related
chains (end-of-file hunks, overlapping hunks, growth by shared files). No Docker, no network."""

from __future__ import annotations

import importlib.util
import pathlib
import random
import sys
from types import ModuleType

import pytest

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"
sys.path.append(str(ADOPT))  # for their own imports (chains, docker_env); appended, not first


def _load(name: str, file: str) -> ModuleType:
    """Under a name of its own: other benchmarks also have a `run` module."""
    spec = importlib.util.spec_from_file_location(name, ADOPT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("adopt_run", "run.py")
related = _load("adopt_related", "related.py")


def patch(path: str, *hunks: str) -> str:
    head = f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n"
    return head + "".join(hunks)


EOL = (
    "@@ -40,2 +40,2 @@ def f():\n     x = 1\n-    return x\n+    return x\n"
    "\\ No newline at end of file\n"
)
REAL = "@@ -10,3 +10,3 @@ def g():\n     a = 1\n-    b = a + 1\n+    b = a - 1\n     return b\n"


def row(name: str, text: str, f2p: tuple[str, ...]) -> dict:
    return {"instance_id": name, "patch": text, "FAIL_TO_PASS": list(f2p)}


# ---- arms ---------------------------------------------------------------------------------------


def test_n_and_s_are_unchanged_for_the_singles_runner() -> None:
    assert run.ARMS == ("N", "S")
    assert run.ARM_SPECS["N"] == run.Arm(None) and run.ARM_SPECS["S"] == run.Arm(())
    assert run.ARM_SPECS["Nf"].fresh and run.ARM_SPECS["Nf"].install is None
    assert run.ARM_SPECS["Sf"] == run.Arm(("--memory",), fresh=True)
    assert "--memory" in run.ARM_SPECS["Sm"].install and not run.ARM_SPECS["Sm"].fresh


def test_a_resumed_session_is_charged_the_difference_and_a_fresh_one_its_own_cost() -> None:
    rows = [{"cost_cumulative": 0.40, "cost_usd": 0.40}]
    resumed = run.call_cost({"cost_usd": 0.65}, rows, fresh=False, code=0)
    assert resumed["cost_usd"] == 0.25 and resumed["cost_cumulative"] == 0.65
    fresh = run.call_cost({"cost_usd": 0.30}, rows, fresh=True, code=0)
    assert fresh["cost_usd"] == 0.30


def test_a_call_cut_before_its_result_is_charged_its_cap() -> None:
    cut = run.call_cost({"cost_usd": 0.0}, [], fresh=True, code=-9)
    assert cut["cost_usd"] == run.CALL_CAP_USD
    assert run.call_cost({"cost_usd": 0.0}, [], fresh=True, code=1)["cost_usd"] == 0.0


def test_a_cut_call_then_a_resumed_one_are_not_charged_the_cut_part_twice() -> None:
    cap = run.CALL_CAP_USD
    rows = [{"cost_cumulative": 0.40, "cost_usd": 0.40}]
    cut = run.call_cost({"cost_usd": 0.0}, rows, fresh=False, code=-9)
    assert cut["cost_usd"] == cap and cut["cost_cumulative"] == 0.40 + cap
    # the session's own total now holds the cut call's partial cost and the next call's (0.30)
    partial = cap - 0.10
    after = run.call_cost({"cost_usd": 0.40 + partial + 0.30}, [*rows, cut], fresh=False, code=0)
    assert after["cost_usd"] == pytest.approx(0.20)  # the cap charged 0.10 more than the partial
    assert rows[0]["cost_usd"] + cut["cost_usd"] + after["cost_usd"] == pytest.approx(
        0.40 + partial + 0.30)  # the session's true total, charged once  # fmt: skip
    # a partial well below the cap leaves a negative difference: charged 0, never less
    low = run.call_cost({"cost_usd": 0.40 + 0.10}, [*rows, cut], fresh=False, code=0)
    assert low["cost_usd"] == 0.0


# ---- related chains -----------------------------------------------------------------------------


def test_normalize_drops_end_of_file_hunks_and_keeps_the_bug() -> None:
    text = patch("pkg/a.py", REAL, EOL)
    out = related.normalize(text)
    assert "No newline" not in out and "b = a - 1" in out
    assert related.normalize(patch("pkg/b.py", EOL)) == ""  # a file with only that hunk goes
    assert related.normalized(row("x", text, ()))["patch_original"] == text


def test_spans_and_overlaps() -> None:
    a = related.spans(patch("pkg/a.py", REAL))
    assert a == {"pkg/a.py": [(10, 12)]}
    near = related.spans(patch("pkg/a.py", REAL.replace("-10,3", "-12,3")))
    far = related.spans(patch("pkg/a.py", REAL.replace("-10,3", "-30,3")))
    other = related.spans(patch("pkg/c.py", REAL))
    assert related.overlaps(a, near) and not related.overlaps(a, far)
    assert not related.overlaps(a, other)


def test_grow_takes_bugs_sharing_a_file_without_overlap_or_shared_tests() -> None:
    seed = row("s", patch("pkg/a.py", REAL), ("t1",))
    same_place = row("x", patch("pkg/a.py", REAL), ("t2",))
    shared_test = row("y", patch("pkg/a.py", REAL.replace("-10,3", "-50,3")), ("t1",))
    unrelated = row("z", patch("pkg/z.py", REAL), ("t3",))
    good = row("g", patch("pkg/a.py", REAL.replace("-10,3", "-80,3")), ("t4",))
    chain = related.grow(seed, [same_place, shared_test, unrelated, good], set(), 5)
    assert [r["instance_id"] for r in chain] == ["s", "g"]


def test_draw_is_seeded_and_every_later_bug_shares_a_file_with_an_earlier_one() -> None:
    rows = [row(f"b{i}", patch("pkg/a.py", REAL.replace("-10,3", f"-{10 + 20 * i},3")), (f"t{i}",))
            for i in range(9)]  # fmt: skip
    rows = [{**r, "problem_statement": "x", "PASS_TO_PASS": []} for r in rows]
    first = related.draw(rows, 1, random.Random(1), 3)
    again = related.draw(rows, 1, random.Random(1), 3)
    assert first == again and len(first[0][0]) == 5 and len(first[0][1]) == 3
    bugs = first[0][0]
    for k in range(1, len(bugs)):
        earlier = set().union(*(related.code_files(b) for b in bugs[:k]))
        assert related.code_files(bugs[k]) & earlier


def test_a_call_that_never_opened_a_session_is_a_harness_failure_not_a_result() -> None:
    empty = {"session": "", "subtype": None, "cost_usd": 0.0}
    assert run.harness_failed(1, empty)
    assert not run.harness_failed(-9, empty)  # the timeout: charged its cap, a result
    assert not run.harness_failed(0, empty)
    assert not run.harness_failed(1, {**empty, "session": "abc"})
    assert not run.harness_failed(1, {**empty, "subtype": "error_max_budget_usd"})


def test_install_files_the_agent_emptied_are_restored_and_named(tmp_path: pathlib.Path) -> None:
    work, evidence = tmp_path / "work", tmp_path / "evidence"
    (work / ".claude" / "skills" / "s").mkdir(parents=True)
    (work / ".claude" / "settings.json").write_text('{"hooks": {}}', encoding="utf-8")
    (work / ".claude" / "skills" / "s" / "SKILL.md").write_text("skill", encoding="utf-8")
    (work / ".mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
    run.snapshot_install(work, evidence)
    assert run.restore_install(work, evidence) == []
    (work / ".mcp.json").write_text("", encoding="utf-8")  # what `git checkout .` left
    (work / ".claude" / "skills" / "s" / "SKILL.md").unlink()
    assert run.restore_install(work, evidence) == [".claude/skills/s/SKILL.md", ".mcp.json"]
    assert (work / ".mcp.json").read_text(encoding="utf-8") == '{"mcpServers": {}}'
