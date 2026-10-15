"""Free checks before the need probe spends anything. No question reaches Jev or Claude, and no
image is pulled.

    python -m benchmarks.adopt_dev.probe_need check

1. the confirmation's seal holds; the plan is the need table's development set, S only, none of
   phase D's ids;
2. Claude Code 2.1.285 is first on PATH; ADOPT_SANCHO is the frozen 7a39a1f copy with jev and mcp;
3. the S arms' hooks build JevDecider (`run.decider_probe`: building it sends no question);
4. every planned id is in verified-rows.json, its image named as the Verified harness names it,
   and the registry has that image (`docker manifest inspect`, no pull);
5. `run.install_sancho` in a scratch repository writes find's server with `"alwaysLoad": true`
   and wires no find-hook (the default install has no nudge), and a `claude -p` of the S arm
   against a local endpoint that answers 400 (dummy key, tool search on: nothing billed) shows
   find_in_repo in its first request with its schema and no `defer_loading`, and the server
   connected at init (`check_alwaysload.captured_request`).
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .check_alwaysload import CHECK, captured_request
from .common import (
    CLAUDE_VERSION,
    FROZEN_COMMIT,
    PLAN,
    plan_refusal,
    read_json,
    run,
    singles_run,
)

MANIFEST_TIMEOUT_S = 120


def image_name(name: str) -> str:
    """The Verified harness's image for an instance: `__` becomes `_1776_`, lower case."""
    return f"swebench/sweb.eval.x86_64.{name.replace('__', '_1776_').lower()}:latest"


def image_problems(names: list[str]) -> tuple[list[str], dict[str, Any]]:
    """Each id in verified-rows.json with the expected image name, and the image in the
    registry (a manifest, not a pull); also whether it is already local."""
    known = singles_run.rows()
    problems: list[str] = []
    seen: dict[str, Any] = {}
    for name in names:
        row = known.get(name)
        if row is None:
            problems.append(f"{name} is not in verified-rows.json")
            continue
        if row["image"] != image_name(name):
            problems.append(f"{name}: image {row['image']}, expected {image_name(name)}")
        try:
            remote = subprocess.run(["docker", "manifest", "inspect", row["image"]],
                                    capture_output=True, text=True,
                                    timeout=MANIFEST_TIMEOUT_S).returncode == 0  # fmt: skip
        except (OSError, subprocess.TimeoutExpired):
            remote = False
        local = subprocess.run(["docker", "image", "inspect", row["image"]],
                               capture_output=True).returncode == 0  # fmt: skip
        if not remote:
            problems.append(f"{name}: no manifest for {row['image']} in the registry")
        seen[name] = {"image": row["image"], "registry": remote, "local": local}
    return problems, seen


def nudge_wired() -> bool:
    """Whether the scratch install wired find-hook (the default install of 7a39a1f does not)."""
    settings = CHECK / "work" / ".claude" / "settings.json"
    hooks = read_json(settings).get("hooks", {}) if settings.exists() else {}
    return any("find-hook" in h.get("command", "")
               for entries in hooks.values() for e in entries
               for h in e.get("hooks", []))  # fmt: skip


def check() -> int:
    import confirm  # benchmarks/adopt is on the path (common.py)

    problems: list[str] = []
    if not confirm.seal_holds():
        problems.append("the confirmation's seal does not hold")
    if why := plan_refusal():
        problems.append(why)
    if (found := run.claude_version()) != CLAUDE_VERSION:
        problems.append(f"Claude Code {found or 'none'} first on PATH, not {CLAUDE_VERSION}")
    stamp = run.frozen_stamp() or {}
    if stamp.get("commit") != FROZEN_COMMIT or not {"jev", "mcp"} <= set(stamp.get("extras", [])):
        problems.append(f"frozen copy: {stamp}")
    keyfile = run.keyfile_from_harness_env()
    try:
        decider = run.decider_probe(keyfile)
    finally:
        keyfile.unlink(missing_ok=True)
    if decider != run.HELD_DECIDER:
        problems.append(f"the S hooks would build {decider}")
    more, images = image_problems([name for name, _ in PLAN])
    problems += more
    CHECK.mkdir(parents=True, exist_ok=True)
    capture_problems, seen = captured_request()
    problems += capture_problems
    if nudge_wired():
        problems.append("the install wired find-hook: not 7a39a1f's default install")
    turn1 = {k: v for k, v in seen.items() if k != "tools"}
    print(json.dumps({"claude": found, "frozen": stamp, "decider": decider, "images": images,
                      "nudge_wired": nudge_wired(), "turn1": turn1}, indent=1))  # fmt: skip
    for problem in problems:
        print(f"CHECK FAILED: {problem}", flush=True)
    if not problems:
        print("CHECK OK", flush=True)
    return 1 if problems else 0
