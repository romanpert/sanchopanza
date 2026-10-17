"""Every tracked `*-run.cmd` calls its own lot's script and writes to its own lot's folder.

A launcher made by copying another one kept the other lot's folder and script (C4's started as
B4's: it would have run B4's paid step and logged into B4's folder). This test reads, from each
tracked launcher, the benchmark scripts it calls and the folders it sets (OUT, ROOT,
SANCHOPANZA_*_RUN), and compares them with the table below. A new launcher must be added to the
table, or the test fails.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = re.compile(r"benchmarks[\\/][A-Za-z0-9_\\/.-]+?\.py", re.IGNORECASE)
FOLDER = re.compile(r'\bset\s+"?(OUT|ROOT|SANCHOPANZA_[A-Z0-9_]+_RUN)=([^"\r\n]+)', re.IGNORECASE)
CACHE = "%USERPROFILE%\\.cache\\sanchopanza\\"
MEMORY = "docs/results/2026-10-02-memory-carry/"
ADOPT = {"benchmarks/adopt/long_launch.py"}  # it starts long_run.py itself

# launcher -> (benchmark scripts it calls, folders it sets)
LAUNCHERS: dict[str, tuple[set[str], set[str]]] = {
    "a5-unrelated-run.cmd": ({"benchmarks/facts_gate/run.py"}, {CACHE + "a5-unrelated"}),
    "b4-order-run.cmd": ({"benchmarks/passage_fit/run.py"}, {CACHE + "b4-order"}),
    "b6-es-run.cmd": ({"benchmarks/b6_es/b6_run.py"}, {"C:\\sp-runs\\b6-es"}),
    "c4-written-run.cmd": ({"benchmarks/facts_gate/written_run.py"}, {CACHE + "c4-written"}),
    "c5-free-run.cmd": ({"benchmarks/passage_fit/free_confirm.py"}, {CACHE + "c5-free"}),
    "c5b-free-run.cmd": ({"benchmarks/passage_fit/free_confirm_b.py"}, {CACHE + "c5b-free"}),
    "c6-window-run.cmd": ({"benchmarks/b6_es/c6_window.py"}, {CACHE + "c6-window"}),
    "benchmarks/a3_mcp/w17-mcp-post-run.cmd": (
        {"benchmarks/a3_mcp/w17_replay.py"},
        {"C:\\sp-runs\\w17-mcp-post"},
    ),
    "memlot-night-run.cmd": (
        {"benchmarks/memory_carry/handoff_night.py"},
        {"C:\\sp-runs\\memory-w17-redo"},
    ),
    "checkdone-w17-run.cmd": (
        {"benchmarks/jev114/checkdone_w17.py"},
        {"C:\\sp-runs\\jev114", "C:\\sp-runs\\jev114\\checkdone-w17"},
    ),
    "openai-decisions-run.cmd": (
        {"benchmarks/openai_decisions/run.py"},
        {CACHE + "openai-decisions"},
    ),
    "checkdone114-run.cmd": (
        {"benchmarks/jev114/checkdone114.py"},
        {"C:\\sp-runs\\jev114", "C:\\sp-runs\\jev114\\checkdone114"},
    ),
    MEMORY + "v8-run.cmd": ({"benchmarks/memory_carry/carry.py"}, {CACHE + "memory-carry"}),
    MEMORY + "v81h-run.cmd": ({"benchmarks/memory_carry/carry.py"}, {CACHE + "memory-carry"}),
    MEMORY + "v8h-run.cmd": (set(), set()),  # superseded: refuses and exits
    "f1-gate-run.cmd": (
        {"benchmarks/memory_carry/analyze.py", "benchmarks/memory_carry/carry.py"},
        {"C:\\sp-runs\\memory-carry"},
    ),
    "f2-night-run.cmd": ({"benchmarks/memory_carry/handoff_night.py"}, {"C:\\sp-runs\\memory-f2"}),
    "long-compact-run.cmd": (
        ADOPT,
        {"C:\\sp-runs\\L-compact", "C:\\sp-runs\\L-compact-conan2", "%LL_ROOT%"},
    ),
    "long-gate-run.cmd": (ADOPT, {"C:\\sp-runs\\L", "%LL_ROOT%"}),
    "long-noise-run.cmd": (
        ADOPT,
        {f"C:\\sp-runs\\{x}" for x in ("L-ne", "L-n2", "L-n2c", "L-ne2c", "L-a2c")} | {"%LL_ROOT%"},
    ),
    "long-pilot-a-run.cmd": (
        ADOPT,
        {"C:\\sp-runs\\L-pilot-a", "C:\\sp-runs\\L-pilot-a10", "%LL_ROOT%"},
    ),
    "long-smoke-run.cmd": (ADOPT, {"C:\\sp-runs\\L-smoke", "%LL_ROOT%"}),
    "mem-cell-run.cmd": (
        {f"benchmarks/memory_carry/{x}.py" for x in ("carry", "cell", "sendbacks")},
        {"C:\\sp-runs\\memory-carry"},
    ),
    "redundant-drop-run.cmd": (
        {"benchmarks/jev114/redundant_drop.py"},
        {"C:\\sp-runs\\jev114", "C:\\sp-runs\\jev114\\redundant-drop"},
    ),
}


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*-run.cmd"], cwd=ROOT, capture_output=True,
                         text=True, check=True)  # fmt: skip
    return sorted(x for x in out.stdout.splitlines() if x)


def parsed(name: str) -> tuple[set[str], set[str]]:
    text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
    lines = [x for x in text.splitlines() if not x.lstrip().lower().startswith(("rem", "::"))]
    body = "\n".join(lines)
    scripts = {m.replace("\\", "/") for m in SCRIPT.findall(body)}
    folders = {m.group(2).strip() for m in FOLDER.finditer(body)}
    return scripts, folders


def test_every_tracked_launcher_is_in_the_table() -> None:
    assert sorted(LAUNCHERS) == tracked()


@pytest.mark.parametrize("name", sorted(LAUNCHERS))
def test_a_launcher_calls_its_own_script_and_writes_to_its_own_folder(name: str) -> None:
    assert parsed(name) == LAUNCHERS[name]


def errorlevels_in_blocks(text: str) -> list[int]:
    """Lines that read %ERRORLEVEL% inside a ( ) block, where cmd.exe expands it on reading the
    block, before any command in it has run."""
    depth, found = 0, []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.lower().startswith(("rem ", "::")):
            continue
        if line.startswith(")"):
            depth = max(0, depth - 1)
        if depth and "%errorlevel%" in line.lower():
            found.append(n)
        if line.endswith("("):
            depth += 1
    return found


def test_no_tracked_launcher_reads_the_errorlevel_inside_a_block() -> None:
    # The dry branches of f2-night-run.cmd and memlot-night-run.cmd did: they wrote the previous
    # errorlevel to launch.status and exited 0 whatever the dry run returned.
    assert errorlevels_in_blocks("if x (\n  run\n  echo %ERRORLEVEL%\n)\n") == [3]
    assert errorlevels_in_blocks("run\nset CODE=%ERRORLEVEL%\nif x (\n  echo %CODE%\n)\n") == []
    out = subprocess.run(["git", "ls-files", "*.cmd"], cwd=ROOT, capture_output=True, text=True,
                         check=True)  # fmt: skip
    bad = {name: errorlevels_in_blocks((ROOT / name).read_text(encoding="utf-8", errors="replace"))
           for name in out.stdout.split()}  # fmt: skip
    assert {k: v for k, v in bad.items() if v} == {}


DRY = {"f2-night-run.cmd": r"C:\sp-runs\memory-f2",
       "memlot-night-run.cmd": r"C:\sp-runs\memory-w17-redo"}  # fmt: skip


@pytest.mark.skipif(sys.platform != "win32", reason="runs the launcher in cmd.exe")
@pytest.mark.parametrize("code", [0, 7])
@pytest.mark.parametrize("name", sorted(DRY), ids=["a", "b"])
def test_a_dry_run_s_exit_reaches_the_status_and_the_launcher_s_exit(
        name: str, code: int, tmp_path: Path) -> None:  # fmt: skip
    # A copy of the launcher in a scratch folder, its root and Python pointed there, and a stub
    # handoff_night.py that exits with `code`: nothing real is read, written or called.
    work, root = tmp_path / "wt", tmp_path / "root"
    stub = work / "benchmarks" / "memory_carry" / "handoff_night.py"
    stub.parent.mkdir(parents=True)
    stub.write_text(f"import sys\nprint('stub', sys.argv[1:])\nsys.exit({code})\n",
                    encoding="utf-8")  # fmt: skip
    text = (ROOT / name).read_text(encoding="ascii").replace(DRY[name], str(root))
    text = re.sub(r"(?m)^set PY=.*$", lambda _: f"set PY={sys.executable}", text)
    assert str(root) in text and DRY[name] not in text
    (work / name).write_text(text, encoding="ascii", newline="")
    env = {k: v for k, v in os.environ.items() if k != "SANCHOPANZA_KEYS_ENV"}
    got = subprocess.run(["cmd.exe", "/c", str(work / name), "dry"], cwd=work, env=env,
                         capture_output=True, text=True, timeout=60)  # fmt: skip
    assert got.returncode == code
    status = (root / "launch.status").read_text(encoding="utf-8", errors="replace")
    assert status.startswith(f"dry-exit {code} ")
    assert "stub" in (root / "dry.log").read_text(encoding="utf-8", errors="replace")
