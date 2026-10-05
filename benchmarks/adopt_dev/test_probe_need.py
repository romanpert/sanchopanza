"""Free tests of the need probe (no Docker, no API, no Jev). In its own process, since the probe
pins `common.py` to the `need` profile on import:

Run: .venv/Scripts/python.exe -m pytest benchmarks/adopt_dev/test_probe_need.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("ADOPT_DEV_PROFILE", "need")
try:
    from . import common
    from . import probe_need as need
except RuntimeError as exc:  # common.py pinned to another profile by an earlier test module
    pytest.skip(f"run this file in its own process: {exc}", allow_module_level=True)

from . import probe_alwaysload as base  # noqa: E402
from .need_facts import FIND_TOOL, api_call_of_each, describe, find_hidden  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ROOT = Path.home() / ".cache" / "sanchopanza" / "adopt"
D_COMMIT = "7a39a1f0d4ff8e9cf5c99046ee0aa818ffe955d9"


# ---- paths and plan ------------------------------------------------------------------------------


def test_paths_caps_and_frozen_copy() -> None:
    assert common.PROFILE == "need" and common.FROZEN_COMMIT == D_COMMIT
    assert common.OUT == ROOT / "dev-need" and common.WORK == ROOT / "work-dnd"
    assert common.FROZEN_EXE == ROOT / "frozen" / "7a39a1f0d4ff-jev-mcp" / "Scripts" / \
        "sanchopanza.exe"  # fmt: skip
    assert os.environ["ADOPT_SANCHO"] == str(common.FROZEN_EXE)
    assert common.run.SANCHO == common.FROZEN_EXE  # the sealed modules run this copy
    assert (common.TOTAL_CAP_USD, common.CALL_CAP_USD) == (12.00, 1.50)
    assert common.MODEL == "claude-haiku-4-5-20251001" and common.CLAUDE_VERSION == "2.1.285"


def test_plan_is_the_need_set_s_only() -> None:
    table = json.loads(common.NEED_TABLE.read_text(encoding="utf-8"))
    assert [n for n, _ in common.PLAN] == table["dev_set"] == list(common.NEED)
    assert all(arms == ("S",) for _, arms in common.PLAN) and len(common.PLAN) == 10
    assert common.plan_refusal() is None
    assert not {n for n, _ in common.PLAN} & common.phase_d_ids()


def test_rows_land_where_the_phase_d_ledger_globs(tmp_path: Path, monkeypatch) -> None:
    """`run_d.spent_dev` sums `<root>/*/*/row.json` and `*/*/abandoned.json`, as `spent` does."""
    monkeypatch.setattr(base, "OUT", tmp_path)
    _row(tmp_path / "sympy__sympy-20428" / "S", 0.70, jev=0.01)
    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.glob("*/*/row.json")] == \
        ["sympy__sympy-20428/S/row.json"]  # fmt: skip
    assert base.spent() == 0.71


# ---- refusals ------------------------------------------------------------------------------------


def _import(env_extra: dict[str, str], module: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("ADOPT_SANCHO", "ADOPT_DEV_PROFILE")}
    return subprocess.run([sys.executable, "-c", f"import {module}"], cwd=REPO,
                          env={**env, **env_extra}, capture_output=True, text=True,
                          timeout=120)  # fmt: skip


def test_a_copy_that_is_not_7a39a1f_is_refused() -> None:
    other = ROOT / "frozen" / "1ea9302c8b4c-jev-mcp" / "Scripts" / "sanchopanza.exe"
    done = _import({"ADOPT_DEV_PROFILE": "need", "ADOPT_SANCHO": str(other)},
                   "benchmarks.adopt_dev.common")  # fmt: skip
    assert done.returncode != 0 and "is not this profile's frozen copy" in done.stderr
    ok = _import({"ADOPT_DEV_PROFILE": "need", "ADOPT_SANCHO": str(common.FROZEN_EXE)},
                 "benchmarks.adopt_dev.probe_need")  # fmt: skip
    assert ok.returncode == 0, ok.stderr[-500:]


def test_the_probe_refuses_common_pinned_to_another_profile() -> None:
    done = _import({"ADOPT_DEV_PROFILE": "alwaysload"}, "benchmarks.adopt_dev.probe_need")
    assert done.returncode != 0 and "pinned to 'alwaysload'" in done.stderr


def _row(folder: Path, cost: float, jev: float = 0.0, status: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    call = {"cost_usd": cost, **({"status": status} if status else {})}
    (folder / "row.json").write_text(json.dumps({"calls": [call], "jev_usd": jev}), "utf-8")


class Reached(Exception):
    """The session would have started."""


def _arm_setup(tmp_path: Path, monkeypatch, spent: float) -> dict:
    monkeypatch.setattr(base, "OUT", tmp_path)
    monkeypatch.setattr(base.docker_env, "disk_free_gb", lambda *_a: 100.0)
    _row(tmp_path / "earlier" / "S", spent)
    return {"instance_id": "sympy__sympy-20916"}


def test_cap_refuses_a_session_that_does_not_fit(tmp_path: Path, monkeypatch) -> None:
    row = _arm_setup(tmp_path, monkeypatch, 10.51)

    def session(*_a: object) -> dict:
        raise Reached

    monkeypatch.setattr(base, "session", session)
    with pytest.raises(base.Stop, match="cap: 10.51 USD spent"):
        base.run_arm(row, "S", tmp_path / "k")


def test_cap_lets_the_last_one_that_fits_start(tmp_path: Path, monkeypatch) -> None:
    row = _arm_setup(tmp_path, monkeypatch, 10.50)

    def session(*_a: object) -> dict:
        raise Reached

    monkeypatch.setattr(base, "session", session)
    with pytest.raises(Reached):
        base.run_arm(row, "S", tmp_path / "k")


def test_a_usage_limit_error_stops_the_batch(tmp_path: Path, monkeypatch) -> None:
    row = _arm_setup(tmp_path, monkeypatch, 0.0)
    record = {"instance": row["instance_id"], "arm": "S", "decider": ["JevDecider"],
              "calls": [{"status": base.NOT_RUN_ERROR, "cost_usd": 0.0, "subtype": "success",
                         "turns": 1}],
              "probe": {"watched_calls": {}, "deferral": {"find_deferred": False},
                        "caching": {"ok": False},
                        "latency": {"to_init_s": 1, "to_first_assistant_s": 2}}}  # fmt: skip
    monkeypatch.setattr(base, "session", lambda *_a: record)
    with pytest.raises(base.Stop, match="usage-limit"):
        base.run_arm(row, "S", tmp_path / "k")


# ---- the session's facts -------------------------------------------------------------------------


def _use(mid: str, uid: str, name: str, given: dict, parent: str | None = None) -> dict:
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"id": mid, "content": [
                {"type": "tool_use", "id": uid, "name": name, "input": given}]}}  # fmt: skip


def _result(uid: str, text: str, error: bool = False) -> dict:
    return {"type": "user", "parent_tool_use_id": None,
            "message": {"content": [{"type": "tool_result", "tool_use_id": uid,
                                     "content": text, "is_error": error}]}}  # fmt: skip


def _evidence(tmp_path: Path, tools: list[str], always: bool = True, deferred: bool = False
              ) -> Path:  # fmt: skip
    ev = tmp_path / "ev"
    ev.mkdir()
    init = {"type": "system", "subtype": "init", "tools": tools,
            "mcp_servers": [{"name": "sanchopanza", "status": "connected"}]}  # fmt: skip
    events = [
        init,
        _use("m1", "t1", "Grep", {"pattern": "Poly"}), _result("t1", "a.py\nb.py"),
        _use("m1", "t2", "ToolSearch", {"query": "select:x"}), _result("t2", "ok"),
        _use("m2", "t3", FIND_TOOL, {"query": "clear_denoms"}), _result("t3", "sympy/x.py"),
        _use("m2", "s1", "Grep", {"pattern": "inner"}, parent="t4"),  # a subagent's: ignored
        _use("m3", "t4", "Agent", {"subagent_type": "Explore", "prompt": "p"}),
        _result("t4", "Agent type 'default' not found", error=True),
        _use("m4", "t5", "Read", {"file_path": "C:\\w\\sympy\\polys\\polytools.py"}),
        _result("t5", "src"),
    ]  # fmt: skip
    (ev / "stream-1.jsonl").write_text("\n".join(json.dumps(e) for e in events), "utf-8")
    delta = {"type": "deferred_tools_delta", "addedNames": [FIND_TOOL if deferred else "Monitor"]}
    (ev / "transcript.jsonl").write_text(json.dumps({"attachment": delta}), "utf-8")
    server = {"command": "x", "args": [], **({"alwaysLoad": True} if always else {})}
    (ev / "mcp.json").write_text(json.dumps({"mcpServers": {"sanchopanza": server}}), "utf-8")
    lines = [{"sub": "find-mcp", "event": "server start", "key": True},
             {"sub": "hook", "event": "PreToolUse", "key": True}]  # fmt: skip
    (ev / "hooks.jsonl").write_text("\n".join(json.dumps(x) for x in lines), "utf-8")
    decision = {"kind": "decision", "data": {"provider": "jev", "cost_usd": 3e-5, "error": None}}
    (ev / "journal.jsonl").write_text(json.dumps(decision), "utf-8")
    return ev


def test_facts_of_a_session(tmp_path: Path) -> None:
    ev = _evidence(tmp_path, ["Bash", FIND_TOOL])
    facts = describe(ev, ["sympy/polys/polytools.py"], {"decider": ["JevDecider"]})
    assert facts["find_visible"] and facts["find_hidden"] == ""
    assert facts["find_calls"] == [{"call": 3, "api_call": 2, "query": "clear_denoms",
                                    "kind": "code", "error": False}]  # fmt: skip
    assert [(c["call"], c["api_call"]) for c in facts["toolsearch_calls"]] == [(2, 1)]
    assert facts["agent_failures"] == 1 and facts["agent_calls"][0]["call"] == 4
    assert "not found" in facts["agent_calls"][0]["error_text"]
    assert facts["searches_before_gold_read"] == 1  # the Grep; find and the subagent's do not
    assert facts["reach"]["finds_before"] == 1 and facts["tool_calls"] == 5
    treated = facts["treatment"]
    assert treated["decider"] == ["JevDecider"] and treated["server_at_init"] == "connected"
    assert treated["server_started"] and treated["decisions_by_provider"] == {"jev": 1}
    assert api_call_of_each(ev / "stream-1.jsonl") == [1, 1, 2, 3, 4]


@pytest.mark.parametrize(
    ("tools", "always", "deferred", "why"),
    [(["Bash"], True, False, "not in the init line's tools"),
     (["Bash", FIND_TOOL], True, True, "deferred"),
     (["Bash", FIND_TOOL], False, False, "no alwaysLoad")],
)  # fmt: skip
def test_find_hidden_reasons(tmp_path: Path, tools, always, deferred, why) -> None:
    assert why in find_hidden(_evidence(tmp_path, tools, always, deferred))


def test_find_not_visible_stops_only_a_session_that_ran(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(need, "OUT", tmp_path)
    monkeypatch.setattr(need, "gold_of", lambda _n: ("sympy/polys/polytools.py",))
    ev = _evidence(tmp_path, ["Bash"])
    (tmp_path / "x").mkdir()
    ev.rename(tmp_path / "x" / "S")
    record = {"instance": "x", "arm": "S", "decider": ["JevDecider"], "calls": [{}]}
    (tmp_path / "x" / "S" / "row.json").write_text(json.dumps(record), "utf-8")
    with pytest.raises(base.Stop, match="not visible"):
        need.after_session(record)
    assert (tmp_path / "x" / "S" / "need-facts.json").exists()
    need.after_session({**record, "calls": [{"status": base.NOT_RUN_ERROR}]})  # the driver's stop


def test_an_empty_diff_is_not_resolved_without_the_harness(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(need, "OUT", tmp_path)
    ev = tmp_path / "x" / "S"
    ev.mkdir(parents=True)
    (ev / "final.patch").write_text("", encoding="utf-8")
    monkeypatch.setattr(need.subprocess, "run", lambda *_a, **_k: pytest.fail("harness ran"))
    assert need.grade_arm("x") is False
    assert json.loads((ev / "grade.json").read_text("utf-8"))["reason"] == "empty diff"
