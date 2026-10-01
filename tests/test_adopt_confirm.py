"""The confirmation's verdict code (`benchmarks/adopt/confirm.py`): statistics, completeness,
exploration, guard blocks, the long-session rule, and the seal that gates held-out reading."""

from __future__ import annotations

import hashlib
import importlib.util
import json
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


confirm = _load("adopt_confirm", "confirm.py")
_purge()
SONNET = confirm.PHASE_MODEL["B"]


def use(name: str, uid: str, parent: str | None = None, **inp: str) -> dict:
    block = {"type": "tool_use", "id": uid, "name": name, "input": inp}
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": [block]}}


def result(uid: str, text: str, error: bool = True) -> dict:
    block = {"type": "tool_result", "tool_use_id": uid, "content": text, "is_error": error}
    return {"type": "user", "message": {"content": [block]}}


def write_stream(folder: pathlib.Path, k: int, items: list[dict]) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"stream-{k}.jsonl"
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    return path


def arm(folder: pathlib.Path, calls: list[dict], resolved: list[bool], model: str = SONNET,
        jev: float = 0.0) -> pathlib.Path:  # fmt: skip
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "row.json").write_text(json.dumps({"model": model, "jev_usd": jev, "calls": calls}),
                                     encoding="utf-8")  # fmt: skip
    bugs = [{"instance_id": f"b{i}", "resolved": r} for i, r in enumerate(resolved)]
    (folder / "grade.json").write_text(json.dumps({"resolved": sum(resolved), "bugs": bugs}),
                                       encoding="utf-8")  # fmt: skip
    return folder


def call(k: int, cost: float, **extra: object) -> dict:
    return {"request": k, "subtype": "success", "exit": 0, "cost_usd": cost, **extra}


def test_the_interval_is_seeded_and_holds_the_point() -> None:
    pairs = [(0.8, 1.0), (0.9, 1.0), (1.1, 1.0), (0.7, 1.0), (0.85, 1.0)]
    first = confirm.paired_interval(pairs, confirm.median_ratio)
    assert first == confirm.paired_interval(pairs, confirm.median_ratio)
    point, low, high = first
    assert point == pytest.approx(0.85) and low <= point <= high


def test_ratio_verdicts() -> None:
    assert confirm.ratio_verdict(0.8, 0.95) == "confirmed"
    assert confirm.ratio_verdict(0.8, 1.1) == "direction only, not confirmed"
    assert confirm.ratio_verdict(1.05, 1.2) == "not confirmed"


def test_success_holds_within_the_margin_and_is_undecided_with_a_task_missing() -> None:
    rows = [{"treat": {"resolved": 3}, "control": {"resolved": 5}},
            {"treat": {"resolved": 5}, "control": {"resolved": 5}}]  # fmt: skip
    assert confirm.success(rows, 2, [])["holds"] and not confirm.success(rows, 1, [])["holds"]
    assert confirm.success(rows, 2, ["lost-task"])["holds"] is None


def test_a_request_not_run_or_cut_makes_the_arm_incomplete_and_keeps_it_out_of_h2(
    tmp_path: pathlib.Path,
) -> None:
    full = arm(tmp_path / "t1" / "N", [call(1, 1.0), call(2, 1.0)], [True, True])
    cut = arm(tmp_path / "t1" / "Sm", [call(1, 0.5), {"request": 2, "status": "NOT RUN (cap)",
                                                     "cost_usd": 0.0}], [True, False])  # fmt: skip
    timed = arm(tmp_path / "t2" / "Sm", [call(1, 0.5), call(2, 1.5, exit=-9, subtype=None)],
                [True, False])  # fmt: skip
    for folder in (full, cut, timed):
        for k in (1, 2):
            write_stream(folder, k, [use("Read", f"r{k}")])
    arm(tmp_path / "t2" / "N", [call(1, 1.0), call(2, 1.0)], [True, True])
    rows, missing = confirm.pairs_of(["t1", "t2"], "Sm", "N", tmp_path, SONNET)
    assert missing == [] and not rows[0]["treat"]["complete"] and rows[0]["treat"]["ran"] == [1]
    out = confirm.cheaper(rows)
    assert out["verdict"] == "no data" and len(out["incomplete"]) == 2
    assert out["incomplete"][0] == {"task": "t1", "common_requests": [1], "treat_usd": 0.5,
                                    "control_usd": 1.0}  # fmt: skip


