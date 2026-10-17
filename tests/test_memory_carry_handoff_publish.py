"""F2's public outputs (`benchmarks/memory_carry/handoff_publish.py`): rows keep numbers and flags
only, and H's cost takes the handoff turn's own cost when the resumed turn reports the session's
running total."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
pub = bench_module(ROOT / "benchmarks" / "memory_carry", "handoff_publish")

TOKENS = {"input": 2, "output": 627, "cache_read": 23413, "cache_write": 299}


def h_row() -> dict:
    return {"scene": "h_batch", "model": "sonnet", "arm": "H", "repeat": 1,
            "folder": "C:/somewhere/w16/r2/t00-b", "kept_all": True, "cost": 0.198253,
            "given": ["a", "b"], "native_after_1": [], "stderr": "private",
            "sessions": [{"tag": "session-1", "cost": 0.060688, "final": "the agent's words",
                          "init": {"session_id": "abc", "version": "2.1.287",
                                   "model": "claude-sonnet-5-5", "mcp": {"x": "connected"}},
                          "native": ["C:/somewhere/memory/x.md"]},
                         {"tag": "session-2", "cost": 0.0647244}],
            "handoff": {"cost": 0.0728406, "tokens": TOKENS, "chars": 900,
                        "text": "secret plan", "names": {"C": True, "D": True},
                        "init": {"session_id": "abc"}}}  # fmt: skip


def test_public_rows_keep_numbers_and_flags_only() -> None:
    row = pub.public_row(h_row())
    text = json.dumps(row)
    for private in ("C:/somewhere", "the agent's words", "secret plan", "abc", "private",
                    "connected"):  # fmt: skip
        assert private not in text
    assert row["folder"] == "t00-b" and row["given"] == 2 and row["native_after_1"] == 0
    assert row["sessions"][0]["init"]["version"] == "2.1.287"
    assert row["sessions"][0]["native"] == 1 and row["handoff"]["chars"] == 900


def test_h_cost_takes_the_handoff_turn_s_own_cost() -> None:
    # Measured on F2 (Sonnet 5.5, h_batch r1): session 1 0.060688, the resumed turn reported
    # 0.0728406, its own tokens price to 0.0121526 at Claude Code's rates.
    cost = pub.handoff_cost
    assert cost.priced(TOKENS, "sonnet") == pytest.approx(0.0728406 - 0.060688, abs=1e-9)
    got = cost.own_row(h_row())
    assert got["handoff"]["cost"] == pytest.approx(0.0121526, abs=1e-9)
    assert got["handoff"]["cost_reported_total"] == 0.0728406
    assert got["handoff"]["cost_source"] == cost.RUNNING
    assert got["cost"] == pytest.approx(0.198253 - 0.060688)
    assert cost.own_row(got) == got  # already at its own cost
    n0 = {**h_row(), "arm": "N0"}
    assert cost.own_row(n0) == n0
    assert pub.public_row(h_row())["handoff"]["cost"] == pytest.approx(0.0121526, abs=1e-9)


def w17_row(arm: str, kept: bool) -> dict:
    return {"scene": "h_batch", "model": "sonnet", "arm": arm, "repeat": 3, "line": "bare",
            "scope": "user", "call_cap": 0.5, "folder": "C:/somewhere/w18/r1/t00-c",
            "kept_all": kept, "task_pass": kept, "fact_pass": kept, "decision_pass": kept,
            "intact_pass": True, "tests_pass": True, "cost": 0.12, "jev_usd": 0.0002,
            "sendbacks_other_rule": 0, "given": ["UserPromptSubmit:abc-001"] if arm == "S"
            else [], "native_after_1": [], "hook_starts": 2 if arm == "S" else 0,
            "handoff": {},
            "sessions": [{"tag": "session-1", "cost": 0.06, "seconds": 30.0,
                          "init": {"session_id": "abc", "skill_names": ["sanchopanza-code"],
                                   "memory_auto": "C:/somewhere/memory/"}},
                         {"tag": "session-2", "cost": 0.06, "seconds": 31.0,
                          "touched": []}]}  # fmt: skip


def test_w17_rows_keep_the_stratum_and_the_send_backs() -> None:
    row = pub.public_row(w17_row("S", True))
    text = json.dumps(row)
    for private in ("C:/somewhere", "abc", "skill_names", "memory_auto"):
        assert private not in text
    assert row["line"] == "bare" and row["scope"] == "user" and row["call_cap"] == 0.5
    assert row["sendbacks_other_rule"] == 0 and row["given"] == 1 and "handoff" not in row


def test_w17_runs_are_analysed_by_their_own_sealed_analysis() -> None:
    rows = [w17_row("S", True), w17_row("N0", False)]
    got = pub.analysis(rows, "w17-sonnet", None)
    assert got == pub.handoff_pairs.analyse(rows, "sonnet", None, pub.planned("w17-sonnet"))
    assert got["strata"]["bare"]["kept_all"] == {"N0": 0, "S": 1}
    assert pub.analysis([pub.public_row(r) for r in rows], "w17-sonnet", None) == got


def test_w17_tables_must_match_the_night_in_every_field() -> None:
    table = {"verdict": "x", "cost_median_usd": {"S": 1.0}, "cost_ratio_median": 1.0}
    other = {**table, "cost_median_usd": {"S": 2.0}}
    assert pub.same_as_night(other, table, "f2-sonnet")  # F2: H's handoff turn re-costed
    assert not pub.same_as_night(other, table, "w17-sonnet")
    assert pub.same_as_night(table, table, "w17-sonnet")


def test_runs_default_to_f2_and_take_the_named_ones() -> None:
    assert pub.runs_of([]) == ("f2-pilot", "f2-sonnet", "f2-opus")
    assert pub.runs_of(["w17-sonnet"]) == ("w17-sonnet",)
    with pytest.raises(SystemExit):
        pub.runs_of(["w17-nope"])


def test_costs_keep_the_runs_published_from_another_lot_folder() -> None:
    # W17's Sonnet run and its Opus redo live in different lot folders: publishing one must not
    # drop the other's entry from costs.json, and the lot's total is over both.
    old = {"w17-sonnet": {"spent_usd": 11.182309}, "lot": {"spent_usd": 11.1823}}
    new = {"w17-opus": {"spent_usd": 21.315415}}
    got = pub.merged_costs(old, new)
    assert got == {"w17-sonnet": {"spent_usd": 11.182309}, "w17-opus": {"spent_usd": 21.315415},
                   "lot": {"spent_usd": 32.4977}}  # fmt: skip
    again = pub.merged_costs(got, {"w17-sonnet": {"spent_usd": 11.182309}})
    assert again == got and list(again) == list(got)
    assert pub.merged_costs({}, new) == {**new, "lot": {"spent_usd": 21.3154}}


def test_costs_refuse_another_lot_s_runs_or_an_unknown_run() -> None:
    w17 = {"w17-opus": {"spent_usd": 21.315415}}
    with pytest.raises(SystemExit, match="mix the lots f2, w17"):
        pub.merged_costs({"f2-sonnet": {"spent_usd": 30.0}, "lot": {"spent_usd": 30.0}}, w17)
    with pytest.raises(SystemExit, match="w17-nope"):
        pub.merged_costs({"w17-nope": {"spent_usd": 1.0}}, w17)


def lot_folder(tmp_path: Path, run: str, night_ok: bool = True) -> Path:
    """A lot folder holding one W17 run: its rows, a preflight line in its ledger and the night's
    table (the sealed analysis of those rows, or a changed one when `night_ok` is False)."""
    model = pub.handoff.RUNS[run]["model"]
    rows = [{**w17_row("S", True), "model": model}, {**w17_row("N0", False), "model": model}]
    root = tmp_path / run.split("-")[1]
    (root / run).mkdir(parents=True)
    (root / run / "f2.json").write_text(json.dumps(rows), encoding="utf-8")
    pub.handoff.book(root / run, "preflight", 0.000012, "jev preflight")
    table = pub.analysis(rows, run, root / run)
    table = table if night_ok else {**table, "verdict": "another"}
    (root / f"{run}-table.json").write_text(json.dumps(table), encoding="utf-8")
    return root


def test_publishing_two_lot_folders_into_one_results_folder(tmp_path: Path) -> None:
    # W17: the Sonnet run from its folder, then the Opus redo from its own, into one folder.
    dest = tmp_path / "results"
    sonnet = lot_folder(tmp_path, "w17-sonnet", night_ok=False)
    opus = lot_folder(tmp_path, "w17-opus")
    assert pub.main([str(sonnet), str(dest), "w17-sonnet"]) == 1  # its night's table differs
    assert pub.main([str(opus), str(dest), "w17-opus"]) == 0  # only this call's run is checked
    costs = json.loads((dest / "costs.json").read_text(encoding="utf-8"))
    assert list(costs) == ["w17-sonnet", "w17-opus", "lot"]
    assert costs["w17-sonnet"]["same_as_the_night"] is False
    assert costs["w17-opus"]["same_as_the_night"] is True
    spent = [costs[r]["spent_usd"] for r in ("w17-sonnet", "w17-opus")]
    assert spent == [pytest.approx(0.240412), pytest.approx(0.240412)]
    assert costs["lot"]["spent_usd"] == round(sum(spent), 4)
    for name in ("rows-w17-sonnet.json", "w17-sonnet-table.json", "rows-w17-opus.json",
                 "w17-opus-table.json"):  # fmt: skip
        assert (dest / name).exists()


def test_publishing_refuses_a_results_folder_of_another_lot_before_writing(
        tmp_path: Path) -> None:  # fmt: skip
    dest = tmp_path / "results"
    dest.mkdir()
    f2 = {"f2-sonnet": {"spent_usd": 30.0}, "lot": {"spent_usd": 30.0}}
    (dest / "costs.json").write_text(json.dumps(f2), encoding="utf-8")
    with pytest.raises(SystemExit, match="mix the lots"):
        pub.main([str(lot_folder(tmp_path, "w17-opus")), str(dest), "w17-opus"])
    assert sorted(p.name for p in dest.iterdir()) == ["costs.json"]
    assert json.loads((dest / "costs.json").read_text(encoding="utf-8")) == f2


def test_turn_own_reads_each_kind_of_report() -> None:
    cost = pub.handoff_cost
    own = cost.priced(TOKENS, "sonnet")
    assert cost.turn_own(0.06 + own, 0.06, TOKENS, "sonnet") == (pytest.approx(own),
                                                                  cost.RUNNING)  # fmt: skip
    assert cost.turn_own(own, 0.06, TOKENS, "sonnet") == (own, cost.OWN)
    assert cost.turn_own(0.5, 0.06, TOKENS, "sonnet") == (pytest.approx(own), cost.PRICED)
    assert cost.turn_own(0.5, 0.06, None, "sonnet") == (0.5, cost.OWN)


def test_the_nudge_names_its_running_reading_after_session_2() -> None:
    # The nudge resumes session 2: its running reading has its own label. H's label stays the
    # string F2's published rows carry, so republishing F2 gives the same bytes.
    cost = pub.handoff_cost
    own = cost.priced(TOKENS, "sonnet")
    assert cost.RUNNING == "running total minus session 1"
    assert cost.RUNNING_S2 == "running total minus session 2"
    got = cost.turn_own(0.04 + own, 0.04, TOKENS, "sonnet", cost.RUNNING_S2)
    assert got == (pytest.approx(own), cost.RUNNING_S2)
    assert cost.turn_own(own, 0.04, TOKENS, "sonnet", cost.RUNNING_S2) == (own, cost.OWN)


# ---- the equal-work lot ---------------------------------------------------------------------

EW_PRIVATE = ("C:/somewhere", "sid-2", "abc", "skill_names", "memory_auto", "started",
              "resumed", "1792241133", "a private error", "private stderr",
              "the agent's reply", "pytest's own output")  # fmt: skip


def ew_row(arm: str, nudged: bool, kept: bool, repeat: int = 1) -> dict:
    """An equal-work row: N0 nudged after a session 2 that left step 2 undone, or S' not."""
    checks = {"tests_pass": True, "task_pass": not nudged, "fact_pass": not nudged,
              "decision_pass": not nudged, "intact_pass": True, "kept_all": not nudged}  # fmt: skip
    push = {"tag": "nudge", "returncode": 0, "subtype": "success", "cost": 0.0276,
            "cost_reported": True, "cost_reported_total": 0.068, "cost_source":
            "running total minus session 1", "resumed": "sid-2", "context_carried": True,
            "same_session": True, "first_prompt": 23617, "last_prompt": 24723,
            "tokens": {"input": 4, "output": 1183, "cache_read": 46719, "cache_write": 1617},
            "seconds": 20.1, "started": 1792241133.17, "turns": 2, "tools": 1, "touched": [],
            "subagents": 0, "timeout": False, "session_starts": [], "tree_kept": True,
            "init": {"model": "claude-sonnet-5-5", "version": "2.1.287", "session_id": "sid-2",
                     "memory_auto": "C:/somewhere/memory/", "skill_names": ["x"]},
            "first_request": {"input": 2, "cache_read": 23104, "cache_write": 511},
            "session_2_last_request": {"input": 2, "cache_read": 22397, "cache_write": 707},
            "chars": 901, "error": "a private error", "stderr": "private stderr",
            "text": "the agent's reply"} if nudged else {}  # fmt: skip
    base = w17_row(arm, kept)
    return {**base, "repeat": repeat, "line": "named" if repeat < 3 else "bare",
            "call_cap": 0.25, "folder": "C:/somewhere/w20/r1/t00-a", "kept_all": kept,
            "task_pass": kept, "fact_pass": kept, "decision_pass": kept,
            "checks_s2": {**checks, "output": "pytest's own output"},
            "kept_all_s2": checks["kept_all"], "nudged": nudged, "nudge": push,
            "cost": 0.12 + (0.0276 if nudged else 0.0)}  # fmt: skip


