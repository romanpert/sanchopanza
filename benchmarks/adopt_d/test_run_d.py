"""Free tests of phase D's runner (no session, no Docker, no API, no spend):

Run: .venv/Scripts/python.exe -m pytest benchmarks/adopt_d/test_run_d.py -q

The instance names here are made up, so no drawn or spare id is named in this repository; the
recorded sessions read for (g) are phase A's and the development probe's, already excluded.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_d  # noqa: E402
from run_d import run  # noqa: E402

CACHE = Path.home() / ".cache" / "sanchopanza" / "adopt"
NAME = "owner__repo-1"
ROW = {"instance_id": NAME, "repo": "owner/repo", "image": "img:latest",
       "problem_statement": "issue"}  # fmt: skip


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """singles-d, the working copies, the keys and Claude Code's projects, all under tmp."""
    monkeypatch.setattr(run_d, "RUNS_D", tmp_path / "singles-d")
    monkeypatch.setattr(run, "WORK", tmp_path / "work")
    monkeypatch.setattr(run, "KEYS", tmp_path / "keys")
    monkeypatch.setattr(run, "CLAUDE_PROJECTS", tmp_path / "projects")
    return tmp_path


def _row(evidence: Path, cost: float = 0.3, jev: float = 0.0, status: str = "") -> None:
    evidence.mkdir(parents=True, exist_ok=True)
    call = {"cost_usd": cost, "subtype": "success", **({"status": status} if status else {})}
    (evidence / "row.json").write_text(json.dumps({"calls": [call], "jev_usd": jev}), "utf-8")


# ---- paths per repetition ------------------------------------------------------------------------


def test_paths_carry_the_repetition(roots: Path) -> None:
    assert run_d.evidence_of(NAME, 2, "S") == roots / "singles-d" / NAME / "r2" / "S"
    assert run_d.work_of(NAME, 3, "N") == roots / "work" / f"{NAME}-r3-N"
    source = roots / "key.txt"
    source.write_text("k", encoding="utf-8")
    key = run.arm_keyfile(source, run_d.key_name(NAME, 2), "S")
    assert key == roots / "keys" / f"{NAME}-r2-S.key"
    run.drop_arm_keys()
    # Every repetition and arm has its own working copy, and so its own Claude Code folder.
    works = {run_d.work_of(NAME, r, a) for r in range(1, 4) for a in run_d.ARMS}
    assert len({run.projects_dir(w) for w in works}) == 6


def test_one_keeps_phase_as_refusals(roots: Path) -> None:
    _row(run_d.evidence_of(NAME, 1, "N"))
    run_d.one(ROW, "N", 1, roots / "key")  # a row: done before, nothing happens
    run_d.evidence_of(NAME, 2, "N").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no row.json"):
        run_d.one(ROW, "N", 2, roots / "key")
    projects = run.projects_dir(run_d.work_of(NAME, 3, "N"))
    projects.mkdir(parents=True)
    (projects / "earlier.jsonl").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="earlier sessions"):
        run_d.one(ROW, "N", 3, roots / "key")


# ---- the hold and the ledger ---------------------------------------------------------------------


def test_the_hold_is_six_sessions_caps() -> None:
    hold, cap, sealed_cap = run_d.HOLD_USD, run_d.CALL_CAP_USD, run.CALL_CAP_USD
    assert hold == pytest.approx(9.00) and cap == pytest.approx(1.50) and sealed_cap == cap


