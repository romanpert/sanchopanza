"""C6's runner and rule (benchmarks/b6_es/c6_window.py, c6_stats.py): which questions are
asked, that the window arm reuses the head arm's equal requests, the verdict, and that a paid
run refuses before the key. No network, no data directory, no paid call."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import truth
from sanchopanza.contract import Decision

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks/b6_es" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


c6 = _load("c6_window")
import b6_build as bb  # noqa: E402  (on the path once the runner is loaded)
import b6_run as br  # noqa: E402
import c6_stats as cs  # noqa: E402

FILLER = "Esta frase de relleno habla de otra cosa distinta. "
GOLD = "El castillo fue construido en 1205 por el rey."


def _side(question: str, long_gold: bool) -> dict[str, Any]:
    gold_paragraph = (FILLER * (30 if long_gold else 1) + GOLD + " " + FILLER).strip()
    pages = [["", (FILLER * 2).strip()], ["", gold_paragraph], ["", "Otra frase corta."]]
    gold_s = []
    for k, (_, text) in enumerate(pages):
        ranges = bb.sentence_ranges(text)
        gold_s.append([k == 1 and text[a:b] == GOLD for a, b in ranges])
    return {"question": question, "answer": "1205", "title": "Castillo", "pages": pages,
            "gold_paragraph": 1, "gold_s": gold_s}  # fmt: skip


def _row(qid: str, long_gold: bool = True) -> dict[str, Any]:
    return {
        "id": qid,
        "es": _side("¿Cuándo fue construido el castillo?", long_gold),
        "en": _side("When was the castle built?", long_gold),  # Spanish text: no English match
    }


def test_a_question_is_asked_only_where_the_window_changes_a_paragraph() -> None:
    long_row, short_row = _row("a"), _row("b", long_gold=False)
    assert c6.changed(long_row, "es") and not c6.changed(short_row, "es")
    assert not c6.changed(long_row, "en")  # no shared word: the head stays
    assert c6.in_view(long_row, "es") == (False, True)
    assert c6.in_view(short_row, "es") == (True, True)


class _Counting:
    name = "counting"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.calls.append(point)
        return Decision(point, {k: truth(0.9) for k in qs}, "counting", c6.MODEL)


def test_the_window_arm_reuses_every_equal_request_and_unchanged_questions_cost_nothing() -> None:
    live = _Counting()
    asker = br.Asker(live)
    out = asyncio.run(c6.ask([_row("a"), _row("b", long_gold=False)], asker))
    assert set(out[0]) == {"id", "Dh-es", "Dw-es"} and set(out[1]) == {"id"}
    # head: one tournament call and three sentence calls; the window: only its own tournament
    # call, since every paragraph passes in both and the sentence calls are the same requests
    assert asker.calls["Dh-es"]["calls"] == 4
    assert asker.calls["Dw-es"]["calls"] == 1 and len(live.calls) == 5


def _reading(diff_low: float, text_high: float) -> dict[str, Any]:
    return {"recall": {"ci95_cluster": (diff_low, diff_low + 0.05)},
            "text_kept_share": {"ci95_cluster": (text_high - 0.01, text_high)}}  # fmt: skip


@pytest.mark.parametrize(
    ("es", "en", "start"),
    [
        (_reading(0.01, 0.005), _reading(-0.01, 0.005), "window confirmed"),
        (_reading(0.01, 0.005), _reading(-0.02, 0.005), "not adopted"),
        (_reading(0.0, 0.005), _reading(0.0, 0.005), "not shown"),
        (_reading(0.01, 0.01), _reading(0.0, 0.005), "Spanish recall gain, but more text"),
        (_reading(0.01, 0.005), _reading(0.0, 0.012), "Spanish recall gain, but more text"),
    ],
)
def test_the_registered_rule(es: dict, en: dict, start: str) -> None:
    assert cs.verdict(es, en).startswith(start)


def test_the_report_scales_the_changed_questions_to_every_question() -> None:
    def score(head: bool, window: bool, article: str) -> dict[str, Any]:
        def doc(hit: bool) -> dict[str, Any]:
            return {"all_gold": hit, "answer_kept": hit, "kept_share": 0.1}

        return {
            "id": article,
            "article": article,
            "head": doc(head),
            "window": doc(window),
            "enters_view": True,
        }

    es = [score(False, True, "x"), score(True, True, "y")]
    en = [score(True, True, "x")]
    got = cs.report({"es": es, "en": en}, {"es": 10, "en": 10})
    assert got["es"]["recall"]["diff"] == 0.5
    assert got["es"]["recall_over_every_question"] == 0.1
    assert got["es"]["changed_questions"] == {"n": 2, "of": 10, "share": 0.2}
    assert got["es"]["text_kept_share"]["diff"] == 0.0
    assert got["gap_es_minus_en"]["head"]["n"] == 1  # "x" is changed in both languages
    assert got["gap_es_minus_en"]["head"]["diff"] == -1.0


def test_power_rises_with_questions_and_falls_with_noise() -> None:
    assert cs.power_gain(400, 0.047, 0.09) > cs.power_gain(400, 0.047, 0.15)
    assert cs.power_gain(800, 0.047, 0.15) > cs.power_gain(400, 0.047, 0.15)
    assert cs.power_gain(0, 0.047, 0.15) == 0.0


def test_a_paid_run_refuses_before_the_key_without_its_launcher(tmp_path: Path) -> None:
    def trap(*_: Any, **__: Any) -> Any:
        raise AssertionError("the key was read")

    with pytest.raises(SystemExit, match="c6-window-run.cmd"):
        c6.paid(None, load_key=trap, check=trap, build_live=trap)
    other = tmp_path / "other.cmd"
    other.write_text("@echo off\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="c6-window-run.cmd"):
        c6.paid(other, load_key=trap, check=trap, build_live=trap)


def test_the_lot_is_bound_to_its_input_cap_and_instrument() -> None:
    lot = c6.lot()
    assert lot.name == "c6-window" and lot.cap_usd == c6.CAP_USD <= 10.0
    assert lot.inputs[0][0] == c6.INPUT and "benchmarks/b6_es" in lot.instrument
    assert br.FIXTURE == c6.FIXTURE  # the B6 asker replays this lot's recording only


def test_the_manifest_names_the_input_the_code_pins() -> None:
    import json

    manifest = json.loads(c6.MANIFEST.read_text(encoding="utf-8"))
    assert manifest["sha256"] == c6.INPUT_SHA256
    assert len(manifest["ids"]) == len(set(manifest["ids"])) == 836
    used, _, _ = c6.b6_used()
    assert not used & set(manifest["ids"])  # fresh: no question B6 asked