def ew_rows() -> list[dict]:
    return [ew_row("S", False, True, 1), ew_row("N0", True, False, 1),
            ew_row("S", False, True, 3), ew_row("N0", True, False, 3)]  # fmt: skip


def test_ew_rows_keep_the_nudge_s_numbers_and_flags_only() -> None:
    n0 = pub.public_row(ew_row("N0", True, False))
    text = json.dumps(n0)
    for private in EW_PRIVATE:
        assert private not in text
    assert n0["checks_s2"]["task_pass"] is False and n0["kept_all_s2"] is False
    assert list(n0["checks_s2"]) == ["tests_pass", "task_pass", "fact_pass", "decision_pass",
                                     "intact_pass", "kept_all"]  # fmt: skip
    assert n0["nudged"] is True and n0["nudge"]["cost"] == 0.0276
    assert n0["nudge"]["cost_source"] == "running total minus session 1"  # as recorded
    assert n0["nudge"]["init"] == {**dict.fromkeys(pub.INIT_KEYS), "model": "claude-sonnet-5-5",
                                   "version": "2.1.287"}  # fmt: skip
    assert n0["nudge"]["first_request"]["cache_read"] == 23104 and n0["nudge"]["tree_kept"]
    s = pub.public_row(ew_row("S", False, True))
    assert s["nudged"] is False and s["nudge"] == {} and s["kept_all_s2"] is True
    assert "nudge" not in pub.public_row(w17_row("S", True))  # W17's rows unchanged


