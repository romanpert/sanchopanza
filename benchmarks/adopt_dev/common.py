"""What a development probe runs with, pinned before the sealed modules are imported.

`run.py` and `hook_env.py` read `ADOPT_SANCHO` when they are imported, so the frozen copy is set
here first, and the private Claude Code 2.1.285 goes first on PATH for this process and its
children. Import the sealed modules from this file only (`from .common import run, ...`), never
before it.

One process, one probe: `ADOPT_DEV_PROFILE` picks it when this module is first imported.
- `alwaysload` (default): the frozen copy of 1ea9302 (find_in_repo's server registered with
  `"alwaysLoad": true`), output dev-alwaysload/, 8.00 USD.
- `nudge`: the frozen copy of 4ee2901 (e57c374's find description, server instructions and
  nudge, with the nudge's once-per-session lock and approval check),
  output dev-nudge/, 14.00 USD, plan from `behaviour-set.json` (`probe_nudge.py`).
- `need`: the frozen copy of 7a39a1f (phase D's: the default install, find alwaysLoad, no nudge,
  the delegation fix), output dev-need/, 12.00 USD, S only on the need-ranked development set of
  `benchmarks/find_need/need-table.json` (`probe_need.py`).
- `auto`: the frozen copy of `AUTO_COMMIT` (the find-auto hook, `harness.find_auto`), installed
  with `--find-auto`, output dev-auto/, 12.00 USD, S only on the need set again
  (`probe_auto.py`). Empty until the owner commits that work and freezes it.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

ADOPT = Path(__file__).resolve().parents[1] / "adopt"
ROOT = Path.home() / ".cache" / "sanchopanza" / "adopt"
PROFILE = os.environ.get("ADOPT_DEV_PROFILE", "alwaysload")
# The find-auto probe's commit (full hash), set once the owner has committed the src work and
# frozen it (`python benchmarks/adopt/freeze.py <commit>`). Empty: nothing frozen yet, and the
# probe refuses to run (`auto_refusal`).
AUTO_COMMIT = "50f605b8ce39e3190c4811c17b79b7a8f2dfc8cb"
# profile -> (frozen commit, output folder, working copies folder, total cap in USD)
PROFILES = {
    "alwaysload": ("1ea9302c8b4c3e63b908b5cd84b5c0204ba5eae1", "dev-alwaysload", "work-dal", 8.00),
    "nudge": ("4ee2901d2cc10fc4967bda6bc915bd33c785eff4", "dev-nudge", "work-dn", 14.00),
    "need": ("7a39a1f0d4ff8e9cf5c99046ee0aa818ffe955d9", "dev-need", "work-dnd", 12.00),
    "auto": (AUTO_COMMIT, "dev-auto", "work-dau", 12.00),
}
if PROFILE not in PROFILES:
    raise RuntimeError(f"ADOPT_DEV_PROFILE={PROFILE!r}; known: {sorted(PROFILES)}")
FROZEN_COMMIT, _OUT, _WORK, TOTAL_CAP_USD = PROFILES[PROFILE]
FROZEN = ROOT / "frozen" / f"{FROZEN_COMMIT[:12]}-jev-mcp"
FROZEN_EXE = FROZEN / "Scripts" / "sanchopanza.exe"
CLAUDE_DIR = ROOT / "claude-2.1.285"
CLAUDE_VERSION = "2.1.285"
OUT = ROOT / _OUT  # evidence and rows of this probe, nothing else
WORK = ROOT / _WORK  # working copies (short: Django's paths are deep)
SINGLES = ROOT / "singles"  # read only: the development N rows of batch dev1
FIND_TOOL = "mcp__sanchopanza__find_in_repo"

_given = os.environ.get("ADOPT_SANCHO")
if _given and Path(_given).resolve() != FROZEN_EXE.resolve():
    raise RuntimeError(f"ADOPT_SANCHO={_given} is not this profile's frozen copy {FROZEN_EXE}")
os.environ["ADOPT_SANCHO"] = str(FROZEN_EXE)
os.environ["DISABLE_AUTOUPDATER"] = "1"
_path = os.environ.get("PATH", "").split(os.pathsep)
if not _path or Path(_path[0]) != CLAUDE_DIR:
    os.environ["PATH"] = os.pathsep.join([str(CLAUDE_DIR), *_path])
sys.path.insert(0, str(ADOPT))

import docker_env  # noqa: E402
import hook_env  # noqa: E402
import run  # noqa: E402
import singles  # noqa: E402
import singles_run  # noqa: E402

__all__ = ["docker_env", "hook_env", "run", "singles", "singles_run"]  # the sealed modules

MODEL = run.MODELS["haiku"]
CALL_CAP_USD = 1.50

# Development singles of `singles-selected.json` (dev1 ran N and S on them, 2026-09-30): only S
# runs again. Then four new development draws (`draw_new`), S and N each.
DEV1 = ("django__django-15315", "django__django-14752", "matplotlib__matplotlib-23412",
        "django__django-11206", "django__django-12708", "django__django-16631")  # fmt: skip
NEW = ("django__django-15104", "sympy__sympy-18763", "django__django-15563",
       "django__django-12143")  # fmt: skip
BEHAVIOUR_SET = Path(__file__).resolve().parent / "behaviour-set.json"
NEED_TABLE = ADOPT.parent / "find_need" / "need-table.json"
# The need-ranked development set (`find_need/need.py`, rule written before the table), in its
# rank order. Five of them were phase A's held-out singles: its confirmation is closed, so the
# held-out refusal does not apply to this profile; phase D's ids still do.
NEED = ("sympy__sympy-20428", "sympy__sympy-20916", "pydata__xarray-7393", "sympy__sympy-12419",
        "django__django-14007", "django__django-15563", "django__django-11211",
        "django__django-14011", "matplotlib__matplotlib-25332",
        "matplotlib__matplotlib-26342")  # fmt: skip


def nudge_plan() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The behaviour-only issues first, then the controls; S then N on each."""
    if not BEHAVIOUR_SET.exists():
        return ()
    drawn = json.loads(BEHAVIOUR_SET.read_text(encoding="utf-8"))
    return tuple((name, ("S", "N")) for name in [*drawn["behaviour"], *drawn["control"]])


