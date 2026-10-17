"""The guard-pointers lot's launcher, `guard-pointers-run.cmd`, end to end through `cmd.exe` with
the stand-in `claude` and runner, and the REAL install and guard hooks of the development
sanchopanza (main's venv): at each injected compaction the stand-in runs the install's own
PreCompact and SessionStart guard hooks through `hook_env.py`, so the rows carry the chooser
each arm's guard really ran. Free: no model, no API, no Jev, no Docker."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys

import pytest

from tests.test_adopt_guardptr_seal import filled
from tests.test_adopt_long_launch import MAIN_VENV, dry_environment, launch

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
CMD = "guard-pointers-run.cmd"
CHAINS = (
    "conan-io__conan-long60-1",
    "pydantic__pydantic-long60-1",
    "conan-io__conan-long60-2",
    "getmoto__moto-long60-1",
    "getmoto__moto-long60-2",
)
SMOKE = "pydantic__pydantic-long60-1"
DEV_SANCHO = MAIN_VENV / "sanchopanza.exe"

windows = pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
dev = pytest.mark.skipif(not DEV_SANCHO.exists(), reason="main's venv is not on this machine")


def copy(base: pathlib.Path) -> str:
    """The launcher filled as the owner fills it in the run's root (PY, WT)."""
    return str(filled(base / "run", ROOT / CMD, ROOT))


def lot_environment(base: pathlib.Path, chains: tuple[str, ...], model: str,
                    pre: int) -> dict[str, str]:  # fmt: skip
    """`dry_environment` with the development sanchopanza (it has the pointer guard and
    --guard-full) and a compaction at the second call of every arm, its guard hooks run."""
    env = dry_environment(base, chains)
    config = json.loads((base / "dry.json").read_text(encoding="utf-8"))
    (base / "dry.json").write_text(json.dumps({**config, "sancho": str(DEV_SANCHO)}),
                                   encoding="utf-8")  # fmt: skip
    inject = {f"{c}-{model}-{a}": {"2": "compact"} for c in chains for a in ("P", "F")}
    return {**env, "FAKE_CLAUDE_INJECT": json.dumps(inject), "FAKE_COMPACT_PRE": str(pre),
            "FAKE_RUN_GUARD": "1", "FAKE_CONTEXT_SCALE": "0.5"}  # fmt: skip


def _row(root: pathlib.Path, run: str, arm: str) -> dict:
    return json.loads((root / "runs" / run / arm / "row.json").read_text(encoding="utf-8"))


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@windows
@dev
def test_the_launcher_runs_p_and_f_on_each_chain_with_their_own_guard(tmp_path) -> None:
    env = lot_environment(tmp_path, CHAINS, "sonnet", 160_500)
    code = launch(copy(tmp_path), ["0000000", "dry"], env, timeout=1500)
    root = tmp_path / "L"
    log = _text(root / "launch.log")
    assert code in (0, 3), log
    assert "keyless: no TypeSafe key is read and no preflight is asked" in log
    assert not (root / "preflight.txt").exists() and "ceiling 250.00 (hard, in code)" in log
    assert code != 0 or ("graded apart" in log and not (root / "grade.log").exists())
    for chain in CHAINS:
        for arm, chooser in (("P", "pointers"), ("F", "struct")):
            row = _row(root, f"{chain}-sonnet", arm)
            assert row["arm"] == arm and not row.get("stopped"), row.get("stopped")
            assert row["window"]["configured"] == 193_000
            built = [g for call in row["calls"] for g in call.get("guard") or []]
            assert [g["chooser"] for g in built] == [chooser], built
            evidence = root / "runs" / f"{chain}-sonnet" / arm
            settings = _text(evidence / "install" / ".claude" / "settings.json")
            assert ('"SANCHOPANZA_GUARD_CHOOSER": "struct"' in settings) == (arm == "F")
            assert "--parts 6" in settings if arm == "F" else "--parts" not in settings
            hooks = [json.loads(x) for x in _text(evidence / "hooks.jsonl").splitlines()]
            assert hooks and not any(h.get("key") for h in hooks)  # never a key in the hooks
            assert not list(evidence.glob("archive"))  # the archive is the install's, not ours
    assert not (root / "STOP").exists()


