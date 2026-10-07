"""The launch's parts, each on its own: the check-done term of the cost model, the window the
session reports, the give-ups apart, the manifests, the sealed sanchopanza, the Jev preflight and
the environment the agents get. Free: no model, no API, no Jev, no Docker."""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
FAKE = ROOT / "tests" / "fixtures" / "long_fake"


@pytest.fixture
def m(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """benchmarks/adopt's modules for one test, then out of sys.modules and sys.path again:
    their plain names (`run`, `meter`) are other benchmarks' too, so any module of that name
    already loaded is set aside for the test and put back after."""
    path = list(sys.path)
    plain = {f.stem for d in (ADOPT, ADOPT.parent, ADOPT.parent / "memory_carry")
             for f in d.glob("*.py")}  # fmt: skip
    aside = {n: sys.modules.pop(n) for n in plain if n in sys.modules}
    before = set(sys.modules)
    monkeypatch.syspath_prepend(str(ADOPT))
    names = ("arm_files", "costmodel", "long_call", "long_guard", "long_launch",
             "long_report", "long_run", "long_window", "run")  # fmt: skip
    yield SimpleNamespace(**{n: importlib.import_module(n) for n in names})
    for name in set(sys.modules) - before:
        sys.modules.pop(name, None)
    sys.modules.update(aside)
    sys.path[:] = path


# ---- check-done in the cost model (STATUS-runner item 9) ----------------------------------------


def test_check_done_rates_come_from_the_gate_a_data(m: SimpleNamespace) -> None:
    assert pytest.approx(41 / 17) == m.costmodel.REQUESTS_PER_SEND_BACK  # 23 + 18 after 10 + 7
    assert m.costmodel.CHECK_DONE["low"] == pytest.approx(13 / 342)
    assert m.costmodel.CHECK_DONE["mid"] == pytest.approx(13 / 40 * 286 / 313 + 27 / 40 * 13 / 342)
    assert m.costmodel.CHECK_DONE["high"] == pytest.approx(17 / 20)
    assert (
        m.costmodel.CHECK_DONE["low"]
        < m.costmodel.CHECK_DONE["mid"]
        < m.costmodel.CHECK_DONE["high"]
    )


def test_the_check_done_term_charges_s_only_and_grows_with_the_rate(m: SimpleNamespace) -> None:
    table = m.costmodel.arms("sonnet-5.5", 339, open_requests=62)
    assert table["N"]["send_back_requests"] == table["N-early"]["send_back_requests"] == 0
    s = table["S"]
    assert s["send_backs"] == pytest.approx(62 * m.costmodel.CHECK_DONE["mid"], abs=0.05)
    assert s["send_back_requests"] == round(62 * m.costmodel.CHECK_DONE["mid"] * 41 / 17)
    assert s["check_done_usd"] > 0
    arms = m.costmodel.arms
    terms = [arms("sonnet-5.5", 339, open_requests=62, scenario=k)["S"]["check_done_usd"]
             for k in ("low", "mid", "high")]  # fmt: skip
    assert terms == sorted(terms) and terms[0] > 0
    # an extra turn costs what a request costs at that context: zero rate, zero dollars
    none = m.costmodel.with_check_done("sonnet-5.5", 339, m.costmodel.CheckDone(0.0, 62),
                                     threshold=160_000)  # fmt: skip
    assert none["check_done_usd"] == 0 and none["send_back_requests"] == 0


def test_the_calibration_and_the_prereg_table_are_unchanged_by_the_term(m: SimpleNamespace) -> None:
    assert m.costmodel.calib()["usd"] == 8.39  # B2 N measured 8.74
    l60 = m.costmodel.arms("sonnet-5.5", 339, open_requests=62)
    assert l60["N"]["usd"] == 24.97 and l60["N-early"]["usd"] == 17.14
    assert m.costmodel.expected("opus", 60, 2, ("N",), 160_000)["N"] == (25.76, 42.46)


def test_a_threshold_with_no_room_after_a_compaction_is_refused_not_looped(
    m: SimpleNamespace,
) -> None:
    with pytest.raises(ValueError, match="no room"):
        m.costmodel.session_cost("haiku-4.5", 100, threshold=37_500)
    small = m.costmodel.session_cost("haiku-4.5", 240, threshold=67_000, reread_tok=25_000,
                                   reread_req=10)  # fmt: skip
    assert small["compactions"] > 0 and small["requests"] < 240 * 3


# ---- the window ---------------------------------------------------------------------------------


def test_the_debug_line_is_read_and_the_file_trimmed(
    m: SimpleNamespace, tmp_path: pathlib.Path
) -> None:
    debug = tmp_path / "debug-1.log"
    debug.write_text("x [DEBUG] [api] noise\n"
                     "x [DEBUG] autocompact: tokens=120000 level=ok effectiveWindow=380000\n"
                     "x [DEBUG] autocompact: tokens=150000 level=warn effectiveWindow=380000\n",
                     encoding="utf-8")  # fmt: skip
    seen = m.long_window.read_debug(debug)
    assert seen == {"lines": 2, "effective": 380_000, "effective_seen": [380_000],
                    "max_tokens": 150_000, "levels": ["ok", "warn"]}  # fmt: skip
    m.long_window.trim_debug(debug)
    assert "[api]" not in debug.read_text(encoding="utf-8")
    assert m.long_window.read_debug(tmp_path / "absent.log") == {}


def test_the_source_is_env_the_server_cache_or_a_default(
    m: SimpleNamespace, tmp_path: pathlib.Path
) -> None:
    config = tmp_path / "claude-config"
    config.mkdir()
    debug = tmp_path / "d.log"
    debug.write_text("autocompact: tokens=1 level=ok effectiveWindow=980000\n", encoding="utf-8")
    plain = m.long_window.call_window(debug, config, None)
    assert plain["source"].startswith("server or model default") and plain["window"] == 1_000_000
    (config / ".claude.json").write_text(
        json.dumps({"autoCompactWindowsCache": {"claude-opus-5-5": 1_000_000}, "other": 1}), "utf-8"
    )
    cached = m.long_window.call_window(debug, config, None)
    assert cached["source"] == "clientdata (server cache)"
    assert cached["server_cache"] == {"autoCompactWindowsCache": {"claude-opus-5-5": 1_000_000}}
    assert m.long_window.call_window(debug, config, "193000")["source"] == "env"


def test_every_arm_gets_the_same_debug_flags_on_its_command(
    m: SimpleNamespace, tmp_path: pathlib.Path
) -> None:
    debug = tmp_path / "debug-3.log"
    cmd = m.long_call.command(("claude",), "claude-opus-5-5", "fix", "s1", 3.2, tmp_path / "m.json",
                            debug)  # fmt: skip
    assert "--debug=autocompact" in cmd and f"--debug-file={debug}" in cmd
    assert cmd[-2:] == ["--resume", "s1"]


def test_the_gate_reads_the_reported_window_with_its_source(m: SimpleNamespace) -> None:
    row = {"window": {"value": 1_000_000, "configured": None, "effective_reported": 980_000,
                      "source": "clientdata (server cache)"}, "calls": []}  # fmt: skip
    found = m.long_report.window_evidence(row, 300_000)
    assert found["value"] == 1_000_000 and found["bound"] == "exact"
    assert found["source"].startswith("session debug line; clientdata")
    old = {"window": {"value": None, "source": "server default"}, "calls": []}
    assert m.long_report.window_evidence(old, 300_000)["bound"] == "at least"


# ---- give-ups, apart from wrong fixes -----------------------------------------------------------


def _patch(files: dict[str, str]) -> str:
    return "".join(f"diff --git a/{p} b/{p}\n+{body}\n" for p, body in files.items())


def test_give_ups_are_counted_apart_with_their_context(
    m: SimpleNamespace, tmp_path: pathlib.Path
) -> None:
    diffs = {
        1: {"src/a.py": "x"},
        2: {"src/a.py": "x", "changes/2.md": "Ref"},  # only the note: no fix
        3: {"src/a.py": "x", "changes/2.md": "Ref", "src/b.py": "y"},
        4: {"src/a.py": "x", "changes/2.md": "Ref", "src/b.py": "y", "src/c.py": "z"},
    }
    for k, files in diffs.items():
        (tmp_path / f"diff-{k}.patch").write_text(_patch(files), encoding="utf-8")
    calls = [
        {"request": 1, "kind": "bug", "status": "ran", "peak_context": 40_000},
        {"request": 2, "kind": "bug", "status": "ran", "peak_context": 160_000},
        {
            "request": 3,
            "kind": "bug",
            "status": "ran",
            "peak_context": 180_000,
            "result_tail": "I fixed b.py.",
        },
        {
            "request": 4,
            "kind": "bug",
            "status": "ran",
            "peak_context": 90_000,
            "result_tail": "I could not reproduce the failure, so I changed c.py defensively.",
        },
        {"request": 5, "kind": "callback", "status": "ran", "peak_context": 95_000},
    ]
    found = m.long_report.give_ups(tmp_path, {"calls": calls})
    assert [i["request"] for i in found["items"]] == [2, 4]
    assert found["no_code_change"] == 1 and found["said_so"] == 1
    assert found["at_or_past_150k"] == 1 and found["median_context"] == 125_000
    assert m.long_report.code_part(_patch({"changes/1.md": "Ref", "x.py": "1"})).count("x.py") == 2
    # With the grade: a give-up whose bug ends resolved (fixed under an earlier bug) is no give-up
    # at all (indagis-e8, 2026-10-07); `unresolved` counts only those the grade left unresolved.
    calls_ids = [{**c, "instance_id": f"b{c['request']}"} for c in calls]
    grade = {"bugs": [{"instance_id": "b2", "resolved": True},
                      {"instance_id": "b4", "resolved": False}]}  # fmt: skip
    graded = m.long_report.give_ups(tmp_path, {"calls": calls_ids}, grade)
    assert graded["give_ups"] == 2 and graded["unresolved"] == 1
    assert graded["unresolved_at_or_past_150k"] == 0 and graded["unresolved_contexts"] == [90_000]
    assert [i["resolved"] for i in graded["items"]] == [True, False]
    assert "unresolved" not in m.long_report.give_ups(tmp_path, {"calls": calls_ids})
    unknown = m.long_report.give_ups(tmp_path, {"calls": calls_ids}, {"bugs": []})
    assert unknown["unresolved"] == 0 and [i["resolved"] for i in unknown["items"]] == [None, None]


# ---- manifests, the seal, the preflight, the agents' environment --------------------------------


def test_a_chain_without_its_manifest_or_with_another_digest_is_refused(
    m: SimpleNamespace,
    tmp_path: pathlib.Path,
) -> None:
    chain = {"image": "i", "tag": "t", "bugs": [{"instance_id": "b1"}]}
    known = {"c": chain}
    assert "no manifest" in m.long_guard.manifest_refusal(
        ["c"], known, tmp_path, m.run.chain_digest
    )
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"valid": False, "sha256": m.run.chain_digest(chain)}), "utf-8")
    assert "valid" in m.long_guard.manifest_refusal(["c"], known, tmp_path, m.run.chain_digest)
    path.write_text(json.dumps({"valid": True, "sha256": "0" * 64}), "utf-8")
    assert "not the one" in m.long_guard.manifest_refusal(
        ["c"], known, tmp_path, m.run.chain_digest
    )
    path.write_text(json.dumps({"valid": True, "sha256": m.run.chain_digest(chain)}), "utf-8")
    assert m.long_guard.manifest_refusal(["c"], known, tmp_path, m.run.chain_digest) == ""