def _no_docker(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    monkeypatch.setattr(run_d.docker_env, "disk_free_gb", lambda *a: 100.0)
    monkeypatch.setattr(run_d.docker_env, "pull", lambda image: calls.append("pull"))
    monkeypatch.setattr(run_d.docker_env, "drop", lambda *tags: calls.append("drop"))
    monkeypatch.setattr(run_d, "grade_instance", lambda name: calls.append("grade"))


def test_an_instance_starts_only_if_its_hold_fits(roots: Path, monkeypatch) -> None:
    calls: list[str] = []
    _no_docker(monkeypatch, calls)
    monkeypatch.setattr(run_d, "ledger", lambda: 100.0)
    monkeypatch.setattr(run_d, "run_pair",
                        lambda row, rep, arms, key, inputs: calls.append(f"r{rep}"))  # fmt: skip
    monkeypatch.setitem(run._ledger, "reserved", 0.0)
    with pytest.raises(run_d.Stop, match="do not fit"):
        run_d.run_instance(ROW, roots / "key", 108.99, {})
    assert calls == [] and run._ledger["reserved"] == 0.0
    run_d.run_instance(ROW, roots / "key", 109.00, {})  # exactly room for 9.00
    assert calls == ["pull", "r1", "r2", "r3", "grade", "drop"]
    assert run._ledger["reserved"] == 0.0  # released after the instance


def test_the_hold_is_released_when_a_pair_stops_the_batch(roots: Path, monkeypatch) -> None:
    calls: list[str] = []
    _no_docker(monkeypatch, calls)
    monkeypatch.setattr(run_d, "ledger", lambda: 0.0)
    monkeypatch.setitem(run._ledger, "reserved", 0.0)

    def limited(row: dict, rep: int, arms: list, key: Path, inputs: dict) -> None:
        raise run_d.Stop("usage limit")

    monkeypatch.setattr(run_d, "run_pair", limited)
    with pytest.raises(run_d.Stop):
        run_d.run_instance(ROW, roots / "key", 50.0, {})
    assert calls == ["pull", "grade", "drop"] and run._ledger["reserved"] == 0.0


def test_the_hold_is_released_on_any_exception(roots: Path, monkeypatch) -> None:
    calls: list[str] = []
    _no_docker(monkeypatch, calls)
    monkeypatch.setattr(run_d, "ledger", lambda: 0.0)
    monkeypatch.setitem(run._ledger, "reserved", 0.0)

    def broken(image: str) -> None:
        raise RuntimeError("pull failed")

    monkeypatch.setattr(run_d.docker_env, "pull", broken)
    with pytest.raises(RuntimeError, match="pull failed"):
        run_d.run_instance(ROW, roots / "key", 50.0, {})
    assert run._ledger["reserved"] == 0.0


def test_spent_d_counts_rows_jev_set_asides_and_crashes(roots: Path) -> None:
    base = roots / "singles-d"
    _row(base / NAME / "r1" / "N", 0.40)
    _row(base / NAME / "r1" / "S", 0.50, jev=0.02)
    _row(base / f"{NAME}-limit1" / "r1" / "S", 0.10, status=run_d.NOT_RUN_ERROR)
    crashed = base / NAME / "r2" / "S"
    crashed.mkdir(parents=True)
    (crashed / "stream-1.jsonl").write_text('{"type": "system"}\n', encoding="utf-8")
    (base / NAME / "r2" / "N").mkdir(parents=True)  # never reached claude: nothing spent
    assert run_d.spent_d() == pytest.approx(0.40 + 0.52 + 0.10 + run_d.CALL_CAP_USD)


def test_spent_dev_counts_rows_and_abandoned_attempts(tmp_path: Path) -> None:
    _row(tmp_path / "a" / "x" / "S", 0.40, jev=0.01)
    aside = tmp_path / "a" / "x" / "N-abandoned-1"
    aside.mkdir(parents=True)
    (aside / "abandoned.json").write_text(json.dumps({"charged_usd": 1.5, "jev_usd": 0.02}))
    assert run_d.spent_dev((tmp_path / "a", tmp_path / "none")) == pytest.approx(1.93)


def test_the_need_probe_is_in_the_ledger(tmp_path: Path, monkeypatch) -> None:
    assert [r.name for r in run_d.DEV_ROOTS] == ["dev-alwaysload", "dev-need", "dev-nudge"]
    need = tmp_path / "dev-need"
    _row(need / "x" / "S", 0.70, jev=0.01)
    (need / "y" / "S-abandoned-1").mkdir(parents=True)
    (need / "y" / "S-abandoned-1" / "abandoned.json").write_text(json.dumps({"charged_usd": 1.5}))
    monkeypatch.setattr(run_d, "DEV_ROOTS", (tmp_path / "dev-alwaysload", need))
    assert run_d.spent_dev(run_d.DEV_ROOTS) == pytest.approx(2.21)


def test_the_ceiling_needs_its_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_d, "CEILING_BASE_USD", None)
    with pytest.raises(SystemExit):
        run_d.ceiling()
    monkeypatch.setattr(run_d, "CEILING_BASE_USD", 200.0)
    assert run_d.ceiling() == pytest.approx(310.0)


