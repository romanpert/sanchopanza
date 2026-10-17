"""The pilot of bet A (passages on arrival, `long_pilot.py`): its profile and arms, the install kept
to the passages hook alone, the journal facts per call and arm, the re-request abort, the frozen
commit's check, the plan and the money it holds. The runner end to end with a stand-in `claude`
and a stand-in sanchopanza (`tests/fixtures/long_fake`). Free: no model, no API, no Jev, no Docker.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest

from tests.helpers import main_venv, missing_commits
from tests.test_adopt_long_runner import _setup, lr  # noqa: F401  (lr: the runner fixture)

ROOT = pathlib.Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fixtures" / "long_fake"
LEAN_SRC = ROOT.parent / "sanchopanza-lean" / "src"
MAIN_VENV = main_venv()
MAIN_PY = MAIN_VENV / "python.exe"
GATE = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")
PYD = "pydantic__pydantic-long40-1"
# What `lean` edd37bb writes for `install --passages --provider jev --scope project --write
# --no-guard --no-find --no-skill --context-budget 0` (run by hand, 2026-10-07), hooks rewritten
# by `run.install_sancho` as the runner does.
PRE = "Agent|Bash|PowerShell|Task|WebSearch|bash|execute|run_command|shell"
PREFIX = "C:/py/python.exe C:/wt/hook_env.py C:/ev C:/keys/k.key"
REAL = {"hooks": {"PreToolUse": [{"matcher": PRE, "hooks": [
            {"type": "command", "command": f"{PREFIX} hook"}]},
            {"matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [
                {"type": "command", "command": f"{PREFIX} passages-hook", "timeout": 10}]}],
        "PostToolUse": [
            {"matcher": "Agent|Task", "hooks": [{"type": "command", "command": f"{PREFIX} hook"}]},
            {"matcher": "Bash|PowerShell|Read", "hooks": [
                {"type": "command", "command": f"{PREFIX} passages-hook"}]}],
        "Stop": [], "UserPromptSubmit": []},
        "env": {"SANCHOPANZA_PROVIDER": "jev", "SANCHOPANZA_GUARD_PROFILE": "coding",
                "SANCHOPANZA_PASSAGES_FRACTION": "0.25",
                "SANCHOPANZA_PASSAGES_TOKENS": "2000"}}  # fmt: skip


@pytest.fixture
def lp(lr: ModuleType) -> ModuleType:  # noqa: F811
    import long_pilot

    return long_pilot


def stand_in(tmp_path: pathlib.Path) -> pathlib.Path:
    """A frozen-copy stand-in: `Scripts/sanchopanza.cmd` running `fake_sancho.py`."""
    folder = tmp_path / "frozen" / "Scripts"
    folder.mkdir(parents=True)
    exe = folder / "sanchopanza.cmd"
    exe.write_text(f'@"{sys.executable}" "{FAKE / "fake_sancho.py"}" %*\r\n', encoding="utf-8",
                   newline="")  # fmt: skip
    return exe


def _events(path: pathlib.Path, events: list[tuple[str, dict[str, Any]]]) -> pathlib.Path:
    path.write_text("".join(json.dumps({"ts": "t", "kind": k, "data": d}) + "\n"
                            for k, d in events), encoding="utf-8")  # fmt: skip
    return path


def _cuts(n: int, whole: int = 0, targeted: int = 0) -> list[tuple[str, dict[str, Any]]]:
    cuts = [("passages", {"tool_use_id": f"c{i}", "acted": True, "chars_in": 8000,
                          "chars_out": 2000, "injected_chars": 2200})
            for i in range(n)]  # fmt: skip
    kinds = ["whole"] * whole + ["targeted"] * targeted
    return [*cuts, *(("passages_rerequest", {"cut": f"c{i}", "kind": k})
                     for i, k in enumerate(kinds))]  # fmt: skip


# ---- profile and arms ----------------------------------------------------------------------------


def test_the_pilot_profile_is_the_gates_sonnet_with_its_own_hard_ceiling(lr: ModuleType) -> None:  # noqa: F811
    p = lr.PROFILES["pilot-a"]
    assert p.arms == ("A",) and p.models == ("sonnet",) and p.chains == GATE == lr.GATE_CHAINS
    assert dict(p.call_cap) == {"sonnet": 4.5} == {"sonnet": lr.GATE_CALL_CAP["sonnet"]}
    assert dict(p.chain_cap) == {"sonnet": 38.0} == {"sonnet": lr.GATE_CHAIN_CAP["sonnet"]}
    assert p.ceiling == 80.0 == p.hard_cap
    assert p.hours["sonnet"] == lr.PROFILES["gate"].hours["sonnet"]  # midnight rule as the gate
    assert p.with_arms(("A10",)).arms == ("A10",) and p.with_arms(()).arms == ("A",)
    for wrong in (("S",), ("N",), ("A", "Ne")):
        with pytest.raises(SystemExit, match="arms"):
            p.with_arms(wrong)
    assert lr.PROFILES["gate"].with_arms(()).arms == ("N",)


def test_arms_a_and_a10_install_the_passages_hook_with_jev_and_nothing_else(
    lr: ModuleType,  # noqa: F811
) -> None:
    a, a10 = lr.arm_spec("A", lr.PROFILES["pilot-a"]), lr.arm_spec("A10", lr.PROFILES["pilot-a"])
    for spec in (a, a10):
        flags = spec.install
        at = flags.index("--provider")
        assert flags[:1] == ("--passages",) and flags[at : at + 2] == ("--provider", "jev")
        assert {"--no-guard", "--no-find", "--no-skill"} <= set(flags)
        assert flags[flags.index("--context-budget") + 1] == "0"
        assert not {"--memory", "--candor", "--guard", "--check-done", "--crawl"} & set(flags)
        assert spec.env == (("SANCHOPANZA_PROVIDER", "jev"),) and not spec.fresh
    assert "--passages-fraction" not in a.install
    assert a10.install[a10.install.index("--passages-fraction") + 1] == "0.10"
    assert lr.installed("A", lr.PROFILES["pilot-a"]) and not lr.installed("N", lr.PROFILES["gate"])


def test_only_the_passages_hook_is_kept_and_anything_else_is_a_break(lp: ModuleType) -> None:
    kept = lp.only_passages(REAL)
    commands = [h["command"] for es in kept["hooks"].values() for e in es for h in e["hooks"]]
    assert commands == [f"{PREFIX} passages-hook"] * 2  # the guard before, the cut after
    assert kept["hooks"]["PreToolUse"][0]["matcher"] == "Write|Edit|MultiEdit|NotebookEdit"
    assert kept["hooks"]["PostToolUse"][0]["matcher"] == "Bash|PowerShell|Read"
    unguarded = {**kept, "hooks": {"PostToolUse": kept["hooks"]["PostToolUse"]}}
    assert any("wired" in b for b in lp.install_breaks(unguarded, {}, "0.25"))
    assert kept["env"] == REAL["env"] and REAL["hooks"]["PreToolUse"]  # REAL left as it was
    assert lp.install_breaks(kept, {}, "0.25") == []
    assert any("passages-hook" in b for b in lp.install_breaks(REAL, {}, "0.25"))
    assert any("0.1" in b for b in lp.install_breaks(kept, {}, "0.1"))
    windowed = {**kept, "env": {**kept["env"], "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "193000"}}
    assert any("WINDOW" in b for b in lp.install_breaks(windowed, {}, "0.25"))
    assert any("server" in b for b in lp.install_breaks(kept, {"sanchopanza": {}}, "0.25"))
    no_jev = {**kept, "env": {**kept["env"], "SANCHOPANZA_PROVIDER": "local"}}
    assert any("jev" in b for b in lp.install_breaks(no_jev, {}, "0.25"))


@pytest.mark.skipif(not (LEAN_SRC / "sanchopanza" / "harness" / "passages_hook.py").exists()
                    or not MAIN_PY.exists(), reason="no lean worktree to install from")  # fmt: skip
@pytest.mark.parametrize("arm", ["A", "A10"])
def test_the_real_lean_install_with_the_arms_flags_prunes_to_the_passages_hook(
    lp: ModuleType, tmp_path: pathlib.Path, arm: str
) -> None:
    """The arms' flags against the `lean` CLI itself (free: an install asks no decider)."""
    env = {**os.environ, "PYTHONPATH": str(LEAN_SRC)}
    done = subprocess.run([str(MAIN_PY), "-m", "sanchopanza", "install", "--scope", "project",
                           "--write", *lp.arm_spec(arm).install], cwd=tmp_path, env=env,
                          capture_output=True, text=True)  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert not (tmp_path / ".mcp.json").exists()  # --no-find: no server
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert lp.install_breaks(settings, {}, lp.fraction_of(lp.arm_spec(arm).install))  # base hook
    assert lp.install_breaks(lp.only_passages(settings), {},
                             lp.fraction_of(lp.arm_spec(arm).install)) == []  # fmt: skip