def test_the_real_pydantic_gate_manifest_matches_its_validated_chain_when_cached(
    m: SimpleNamespace,
) -> None:
    manifest = ADOPT / "long60" / "pydantic__pydantic-long60-1.json"
    body = json.loads(manifest.read_text(encoding="utf-8"))
    assert body["valid"] is True and body["chain"] == "pydantic__pydantic-long60-1"
    try:
        known = m.run.chains()
    except (OSError, ValueError):
        pytest.skip("no validated chains in this machine's cache")
    if body["chain"] not in known:
        pytest.skip("the chain is not in this machine's cache")
    assert m.long_guard.manifest_refusal([body["chain"]], known, manifest.parent,
                                       m.run.chain_digest) == ""  # fmt: skip


def test_the_seal_must_carry_gate_a_and_the_402_breaker_and_be_frozen(m: SimpleNamespace) -> None:
    with pytest.raises(SystemExit, match="not a commit"):
        m.long_launch.frozen_sancho("not-a-commit-xyz")
    with pytest.raises(SystemExit, match="f2a0fe2"):
        m.long_launch.frozen_sancho("3276a05")  # long-bench's base: before gate A
    with pytest.raises(SystemExit, match="sealed at cb0062e"):
        m.long_launch.frozen_sancho("aad9903")  # carries both, but is not the seal
    full = m.long_launch.git("rev-parse", "cb0062e").stdout.strip()
    frozen = m.long_launch.freeze.ROOT / f"{full[:12]}-jev-mcp" / "Scripts" / "sanchopanza.exe"
    if frozen.exists():
        assert m.long_launch.frozen_sancho("cb0062e") == frozen
    else:
        with pytest.raises(SystemExit, match="freeze.py"):
            m.long_launch.frozen_sancho("cb0062e")


