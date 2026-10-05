"""The offline replay of the sources trigger variants (v2 / v2.1, cap share) on both FRAMES pilots.
No model, no network, no money: only the pure helpers are run here."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


variants = _load("browse_free_frames_variants", "benchmarks/browse/free_frames_variants.py")


def _s(right: bool, usd: float, signs=("number",), stopped=True, web=3, listed=False) -> dict:
    return {"right": right, "estimated_usd": usd, "cap_usd": 1.0, "signs_v2": list(signs),
            "signs_v21": [], "stopped": stopped, "web_calls": web, "list": listed,
            "task": "FR1"}  # fmt: skip


def test_list_answer_needs_three_items():
    assert variants.list_answer("breast cancer, melanoma, and ovarian cancer")
    assert not variants.list_answer("breast cancer and melanoma")
    assert not variants.list_answer("Barcelona")


def test_a_session_at_its_cap_or_past_the_src_cap_never_stops():
    capped = {"arm": "HAIKU-SRC2", "subtype": "error_max_budget_usd", "hook_fired": False,
              "list_usd": 0.43}  # fmt: skip
    assert not variants.reached_stop(capped, 0.42)
    assert variants.reached_stop({**capped, "hook_fired": True}, 0.42)
    base = {"arm": "HAIKU", "subtype": "success", "hook_fired": False, "list_usd": 0.5}
    assert not variants.reached_stop(base, 0.42)
    assert variants.reached_stop({**base, "list_usd": 0.3}, 0.42)


def test_fires_needs_a_stop_web_a_sign_and_room_under_the_share():
    assert variants.fires(_s(False, 0.5), "signs_v2", 0.6)
    assert not variants.fires(_s(False, 0.7), "signs_v2", 0.6)
    assert variants.fires(_s(False, 0.7), "signs_v2", 0.8)
    assert variants.fires(_s(False, 0.99), "signs_v2", None)
    assert not variants.fires(_s(False, 0.5, stopped=False), "signs_v2", None)
    assert not variants.fires(_s(False, 0.5, web=0), "signs_v2", None)
    assert not variants.fires(_s(False, 0.5), "signs_v21", None)
    assert variants.fires(_s(False, 0.5, signs=(), listed=True), "signs_v2", 0.6, True)


def test_cell_bounds_the_gain_at_the_fix_rate_and_prices_each_block():
    sessions = [_s(False, 0.1), _s(False, 0.1), _s(True, 0.1), _s(True, 0.1, signs=())]
    out = variants.cell(sessions, ("signs_v2", 0.6, False), block_usd=0.1)
    assert (out["fires_right"], out["fires_wrong"]) == (1, 2)
    assert out["bound_right_per_100"] == round(100 * 0.4 * 2 / 4, 2)
    assert out["extra_usd_per_session"] == round(3 * 0.1 / 4, 4)
    assert out["usd_per_right_answer"] == round(0.3 / 0.8, 3)


def test_misses_say_why_a_wrong_session_was_not_asked():
    sessions = [_s(False, 0.9), _s(False, 0.1, signs=()), _s(False, 0.1, stopped=False),
                _s(False, 0.1, web=0), _s(True, 0.9)]  # fmt: skip
    assert variants.misses(sessions, ("signs_v2", 0.6, False)) == {
        "no_web": 1, "no_stop": 1, "past_share": 1, "no_sign": 1}  # fmt: skip
