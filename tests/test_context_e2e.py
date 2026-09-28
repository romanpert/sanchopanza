"""The compaction end-to-end run in `docs/results/2026-09-28-context-e2e/`, pinned. Free.

1. The registration: `prereg.md` hashes to what `prereg.sha256` recorded before any paid call.
2. The tasks: the generator rebuilds the registered repositories byte for byte; the planted
   one-shot facts are nowhere in a repository but their tool's own input; hidden tests fail
   as generated and pass on the reference solution.
3. The hook's command: the wrapper runs `sanchopanza compact` for the rules arm, logs it, and
   keeps the exit code (0 pruned, 3 below the minimum).
4. The session environment carries no credential, and the native arm no sanchopanza variable.
5. The numbers: `analysis.json` is what `analyze.py` computes from the committed rows.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results" / "2026-09-28-context-e2e"
PREREG_SHA256 = (
    (RESULTS / "prereg.sha256").read_text("utf-8").split()[0]
    if (RESULTS / "prereg.sha256").exists()
    else ""
)
SANCHO = ROOT / ".venv" / "Scripts" / "sanchopanza.exe"

if not (RESULTS / "tasks.py").exists():  # pragma: no cover
    pytest.skip("context e2e results not present", allow_module_level=True)

sys.path.insert(0, str(RESULTS))


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tasks = _module("context_e2e_tasks", RESULTS / "tasks.py")
analyze = _module("context_e2e_analyze", RESULTS / "analyze.py")


def test_registration_hash() -> None:
    """Round 1 is the text before the R2 amendment, unchanged; the whole file is round 2's."""
    assert PREREG_SHA256 == "48d63652e98ba0f0440ccd0a00d90bb8faeec11c3ec33056fdc08c313df690d1"
    text = (RESULTS / "prereg.md").read_bytes()
    round1 = text[: text.index(b"\n---\n\n## Amendment R2")]
    assert hashlib.sha256(round1).hexdigest() == PREREG_SHA256
    lines = (RESULTS / "prereg.sha256").read_text("utf-8").splitlines()
    round2 = text[: text.index(b"\n---\n\n## Amendment R3")]
    assert lines[1].split()[0] == "4ca07b5e3f5bb9662ce900639663ac92ce7b3c6fc6f01c18ea087e15b1c1b247"
    assert hashlib.sha256(round2).hexdigest() == lines[1].split()[0]
    assert lines[2].split()[0] == "3106b92e19dc4147932103ab789d5c1d7a51672627d5d7861a9a5ae38336f10b"
    assert hashlib.sha256(text).hexdigest() == lines[2].split()[0]


def test_round2_settings_hold_no_key_and_no_marketplace(tmp_path: Path) -> None:
    run2 = _module("context_e2e_round2", RESULTS / "run_round2.py")
    ev = tmp_path / "ev"
    ev.mkdir()
    if not SANCHO.exists():
        pytest.skip("the venv's sanchopanza entry point is needed")
    data = json.loads(run2.settings_for(ev, tmp_path / "keyfile").read_text("utf-8"))
    assert "extraKnownMarketplaces" not in data and "enabledPlugins" not in data
    assert data["env"]["SANCHOPANZA_COMPACT_COMMAND"].split()[2:] == ["M", str(ev)]
    assert "TYPESAFE_API_KEY" not in json.dumps(data)
    commands = {h["command"] for hs in data["hooks"].values() for m in hs for h in m["hooks"]}
    assert commands and all("hook_wrapper.py" in c for c in commands)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("tasks")
    tasks.build(out)
    return out


def test_tasks_are_the_registered_ones(built: Path) -> None:
    registered = (RESULTS / "tasks.sha256").read_text("utf-8").split()[0]
    assert tasks.tree_digest(built / "repos") == registered
    assert tasks.tree_digest(built / "hidden") == (
        "92b0a6675d451dfc73e00860a523aa71decb100800d35f442dbccea7392d7b09"
    )


def test_one_shot_facts_only_in_their_tools_inputs(built: Path) -> None:
    facts = json.loads((built / "facts.json").read_text("utf-8"))
    assert len(facts) == tasks.N_TASKS
    for f in facts:
        repo = built / "repos" / f["task"]
        texts = {
            p.relative_to(repo).as_posix(): p.read_text("utf-8")
            for p in repo.rglob("*")
            if p.is_file()
        }
        assert not [n for n, t in texts.items() if f["token"] in t]  # derived at run time only
        assert [n for n, t in texts.items() if f["code"] in t] == ["tools/.probe_state"]
        homes = [n for n, t in texts.items() if "GRACE_WINDOW_DAYS =" in t]
        assert homes == [f"pkg/{f['window_home']}"]


