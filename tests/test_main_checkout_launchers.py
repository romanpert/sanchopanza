"""The launchers that take Python from the main checkout name no local path: they find it by git's
common directory (the folder above it is the main checkout, the only one with a `.venv`), and
refuse with exit 2 and a logged line when it is not there.

The six adopt launchers (`benchmarks/adopt_d`, `benchmarks/adopt_dev`) also run from the main
checkout, as they always did. The long and F2 launchers run from their own worktree and take
SANCHOPANZA_PY first. The refusals run for real, on copies in a scratch folder: nothing past
them (Claude Code, Docker, a runner) is reached.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMON_DIR = (
    'for /f "delims=" %%G in (\'git -C "%~dp0." rev-parse --path-format^=absolute'
    " --git-common-dir 2^>nul') do set "
)
# launcher -> (tag of its log lines, the log under %L%, the python call it guards)
ADOPT = {
    "benchmarks/adopt_d/run-d.cmd": ("D", "D.log", "benchmarks\\adopt_d\\run_d.py run"),
    "benchmarks/adopt_d/run-validate.cmd": (
        "VALIDATION", "validate.out", "benchmarks\\adopt_d\\validate_d.py run"),
    "benchmarks/adopt_dev/run-probe-alwaysload.cmd": (
        "PROBE", "probe.log", "-m benchmarks.adopt_dev.probe_alwaysload run"),
    "benchmarks/adopt_dev/run-probe-auto.cmd": (
        "PROBE", "probe.log", "-m benchmarks.adopt_dev.probe_auto run"),
    "benchmarks/adopt_dev/run-probe-need.cmd": (
        "PROBE", "probe.log", "-m benchmarks.adopt_dev.probe_need run"),
    "benchmarks/adopt_dev/run-probe-nudge.cmd": (
        "PROBE", "probe.log", "-m benchmarks.adopt_dev.probe_nudge run"),
}  # fmt: skip
OWN_WORKTREE = ("f2-night-run.cmd", "long-compact-run.cmd", "long-gate-run.cmd",
                "long-noise-run.cmd", "long-pilot-a-run.cmd", "long-smoke-run.cmd")  # fmt: skip
WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="runs a launcher in cmd.exe")


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="ascii")


@pytest.mark.parametrize("rel", sorted(ADOPT))
def test_an_adopt_launcher_runs_in_the_main_checkout_found_by_git(rel: str) -> None:
    tag, log, call = ADOPT[rel]
    text = _text(rel)
    assert "Users" not in text and "proyectos" not in text and "%~dp0.." not in text
    assert COMMON_DIR + '"MAIN=%%~dpG"' in text
    assert 'set "PY=%MAIN%.venv\\Scripts\\python.exe"' in text
    refusal = rf'echo {tag} REFUSED: [^\n>]+>> "%L%\\{re.escape(log)}"\n  exit /b 2'
    refusals = re.findall(refusal, text)
    assert len(refusals) == 2  # no checkout, no python
    # the refusals, then the main checkout, then the one python call
    order = [text.index(s) for s in ("if not defined MAIN", 'if not exist "%PY%"',
                                     'cd /d "%MAIN%"', f'"%PY%" -u {call}')]  # fmt: skip
    assert order == sorted(order) and text.count('"%PY%"') == 2  # the check and the call


@pytest.mark.parametrize("rel", OWN_WORKTREE)
def test_a_worktree_launcher_takes_sanchopanza_py_else_the_main_checkout(rel: str) -> None:
    text = _text(rel)
    assert "Users" not in text and "proyectos" not in text
    assert 'set "PY=%SANCHOPANZA_PY%"' in text
    assert "if not defined PY " + COMMON_DIR + '"PY=%%~dpG.venv\\Scripts\\python.exe"' in text
    check = text.index('if not exist "%PY%" (')
    assert text.index("set STATUS=%ROOT%\\launch.status") < check
    assert check < min(m.start() for m in re.finditer(r'"%PY%" -', text))  # before any call
    assert "exit /b 2" in text[check : check + 200]


def _run(launcher: Path, env: dict[str, str], *args: str) -> int:
    done = subprocess.run(["cmd.exe", "/c", str(launcher), *args], env=env,
                          capture_output=True, text=True, timeout=60)  # fmt: skip
    return done.returncode


def _env(home: Path, ceiling: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("SANCHOPANZA_PY", "PYTHONPATH")}
    # %L% lands in `home`; git looks for a repository below `ceiling` only
    return {**env, "USERPROFILE": str(home), "GIT_CEILING_DIRECTORIES": str(ceiling)}


@WINDOWS
@pytest.mark.parametrize("rel", ["benchmarks/adopt_d/run-validate.cmd",
                                 "benchmarks/adopt_dev/run-probe-need.cmd"])  # fmt: skip
def test_an_adopt_launcher_refuses_outside_a_checkout_and_without_its_python(
        rel: str, tmp_path: Path) -> None:  # fmt: skip
    tag, log, _ = ADOPT[rel]
    logs = {}
    for case in ("bare", "repo"):
        work = tmp_path / case
        copy = work / rel
        copy.parent.mkdir(parents=True)
        copy.write_text(_text(rel), encoding="ascii", newline="")
        if case == "repo":  # a checkout with no .venv
            subprocess.run(["git", "init", "-q", str(work)], check=True, capture_output=True)
        assert _run(copy, _env(work, tmp_path)) == 2
        folder = re.search(r"set L=%USERPROFILE%\\(.+)", _text(rel)).group(1).strip()
        logs[case] = (work / folder / log).read_text(encoding="utf-8")
    assert logs["bare"].startswith(f"{tag} REFUSED: this launcher is not in a git checkout")
    assert logs["repo"].startswith(f"{tag} REFUSED: no python in the main checkout's .venv")


@WINDOWS
def test_a_worktree_launcher_refuses_without_a_python(tmp_path: Path) -> None:
    work, root = tmp_path / "wt", tmp_path / "root"
    work.mkdir()
    copy = work / "long-gate-run.cmd"
    copy.write_text(_text("long-gate-run.cmd"), encoding="ascii", newline="")
    dry = {"LL_ROOT": root, "LL_PIN": tmp_path / "pin", "LL_MANIFESTS": tmp_path / "m",
           "LL_DRY_CONFIG": tmp_path / "dry.json"}  # fmt: skip
    env = {**_env(tmp_path, tmp_path), **{k: str(v) for k, v in dry.items()}}
    assert _run(copy, env, "dry") == 2
    status = (root / "launch.status").read_text(encoding="utf-8")
    assert "refused" in status and "no python" in status and "start" not in status