# ---- error results, missing pairs, resume --------------------------------------------------------


def test_an_error_result_sets_the_instance_aside_and_keeps_missing_pairs(roots: Path) -> None:
    ev = run_d.evidence_of
    _row(ev(NAME, 1, "N"))
    _row(ev(NAME, 1, "S"))
    _row(ev(NAME, 2, "N"))
    _row(ev(NAME, 2, "S"), status=run_d.NOT_RUN_ERROR)
    ev(NAME, 3, "S").mkdir(parents=True)  # started (its stream), no row: missing for good
    (ev(NAME, 3, "S") / "stream-1.jsonl").write_text("{}\n", encoding="utf-8")
    _row(ev(NAME, 3, "N"))
    projects = run.projects_dir(run_d.work_of(NAME, 2, "S"))
    projects.mkdir(parents=True)
    (projects / "limited.jsonl").write_text("{}", encoding="utf-8")
    aside = run_d.set_aside_limit(NAME)
    assert aside is not None and aside.name == f"{NAME}-limit1"
    assert (aside / "r2" / "S" / "claude-projects" / "limited.jsonl").exists()
    assert not projects.exists()
    assert {p.relative_to(aside).as_posix() for p in aside.glob("r*/*") if p.is_dir()} == {
        "r1/N", "r1/S", "r2/N", "r2/S"}  # fmt: skip
    assert run_d.todo(NAME) == [(1, ["N", "S"]), (2, ["N", "S"])]  # r3 is missing, not rerun
    assert run_d.missing_reps(NAME) == [3]
    assert run_d.set_aside_limit(NAME) is None  # nothing left to set aside


def test_a_pair_with_an_error_result_stops_the_batch(roots: Path, monkeypatch) -> None:
    def fake_one(row: dict, arm: str, rep: int, key: Path) -> None:
        _row(run_d.evidence_of(NAME, rep, arm),
             status=run_d.NOT_RUN_ERROR if arm == "S" else "")  # fmt: skip

    monkeypatch.setattr(run_d, "one", fake_one)
    monkeypatch.setattr(run_d, "ledger", lambda: 0.0)
    monkeypatch.setattr(run, "decider_probe", lambda key: run_d.DECIDER)
    monkeypatch.setattr(run_d, "pair_refusal", lambda inputs: None)
    with pytest.raises(run_d.Stop, match="usage limit"):
        run_d.run_pair(ROW, 1, ["N", "S"], roots / "key", {})
    run.drop_arm_keys()
    assert (roots / "singles-d" / f"{NAME}-limit1" / "r1" / "S" / "row.json").exists()
    assert run_d.todo(NAME)[0] == (1, ["N", "S"])


def _patch(name: str, rep: int, arm: str, text: str, graded: bool = False) -> Path:
    evidence = run_d.evidence_of(name, rep, arm)
    _row(evidence)
    (evidence / "final.patch").write_text(text, encoding="utf-8")
    if graded:
        (evidence / "grade.json").write_text('{"resolved": true}', encoding="utf-8")
    return evidence


def _no_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_d.subprocess, "run", lambda *a, **k: pytest.fail("harness started"))
    monkeypatch.setattr(run_d.docker_env, "pull", lambda image: pytest.fail("image pulled"))
    monkeypatch.setattr(run_d.docker_env, "drop", lambda *tags: pytest.fail("image dropped"))


def test_an_empty_diff_is_graded_not_resolved_without_the_harness(roots: Path, monkeypatch) -> None:
    """swebench drops an empty prediction and writes no report: the session is a loss, not a
    missing grade, so its pair stays complete (prereg, "Measures")."""
    _no_harness(monkeypatch)
    empty = _patch(NAME, 1, "N", "")
    _patch(NAME, 1, "S", "diff --git a/x b/x\n")
    assert run_d.ungraded(NAME) == [1, 1] and run_d.needs_harness(NAME)
    assert run_d.grade_arm(NAME, empty, "N-r1") is False
    assert json.loads((empty / "grade.json").read_text(encoding="utf-8")) == {
        "resolved": False, "reason": "empty diff",
        "run_swe_sha256": run_d.guard_d.file_sha(run_d.singles_run.SWE / "run_swe.py")}  # fmt: skip
    assert not (empty / "preds.jsonl").exists()
    assert run_d.ungraded(NAME) == [1]  # the non-empty diff still waits for the harness
    (run_d.evidence_of(NAME, 1, "S") / "grade.json").write_text('{"resolved": true}')
    assert run_d.ungraded(NAME) == [] and not run_d.needs_harness(NAME)