# ---- journal facts and the abort -----------------------------------------------------------------


def test_the_summary_counts_cuts_chars_rerequests_and_both_rates(
    lp: ModuleType, tmp_path: pathlib.Path
) -> None:
    passed = ("passages", {"tool_use_id": "p", "acted": False, "chars_in": 9000,
                           "chars_out": 9000, "injected_chars": 9000})  # fmt: skip
    identical = ("passages_rerequest", {"cut": "c3", "kind": "whole", "identical": True})
    events = [*_cuts(4, whole=1, targeted=2), passed, identical, ("decision", {"cost_usd": 1e-5}),
              ("passages_rerequest", {"cut": "c0", "kind": "targeted"})]  # fmt: skip
    journal = _events(tmp_path / "journal.jsonl", events)
    s = lp.summary(lp.journal_events(journal))
    assert s["cuts"] == 4 and s["passed"] == 1
    assert s["chars_in"] == 32_000 and s["chars_out"] == 8_000 and s["injected_chars"] == 8_800
    assert s["rerequests_whole"] == 2 and s["rerequests_targeted"] == 3
    assert s["rerequests_whole_identical"] == 1
    assert s["cuts_rerequested"] == 4 and s["cuts_whole"] == 2
    assert s["r"] == pytest.approx(1.0) and s["r_whole"] == pytest.approx(0.5)
    facts = lp.call_facts(journal, skip=len(events) - 1)["passages"]
    assert facts["call"]["rerequests_targeted"] == 1 and facts["call"]["cuts"] == 0
    assert facts["arm"] == s
    assert lp.summary([])["r"] is None and lp.summary([])["r_whole"] is None


