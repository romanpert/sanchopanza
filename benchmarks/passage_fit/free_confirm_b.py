"""C5b: C5's design (`free_confirm.py`) on a fresh QASPER train draw, with the fixed runner.

    python -I benchmarks/passage_fit/free_confirm_b.py export PARQUET   # free: QASPER train
    python -I benchmarks/passage_fit/free_confirm_b.py rows             # free: the questions
    python -I benchmarks/passage_fit/free_confirm_b.py dry              # free: calls and cost
    python -I benchmarks/passage_fit/free_confirm_b.py seal             # once, before any answer
    python -I benchmarks/passage_fit/free_confirm_b.py paid --launcher c5b-free-run.cmd  # Jev
    python -I benchmarks/passage_fit/free_confirm_b.py report           # free once recorded

Pre-registered in docs/results/2026-10-16-c5b-free/prereg.md, a delta on C5's sealed prereg.

`free_confirm.py` is loaded here as a private copy (not the module C5's runner or its tests
import), and only that copy's constants are set: the lot (`c5b-free`, its fixture, results,
launcher, batch cap), the split (QASPER train, its parquet and export hashes) and the
questions (a paper-wise draw of 646). C5's file and its sealed values stay as they ran. The
copy's squire has no cap of its own for every action, `report` included (C5's sealed replay
needed 2.00), and the post-data action is C5's alone.
"""

from __future__ import annotations

import importlib.util
import pathlib
import random
import sys
from collections.abc import Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _copy_of_c5() -> Any:
    spec = importlib.util.spec_from_file_location("free_confirm_c5b", HERE / "free_confirm.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["free_confirm_c5b"] = module
    spec.loader.exec_module(module)
    return module


c5 = _copy_of_c5()

NAME = "c5b-free"
RESULTS = ROOT / "docs" / "results" / "2026-10-16-c5b-free"
QASPER = pathlib.Path.home() / ".cache" / "sancho" / "qasper-train.jsonl"
PARQUET_SHA256 = "9af08092ee26c4f700202c1f90d1592b662926f23f3a308a10ff0a53345e37fe"
QASPER_SHA256 = "1f97c5fd3b308e601b82bf00551519ad190597caebc066f44c56cdd160926c74"  # `export`, LF
DRAW_SEED = 20261019
DRAW_SIZE = 646  # C5's number of questions

c5.NAME = NAME
c5.RESULTS = RESULTS
c5.PREREG = RESULTS / "prereg.md"
c5.QASPER = QASPER
c5.PARQUET_SHA256 = PARQUET_SHA256
c5.QASPER_SHA256 = QASPER_SHA256
c5.FIXTURE = ROOT / "fixtures" / NAME / "recording.jsonl"
c5.CAP_USD = c5.w17_round.BATCH_CAPS[NAME]  # 2.00 on the round's shared ledger
c5.SEALED_SQUIRE_CAP_USD = c5.SQUIRE_CAP_USD  # no cap of the squire's own, in every action
C5_BUILD_ROWS = c5.build_rows  # C5's builder, before the draw replaces it in the copy


def lot() -> Any:
    return c5.paid_once.Lot(
        name=NAME,
        prereg=c5.PREREG,
        launcher=ROOT / "c5b-free-run.cmd",  # fixed by the seal, not an instrument path
        fixture=c5.FIXTURE,
        model=c5.MODEL,
        cap_usd=c5.CAP_USD,
        instrument=c5.INSTRUMENT,
        inputs=((QASPER, QASPER_SHA256),),
        home=c5.HOME,
        shared_ledger=c5.w17_round.LEDGER,
        shared_cap_usd=c5.w17_round.CAP_USD,
    )


def draw(rows: Sequence[dict[str, Any]], *, seed: int, size: int) -> list[dict[str, Any]]:
    """Papers in an order shuffled with `seed`, every row of each, until there are `size` rows
    or more; rows keep the order they came in."""
    papers = sorted({r["paper"] for r in rows})
    random.Random(seed).shuffle(papers)
    taken: set[str] = set()
    count = 0
    for paper in papers:
        if count >= size:
            break
        taken.add(paper)
        count += sum(r["paper"] == paper for r in rows)
    return [r for r in rows if r["paper"] in taken]


def load_rows() -> list[dict[str, Any]]:
    if c5.paid_once.raw_digest(QASPER) != QASPER_SHA256:
        raise SystemExit(f"{QASPER} is not the registered export: run `export` first")
    return build_rows(QASPER)[0]


def build_rows(path: pathlib.Path = QASPER) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """C5's builder on the train export, then the draw; the counts say what each step left."""
    built, counts = C5_BUILD_ROWS(path)
    rows = draw(built, seed=DRAW_SEED, size=DRAW_SIZE)
    return rows, {**counts, "built": counts["rows"], "rows": len(rows),
                  "papers_drawn": len({r["paper"] for r in rows})}  # fmt: skip


c5.lot = lot
c5.load_rows = load_rows
c5.build_rows = build_rows


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "postdata":
        raise SystemExit("postdata is C5's post-data reading; C5b has none")
    sys.argv = [sys.argv[0], *args]
    return c5.main()


if __name__ == "__main__":
    raise SystemExit(main())
