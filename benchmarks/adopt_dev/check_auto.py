"""Free checks before the find-auto probe spends anything. No question reaches Jev or Claude, and
no image is pulled.

    python -m benchmarks.adopt_dev.probe_auto check          # after the freeze: all of it
    python -m benchmarks.adopt_dev.probe_auto check --dev    # before it: this checkout's hook

1. the confirmation's seal holds; the plan is the need table's development set, S only, none of
   phase D's ids; `AUTO_COMMIT` is set and frozen (skipped with --dev, and said so);
2. Claude Code 2.1.285 is first on PATH; ADOPT_SANCHO is the frozen copy of AUTO_COMMIT with jev
   and mcp, and the S hooks build JevDecider (`run.decider_probe`: building it sends no question)
   (both skipped with --dev);
3. every planned id is in verified-rows.json with the harness's image name, in the registry
   (`docker manifest inspect`, no pull);
4. end to end on a local fake endpoint (`auto_e2e.py`): the sealed runner's own wiring
   (`run.install_sancho` with `--find-auto`, hooks and server through `hook_env.py`, a key path
   that does not exist, so the hook ranks with free BM25), `claude -p` of 2.1.285: the server
   connected at init, find_in_repo in the first request and find_auto not, the hook's places in
   the fifth request and in no earlier one, one journal row `free` at search 4. With --dev the
   same check runs a plain install from this checkout's .venv.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import auto_e2e
from .check_need import image_problems
from .common import (
    AUTO_COMMIT,
    CLAUDE_DIR,
    CLAUDE_VERSION,
    OUT,
    PLAN,
    auto_refusal,
    plan_refusal,
    run,
)

CHECK = OUT / "check"
DEV_SANCHO = Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "sanchopanza.exe"


def sealed_e2e() -> tuple[list[str], dict[str, Any]]:
    """The e2e through `run.install_sancho` (patched by probe_auto to add --find-auto)."""
    out = CHECK / "e2e"

    def install(work: Path, evidence: Path) -> Path:
        return run.install_sancho(work, evidence, CHECK / "no.key")  # no key: free BM25

    env = {**run.child_env("", ""), "DISABLE_AUTOUPDATER": "1"}
    return auto_e2e.run(CLAUDE_DIR / "claude.exe", out, install, env)


def dev_e2e() -> tuple[list[str], dict[str, Any]]:
    out = CHECK / "e2e-dev"
    claude = CLAUDE_DIR / "claude.exe"
    env = auto_e2e.child_env(DEV_SANCHO, claude, out)
    return auto_e2e.run(claude, out, auto_e2e.plain_install(DEV_SANCHO, env), env)


def check(dev: bool = False) -> int:
    import confirm  # benchmarks/adopt is on the path (common.py)

    problems: list[str] = []
    notes: list[str] = []
    if not confirm.seal_holds():
        problems.append("the confirmation's seal does not hold")
    pending = auto_refusal()
    why = plan_refusal()
    if why and why != pending:
        problems.append(why)
    if pending:
        (notes if dev else problems).append(pending)
    if (found := run.claude_version()) != CLAUDE_VERSION:
        problems.append(f"Claude Code {found or 'none'} first on PATH, not {CLAUDE_VERSION}")
    stamp, decider = run.frozen_stamp() or {}, "not probed (--dev)"
    if not dev:
        if stamp.get("commit") != AUTO_COMMIT or not {"jev", "mcp"} <= set(stamp.get("extras", [])):
            problems.append(f"frozen copy: {stamp}")
        keyfile = run.keyfile_from_indagis()
        try:
            decider = run.decider_probe(keyfile)
        finally:
            keyfile.unlink(missing_ok=True)
        if decider != run.HELD_DECIDER:
            problems.append(f"the S hooks would build {decider}")
    more, images = image_problems([name for name, _ in PLAN])
    problems += more
    CHECK.mkdir(parents=True, exist_ok=True)
    e2e_problems, seen = dev_e2e() if dev else sealed_e2e()
    problems += [f"e2e: {p}" for p in e2e_problems]
    print(json.dumps({"claude": found, "frozen": stamp, "decider": decider, "images": images,
                      "e2e": seen, "dev": dev}, indent=1, ensure_ascii=False))  # fmt: skip
    for note in notes:
        print(f"CHECK PENDING: {note}", flush=True)
    for problem in problems:
        print(f"CHECK FAILED: {problem}", flush=True)
    if not problems:
        print("CHECK OK (dev: the frozen copy is still to make)" if dev else "CHECK OK", flush=True)
    return 1 if problems else 0