@windows
@dev
def test_the_smoke_runs_haiku_compacting_near_67k(tmp_path) -> None:
    env = lot_environment(tmp_path, (SMOKE,), "haiku", 67_500)
    code = launch(copy(tmp_path), ["0000000", "smoke", "dry"], env)
    root = tmp_path / "L"
    assert code in (0, 3), _text(root / "launch.log")
    assert "ceiling 8.00 (hard, in code)" in _text(root / "launch.log")
    for arm, chooser in (("P", "pointers"), ("F", "struct")):
        row = _row(root, f"{SMOKE}-haiku", arm)
        assert row["window"]["configured"] == 100_000 and not row.get("stopped")
        assert [g["chooser"] for c in row["calls"] for g in c.get("guard") or []] == [chooser]


@windows
@dev
def test_a_compaction_where_the_window_never_took_stops_the_launch(tmp_path) -> None:
    env = lot_environment(tmp_path, CHAINS, "sonnet", 67_500)
    assert launch(copy(tmp_path), ["0000000", "dry"], env, timeout=900) == 4
    assert "compacted at 67500" in _text(tmp_path / "L" / "STOP")


@windows
def test_the_launcher_needs_a_seal_and_takes_30_smoke_and_dry_only(tmp_path) -> None:
    env = dry_environment(tmp_path, CHAINS)
    assert launch(CMD, ["0000000", "dry"], env) == 2  # the tracked file: placeholders, refused
    cmd = copy(tmp_path)
    assert launch(cmd, [], env) == 2
    assert launch(cmd, ["dry"], env) == 2
    assert launch(cmd, ["0000000", "x"], env) == 2
    assert launch(cmd, ["0000000", "smoke", "x"], env) == 2
    no_root = {k: v for k, v in env.items() if k != "LL_ROOT"}
    assert launch(cmd, ["0000000", "dry"], {**no_root, "LL_ROOT": ""}) == 2


def test_the_launcher_pins_claude_code_and_its_roots() -> None:
    text = (ROOT / CMD).read_bytes().decode("utf-8")
    assert r"claude-pin\2.1.287" in text and "DISABLE_AUTOUPDATER=1" in text
    for root in (r"C:\sp-runs\L-guardptr", r"C:\sp-runs\L-guardptr30", "L-guardptr-smoke"):
        assert root in text
    assert "long_launch.py %PROFILE% --seal %SEAL%" in text and "RebootPending" in text


def test_no_chain_starts_between_midnight_and_eight(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ADOPT))
    import long_run
    import long_start

    p = long_run.PROFILES["guardptr"]
    held = lambda: ""  # noqa: E731  (updates not paused)
    assert long_start.quiet_refusal(p, False, dt.datetime(2026, 10, 17, 5, 0), held)
    assert long_start.quiet_refusal(p, False, dt.datetime(2026, 10, 17, 0, 30), held)
    assert long_start.quiet_refusal(p, False, dt.datetime(2026, 10, 17, 8, 5), held) == ""
    assert long_start.quiet_refusal(p, True, dt.datetime(2026, 10, 17, 5, 0), held) == ""
    assert long_start.quiet_refusal(long_run.PROFILES["compact"], False,
                                    dt.datetime(2026, 10, 17, 5, 0), held) == ""  # fmt: skip
    # Amendment 1: updates paused past the margin lift the hours, for the guard lot only.
    paused = lambda: "Windows Update paused until 2026-10-24 01:10 UTC"  # noqa: E731
    assert long_start.quiet_refusal(p, False, dt.datetime(2026, 10, 17, 5, 0), paused) == ""
    assert dt.timedelta(hours=16) <= long_start.winupdate.MARGIN  # the lot's slowest wall
    # The log notes a lift only where the hours would have held.
    night, day = dt.datetime(2026, 10, 17, 5, 0), dt.datetime(2026, 10, 17, 14, 0)
    assert "paused until" in long_start.quiet_lift_note(p, False, night, paused)
    assert long_start.quiet_lift_note(p, False, day, paused) == ""
    assert long_start.quiet_lift_note(p, False, night, held) == ""
    assert long_start.quiet_lift_note(p, True, night, paused) == ""
    assert long_start.quiet_lift_note(long_run.PROFILES["compact"], False, night, paused) == ""
    for name in [n for n in sys.modules if n.startswith(("long_", "run", "docker_env"))]:
        sys.modules.pop(name, None)