def test_ew_runs_are_analysed_by_their_own_sealed_reading() -> None:
    rows = ew_rows()
    got = pub.analysis(rows, "ew-sonnet", None)
    assert got == pub.handoff_ew.analyse(rows, None, pub.planned("ew-sonnet"))
    assert got["reading"] == "equal work (R3)" and got["nudges"]["N0"]["nudged"] == 2
    assert pub.analysis([pub.public_row(r) for r in rows], "ew-sonnet", None) == got
    assert not pub.same_as_night({**got, "cost_median_usd": {}}, got, "ew-sonnet")


PUBLISHED = {"2026-10-16-memory-f2": ("f2-pilot", "f2-sonnet", "f2-opus"),
             "2026-10-16-memory-w17": ("w17-sonnet", "w17-opus"),
             "2026-10-17-memory-equal-work": ("ew-sonnet",)}  # fmt: skip


@pytest.mark.parametrize("folder,run", [(f, r) for f, runs in PUBLISHED.items() for r in runs])
def test_each_published_table_is_its_sealed_reading_of_the_published_rows(
        folder: str, run: str) -> None:  # fmt: skip
    # The publisher as it stands reproduces, byte for byte, every table already published.
    results = ROOT / "docs" / "results" / folder
    rows = json.loads((results / f"rows-{run}.json").read_text(encoding="utf-8"))
    text = json.dumps(pub.analysis(rows, run, None), indent=1, ensure_ascii=False) + "\n"
    assert text.encode("utf-8") == (results / f"{run}-table.json").read_bytes()