def test_an_arm_run_on_another_model_is_missing(tmp_path: pathlib.Path) -> None:
    arm(tmp_path / "t" / "N", [call(1, 1.0)], [True], model="claude-haiku-4-5-20251001")
    arm(tmp_path / "t" / "Sm", [call(1, 1.0)], [True])
    assert confirm.pairs_of(["t"], "Sm", "N", tmp_path, SONNET) == ([], ["t"])


def test_exploration_counts_the_main_thread_before_its_first_edit(tmp_path: pathlib.Path) -> None:
    sub = [use("Read", "s1", parent="t"), use("Edit", "s2", parent="t")]
    one = write_stream(tmp_path, 1, [use("Grep", "a"), use("Task", "t"), *sub, use("Read", "b"),
                                     use("Edit", "c"), use("Read", "d")])  # fmt: skip
    two = write_stream(tmp_path, 2, [use("Grep", "a"), use("Read", "b")])
    assert confirm.exploration(one) == 3  # Grep, Task, Read; the subagent's calls do not count
    assert confirm.exploration(two) == 2  # never edits: all of them


def test_guard_blocks_name_the_command_and_count_shell_calls(tmp_path: pathlib.Path) -> None:
    denial = "PreToolUse:Bash hook error: Command denied (the decision model flags it)"
    stream = write_stream(tmp_path, 3, [use("Bash", "x", command="rm -f scratch.txt"),
                                        result("x", denial), use("Bash", "y", command="ls"),
                                        result("y", "boom"), use("Read", "z")])  # fmt: skip
    found, shells = confirm.guard_blocks(stream, "task/Sm")
    assert shells == 2 and len(found) == 1
    assert found[0]["key"] == "task/Sm/stream-3/x"
    assert found[0]["input"] == {"command": "rm -f scratch.txt"}
    listed = {"type": "tool_result", "tool_use_id": "x", "is_error": True,
              "content": [{"type": "text", "text": denial}]}  # fmt: skip
    assert confirm.result_text(listed) == denial


def test_the_long_session_rule_compares_the_requests_both_arms_ran() -> None:
    def side(costs: dict[int, float], resolved: int) -> dict:
        return {"ran": sorted(costs), "request_cost": {**costs, 3: 0.0}, "jev": 0.0,
                "resolved": resolved, "complete": 3 in costs}  # fmt: skip

    ok = {"treat": side({1: 4.0, 2: 4.0}, 7), "control": side({1: 5.0, 2: 5.0}, 8)}
    assert confirm.long_session(ok)["holds"]
    # N cut at request 3 by a cap: its request 3 is left out of both sides
    cut = {"treat": side({1: 4.0, 2: 4.0, 3: 9.0}, 7), "control": side({1: 5.0, 2: 5.0}, 8)}
    assert confirm.long_session(cut)["cost_ratio"] == 0.8
    dearer = {"treat": side({1: 4.8, 2: 4.8}, 8), "control": side({1: 5.0, 2: 5.0}, 8)}
    assert not confirm.long_session(dearer)["holds"]
    fewer = {"treat": side({1: 3.0, 2: 3.0}, 6), "control": side({1: 5.0, 2: 5.0}, 8)}
    assert not confirm.long_session(fewer)["holds"]
    assert confirm.long_session(None)["holds"] is None


