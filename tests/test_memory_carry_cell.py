"""Arm S of the carry runner (`carry_s.py`, `carry_hook.py ... sub`) and the memory cell's reading
(`cell.py`), with no session: `claude` is a fake, the install is the real one (local, free), and
no hook here has a key, so nothing calls a provider."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from .helpers import bench_module
from .test_memory_carry_cross import RESULTS
from .test_memory_carry_f1 import FAKE, THREE, FakeClaude
from .test_memory_carry_parallel import THREADS

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "memory_carry"
carry = bench_module(BENCH, "carry")
carry_s = bench_module(BENCH, "carry_s")
cell = bench_module(BENCH, "cell")
PARALLEL = bench_module(BENCH, "scenes_parallel").PARALLEL


def commands(settings: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(event, entry.get("matcher", ""), h["command"])
            for event, entries in settings["hooks"].items() for entry in entries
            for h in entry["hooks"]]  # fmt: skip


def plain_install(folder: Path) -> Path:
    folder.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "sanchopanza", *carry_s.S_INSTALL], cwd=folder,
                   env={**carry.environment(), "PYTHONPATH": str(carry_s.SRC)}, check=True,
                   capture_output=True)  # fmt: skip
    return folder


def test_s_is_what_install_writes_with_only_the_commands_behind_the_launcher(
        tmp_path: Path) -> None:  # fmt: skip
    run, repo = tmp_path / "pair", tmp_path / "pair" / "repo"
    repo.mkdir(parents=True)
    carry_s.install(run, repo, tmp_path / "k", carry.environment())
    plain = plain_install(tmp_path / "plain")
    written = json.loads((run / "install/as-written/.claude/settings.json").read_text("utf-8"))
    assert written == json.loads((plain / ".claude/settings.json").read_text("utf-8"))
    assert (repo / ".claude/skills/sanchopanza-code/SKILL.md").read_bytes() == \
        (plain / ".claude/skills/sanchopanza-code/SKILL.md").read_bytes()  # fmt: skip
    rewired = json.loads((repo / ".claude/settings.json").read_text("utf-8"))
    assert {k: v for k, v in rewired.items() if k != "hooks"} == \
        {k: v for k, v in written.items() if k != "hooks"}  # fmt: skip
    before, after = commands(written), commands(rewired)
    assert [(e, m) for e, m, _ in before] == [(e, m) for e, m, _ in after]
    head = carry_s.prefix(run, tmp_path / "k")
    for (_, _, old), (_, _, new) in zip(before, after, strict=True):
        assert old.startswith("sanchopanza ") and new == f"{head} {old[len('sanchopanza '):]}"
    subs = {c.split(" sub ")[1].split()[0] for _, _, c in after}
    assert subs == {"hook", "guard-hook", "memory-hook"}  # the Guardian, the guard and memory
    assert rewired["env"]["SANCHOPANZA_GUARD_PROFILE"] == "coding"
    assert rewired["enabledMcpjsonServers"] == ["sanchopanza"]
    server = json.loads((repo / ".mcp.json").read_text("utf-8"))["mcpServers"]["sanchopanza"]
    assert server["args"][-2:] == ["sub", "find-mcp"] and server["alwaysLoad"] is True


def test_an_s_hook_runs_this_checkouts_code_with_the_pairs_state_and_no_token(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.setenv(carry.TOKEN, FAKE)
    run = tmp_path / "pair"
    run.mkdir()
    env = bench_module(BENCH, "carry_hook").s_env(run, tmp_path / "missing.key")
    assert carry.TOKEN not in env and "TYPESAFE_API_KEY" not in env
    assert env["PYTHONPATH"] == str(carry_s.SRC)
    assert env["SANCHOPANZA_MEMORY_STORE"] == str(run / "store")
    assert env["SANCHOPANZA_MEMORY_STORE_LOG"] == str(run / "hook-log.jsonl")
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "go on",
             "cwd": str(tmp_path), "transcript_path": str(tmp_path / "none.jsonl")}  # fmt: skip
    done = subprocess.run([sys.executable, str(carry_s.LAUNCHER), str(run),
                           str(tmp_path / "missing.key"), "sub", "memory-hook"],
                          input=json.dumps(event).encode(), capture_output=True)  # fmt: skip
    assert done.returncode == 0
    row = json.loads((run / "hooks.jsonl").read_text("utf-8").splitlines()[0])
    assert row["sub"] == "memory-hook" and row["event"] == "UserPromptSubmit"
    assert row["session"] == "s1" and row["exit"] == 0 and row["key"] is False


@pytest.mark.parametrize("name", sorted(PARALLEL))
def test_the_install_changes_no_check_of_a_parallel_scene(name: str, tmp_path: Path) -> None:
    scene = PARALLEL[name]
    run = tmp_path / "pair"
    run.mkdir()
    repo = carry.build(run, scene, lambda r: carry_s.install(run, r, tmp_path / "k",
                                                             carry.environment()))  # fmt: skip
    assert (repo / ".mcp.json").is_file()
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                           cwd=repo, capture_output=True)  # fmt: skip
    assert tests.returncode == 0
    assert not carry.passes(repo, scene["task"]) and not carry.passes(repo, scene["fact"])
    rel, good, bad = RESULTS[scene["cross"]]
    for text, kept in ((good, True), (bad, False)):
        (repo / rel).write_text(THREADS[scene["cross"]] + "\n\n" + text, encoding="utf-8")
        if scene["cross"] == "x_stdlib" and not kept:
            assert not carry.passes(repo, scene["fact"])  # PyYAML need not be installed here
            continue
        assert carry.passes(repo, scene["task"]) and carry.passes(repo, scene["fact"]) is kept


class FakeS(FakeClaude):
    """Claude Code with S's hooks: each session's memory hook answers its prompt, the find server
    is connected, and a decision lands in the pair's journal. `hooks=False`: none of it."""

    def __init__(self, hooks: bool = True) -> None:
        super().__init__()
        self.hooks = hooks

    def __call__(self, cmd: list[str], **kw: Any) -> Any:
        if cmd[0] != "claude" or cmd[1:] == ["--version"]:
            return super().__call__(cmd, **kw)
        assert cmd[cmd.index("--settings") + 1] == "{}"
        done = super().__call__(cmd, **kw)
        run = Path(kw["cwd"]).parent
        if not (run / "install").is_dir() or not self.hooks:
            return done
        sid = f"s{len(self.calls)}"
        with (run / "hooks.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"sub": "memory-hook", "event": "UserPromptSubmit",
                                  "session": sid, "exit": 0}) + "\n")  # fmt: skip
        with (run / "journal.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"kind": "decision", "data": {"provider": "jev",
                                                               "cost_usd": 0.001}}) + "\n")
        stream = kw["stdout"]
        stream.flush()
        events = [json.loads(x) for x in Path(stream.name).read_text("utf-8").splitlines()]
        events[0] = {**events[0], "session_id": sid,
                     "mcp_servers": [{"name": "sanchopanza", "status": "connected"}]}
        stream.seek(0)
        stream.truncate()
        stream.write("".join(json.dumps(e) + "\n" for e in events))
        return done


