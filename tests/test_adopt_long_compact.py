"""The context close-out on the long bench (owner, 2026-10-13, 250 USD hard): N-early (window
193,000, compacts near 160k) against N-early-low (window 100,000, what `install --context-budget
67000` writes, compacts near 67k), Sonnet 5.5, one run per arm and chain. N-early-low's
compactions must fire where the prereg says, or the run stops. Free: no model, no API, no Jev,
no Docker."""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

from tests.test_adopt_long_launch import dry_environment, launch

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
CMD = "long-compact-run.cmd"
CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1",
          "conan-io__conan-long60-2", "getmoto__moto-long60-1")  # long_run.COMPACT_CHAINS
FIFTH = "getmoto__moto-long60-2"  # long_run.COMPACT_FIFTH
SIXTH = "iterative__dvc-long60-1"  # long_run.COMPACT_EXTRA


@pytest.fixture
def m(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ADOPT))
    import long_guard
    import long_launch
    import long_run

    yield long_run, long_launch, long_guard
    for name in [n for n in sys.modules if n.startswith(("long_", "run", "docker_env"))]:
        sys.modules.pop(name, None)


def test_the_profile_holds_the_approved_250_hard(m) -> None:
    long_run, long_launch, _ = m
    p = long_run.PROFILES["compact"]
    assert p.arms == ("Ne", "Nl") and p.models == ("sonnet",)
    assert dict(p.call_cap) == {"sonnet": 4.5} and dict(p.chain_cap) == {"sonnet": 25.0}
    assert p.ceiling == p.hard_cap == 250.0
    assert len(p.chains) * len(p.arms) * 25.0 <= 250.0
    assert p.chains == CHAINS
    assert str(long_launch.ROOTS["compact"]).endswith("L-compact")
    others = {k: v for k, v in long_launch.ROOTS.items() if not k.startswith("compact")}
    assert long_launch.ROOTS["compact"] not in others.values()
    taken = set(p.chains)
    for name, chain in (("compact-fifth", FIFTH), ("compact-extra", SIXTH)):
        other = long_run.PROFILES[name]
        assert long_launch.ROOTS[name] == long_launch.ROOTS["compact"]
        assert (other.arms, other.models, other.hard_cap) == (p.arms, p.models, 250.0)
        assert dict(other.chain_cap) == {"sonnet": 25.0} and other.chains == (chain,)
        assert chain not in taken and other.local_stops == ("cap", "wall")
        taken.add(chain)
    with pytest.raises(SystemExit):
        long_run.ceiling_of(p, 251.0)


def test_the_two_arms_differ_by_the_window_only(m) -> None:
    long_run, long_launch, _ = m
    p = long_run.PROFILES["compact"]
    ne, nl = long_run.arm_spec("Ne", p), long_run.arm_spec("Nl", p)
    assert ne.install is None and nl.install is None and not ne.fresh and not nl.fresh
    assert dict(ne.env) == {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "193000"}
    assert dict(nl.env) == {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "100000"}
    assert long_launch.low_window() == 100_000
    # 100,000 - 20k reserve - 13k = 67,000: the install's budget for that window
    assert long_run.COMPACT_LOW_BUDGET == 67_000


def test_nl_compacting_near_67k_is_the_registered_treatment(m) -> None:
    long_run, _, _ = m
    ok = {"compactions": [{"pre": 67_400}, {"pre": 96_000}], "peak_context": 66_900}
    assert long_run.low_window_breaks(ok) == []


def test_nl_compacting_at_ne_s_threshold_or_never_stops_the_run(m) -> None:
    long_run, _, _ = m
    late = long_run.low_window_breaks({"compactions": [{"pre": 160_500}], "peak_context": 60_000})
    assert late and "160500" in late[0]
    never = long_run.low_window_breaks({"compactions": [], "peak_context": 140_000})
    assert never and "140000" in never[0]
    early = long_run.low_window_breaks({"compactions": [{"pre": 20_000}], "peak_context": 0})
    assert early


def test_ne_and_nl_must_share_their_first_prefix(m) -> None:
    _, _, long_guard = m
    assert long_guard.prefix_breaks({"Ne": 15_786, "Nl": 15_790}) == ()
    assert long_guard.prefix_breaks({"Ne": 15_786, "Nl": 17_000})