# alwaysload: S before N, the question is whether Haiku calls find; if the cap binds, an N goes
# first. nudge: both arms on every issue of the behaviour set.
# need: S only, one session each; the N reference is the recorded sessions of the need table.
# auto: the same, with the find-auto hook; the reference is the need probe's rows.
PLAN: tuple[tuple[str, tuple[str, ...]], ...] = (
    nudge_plan()
    if PROFILE == "nudge"
    else tuple((name, ("S",)) for name in NEED)
    if PROFILE in ("need", "auto")
    else (*((name, ("S",)) for name in DEV1), *((name, ("S", "N")) for name in NEW))
)


def held_out() -> set[str]:
    chosen = json.loads((ADOPT / "singles-selected.json").read_text(encoding="utf-8"))
    return {r["instance_id"] for r in chosen if r["split"] == "held"}


def draw_new() -> list[str]:
    """Two "<15 min fix" and two "15 min - 1 hour" Verified issues, seeded, outside everything the
    find runs used, every single of `singles-selected.json` and every chain's bugs."""
    import pyarrow.parquet as pq
    import swebench  # benchmarks/find, put on the path by `singles`

    chosen = json.loads((ADOPT / "singles-selected.json").read_text(encoding="utf-8"))
    taken = singles.used_by_find() | {r["instance_id"] for r in chosen}
    taken |= {b["instance_id"] for c in run.chains().values() for b in c["bugs"]}
    table = pq.read_table(swebench.DATA / "verified.parquet").to_pylist()
    rows = sorted((r for r in table if r["instance_id"] not in taken),
                  key=lambda r: r["instance_id"])  # fmt: skip
    rng = random.Random(f"{singles.SEED}-dev-alwaysload")
    out: list[str] = []
    for level in ("<15 min fix", "15 min - 1 hour"):
        out += [r["instance_id"] for r in rng.sample([r for r in rows
                                                      if r["difficulty"] == level], 2)]  # fmt: skip
    return out


PHASE_D = ADOPT.parent / "adopt_d" / "singles-d.json"
INSTANCE_ID = re.compile(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+")


def phase_d_ids() -> set[str]:
    """Every instance id anywhere in phase D's draw (held out and spares): never run here."""
    if not PHASE_D.exists():
        return set()
    return set(INSTANCE_ID.findall(PHASE_D.read_text(encoding="utf-8")))


def plan_refusal() -> str | None:
    """Why the plan may not run: a held-out single in it (the confirmation's or phase D's), or
    the draw no longer gives NEW."""
    names = {name for name, _ in PLAN}
    if PROFILE not in ("need", "auto") and (bad := sorted(names & held_out())):
        return f"held-out singles in the plan: {bad}"
    if bad := sorted(names & phase_d_ids()):
        return f"phase D singles in the plan: {bad}"
    if PROFILE == "need":
        return need_refusal()
    if PROFILE == "auto":
        return auto_refusal() or need_refusal()
    if PROFILE == "nudge":
        return nudge_refusal(names)
    if list(NEW) != draw_new():
        return f"the seeded draw gives {draw_new()}, the plan names {list(NEW)}"
    return None


def nudge_refusal(names: set[str]) -> str | None:
    """The nudge plan: ten issues, none excluded by the behaviour set's own rule."""
    from .behaviour_set import check

    if len(names) != 10:
        return f"the nudge plan has {len(names)} issues, not 10 (behaviour-set.json drawn?)"
    if problems := check():
        return "; ".join(problems)
    return None


def auto_refusal() -> str | None:
    """The find-auto probe needs its own frozen copy: a commit, frozen with jev and mcp."""
    if len(AUTO_COMMIT) != 40:
        return ("AUTO_COMMIT is not set: commit the find-auto work, freeze it "
                "(benchmarks/adopt/freeze.py <commit>) and write its full hash in common.py")
    if not FROZEN_EXE.exists():
        return f"no frozen copy at {FROZEN_EXE}: run benchmarks/adopt/freeze.py {AUTO_COMMIT}"
    return None


def need_refusal() -> str | None:
    """The need plan: the table's development set as written here, S only, each id once."""
    if not NEED_TABLE.exists():
        return f"no need table at {NEED_TABLE}"
    drawn = read_json(NEED_TABLE).get("dev_set")
    if drawn != list(NEED):
        return f"the need table's dev_set is {drawn}, the plan names {list(NEED)}"
    if [name for name, _ in PLAN] != list(NEED) or {a for _, arms in PLAN for a in arms} != {"S"}:
        return f"the need plan is not S on each of the set: {PLAN}"
    return None


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
