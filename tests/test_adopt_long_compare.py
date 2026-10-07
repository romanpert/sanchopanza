"""`long_compare.py` (and its `pilot_a_compare.py` wrapper) on synthetic rows, grades and diffs.
Free: no model, no API, no Docker."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")
BUGS = ("b1", "b2", "b3", "b4")
CONTEXT = {"b1": 50_000, "b2": 120_000, "b3": 160_000, "b4": 250_000}


@pytest.fixture(scope="module")
def lc() -> Any:
    sys.path.insert(0, str(ADOPT))
    import long_compare

    return long_compare


def _dump(path: pathlib.Path, data: Any) -> None:
    path.write_bytes(json.dumps(data).encode("utf-8"))


def chain_arm(root: pathlib.Path, arm: str, resolved: dict[str, bool], quit: set[str],
              cut_after: int | None = None, chain: str = CHAINS[1]) -> None:  # fmt: skip
    """Four bug calls; a bug in `quit` leaves the code unchanged (a give-up); calls past
    `cut_after` were cut at the cap and never ran."""
    folder = root / "runs" / f"{chain}-sonnet" / arm
    folder.mkdir(parents=True)
    calls, patch = [], ""
    for k, iid in enumerate(BUGS, start=1):
        ran = cut_after is None or k <= cut_after
        if ran and iid not in quit:
            patch += f"diff --git a/src/{iid}.py b/src/{iid}.py\n+fix\n"
        if ran:
            (folder / f"diff-{k}.patch").write_bytes(patch.encode("utf-8"))
        calls.append({"request": k, "kind": "bug", "instance_id": iid,
                      "status": "ran" if ran else "cut", "peak_context": CONTEXT[iid],
                      "owner_usd": 1.0 if ran else 0.0, "requests": 10, "compactions": [],
                      "result_tail": ""})  # fmt: skip
    _dump(folder / "row.json", {"model": "claude-sonnet-5-5", "bugs": 4, "calls": calls,
                                "stopped": "cap" if cut_after else ""})  # fmt: skip
    _dump(folder / "grade.json", {"resolved": sum(resolved.values()), "bugs_total": 4,
                                  "bugs": [{"instance_id": i, "resolved": resolved[i]}
                                           for i in BUGS]})  # fmt: skip


@pytest.fixture()
def three(tmp_path: pathlib.Path, lc: Any) -> dict[str, Any]:
    """N and N2 differ on b2 (noise); Ne was cut before b4, resolves b3 and gives up on none."""
    chain_arm(tmp_path / "N", "N", {"b1": True, "b2": True, "b3": False, "b4": False}, {"b4"})
    chain_arm(tmp_path / "N2", "N", {"b1": True, "b2": False, "b3": False, "b4": False},
              {"b3", "b4"})  # fmt: skip
    chain_arm(tmp_path / "Ne", "Ne", {"b1": True, "b2": True, "b3": True, "b4": False}, set(),
              cut_after=3)  # fmt: skip
    spec = {"N": (tmp_path / "N", "N"), "N2": (tmp_path / "N2", "N"), "Ne": (tmp_path / "Ne", "Ne")}
    return lc.compare(spec)["chains"][CHAINS[1]]


def test_give_ups_come_from_long_report_with_their_context_band(three: dict[str, Any]) -> None:
    n2 = three["arms"]["N2"]
    assert n2["give_ups"]["give_ups"] == 2 and n2["give_ups"]["at_or_past_150k"] == 2
    assert n2["give_up_bands"] == {"150-200k": 1, ">=200k": 1}
    assert three["arms"]["Ne"]["give_ups"]["give_ups"] == 0


def test_bands_cover_every_context(lc: Any) -> None:
    assert [lc.band(c) for c in (0, 99_999, 100_000, 150_000, 199_999, 200_000, 900_000)] == [
        "0-100k",
        "0-100k",
        "100-150k",
        "150-200k",
        "150-200k",
        ">=200k",
        ">=200k",
    ]


def test_a_pair_reads_only_the_bugs_both_arms_ran(three: dict[str, Any]) -> None:
    p = three["pairs"]["N_vs_Ne"]
    assert p["common_ran"] == 3 and p["graded_common"] == 3  # Ne was cut before b4
    assert (p["resolved_discordant"]["treated_only"], p["resolved_discordant"]["control_only"]) == (
        0,
        1,
    )  # b3
    assert (p["give_up_discordant"]["treated_only"], p["give_up_discordant"]["control_only"]) == (
        0,
        0,
    )  # N's b4 give-up is not common


def test_the_noise_floor_is_n_against_n2(three: dict[str, Any]) -> None:
    p = three["pairs"]["N_vs_N2"]
    assert p["common_ran"] == 4
    assert (p["resolved_discordant"]["treated_only"], p["resolved_discordant"]["control_only"]) == (
        1,
        0,
    )  # b2
    assert (p["give_up_discordant"]["treated_only"], p["give_up_discordant"]["control_only"]) == (
        0,
        1,
    )  # b3
    assert set(three["pairs"]) == {"N_vs_N2", "N_vs_Ne", "N2_vs_Ne"}


def test_stable_flips_set_aside_what_n_changes_against_itself(three: dict[str, Any]) -> None:
    flips = three["stable_flips"]["Ne_vs_N+N2"]
    res = flips["resolved"]
    assert res["seen"] == 3 and res["base_agree"] == 2  # b2 is noise; Ne never ran b4
    assert (res["other_true_base_false"], res["other_false_base_true"]) == (1, 0)  # b3
    quit = flips["gave_up"]
    assert quit["base_agree"] == 2  # b3 is noise (N2 gave up, N did not)
    assert (quit["other_true_base_false"], quit["other_false_base_true"]) == (0, 0)
    assert "A_vs_N+N2" not in three["stable_flips"]


def test_flip_bases_are_configurable_and_pairs_follow_the_given_order(
    tmp_path: pathlib.Path, lc: Any
) -> None:
    """A second Ne run as the base (Ne, Ne2) and N as the other: N's b3 miss is a flip against a
    stable Ne pair; N2 is absent, so the default N,N2 bases give nothing."""
    chain_arm(tmp_path / "N", "N", {"b1": True, "b2": True, "b3": False, "b4": False}, {"b4"})
    chain_arm(tmp_path / "Ne", "Ne", {"b1": True, "b2": True, "b3": True, "b4": False}, set())
    chain_arm(tmp_path / "Ne2", "Ne", {"b1": True, "b2": False, "b3": True, "b4": False}, set())
    spec = {"Ne": (tmp_path / "Ne", "Ne"), "Ne2": (tmp_path / "Ne2", "Ne"),
            "N": (tmp_path / "N", "N")}  # fmt: skip
    c = lc.compare(spec, ["Ne,Ne2:N", "N,N2:Ne"])["chains"][CHAINS[1]]
    assert list(c["pairs"]) == ["Ne_vs_Ne2", "Ne_vs_N", "Ne2_vs_N"]
    assert list(c["stable_flips"]) == ["N_vs_Ne+Ne2"]
    res = c["stable_flips"]["N_vs_Ne+Ne2"]["resolved"]
    assert res["base_agree"] == 3  # b1, b3, b4 (b2 is Ne's noise)
    assert (res["other_true_base_false"], res["other_false_base_true"]) == (0, 1)  # b3
    assert lc.parse_flips(["N,N2:Ne"]) == [(("N", "N2"), "Ne")]


def test_cumulative_cost_counts_what_ran_up_to_each_checkpoint(three: dict[str, Any]) -> None:
    ne = three["arms"]["Ne"]
    assert ne["cost_usd"] == 3.0 and ne["calls_ran"] == 3 and ne["stopped"] == "cap"
    assert ne["cumulative_usd"][10] == 3.0 and three["arms"]["N"]["cumulative_usd"][60] == 4.0


def test_a_no_change_call_on_a_bug_already_fixed_is_no_unresolved_give_up(
    tmp_path: pathlib.Path, lc: Any
) -> None:
    """b2 changed no code but resolves (an earlier request fixed it); b4 changed none and fails."""
    chain_arm(tmp_path, "N", {"b1": True, "b2": True, "b3": False, "b4": False}, {"b2", "b4"})
    n = lc.compare({"N": (tmp_path, "N")})["chains"][CHAINS[1]]["arms"]["N"]
    assert n["give_ups"]["give_ups"] == 2
    assert n["gave_up_unresolved"] == {"count": 1, "at_or_past_150k": 1, "contexts": [250_000]}
    assert n["per_bug"]["b2"]["gave_up_unresolved"] is False
    assert n["per_bug"]["b4"]["gave_up_unresolved"] is True


def test_unresolved_give_ups_wait_for_the_grade(tmp_path: pathlib.Path, lc: Any) -> None:
    chain_arm(tmp_path, "N", {"b1": True, "b2": True, "b3": False, "b4": False}, {"b4"})
    (tmp_path / "runs" / f"{CHAINS[1]}-sonnet" / "N" / "grade.json").unlink()
    n = lc.compare({"N": (tmp_path, "N")})["chains"][CHAINS[1]]["arms"]["N"]
    assert n["give_ups"]["give_ups"] == 1 and n["gave_up_unresolved"] is None
    assert n["per_bug"]["b4"]["gave_up_unresolved"] is None


def test_pairs_and_flips_carry_the_unresolved_give_ups(three: dict[str, Any]) -> None:
    floor = three["pairs"]["N_vs_N2"]["gave_up_unresolved_discordant"]
    assert (floor["treated_only"], floor["control_only"]) == (0, 1)  # b3: N2 only
    assert three["arms"]["N2"]["gave_up_unresolved"]["contexts"] == [160_000, 250_000]
    flips = three["stable_flips"]["Ne_vs_N+N2"]["gave_up_unresolved"]
    assert flips["base_agree"] == 2  # b1, b2 (b3 is noise, Ne never ran b4)
    assert (flips["other_true_base_false"], flips["other_false_base_true"]) == (0, 0)


# ---- the pilot's columns, through the wrapper ----------------------------------------------------


def _arm(root: pathlib.Path, chain: str, arm: str, calls: list[dict[str, Any]],
         resolved: int | None, **row: Any) -> None:  # fmt: skip
    folder = root / "runs" / f"{chain}-sonnet" / arm
    folder.mkdir(parents=True)
    body = {"chain": chain, "run": f"{chain}-sonnet", "arm": arm, "model": "claude-sonnet-5-5",
            "bugs": 60, "requests_planned": 62, "stopped": "", "calls": calls,
            "owner_usd": round(sum(c["owner_usd"] for c in calls), 6), **row}  # fmt: skip
    _dump(folder / "row.json", body)
    if resolved is not None:
        _dump(folder / "grade.json", {"resolved": resolved, "bugs_total": 60})


def _call(usd: float, requests: int, peak: int, compactions: int = 0) -> dict[str, Any]:
    return {"status": "ran", "owner_usd": usd, "requests": requests, "peak_context": peak,
            "compactions": [{"pre": 1}] * compactions}  # fmt: skip


def test_the_pilot_wrapper_is_per_chain_descriptive_and_reads_both_roots(
    tmp_path: pathlib.Path,
) -> None:
    gate, pilot = tmp_path / "L", tmp_path / "L-pilot-a"
    _arm(gate, CHAINS[0], "N", [_call(10.0, 100, 300_000, 1), _call(14.0, 80, 420_000)], 30)
    _arm(gate, CHAINS[1], "N", [_call(20.0, 150, 500_000)], None)  # not graded yet
    passages = {"cuts": 40, "r": 0.3, "r_whole": 0.1, "chars_in": 400_000, "chars_out": 100_000}
    _arm(pilot, CHAINS[0], "A", [_call(9.0, 90, 200_000), _call(9.0, 70, 250_000)], 33,
         passages=passages)  # fmt: skip
    _arm(pilot, CHAINS[1], "A", [_call(5.0, 30, 90_000)], 0, stopped="rerequest",
         passages={**passages, "r_whole": 0.6})  # fmt: skip
    out = tmp_path / "compare.json"
    done = subprocess.run([sys.executable, str(ADOPT / "pilot_a_compare.py"), "--gate", str(gate),
                           "--pilot", str(pilot), "--pilot10", str(tmp_path / "none"),
                           "--json", str(out)], capture_output=True, text=True)  # fmt: skip
    assert done.returncode == 0, done.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "k=1" in data["declared"] and "no inferential" in data["declared"]
    conan = data["chains"][CHAINS[0]]
    n, a = conan["arms"]["N"], conan["arms"]["A"]
    assert n["cost_usd"] == 24.0 and n["resolved"] == 30
    assert n["cost_per_resolved"] == pytest.approx(0.8) and n["f2p"] == 0.5
    assert n["requests"] == 180 and n["peak_context"] == 420_000
    assert n["compactions"] == 1 and n["cuts"] is None
    assert n["cumulative_usd"]["10"] == 24.0
    assert a["cost_usd"] == 18.0 and a["f2p"] == pytest.approx(0.55)
    assert a["cuts"] == 40 and a["r"] == 0.3 and a["r_whole"] == 0.1
    assert conan["ratios"]["A_vs_N"]["cost"] == pytest.approx(0.75)
    assert conan["ratios"]["A_vs_N"]["cost_per_resolved"] == pytest.approx((18 / 33) / 0.8,
                                                                           abs=1e-3)  # fmt: skip
    assert conan["pairs"]["N_vs_A"]["common_ran"] == 0  # these rows name no bug
    pyd = data["chains"][CHAINS[1]]
    assert pyd["arms"]["N"]["resolved"] is None and pyd["arms"]["N"]["cost_per_resolved"] is None
    assert pyd["arms"]["A"]["stopped"] == "rerequest"
    assert pyd["arms"]["A"]["cost_per_resolved"] is None
    assert pyd["ratios"]["A_vs_N"]["cost_per_resolved"] is None and "A10" not in pyd["arms"]
    assert "rerequest" in done.stdout and CHAINS[0] in done.stdout and "k=1" in done.stdout


def test_arms_parse_with_a_drive_colon_in_the_root(lc: Any) -> None:
    assert lc.parse_arms([r"Ne=C:\sp-runs\L-ne:Ne"]) == {
        "Ne": (pathlib.Path(r"C:\sp-runs\L-ne"), "Ne")
    }
