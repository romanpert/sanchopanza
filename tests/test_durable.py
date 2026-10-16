"""Writes that survive the machine going down (`sanchopanza.durable`): the file is fsynced before
it is renamed into place or after a line is appended, with the same bytes as before. The W17
Opus run lost its rows file to an unclean shutdown (zero-filled after `write_text` + `os.replace`
with no fsync), and its ledger's last line with it."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import budget, durable, funds
from sanchopanza.context import episodes

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
handoff = bench_module(ROOT / "benchmarks" / "memory_carry", "handoff")
paid_once = bench_module(ROOT / "benchmarks", "paid_once")
arm_files = bench_module(ROOT / "benchmarks" / "adopt", "arm_files")


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Every fsync (by the file's name when known) and every rename, in order."""
    seen: list[tuple[str, Any]] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd: int) -> None:
        seen.append(("fsync", fd))
        real_fsync(fd)

    def replace(src: Any, dst: Any) -> None:
        seen.append(("replace", Path(dst).name))
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    return seen


def kinds(seen: list[tuple[str, Any]]) -> list[str]:
    return [k for k, _ in seen]


def test_replace_text_syncs_before_the_rename_with_the_same_bytes(
    tmp_path: Path, events: list[tuple[str, Any]]
) -> None:
    text = json.dumps([{"a": 1}, {"b": "ñ"}], indent=1)
    durable.replace_text(tmp_path / "rows.json", text)
    (tmp_path / "plain.json").write_text(text, encoding="utf-8")
    assert kinds(events)[:2] == ["fsync", "replace"]
    assert (tmp_path / "rows.json").read_bytes() == (tmp_path / "plain.json").read_bytes()
    assert not (tmp_path / "rows.json.tmp").exists()


def test_replace_text_keeps_a_given_temp_and_newline(
    tmp_path: Path, events: list[tuple[str, Any]]
) -> None:
    durable.replace_text(tmp_path / "x.txt", "a\nb\n", temp=tmp_path / "x.part", newline="\n")
    assert (tmp_path / "x.txt").read_bytes() == b"a\nb\n"
    assert not (tmp_path / "x.part").exists()


def test_append_text_syncs(tmp_path: Path, events: list[tuple[str, Any]]) -> None:
    durable.append_text(tmp_path / "l.jsonl", "one\n")
    durable.append_text(tmp_path / "l.jsonl", "two\n")
    assert kinds(events) == ["fsync", "fsync"]
    assert (tmp_path / "l.jsonl").read_text(encoding="utf-8").splitlines() == ["one", "two"]


def test_sync_dir_never_raises(tmp_path: Path) -> None:
    durable.sync_dir(tmp_path)
    durable.sync_dir(tmp_path / "missing")


# ---- the writers ----------------------------------------------------------------------------


def test_handoff_rows_are_synced_before_the_rename(
    tmp_path: Path, events: list[tuple[str, Any]]
) -> None:
    rows = [{"scene": "h_batch", "arm": "S", "kept_all": True}]
    handoff.write_rows(tmp_path, rows)
    assert ("replace", "f2.json") in events
    assert kinds(events).index("fsync") < events.index(("replace", "f2.json"))
    assert handoff.rows_of(tmp_path) == rows
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps(rows, indent=1), encoding="utf-8")  # the sealed lots' bytes
    assert (tmp_path / "f2.json").read_bytes() == plain.read_bytes()


def test_handoff_ledger_and_interrupts_are_synced(
    tmp_path: Path, events: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff.book(tmp_path, "arm", 0.25, "t00-a")
    assert kinds(events) == ["fsync"]
    assert handoff.ledger(tmp_path) == 0.25
    monkeypatch.setattr(handoff, "lost_cost", lambda work, rec: 0.5)
    events.clear()
    seen, again = handoff.resume_interrupted(tmp_path, tmp_path / "work" / "t01-b", {})
    assert seen == {"t01-b": 1} and handoff.interrupts(tmp_path) == seen
    assert ("replace", "interrupts.json") in events
    assert kinds(events).count("fsync") >= 2  # the ledger line, then interrupts.json


def test_spend_ledger_lines_are_synced(tmp_path: Path, events: list[tuple[str, Any]]) -> None:
    ledger = budget.SpendLedger(tmp_path / "ledger.jsonl", cap_usd=1.0)
    rid = ledger.reserve(0.1, batch="b")
    assert rid is not None and "fsync" in kinds(events)
    assert ledger.spent() == pytest.approx(0.1)


def test_funds_breaker_is_synced_before_the_rename(
    tmp_path: Path, events: list[tuple[str, Any]]
) -> None:
    assert funds._write(tmp_path / "funds.json", {"status": 402, "count": 1})
    assert kinds(events)[:2] == ["fsync", "replace"]
    assert json.loads((tmp_path / "funds.json").read_text(encoding="utf-8"))["count"] == 1


def test_episodes_are_synced_before_the_rename(
    tmp_path: Path, events: list[tuple[str, Any]]
) -> None:
    episodes.write_private(tmp_path / "e" / "store.json", '{"x": 1}')
    assert kinds(events)[:2] == ["fsync", "replace"]
    assert (tmp_path / "e" / "store.json").read_text(encoding="utf-8") == '{"x": 1}'


def test_paid_once_launch_log_is_synced(tmp_path: Path, events: list[tuple[str, Any]]) -> None:
    lot = paid_once.Lot(name="t", prereg=tmp_path / "prereg.md", launcher=tmp_path / "x.cmd",
                        fixture=tmp_path / "f.jsonl", model="m", cap_usd=1.0, instrument=(),
                        home=tmp_path)  # fmt: skip
    paid_once._note(lot, {"event": "start"})
    assert kinds(events) == ["fsync"]
    assert paid_once.history(lot) == [{"event": "start", "stop_kind": "unfinished"}]


def test_adopt_rows_are_synced_before_the_rename(
    tmp_path: Path, events: list[tuple[str, Any]]
) -> None:
    arm_files.write_row(tmp_path, {"ok": True})
    assert kinds(events)[:2] == ["fsync", "replace"]


# ---- no unsynced temp-and-rename left ------------------------------------------------------

# A temporary file written and renamed into place with no fsync. Left as they are, on purpose:
# caches and per-session hook state that a crash makes moot, and the candor lock, which reads
# an unreadable file as engaged (fails closed).
PLAIN_OK = {"src/sanchopanza/harness/browse_hook.py", "src/sanchopanza/harness/candor_hook.py",
            "src/sanchopanza/harness/passages_state.py", "src/sanchopanza/harness/autopilot.py",
            "src/sanchopanza/candor/lock.py"}  # fmt: skip
UNSYNCED = re.compile(
    r"\.write_text\((?:[^\n]*\n){1,3}?[ \t]*"
    r"(?:os\.replace\(|\w+\.replace\(\w+\)[ \t]*(?:#[^\n]*)?\n)"
)


def test_no_state_writer_renames_an_unsynced_temp_file() -> None:
    found = []
    for folder in ("src/sanchopanza", "benchmarks"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel not in PLAIN_OK and UNSYNCED.search(path.read_text(encoding="utf-8")):
                found.append(rel)
    assert found == []
