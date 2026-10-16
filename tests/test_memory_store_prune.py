"""The 30-day retention of a project's memory store removes old records only: the standing rules
(`rules.json`), the index and any other file the store keeps beside the records stay. No network."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from sanchopanza.context import episodes as ep
from sanchopanza.harness import memory_rules as mr
from sanchopanza.harness import memory_store as ms

OLD = 1_000_000.0  # 1970: far older than any retention


def _episode(session: str, index: int) -> ep.Episode:
    return ep.Episode(session=session, index=index, request=f"request {index}",
                      report="done", at=time.time())  # fmt: skip


def _old_file(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    os.utime(path, (OLD, OLD))
    return path


def test_old_standing_rules_survive_a_save_that_prunes(tmp_path: Path) -> None:
    rules = {"rules": [{"text": "Never push to main.", "at": OLD}], "asked": [], mr.AUDITED: []}
    _old_file(tmp_path / mr.RULES, json.dumps(rules))
    ep.save(tmp_path, [_episode("s", 1)])
    assert (tmp_path / mr.RULES).exists()
    assert mr.load(tmp_path)["rules"][0]["text"] == "Never push to main."


def test_old_records_are_pruned_and_recent_ones_kept(tmp_path: Path) -> None:
    old = _old_file(tmp_path / "a1b2c3d4-0000-4000-8000-000000000001-001.json", "{}")
    old_long = _old_file(tmp_path / "s-1000.json", "{}")  # a session past 999 requests
    recent = tmp_path / "r-001.json"
    recent.write_text(json.dumps(_episode("r", 1).to_dict()), encoding="utf-8")
    ep.prune(tmp_path, time.time() - ep.KEEP_DAYS * 86_400)
    assert not old.exists() and not old_long.exists()
    assert recent.exists()


def test_files_that_are_not_records_are_kept_however_old(tmp_path: Path) -> None:
    kept = [
        _old_file(tmp_path / mr.RULES, "{}"),
        _old_file(tmp_path / ep.INDEX, "{}"),
        _old_file(tmp_path / ms.ADOPTED, "{}"),
        _old_file(tmp_path / "notes.json", "{}"),
        _old_file(tmp_path / "s-01.json", "{}"),  # not three digits: not a name `save` writes
        _old_file(tmp_path / "s-abc.json", "{}"),
    ]
    ep.prune(tmp_path, time.time())
    assert [p.name for p in kept if not p.exists()] == []


def test_the_rules_file_does_not_take_a_records_place_in_load(tmp_path: Path) -> None:
    ep.save(tmp_path, [_episode("s", 1), _episode("s", 2)], keep_days=0)
    (tmp_path / mr.RULES).write_text(json.dumps({"rules": []}), encoding="utf-8")
    (tmp_path / ms.ADOPTED).write_text("{}", encoding="utf-8")
    assert [e.key for e in ep.load(tmp_path, limit=2)] == ["s-001", "s-002"]
