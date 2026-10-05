"""The second FRAMES pilot's runner: harder tasks chosen by metadata alone, disjoint from the
first pilot; the v2 arms get the hook with its version and cap. No model, no network, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


frames2 = _load("browse_free_frames2", "benchmarks/browse/free_frames2.py")
frames = frames2.frames


def _row(i: int, types: str, answer: str = "Paris", links: int = 3) -> dict[str, str]:
    row = {"": str(i), "Prompt": f"q{i}", "Answer": answer, "reasoning_types": types}
    for k in range(1, 12):
        row[f"wikipedia_link_{k}"] = f"https://en.wikipedia.org/wiki/P{k}" if k <= links else ""
    return row


THREE = "Numerical reasoning | Multiple constraints | Temporal reasoning"


def test_harder_by_metadata_only():
    assert frames2.eligible(_row(1, THREE, links=2))
    assert frames2.eligible(_row(1, "Multiple constraints", links=4))
    assert not frames2.eligible(_row(1, "Numerical reasoning | Multiple constraints", links=3))
    assert not frames2.eligible(_row(1, THREE, answer="one two three four five"))
    assert frames2.eligible(_row(1, THREE, answer="one two three four"))


def test_sample_is_seeded_disjoint_and_eligible():
    bank = [_row(i, THREE) for i in range(60)] + [_row(100 + i, "Tabular reasoning", links=5)
                                                  for i in range(10)]  # fmt: skip
    bank += [_row(200, "Multiple constraints")]
    taken = {f"FR{i}" for i in range(0, 60, 2)}
    first = frames2.sample(bank, taken, 20, seed=3)
    assert first == frames2.sample(bank, taken, 20, seed=3)
    assert first != frames2.sample(bank, taken, 20, seed=4)
    assert len(set(first)) == 20 and not set(first) & taken
    by_id = {frames.tid_of(r): r for r in bank}
    assert all(frames2.eligible(by_id[t]) for t in first)


def test_the_ids_in_the_repo_are_twenty_new_tasks_if_the_set_is_cached():
    ids = frames2.IDS.read_text(encoding="utf-8").split()
    first = set(frames.IDS.read_text(encoding="utf-8").split())
    assert len(ids) == len(set(ids)) == 20 and not set(ids) & first
    if not frames.FRAMES.exists():
        pytest.skip("FRAMES is not cached here")
    assert ids == frames2.sample(frames.read_frames(), first)


def test_arms_caps_and_ceiling():
    assert frames2.CAPS == {"SONNET": 1.50, "SONNET-SRC2": 1.05, "HAIKU": 0.60,
                            "HAIKU-SRC2": 0.42}  # fmt: skip
    assert frames2.CEILING_USD == 32.0
    assert frames2.PRIVATE != frames.PRIVATE


def test_only_v2_arms_get_the_hook_with_version_and_cap(tmp_path: pathlib.Path):
    assert frames2.env_for("SONNET", tmp_path) == {"SANCHOPANZA_SOURCES_DIR": str(tmp_path)}
    env = frames2.env_for("HAIKU-SRC2", tmp_path)
    assert env["SANCHOPANZA_SOURCES_VERSION"] == "2"
    assert env["SANCHOPANZA_SOURCES_CAP_USD"] == "0.42"
    assert frames.hooks_for("SONNET") is None
    assert list(frames.hooks_for("SONNET-SRC2")) == ["Stop"]


def test_the_v2_hook_as_a_session_runs_it_blocks_a_weak_answer_once():
    outs = frames2.hook_v2_checks()
    assert json.loads(outs["weak"][0])["decision"] == "block" and outs["weak"][1] == ""
    assert outs["clean"] == ["", ""]


def test_what_the_hook_saw_is_read_from_its_folder(tmp_path: pathlib.Path):
    (tmp_path / "checked-x.json").write_text(json.dumps({"signs": ["doubt"], "over_cap": False}))
    assert frames2.hook_seen(tmp_path) == {"signs": ["doubt"], "over_cap": False}
    assert frames2.hook_seen(tmp_path / "missing") is None


# --- the offline replay of the v2 trigger on the first pilot -----------------------------------

trigger = _load("browse_free_frames_trigger", "benchmarks/browse/free_frames_trigger.py")


def test_replay_cuts_main_and_subagents_at_the_first_block(tmp_path: pathlib.Path):
    src, out = tmp_path / "src", tmp_path / "out"
    (src / "sid" / "subagents").mkdir(parents=True)
    out.mkdir()
    main = [{"type": "assistant", "timestamp": "t1", "n": 1},
            {"type": "user", "timestamp": "t3", "text": frames.REQUEST},
            {"type": "assistant", "timestamp": "t4", "n": 2}]  # fmt: skip
    sub = [{"type": "assistant", "timestamp": "t2"}, {"type": "assistant", "timestamp": "t5"}]
    (src / "sid.jsonl").write_text("\n".join(json.dumps(e) for e in main), encoding="utf-8")
    (src / "sid" / "subagents" / "agent-a.jsonl").write_text(
        "\n".join(json.dumps(e) for e in sub), encoding="utf-8"
    )
    cut = trigger.at_first_stop(src, out, (frames.REQUEST[:48],))
    assert [json.loads(x)["n"] for x in cut.read_text(encoding="utf-8").splitlines()] == [1]
    kept = (out / "sid" / "subagents" / "agent-a.jsonl").read_text(encoding="utf-8").split("\n")
    assert [json.loads(x)["timestamp"] for x in kept if x] == ["t2"]


def test_replay_table_counts_fires_against_the_grade():
    rows = [{"right": True, "fires": True}, {"right": False, "fires": True},
            {"right": False, "fires": False}, {"right": True, "fires": False}]  # fmt: skip
    assert trigger.table(rows) == {"fires_right": 1, "fires_wrong": 1, "silent_right": 1,
                                   "silent_wrong": 1}  # fmt: skip