@pytest.fixture
def fake_s(monkeypatch: pytest.MonkeyPatch) -> FakeS:
    runner = FakeS()
    monkeypatch.setattr(carry.subprocess, "run", runner)
    monkeypatch.setitem(carry.SCENES, "t_three", THREE)
    monkeypatch.setenv(carry.TOKEN, FAKE)
    monkeypatch.setattr(carry, "ancestors_memory", lambda path: [])
    return runner


def test_an_s_pair_runs_with_its_install_decoys_and_decisions_counted(
        tmp_path: Path, fake_s: FakeS) -> None:  # fmt: skip
    stop = carry.run_plan(tmp_path, [("t_three", "sonnet", "S", 1)], tmp_path / "k", False,
                          10.0, clean=True)  # fmt: skip
    assert stop == ""
    row = json.loads((tmp_path / "carry.json").read_text("utf-8"))[0]
    assert "cut" not in row and row["fact_kept"] and row["jev_decisions"] == 3
    assert row["jev_usd"] == pytest.approx(0.003) and carry.spent_of(row) == pytest.approx(0.303)
    run = tmp_path / "t_three-sonnet-S-1"
    store = next((run / "store").iterdir())
    assert len(json.loads((store / "rules.json").read_text("utf-8"))["rules"]) == carry.DECOYS
    for checkout in (run / "repo", run / "repo-wt"):  # the worktree holds the install too
        assert (checkout / ".claude" / "settings.json").is_file()


def test_an_s_session_whose_hooks_never_ran_cuts_the_pair_and_stops_the_run(
        tmp_path: Path, fake_s: FakeS) -> None:  # fmt: skip
    fake_s.hooks = False
    plan = [("t_three", "sonnet", "S", 1), ("t_three", "sonnet", "N", 1)]
    assert carry.run_plan(tmp_path, plan, tmp_path / "k", False, 10.0, clean=True) == "harness"
    rows = json.loads((tmp_path / "carry.json").read_text("utf-8"))
    assert len(rows) == 1 and rows[0]["cut"].startswith("harness: session thread")
    assert "memory hook answered no prompt" in rows[0]["cut"]
    assert len(fake_s.calls) == 1  # sessions 1b and 2 never started


def test_s_session_and_pair_breaks() -> None:
    ok = {"init": {"mcp": {"sanchopanza": "failed"}}}
    assert carry_s.pair_breaks({"jev_decisions": 0, "jev_failed": 0})
    assert carry_s.pair_breaks({"jev_decisions": 4, "jev_failed": 4})
    assert not carry_s.pair_breaks({"jev_decisions": 4, "jev_failed": 3})
    assert any("sanchopanza: failed" in b for b in carry_s.session_breaks(Path("."), ok))


