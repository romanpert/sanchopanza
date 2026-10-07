"""The window and noise round on the long bench (owner, 2026-10-07): N-early on the gate's two
chains and a second run of N on pydantic, Sonnet 5.5, hard ceilings that add up to the 110 USD the
owner approved. Free: no model, no API, no Jev, no Docker."""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

from tests.test_adopt_long_launch import dry_environment, launch

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
GATE = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")
CMD = "long-noise-run.cmd"


@pytest.fixture
def m(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ADOPT))
    import long_launch
    import long_run

    yield long_run, long_launch
    for name in [n for n in sys.modules if n.startswith(("long_", "run", "docker_env"))]:
        sys.modules.pop(name, None)


def test_the_two_profiles_hold_the_approved_110(m) -> None:
    long_run, _ = m
    ne, n2 = long_run.PROFILES["noise-ne"], long_run.PROFILES["noise-n"]
    assert ne.arms == ("Ne",) and ne.models == ("sonnet",) and ne.chains == GATE
    assert dict(ne.call_cap) == {"sonnet": 4.5} and dict(ne.chain_cap) == {"sonnet": 35.0}
    assert ne.ceiling == ne.hard_cap == 70.0 and ne.window == 193_000
    assert n2.arms == ("N",) and n2.models == ("sonnet",) and n2.chains == (GATE[1],)
    assert dict(n2.call_cap) == {"sonnet": 4.5} and dict(n2.chain_cap) == {"sonnet": 40.0}
    assert n2.ceiling == n2.hard_cap == 40.0
    assert ne.ceiling + n2.ceiling == 110.0


def test_their_roots_are_their_own(m) -> None:
    _, long_launch = m
    roots = {long_launch.ROOTS[k] for k in ("noise-ne", "noise-n", "gate", "pilot-a", "smoke")}
    assert len(roots) == 5
    assert str(long_launch.ROOTS["noise-ne"]).endswith("L-ne")
    assert str(long_launch.ROOTS["noise-n"]).endswith("L-n2")


def test_the_plan_prints_the_caps_and_the_window(m) -> None:
    long_run, long_launch = m
    known = {n: {"bugs": [{}] * 60} for n in GATE}
    ne = "\n".join(long_launch.plan_lines("noise-ne", known, list(GATE),
                                          pathlib.Path("Z:/nowhere"), 70.0))  # fmt: skip
    assert "caps held 70.00 USD" in ne and "ceiling 70.00 (hard, in code)" in ne
    assert "193000" in ne
    n2 = "\n".join(long_launch.plan_lines("noise-n", known, [GATE[1]],
                                          pathlib.Path("Z:/nowhere"), 40.0))  # fmt: skip
    assert "caps held 40.00 USD" in n2 and "ceiling 40.00 (hard, in code)" in n2


def test_the_launcher_is_lf() -> None:
    assert b"\r\n" not in (ROOT / CMD).read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_the_launcher_runs_ne_on_both_chains_without_jev(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, GATE)
    assert launch(CMD, ["ne", "dry"], env) == 0
    root = tmp_path / "L"
    for chain in GATE:
        row = json.loads((root / "runs" / f"{chain}-sonnet" / "Ne" / "row.json")
                         .read_text(encoding="utf-8"))  # fmt: skip
        assert row["arm"] == "Ne" and row["window"]["configured"] == 193_000
    log = (root / "launch.log").read_text(encoding="utf-8", errors="replace")
    assert "jev-preflight" not in log and "preflight" not in log.split("caps held")[0]


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_the_launcher_runs_n_again_on_pydantic_only(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, GATE)
    assert launch(CMD, ["n", "dry"], env) == 0
    runs = tmp_path / "L" / "runs"
    assert (runs / f"{GATE[1]}-sonnet" / "N" / "row.json").exists()
    assert not (runs / f"{GATE[0]}-sonnet").exists()


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_the_launcher_refuses_another_round(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, GATE)
    assert launch(CMD, ["s", "dry"], env) != 0