@pytest.mark.parametrize(("cuts", "whole", "stops"),
                         [(9, 9, False), (10, 5, False), (10, 6, True), (40, 21, True),
                          (40, 20, False)])  # fmt: skip
def test_the_arm_stops_past_half_whole_rerequests_after_ten_cuts(
    lp: ModuleType, tmp_path: pathlib.Path, cuts: int, whole: int, stops: bool
) -> None:
    s = lp.summary(lp.journal_events(_events(tmp_path / "j.jsonl", _cuts(cuts, whole))))
    why = lp.rerequest_stop(s)
    assert bool(why) is stops
    if stops:
        assert f"{whole} of {cuts} cuts" in why and "0.5" in why
    assert lp.MIN_CUTS == 10 and lp.MAX_WHOLE == 0.5


# ---- the runner end to end -----------------------------------------------------------------------


def _pilot(lr: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
           arm: str, plan: dict[str, int]) -> list[str]:  # fmt: skip
    monkeypatch.setattr(lr.run, "SANCHO", stand_in(tmp_path))
    monkeypatch.setattr(lr.run, "PYTHON", pathlib.Path(sys.executable))
    monkeypatch.setattr(lr.run, "KEYS", tmp_path / "keys")
    monkeypatch.setattr(lr.run, "decider_probe", lambda _key: "JevDecider")
    monkeypatch.setenv("FAKE_PASSAGES", json.dumps(plan))
    return _setup(lr, tmp_path, monkeypatch, (arm,), (PYD,), ("sonnet",), {})