def test_a_whitespace_diff_still_goes_to_the_harness(roots: Path) -> None:
    """Only the harness's own empty test (`model_patch in ["", None]`) skips it."""
    _patch(NAME, 1, "N", "\n")
    assert run_d.needs_harness(NAME)


def test_only_empty_diffs_waiting_pull_no_image(roots: Path, monkeypatch) -> None:
    _no_harness(monkeypatch)
    for rep in range(1, run_d.REPS + 1):
        for arm in run_d.ARMS:
            _patch(NAME, rep, arm, "diff --git a/x b/x\n", graded=True)
    (run_d.evidence_of(NAME, 2, "S") / "grade.json").unlink()
    (run_d.evidence_of(NAME, 2, "S") / "final.patch").write_text("", encoding="utf-8")
    run_d.run_instance(ROW, roots / "key", 0.0, {})  # nothing to run, one empty diff to grade
    assert json.loads((run_d.evidence_of(NAME, 2, "S") / "grade.json").read_text())["reason"] == (
        "empty diff")  # fmt: skip
    (run_d.evidence_of(NAME, 2, "S") / "grade.json").unlink()
    monkeypatch.setattr(run_d, "seal_refusal", lambda: None)
    monkeypatch.setattr(run_d, "plan_rows", lambda: [ROW])
    assert run_d.main(["grade"]) == 0  # the free `grade` action: no image either
    assert (run_d.evidence_of(NAME, 2, "S") / "grade.json").exists()


def test_graded_sessions_are_not_graded_again(roots: Path) -> None:
    _patch(NAME, 1, "N", "diff --git a/x b/x\n", graded=True)
    _patch(NAME, 1, "S", "", graded=True)
    assert run_d.ungraded(NAME) == [] and not run_d.needs_harness(NAME)


# ---- evidence (g) on recorded sessions -----------------------------------------------------------


def _first(paths: list[Path]) -> Path:
    found = [p for p in paths if (p / "transcript.jsonl").exists()]
    if not found:
        pytest.skip("recorded sessions not on this machine")
    return found[0]


def test_g_fails_on_phase_a_where_find_was_deferred() -> None:
    evidence = _first([CACHE / "singles" / "django__django-11211" / "S",
                       *sorted((CACHE / "singles").glob("*/S"))])  # fmt: skip
    why = run_d.find_hidden(evidence)
    assert why and not run_d.find_visible(evidence)
    if evidence == CACHE / "singles" / "django__django-11211" / "S":
        assert why.startswith("deferred")  # in the init tools, but named by the delta


def test_g_passes_on_the_development_probe_with_always_load() -> None:
    evidence = _first([CACHE / "dev-alwaysload" / "django__django-15104" / "S",
                       *sorted((CACHE / "dev-nudge").glob("*/S"))])  # fmt: skip
    assert run_d.find_hidden(evidence) == ""


def test_g_needs_every_part(tmp_path: Path) -> None:
    init = {"type": "system", "subtype": "init", "tools": ["Bash", run_d.FIND_TOOL]}
    (tmp_path / "stream-1.jsonl").write_text(json.dumps(init) + "\n", encoding="utf-8")
    assert run_d.find_hidden(tmp_path) == "transcript not copied"
    delta = {"type": "attachment", "attachment": {"type": "deferred_tools_delta",
                                                  "addedNames": ["Monitor"]}}  # fmt: skip
    (tmp_path / "transcript.jsonl").write_text(json.dumps(delta) + "\n", encoding="utf-8")
    assert run_d.find_hidden(tmp_path) == "no copied mcp.json"
    server = {"mcpServers": {"sanchopanza": {"command": "x"}}}
    (tmp_path / "mcp.json").write_text(json.dumps(server), encoding="utf-8")
    assert "alwaysLoad" in run_d.find_hidden(tmp_path)
    server["mcpServers"]["sanchopanza"]["alwaysLoad"] = True
    (tmp_path / "mcp.json").write_text(json.dumps(server), encoding="utf-8")
    assert run_d.find_visible(tmp_path)
    init["tools"] = ["Bash"]
    (tmp_path / "stream-1.jsonl").write_text(json.dumps(init) + "\n", encoding="utf-8")
    assert run_d.find_hidden(tmp_path) == "not in the init line's tools"