@pytest.mark.parametrize("code", [0, 10, 11, 12, 13, 14])
def test_the_preflight_exit_code_is_the_launchs(m: SimpleNamespace, tmp_path: pathlib.Path,
                                                monkeypatch: pytest.MonkeyPatch,
                                                code: int) -> None:  # fmt: skip
    monkeypatch.setenv("FAKE_PREFLIGHT_EXIT", str(code))
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-key")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "ours"))  # must not reach the preflight
    assert m.long_launch.preflight(pathlib.Path(sys.executable), tmp_path,
                                 str(FAKE / "preflight")) == code  # fmt: skip
    text = (tmp_path / "preflight.txt").read_text(encoding="utf-8")
    assert f"exit {code} ({m.long_launch.PREFLIGHT_CODES[code]})" in text and "key set" in text


def test_the_agents_and_hooks_do_not_inherit_the_runners_pythonpath(
    m: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", r"C:\somewhere\src")
    monkeypatch.setenv("PYTHONHOME", r"C:\py")
    env = m.run.child_env("tag", "base")
    assert "PYTHONPATH" not in env and "PYTHONHOME" not in env
    assert env["DISABLE_AUTOUPDATER"] == "1"


def test_the_launch_plan_prints_caps_and_expected_cost_without_spending(m: SimpleNamespace) -> None:
    known = {n: {"bugs": [{}] * 60} for n in ("conan-io__conan-long60-1",
                                              "pydantic__pydantic-long60-1")}  # fmt: skip
    lines = m.long_launch.plan_lines("gate", known, list(known), pathlib.Path("Z:/nowhere"), 230.0)
    text = "\n".join(lines)
    assert "--max-budget-usd at most 3.00" in text and "at most 3.20" in text
    assert "N: one turn past a cap costs up to 6.48 USD (context at the window 1000000)" in text
    assert "up to 10.80 USD" in text and "no call past 56.20 spent of its 75.00" in text
    assert "room for its cap and one more turn" in text
    assert "60 bugs + 2 callbacks; expected N 24.97-24.97 USD" in text
    assert "expected N 25.76-42.46 USD" in text
    assert "expected total 101.46-134.86 USD" in text and "caps held 226.00 USD" in text


def test_the_launcher_module_is_importable_without_side_effects(m: SimpleNamespace) -> None:
    done = subprocess.run([sys.executable, "-c", "import long_launch"], cwd=ADOPT,
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(ROOT / "src")})  # fmt: skip
    assert done.returncode == 0, done.stderr


