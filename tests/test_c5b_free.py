"""C5b's runner (benchmarks/passage_fit/free_confirm_b.py): C5's design on a QASPER train draw,
with its own lot and C5's sealed values untouched. No network, no paid call; the draw on the
real export is checked only where the export is present."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fb = _load("free_confirm_b", ROOT / "benchmarks/passage_fit/free_confirm_b.py")


def _rows(papers: dict[str, int]) -> list[dict[str, Any]]:
    return [{"id": f"{p}#{k}", "paper": p} for p, n in papers.items() for k in range(n)]


def test_the_draw_takes_whole_papers_in_seeded_order_until_the_size() -> None:
    rows = _rows({f"p{k}": 1 + k % 4 for k in range(40)})
    got = fb.draw(rows, seed=fb.DRAW_SEED, size=30)
    papers = {r["paper"] for r in got}
    assert len(got) >= 30 and all(sum(r["paper"] == p for r in rows) ==
                                  sum(r["paper"] == p for r in got) for p in papers)  # fmt: skip
    smaller = fb.draw(rows, seed=fb.DRAW_SEED, size=29)
    assert {r["paper"] for r in smaller} <= papers  # a prefix of the same paper order
    assert fb.draw(rows, seed=fb.DRAW_SEED, size=30) == got  # deterministic


def test_the_lot_is_c5bs_and_c5s_sealed_values_are_untouched() -> None:
    lot = fb.lot()
    assert lot.name == "c5b-free" and lot.cap_usd == 2.0
    assert lot.launcher.name == "c5b-free-run.cmd"
    assert lot.fixture == ROOT / "fixtures" / "c5b-free" / "recording.jsonl"
    assert lot.inputs == ((fb.QASPER, fb.QASPER_SHA256),) and "train" in fb.QASPER.name
    assert lot.ledger == fb.c5.w17_round.LEDGER
    c5 = _load("free_confirm_fresh", ROOT / "benchmarks/passage_fit/free_confirm.py")
    assert c5.NAME == "c5-free" and c5.lot().launcher.name == "c5-free-run.cmd"
    assert c5.SEALED_SQUIRE_CAP_USD == 2.0  # C5's sealed replay stays as it ran


def test_c5bs_report_gives_its_squire_no_cap_and_there_is_no_post_data_action() -> None:
    assert fb.c5.SEALED_SQUIRE_CAP_USD == fb.c5.SQUIRE_CAP_USD == 1e9
    with pytest.raises(SystemExit, match="postdata"):
        fb.main(["postdata"])


def test_a_paid_run_refuses_before_the_key_without_its_launcher() -> None:
    def trap(*_: Any, **__: Any) -> Any:
        raise AssertionError("the key was read")

    with pytest.raises(SystemExit, match="run.cmd"):
        fb.c5.paid(None, load_key=trap, check=trap, build_live=trap)


def test_the_draw_on_the_pinned_export() -> None:
    if not fb.QASPER.exists():
        pytest.skip("the QASPER train export is not here (free_confirm_b.py export)")
    rows = fb.c5.load_rows()
    assert len(rows) == 646 and len({r["paper"] for r in rows}) == 300
    validation = Path.home() / ".cache" / "sancho" / "qasper-validation.jsonl"  # C5's export
    if validation.exists():
        assert not set(fb.c5.papers_of(validation)) & {r["paper"] for r in rows}