def test_the_plan_prints_both_windows_and_the_caps(m) -> None:
    long_run, long_launch, _ = m
    names = list(long_run.PROFILES["compact"].chains)
    known = {n: {"bugs": [{}] * 60} for n in names}
    text = "\n".join(long_launch.plan_lines("compact", known, names,
                                            pathlib.Path("Z:/nowhere"), 250.0))  # fmt: skip
    held = 25.0 * 2 * len(names)
    assert f"caps held {held:.2f} USD" in text and "ceiling 250.00 (hard, in code)" in text
    assert "N-early window 193000" in text and "N-early-low window 100000" in text
    assert "Nl" in text and "stops the run" in text


def test_the_launcher_is_lf() -> None:
    assert b"\r\n" not in (ROOT / CMD).read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_the_launcher_runs_both_arms_on_each_chain_without_jev(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, CHAINS)
    nl = f"{CHAINS[0]}-sonnet-Nl"
    inject = {nl: {"2": "compact"}}
    code = launch(CMD, ["dry"], {**env, "FAKE_CLAUDE_INJECT": json.dumps(inject),
                                 "FAKE_COMPACT_PRE": "67500", "FAKE_CONTEXT_SCALE": "0.5"})
    root = tmp_path / "L"
    log = (root / "launch.log").read_text(encoding="utf-8", errors="replace")
    assert code in (0, 3), log  # 3: the dry chains are short; graded or not, both arms ran
    for chain in CHAINS:
        for arm, window in (("Ne", 193_000), ("Nl", 100_000)):
            row = json.loads((root / "runs" / f"{chain}-sonnet" / arm / "row.json")
                             .read_text(encoding="utf-8"))  # fmt: skip
            assert row["arm"] == arm and row["window"]["configured"] == window
            assert not row.get("stopped"), row.get("stopped")
    nl_row = json.loads((root / "runs" / f"{CHAINS[0]}-sonnet" / "Nl" / "row.json")
                        .read_text(encoding="utf-8"))  # fmt: skip
    assert [c["pre"] for call in nl_row["calls"] for c in call.get("compactions") or []] == [67_500]
    assert "jev preflight" not in log and "N-early-low window 100000" in log


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_nl_compacting_where_it_should_not_stops_the_launch(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, CHAINS)
    inject = {f"{chain}-sonnet-Nl": {"2": "compact"} for chain in CHAINS}
    code = launch(CMD, ["dry"], {**env, "FAKE_CLAUDE_INJECT": json.dumps(inject),
                                 "FAKE_COMPACT_PRE": "160500", "FAKE_CONTEXT_SCALE": "0.5"})
    assert code == 4
    root = tmp_path / "L"
    assert "Nl compacted at 160500" in (root / "STOP").read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_the_launcher_takes_extra_and_dry_only(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, CHAINS)
    assert launch(CMD, ["ne"], env) == 2
    assert launch(CMD, ["extra", "ne"], env) == 2
    assert launch(CMD, ["fifth", "x"], env) == 2


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_the_fifth_and_sixth_chains_run_under_the_same_root_and_ceiling(
    tmp_path: pathlib.Path,
) -> None:
    env = {**dry_environment(tmp_path, (*CHAINS, FIFTH, SIXTH)), "FAKE_CONTEXT_SCALE": "0.5"}
    assert launch(CMD, ["dry"], env) in (0, 3)
    assert launch(CMD, ["fifth", "dry"], env) in (0, 3)
    assert launch(CMD, ["extra", "dry"], env) in (0, 3)
    runs = tmp_path / "L" / "runs"
    assert {p.parent.parent.name for p in runs.glob("*/*/row.json")} == {
        f"{c}-sonnet" for c in (*CHAINS, FIFTH, SIXTH)}
    log = (tmp_path / "L" / "launch.log").read_text(encoding="utf-8", errors="replace")
    assert log.count("ceiling 250.00 (hard, in code)") == 3  # one plan per launch, one ledger