def test_the_reserve_holds_s_decisions_and_rotation_alternates_the_first_arm() -> None:
    three = len(carry.steps(carry.SCENES["q_tz"]))
    assert carry.reserve_of("q_tz", "sonnet", "N") == pytest.approx(three * 0.60)
    assert carry.reserve_of("q_tz", "sonnet", "S") == pytest.approx(three * 0.65)
    plan = carry.build_plan("parallel", "sonnet", "N,S", 3, 1, rotate=True)
    assert len(plan) == 48 and {r for *_, r in plan} == {1, 2, 3}
    firsts = [plan[i][2] for i in range(0, 48, 2)]
    assert firsts == ["N", "S"] * 12
    assert all({plan[i][2], plan[i + 1][2]} == {"N", "S"} and plan[i][0] == plan[i + 1][0]
               for i in range(0, 48, 2))  # fmt: skip


def test_a_failed_jev_preflight_refuses_before_any_pair(tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(carry.carry_s, "preflight", lambda *a: {"ok": False, "reason": "402"})
    with pytest.raises(SystemExit, match="402"):
        carry.jev_first(tmp_path, [("q_tz", "sonnet", "S", 1)], tmp_path / "k")
    assert carry.jev_first(tmp_path, [("q_tz", "sonnet", "N", 1)], tmp_path / "k") == 0.0


# cell.py


def row(scene: str, arm: str, rep: int, kept: bool, task: bool = True, cost: float = 0.1,
        **extra: Any) -> dict[str, Any]:  # fmt: skip
    return {"scene": scene, "model": "sonnet", "arm": arm, "repeat": rep, "run": "r",
            "planned": ["thread", "first", "second"], "second": {"key": "second"},
            "sessions": [{"returncode": 0, "subtype": "success"}] * 3,
            "fact_kept": kept, "task_pass": task, "tests_pass": True, "cost": cost, **extra}


def table(n_broken: int, s_broken: int, pairs: int = 24, s_cost: float = 0.1) -> list[dict]:
    out = []
    for i in range(pairs):
        scene, rep = sorted(PARALLEL)[i % 8], 1 + i // 8
        out += [row(scene, "N", rep, kept=i >= n_broken),
                row(scene, "S", rep, kept=i >= s_broken, cost=s_cost, jev_usd=0.001)]
    return out


def test_the_cell_wins_only_when_s_breaks_fewer_and_does_no_harm(tmp_path: Path) -> None:
    dirs = {"r": tmp_path}
    won = cell.cell(table(n_broken=8, s_broken=1), dirs)
    assert won["a_only_kept"] == 7 and won["p_a_better"] < 0.05 and won["verdict"] == "gana"
    tie = cell.cell(table(n_broken=3, s_broken=3), dirs)
    assert tie["verdict"].startswith("no gana") and "primary" in tie["verdict"]
    costly = cell.cell(table(n_broken=8, s_broken=1, s_cost=0.2), dirs)
    assert costly["verdict"] == "no gana (cost)"
    few = cell.cell(table(n_broken=8, s_broken=1, pairs=16), dirs)
    assert few["verdict"].startswith("sin veredicto")


def test_a_break_needs_the_task_done_and_a_not_run_pair_is_left_out(tmp_path: Path) -> None:
    rows = table(n_broken=0, s_broken=0)
    rows[0] = {**rows[0], "fact_kept": False, "task_pass": False}  # N: not a break
    rows[3] = {**rows[3], "cut": "usage limit"}  # S of the second pair: NOT RUN
    found = cell.cell(rows, {"r": tmp_path})
    assert found["pairs"] == 23 and found["not_run"] == [f"{sorted(PARALLEL)[1]} r1"]
    assert found["count"]["N"]["broken"] == 0 and found["count"]["N"]["not_kept"] == 1
    assert found["count"]["N"]["task"] == 22


def test_a_false_send_back_in_the_last_session_counts_against_s(tmp_path: Path) -> None:
    scene = sorted(PARALLEL)[0]
    pair = tmp_path / f"{scene}-sonnet-S-1"
    pair.mkdir()
    start = json.dumps({"event": "SessionStart", "source": "startup"})
    decoy = json.dumps({"event": "rules", "broken": ["Some other project rule."]})
    (pair / "hook-log.jsonl").write_text("\n".join([start, start, start, decoy]) + "\n",
                                         encoding="utf-8")  # fmt: skip
    found = cell.cell(table(n_broken=8, s_broken=1), {"r": tmp_path})
    assert found["false_sendbacks"] == {f"{scene} r1": ["Some other project rule."]}
    assert found["criteria"]["false_sendbacks"]["holds"]  # 1 of 24 is the most allowed