# ---- refusals and the seal -----------------------------------------------------------------------


def _no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "claude_version", lambda: pytest.fail("claude was started"))
    monkeypatch.setattr(run, "decider_probe", lambda key: pytest.fail("the probe was started"))


def test_refused_while_the_constants_are_unset(monkeypatch, tmp_path: Path) -> None:
    _no_process(monkeypatch)
    monkeypatch.setattr(run_d, "D_COMMIT", "")
    assert "D_COMMIT" in run_d.d_refusal(tmp_path / "key")
    monkeypatch.setattr(run_d, "D_COMMIT", "0" * 40)
    monkeypatch.setattr(run_d, "CEILING_BASE_USD", None)
    assert "CEILING_BASE_USD" in run_d.d_refusal(tmp_path / "key")


def test_refused_while_unsealed(monkeypatch, tmp_path: Path) -> None:
    _no_process(monkeypatch)
    monkeypatch.setattr(run_d, "D_COMMIT", "0" * 40)
    monkeypatch.setattr(run_d, "CEILING_BASE_USD", 100.0)
    monkeypatch.setattr(run_d, "PREREG", tmp_path)  # no prereg.sha256 there
    assert "not sealed" in run_d.d_refusal(tmp_path / "key")


def _sealed_repo(repo: Path) -> tuple[Path, Path]:
    """A repository with every required file, sealed the way seal.py seals."""
    for path in run_d.REQUIRED:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(f"{path}\n", encoding="utf-8")
    digest = run_d._seal_module().digest
    manifest = {p: digest(repo / p) for p in run_d.REQUIRED}
    folder = repo / "docs" / "results" / "2026-10-03-adopt-d"
    (folder / "prereg.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    (folder / "prereg.sha256").write_text(combined.hexdigest() + "\n", encoding="utf-8")
    phase_a = repo / "a-manifest.json"
    phase_a.write_text(json.dumps({k: v for k, v in manifest.items()
                                   if k.startswith("benchmarks/adopt/")}),
                       encoding="utf-8")  # fmt: skip
    return folder, phase_a


def test_the_seal_holds_and_breaks(tmp_path: Path) -> None:
    folder, phase_a = _sealed_repo(tmp_path)
    assert run_d.seal_refusal(folder, tmp_path, phase_a) is None
    extra = tmp_path / "benchmarks" / "adopt_d" / "later.py"
    extra.write_text("x", encoding="utf-8")
    assert "does not name" in run_d.seal_refusal(folder, tmp_path, phase_a)
    extra.unlink()
    (tmp_path / "benchmarks" / "adopt" / "run.py").write_text("changed", encoding="utf-8")
    assert "changed since the seal" in run_d.seal_refusal(folder, tmp_path, phase_a)


def test_the_seal_needs_phase_as_files_unchanged(tmp_path: Path) -> None:
    folder, phase_a = _sealed_repo(tmp_path)
    sealed_a = json.loads(phase_a.read_text(encoding="utf-8"))
    phase_a.write_text(json.dumps({**sealed_a, "benchmarks/adopt/run.py": "0" * 64}))
    assert "not phase A's" in run_d.seal_refusal(folder, tmp_path, phase_a)


def test_d_runs_the_frozen_copy_of_7a39a1f() -> None:
    """The delegation fix (7a39a1f): D's copy, the only one run_d lets phase A's modules run."""
    assert run_d.D_COMMIT == "7a39a1f0d4ff8e9cf5c99046ee0aa818ffe955d9"
    assert run_d.FROZEN.name == "7a39a1f0d4ff-jev-mcp"
    assert run.SANCHO == run_d.D_EXE
    assert Path(run_d.hook_env.SANCHO) == run_d.D_EXE


def test_phase_d_is_not_sealed_yet() -> None:
    """Today: no seal, so the runner and the verdicts refuse (this test goes once it is)."""
    if (run_d.PREREG / "prereg.sha256").exists():
        pytest.skip("sealed")
    assert run_d.seal_refusal() is not None


# ---- the plan ------------------------------------------------------------------------------------


def test_instances_read_validate_d_output_in_table_order(tmp_path: Path) -> None:
    path = tmp_path / "v.json"
    selected = [{"instance_id": "b__b-2", "stratum": "hard", "image": "i"},
                {"instance_id": "a__a-1", "stratum": "general-easy"}]  # fmt: skip
    path.write_text(json.dumps({"complete": True, "selected": selected}), encoding="utf-8")
    assert [i["instance_id"] for i in run_d.instances(path)] == ["b__b-2", "a__a-1"]
    assert run_d.instances(path)[0]["stratum"] == "hard"
    path.write_text(json.dumps({"complete": False, "next": "a__a-1"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="not complete"):
        run_d.instances(path)
    path.write_text(json.dumps(["c__c-3"]), encoding="utf-8")
    assert run_d.instances(path) == [{"instance_id": "c__c-3", "stratum": None, "image": None}]


def test_plan_rows_refuses_an_image_other_than_validated(monkeypatch) -> None:
    monkeypatch.setattr(run_d.singles_run, "rows", lambda: {NAME: ROW})
    monkeypatch.setattr(run_d, "instances", lambda: [{"instance_id": NAME, "image": "other"}])
    with pytest.raises(SystemExit, match="validated other"):
        run_d.plan_rows()
    monkeypatch.setattr(run_d, "instances", lambda: [{"instance_id": NAME, "image": "img:latest"}])
    assert run_d.plan_rows() == [ROW]


def test_sealed_but_another_frozen_copy_is_refused(monkeypatch, tmp_path: Path) -> None:
    _no_process(monkeypatch)
    monkeypatch.setattr(run_d, "D_COMMIT", "0" * 40)
    monkeypatch.setattr(run_d, "CEILING_BASE_USD", 100.0)
    monkeypatch.setattr(run_d, "seal_refusal", lambda: None)
    monkeypatch.setattr(run, "frozen_stamp", lambda: {"commit": "1" * 40, "extras": ["jev", "mcp"]})
    assert "freeze it" in run_d.d_refusal(tmp_path / "key")
    monkeypatch.setattr(run, "frozen_stamp", lambda: {"commit": "0" * 40, "extras": ["jev"]})
    assert "without ['mcp']" in run_d.d_refusal(tmp_path / "key")
    monkeypatch.setattr(run, "frozen_stamp", lambda: {"commit": "0" * 40, "extras": ["jev", "mcp"]})
    assert "phase D runs claude" in run_d.d_refusal(tmp_path / "key", model="claude-sonnet-5-5")


# ---- review fixes: order, inputs, lock, error kinds, treatment stops, logs -----------------------


def test_order_is_seeded_and_spreads_the_strata() -> None:
    items = [{"instance_id": f"e{k}", "stratum": "general-easy"} for k in range(10)]
    items += [{"instance_id": f"m{k}", "stratum": "general-medium"} for k in range(10)]
    items += [{"instance_id": f"h{k}", "stratum": "hard"} for k in range(6)]
    first, again = run_d.order(items), run_d.order(items)
    assert first == again and sorted(map(str, first)) == sorted(map(str, items))
    hard = [k for k, i in enumerate(first) if i["stratum"] == "hard"]
    assert max(b - a for a, b in zip(hard, hard[1:], strict=False)) <= 5
    assert hard[0] <= 4 and hard[-1] >= 21  # neither bunched at the start nor at the end
    assert run_d.order(items, seed=1) != first


def test_a_pair_does_not_start_once_an_input_changed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_d, "CLAUDE_HOME", tmp_path / "home")
    (tmp_path / "home" / "rules").mkdir(parents=True)
    (tmp_path / "home" / "CLAUDE.md").write_text("a", encoding="utf-8")
    monkeypatch.setattr(run_d, "seal_refusal", lambda: None)
    recorded = run_d.unsealed_inputs()
    assert run_d.pair_refusal(recorded) is None
    (tmp_path / "home" / "rules" / "new.md").write_text("b", encoding="utf-8")
    assert "rules/new.md" in run_d.pair_refusal(recorded)
    monkeypatch.setattr(run_d, "seal_refusal", lambda: "phase D is not sealed")
    with pytest.raises(run_d.Stop, match="not sealed"):
        run_d.run_pair(ROW, 1, ["N", "S"], tmp_path / "key", recorded)


def test_one_batch_at_a_time(roots: Path) -> None:
    lock = run_d.take_lock()
    with pytest.raises(SystemExit, match="another batch"):
        run_d.take_lock()  # this process holds it
    lock.write_text("999999999", encoding="utf-8")  # a process that is gone
    assert run_d.take_lock() == lock
    lock.unlink()


def _fake_claude(result: dict) -> list[str]:
    lines = [{"type": "system", "subtype": "init", "session_id": "s1"},
             {"type": "result", "session_id": "s1", **result}]  # fmt: skip
    body = "".join(f"print({json.dumps(json.dumps(x))})\n" for x in lines)
    return [sys.executable, "-c", body]


@pytest.mark.parametrize(("result", "status"), [
    ({"subtype": "success", "is_error": True, "api_error_status": 429,
      "result": "You've hit your weekly limit"}, run_d.NOT_RUN_ERROR),
    ({"subtype": "success", "is_error": True, "result": "Claude AI usage limit reached"},
     run_d.NOT_RUN_ERROR),
    ({"subtype": "success", "is_error": True, "result": "API Error: 500 overloaded"},
     run_d.ERROR_OTHER),
    ({"subtype": "success", "is_error": False, "total_cost_usd": 0.2, "result": "done"}, None),
])  # fmt: skip
def test_only_a_usage_limit_is_not_run(tmp_path: Path, monkeypatch, result, status) -> None:
    monkeypatch.setitem(run._ledger, "reserved", 0.0)
    call = run_d.session_call(_fake_claude(result), tmp_path, dict(run_d.os.environ), "p",
                              tmp_path)  # fmt: skip
    assert call.get("status") == status and run._ledger["reserved"] == 0.0
    ran = run_d.confirm.ran(call)
    assert ran is (status != run_d.NOT_RUN_ERROR)  # any other error result counts as run


def test_sessions_that_never_started_are_run_again(roots: Path) -> None:
    ev = run_d.evidence_of
    _row(ev(NAME, 1, "N"))
    _row(ev(NAME, 1, "S"), status=run_d.NOT_RUN_HARNESS)  # claude -p never started
    assert run_d.state(NAME, 1, "S") == "rerun"
    ev(NAME, 2, "N").mkdir(parents=True)  # a folder, no stream, no row (an export that failed)
    assert run_d.state(NAME, 2, "N") == "rerun"
    _row(ev(NAME, 3, "N"), status=run_d.ERROR_OTHER)
    assert run_d.state(NAME, 3, "N") == "done"  # ran: graded, never run again
    aside = run_d.set_aside_limit(NAME)
    assert aside is not None
    assert {p.relative_to(aside).as_posix() for p in aside.glob("r*/*")} == {
        "r1/N", "r1/S", "r2/N", "r3/N"}  # fmt: skip
    assert run_d.todo(NAME) == [(1, ["N", "S"]), (2, ["N", "S"]), (3, ["N", "S"])]


def test_an_error_in_a_missing_repetition_still_sets_aside(roots: Path) -> None:
    ev = run_d.evidence_of
    ev(NAME, 1, "N").mkdir(parents=True)
    (ev(NAME, 1, "N") / "stream-1.jsonl").write_text("{}\n", encoding="utf-8")  # missing
    _row(ev(NAME, 1, "S"), status=run_d.NOT_RUN_ERROR)
    _row(ev(NAME, 2, "N"))
    _row(ev(NAME, 2, "S"))
    aside = run_d.set_aside_limit(NAME)
    assert aside is not None and (aside / "r1" / "S" / "row.json").exists()
    assert (aside / "r2" / "N").exists() and ev(NAME, 1, "N").exists()  # missing stays
    assert run_d.missing_reps(NAME) == [1] and run_d.set_aside_limit(NAME) is None


def test_an_other_error_result_stops_the_batch_unset_aside(roots: Path, monkeypatch) -> None:
    def fake_one(row: dict, arm: str, rep: int, key: Path) -> None:
        _row(run_d.evidence_of(NAME, rep, arm), status=run_d.ERROR_OTHER if arm == "N" else "")

    monkeypatch.setattr(run_d, "one", fake_one)
    monkeypatch.setattr(run, "decider_probe", lambda key: run_d.DECIDER)
    monkeypatch.setattr(run_d, "pair_refusal", lambda inputs: None)
    monkeypatch.setattr(run_d, "ledger", lambda: 0.0)
    with pytest.raises(run_d.Stop, match="not a usage limit"):
        run_d.run_pair(ROW, 1, ["N", "S"], roots / "key", {})
    run.drop_arm_keys()
    assert run_d.todo(NAME) == [(2, ["N", "S"]), (3, ["N", "S"])]  # r1 stays, graded later


def _criteria(monkeypatch, outcomes: dict[str, dict[str, bool]]) -> None:
    import confirm_d

    good = dict.fromkeys(("commit", "a", "b", "c", "d", "e", "f", "g"), True)
    monkeypatch.setattr(confirm_d, "criteria",
                        lambda e: {**good, **outcomes.get(e.parent.parent.name, {})})  # fmt: skip


def test_a_systemic_criterion_stops_at_once(roots: Path, monkeypatch) -> None:
    _row(run_d.evidence_of(NAME, 1, "S"))
    _criteria(monkeypatch, {NAME: {"d": False}})
    assert "['d']" in run_d.treatment_stop(NAME, 1)
    _criteria(monkeypatch, {NAME: {"g": False}})
    assert "['g']" in run_d.treatment_stop(NAME, 1)


def test_f_stops_only_in_two_of_the_last_three(roots: Path, monkeypatch) -> None:
    names = ["a__a-1", "b__b-2", "c__c-3", "d__d-4"]
    for k, name in enumerate(names):
        evidence = run_d.evidence_of(name, 1, "S")
        _row(evidence)
        row = json.loads((evidence / "row.json").read_text(encoding="utf-8"))
        (evidence / "row.json").write_text(json.dumps({**row, "started": 100 + k}), "utf-8")
    _criteria(monkeypatch, {"a__a-1": {"f": False}, "d__d-4": {"f": False}})
    assert run_d.treatment_stop("d__d-4", 1) == ""  # a is outside the last three
    _criteria(monkeypatch, {"c__c-3": {"f": False}, "d__d-4": {"f": False}})
    assert "2 of the last 3" in run_d.treatment_stop("d__d-4", 1)
    assert run_d.treatment_stop("b__b-2", 1) == ""  # (f) passes here: only excluded elsewhere


def test_the_log_never_says_a_grade(roots: Path, monkeypatch, capsys) -> None:
    _patch(NAME, 1, "N", "")
    monkeypatch.setattr(run_d.singles_run, "SWE", roots)
    run_d.grade_instance(NAME)
    out = capsys.readouterr().out
    assert f"graded {NAME} r1" in out and "False" not in out and "resolved" not in out


def test_g_reads_only_the_added_names(tmp_path: Path) -> None:
    init = {"type": "system", "subtype": "init", "tools": [run_d.FIND_TOOL]}
    (tmp_path / "stream-1.jsonl").write_text(json.dumps(init) + "\n", encoding="utf-8")
    server = {"mcpServers": {"sanchopanza": {"alwaysLoad": True}}}
    (tmp_path / "mcp.json").write_text(json.dumps(server), encoding="utf-8")
    removed = {"attachment": {"type": "deferred_tools_delta", "addedNames": ["Monitor"],
                              "removedNames": [run_d.FIND_TOOL]}}  # fmt: skip
    (tmp_path / "transcript.jsonl").write_text(json.dumps(removed) + "\n", encoding="utf-8")
    assert run_d.find_visible(tmp_path)
    added = {"attachment": {"type": "deferred_tools_delta", "addedLines": [run_d.FIND_TOOL]}}
    (tmp_path / "transcript.jsonl").write_text(json.dumps(added) + "\n", encoding="utf-8")
    assert run_d.find_hidden(tmp_path).startswith("deferred")


def test_selftest_names_the_fail_to_pass_tests() -> None:
    import selftest_d

    django = selftest_d.test_args("django/django", ["test_x (app.tests.Case)", "a docstring"], "")
    assert django == ["app.tests.Case.test_x"]
    nodes = ["tests/test_a.py::test_b"]
    assert selftest_d.test_args("sphinx-doc/sphinx", nodes, "") == nodes
    patch = "+++ b/sympy/core/tests/test_x.py\n"
    assert selftest_d.test_args("sympy/sympy", ["test_y", "test_z"], patch) == [
        "sympy/core/tests/test_x.py", "-k", "test_y or test_z"]  # fmt: skip
