"""Every tracked `*-run.cmd` calls its own lot's script and writes to its own lot's folder.

A launcher made by copying another one kept the other lot's folder and script (C4's started as
B4's: it would have run B4's paid step and logged into B4's folder). This test reads, from each
tracked launcher, the benchmark scripts it calls and the folders it sets (OUT, ROOT,
SANCHOPANZA_*_RUN), and compares them with the table below. A new launcher must be added to the
table, or the test fails.
"""

from __future__ import annotations

import re
import subprocess
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
