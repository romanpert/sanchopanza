"""F1's family iii (`benchmarks/memory_carry/scenes_parallel.py`), checked before any session sees
it: the checks still tell keeping the fact from breaking it once session 1a's module is there, a
session 2 that does nothing keeps nothing, and neither new prompt gives the fact away."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from .helpers import bench_module
from .test_memory_carry_cross import RESULTS, TELLS

ROOT = Path(__file__).resolve().parents[1]
mod = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes_parallel")
PARALLEL, PARALLEL_RULES = mod.PARALLEL, mod.PARALLEL_RULES
CROSS = bench_module(ROOT / "benchmarks" / "memory_carry", "scenes_cross").CROSS

# Per cross scene: what session 1a leaves, by hand (the module session 2 goes on with).
THREADS: dict[str, str] = {
    "x_tz": "def describe(entry):\n    return f\"{entry['user']}: {entry['action']}\"\n",
    "x_cents": "def parcel_class(weight_kg):\n    if weight_kg <= 0:\n"
    "        raise ValueError(weight_kg)\n    return 'small' if weight_kg <= 2 else 'large'\n",
    "x_print": "def valid_rows(rows):\n"
    "    return [r for r in rows if isinstance(r.get('amount'), (int, float))]\n",
    "x_camel": "def check_user(user):\n    if 'id' not in user or not user.get('display_name'):\n"
    "        raise ValueError('bad user')\n",
    "x_zeros": "def invoice_total(lines):\n    if any(l['qty'] < 0 for l in lines):\n"
    "        raise ValueError('negative qty')\n"
    "    return sum(l['price'] * l['qty'] for l in lines)\n",
    "x_stdlib": "def merged(defaults, overrides):\n    return {**defaults, **overrides}\n",
    "x_prefix": "from email.message import EmailMessage\n\n\n"
    "def build_message(to, subject, body):\n    if '@' not in to:\n        raise ValueError(to)\n"
    "    msg = EmailMessage()\n    msg['To'], msg['Subject'] = to, subject\n"
    "    msg.set_content(body)\n    return msg\n",
    "x_trash": "import os, time\n\n\ndef old_files(folder, days):\n"
    "    cut = time.time() - days * 86400\n"
    "    return [n for n in os.listdir(folder)\n"
    "            if os.path.isfile(os.path.join(folder, n))"
    " and os.path.getmtime(os.path.join(folder, n)) < cut]\n",
}


def build(root: Path, scene: dict) -> Path:
    for rel, text in scene["files"].items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def passes(root: Path, code: str) -> bool:
    done = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, timeout=60)
    return done.returncode == 0


def test_eight_scenes_four_in_a_worktree_each_on_its_cross_scene() -> None:
    assert sorted(PARALLEL) == sorted(f"q_{c[2:]}" for c in CROSS)
    assert sum(bool(s["worktree"]) for s in PARALLEL.values()) == 4
    assert set(THREADS) == {s["cross"] for s in PARALLEL.values()}
    for name, scene in PARALLEL.items():
        cross = CROSS[scene["cross"]]
        assert scene["files"] == cross["files"] and scene["first"] == cross["first"]
        assert scene["task"] == cross["task"] and scene["fact"].endswith(cross["fact"])
        assert scene["fact"] == cross["fact"] or name == "q_stdlib"  # its fact needs the function
        assert PARALLEL_RULES[name] in scene["first"]
        assert scene["thread"] and scene["second"] != cross["second"]


def test_the_variants_split_the_scenes_that_broke_on_sonnet_evenly() -> None:
    # v7-cross, N on Sonnet: x_tz, x_cents, x_stdlib and x_trash broke at least once
    broke = {"x_tz", "x_cents", "x_stdlib", "x_trash"}
    for tree in (False, True):
        crosses = {s["cross"] for s in PARALLEL.values() if bool(s["worktree"]) is tree}
        assert len(crosses & broke) == 2


@pytest.mark.parametrize("name", sorted(PARALLEL))
def test_the_checks_tell_keeping_from_breaking_after_the_thread(name: str, tmp_path: Path) -> None:
    scene = PARALLEL[name]
    rel, good, bad = RESULTS[scene["cross"]]
    thread = THREADS[scene["cross"]]
    for label, text, fact in (("good", good, True), ("bad", bad, False)):
        root = build(tmp_path / label, scene)
        (root / rel).write_text(thread + "\n\n" + text, encoding="utf-8")
        if scene["cross"] == "x_stdlib" and label == "bad":
            assert not passes(root, scene["fact"])  # PyYAML need not be installed here
            continue
        assert passes(root, scene["task"]), (label, "task")
        assert passes(root, scene["fact"]) is fact, (label, "fact")


@pytest.mark.parametrize("name", sorted(PARALLEL))
def test_a_session_2_that_does_nothing_keeps_nothing(name: str, tmp_path: Path) -> None:
    scene = PARALLEL[name]
    rel = RESULTS[scene["cross"]][0]
    start = build(tmp_path / "start", scene)
    assert not passes(start, scene["task"])
    after = build(tmp_path / "thread", scene)
    (after / rel).write_text(THREADS[scene["cross"]], encoding="utf-8")
    assert not passes(after, scene["task"]), "session 2 would have nothing left to do"
    assert not passes(after, scene["fact"]), "the fact would be kept by default"


@pytest.mark.parametrize("name", sorted(PARALLEL))
def test_no_new_prompt_gives_the_fact_away_or_names_session_1b(name: str) -> None:
    scene = PARALLEL[name]
    rel = RESULTS[scene["cross"]][0]
    for key in ("thread", "second"):
        text = scene[key].lower()
        assert not [w for w in TELLS[scene["cross"]] if w.lower() in text], key
        earlier = [f for f in scene["files"] if f.startswith("app/") and f != "app/__init__.py"]
        assert not [f for f in earlier if f in scene[key]], key
        assert rel in scene[key], f"{key} must name the module the line of work builds"
    assert scene["second"].startswith("Go on with") and "from earlier" in scene["second"]
    assert "later session" in scene["thread"]
