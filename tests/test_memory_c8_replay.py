"""benchmarks/memory_c8: the free C8 figures. SWE-chat's counter and the owner's-rules counter
on synthetic files (counts only, no text out), and the summary's arithmetic on made-up arms."""

from __future__ import annotations

import json
from pathlib import Path

from .helpers import bench_module

BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "memory_c8"
swechat = bench_module(BENCH, "swechat")
own_rules = bench_module(BENCH, "own_rules")
replay = bench_module(BENCH, "replay_c8")


def record(session: str, at: float) -> dict:
    return {"session": session, "index": 1, "request": "Step 2, in the next session: export.",
            "report": "done", "changed": ["app/export.py"], "at": at}  # fmt: skip


def test_swechat_counts_cues_and_long_prompts_and_writes_no_text(tmp_path: Path) -> None:
    items = [
        {"prompt": "continue", "pool": [record("a", 1.0)], "labels": {"a-001": "file"}},
        {"prompt": "Howdy, where did we leave it? where we left off?", "pool": [record("b", 2.0)],
         "labels": {"b-001": "none"}},
        {"prompt": "Resume parsing fails on PDF uploads", "pool": [record("c", 3.0)],
         "labels": {}},
        {"prompt": "x " * 700, "pool": [], "labels": {}},
    ]  # fmt: skip
    path = tmp_path / "items.jsonl"
    path.write_text("\n".join(json.dumps(i) for i in items) + "\n", encoding="utf-8")
    out = swechat.run(path)
    assert out["items"] == 4 and out["long"] == 1 and out["cue"] == 2
    assert out["cue_opening"] == 1 and out["cue_left_off"] == 1
    assert out["cue_given_file"] == 1 and out["cue_given_none"] == 1
    assert "continue" not in json.dumps(out) and "Howdy" not in json.dumps(out)


def test_own_rules_gives_counts_only(tmp_path: Path) -> None:
    rules = [{"text": "Never push to main."}, {"text": "For step 2, cap the discount at 20 %."}]
    data = {"projects": [{"folder": "secret-project", "rules": rules}]}
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert own_rules.run(path) == {"rules": 2, "plan_shaped": 1}


def test_a_part_without_its_input_is_not_run_and_the_brief_drops_per_arm_rows(
    tmp_path: Path, monkeypatch
) -> None:
    for name in ("SANCHOPANZA_F2_ROOT", "SANCHOPANZA_C8_ITEMS", "SANCHOPANZA_C8_OWN_RULES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(replay.swechat, "ITEMS", tmp_path / "missing.jsonl")
    out = tmp_path / "out.json"
    assert replay.main(["--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["live_calls"] == 0 and result["f2"].startswith("not run")
    full = {"f2": {"runs": {"r": {"summary": {"arms": 1}, "arms": [{"scene": "s"}]}}}}
    assert replay.brief(full) == {"f2": {"runs": {"r": {"arms": 1}}}}
