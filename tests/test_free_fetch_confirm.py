"""The sealed confirmation of fetch v2 (fetch1): sixty new FRAMES tasks, four arms, the -FETCH2
arms with the server at version 2 and no page budget, blind grading and the registered verdicts.
No model, no network, no money."""

from __future__ import annotations

import importlib.util
import pathlib
import random
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


grader = _load("browse_free_fetch_confirm_hand", "benchmarks/browse/free_fetch_confirm_hand.py")
conf = grader.conf


# --- design -------------------------------------------------------------------------------------


def test_arms_caps_ceiling_and_a_private_folder():
    assert conf.ARMS == ("HAIKU", "HAIKU-FETCH2", "SONNET", "SONNET-FETCH2")
    assert conf.CAPS == {"HAIKU": 0.60, "HAIKU-FETCH2": 0.60, "SONNET": 1.50, "SONNET-FETCH2": 1.50}
    assert conf.CEILING_USD == 55.0 and conf.N_TASKS == 60
    assert conf.PRIVATE not in (conf.p2.PRIVATE, conf.pilot.PRIVATE, conf.free.CACHE)
    assert conf.SEED not in (conf.p2.SEED, conf.pilot.SEED, conf.frames.SEED)
    assert conf.frames.CLAUDE_VERSION == "2.1.287"


def test_the_sixty_tasks_are_none_of_any_earlier_pilot_or_smoke():
    assert set(conf.PRIOR_IDS) == {
        "frames-ids.txt", "frames2-ids.txt", "fetch-pilot-ids.txt", "fetch2-pilot-ids.txt"
    }  # fmt: skip
    ids = conf.IDS.read_text(encoding="utf-8").split()
    assert len(ids) == len(set(ids)) == 60 and not set(ids) & conf.taken_ids()
    private = conf.private_session_ids()
    if private is not None:  # every earlier session file on this machine, smokes included
        assert private <= conf.taken_ids() and not set(ids) & private
    if not conf.frames.FRAMES.exists():
        pytest.skip("FRAMES is not cached here")
    rows = conf.frames.read_frames()
    assert ids == conf.pilot.sample(rows, conf.taken_ids(), n=60, seed=conf.SEED)
    by_id = {conf.frames.tid_of(r): r for r in rows}
    assert all(conf.pilot.eligible(by_id[t]) for t in ids)


def test_the_plan_runs_every_task_in_the_four_arms_interleaved_by_task():
    items = [(f"FR{i}", "", "q", "a") for i in range(60)]
    steps = conf.plan(items)
    assert len(steps) == 240
    for k in range(60):
        block = steps[4 * k : 4 * k + 4]
        assert {s[1][0] for s in block} == {f"FR{k}"}
        assert tuple(s[3] for s in block) == conf.ARMS


def test_the_fetch2_arms_get_version_two_the_webfetch_hook_and_no_page_budget(tmp_path):
    from sanchopanza.harness.fetch_hook import FETCH_HOOKS

    for base in ("HAIKU", "SONNET"):
        assert conf.arm_options(base, tmp_path) == {"hooks": None, "env_extra": None,
                                                    "mcp_servers": None}  # fmt: skip
    for arm in ("HAIKU-FETCH2", "SONNET-FETCH2"):
        options = conf.arm_options(arm, tmp_path)
        env = options["env_extra"]
        assert env["SANCHOPANZA_FETCH_VERSION"] == "2"
        assert env["SANCHOPANZA_FETCH_DIR"] == str(tmp_path)
        server = options["mcp_servers"][conf.pilot.SERVER]
        assert server["alwaysLoad"] is True and server["env"]["SANCHOPANZA_FETCH_VERSION"] == "2"
        assert not any("MAX_PAGES" in k for k in {**env, **server["env"]})
        hooks = options["hooks"]
        assert {event: v[0]["matcher"] for event, v in hooks.items()} == FETCH_HOOKS
        assert "fetch_hook" in hooks["PreToolUse"][0]["hooks"][0]["command"]


def test_the_sessions_go_through_the_pilot_runner_with_this_run_s_caps_and_options(monkeypatch):
    seen = {}

    def one_session(task, run, arm, session_max_usd, deny, hooks, env_extra, mcp_servers):
        seen.update(arm=arm, cap=session_max_usd, deny=deny, hooks=hooks, env=env_extra)
        raise RuntimeError("stop here")

    monkeypatch.setattr(conf.free, "one_session", one_session)
    with pytest.raises(RuntimeError):
        conf.session_for(conf.SESSIONS)(("FR1", "", "q", "a"), 1, "SONNET-FETCH2")
    assert seen["cap"] == 1.50 and seen["deny"] == conf.frames.DENY
    assert seen["env"]["SANCHOPANZA_FETCH_VERSION"] == "2" and seen["hooks"]


