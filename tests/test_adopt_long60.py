"""long60 chains (`benchmarks/adopt/long.py`, `perbug.py`): the draw that mixes real and synthetic
bugs, the control token that only the first prompt carries, the callbacks, the per-bug grade with
its separate guard, and the validation's drop rule. No Docker, no network, no model."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import random
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest

ADOPT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "adopt"
sys.path.append(str(ADOPT))


def _load(name: str, file: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ADOPT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("adopt_run", "run.py")
import long  # noqa: E402
import perbug  # noqa: E402

TOKEN = "c0ffee12"


def bug(i: int, path: str = "", issue: str = "") -> dict[str, Any]:
    path = path or f"pkg/m{i}.py"
    text = (f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -10,3 +10,3 @@\n a\n-b{i}\n+c{i}\n d\n")  # fmt: skip
    return {"instance_id": f"o__r.abc.pr_{i}", "patch": text, "FAIL_TO_PASS": [f"t.py::f{i}"],
            "PASS_TO_PASS": ["t.py::g"], "PASS_TO_PASS_STAR": ["t.py::g"],
            "problem_statement": issue or f"Issue number {i} breaks things.",
            "source": "pr_mirror", "origin": "real", "image_name": "img"}  # fmt: skip


def chain_of(size: int, token: str = TOKEN) -> dict[str, Any]:
    return {"chain": "r-long60-1", "repo": "r", "image": "img", "tag": "tag", "split": "dev",
            "kind": "long", "grader": "per_bug", "size": size, "seed": long.SEED60,
            "token": token, "bugs": [bug(i) for i in range(1, size + 1)],
            "guard": ["t.py::g", "t.py::h"]}  # fmt: skip


# ---- the prompts and the control token ----------------------------------------------------------


def test_sixty_bugs_give_sixty_two_requests_with_callbacks_after_45_and_60() -> None:
    asks = long.requests(chain_of(60), run.PROMPT)
    assert len(asks) == 62
    kinds = [(r, a["kind"]) for r, a in enumerate(asks, start=1) if a["kind"] == "callback"]
    assert kinds == [(46, "callback"), (62, "callback")]
    assert long.callbacks(60) == [(45, [3, 7, 12]), (60, [5, 9, 15])]
    assert "bugs 3, 7 and 12" in asks[45]["prompt"] and "recall-1.md" in asks[45]["prompt"]
    assert [a["bug"] for a in asks if a["kind"] == "bug"] == list(range(1, 61))
    assert asks[10]["prompt"].startswith("Bug 11 of this session.")


def test_the_token_is_in_the_first_prompt_only() -> None:
    asks = long.requests(chain_of(60), run.PROMPT)
    assert f"`Ref: {TOKEN}`" in asks[0]["prompt"] and "changes/<n>.md" in asks[0]["prompt"]
    assert asks[0]["prompt"].index("Ref:") < asks[0]["prompt"].index("Bug 1 of this session.")
    assert not [r for r, a in enumerate(asks[1:], start=2) if TOKEN in a["prompt"]]
    assert all("Ref:" not in a["prompt"] for a in asks[1:])


def test_the_token_avoids_every_text_of_the_chain() -> None:
    first = long.token_for("r-long60-1")
    assert len(first) == 8 and int(first, 16) >= 0
    texts = (f"an issue that quotes {first} by chance",)
    other = long.token_for("r-long60-1", texts)
    assert other != first and not any(other in t for t in texts)
    assert long.token_for("r-long60-1", (), index=1) != first
    assert long.token_for("r-long60-2") != first  # per chain


def test_a_drawn_chain_never_carries_its_token_in_its_texts() -> None:
    bugs = [bug(i) for i in range(1, 6)]
    token = long.token_for("x", long.texts_of(bugs))
    asks = long.requests({**chain_of(5, token), "bugs": bugs}, run.PROMPT)
    assert [a for a in asks if token in a["prompt"]] == [asks[0]]


def test_token_absent_reads_every_file_of_a_working_copy(tmp_path: pathlib.Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert perbug.token_absent(tmp_path, TOKEN) == []
    (tmp_path / "pkg" / "b.lock").write_bytes(b"\x00hash " + TOKEN.encode())
    assert perbug.token_absent(tmp_path, TOKEN) == ["pkg/b.lock"]


def test_other_chains_get_the_prompts_they_always_had() -> None:
    plain = {"chain": "c", "bugs": [bug(1), bug(2)]}
    asks = run.requests_of(plain)
    assert [a["prompt"] for a in asks] == [run.PROMPT.format(issue=b["problem_statement"].strip())
                                           for b in plain["bugs"]]  # fmt: skip
    assert run.requests_of(chain_of(3))[0]["prompt"].startswith("Before the first bug")


def test_an_old_chain_keeps_its_digest_and_a_long60_one_hashes_guard_and_token() -> None:
    plain = {"image": "i", "tag": "t", "bugs": [bug(1)], "split": "dev"}
    import hashlib

    body = {k: plain.get(k) for k in ("image", "tag", "bugs")}
    expected = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    assert run.chain_digest(plain) == expected
    one = chain_of(3)
    assert run.chain_digest(one) != run.chain_digest({**one, "token": "00000000"})
    assert run.chain_digest(one) != run.chain_digest({**one, "guard": []})


def test_the_driver_sends_the_sequence_and_snapshots_each_request(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(run, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    monkeypatch.setattr(run.docker_env, "export", lambda tag, work: "base")
    diffs = iter(range(100))
    monkeypatch.setattr(run.docker_env, "agent_diff", lambda work, base: f"diff {next(diffs)}")
    monkeypatch.setattr(run, "reserve", lambda *_a: True)
    monkeypatch.setattr(run, "settle", lambda *_a: None)
    monkeypatch.setattr(run, "claude_version", lambda: "x")
    sent: list[str] = []

    def fake(cmd, **kwargs):  # noqa: ANN001, ANN003, ANN202
        sent.append(kwargs["input"].decode() if kwargs.get("input") else cmd[2])
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run.subprocess, "run", fake)
    chain = chain_of(8)
    run.one_chain(chain, "N", "m", 10.0, tmp_path / "key")
    assert sent == [a["prompt"] for a in long.requests(chain, run.PROMPT)]
    evidence = tmp_path / "runs" / "r-long60-1" / "N"
    assert len(sent) == 10 and (evidence / "diff-10.patch").exists()
    row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
    assert [c["instance_id"] for c in row["calls"]][6:] == [
        "callback-1", "o__r.abc.pr_7", "o__r.abc.pr_8", "callback-2"]  # fmt: skip
    assert long.callbacks(8) == [(6, [1, 2]), (8, [1, 2])]


# ---- the draw ------------------------------------------------------------------------------------


@pytest.fixture
def plain(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(long.chains, "usable", lambda row: True)
    monkeypatch.setattr(long.related, "normalized", lambda row: row)


def test_real_bugs_first_then_synthetic_ones_fill_the_chain(plain) -> None:  # noqa: ANN001
    real = [bug(i) for i in range(1, 5)]
    synth = [{**bug(i), "instance_id": f"o__r.abc.lm_rewrite__x{i}"} for i in range(10, 20)]
    bugs, spares = long.draw_mixed(real, synth, 8, 3, random.Random(1))
    assert len(bugs) == 8 and len(spares) == 3
    assert sum(b["origin"] == "real" for b in bugs) == 4
    assert {b["source"] for b in bugs} == {"pr_mirror", "lm_rewrite"}
    assert all(s["origin"] == "synthetic" for s in spares)


def test_bugs_sharing_a_failing_test_or_an_overlapping_hunk_never_go_together(plain) -> None:  # noqa: ANN001
    same_test = {**bug(2), "FAIL_TO_PASS": ["t.py::f1"]}
    same_hunk = {**bug(3, path="pkg/m1.py")}
    for other in (same_test, same_hunk):
        bugs, spares = long.draw_mixed([bug(1), other], [], 1, 5, random.Random(0))
        assert len([*bugs, *spares]) == 1


def test_source_names_pr_mirror_and_each_synthetic_kind() -> None:
    assert long.source_of("conan-io__conan.86f29e13.pr_15044") == "pr_mirror"
    assert long.source_of("x__y.1.func_pm_remove_cond__ab12") == "func_pm_remove_cond"
    assert long.source_of("x__y.1.lm_rewrite__zz") == "lm_rewrite"


def test_the_long40_plan_and_draw_are_untouched() -> None:
    assert [n for _, n, _ in long.PLAN] == ["pydantic__pydantic-long40-1",
                                             "conan-io__conan-long40-1"]  # fmt: skip
    assert (long.SEED, long.SIZE, long.SPARES) == (20261003, 40, 12)
    built = [s for _, _, s in long.PLAN60]
    assert built.count("gate") == 2 and built.count("dev") == 4
    assert len({r for r, _, _ in long.PLAN60}) >= 3 and len(long.RESERVE60) >= 12


# ---- the grade -----------------------------------------------------------------------------------


def new_file(path: str, *lines: str) -> str:
    body = "".join(f"+{line}\n" for line in lines)
    return (f"diff --git a/{path} b/{path}\nnew file mode 100644\nindex 0000000..1111111\n"
            f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}")  # fmt: skip


def test_the_token_is_ok_wrong_or_missing_per_bug() -> None:
    patch = (new_file("changes/1.md", f"Ref: {TOKEN}", "A typo.")
             + new_file("changes/2.md", "Ref: deadbeef", "x")
             + new_file("changes/4.md", f"Ref: {TOKEN}\r"))  # fmt: skip
    status = perbug.token_status(patch, 4, TOKEN)
    assert status["per_bug"] == {1: "ok", 2: "wrong", 3: "missing", 4: "ok"}
    assert (status["ok"], status["wrong"], status["missing"]) == (2, 1, 1)


def test_each_bug_is_resolved_by_its_own_tests_and_regressions_stand_apart(monkeypatch) -> None:  # noqa: ANN001
    chain = chain_of(3)
    outcome = {"t.py::f1": "PASSED", "t.py::f2": "FAILED", "t.py::f3": "PASSED",
               "t.py::g": "FAILED", "t.py::h": "PASSED"}  # fmt: skip
    monkeypatch.setattr(perbug.docker_env, "pytest", lambda *a, **k: outcome)
    g = perbug.grade(chain, "patch")
    assert g["resolved"] == 2 and g["regressions"] == ["t.py::g"]
    assert [b["resolved"] for b in g["bugs"]] == [True, False, True]
    assert g["strict_resolved"] == 0  # B2's rule: t.py::g is in every bug's PASS_TO_PASS*


def test_a_patch_that_does_not_apply_resolves_nothing(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(perbug.docker_env, "pytest", lambda *a, **k: {"<patch>": "ERROR"})
    g = perbug.grade(chain_of(2), "bad")
    assert g["resolved"] == 0 and not g["patch_applied"] and g["regressions"] == []


def section(path: str, tag: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-a\n+{tag}\n"


def test_callbacks_are_scored_against_the_diff_snapshots() -> None:
    chain = chain_of(60)
    asks = long.requests(chain, run.PROMPT)
    snaps, cumulative = [], {}
    for ask in asks:
        if ask["kind"] == "bug":
            n = ask["bug"]
            cumulative = {**cumulative, f"pkg/m{n}.py": section(f"pkg/m{n}.py", "fix")}
            if n == 7:  # bug 7 also touched a file an earlier bug changed
                cumulative = {**cumulative, "pkg/m3.py": section("pkg/m3.py", "again")}
            cumulative = {**cumulative, f"changes/{n}.md": new_file(f"changes/{n}.md", "Ref: x")}
        else:
            answer = (["bug 3: pkg/m3.py", "bug 7: `pkg/m7.py`, pkg/m3.py", "bug 12: none"]
                      if ask["callback"] == 1 else ["- bug 5: ./pkg/m5.py"])  # fmt: skip
            path = f"changes/recall-{ask['callback']}.md"
            cumulative = {**cumulative, path: new_file(path, *answer)}
        snaps.append("".join(cumulative.values()))
    scored = perbug.score_callbacks(chain, snaps, run.PROMPT)
    first, second = scored
    assert first["per_bug"][3]["jaccard"] == 1.0 and first["per_bug"][7]["jaccard"] == 1.0
    assert first["per_bug"][7]["truth"] == ["pkg/m3.py", "pkg/m7.py"]
    assert first["per_bug"][12]["jaccard"] == 0.0  # said none, changed pkg/m12.py
    assert second["per_bug"][5]["jaccard"] == 1.0 and second["per_bug"][9]["answer"] is None
    assert second["mean"] == round(1 / 3, 3) and first["written"]


def test_recall_lines_take_common_shapes() -> None:
    got = perbug.recall_answer("Bug 3: a/b.py, c/d.py\n* bug #7 - none\nnoise\nbug 9: setup.cfg")
    assert got == {3: {"a/b.py", "c/d.py"}, 7: set(), 9: {"setup.cfg"}}


# ---- the validation's drop rule ------------------------------------------------------------------


def test_a_bug_whose_tests_another_fix_flips_is_dropped_and_culprits_too(monkeypatch) -> None:  # noqa: ANN001
    bugs = [bug(i) for i in range(1, 5)]

    def fake(tag, patch, nodes, reverse=False, keep_collecting=False):  # noqa: ANN001, ANN202
        everything = {f"t.py::f{i}": "FAILED" for i in range(1, 5)} | {"t.py::g": "PASSED"}
        if not reverse:
            return everything
        if patch == perbug.joined(bugs):
            return {k: "PASSED" for k in everything}
        fixed = int(patch.split("+c", 1)[1][0])
        out = {**everything, f"t.py::f{fixed}": "PASSED"}
        if fixed == 1:
            out["t.py::f2"] = "PASSED"  # fixing bug 1 also makes bug 2's test pass
        if fixed == 3:
            out["t.py::f3"] = "FAILED"  # bug 3's tests need another fix too
        return out

    monkeypatch.setattr(perbug.docker_env, "pytest", fake)
    monkeypatch.setattr(perbug.masking, "culprits", lambda tag, b, bad, rec, keep: [3])
    result = perbug.check("tag", bugs)
    assert set(result["drop"]) == {1, 3}  # bug 2 (flipped), bug 4 (bug 3's culprit)
    assert result["guard"] == ["t.py::g"]
    assert [r["valid"] for r in result["records"]] == [True, False, True, False]


def test_a_dropped_slot_takes_the_next_spare_that_fits() -> None:
    bugs = [bug(1), bug(2), bug(3)]
    spares = [{**bug(4), "FAIL_TO_PASS": ["t.py::f1"]}, bug(5), bug(6)]
    tried = {b["instance_id"] for b in bugs}
    out = perbug.refill(bugs, {1}, spares, tried)
    assert [b["instance_id"] for b in out] == ["o__r.abc.pr_1", "o__r.abc.pr_5", "o__r.abc.pr_3"]
    assert perbug.refill(out, {0, 2}, [], tried) == [out[1]]  # no spare left: the slot goes


def test_files_changed_during_a_request_leave_changes_out() -> None:
    before = section("a.py", "1") + new_file("changes/1.md", "Ref: x")
    after = section("a.py", "2") + section("b.py", "1") + new_file("changes/2.md", "Ref: x")
    assert perbug.changed_during(before, after) == {"a.py", "b.py"}