def _row(tmp_path: pathlib.Path, arm: str) -> dict[str, Any]:
    path = tmp_path / "L" / "runs" / f"{PYD}-sonnet" / arm / "row.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.skipif(os.name != "nt", reason="the frozen stand-in is a Windows batch file")
def test_an_a_arm_runs_with_the_passages_hook_alone_and_its_rows_carry_the_journal(
    lr: ModuleType,  # noqa: F811
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = _pilot(lr, tmp_path, monkeypatch, "A", {"cuts": 2, "whole": 0, "targeted": 1})
    assert lr.main(argv) == 0
    row = _row(tmp_path, "A")
    assert row["stopped"] == "" and all(c["status"] == "ran" for c in row["calls"])
    assert all(c["passages"]["call"]["cuts"] == 2 for c in row["calls"])
    last = row["calls"][-1]["passages"]["arm"]
    assert last["cuts"] == 2 * len(row["calls"]) and last["r"] == 0.5 and last["r_whole"] == 0.0
    assert row["passages"] == last and row["calls"][0]["jev_decisions"] == 2
    work = tmp_path / "L" / "w" / f"{PYD}-sonnet-A"
    settings = json.loads((work / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for es in settings["hooks"].values() for e in es for h in e["hooks"]]
    assert len(commands) == 2 and all(c.endswith(" passages-hook") for c in commands)
    assert all("hook_env.py" in c for c in commands)
    assert settings["env"]["SANCHOPANZA_PROVIDER"] == "jev"
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in settings["env"]
    archive = settings["permissions"]["additionalDirectories"]
    assert archive == [(tmp_path / "L" / "runs" / f"{PYD}-sonnet" / "A" / "archive").as_posix()]
    assert json.loads((work / ".mcp.json").read_text(encoding="utf-8")) == {"mcpServers": {}}
    assert row["window"]["configured"] is None  # N's window: the server's


@pytest.mark.skipif(os.name != "nt", reason="the frozen stand-in is a Windows batch file")
def test_whole_rerequests_past_half_stop_the_arm_and_are_declared(
    lr: ModuleType,  # noqa: F811
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = _pilot(lr, tmp_path, monkeypatch, "A10", {"cuts": 4, "whole": 3})
    assert lr.main(argv) == 5
    row = _row(tmp_path, "A10")
    assert row["stopped"] == "rerequest"
    ran = [c for c in row["calls"] if c["status"] == "ran"]
    assert len(ran) == 3  # 4 and 8 cuts are under 10; 12 cuts with 9 whole stop it
    assert all(c["status"] == "NOT RUN (rerequest)" for c in row["calls"][3:])
    assert row["passages"]["cuts"] == 12 and row["passages"]["r_whole"] == 0.75
    settings = json.loads((tmp_path / "L" / "w" / f"{PYD}-sonnet-A10" / ".claude" /
                           "settings.json").read_text(encoding="utf-8"))  # fmt: skip
    assert settings["env"]["SANCHOPANZA_PASSAGES_FRACTION"] == "0.1"
    # not resumed: a second run says the arm is done
    assert lr.main(argv) == 0


# ---- the frozen commit, the plan and the money ---------------------------------------------------


@pytest.fixture
def ll(lr: ModuleType) -> ModuleType:  # noqa: F811
    import long_launch

    return long_launch


def test_the_pilot_commit_must_be_frozen_and_have_passages_hook_and_s_is_unchanged(
    ll: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit, match="not a commit"):
        ll.pilot_sancho("not-a-commit-xyz")
    if missing := missing_commits("3276a05", "aad9903", "cb0062e", *ll.long_pilot.NEEDS):
        pytest.skip(f"sealed commits not in this clone (CI checks out one): {missing}")
    with pytest.raises(SystemExit, match="674806b"):
        ll.pilot_sancho("3276a05")  # before the 402 breaker and jev-preflight
    sealed = ll.freeze.ROOT / "cb0062e36340-jev-mcp" / "Scripts" / "sanchopanza.exe"
    if sealed.exists():  # the S seal has no passages-hook: refused for A
        with pytest.raises(SystemExit, match="passages-hook"):
            ll.pilot_sancho("cb0062e")
    with pytest.raises(SystemExit, match="sealed at cb0062e"):
        ll.frozen_sancho("aad9903")  # S: still the owner's seal only
    monkeypatch.setattr(ll.freeze, "ROOT", tmp_path / "frozen-root")
    with pytest.raises(SystemExit, match="freeze.py"):
        ll.pilot_sancho("aad9903")
    full = ll.git("rev-parse", "aad9903").stdout.strip()
    target = tmp_path / "frozen-root" / f"{full[:12]}-jev-mcp"
    (target / "Scripts").mkdir(parents=True)
    (target / "Scripts" / "sanchopanza.exe").write_bytes(b"")
    (target / "stamp.json").write_text(json.dumps({"commit": full, "extras": ["jev", "mcp"]}),
                                       encoding="utf-8")  # fmt: skip
    monkeypatch.setattr(ll.long_pilot, "passages_refusal", lambda exe: "")
    assert ll.pilot_sancho("aad9903") == target / "Scripts" / "sanchopanza.exe"
    monkeypatch.setattr(ll.long_pilot, "passages_refusal", lambda exe: "no passages-hook")
    with pytest.raises(SystemExit, match="passages-hook"):
        ll.pilot_sancho("aad9903")


@pytest.mark.skipif(os.name != "nt", reason="the frozen stand-in is a Windows batch file")
def test_the_passages_check_runs_the_copys_own_help(
    lp: ModuleType, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = stand_in(tmp_path)
    assert lp.passages_refusal(exe) == ""
    monkeypatch.setenv("FAKE_NO_PASSAGES", "1")
    assert "passages-hook" in lp.passages_refusal(exe)
    assert "passages-hook" in lp.passages_refusal(tmp_path / "missing.exe")


def test_the_plan_prints_the_caps_the_ceiling_the_install_and_the_abort_rule(
    ll: ModuleType,
) -> None:
    known = {n: {"bugs": [{}] * 60} for n in GATE}
    for arm, flag in (("A", "--passages --provider jev"),
                      ("A10", "--passages --passages-fraction 0.10 --provider jev")):  # fmt: skip
        text = "\n".join(ll.plan_lines("pilot-a", known, list(known), pathlib.Path("Z:/nowhere"),
                                       80.0, arms=(arm,)))  # fmt: skip
        assert (
            "sonnet (claude-sonnet-5-5): 4.50 USD per call (--max-budget-usd at most 3.00" in text
        )
        assert f"38.00 per chain and arm, arms {arm}" in text
        assert (
            f"{arm}: one turn past a cap costs up to 6.48 USD (context at the window "
            "1000000); at that context the arm starts no call past 27.02"
        ) in text
        assert f"expected {arm} 24.97-24.97 USD" in text and "N's cost model" in text
        assert "caps held 76.00 USD" in text and "ceiling 80.00 (hard, in code)" in text
        assert flag in text and "--no-guard --no-find --no-skill --context-budget 0" in text
        assert ">= 10 cuts" in text and "more than 0.5" in text and "exit 5" in text


def test_spend_of_an_arm_outside_the_profile_is_held_outside_its_blocks(
    lr: ModuleType,  # noqa: F811
    tmp_path: pathlib.Path,
) -> None:
    layout = lr.Layout(tmp_path)
    folder = layout.runs / f"{GATE[0]}-sonnet" / "A"
    folder.mkdir(parents=True)
    row = {"run": f"{GATE[0]}-sonnet", "arm": "A", "calls": [{"owner_usd": 50.0}]}
    (folder / "row.json").write_text(json.dumps(row), encoding="utf-8")
    a10 = lr.PROFILES["pilot-a"].with_arms(("A10",))
    blocks, outside = lr.held(layout, a10, list(GATE), ["sonnet"])
    assert [c for *_x, c in blocks] == [38.0, 38.0] and outside == 50.0  # 126 > 80: refused
    blocks, outside = lr.held(layout, lr.PROFILES["pilot-a"], list(GATE), ["sonnet"])
    assert [c for *_x, c in blocks] == [50.0, 38.0] and outside == 0.0
