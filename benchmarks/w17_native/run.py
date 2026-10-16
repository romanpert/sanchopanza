"""W17 runner (DRAFT, not sealed): the memory bridge against the user-scope install and against
clean Claude Code, on F2's scenes (`benchmarks/w17_native/prereg.md`).

F2's runner (`memory_carry/handoff.py`) with its scenes, checks, calls and NOT RUN rules, and
three arms in place of N0/H/S:

- `N0`: clean Claude Code 2.1.287, session 2 with the scene's `continue` line;
- `S`: `sanchopanza install --memory --write` at USER scope, as a user types it, into the arm's
  clean configuration folder (`--path <config>/settings.json`). At user scope the install
  registers no MCP server (it prints the `claude mcp add-json` line; the runner does not run
  it), so S here is lighter than F2's project-scope S;
- `SN`: the same plus `--memory-native` (`harness.memory_native`).

The hooks are rewired through `carry_hook.py` (`carry_s.rewire_settings`), so each arm keeps its
state in its own folder; the decoy rules are seeded as in F2 (`handoff.seed`). Nothing is
installed in the repository itself.

    python benchmarks/w17_native/run.py --run w17-pilot --dry [--out DIR]

Only `--dry` is wired to run here: a live run needs the seal (prereg + review) first, and the
live path below refuses without `--live-after-seal`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CARRY = REPO / "benchmarks" / "memory_carry"
sys.path.insert(0, str(CARRY))
sys.path.insert(0, str(REPO / "benchmarks"))
sys.path.insert(0, str(REPO / "src"))

import carry  # noqa: E402
import carry_s  # noqa: E402
import handoff  # noqa: E402
from scenes_handoff import HANDOFF, HANDOFF_PILOT  # noqa: E402

ARMS = ("N0", "S", "SN")
INSTALL = ("install", "--memory", "--write")  # the user's line; scope user is the default
NATIVE_FLAG = "--memory-native"
NATIVE_ENV = "SANCHOPANZA_MEMORY_NATIVE"
BARE = ("h_judge", "h_loud", "h_merge")  # F2: the continue line names no file step 1 wrote
OUT = Path(r"C:\sp-runs\w17-native")
MODEL = "sonnet"
# Expected cost per arm at Claude Code's list price, F2's Sonnet medians per triple (N0 0.105,
# S 0.127; SN taken as S), for the estimate only; the caps below are what binds.
EXPECTED_ARM_USD = {"N0": 0.105, "S": 0.127, "SN": 0.127}
RUNS: dict[str, dict[str, Any]] = {
    "w17-pilot": {"scenes": HANDOFF_PILOT, "repeats": [0], "cap": 5.0},
    "w17-sonnet": {"scenes": list(HANDOFF), "repeats": [1, 2, 3, 4], "cap": 26.0},
}


def build_plan(run: str) -> list[tuple[str, str, str, int]]:
    """(scene, model, arm, repetition), the arms of a triple one after the other, their order
    rotated from triple to triple and repetition to repetition (as F2)."""
    spec = RUNS[run]
    out = []
    for rep in spec["repeats"]:
        for i, name in enumerate(spec["scenes"]):
            k = (i + rep) % len(ARMS)
            out += [(name, MODEL, arm, rep) for arm in (*ARMS[k:], *ARMS[:k])]
    return out


def folder_name(run: str, triple: int, arm: str) -> str:
    """`t<NN>-<x>`, the letter shuffled per triple with a seed (F2's rule, these arms)."""
    import random

    letters = list(handoff.LETTERS)
    random.Random(f"{run}/{triple}").shuffle(letters)
    return f"t{triple:02d}-{dict(zip(ARMS, letters, strict=True))[arm]}"


def reserve_of(arm: str) -> float:
    """Two sessions, each at its cap plus one worst turn past it, and the Jev reserve for the
    sanchopanza arms (F2's rule)."""
    jev = 2 * carry_s.JEV_RESERVE if arm in ("S", "SN") else 0.0
    return 2 * (handoff.CALL_CAPS[MODEL] + handoff.WORST_TURN[MODEL]) + jev


def estimate(run: str) -> dict[str, float]:
    """The run's expected cost (F2's medians) and its worst case (every arm at its reserve)."""
    plan = build_plan(run)
    return {"arms": len(plan),
            "expected_usd": round(sum(EXPECTED_ARM_USD[a] for *_, a, _r in plan), 2),
            "worst_usd": round(sum(reserve_of(a) for *_, a, _r in plan), 2),
            "cap_usd": RUNS[run]["cap"]}  # fmt: skip


def install_user(work: Path, config: Path, keyfile: Path, native: bool,
                 env: Mapping[str, str]) -> dict[str, Any]:  # fmt: skip
    """`sanchopanza install` at user scope into the arm's clean `config`, from this checkout's
    `src`, then its commands rewired through `carry_hook.py`. Returns what was installed."""
    settings = config / "settings.json"
    line = [sys.executable, "-m", "sanchopanza", *INSTALL, "--path", str(settings),
            *([NATIVE_FLAG] if native else [])]  # fmt: skip
    done = subprocess.run(line, cwd=work, env={**env, "PYTHONPATH": str(REPO / "src")},
                          capture_output=True, text=True, timeout=120, check=False)  # fmt: skip
    (work / "install.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
    if done.returncode or not settings.is_file():
        raise RuntimeError(f"sanchopanza install failed ({done.returncode}): {done.stderr[-400:]}")
    data = json.loads(settings.read_text(encoding="utf-8"))
    rewired = carry_s.rewire_settings(data, work, keyfile)
    settings.write_text(json.dumps(rewired, indent=2) + "\n", encoding="utf-8", newline="\n")
    text = settings.read_text(encoding="utf-8")
    if '"sanchopanza ' in text:
        raise RuntimeError("not every sanchopanza command was rewired")
    native_on = (rewired.get("env") or {}).get(NATIVE_ENV) == "1"
    if native_on != native:
        raise RuntimeError(f"{NATIVE_ENV} is {'on' if native_on else 'off'} in arm {native}")
    memory = sum(
        1
        for entries in (rewired.get("hooks") or {}).values()
        for e in entries
        for h in e.get("hooks", [])
        if " memory-hook" in str(h.get("command"))
    )
    return {"settings": str(settings), "native_env": native_on, "memory_hooks": memory,
            "skill": (config / "skills" / "sanchopanza-code" / "SKILL.md").is_file()}  # fmt: skip


def arm_run(out: Path, work: Path, name: str, arm: str, rep: int, keyfile: Path,
            dry: bool) -> dict[str, Any]:  # fmt: skip
    """One arm: its repository and clean user, the install for S and SN, then (live only) the
    two sessions and the checks through F2's code."""
    rec = out / "arms" / work.name
    work.mkdir(parents=True, exist_ok=True)
    rec.mkdir(parents=True, exist_ok=True)
    repo = carry.build(work, {"files": HANDOFF[name]["files"]}, None)
    config = carry.clean_config(work)
    installed: dict[str, Any] = {}
    if arm in ("S", "SN"):
        installed = install_user(work, config, keyfile, arm == "SN", carry.environment())
        handoff.seed(work, repo, name)
    row = {"scene": name, "model": MODEL, "arm": arm, "repeat": rep, "folder": str(work),
           "bare": name in BARE, "planned": ["session 1: first", "session 2: continue"],
           "installed": installed}  # fmt: skip
    if dry:
        return {**row, "dry": True, "repo": str(repo)}
    raise SystemExit("live sessions are not wired before the seal (prereg.md, review)")


def run_plan(out: Path, run: str, keyfile: Path, dry: bool, work_root: Path) -> list[dict]:
    rows = []
    spent = 0.0
    for index, (name, _model, arm, rep) in enumerate(build_plan(run)):
        if spent + reserve_of(arm) > RUNS[run]["cap"]:
            print(f"stop: the next arm could pass the cap {RUNS[run]['cap']}", flush=True)
            break
        work = work_root / folder_name(run, index // len(ARMS), arm)
        row = arm_run(out, work, name, arm, rep, keyfile, dry)
        rows.append(row)
        spent += 0.0 if dry else float(row.get("cost") or 0.0)
        print(json.dumps({k: row[k] for k in ("scene", "arm", "repeat", "bare", "installed")}),
              flush=True)  # fmt: skip
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", choices=sorted(RUNS), required=True)
    parser.add_argument("--out")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--estimate", action="store_true")
    args = parser.parse_args(argv)
    if args.estimate:
        print(json.dumps(estimate(args.run)))
        return 0
    if not args.dry:
        raise SystemExit("only --dry before the seal")
    out = Path(args.out) if args.out else OUT / f"{args.run}-dry"
    rows = run_plan(out, args.run, out / "typesafe.key", True, out / "w")
    (out / "dry.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(json.dumps({"arms": len(rows), **estimate(args.run)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
