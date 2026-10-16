"""The guard-pointers lot runs only from its sealing commit (`benchmarks/adopt/guardptr_seal.py`),
checked by `long_launch.py` before anything is spent, through the launcher's real entry point
(`cmd.exe`, the filled copy that sets ADOPT_LAUNCHER). Free: git and hashes; the dry launch uses
the stand-in `claude` and runner, no model, no API, no Jev, no Docker."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from tests.test_adopt_long_launch import MAIN_VENV, dry_environment, launch

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
SMOKE = "pydantic__pydantic-long60-1"
PYTHON = MAIN_VENV / "python.exe"


@pytest.fixture
def seal_mod(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ADOPT))
    import guardptr_seal

    yield guardptr_seal
    sys.modules.pop("guardptr_seal", None)


def _git(repo: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "core.autocrlf=false", *args], capture_output=True, text=True,
                          check=True)  # fmt: skip
    return done.stdout.strip()


def sealed_repo(base: pathlib.Path, seal_mod) -> tuple[pathlib.Path, str, str]:  # noqa: ANN001
    """A repository holding the sealed files (copied from this tree), the instrument committed,
    then sealed in its own commit. Returns (repo, instrument, sealing commit)."""
    repo = base / "sealed"
    files = [seal_mod.PREREG, seal_mod.LAUNCHER, *seal_mod.sealed(ROOT)]
    for rel in files:
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    (repo / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "instrument")
    instrument = _git(repo, "rev-parse", "HEAD")
    seal_mod.seal(repo)
    _git(repo, "add", seal_mod.SHA, seal_mod.MANIFEST)
    _git(repo, "commit", "-q", "-m", f"seal: instrument {instrument}")
    return repo, instrument, _git(repo, "rev-parse", "HEAD")


def filled(base: pathlib.Path, source: pathlib.Path, worktree: pathlib.Path,
           keys: pathlib.Path | None = None) -> pathlib.Path:  # fmt: skip
    """The launcher as the owner fills it in the run's root: PY, WT and, when given, the keys
    file (SANCHOPANZA_KEYS_ENV), nothing else."""
    text = source.read_bytes().decode("utf-8")
    text = text.replace('set "PY=<PYTHON>"', f'set "PY={PYTHON}"', 1)
    text = text.replace('set "WT=<WORKTREE>"', f'set "WT={worktree}"', 1)
    if keys is not None:
        text = text.replace('set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"',
                            f'set "SANCHOPANZA_KEYS_ENV={keys}"', 1)  # fmt: skip
    base.mkdir(parents=True, exist_ok=True)
    out = base / "guard-pointers-run.cmd"
    out.write_bytes(text.encode("utf-8"))
    return out


def test_the_launcher_s_local_values_do_not_change_the_seal(seal_mod, tmp_path) -> None:
    copy = filled(tmp_path / "run", ROOT / seal_mod.LAUNCHER, ROOT, tmp_path / "keys.env")
    assert seal_mod.launcher_text(copy) == seal_mod.launcher_text(ROOT / seal_mod.LAUNCHER)
    other = copy.read_text(encoding="utf-8").replace("exit /b 3", "exit /b 0")
    copy.write_text(other, encoding="utf-8")
    assert seal_mod.launcher_text(copy) != seal_mod.launcher_text(ROOT / seal_mod.LAUNCHER)


def test_the_tracked_launcher_holds_placeholders_only(seal_mod) -> None:
    text = (ROOT / seal_mod.LAUNCHER).read_text(encoding="utf-8")
    assert 'set "PY=<PYTHON>"' in text and 'set "WT=<WORKTREE>"' in text
    assert 'set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"' in text
    assert "Users\\roman" not in text and 'set "ADOPT_LAUNCHER=%~f0"' in text
    assert "git rev-parse HEAD" in text
    assert b"\r\n" in (ROOT / seal_mod.LAUNCHER).read_bytes()  # labels and goto: CRLF
    assert "guard-pointers-run.cmd text eol=crlf" in (ROOT / ".gitattributes").read_text("utf-8")


def test_only_the_sealing_commit_on_a_clean_tree_passes(seal_mod, tmp_path) -> None:
    repo, instrument, head = sealed_repo(tmp_path, seal_mod)
    ran = filled(tmp_path / "run", repo / seal_mod.LAUNCHER, repo)
    assert seal_mod.require_seal(str(ran), instrument, repo) == head
    with pytest.raises(SystemExit, match="not the instrument"):
        seal_mod.require_seal(str(ran), head, repo)
    with pytest.raises(SystemExit, match="ADOPT_LAUNCHER"):
        seal_mod.require_seal("", instrument, repo)
    (repo / "benchmarks/adopt/long_run.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not clean"):
        seal_mod.require_seal(str(ran), instrument, repo)
    _git(repo, "commit", "-q", "-am", "after the seal")
    with pytest.raises(SystemExit, match="not the sealing commit"):
        seal_mod.require_seal(str(ran), instrument, repo)


def test_a_seal_commit_that_changes_more_than_the_seal_is_refused(seal_mod, tmp_path) -> None:
    repo, instrument, _ = sealed_repo(tmp_path, seal_mod)
    _git(repo, "reset", "-q", "--soft", "HEAD^")
    (repo / seal_mod.PREREG).write_text("edited with the seal\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seal and an edit")
    with pytest.raises(SystemExit, match="changes"):
        seal_mod.require_seal_commit(repo)


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
@pytest.mark.skipif(not PYTHON.exists(), reason="main's venv is not on this machine")
def test_the_real_entry_point_checks_the_seal_before_anything(seal_mod, tmp_path) -> None:
    repo, instrument, head = sealed_repo(tmp_path, seal_mod)
    env = dry_environment(tmp_path, (SMOKE,))
    config = json.loads((tmp_path / "dry.json").read_text(encoding="utf-8"))
    dev = str(MAIN_VENV / "sanchopanza.exe")
    (tmp_path / "dry.json").write_text(json.dumps({**config, "sancho": dev,
                                                   "seal_repo": str(repo)}),
                                       encoding="utf-8")  # fmt: skip
    ran = filled(tmp_path / "run", ROOT / seal_mod.LAUNCHER, ROOT)
    assert launch(str(ran), [instrument, "smoke", "dry"], env) in (0, 3)
    root = tmp_path / "L"
    log = (root / "launch.log").read_text(encoding="utf-8", errors="replace")
    assert f"HEAD {head} (the sealing commit)" in log
    assert f"seal HEAD {head}" in (root / "launch.status").read_text(encoding="utf-8")
    # a copy changed beyond its local values: refused before any call
    root = tmp_path / "L2"
    changed = filled(tmp_path / "bad", ROOT / seal_mod.LAUNCHER, ROOT)
    changed.write_bytes(changed.read_bytes().replace(b"exit /b 3", b"exit /b 4"))
    assert launch(str(changed), [instrument, "smoke", "dry"], {**env, "LL_ROOT": str(root)}) == 1
    log = (root / "launch.log").read_text(encoding="utf-8", errors="replace")
    assert "differs from the sealed" in log and not (root / "runs").exists()
    # the wrong frozen copy: refused
    root = tmp_path / "L3"
    assert launch(str(ran), [head, "smoke", "dry"], {**env, "LL_ROOT": str(root)}) == 1
    assert "not the instrument" in (root / "launch.log").read_text(encoding="utf-8")


def test_every_repository_module_the_run_imports_is_sealed(seal_mod) -> None:
    """The seal derives its files from the imports; this checks it against what Python really
    loads when the lot's entry modules are imported as the runner imports them."""
    code = (
        "import sys, json; sys.path[:0] = sys.argv[1:3]; sys.path.append(sys.argv[3]); "
        "import long_launch, long_run, long_pointers_read, guardptr_seal, hook_env, perbug, long; "
        "print(json.dumps([getattr(m, '__file__', None) for m in list(sys.modules.values())]))"
    )
    paths = [str(ADOPT), str(ROOT / "benchmarks" / "memory_carry"), str(ROOT / "benchmarks")]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run([sys.executable, "-c", code, *paths], capture_output=True, text=True,
                          check=True, env=env)  # fmt: skip
    loaded = {pathlib.Path(f).resolve() for f in json.loads(done.stdout) if f}
    sealed = {(ROOT / rel).resolve() for rel in seal_mod.sealed(ROOT)}
    repo_modules = {f for f in loaded if ROOT.resolve() in f.parents and ".venv" not in f.parts}
    assert repo_modules and not repo_modules - sealed, sorted(repo_modules - sealed)
    for rel in ("benchmarks/adopt/masking.py", "benchmarks/adopt/related.py",
                "benchmarks/adopt/chains.py", "benchmarks/memory_carry/carry_s.py",
                "benchmarks/memory_carry/rules.py", "benchmarks/memory_carry/scenes_stale.py",
                "src/sanchopanza/harness/compact_hook.ts",
                "src/sanchopanza/candor/frontier_measured.json", "pyproject.toml"):  # fmt: skip
        assert rel in seal_mod.sealed(ROOT), rel