def seal_at(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    doc = tmp_path / "doc.md"
    doc.write_text("prereg\n", encoding="utf-8")
    monkeypatch.setattr(confirm, "REPO", tmp_path)
    manifest = {"doc.md": hashlib.sha256(b"prereg\n").hexdigest()}
    (tmp_path / "m.json").write_text(json.dumps(manifest), encoding="utf-8")
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    (tmp_path / "s.sha256").write_text(combined.hexdigest() + "\n", encoding="utf-8")
    monkeypatch.setattr(confirm, "MANIFEST", tmp_path / "m.json")
    monkeypatch.setattr(confirm, "SEAL", tmp_path / "s.sha256")
    monkeypatch.setattr(confirm, "REQUIRED", ("doc.md",))
    return doc


def test_the_seal_holds_only_while_the_sealed_files_are_unchanged(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_repo = confirm.REPO
    monkeypatch.setattr(confirm, "importlib", confirm.importlib)
    doc = seal_at(tmp_path, monkeypatch)
    (tmp_path / "benchmarks" / "candor").mkdir(parents=True)
    (tmp_path / "benchmarks" / "candor" / "seal.py").write_text(
        (real_repo / "benchmarks" / "candor" / "seal.py").read_text(encoding="utf-8"),
        encoding="utf-8")  # fmt: skip
    assert confirm.seal_holds()
    doc.write_text("prereg, changed after the seal\n", encoding="utf-8")
    assert not confirm.seal_holds()


def test_nothing_but_b_is_read_without_the_seal(monkeypatch: pytest.MonkeyPatch,
                                                tmp_path: pathlib.Path) -> None:  # fmt: skip
    monkeypatch.setattr(confirm, "SEAL", tmp_path / "missing.sha256")
    for argv in (["A"], ["C"], ["A", "--blocks"], ["C", "--blocks"]):
        with pytest.raises(SystemExit, match="not sealed"):
            confirm.main(argv)
    for bad in (["a"], ["blocks"], ["blocks", "A"]):
        with pytest.raises(SystemExit):  # argparse: not a phase
            confirm.main(bad)


def test_held_lists_come_from_the_sealed_selections() -> None:
    assert len(confirm.held("chains", valid_only=False)) == 8
    assert len(confirm.held("related", valid_only=False)) == 5
    assert len(confirm.held("singles")) == 26


def test_which_chains_are_valid_comes_from_the_summary_in_the_repository(monkeypatch) -> None:  # noqa: ANN001
    # The cache file is not sealed: a validation run after the seal must not change who counts.
    import validate

    monkeypatch.setattr(validate, "validated", lambda: {})  # the cache says nothing is valid
    summary = json.loads((ADOPT / "chains-validated-summary.json").read_text(encoding="utf-8"))
    names = confirm.held("chains", valid_only=False)
    assert confirm.held("chains") == [n for n in names if summary.get(n, {}).get("valid")]


def test_the_chains_margin_is_five_percent_of_their_bugs_and_at_least_one() -> None:
    assert confirm.margin(65) == 3 and confirm.margin(45) == 2 and confirm.margin(15) == 1
    assert confirm.margin(5) == 1


def test_memory_counts_prompt_and_touch_injections_apart(tmp_path: pathlib.Path) -> None:
    events = [{"event": "UserPromptSubmit", "shown": ["r1"], "chars": 100},
              {"event": "UserPromptSubmit", "shown": [], "chars": 0},
              {"event": "PostToolUse", "shown": ["r1", "r2"], "path": "a.py", "chars": 300},
              {"event": "PostToolUse", "shown": []},
              {"event": "Stop", "written": ["x"]}]  # fmt: skip
    (tmp_path / "memory.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n",
                                           encoding="utf-8")  # fmt: skip
    out = confirm.memory_log(tmp_path)
    assert (out["memory_prompts"], out["memory_injected"], out["memory_records"]) == (2, 1, 1)
    assert (out["memory_touch_given"], out["memory_touch_records"],
            out["memory_touch_chars"]) == (1, 2, 300)  # fmt: skip


def test_the_fail_to_pass_count_is_reported_beside_the_strict_one(tmp_path: pathlib.Path) -> None:
    # Phase B2: one PASS_TO_PASS test shared by every bug, broken once, left Sm 0/40 strict and
    # 26 by FAIL_TO_PASS. Both are reported; the strict one decides.
    folder = arm(tmp_path / "Sm", [call(1, 0.1), call(2, 0.1)], [False, False], model=SONNET)
    bugs = [{"instance_id": "b0", "resolved": False, "f2p_passed": 2, "f2p": 2, "p2p_broken": 1},
            {"instance_id": "b1", "resolved": False, "f2p_passed": 1, "f2p": 2, "p2p_broken": 1}]
    (folder / "grade.json").write_text(json.dumps({"resolved": 0, "bugs": bugs}), encoding="utf-8")
    got = confirm.arm_result(folder, SONNET)
    assert got is not None and got["resolved"] == 0 and got["f2p_resolved"] == 1
    rows = [{"treat": got, "control": {**got, "resolved": 2, "f2p_resolved": 2}}]
    out = confirm.success(rows, 1, [])
    assert out["treat"] == 0 and out["treat_f2p"] == 1 and out["control_f2p"] == 2


def _sealed_repo(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    doc = seal_at(tmp_path, monkeypatch)
    (tmp_path / "benchmarks" / "candor").mkdir(parents=True)
    (tmp_path / "benchmarks" / "candor" / "seal.py").write_text(
        (ADOPT.parents[1] / "benchmarks" / "candor" / "seal.py").read_text(encoding="utf-8"),
        encoding="utf-8")  # fmt: skip
    return doc


def test_the_seal_fails_when_it_does_not_name_what_decides(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _sealed_repo(tmp_path, monkeypatch)
    assert confirm.seal_holds()
    monkeypatch.setattr(confirm, "REQUIRED", ("doc.md", "benchmarks/adopt/confirm.py"))
    assert not confirm.seal_holds()  # the manifest does not name the verdicts' code


def test_a_module_added_after_the_seal_breaks_it(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    _sealed_repo(tmp_path, monkeypatch)
    (tmp_path / "benchmarks" / "adopt").mkdir(parents=True)
    assert confirm.seal_holds()
    (tmp_path / "benchmarks" / "adopt" / "statistics.py").write_text("x = 1", encoding="utf-8")
    assert not confirm.seal_holds()


def test_only_bugs_of_requests_that_ran_count(tmp_path: pathlib.Path) -> None:
    # Request 2 hit the chain cap; the final diff fixed its bug while working on request 1.
    calls = [call(1, 0.5), {"request": 2, "status": "NOT RUN (cap)", "cost_usd": 0.0}]
    folder = arm(tmp_path / "N", calls, [True, True])
    got = confirm.arm_result(folder, SONNET)
    assert got is not None and got["resolved"] == 1 and got["f2p_resolved"] == 1
    assert not got["complete"]


def test_a_sanchopanza_arm_counts_only_on_the_frozen_commit(tmp_path: pathlib.Path) -> None:
    folder = arm(tmp_path / "Sm", [call(1, 0.5)], [True])
    assert confirm.arm_result(folder, SONNET, "abc") is None  # no frozen install recorded
    row = json.loads((folder / "row.json").read_text(encoding="utf-8"))
    row["sanchopanza"] = {"exe": "x", "frozen": {"commit": "abc"}}
    (folder / "row.json").write_text(json.dumps(row), encoding="utf-8")
    assert confirm.arm_result(folder, SONNET, "abc") is not None
    assert confirm.arm_result(folder, SONNET, "other") is None
    control = arm(tmp_path / "N", [call(1, 0.5)], [True])
    assert confirm.arm_result(control, SONNET, "abc") is not None  # Claude Code alone: no install


def test_a_hypothesis_with_no_data_is_undecided_not_false() -> None:
    assert confirm.decided(True, "no data") is None
    assert confirm.decided(None, "confirmed") is None
    assert confirm.decided(True, "confirmed") is True
    assert confirm.decided(True, "direction only, not confirmed") is False
