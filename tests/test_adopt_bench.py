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


def test_the_frozen_copy_is_named_in_every_row(tmp_path: pathlib.Path, monkeypatch) -> None:  # noqa: ANN001
    exe = tmp_path / "frozen" / "abc" / "Scripts" / "sanchopanza.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.setattr(run, "SANCHO", exe)
    assert run.frozen_stamp() is None and run.provenance()["frozen"] is None
    (exe.parents[1] / "stamp.json").write_text('{"commit": "abc", "version": "0.3.0"}',
                                               encoding="utf-8")  # fmt: skip
    assert run.provenance() == {"exe": str(exe), "frozen": {"commit": "abc", "version": "0.3.0"}}


masking = _load("adopt_masking", "masking.py")


def test_maskers_are_found_by_bisection_and_a_broken_bug_is_its_own_culprit() -> None:
    # bug 0 passes only when bug 5 is fixed with it
    calls: list[list[int]] = []

    def passes(i: int, fixed: list[int]) -> bool:
        calls.append(fixed)
        return 5 in fixed

    assert masking.maskers(0, list(range(1, 9)), passes) == [5]
    assert len(calls) <= 5  # all, then halves: log2(8) + 1
    assert masking.maskers(0, [1, 2, 3], lambda i, fixed: False) == [0]  # broken on its own
    # needs 2 and 7 together: the halves both fail, the group is kept whole
    assert masking.maskers(0, [2, 7], lambda i, fixed: {2, 7} <= set(fixed)) == [2, 7]


def test_a_group_bisection_cannot_split_is_narrowed_to_the_bugs_it_needs() -> None:
    # bug 0 passes only with 1 and 6 fixed: the halves [1..4] and [5..8] both fail
    group = masking.maskers(0, list(range(1, 9)), lambda i, fixed: {1, 6} <= set(fixed))
    assert group == [1, 6]