def test_the_frozen_copy_must_carry_the_sealed_package(seal_mod, tmp_path) -> None:
    exe = tmp_path / "frozen" / "Scripts" / "sanchopanza.exe"
    site = tmp_path / "frozen" / "Lib" / "site-packages" / "sanchopanza"
    found = {"src/sanchopanza/a.py": seal_mod._digest(ROOT / "pyproject.toml"),
             "src/sanchopanza/data.json": "0" * 64, "benchmarks/x.py": "1" * 64}  # fmt: skip
    site.mkdir(parents=True)
    (site / "a.py").write_bytes((ROOT / "pyproject.toml").read_bytes())
    assert seal_mod.frozen_refusal(exe, found) == ""  # data.json not installed: not compared
    (site / "a.py").write_text("other\n", encoding="utf-8")
    assert "a.py differs" in seal_mod.frozen_refusal(exe, found)
    (site / "a.py").unlink()
    assert "a.py missing" in seal_mod.frozen_refusal(exe, found)


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
@pytest.mark.skipif(not PYTHON.exists(), reason="main's venv is not on this machine")
def test_the_token_arrives_through_the_keys_file_the_copy_names(seal_mod, tmp_path) -> None:
    """No CLAUDE_CODE_OAUTH_TOKEN anywhere in the environment: only the keys file the filled copy
    names carries it, as on the real path (a launch by WMI gets no window variables)."""
    env = dry_environment(tmp_path, (SMOKE,))
    config = json.loads((tmp_path / "dry.json").read_text(encoding="utf-8"))
    config = {**config, "sancho": str(MAIN_VENV / "sanchopanza.exe"), "env": {}}
    (tmp_path / "dry.json").write_text(json.dumps(config), encoding="utf-8")
    keys = tmp_path / "keys" / "owner.env"
    keys.parent.mkdir()
    keys.write_text("OTHER=1\nCLAUDE_CODE_OAUTH_TOKEN=fake-token-from-the-file\n", encoding="utf-8")
    ran = filled(tmp_path / "run", ROOT / seal_mod.LAUNCHER, ROOT, keys)
    scrub = ("CLAUDE_CODE_OAUTH_TOKEN", "SANCHOPANZA_KEYS_ENV", "PYTHONPATH", "CLAUDE_CONFIG_DIR",
             "TYPESAFE_API_KEY")  # fmt: skip
    full = {k: v for k, v in {**os.environ, **env}.items() if k not in scrub}
    done = subprocess.run(["cmd.exe", "/c", str(ran), "0000000", "smoke", "dry"], env=full,
                          capture_output=True, text=True, timeout=600)  # fmt: skip
    root = tmp_path / "L"
    log = (root / "launch.log").read_text(encoding="utf-8", errors="replace")
    assert done.returncode in (0, 3), log
    assert (root / "runs" / f"{SMOKE}-haiku" / "P" / "row.json").exists()
    assert "fake-token-from-the-file" not in log
    # the same copy without the file's token refuses before any call
    keys.write_text("OTHER=1\n", encoding="utf-8")
    again = {**full, "LL_ROOT": str(tmp_path / "L2")}
    done = subprocess.run(["cmd.exe", "/c", str(ran), "0000000", "smoke", "dry"], env=again,
                          capture_output=True, text=True, timeout=600)  # fmt: skip
    assert done.returncode == 1
    assert not (tmp_path / "L2" / "runs").exists()


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_a_real_launch_refuses_the_keys_placeholder(seal_mod, tmp_path) -> None:
    ran = filled(tmp_path / "run", ROOT / seal_mod.LAUNCHER, ROOT)
    full = {k: v for k, v in os.environ.items() if k != "SANCHOPANZA_KEYS_ENV"}
    done = subprocess.run(["cmd.exe", "/c", str(ran), "0000000"], env=full, capture_output=True,
                          text=True, timeout=120)  # fmt: skip
    assert done.returncode == 2 and "fill SANCHOPANZA_KEYS_ENV" in done.stdout