def test_preflight_refuses_a_page_budget_in_the_run_environment(monkeypatch):
    monkeypatch.setattr(conf.pilot, "preflight", lambda: [])
    monkeypatch.setattr(conf, "registered", lambda: True)
    assert conf.preflight({}) == []
    problems = conf.preflight({"SANCHOPANZA_FETCH_MAX_PAGES": "8"})
    assert any("SANCHOPANZA_FETCH_MAX_PAGES" in p for p in problems)
    monkeypatch.setattr(conf, "registered", lambda: False)
    assert any("not registered" in p for p in conf.preflight({}))


def test_the_registration_is_checked_byte_for_byte(tmp_path, monkeypatch):
    prereg = tmp_path / "prereg-fetch1.md"
    prereg.write_text("# registered\n", encoding="utf-8")
    monkeypatch.setattr(conf, "PREREG", prereg)
    assert not conf.registered()
    prereg.with_suffix(".sha256").write_text(conf.digest(prereg) + "\n", encoding="utf-8")
    assert conf.registered()
    prereg.write_text("# registered, then changed\n", encoding="utf-8")
    assert not conf.registered()


# --- verdicts -----------------------------------------------------------------------------------

IDS = [f"FR{i}" for i in range(60)]


def _rows(costs: dict[str, float], answer: str = "x") -> list[dict]:
    return [{"task": t, "arm": arm, "list_usd": usd, "answer_after": answer, "subtype": "success",
             "calls": {}, "run": 1}
            for t in IDS for arm, usd in costs.items()]  # fmt: skip


def _grades(right: dict[str, bool] | None = None) -> dict:
    return {(t, arm): (right or {}).get(arm, True) for t in IDS for arm in conf.ARMS}


CHEAP = {"HAIKU": 0.20, "HAIKU-FETCH2": 0.10, "SONNET": 0.40, "SONNET-FETCH2": 0.20}


def test_beats_the_harness_only_on_price_and_answers_at_once():
    out = grader.verdicts(_rows(CHEAP), _grades(), set(), IDS)
    assert out["complete"]
    assert out["HAIKU"]["beats_the_harness"] and out["SONNET"]["beats_the_harness"]
    lost = grader.verdicts(_rows(CHEAP), _grades({"SONNET-FETCH2": False}), set(), IDS)
    assert lost["HAIKU"]["beats_the_harness"] and not lost["SONNET"]["beats_the_harness"]
    assert lost["SONNET"]["price"]["holds"] and not lost["SONNET"]["answers"]["holds"]
    dear = grader.verdicts(_rows({**CHEAP, "HAIKU-FETCH2": 0.17}), _grades(), set(), IDS)
    assert not dear["HAIKU"]["price"]["holds"] and dear["HAIKU"]["answers"]["holds"]


def test_the_price_bar_is_a_ratio_of_at_most_080_and_cheaper_on_at_least_55_percent():
    rows = _rows({"HAIKU": 0.25, "HAIKU-FETCH2": 0.20, "SONNET": 0.40, "SONNET-FETCH2": 0.20})
    assert grader.verdicts(rows, _grades(), set(), IDS)["HAIKU"]["price"]["holds"]  # 0.80
    over = [{**r, "list_usd": 0.2001} if r["arm"] == "HAIKU-FETCH2" else r for r in rows]
    assert not grader.verdicts(over, _grades(), set(), IDS)["HAIKU"]["price"]["holds"]

    def cheaper_on(n: int) -> list[dict]:  # cheaper on n tasks, dearer on the rest, ratio low
        out = []
        for r in _rows({"HAIKU": 1.0, "HAIKU-FETCH2": 0.1, "SONNET": 1.0, "SONNET-FETCH2": 0.1}):
            k = int(r["task"][2:])
            if r["arm"] == "HAIKU-FETCH2" and k >= n:
                r = {**r, "list_usd": 0.3}
            if r["arm"] == "HAIKU" and k >= n:
                r = {**r, "list_usd": 0.2}
            out.append(r)
        return out

    at = grader.verdicts(cheaper_on(33), _grades(), set(), IDS)["HAIKU"]["price"]
    assert at["tasks_cheaper"] == 33 and at["ratio_total"] <= 0.8 and at["holds"]
    under = grader.verdicts(cheaper_on(32), _grades(), set(), IDS)["HAIKU"]["price"]
    assert under["ratio_total"] <= 0.8 and not under["holds"]


def test_one_answer_fewer_fails_and_a_tie_holds():
    grades = _grades()
    grades[("FR7", "HAIKU-FETCH2")] = False
    assert not grader.verdicts(_rows(CHEAP), grades, set(), IDS)["HAIKU"]["answers"]["holds"]
    grades[("FR9", "HAIKU")] = False
    assert grader.verdicts(_rows(CHEAP), grades, set(), IDS)["HAIKU"]["answers"]["holds"]