def test_a_live_launcher_or_runner_of_the_root_refuses_a_second_launch(
    m: SimpleNamespace, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = {"pid": os.getpid(), "command_line": "x", "created": "t"}
    monkeypatch.setattr(m.long_launch.long_guard, "process_info",
                        lambda pid: {"command_line": "x", "created": "t"} if pid == os.getpid()
                        else None)  # fmt: skip
    history = [{"launcher": me}, {"launcher": {"pid": 1}}]
    (tmp_path / "launch.json").write_text(json.dumps(history), encoding="utf-8")
    assert "launcher" in m.long_launch.busy(tmp_path)
    (tmp_path / "launch.json").write_text(json.dumps(history[1:]), encoding="utf-8")
    assert m.long_launch.busy(tmp_path) == ""
    (tmp_path / "long-run.status.json").write_text(json.dumps(me), encoding="utf-8")
    assert "runner" in m.long_launch.busy(tmp_path)


# ---- one turn past a cap (live probe 2026-10-06: Opus given 0.34 USD spent 0.94) ---------------


def test_the_worst_turn_is_the_window_written_at_one_hour_plus_a_maximal_answer(
    m: SimpleNamespace,
) -> None:
    money = m.long_launch.long_money
    assert money.turn_cost("claude-opus-5-5", 1_000_000) == pytest.approx(10 + 0.8)
    assert money.turn_cost("claude-sonnet-5-5", 193_000) == pytest.approx(1.158 + 0.48)
    assert money.turn_cost("claude-haiku-4-5-20251001", 100_000) == pytest.approx(0.2 + 0.16)
    # the next call's turn: its context + 50k, never past the window
    assert money.overshoot("claude-opus-5-5", 300_000, 193_000) == pytest.approx(2.73)
    assert money.overshoot("claude-opus-5-5", 100_000, None) == pytest.approx(1.5 + 0.8)


def test_the_measured_case_is_refused_where_the_old_check_let_it_through(
    m: SimpleNamespace,
) -> None:
    money = m.long_launch.long_money
    budget, spent_measured = 0.34, 0.94  # the probe: Opus 5.5, a resumed call
    over = money.overshoot("claude-opus-5-5", 0, None)
    assert over >= spent_measured - budget  # the allowance covers what the probe overshot
    ceiling, spent = 10.0, 10.0 - budget  # 0.34 left: exactly the call's cap
    assert spent + budget <= ceiling  # the old check: the call would have started
    assert "ceiling" in money.room_refusal(spent, budget, over, ceiling, "ceiling")
    assert money.room_refusal(spent - over, budget, over, ceiling, "ceiling") == ""


# ---- the S seal (owner, 2026-10-06: cb0062e, the install's default guard) ----------------------


def test_s_sets_no_guard_chooser_of_its_own(m: SimpleNamespace) -> None:
    assert not any(k.endswith("GUARD_CHOOSER") for k, _v in m.long_run.S_ENV)
    assert m.long_launch.SEAL_COMMIT == "cb0062e"


def test_s_settings_at_the_seal_deliver_the_guard_in_six_parts(
    m: SimpleNamespace, tmp_path: pathlib.Path
) -> None:
    full = m.long_launch.git("rev-parse", "cb0062e").stdout.strip()
    exe = m.long_launch.freeze.ROOT / f"{full[:12]}-jev-mcp" / "Scripts" / "sanchopanza.exe"
    if not exe.exists():
        pytest.skip("the seal is not frozen here (benchmarks/adopt/freeze.py cb0062e)")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    spec = m.long_run.arm_spec("S", m.long_run.PROFILES["dev"])
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SANCHOPANZA_", "SANCHO_", "TYPESAFE_", "PYTHONPATH"))}
    done = subprocess.run([str(exe), "install", "--scope", "project", "--write", *spec.install],
                          cwd=tmp_path, env=env, capture_output=True, text=True)  # fmt: skip
    assert done.returncode == 0, done.stderr
    m.arm_files.write_env_settings(tmp_path, spec.env)  # what the runner adds for S
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    compact = [h["command"] for e in settings["hooks"]["SessionStart"]
               if e.get("matcher") == "compact" for h in e["hooks"]]  # fmt: skip
    assert [c.split("guard-hook ", 1)[1] for c in compact] == [
        f"--part {i} --parts 6" for i in range(1, 7)]
    assert any("guard-hook --parts 6" in h["command"] for e in settings["hooks"]["PreCompact"]
               for h in e["hooks"])  # fmt: skip
    assert "SANCHOPANZA_GUARD_CHOOSER" not in settings["env"]
    assert settings["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "193000"
    assert settings["env"]["SANCHOPANZA_CANDOR_MODE"] == "observe"
    assert m.arm_files.guard_parts(tmp_path) == (
        "guard: 6 SessionStart(compact) parts, chooser the install's default")