def test_a_run_where_nothing_ran_counts_as_not_passing(monkeypatch) -> None:  # noqa: ANN001
    def broken(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("pytest gave no results (exit 123): no tests ran")

    monkeypatch.setattr(masking.docker_env, "pytest", broken)
    bugs = [{"patch": "p0\n", "FAIL_TO_PASS": ["t::a[x]"]}, {"patch": "p1\n", "FAIL_TO_PASS": []}]
    assert masking.passes_with("tag", bugs, 0, [1]) is False
    assert masking.fails_with("tag", bugs, 0, [1]) is False


def _world(masker: int, n: int = 8):  # noqa: ANN202
    """Docker faked: bug 0's test passes with every bug in because bug `masker` hides it (the
    bug undoes the path 0 breaks); it fails with 0 in and `masker` undone, and passes with 0
    undone. The patch names the undone bugs ("p<k>")."""
    bugs = [{"patch": f"p{k}\n", "FAIL_TO_PASS": [f"t::b{k}"]} for k in range(n)]

    def pytest(_tag, patch, nodes, reverse=False):  # noqa: ANN001, ANN202
        undone = {int(x[1:]) for x in patch.split()}
        baked = set(range(n)) - undone
        failed = 0 in baked and masker not in baked
        return {node: "FAILED" if node == "t::b0" and failed else "PASSED" for node in nodes}

    return bugs, pytest


def test_a_bug_another_hides_with_every_bug_in_blames_the_bug_that_hides_it(monkeypatch) -> None:  # noqa: ANN001
    # pydantic-long40-1: pr_7827's test passed with the 40 bugs in, and the search built for the
    # other direction blamed whatever bug sat first in the chain, five rounds running.
    bugs, fake = _world(masker=5)
    monkeypatch.setattr(masking.docker_env, "pytest", fake)
    forward = {"f2p": 1, "f2p_failing_with_bugs": 0, "f2p_passing_when_fixed": 1}
    fine = {"f2p": 1, "f2p_failing_with_bugs": 1, "f2p_passing_when_fixed": 1}
    records = [forward, *[fine] * 7]
    assert masking.culprits("tag", bugs, [0], records) == [5]
    assert masking.fails_with("tag", bugs, 0, [5]) is True
    assert masking.fails_with("tag", bugs, 0, []) is False


def test_a_bug_that_does_not_fail_even_alone_is_its_own_culprit(monkeypatch) -> None:  # noqa: ANN001
    bugs = [{"patch": f"p{k}\n", "FAIL_TO_PASS": [f"t::b{k}"]} for k in range(4)]
    def pytest(_tag, _patch, nodes, reverse=False):  # noqa: ANN001, ANN202
        return dict.fromkeys(nodes, "PASSED")

    monkeypatch.setattr(masking.docker_env, "pytest", pytest)
    forward = {"f2p": 1, "f2p_failing_with_bugs": 0, "f2p_passing_when_fixed": 1}
    assert masking.culprits("tag", bugs, [0], [forward, forward, forward, forward]) == [0]


def test_the_direction_comes_from_the_record(monkeypatch) -> None:  # noqa: ANN001
    # backward (fails with the bugs in, does not pass fixed alone): the maskers of the fix
    bugs = [{"patch": f"p{k}\n", "FAIL_TO_PASS": [f"t::b{k}"]} for k in range(8)]

    def pytest(_tag, patch, nodes, reverse=False):  # noqa: ANN001, ANN202
        undone = {int(x[1:]) for x in patch.split()}
        ok = 0 in undone and 3 in undone
        return {node: "PASSED" if node != "t::b0" or ok else "FAILED" for node in nodes}

    monkeypatch.setattr(masking.docker_env, "pytest", pytest)
    backward = {"f2p": 1, "f2p_failing_with_bugs": 1, "f2p_passing_when_fixed": 0}
    fine = {"f2p": 1, "f2p_failing_with_bugs": 1, "f2p_passing_when_fixed": 1}
    assert masking.culprits("tag", bugs, [0], [backward, *[fine] * 7]) == [3]


def test_a_patch_that_does_not_apply_stops_the_search(monkeypatch) -> None:  # noqa: ANN001
    # pydantic-long40-1: undoing a bug the image did not hold gave {"<patch>": "ERROR"}, and
    # both questions read it as an answer ("does not pass", "fails").
    monkeypatch.setattr(masking.docker_env, "pytest",
                        lambda *_a, **_k: {"<patch>": "ERROR"})  # fmt: skip
    bugs = [{"patch": "p0\n", "FAIL_TO_PASS": ["t::a"]}, {"patch": "p1\n", "FAIL_TO_PASS": []}]
    with pytest.raises(ValueError, match="does not apply"):
        masking.passes_with("tag", bugs, 0, [1])
    with pytest.raises(ValueError, match="does not apply"):
        masking.fails_with("tag", bugs, 0, [1])


def test_validation_keeps_the_bugs_of_its_last_check(monkeypatch) -> None:  # noqa: ANN001
    # pydantic-long40-1: the fifth check failed, a fifth swap was made with no check after it,
    # and the chain was saved with the new bug beside the records of the one it replaced.
    validate = _load("adopt_validate", "validate.py")
    bug = {"instance_id": "r.b0", "patch": "p0\n", "FAIL_TO_PASS": ["t::a"], "PASS_TO_PASS": []}
    spares = [{**bug, "instance_id": f"r.s{k}"} for k in range(9)]
    chain = {"chain": "r-long", "image": "img", "bugs": [bug], "spares": spares}
    checks: list[str] = []

    def check(_chain, bugs):  # noqa: ANN001, ANN202
        checks.append(bugs[0]["instance_id"])
        return [{"instance_id": bugs[0]["instance_id"], "valid": False,
                 "PASS_TO_PASS_STAR": []}], [0]  # fmt: skip

    def swap(_chain, bugs, index, _tried):  # noqa: ANN001, ANN202
        bugs[index] = spares[len(checks)]
        return True

    monkeypatch.setattr(validate.docker_env, "pull", lambda _image: None)
    monkeypatch.setattr(validate, "check", check)
    monkeypatch.setattr(validate, "swap", swap)
    monkeypatch.setattr(validate.masking, "culprits", lambda *_a: [0])
    result = validate.validate(chain)
    assert len(checks) == validate.SWAPS + 1
    kept = [b["instance_id"] for b in result["bugs"]]
    assert kept == [r["instance_id"] for r in result["records"]]
    assert result["bugs"][0]["instance_id"] == checks[-1]
    assert not result["history"][-1][0].startswith("replace")  # no swap after the last check


def test_extra_spares_come_after_the_drawn_ones(monkeypatch) -> None:  # noqa: ANN001
    # The amendment of 2026-10-01: a chain it names tries its drawn spares first, then the extra.
    validate = _load("adopt_validate_extra", "validate.py")
    drawn = {"chain": "conan-io__conan-1", "spares": [{"instance_id": "a"}]}
    other = {"chain": "pygments__pygments-2", "spares": [{"instance_id": "b"}]}
    def spares(name: str) -> list[dict[str, str]]:
        return [{"instance_id": "x"}] if name == drawn["chain"] else []

    monkeypatch.setattr(validate.extra, "spares", spares)
    got = validate.with_extra([drawn, other])
    assert [s["instance_id"] for s in got[0]["spares"]] == ["a", "x"]
    assert [s["instance_id"] for s in got[1]["spares"]] == ["b"]
    assert [s["instance_id"] for s in drawn["spares"]] == ["a"]  # the drawn chain is not changed