def test_a_run_stopped_by_its_cap_lets_the_next_arm_go_on(m, monkeypatch, tmp_path) -> None:  # noqa: ANN001
    long_run, _, long_guard = m
    ran: list[str] = []

    def fake_arm(ctx, chain, arm, status, row):  # noqa: ANN001, ANN202
        ran.append(arm)
        return "cap" if len(ran) == 1 else ""

    monkeypatch.setattr(long_run, "run_arm", fake_arm)
    monkeypatch.setattr(long_guard, "cross_arm_breaks", lambda folder: "")
    chain = {"chain": CHAINS[0]}
    for name, expected, arms in (("compact", "", 2), ("conan-ne2", "cap", 1)):
        ran.clear()
        ctx = long_run.Ctx(long_run.Layout(tmp_path / name), long_run.PROFILES[name], "sonnet")
        assert long_run.run_chain(ctx, chain, {}) == expected
        assert len(ran) == arms
    assert long_run.PROFILES["compact"].local_stops == ("cap", "wall")


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_nl_past_its_peak_without_compacting_stops_the_launch(tmp_path: pathlib.Path) -> None:
    env = dry_environment(tmp_path, CHAINS)  # B2's contexts unscaled: past 110k, no compaction
    assert launch(CMD, ["dry"], env) == 4
    assert "Nl reached" in (tmp_path / "L" / "STOP").read_text(encoding="utf-8")


# ---- the conan-2 repeat (owner 2026-10-14, 45 USD hard; amendment-conan2.md) --------------------

CONAN2 = "conan-io__conan-long60-2"


def test_the_conan2_repeat_holds_45_hard_in_its_own_root(m) -> None:
    long_run, long_launch, long_guard = m
    p, sealed = long_run.PROFILES["compact-conan2"], long_run.PROFILES["compact"]
    assert p.chains == (CONAN2,) and CONAN2 in sealed.chains
    assert (p.arms, p.models, dict(p.call_cap)) == (sealed.arms, sealed.models,
                                                    dict(sealed.call_cap))  # fmt: skip
    assert long_run.arm_order(CONAN2, p.arms) == long_run.arm_order(CONAN2, sealed.arms)
    assert long_run.arm_order(CONAN2, p.arms)[0] == "Nl"  # as in the close-out
    assert dict(p.chain_cap) == {"sonnet": 22.5} and p.ceiling == p.hard_cap == 45.0
    assert p.local_stops == ("cap", "wall") and dict(p.hours) == dict(sealed.hours)
    blocks = long_run.held(long_run.Layout(pathlib.Path("Z:/nowhere")), p, list(p.chains),
                           ["sonnet"])[0]  # fmt: skip
    assert long_guard.plan_refusal(blocks, 45.0) == ""
    root = long_launch.ROOTS["compact-conan2"]
    assert str(root).endswith("L-compact-conan2") and root != long_launch.ROOTS["compact"]
    assert root not in {v for k, v in long_launch.ROOTS.items() if k != "compact-conan2"}
    for cap in (45.01, 76.89, 250.0):
        with pytest.raises(SystemExit):
            long_run.ceiling_of(p, cap)


def test_the_conan2_arms_are_the_close_out_s(m) -> None:
    long_run, _, _ = m
    p, sealed = long_run.PROFILES["compact-conan2"], long_run.PROFILES["compact"]
    for arm in ("Ne", "Nl"):
        assert long_run.arm_spec(arm, p) == long_run.arm_spec(arm, sealed)


@pytest.mark.skipif(os.name != "nt", reason="the launchers are Windows batch files")
def test_the_launcher_runs_the_conan2_repeat_under_its_45_ceiling(tmp_path: pathlib.Path) -> None:
    env = {**dry_environment(tmp_path, (CONAN2,)), "FAKE_CONTEXT_SCALE": "0.5"}
    assert launch(CMD, ["conan2", "x"], env) == 2
    assert launch(CMD, ["conan2", "dry"], env) in (0, 3)
    root = tmp_path / "L"
    log = (root / "launch.log").read_text(encoding="utf-8", errors="replace")
    assert "ceiling 45.00 (hard, in code)" in log and "caps held 45.00 USD" in log
    assert "22.50 per chain and arm" in log and "N-early-low window 100000" in log
    assert {p.parent.name for p in (root / "runs").glob("*/*/row.json")} == {"Ne", "Nl"}
    assert "compact-conan2" in (root / "launch.status").read_text(encoding="utf-8")
