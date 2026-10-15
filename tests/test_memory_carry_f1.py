"""The carry runner's F1 changes (`benchmarks/memory_carry/carry.py`, `analyze.py`), with no
session: `claude` is replaced by a fake that writes a stream. Nothing here calls a provider."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "memory_carry"
carry = bench_module(BENCH, "carry")
analyze = bench_module(BENCH, "analyze")
FAKE = "fake-token-for-tests-0123456789"
ONEXC = pytest.mark.skipif(sys.version_info < (3, 12), reason="carry.py cleans up with "
                           "shutil.rmtree(onexc=), new in Python 3.12")  # fmt: skip

THREE = {
    "files": {"app/__init__.py": "", "app/a.py": "X = 1\n",
              "tests/test_a.py": "from app.a import X\n\n\ndef test_x():\n    assert X\n"},
    "thread": "start a line", "first": "say the fact", "second": "go on",
    "task": "import app.a\n", "fact": "from app.a import X\nassert X == 1\n",
    "worktree": True,
}  # fmt: skip


class FakeClaude:
    """Stands in for `subprocess.run` when the command is `claude`; anything else runs. `modes`
    says how each session ends, in order (default "ok")."""

    def __init__(self, leak: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.leak, self.modes, self.version = leak, [], "2.1.287 (Claude Code)"
        self.real = subprocess.run

    def __call__(self, cmd: list[str], **kw: Any) -> Any:
        if cmd[0] != "claude":
            return self.real(cmd, **kw)
        if cmd[1:] == ["--version"]:
            self.calls.append({"cmd": cmd, "env": kw.get("env"), "cwd": None})
            return subprocess.CompletedProcess(cmd, 0, self.version + "\n", "")
        env, cwd = kw["env"], Path(kw["cwd"])
        self.calls.append({"cmd": cmd, "env": env, "cwd": cwd})
        mode = self.modes.pop(0) if self.modes else "ok"
        memory = (
            Path(env.get("CLAUDE_CONFIG_DIR", "unused"))
            / "projects"
            / carry.project_name(cwd)
            / "memory"
        )
        if "CLAUDE_CONFIG_DIR" in env:
            memory.mkdir(parents=True, exist_ok=True)
            (memory / f"note-{len(self.calls)}.md").write_text("saved", encoding="utf-8")
            if self.leak:
                (Path(env["CLAUDE_CONFIG_DIR"]) / ".claude.json").write_text(
                    json.dumps({"t": env[carry.TOKEN]}), encoding="utf-8"
                )
        if mode == "repo-leak":  # the token in a file the next commit keeps
            (cwd / "leak.txt").write_text(env[carry.TOKEN], encoding="utf-8")
        if mode == "timeout":
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        events = [{"type": "system", "subtype": "init", "model": cmd[cmd.index("--model") + 1],
                   "claude_code_version": "2.1.287", "mcp_servers": [], "plugins": [],
                   "skills": [], "agents": [], "permissionMode": "default",
                   "apiKeySource": "none", "memory_paths": {"auto": str(memory)}}]  # fmt: skip
        result = {"type": "result", "subtype": "success", "total_cost_usd": 0.1,
                  "num_turns": 2, "result": "done"}  # fmt: skip
        code = 0
        if mode == "budget":
            result, code = {**result, "subtype": carry.BUDGET_STOP, "is_error": True}, 1
        if mode == "limit":
            events.append(LIMIT_EVENT)
            result = {**result, "is_error": True, "api_error_status": 429, "total_cost_usd": 0}
        events += [] if mode == "noresult" else [result]
        code = 1 if mode in ("noresult", "error") else code
        kw["stdout"].write("".join(json.dumps(e) + "\n" for e in events))
        stderr = f"oops {env.get(carry.TOKEN)}" if mode == "stderr-leak" else ""
        return subprocess.CompletedProcess(cmd, code, "", stderr)


# From a real stream (adopt, conan-io__conan-1-limit1, 2026-10-01): the weekly limit.
LIMIT_EVENT = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "rejected", "resetsAt": 1791230400, "rateLimitType": "seven_day",
    "overageStatus": "rejected", "isUsingOverage": False}}  # fmt: skip


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeClaude:
    runner = FakeClaude()
    monkeypatch.setattr(carry.subprocess, "run", runner)
    monkeypatch.setitem(carry.SCENES, "t_three", THREE)
    monkeypatch.setenv(carry.TOKEN, FAKE)
    # tmp_path sits under the home folder, whose ~/.claude the clean-user check refuses
    monkeypatch.setattr(carry, "ancestors_memory", lambda path: [])
    return runner


def test_sessions_run_thread_first_between_second_and_only_first_in_the_worktree() -> None:
    scene = {"second": "s", "between": "b", "first": "f", "thread": "t", "worktree": True}
    assert carry.steps(scene) == [("thread", False), ("first", True), ("between", False),
                                  ("second", False)]  # fmt: skip
    assert carry.steps({"first": "f", "second": "s"}) == [("first", False), ("second", False)]


@ONEXC
def test_the_worktree_is_a_sibling_checkout_and_survives_a_held_index(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    repo = carry.build(tmp_path / "pair", THREE)
    real, failed = carry.git, []

    def flaky(cwd: Path, *args: str) -> None:
        if args[0] == "worktree" and not failed:
            failed.append(args)
            (repo.parent / "repo-wt").mkdir()  # what a half-made try leaves behind
            raise subprocess.CalledProcessError(128, ["git", *args])
        real(cwd, *args)

    monkeypatch.setattr(carry, "git", flaky)
    monkeypatch.setattr(carry.time, "sleep", lambda s: None)
    tree = carry.worktree(repo)
    assert failed and tree == repo.parent / "repo-wt" and (tree / "app" / "a.py").exists()
    listed = subprocess.run(["git", "-C", str(repo), "worktree", "list"], capture_output=True,
                            text=True, check=True).stdout  # fmt: skip
    assert "[side]" in listed and not (repo / "repo-wt").exists()


def test_a_three_session_pair_runs_in_order_where_it_should_and_is_checked(
        tmp_path: Path, fake: FakeClaude) -> None:  # fmt: skip
    row = carry.pair(tmp_path, "t_three", "sonnet", "N", 0, tmp_path / "k", False, clean=True)
    run = tmp_path / "t_three-sonnet-N-0"
    assert [c["cwd"] for c in fake.calls] == [run / "repo", run / "repo-wt", run / "repo"]
    assert [s["key"] for s in row["sessions"]] == ["thread", "first", "second"]
    assert [s["where"] for s in row["sessions"]] == ["main", "worktree", "main"]
    assert row["first"]["key"] == "first" and row["second"]["key"] == "second"
    assert row["fact_kept"] and row["task_pass"] and row["tests_pass"]
    assert row["cost"] == pytest.approx(0.3) and row["first"]["subtype"] == "success"
    assert row["first"]["init"]["version"] == "2.1.287"
    assert all((run / f"session-{i}.jsonl").exists() for i in (1, 2, 3))

    def log(branch: str) -> str:
        return subprocess.run(["git", "-C", str(run / "repo"), "log", branch, "--format=%s"],
                              capture_output=True, text=True, check=True).stdout  # fmt: skip

    # thread committed in main, first in the worktree's branch; the last session is not
    assert log("main").split() == ["wip", "start"] and log("side").split() == ["wip", "start"]


def test_clean_user_gets_its_own_config_per_pair_and_the_token_only_in_the_process_env(
        tmp_path: Path, fake: FakeClaude) -> None:  # fmt: skip
    carry.run_plan(tmp_path, [("t_three", "sonnet", "N", 0), ("t_three", "sonnet", "N", 1)],
                   tmp_path / "k", False, 10.0, clean=True)  # fmt: skip
    configs = [c["env"]["CLAUDE_CONFIG_DIR"] for c in fake.calls]
    assert len(set(configs[:3])) == 1 and len(set(configs[3:])) == 1  # kept across a pair
    assert configs[0] != configs[3] and configs[0].startswith(str(tmp_path))
    assert all(c["env"][carry.TOKEN] == FAKE for c in fake.calls)
    assert not [c for c in fake.calls if any(FAKE in part for part in c["cmd"])]
    rows = json.loads((tmp_path / "carry.json").read_text(encoding="utf-8"))
    # auto memory is read from the configuration actually used, not from ~/.claude
    assert rows[0]["native_after_1"] and all("note-" in n for n in rows[0]["native_after_1"])
    assert not [p for p in tmp_path.rglob("*") if p.is_file() and FAKE.encode() in p.read_bytes()]


def test_a_token_claude_code_wrote_into_the_pair_is_scrubbed(tmp_path: Path,
                                                            fake: FakeClaude) -> None:  # fmt: skip
    fake.leak = True
    row = carry.pair(tmp_path, "t_three", "sonnet", "N", 0, tmp_path / "k", False, clean=True)
    assert row["token_scrubbed"] == [str(Path("claude-config") / ".claude.json")]
    assert not [p for p in tmp_path.rglob("*") if p.is_file() and FAKE.encode() in p.read_bytes()]


def test_clean_user_without_a_token_refuses_before_building_anything(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.delenv(carry.TOKEN, raising=False)
    monkeypatch.setattr(carry, "HARNESS_ENV", tmp_path / "no.env")
    with pytest.raises(SystemExit, match=carry.TOKEN):
        carry.main(["--out", str(tmp_path / "out"), "--scenes", "parallel", "--arms", "N",
                    "--clean-user", "--dry"])  # fmt: skip
    assert not (tmp_path / "out").exists()


def test_clean_user_token_comes_from_the_harness_env_when_the_window_has_none(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.delenv(carry.TOKEN, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f'OTHER=1\n{carry.TOKEN}="{FAKE}"\n', encoding="utf-8")
    monkeypatch.setattr(carry, "HARNESS_ENV", env_file)
    assert carry.clean_token() == FAKE
    monkeypatch.setenv(carry.TOKEN, "from-window")
    assert carry.clean_token() == "from-window"


def test_without_clean_user_the_config_and_token_are_left_as_they_were(
        monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv(carry.TOKEN, raising=False)
    env = carry.environment()
    assert "CLAUDE_CONFIG_DIR" not in env and carry.TOKEN not in env


def test_the_total_cap_reserves_every_session_of_the_next_pair(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.setitem(carry.SCENES, "t_three", THREE)
    ran: list[str] = []

    def pair(out: Path, name: str, *rest: Any) -> dict[str, Any]:
        ran.append(name)
        return {"scene": name, "cost": 0.5}

    monkeypatch.setattr(carry, "pair", pair)
    # 0.5 spent; a two-session pair needs 1.20 (fits under 2.0), a three-session one 1.80 (not)
    plan = [
        ("columns", "sonnet", "N", 0),
        ("columns", "sonnet", "N", 1),
        ("t_three", "sonnet", "N", 0),
    ]
    carry.run_plan(tmp_path, plan, tmp_path / "k", True, 2.0)
    assert ran == ["columns", "columns"]  # then 1.0 + 3 x 0.60 = 2.80 > 2.0
    ran.clear()
    carry.run_plan(tmp_path, [("columns", "sonnet", "N", 0), ("t_three", "sonnet", "N", 0)],
                   tmp_path / "k", True, 2.25)  # fmt: skip
    assert ran == ["columns"]  # 0.5 + 3 x 0.60 = 2.30 > 2.25
    ran.clear()
    carry.run_plan(tmp_path, [("t_three", "opus", "N", 0)], tmp_path / "k", True, 2.9)
    assert ran == []  # opus: 3 x 1.00 > 2.9


def test_each_model_has_its_own_session_cap(tmp_path: Path) -> None:
    def cap(model: str) -> str:
        cmd = carry.command(tmp_path, "p", model, "N", tmp_path / "k")
        return cmd[cmd.index("--max-budget-usd") + 1]

    assert (cap("haiku"), cap("sonnet"), cap("opus")) == ("0.60", "0.60", "1.00")
    assert carry.MODELS["opus"] == "claude-opus-5-5"


def test_first_repeat_numbers_the_repetitions_from_it() -> None:
    plan = carry.build_plan("parallel", "sonnet", "N", 3, first=1)
    assert sorted({rep for *_, rep in plan}) == [1, 2, 3] and len(plan) == 24
    assert {rep for *_, rep in carry.build_plan("parallel", "sonnet", "N", 1)} == {0}
    with pytest.raises(SystemExit, match="unknown"):
        carry.build_plan("nope", "sonnet", "N", 1)


def test_the_f1_sets_are_registered_and_family_iii_rules_are_known() -> None:
    sets = ("principle", "stale", "parallel")
    assert carry.SETS["f1"] == [n for s in sets for n in carry.SETS[s]]
    assert all(carry.ALL_RULES[q] in carry.SCENES[q]["first"] for q in carry.SETS["parallel"])
    # every scene's own rule is one sentence of text (family ii: the newer, said in `between`)
    assert all(isinstance(carry.ALL_RULES[n], str) for n in carry.SETS["f1"])
    for u in carry.SETS["stale"]:
        assert carry.ALL_RULES[u] in carry.SCENES[u]["between"]
        assert carry.STALE_OLD[u] in carry.SCENES[u]["first"]


def test_decoys_of_the_earlier_scenes_are_unchanged_and_a_twin_is_never_a_decoy() -> None:
    pool = {**carry.RULES, **carry.CROSS_RULES}
    same = (
        {"naive", "x_tz"},
        {"stdlib", "x_stdlib"},
        {"stdout", "x_print"},
        {"ids", "x_zeros"},
        {"envvar", "x_prefix"},
        {"legacy", "nulls"},
    )  # v7 / v8's groups, as sealed
    for name in pool:  # v7 / v8's formula, on v7 / v8's pool
        near = set().union(*(g for g in same if name in g)) | {name}
        keys = sorted(k for k in pool if k not in near)
        start = sum(map(ord, name)) % len(keys)
        assert carry.decoys(name) == [pool[k] for k in (keys[start:] + keys[:start])[:7]]
    for q in carry.SETS["parallel"]:
        assert carry.ALL_RULES[q] not in carry.decoys(q)
    assert carry.RULES["naive"] not in carry.decoys("q_tz")


@pytest.mark.parametrize(("scene", "near"), [
    ("p_json", ("x_print", "stdout")), ("p_dryrun", ("x_print", "stdout")),
    ("u_time", ("naive", "x_tz")), ("u_money", ("x_cents",)), ("u_sep", ("fields",)),
])  # fmt: skip
def test_an_f1_scene_never_gets_a_near_identical_decoy(scene: str, near: tuple[str, ...]) -> None:
    if scene not in carry.SCENES:
        pytest.skip(f"{scene} has not landed")
    got = carry.decoys(scene)
    assert len(got) == carry.DECOYS and not [n for n in near if carry.ALL_RULES[n] in got]
    assert not carry.own_rules(scene) & set(got)


def test_a_stale_scene_owns_both_its_rules_and_a_send_back_by_the_older_is_stale(
        tmp_path: Path) -> None:  # fmt: skip
    sendbacks = bench_module(BENCH, "sendbacks")
    name = carry.SETS["stale"][0]
    old, new = carry.STALE_OLD[name], carry.ALL_RULES[name]
    assert carry.own_rules(name) == {old, new}
    pair = tmp_path / f"{name}-sonnet-S-0"
    pair.mkdir()
    rows = [
        {"event": "SessionStart", "source": "startup"},
        {"event": "rules", "broken": [new, f"For context: {old}", carry.RULES["fields"]]},
    ]
    (pair / "hook-log.jsonl").write_text("\n".join(json.dumps(r) for r in rows), "utf-8")
    found = sendbacks.sendbacks(pair)
    assert [(f["own"], f["stale"]) for f in found] == [(True, False), (False, True),
                                                       (False, False)]  # fmt: skip


def test_the_stale_check_is_read_three_ways(tmp_path: Path) -> None:
    assert carry.carried(True, False) == "newer" and carry.carried(False, True) == "stale"
    assert carry.carried(False, False) == "neither" and carry.carried(True, None) is None
    scene = {**THREE, "stale": "from app.a import X\nassert X == 2\n"}
    repo = carry.build(tmp_path / "p", scene)
    found = carry.check(repo, scene)
    assert found["fact_kept"] and found["stale_kept"] is False and found["carried"] == "newer"
    assert "stale_kept" not in carry.check(repo, THREE)


def test_the_dry_run_builds_every_repository_and_worktree_and_calls_nothing(
        tmp_path: Path, fake: FakeClaude, capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    assert carry.main(["--out", str(tmp_path), "--models", "sonnet,opus", "--scenes", "parallel",
                       "--arms", "N", "--repeats", "1", "--clean-user", "--dry"]) == 0  # fmt: skip
    rows = json.loads((tmp_path / "carry.json").read_text(encoding="utf-8"))
    assert len(rows) == 16 and not fake.calls
    assert sum(1 for r in rows if r["worktree"]) == 8
    assert all((Path(r["worktree"]) / ".git").is_file() for r in rows if r["worktree"])
    assert {tuple(r["planned"]) for r in rows} == {("thread", "first", "second")}
    printed = [x for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert len(printed) == 16 and FAKE not in "".join(printed)


def test_the_hook_arms_alone_need_the_typesafe_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[Path] = []
    monkeypatch.setattr(carry, "record_claude", lambda *a: None)
    monkeypatch.setattr(
        carry, "keyfile_from_harness_env", lambda out: asked.append(out) or out / "k"
    )
    monkeypatch.setattr(carry, "run_plan", lambda *a, **k: None)
    carry.main(["--out", str(tmp_path), "--scenes", "parallel", "--arms", "N"])
    assert not asked
    carry.main(["--out", str(tmp_path), "--scenes", "parallel", "--arms", "N,M"])
    assert asked


# analyze.py


def session(code: int = 0, subtype: str | None = "success") -> dict[str, Any]:
    return {"returncode": code, **({"subtype": subtype} if subtype is not None else {})}


def row(scene: str, kept: bool, model: str = "sonnet", **extra: Any) -> dict[str, Any]:
    s = [session(), session(), session()]
    return {"scene": scene, "model": model, "arm": "N", "repeat": 0, "fact_kept": kept,
            "tests_pass": True, "task_pass": True, "cost": 0.5, "planned": ["thread", "first",
            "second"], "sessions": s, "first": s[1], "second": s[2], "limit_hit": False,
            **extra}  # fmt: skip


def test_a_session_its_own_budget_stopped_counts_as_run_and_one_without_a_result_does_not() -> None:
    stopped = row("q_tz", False)
    stopped["sessions"] = [session(), session(1, "error_max_budget_usd"), session()]
    assert not analyze.ran({**stopped, "cut": "timeout"})
    assert analyze.ran(stopped)
    cut = row("q_tz", False)
    cut["sessions"] = [session(), session(1, None), session()]
    assert not analyze.ran(cut)
    short = row("q_tz", False)
    short["sessions"] = short["sessions"][:2]
    assert not analyze.ran(short)
    old = {"first": {"returncode": 0}, "second": {"returncode": 1}, "limit_hit": False}
    assert not analyze.ran(old) and analyze.ran({**old, "second": {"returncode": 0}})


def test_the_gate_table_counts_breaks_per_family_and_model(tmp_path: Path,
                                                          capsys: pytest.CaptureFixture[str],
                                                          ) -> None:  # fmt: skip
    sets = carry.SETS
    q = [row(n, i >= 3) for i, n in enumerate(sets["parallel"])]  # 3 broken: passes
    u = [row(n, i != 0, stale_kept=i == 0, carried="newer" if i else "stale")
         for i, n in enumerate(sets["stale"])]  # fmt: skip
    u[1] = {**u[1], "limit_hit": True}  # not run
    p_opus = [row(n, i >= 2, model="opus") for i, n in enumerate(sets["principle"])]  # 2: fails
    for name, rows in (("f1-gate-sonnet", q + u), ("f1-gate-opus", p_opus)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "carry.json").write_text(json.dumps(rows), encoding="utf-8")
    assert analyze.main([str(tmp_path / "f1-gate-*"), "--gate"]) == 0
    table = {
        (r["family"], r["model"]): r
        for r in analyze.gate(analyze.rows(analyze.folders([str(tmp_path / "f1-gate-*")])))
    }
    assert table[("parallel", "sonnet")]["broken"] == 3 and table[("parallel", "sonnet")]["pass"]
    principle = table[("principle", "opus")]
    assert principle["broken"] == 2 and principle["verdict"] == "fail"
    stale = table[("stale", "sonnet")]
    assert stale["ran"] == 7 and stale["not_run"] == [f"{sets['stale'][1]} r0"]
    assert stale["verdict"] == "incomplete"  # 1 break, 7 of 8 run
    assert stale["stale_split"] == {"newer": 6, "stale": 1, "neither": 0}
    # a family a model never ran: every planned scene listed as missing
    missing = table[("principle", "sonnet")]
    assert missing["ran"] == 0 and missing["verdict"] == "incomplete"
    assert len(missing["not_run"]) == 8 and all("(missing)" in x for x in missing["not_run"])
    out = capsys.readouterr().out
    assert "PASS" in out and "fail" in out and "incomplete" in out


def test_a_gate_break_needs_the_task_done_and_both_counts_are_reported() -> None:
    names = carry.SETS["parallel"]
    rows = [
        row(names[0], False),
        row(names[1], False),
        row(names[2], False, task_pass=None),
        row(names[3], False, task_pass=False),
        row(names[4], False, task_pass=False),
    ]
    rows += [row(n, True) for n in names[5:]]
    (cell,) = [c for c in analyze.gate(rows) if c["family"] == "parallel"]
    assert cell["not_kept"] == 5 and cell["broken"] == 3 and cell["pass"]
    assert f"{names[3]} r0" not in cell["broken_scenes"]
    rows[0] = {**rows[0], "task_pass": False}
    (cell,) = [c for c in analyze.gate(rows) if c["family"] == "parallel"]
    assert cell["broken"] == 2 and cell["verdict"] == "fail"


def test_pooling_refuses_the_same_pair_in_two_folders(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "carry.json").write_text(json.dumps([row("q_tz", True)]), "utf-8")
    with pytest.raises(SystemExit, match="pooling"):
        analyze.rows([tmp_path / "a", tmp_path / "b"])


def test_compare_reports_the_three_way_split_when_a_scene_has_a_stale_check() -> None:
    n = row("u_a", False, stale_kept=True, carried="stale")
    s = {**row("u_a", True, stale_kept=False, carried="newer"), "arm": "S"}
    out = analyze.compare([n, s], "S", "N")
    assert out["stale_split"]["N"]["stale"] == 1 and out["stale_split"]["S"]["newer"] == 1
    assert out["a_only"] == 1


# Review fixes (2026-10-05)


def test_1_a_memory_file_above_the_run_folder_refuses_a_clean_user(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.setenv(carry.TOKEN, FAKE)
    (tmp_path / "a" / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / "a" / ".claude" / "rules" / "style.md").write_text("x", encoding="utf-8")
    (tmp_path / "a" / ".claude" / "CLAUDE.md").write_text("x", encoding="utf-8")
    out = tmp_path / "a" / "b" / "run"
    found = carry.ancestors_memory(out)
    assert str(tmp_path / "a" / ".claude" / "rules") in found
    assert str(tmp_path / "a" / ".claude" / "CLAUDE.md") in found
    with pytest.raises(SystemExit, match="memory files above"):
        carry.main(["--out", str(out), "--scenes", "parallel", "--arms", "N", "--clean-user",
                    "--dry"])  # fmt: skip
    assert not out.exists()


def test_2_a_session_on_another_version_or_model_makes_the_pair_not_run() -> None:
    def with_init(version: str, model: str, source: str = "none") -> dict[str, Any]:
        r = row("q_tz", True)
        init = {"version": version, "model": model, "api_key_source": source}
        r["sessions"] = [{**s, "init": init} for s in r["sessions"]]
        return r

    assert analyze.ran(with_init("2.1.287", "claude-sonnet-5-5"))
    assert not analyze.ran(with_init("2.1.288", "claude-sonnet-5-5"))
    assert not analyze.ran(with_init("2.1.287", "claude-opus-5-5"))
    assert analyze.ran(row("q_tz", True))  # rows without init: as before
    rows = [with_init("2.1.287", "claude-sonnet-5-5", "ANTHROPIC_API_KEY")]
    (cell,) = [c for c in analyze.gate(rows) if c["family"] == "parallel"]
    assert cell["auth"] == {"ANTHROPIC_API_KEY": 3}


@pytest.mark.parametrize(("stop", "code"), [("", 0), ("cap", 2), ("limit", 2), ("timeout", 3)])
def test_3_main_exits_non_zero_when_the_run_stopped_early(
        stop: str, code: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    monkeypatch.setattr(carry, "record_claude", lambda *a: None)
    monkeypatch.setattr(carry, "run_plan", lambda *a, **k: stop)
    assert carry.main(["--out", str(tmp_path), "--scenes", "parallel", "--arms", "N"]) == code


def test_3_run_plan_says_why_it_stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        carry,
        "pair",
        lambda out, name, *r: {"scene": name, "cost": 0.5, "limit_hit": name == "legacy"},
    )
    plan = [("columns", "sonnet", "N", 0), ("legacy", "sonnet", "N", 0)]
    assert carry.run_plan(tmp_path, plan[:1], tmp_path / "k", True, 9.0) == ""
    assert carry.run_plan(tmp_path, plan, tmp_path / "k", True, 1.0) == "cap"
    assert carry.run_plan(tmp_path, plan, tmp_path / "k", True, 9.0) == "limit"


@ONEXC
def test_4_a_cut_pairs_cost_is_counted_before_it_runs_again(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    ran: list[str] = []
    monkeypatch.setattr(carry, "pair", lambda out, name, *r: ran.append(name) or
                        {"scene": name, "cost": 0.1})  # fmt: skip
    cut = tmp_path / "columns-sonnet-N-0"
    cut.mkdir()
    (cut / "session-1.jsonl").write_text(
        json.dumps({"type": "result", "subtype": "success", "total_cost_usd": 0.5}),
        encoding="utf-8",
    )
    # 0.5 already spent by the cut pair + 2 x 0.60 = 1.70 > 1.5: it does not run again
    plan = [("columns", "sonnet", "N", 0)]
    assert carry.run_plan(tmp_path, plan, tmp_path / "k", True, 1.5, carry_on=True) == "cap"
    assert not ran
    assert carry.run_plan(tmp_path, plan, tmp_path / "k", True, 1.8, carry_on=True) == ""
    assert ran == ["columns"]


def test_4_a_session_that_times_out_cuts_its_pair_and_stops_the_run(
        tmp_path: Path, fake: FakeClaude) -> None:  # fmt: skip
    fake.modes = ["ok", "timeout"]
    plan = [("t_three", "sonnet", "N", 0), ("t_three", "sonnet", "N", 1)]
    assert carry.run_plan(tmp_path, plan, tmp_path / "k", False, 9.0, clean=True) == "timeout"
    assert not (tmp_path / "carry.json").exists()  # no row: --continue runs it again, whole
    assert (tmp_path / "t_three-sonnet-N-0").exists()
    assert len([c for c in fake.calls if c["cwd"]]) == 2


def test_7_a_clean_user_gets_no_anthropic_or_provider_variable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    for name in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_MODEL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CONFIG_DIR",
    ):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv(carry.TOKEN, FAKE)
    env = carry.environment(tmp_path / "cfg")
    assert not [k for k in env if k.upper().startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_"))]
    assert env[carry.TOKEN] == FAKE and env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "cfg")
    assert carry.environment()["ANTHROPIC_BASE_URL"] == "x"  # the old arms: as they were


@pytest.mark.parametrize(("modes", "calls", "cut"), [
    (["ok", "noresult"], 2, "did not end with a result"),
    (["error"], 1, "did not end with a result"),
    (["ok", "limit"], 2, "usage limit"),
    (["ok", "budget"], 3, None),
])  # fmt: skip
def test_8_a_session_without_a_result_or_failing_cuts_its_pair(
        modes: list[str], calls: int, cut: str | None, tmp_path: Path,
        fake: FakeClaude) -> None:  # fmt: skip
    fake.modes = list(modes)
    row_ = carry.pair(tmp_path, "t_three", "sonnet", "N", 0, tmp_path / "k", False, clean=True)
    assert len(fake.calls) == calls
    if cut is None:  # a session its own budget stopped counts as run, and the pair goes on
        assert "cut" not in row_ and row_["fact_kept"] and analyze.ran(row_)
        assert row_["first"]["subtype"] == carry.BUDGET_STOP
    else:
        assert cut in row_["cut"] and "fact_kept" not in row_ and not analyze.ran(row_)


def test_9_the_token_never_reaches_a_row_and_one_in_git_is_flagged_not_deleted(
        tmp_path: Path, fake: FakeClaude) -> None:  # fmt: skip
    fake.modes = ["repo-leak", "stderr-leak"]
    row_ = carry.pair(tmp_path, "t_three", "sonnet", "N", 0, tmp_path / "k", False, clean=True)
    assert FAKE not in json.dumps(row_) and "[token]" in row_["first"]["stderr"]
    assert "repo/leak.txt" in [x.replace("\\", "/") for x in row_["token_scrubbed"]]
    assert row_["token_in_git"] and (tmp_path / "t_three-sonnet-N-0" / "repo" / ".git").is_dir()


def test_9_the_scrub_runs_even_when_the_pair_fails(
    tmp_path: Path, fake: FakeClaude, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.leak = True

    def broken(repo: Path, tries: int = 3) -> None:
        raise subprocess.CalledProcessError(128, ["git", "commit"])

    monkeypatch.setattr(carry, "commit_wip", broken)
    with pytest.raises(subprocess.CalledProcessError):
        carry.pair(tmp_path, "t_three", "sonnet", "N", 0, tmp_path / "k", False, clean=True)
    leaked = [p for p in tmp_path.rglob("*") if p.is_file() and ".git" not in p.parts
              and FAKE.encode() in p.read_bytes()]  # fmt: skip
    assert not leaked


def test_10_the_usage_limit_is_read_from_events_not_from_text() -> None:
    allowed = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed",
               "rateLimitType": "five_hour"}}  # fmt: skip
    warned = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning",
              "rateLimitType": "seven_day", "surpassedThreshold": 0.75}}  # fmt: skip
    talk = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": 'You hit your usage limit? "status":429 is not this.'}
            ]
        },
    }
    assert not [e for e in (allowed, warned, talk) if carry.limited(e)]
    assert carry.limited(LIMIT_EVENT)
    assert carry.limited({"type": "assistant", "error": "rate_limit", "message": {}})
    assert carry.limited({"type": "result", "subtype": "success", "is_error": True,
                          "api_error_status": 429})  # fmt: skip


def test_11_u_sep_stale_needs_the_event_key(tmp_path: Path) -> None:
    scene = carry.SCENES["u_sep"]
    for line, stale in (
        ("event=login_failed user={user} ip={ip}", True),
        ("user={user} ip={ip} reason=bad", False),
    ):
        repo = tmp_path / str(stale)
        for rel, text in scene["files"].items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text, encoding="utf-8")
        (repo / "app" / "auth.py").write_text(
            "def log_failed_login(user, ip, path):\n"
            "    with open(path, 'a', encoding='utf-8') as f:\n"
            f"        f.write(f'{line}\\n')\n",
            encoding="utf-8",
        )
        assert carry.passes(repo, scene["task"])
        assert carry.passes(repo, scene["stale"]) is stale, line


@pytest.mark.parametrize(("version", "refused"), [("2.1.287 (Claude Code)", False),
                                                  ("2.1.290 (Claude Code)", True)])  # fmt: skip
def test_12_the_run_logs_its_claude_and_a_clean_user_refuses_another_version(
        version: str, refused: bool, tmp_path: Path, fake: FakeClaude) -> None:  # fmt: skip
    fake.version = version
    if refused:
        with pytest.raises(SystemExit, match="not 2.1.287"):
            carry.record_claude(tmp_path, False, True)
    else:
        carry.record_claude(tmp_path, False, True)
    carry.record_claude(tmp_path, False, False)  # not clean: logged, never refused
    logged = (tmp_path / "claude.txt").read_text(encoding="utf-8")
    assert logged.count(version) == 2 and FAKE not in logged


def test_12_a_dry_run_asks_claude_nothing(tmp_path: Path, fake: FakeClaude) -> None:
    carry.record_claude(tmp_path, True, True)
    assert not fake.calls and "not asked (dry run)" in (tmp_path / "claude.txt").read_text()
