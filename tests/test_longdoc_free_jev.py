"""Lot longdoc-free's phase J (benchmarks/longdoc_free/jev_phase.py): passages then the gate per
question through B6's asker, the dry stub, the replay and the refusals before any spend. No
network, no key."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


jp = _load("lf_jev_phase", "benchmarks/longdoc_free/jev_phase.py")
br = jp.br
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402


def _benchmarks_off_the_path() -> None:
    """jev_phase puts benchmarks/ on sys.path, where `agentdojo/` imports as a namespace package
    and breaks the agentdojo skip of later tests (memory: trampas-tests-sys-path)."""
    for entry in (str(ROOT / "benchmarks"), str(ROOT / "benchmarks" / "b6_es")):
        while entry in sys.path:
            sys.path.remove(entry)


_benchmarks_off_the_path()


@pytest.fixture(autouse=True)
def _benchmarks_on_the_path_while_testing(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks"))
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks" / "b6_es"))


def _rows(n: int = 3) -> list[dict]:
    text = "\n\n".join(
        f"Chapter {i}. Emma walked to Highbury with Harriet in May." for i in range(80)
    )
    novel = jp.pages.pages_of(text)
    return [{"id": i, "novel": "n0", "question": "Where did Emma walk with Harriet?",
             "answers": ["Highbury"], "pages": novel} for i in range(n)]  # fmt: skip


def _stub_asker() -> br.Asker:
    return br.Asker(br.Stub(), recorded=RecordedDecider([]), memo_failures=True, model_halts=True)


def test_each_question_gets_its_passages_then_one_gate_call():
    asker = _stub_asker()
    got = asyncio.run(jp.ask(_rows(), asker))
    assert [g["id"] for g in got] == [0, 1, 2]
    assert all(g["p"] == pytest.approx(0.5) for g in got)  # the stub's gate answer
    assert all(g["kept"] != jp.pages.EMPTY and len(g["kept"]) <= jp.FIT_CHARS + 2000 for g in got)
    assert asker.calls["gate"]["calls"] == 1  # the same question and passages: asked once
    assert asker.calls["select"]["calls"] > 0


def test_a_question_without_a_recording_or_live_decider_is_not_complete():
    asker = br.Asker(None, recorded=RecordedDecider([]), memo_failures=True, model_halts=True)
    got = asyncio.run(jp.ask(_rows(1), asker))
    assert got[0]["p"] is None and asker.failed_keys


def test_the_gold_check_uses_infbench_normalisation():
    assert jp.gold_in("They walked to Highbury, in May.", ['"Highbury"'])
    assert not jp.gold_in("They walked to Hartfield.", ["Highbury"])
    assert not jp.gold_in("anything", ["the"])  # a reference that normalises to nothing


def test_the_gate_is_one_truth_over_question_and_passages():
    text = jp.GATE.instructions
    assert "`passages`" in text and "`question`" in text
    assert jp.POINT == "longdoc_free_gate"


def test_the_phases_are_separate_lots_under_the_owners_jev_cap():
    dev, confirm = jp.lot("dev"), jp.lot("confirm")
    assert dev.name == "longdoc-free-dev" and confirm.name == "longdoc-free"
    assert dev.fixture != confirm.fixture and dev.run_dir != confirm.run_dir
    assert dev.prereg.name == "prereg-dev.md" and confirm.prereg.name == "prereg.md"
    assert dev.cap_usd + confirm.cap_usd <= 14.00  # the owner's, raised on 2026-10-17
    assert "docs/results/2026-10-16-longdoc-free/ids.json" in dev.instrument
    assert dev.model == confirm.model == "jev-1.13.0"


def test_a_paid_run_without_the_launcher_spends_nothing(tmp_path: Path):
    with pytest.raises(SystemExit, match="launcher"):
        jp.paid("dev", None, load_key=lambda: pytest.fail("the key was read"))
    with pytest.raises(SystemExit, match="launcher"):
        jp.paid("dev", tmp_path / "other.cmd", load_key=lambda: pytest.fail("the key was read"))


def test_the_dry_run_counts_calls_and_compares_with_the_cap(monkeypatch):
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: _stub_asker())
    got = jp.dry("dev", _rows())
    assert got["questions"] == 3 and got["claude_usd"] == 0.0
    assert got["calls"]["gate"]["calls"] == 1
    assert got["fits_under_cap"] == (got["pessimistic_usd"] <= jp.CAP_USD["dev"])


def test_the_replay_refuses_an_incomplete_recording(monkeypatch):
    monkeypatch.setattr(jp, "load_rows", lambda phase: _rows(1))
    no_live = br.Asker(None, recorded=RecordedDecider([]), memo_failures=True, model_halts=True)
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: no_live)
    with pytest.raises(SystemExit, match="not recorded"):
        jp.replay("dev")


def test_the_replay_writes_the_kept_text_privately_and_public_rows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(jp, "load_rows", lambda phase: _rows(2))
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: _stub_asker())
    monkeypatch.setattr(jp, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(jp, "RESULTS", tmp_path / "results")
    (tmp_path / "results").mkdir()
    out = jp.replay("dev")
    assert {r["id"] for r in out} == {0, 1}
    assert set(out[0]) == {"id", "novel", "p", "kept_chars", "empty", "gold_in_kept"}
    assert out[0]["gold_in_kept"] is True
    kept = (tmp_path / "private" / "dev" / "passages" / "0.txt").read_text("utf-8")
    assert "Highbury" in kept and len(kept) == out[0]["kept_chars"]
    public = (tmp_path / "results" / "jev-dev.jsonl").read_text("utf-8")
    assert "Highbury" not in public and json.loads(public.splitlines()[0])["id"] == 0


def test_a_paid_run_off_the_seal_commit_spends_nothing(monkeypatch, tmp_path: Path):
    launcher = jp.lot("dev").launcher
    monkeypatch.setattr(jp, "load_rows", lambda phase: _rows(1))
    monkeypatch.setattr(jp, "lot_asker", lambda phase, fallback: _stub_asker())
    monkeypatch.setattr(jp.paid_once, "room", lambda lot: 99.0)
    monkeypatch.setattr(jp.paid_once, "require_sealed", lambda lot: None)
    monkeypatch.setattr(jp.paid_once, "require_instrument", lambda lot: "c" * 40)
    monkeypatch.setattr(jp.paid_once, "require_inputs", lambda lot: None)
    with pytest.raises(SystemExit, match="not the commit that sealed"):
        jp.paid("dev", launcher, load_key=lambda: pytest.fail("the key was read"),
                sealed_head=lambda lot: ["HEAD is not the commit that sealed it"])  # fmt: skip
