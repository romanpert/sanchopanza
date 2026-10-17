"""The guard-pointers lot (docs/results/2026-10-16-guard-pointers/prereg.md): P, the default
install (pointer guard), against F, the same install with --guard-full, no decider key in either,
Sonnet 5.5, one run per arm and chain. What its arms install, what stops a call, and how it is
read. Free: no model, no API, no Jev, no Docker."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
CHAINS = (
    "conan-io__conan-long60-1",
    "pydantic__pydantic-long60-1",
    "conan-io__conan-long60-2",
    "getmoto__moto-long60-1",
    "getmoto__moto-long60-2",
)


@pytest.fixture
def m(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ADOPT))
    import long_guard
    import long_launch
    import long_pointers
    import long_pointers_read
    import long_run

    yield long_run, long_launch, long_guard, long_pointers, long_pointers_read
    for name in [
        n for n in sys.modules if n.startswith(("long_", "run", "docker_env", "hook_env"))
    ]:
        sys.modules.pop(name, None)


# ---- the arms and the profiles -------------------------------------------------------------------


def test_p_is_the_default_install_and_f_adds_guard_full_only(m) -> None:
    long_run, _, _, long_pointers, _ = m
    p = long_run.PROFILES["guardptr"]
    assert long_run.arm_spec("P", p).install == ()
    assert long_run.arm_spec("F", p).install == ("--guard-full",)
    assert long_run.arm_spec("P", p).env == () and long_run.arm_spec("F", p).env == ()
    assert long_run.installed("P", p) and long_run.installed("F", p)
    smoke = long_run.PROFILES["guardptr-smoke"]
    assert long_run.arm_spec("F", smoke).install == ("--guard-full", "--context-budget", "67000")
    assert long_pointers.install_flags("P") == ()


def test_the_profile_holds_250_hard_on_the_five_valid_chains_keyless(m) -> None:
    long_run, long_launch, _, _, _ = m
    p = long_run.PROFILES["guardptr"]
    assert p.arms == ("P", "F") and p.models == ("sonnet",) and p.keyless
    assert dict(p.call_cap) == {"sonnet": 4.5} and dict(p.chain_cap) == {"sonnet": 25.0}
    assert p.ceiling == p.hard_cap == 250.0 == len(p.chains) * 2 * 25.0
    assert p.chains == CHAINS and p.bugs is None and p.budget == 160_000
    assert p.local_stops == ("cap", "wall") and p.window == 193_000
    with pytest.raises(SystemExit):
        long_run.ceiling_of(p, 250.01)
    thirty = long_run.PROFILES["guardptr-30"]
    assert thirty.bugs == 30 and thirty.hard_cap == 180.0 == len(thirty.chains) * 2 * 18.0
    smoke = long_run.PROFILES["guardptr-smoke"]
    assert smoke.models == ("haiku",) and smoke.hard_cap == 8.0 and smoke.bugs == 3
    roots = {long_launch.ROOTS[n] for n in ("guardptr", "guardptr-30", "guardptr-smoke")}
    others = {v for k, v in long_launch.ROOTS.items() if not k.startswith("guardptr")}
    assert len(roots) == 3 and not roots & others


def test_the_order_of_the_arms_rotates_by_chain(m) -> None:
    long_run, *_ = m
    orders = {c: long_run.arm_order(c, ("P", "F")) for c in CHAINS}
    assert orders[CHAINS[0]] == ("P", "F") and orders[CHAINS[1]] == ("F", "P")
    assert {o[0] for o in orders.values()} == {"P", "F"}


def test_the_plan_prints_the_window_and_the_guard_stop(m) -> None:
    long_run, long_launch, *_ = m
    names = list(long_run.PROFILES["guardptr"].chains)
    known = {n: {"bugs": [{}] * 60} for n in names}
    text = "\n".join(
        long_launch.plan_lines("guardptr", known, names, pathlib.Path("Z:/nowhere"), 250.0)
    )
    assert "caps held 250.00 USD" in text and "ceiling 250.00 (hard, in code)" in text
    assert "P and F: the install's window 193000" in text and "without its arm's guard" in text
    assert "starts no call past 18.86" in text


# ---- what stops a call ---------------------------------------------------------------------------


def _arm(long_run, long_guard, folder: pathlib.Path, arm: str):  # noqa: ANN001, ANN202
    expect = long_guard.Expect("v", "m", "default")
    mcp = folder / ".mcp.json"
    return long_run.Arm("x-sonnet", arm, {"split": "dev"}, folder, folder, folder, "b", mcp, {},
                        expect, ())  # fmt: skip


def test_a_compaction_needs_its_arm_s_guard(m) -> None:
    *_, long_pointers, _ = m
    ok = {"compactions": [{"pre": 160_400}], "guard": [{"chooser": "pointers"}]}
    assert long_pointers.guard_breaks("P", ok) == []
    assert long_pointers.guard_breaks("F", {**ok, "guard": [{"chooser": "struct"}]}) == []
    missing = long_pointers.guard_breaks("P", {**ok, "guard": []})
    assert missing and "1 compaction(s) and 0 guard block(s)" in missing[0]
    wrong = long_pointers.guard_breaks("F", ok)
    assert wrong and "'pointers', not 'struct'" in wrong[0]
    degraded = {**ok, "guard": [{"chooser": "pointers (archive failed: rule only)"}]}
    assert long_pointers.guard_breaks("P", degraded) == []  # recorded, not a stop
    assert long_pointers.guard_breaks("P", {"compactions": [], "guard": []}) == []


def test_the_window_must_take_where_the_install_puts_it(m) -> None:
    *_, long_pointers, _ = m
    good = {"arm": "P", "compactions": [{"pre": 160_900}], "peak_context": 161_000}
    assert long_pointers.window_breaks(good) == []
    late = long_pointers.window_breaks({"arm": "F", "compactions": [], "peak_context": 240_000})
    assert late and "240000" in late[0]
    early = long_pointers.window_breaks({"arm": "P", "compactions": [{"pre": 67_000}]})
    assert early and "67000" in early[0]
    assert long_pointers.window_breaks({"compactions": [{"pre": 67_500}]}, 67_000) == []


def test_a_decision_from_any_provider_but_null_is_a_paid_call(m) -> None:
    *_, long_pointers, _ = m
    assert long_pointers.keyless_breaks([{"provider": "null"}, {"provider": None}]) == []
    paid = long_pointers.keyless_breaks([{"provider": "null"}, {"provider": "jev"}])
    assert paid and "jev" in paid[0]


def test_call_breaks_skips_the_jev_outage_check_and_adds_the_guard_checks(m, tmp_path) -> None:
    long_run, _, long_guard, _, _ = m
    p = long_run.PROFILES["guardptr"]
    a = _arm(long_run, long_guard, tmp_path, "P")
    state = long_run.ArmState(decisions=tuple({"provider": "null"} for _ in range(12)))
    row = {"init": {"version": "v", "model": "m", "permission_mode": "default",
                    "api_key_source": "none"}, "compactions": [{"pre": 160_100}],
           "peak_context": 160_200, "guard": [{"chooser": "pointers"}]}  # fmt: skip
    attempt = {"cut": False, "diff": ""}
    assert long_run.call_breaks(a, row, attempt, state, p) == ()
    # the same null decisions in a keyed profile are Jev's outage
    keyed = long_run.PROFILES["compact"]
    assert any("Jev" in b for b in long_run.call_breaks(a, row, attempt, state, keyed))
    broken = long_run.call_breaks(a, {**row, "guard": []}, attempt, state, p)
    assert any("guard block" in b for b in broken)


def test_a_deferred_find_server_may_be_pending_at_init(m, tmp_path) -> None:
    _, _, long_guard, long_pointers, _ = m
    mcp = tmp_path / ".mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"sanchopanza": {"command": "x"},
                                              "loaded": {"command": "y", "alwaysLoad": True}}}),
                   encoding="utf-8")  # fmt: skip
    deferred = long_pointers.deferred_servers(mcp)
    assert deferred == ("sanchopanza",)
    expect = long_guard.Expect("v", "m", "default", ("sanchopanza", "loaded"), deferred)
    init = {"version": "v", "model": "m", "permission_mode": "default", "api_key_source": "none"}
    ok = {**init, "mcp": {"sanchopanza": "pending", "loaded": "connected"}}
    assert long_guard.init_breaks(ok, expect) == ()
    late = {**init, "mcp": {"sanchopanza": "connected", "loaded": "pending"}}
    assert long_guard.init_breaks(late, expect) == ("MCP server loaded pending",)
    failed = {**init, "mcp": {"sanchopanza": "failed", "loaded": "connected"}}
    assert long_guard.init_breaks(failed, expect) == ("MCP server sanchopanza failed",)


def test_p_and_f_must_share_their_first_prefix(m) -> None:
    _, _, long_guard, _, _ = m
    assert long_guard.prefix_breaks({"P": 22_000, "F": 22_030}) == ()
    assert long_guard.prefix_breaks({"P": 22_000, "F": 23_000})


def test_the_hooks_archive_beside_the_project_and_log_the_guard_in_the_lot(
    m, monkeypatch, tmp_path
) -> None:
    monkeypatch.syspath_prepend(str(ADOPT))
    import hook_env

    key = tmp_path / "none.key"
    key.write_text("", encoding="utf-8")
    plain = hook_env.environment(tmp_path, key, base={"PATH": "x"})
    assert plain["SANCHOPANZA_ARCHIVE"] == str(tmp_path / "archive")
    assert "SANCHOPANZA_GUARD_LOG" not in plain and "TYPESAFE_API_KEY" not in plain
    lot = hook_env.environment(tmp_path, key, base={"PATH": "x", "ADOPT_GUARD_LOT": "1",
                                                    "TYPESAFE_API_KEY": "leak"})  # fmt: skip
    assert "SANCHOPANZA_ARCHIVE" not in lot and "TYPESAFE_API_KEY" not in lot
    assert lot["SANCHOPANZA_GUARD_LOG"] == str(tmp_path / "guard.jsonl")


def test_a_keyless_profile_writes_an_empty_key_and_reads_none(m, monkeypatch, tmp_path) -> None:
    long_run, *_ = m

    def no_env(_name: str) -> str:
        raise AssertionError("a keyless profile must not read the key")

    monkeypatch.setattr(long_run.carry, "from_harness_env", no_env)
    path = long_run.keyfile_for(long_run.PROFILES["guardptr"], long_run.Layout(tmp_path))
    assert path is not None and path.read_text(encoding="utf-8") == ""


def test_the_guard_log_lands_in_the_row(m, tmp_path) -> None:
    long_run, _, long_guard, long_pointers, _ = m
    rows = [{"event": "PreCompact", "chooser": "struct", "block_chars": 44_000, "parts": 6},
            {"event": "SessionStart", "origin": "kept", "block_chars": 44_000}]  # fmt: skip
    (tmp_path / long_pointers.GUARD_LOG).write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    a = _arm(long_run, long_guard, tmp_path, "F")
    facts, state = long_run.s_arm_facts(a, long_run.ArmState())
    assert facts["guard"] == [{"chooser": "struct", "block_chars": 44_000, "parts": 6}]
    assert state.guard_lines == 2
    again, _ = long_run.s_arm_facts(a, state)
    assert again["guard"] == []


# ---- the reading ---------------------------------------------------------------------------------


def _clusters(diffs: list[int], bugs: int = 60) -> list[list[tuple[bool, bool]]]:
    """One cluster per chain: `d` bugs P alone (d > 0) or F alone (d < 0), the rest both."""
    out = []
    for d in diffs:
        pairs = [(True, False)] * max(d, 0) + [(False, True)] * max(-d, 0)
        out.append(pairs + [(True, True)] * (bugs - len(pairs)))
    return out


def test_the_verdict_by_the_rule(m) -> None:
    *_, read = m
    same = read.quality(_clusters([0, 1, -1, 0, 1]))
    assert read.verdict(same, 5, 0.05) == "non-inferior"
    loss = read.quality(_clusters([-3, -4, -3, -5, -4]))  # about -6 points, tight
    assert read.verdict(loss, 5, 0.05) == "worse"
    small = read.quality(_clusters([-1, -2, -1, -1, -2]))  # about -2 points, shown below 0
    assert read.verdict(small, 5, 0.05) == "non-inferior, a smaller loss shown"
    noisy = read.quality(_clusters([4, -9, 3, -6, 2]))
    assert read.verdict(noisy, 5, 0.05) == "not shown"
    assert read.verdict(same, 4, 0.05) == "no verdict"


def test_the_t_bound_is_the_stricter_one_with_five_chains(m) -> None:
    *_, read = m
    q = read.quality(_clusters([2, -3, 1, -2, 0]))
    assert q["t_low"] < q["one_sided_low"] < q["difference"]


def test_the_margin_and_floor_are_the_registered_ones(m) -> None:
    *_, read = m
    assert read.MARGINS == {"guardptr": 0.05, "guardptr-30": 0.07}
    assert read.MIN_CHAINS == 5 and read.MIN_COMMON == {"guardptr": 30, "guardptr-30": 20}
    assert read.TEST_TIMEOUT == 300


def _transcript(path: pathlib.Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def _use(name: str, **data: str) -> dict:
    block = {"type": "tool_use", "name": name, "input": data}
    return {"type": "assistant", "message": {"content": [block]}}


def test_the_mechanism_counts_archive_reads_reruns_and_rereads(m, tmp_path) -> None:
    *_, read = m
    archived = r"C:\w\.sanchopanza\archive\s1\guard-01ABC.txt"
    _transcript(tmp_path / "transcript.jsonl", [
        _use("Read", file_path="src/a.py"),
        _use("Bash", command="runtests tests/test_a.py"),
        _use("Bash", command="git log -5"),
        {"type": "system", "subtype": "compact_boundary"},
        _use("Read", file_path=archived),
        _use("Bash", command="runtests tests/test_a.py"),
        _use("Read", file_path="src/a.py"),
        _use("Read", file_path="src/b.py"),
        _use("Bash", command=f"cat {archived}"),
    ])  # fmt: skip
    found = read.mechanism(tmp_path)
    assert found == {"compactions": 1, "archive_reads": 2, "reruns": 1, "rereads": 1}


def test_the_carry_facts_come_from_the_guard_log_in_the_rows(m) -> None:
    *_, read = m
    first = {"chooser": "pointers", "block_chars": 8_000, "archived": 3}
    second = {"chooser": "pointers", "block_chars": 7_000, "archived": 1}
    row = {"calls": [{"guard": [first]}, {"guard": []}, {"guard": [second]}]}
    assert read.carry(row) == {"blocks": 2, "block_chars": [8_000, 7_000],
                               "median_block_chars": 7_500, "archived": 4,
                               "choosers": ["pointers"], "failed": 0}  # fmt: skip


# ---- the reviewer's points (revisor-prereg, before the seal) ------------------------------------


def test_the_shell_guard_s_own_decisions_are_not_paid_calls(m) -> None:
    *_, long_pointers, _ = m
    free = [{"provider": "code"}, {"provider": "budget"}, {"provider": "null"}]
    assert long_pointers.keyless_breaks(free) == []
    assert long_pointers.keyless_breaks([*free, {"provider": "llm"}])


def test_a_failed_guard_is_counted_not_stopped(m) -> None:
    *_, long_pointers, read = m
    assert long_pointers.FAILED_GUARD == {"P": "pointers (archive failed: rule only)",
                                          "F": "struct (error: rule only)"}  # fmt: skip
    for arm, chooser in long_pointers.FAILED_GUARD.items():
        row = {"compactions": [{"pre": 160_000}], "guard": [{"chooser": chooser}]}
        assert long_pointers.guard_breaks(arm, row) == []
    whole = {"chooser": "struct", "block_chars": 40_000}
    failed = {"chooser": "struct (error: rule only)", "block_chars": 900}
    row = {"calls": [{"guard": [whole]}, {"guard": [failed]}]}
    found = read.carry(row)
    assert found["failed"] == 1 and found["blocks"] == 2
    assert found["choosers"] == ["struct", "struct (error: rule only)"]


def _arm_row(folder: pathlib.Path, arm: str, **extra) -> None:  # noqa: ANN003
    evidence = folder / arm
    evidence.mkdir(parents=True)
    row = {"arm": arm, "calls": [{"request": 1, "status": "ran", "owner_usd": 1.0}], **extra}
    (evidence / "row.json").write_text(json.dumps(row), encoding="utf-8")


def test_a_paused_or_partial_chain_is_not_scored(m, tmp_path) -> None:
    *_, read = m
    base = tmp_path / "runs" / "c1-sonnet"
    _arm_row(base, "P", stopped="limit")
    _arm_row(base, "F", stopped="")
    assert read.paused(base) == ["P: stopped (limit)"]
    other = tmp_path / "runs" / "c2-sonnet"
    _arm_row(other, "P", stopped="", partial=True)
    _arm_row(other, "F", stopped="cap")
    assert read.paused(other) == ["P: partial (the runner died or is running)"]
    done = tmp_path / "runs" / "c3-sonnet"
    _arm_row(done, "P", stopped="cap")
    _arm_row(done, "F", stopped="")
    assert read.paused(done) == []
    for why in ("harness", "ceiling"):
        again = tmp_path / "runs" / f"c-{why}-sonnet"
        _arm_row(again, "P", stopped=why)
        _arm_row(again, "F", stopped="")
        assert read.paused(again)


def test_a_paused_chain_leaves_the_lot_without_verdict(m, monkeypatch, tmp_path) -> None:
    *_, read = m
    line = {"common_calls": 60, "ratio": 0.95, "pairs": [(True, True)] * 60,
            "arms": {"P": {"cost_common": 17.0}, "F": {"cost_common": 18.0}}}  # fmt: skip
    monkeypatch.setattr(read.long_compact, "chain_line", lambda *_a, **_k: dict(line))
    monkeypatch.setattr(read, "paused", lambda base: ["P: stopped (limit)"] if "c5" in str(base)
                        else [])  # fmt: skip
    found = read.read(tmp_path, ["c1", "c2", "c3", "c4", "c5"])
    assert found["chains_counted"] == ["c1", "c2", "c3", "c4"]
    assert found["chains_paused"] == {"c5": ["P: stopped (limit)"]}
    assert found["verdict"] == "no verdict"


def test_the_smoke_runs_p_even_when_f_stops_at_its_cap(m) -> None:
    long_run, *_ = m
    smoke = long_run.PROFILES["guardptr-smoke"]
    assert smoke.local_stops == ("cap", "wall") and smoke.day_only


def test_the_shared_prefix_is_checked_at_the_second_arm_s_first_call(m, tmp_path) -> None:
    long_run, *_ = m
    folder = tmp_path / "c1-sonnet"
    first = {"request": 1, "status": "ran", "first_request": {"read": 15_000, "write": 6_000}}
    _arm_row(folder, "F", calls=[first], window={"configured": 193_000})
    assert long_run.first_call_breaks(folder, "P", False) == ""  # only at the first call that ran
    same = {**first, "first_request": {"read": 15_000, "write": 6_020}}
    _arm_row(folder, "P", calls=[same], window={"configured": 193_000})
    assert long_run.first_call_breaks(folder, "P", True) == ""
    (folder / "P" / "row.json").unlink()
    far = {**first, "first_request": {"read": 15_000, "write": 9_000}}
    (folder / "P" / "row.json").write_text(json.dumps({"arm": "P", "calls": [far]}),
                                           encoding="utf-8")  # fmt: skip
    assert "differs from F's" in long_run.first_call_breaks(folder, "P", True)
    assert long_run.first_call_breaks(folder, "Ne", True) == ""  # other lots keep their own check


def test_a_pending_restart_stops_the_next_chain(m, monkeypatch) -> None:
    long_run, *_ = m
    import long_start

    p = long_run.PROFILES["guardptr"]
    monkeypatch.setattr(long_start, "restart_pending", lambda: "RebootRequired")
    assert "RebootRequired" in long_start.restart_refusal(p, False)
    assert long_start.restart_refusal(p, True) == ""  # the dry runs
    assert long_start.restart_refusal(long_run.PROFILES["compact"], False) == ""
    monkeypatch.setattr(long_start, "restart_pending", lambda: "")
    assert long_start.restart_refusal(p, False) == ""


# ---- the second pass (revisor-prereg) ------------------------------------------------------------


def test_the_runner_refuses_a_guard_profile_without_the_sealed_launcher(m) -> None:
    long_run, *_ = m
    why = long_run.seal_refusal(long_run.PROFILES["guardptr"], {})
    assert "nothing spent" in why
    assert long_run.seal_refusal(long_run.PROFILES["compact"], {}) == ""


def test_long_run_alone_cannot_spend_on_the_lot(m, tmp_path) -> None:
    long_run, *_ = m
    argv = ["run", "--profile", "guardptr", "--root", str(tmp_path / "L"),
            "--limit-flag", str(tmp_path / "LIMIT.flag")]  # fmt: skip
    assert long_run.main(argv) == 1
    assert not (tmp_path / "L" / "runs").exists()


def test_a_call_in_the_quiet_hours_pauses_the_arm(m, monkeypatch, tmp_path) -> None:
    long_run, _, long_guard, _, _ = m
    monkeypatch.setattr(long_run, "quiet_refusal", lambda _p, allow: "" if allow else "02:00")
    monkeypatch.setattr(long_run.docker_env, "health", lambda: "")
    ctx = long_run.Ctx(long_run.Layout(tmp_path, tmp_path / "LIMIT.flag"),
                       long_run.PROFILES["guardptr"], "sonnet", ceiling=250.0)  # fmt: skip
    a = _arm(long_run, long_guard, tmp_path, "P")
    assert long_run.before_call(ctx, a, [], long_run.ArmState()) == "clock"
    dry = long_run.replace(ctx, allow_midnight=True)
    assert long_run.before_call(dry, a, [], long_run.ArmState()) == ""
    assert long_run.EXIT["clock"] == 2


def test_a_clock_pause_is_resumable_and_not_scored(m, tmp_path) -> None:
    *_, read = m
    import long_resume

    assert long_resume.may_resume({"stopped": "clock"})
    base = tmp_path / "runs" / "c1-sonnet"
    _arm_row(base, "P", stopped="clock")
    _arm_row(base, "F", stopped="")
    assert read.paused(base) == ["P: stopped (clock)"]


def test_cut_calls_are_counted_per_arm(m) -> None:
    *_, read = m
    row = {"calls": [{"status": "ran"}, {"status": "cut (timeout)", "deviation": "went on"},
                     {"status": "ran", "retried": True}, {"status": "ran"}]}  # fmt: skip
    assert read.cuts(row) == {"cut": 1, "retried": 1, "set_aside": 0}


def test_the_rule_compares_unrounded_bounds(m) -> None:
    *_, read = m
    q = {"difference": -0.01, "ci95": [-0.06, 0.02], "one_sided_low": -0.049996,
         "t_low": -0.050004}  # fmt: skip
    assert read.verdict(q, 5, 0.05) == "not shown"  # rounded to 4 places both would read -0.05
    assert read.published(q)["t_low"] == -0.05


# ---- the grade under the profile's model ---------------------------------------------------------

SMOKE = "pydantic__pydantic-long60-1"


def _graded_rows(base: pathlib.Path) -> None:
    for arm in ("P", "F"):
        evidence = base / arm
        evidence.mkdir(parents=True)
        row = {"arm": arm, "token": "T", "bugs": 3,
               "calls": [{"request": 1, "status": "ran", "owner_usd": 0.1}]}  # fmt: skip
        (evidence / "row.json").write_text(json.dumps(row), encoding="utf-8")
        (evidence / "diff-1.patch").write_text("", encoding="utf-8")


@pytest.fixture
def no_docker(m, monkeypatch):
    """perbug.grade and the chains stubbed: nothing runs pytest, Docker or reads the cache."""
    import perbug
    import run

    asked = []
    monkeypatch.setattr(run, "chains", lambda: {SMOKE: {"bugs": [{"id": i} for i in range(3)]}})
    monkeypatch.setattr(perbug, "grade", lambda chain, patch: asked.append(chain) or
                        {"resolved": 0, "bugs": []})  # fmt: skip
    return asked


def test_the_grade_reads_the_runs_of_the_profile_s_model(m, no_docker, tmp_path) -> None:
    long_run, *_, read = m
    assert long_run.PROFILES["guardptr-smoke"].models == ("haiku",)
    _graded_rows(tmp_path / "runs" / f"{SMOKE}-haiku")
    assert read.main(["grade", "--profile", "guardptr-smoke", "--root", str(tmp_path)]) == 0
    assert len(no_docker) == 2  # P and F, each at its common call
    for arm in ("P", "F"):
        graded = tmp_path / "runs" / f"{SMOKE}-haiku" / arm / "grade-common.json"
        assert json.loads(graded.read_text(encoding="utf-8"))["common_calls"] == 1


def test_a_grade_with_nothing_to_grade_fails_and_says_where_it_looked(
    m, no_docker, tmp_path, capsys
) -> None:
    *_, read = m
    _graded_rows(tmp_path / "runs" / f"{SMOKE}-sonnet")  # another model's runs: not the smoke's
    assert read.main(["grade", "--profile", "guardptr-smoke", "--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "nothing graded" in err and "-haiku" in err
    assert no_docker == []


def test_rows_of_the_model_without_a_common_call_fail(m, no_docker, tmp_path, capsys) -> None:
    *_, read = m
    base = tmp_path / "runs" / f"{SMOKE}-haiku"
    _graded_rows(base)
    row = json.loads((base / "F" / "row.json").read_text(encoding="utf-8"))
    row["calls"] = [{"request": 1, "status": "NOT RUN (cap)"}]  # F never ran: no common call
    (base / "F" / "row.json").write_text(json.dumps(row), encoding="utf-8")
    assert read.main(["grade", "--profile", "guardptr-smoke", "--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "P/F not graded at a common call" in err and "nothing graded" in err
    assert no_docker == []


def test_a_whole_chain_with_an_arm_left_ungraded_fails_and_names_it(
    m, no_docker, tmp_path, capsys
) -> None:
    *_, read = m
    base = tmp_path / "runs" / f"{SMOKE}-haiku"
    _graded_rows(base)
    (base / "F" / "diff-1.patch").unlink()  # F's snapshot at the common call is gone
    argv = ["grade", "--profile", "guardptr-smoke", "--root", str(tmp_path), "--final"]
    assert read.main(argv) == 1
    out = capsys.readouterr()
    assert f"{SMOKE} P: graded at call 1" in out.out
    assert f"{SMOKE} (haiku): F not graded at a common call" in out.err
    assert len(no_docker) == 1


def test_the_reading_reads_the_profile_s_model_too(m, monkeypatch, tmp_path) -> None:
    import dataclasses

    long_run, *_, read = m
    profile = dataclasses.replace(long_run.PROFILES["guardptr"], models=("opus",))
    monkeypatch.setitem(long_run.PROFILES, "guardptr", profile)
    seen, bases = [], []
    line = {"common_calls": 60, "ratio": 0.95, "pairs": [(True, True)] * 60,
            "arms": {"P": {"cost_common": 17.0}, "F": {"cost_common": 18.0}}}  # fmt: skip

    def chain_line(root, chain, pair, model):  # noqa: ANN001, ANN202
        return seen.append(model) or dict(line)

    monkeypatch.setattr(read.long_compact, "chain_line", chain_line)
    monkeypatch.setattr(read, "paused", lambda base: bases.append(base.name) or [])
    assert read.main(["read", "--profile", "guardptr", "--root", str(tmp_path)]) == 0
    assert seen == ["opus"] * len(CHAINS)
    assert bases == [f"{c}-opus" for c in CHAINS]
