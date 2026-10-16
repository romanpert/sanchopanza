"""D1's runner, free: the registered queries, the verdict rule, the pairing and the refusals
before any key is read. No network."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "openai_decisions"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import paid_once  # noqa: E402
import run  # noqa: E402


def test_the_benches_ask_the_registered_queries() -> None:
    assert len(run.queries()) == run.QUERIES == 301


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [
        (0.001, 0.05, "mejor"),
        (-0.049, 0.02, "no peor"),
        (-0.05, 0.02, "no concluyente"),
        (-0.09, -0.051, "peor"),
        (-0.09, -0.05, "no concluyente"),
    ],
)
def test_the_verdict_rule_is_the_sealed_one(lo, hi, expected) -> None:
    assert run.verdict(lo, hi) == expected


def test_paired_counts_and_a_deterministic_interval() -> None:
    a = [True] * 80 + [False] * 20
    b = [True] * 75 + [False] * 5 + [True] * 10 + [False] * 10
    one, two = run.paired(a, b), run.paired(a, b)
    assert one == two
    assert (one["only_a"], one["only_b"]) == (5, 10)
    assert one["difference"] == pytest.approx(-0.05)
    assert one["ci95"][0] < one["difference"] < one["ci95"][1]


def test_the_lot_counts_a_served_snapshot_as_its_model() -> None:
    assert run.LOT.serves("gpt-6-luna") and run.LOT.serves("gpt-6-luna-2026-10-06")
    assert not run.LOT.serves("gpt-6-luna2") and not run.LOT.serves("jev-1.13.0")
    assert run.LOT.price_per_mtok == 0.10 and run.LOT.cap_usd == 0.10


def test_paid_refuses_without_the_seal_before_reading_the_key(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    lot = paid_once.Lot(
        name="d1-test",
        prereg=tmp_path / "prereg.md",
        launcher=tmp_path / "run.cmd",
        fixture=tmp_path / "fixture.jsonl",
        model="gpt-6-luna",
        cap_usd=0.10,
        instrument=(),
        home=tmp_path,
        price_per_mtok=0.10,
        model_prefix=True,
    )
    (tmp_path / "prereg.md").write_text("x", encoding="utf-8")
    (tmp_path / "run.cmd").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        paid_once.run_paid(
            lot,
            run.queries()[:3],
            load_key=lambda: calls.append("key"),
            make_live=lambda: calls.append("live"),
            check=lambda model: calls.append("check"),
        )
    assert calls == []


def test_the_launcher_refuses_its_placeholders() -> None:
    text = (ROOT / "openai-decisions-run.cmd").read_text(encoding="utf-8")
    assert 'set "PY=<PYTHON>"' in text and 'set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"' in text
    assert "openai_decisions\\run.py paid" in text