def test_the_ew_reading_refuses_a_run_of_another_model(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = {**pub.handoff.RUNS, "ew-sonnet": {**pub.handoff.RUNS["ew-sonnet"], "model": "opus"}}
    monkeypatch.setattr(pub.handoff, "RUNS", runs)
    with pytest.raises(SystemExit, match="sonnet only"):
        pub.analysis(ew_rows(), "ew-sonnet", None)


def ew_folder(tmp_path: Path) -> Path:
    root = tmp_path / "mem-ew"
    (root / "ew-sonnet").mkdir(parents=True)
    rows = ew_rows()
    (root / "ew-sonnet" / "f2.json").write_text(json.dumps(rows), encoding="utf-8")
    pub.handoff.book(root / "ew-sonnet", "preflight", 0.000012, "jev preflight")
    table = pub.analysis(rows, "ew-sonnet", root / "ew-sonnet")
    (root / "ew-sonnet-table.json").write_text(json.dumps(table, ensure_ascii=False),
                                               encoding="utf-8")  # fmt: skip
    return root


def test_publishing_the_ew_lot_twice_gives_the_same_bytes(tmp_path: Path) -> None:
    root, dest = ew_folder(tmp_path), tmp_path / "results"
    names = ("rows-ew-sonnet.json", "ew-sonnet-table.json", "costs.json")
    assert pub.main([str(root), str(dest), "ew-sonnet"]) == 0
    first = {n: (dest / n).read_bytes() for n in names}
    assert pub.main([str(root), str(dest), "ew-sonnet"]) == 0
    assert {n: (dest / n).read_bytes() for n in names} == first
    costs = json.loads(first["costs.json"])
    assert list(costs) == ["ew-sonnet", "lot"]
    assert costs["ew-sonnet"]["same_as_the_night"] is True
    assert costs["ew-sonnet"]["table_from_public_rows"] is True
    assert costs["ew-sonnet"]["spent_usd"] == pytest.approx(4 * 0.1202 + 2 * 0.0276 + 0.000012)
    text = first["rows-ew-sonnet.json"].decode("utf-8")
    for private in EW_PRIVATE:
        assert private not in text


def test_an_ew_results_folder_refuses_another_lot_s_run(tmp_path: Path) -> None:
    dest = tmp_path / "results"
    assert pub.main([str(ew_folder(tmp_path)), str(dest), "ew-sonnet"]) == 0
    with pytest.raises(SystemExit, match="mix the lots ew, w17"):
        pub.main([str(lot_folder(tmp_path, "w17-opus")), str(dest), "w17-opus"])