def test_no_answer_line_is_wrong_whatever_the_grade():
    rows = _rows(CHEAP)
    rows = [{**r, "answer_after": ""} if (r["task"], r["arm"]) == ("FR3", "SONNET-FETCH2") else r
            for r in rows]  # fmt: skip
    out = grader.verdicts(rows, _grades(), set(), IDS)["SONNET"]["answers"]
    assert out["SONNET-FETCH2"] == 59 and not out["holds"]


def test_a_leak_makes_both_arms_of_its_model_wrong_on_that_task():
    out = grader.verdicts(_rows(CHEAP), _grades(), {("FR5", "HAIKU")}, IDS)
    assert out["HAIKU"]["answers"]["HAIKU"] == out["HAIKU"]["answers"]["HAIKU-FETCH2"] == 59
    assert out["SONNET"]["answers"]["SONNET"] == 60
    rows = [{**r, "leak": r["task"] == "FR5" and r["arm"] == "SONNET"} for r in _rows(CHEAP)]
    marks = grader.leak_marks(rows, scan=lambda row: False)
    assert marks == [{"task": "FR5", "arm": "SONNET"}]
    scanned = grader.leak_marks(_rows(CHEAP), scan=lambda row: row["task"] == "FR2")
    assert len(scanned) == 4


def test_a_session_the_runner_killed_is_charged_its_cap():
    rows = _rows(CHEAP)
    rows = [{**r, "subtype": "runner: TimeoutExpired", "list_usd": 0.0}
            if (r["task"], r["arm"]) == ("FR1", "SONNET-FETCH2") else r for r in rows]  # fmt: skip
    out = grader.verdicts(rows, _grades(), set(), IDS)["SONNET"]["price"]
    assert out["total_usd"]["SONNET-FETCH2"] == pytest.approx(59 * 0.20 + 1.50)
    assert out["tasks_cheaper"] == 59


def test_an_incomplete_run_is_marked_so():
    rows = [r for r in _rows(CHEAP) if not (r["task"] == "FR59" and r["arm"] == "SONNET")]
    assert not grader.verdicts(rows, _grades(), set(), IDS)["complete"]


# --- blind grading ------------------------------------------------------------------------------


def test_the_blind_sheet_hides_the_arm_and_the_key_gives_it_back():
    rows = [{**r, "answer_after": f"{r['task']}-{r['arm']}"} for r in _rows(CHEAP)[:40]]
    tasks = {t: (t, "", f"question {t}", f"gold {t}") for t in IDS}
    sheet, key = grader.blind_sheet(rows, tasks, rng=random.Random(1))
    assert len(sheet) == len(key) == 40 and len({e["id"] for e in sheet}) == 40
    for entry in sheet:
        assert set(entry) == {"id", "task", "question", "gold", "answer", "right"}
        assert entry["right"] is None
        assert entry["answer"] == f"{key[entry['id']]['task']}-{key[entry['id']]['arm']}"
    arms_in_order = [key[e["id"]]["arm"] for e in sheet]
    assert arms_in_order[:4] != list(conf.ARMS) or arms_in_order[4:8] != list(conf.ARMS)
    graded = [{**e, "right": key[e["id"]]["arm"].endswith("FETCH2")} for e in sheet]
    grades = {(g["task"], g["arm"]): g["right"] for g in grader.apply_sheet(graded, key)}
    assert grades == {(r["task"], r["arm"]): r["arm"].endswith("FETCH2") for r in rows}


def test_apply_refuses_an_ungraded_or_mismatched_sheet():
    rows = _rows(CHEAP)[:8]
    tasks = {t: (t, "", "q", "g") for t in IDS}
    sheet, key = grader.blind_sheet(rows, tasks, rng=random.Random(2))
    with pytest.raises(SystemExit):
        grader.apply_sheet(sheet, key)
    graded = [{**e, "right": True} for e in sheet]
    with pytest.raises(SystemExit):
        grader.apply_sheet(graded[1:], key)
    with pytest.raises(SystemExit):
        grader.apply_sheet([{**graded[0], "right": "yes"}, *graded[1:]], key)
    assert len(grader.apply_sheet(graded, key)) == 8


def test_described_counts_answers_lines_and_tool_use_per_arm():
    rows = _rows(CHEAP)
    rows = [{**r, "calls": {"fetch_passages": 2}} if r["arm"].endswith("FETCH2") else r
            for r in rows]  # fmt: skip
    out = grader.described(rows, lambda r: True)
    assert out["by_arm"]["HAIKU-FETCH2"]["sessions_calling_fetch_passages"] == 60
    assert out["by_arm"]["HAIKU"]["sessions_calling_fetch_passages"] == 0
    assert out["paired_SONNET-FETCH2_vs_SONNET"]["p_exact"] == 1.0