@pytest.mark.parametrize("index", [0, 7])
def test_hidden_tests_need_the_work(built: Path, tmp_path: Path, index: int) -> None:
    import shutil

    f = tasks.Facts(**json.loads((built / "facts.json").read_text("utf-8"))[index])
    repo = tmp_path / f.task
    shutil.copytree(built / "repos" / f.task, repo)
    hidden = built / "hidden" / f.task
    before = tasks.run_tests(repo, hidden)
    assert not before["passed"]
    assert not any(tasks.facts_passed(before["tests"]).values())
    tasks.solve(repo, f)
    after = tasks.run_tests(repo, hidden)
    assert after["passed"], after["tail"]
    assert all(tasks.facts_passed(after["tests"]).values())


def _conversation(reads: int) -> str:
    msgs = [{"role": "user", "content": [{"type": "text", "text": "do the task"}]}]
    for i in range(reads):
        msgs.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"u{i}",
                        "name": "Read",
                        "input": {"file_path": "/w/a.py"},
                    }
                ],
            }
        )
        msgs.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": f"u{i}", "content": "x" * 3000 + str(i)}
                ],
            }
        )
    for i in range(4):
        msgs.append(
            {
                "role": "assistant" if i % 2 == 0 else "user",
                "content": [{"type": "text", "text": "ok"}],
            }
        )
    return json.dumps({"session": "s1", "messages": msgs})  # fmt: skip


@pytest.mark.skipif(not SANCHO.exists(), reason="the venv's sanchopanza entry point is needed")
@pytest.mark.parametrize("reads,code", [(6, 0), (1, 3)])
def test_wrapper_runs_the_rules_arm(tmp_path: Path, reads: int, code: int) -> None:
    ev = tmp_path / "ev"
    proc = subprocess.run(
        [sys.executable, str(RESULTS / "compact_wrapper.py"), "R", str(ev), "--session", "s1",
         "--out", ".sanchopanza/out.json"],
        input=_conversation(reads), capture_output=True, text=True, cwd=tmp_path,
    )  # fmt: skip
    assert proc.returncode == code, proc.stderr
    line = json.loads((ev / "wrapper.jsonl").read_text("utf-8").splitlines()[-1])
    assert line["exit"] == code and line["report"]["arm"] == "rules"
    assert line["report"]["decisions"] == 0
    if code == 0:
        out = json.loads((tmp_path / ".sanchopanza" / "out.json").read_text("utf-8"))
        assert "[sanchopanza pruned this Read result" in json.dumps(out["messages"])
    else:  # round 1's leftover-file bug, fixed in cli.py: a fallback leaves no copy
        assert not (tmp_path / ".sanchopanza" / "out.json").exists()
        assert not (tmp_path / ".sanchopanza" / "archive").exists()


def test_session_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run = _module("context_e2e_run", RESULTS / "run_e2e.py")
    for k in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY", "SANCHOPANZA_PROVIDER"):
        monkeypatch.setenv(k, "secret-value")
    native = run.child_env("N", tmp_path, None)
    rules = run.child_env("R", tmp_path, None)
    jev = run.child_env("S", tmp_path, tmp_path / ".jev-key")
    for env in (native, rules, jev):
        assert "secret-value" not in env.values()
        assert "ANTHROPIC_API_KEY" not in env and "TYPESAFE_API_KEY" not in env
    assert not [
        k for k in native if k.startswith("SANCHO") or k == "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"
    ]
    assert rules["CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"] == "1"
    assert rules["SANCHOPANZA_COMPACT_COMMAND"].split()[2:] == ["R", str(tmp_path)]
    assert jev["SANCHOPANZA_COMPACT_COMMAND"].split()[2:] == [
        "S",
        str(tmp_path),
        str(tmp_path / ".jev-key"),
    ]  # noqa: E501


@pytest.mark.skipif(not (RESULTS / "analysis.json").exists(), reason="no run yet")
def test_analysis_is_recomputed_from_the_rows() -> None:
    saved = json.loads((RESULTS / "analysis.json").read_text("utf-8"))
    assert json.loads(json.dumps(analyze.analyse())) == saved


def test_no_key_in_the_results_folder() -> None:
    for path in RESULTS.rglob("*"):
        if path.is_file() and path.suffix in (".jsonl", ".json", ".md", ".py"):
            text = path.read_text("utf-8", errors="replace")
            assert "ts_live_" not in text and "sk-ant-" not in text
    assert not os.path.exists(RESULTS / ".jev-key")
