"""The B6 bench (benchmarks/b6_es/): the Wikipedia parser, gold located by construction, the
consumer's two conditions, the scores and verdicts, the power formulas, and the runner's dry
count, caps and stops. No network, no data directory, no paid call."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from sanchopanza.contract import Decision
from sanchopanza.providers.capped import SpendCapReached

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "benchmarks/b6_es" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("b6_run")
import b6_build as bb  # noqa: E402  (on the path once the runner is loaded)
import b6_score as sc  # noqa: E402
import b6_wiki as wiki  # noqa: E402

# ---- the parser ------------------------------------------------------------------------------

HTML = """<div class="mw-parser-output">
<p>Intro <b>bold</b> text.<sup class="reference"><a>[1]</a></sup> More.</p>
<table class="infobox"><tr><td><p>In a table</p></td></tr></table>
<div class="mw-heading mw-heading2"><h2 id="H">Historia<span class="mw-editsection">
editar</span></h2></div>
<figure><figcaption><p>Caption</p></figcaption></figure>
<style>.x{color:red}</style>
<p>Second<br/>para with km<sup>2</sup>.
<p>Unclosed before a div</div>
"""  # fmt: skip


def test_parser_keeps_paragraphs_and_drops_notes_tables_figures_and_edit_links():
    got = wiki.paragraphs(HTML)
    assert got == [
        ("", "Intro bold text. More."),
        ("Historia", "Second para with km2."),
        ("Historia", "Unclosed before a div"),
    ]
    texts = " ".join(t for _, t in got)
    assert "In a table" not in texts and "Caption" not in texts and "color" not in texts
    assert "editar" not in " ".join(s for s, _ in got)


def test_the_zero_width_space_after_a_spanish_footnote_is_dropped_so_sentences_split():
    html = '<p>Fin en 2009.<sup class="reference">[20]</sup>​ Después vino otra.</p>'
    (_, text), = wiki.paragraphs(html)  # fmt: skip
    assert text == "Fin en 2009. Después vino otra."
    assert len(bb.split_sentences(text)) == 2


def test_wiki_refuses_a_language_outside_the_bench():
    with pytest.raises(ValueError):
        wiki._url("fr", title="X")


# ---- MLQA items and anchors ------------------------------------------------------------------


def test_collapse_with_map_points_each_original_position_into_the_collapsed_text():
    flat, where = bb.collapse_with_map("  a  b\n c ")
    assert flat == "a b c"
    assert flat[where[2]] == "a" and flat[where[5]] == "b" and flat[where[8]] == "c"
    flat, where = bb.collapse_with_map("x.​ Y")
    assert flat == "x. Y" and flat[where[4]] == "Y"
    flat, where = bb.collapse_with_map("en 2009.[20]​ Luego [sic] y [n. 3]fin")
    assert flat == "en 2009. Luego [sic] y fin" and flat[where[-3]] == "f"
    assert bb.wiki.collapse("en 2009.[20]​ Luego") == "en 2009. Luego"


def _qa(context: str, answer: str, start: int | None = None) -> dict:
    at = context.index(answer) if start is None else start
    return {"question": "¿Quién?", "answers": [{"text": answer, "answer_start": at}]}


def test_one_item_finds_the_answer_and_its_sentence():
    context = "Primera frase aquí. Luego el Sr. Pérez fundó la empresa en 1990. Otra más."
    item = bb.one_item("T", context, _qa(context, "1990"))
    a, b = item["answer_span"]
    s, e = item["anchor_span"]
    assert item["context"][a:b] == "1990"
    assert item["context"][s:e] == "Luego el Sr. Pérez fundó la empresa en 1990."


def test_one_item_moves_a_stale_offset_to_the_nearest_occurrence_and_refuses_a_missing_one():
    context = "Uno. Dos con  la  respuesta. Tres."
    item = bb.one_item("T", context, _qa(context, "la respuesta", start=3))
    assert item["context"][slice(*item["answer_span"])] == "la respuesta"
    assert bb.one_item("T", context, _qa(context, "nada", start=0)) is None


def test_footnote_marks_do_not_break_a_key():
    assert bb.key_of("siglo XX.[22]​ Entre")[0] == bb.key_of("siglo XX. Entre")[0]


ANCHOR = "La cantera de Trossingen fue excavada repetidamente en el siglo XX por Fraas."
ANSWER = (ANCHOR.index("Fraas"), ANCHOR.index("Fraas") + len("Fraas"))


def _paras(*texts: str) -> list[tuple[str, str]]:
    return [("S", t) for t in texts]


def test_locate_exact_unique():
    paras = _paras("Nada que ver.", "Antes. " + ANCHOR + " Después.")
    j, a, b, how = bb.locate(ANCHOR, ANSWER, paras)
    assert (j, paras[1][1][a:b], how) == (1, "Fraas", "exact")


def test_locate_refuses_a_repeated_or_short_anchor():
    assert bb.locate(ANCHOR, ANSWER, _paras(ANCHOR, ANCHOR)) == "anchor more than once"
    assert bb.locate("Corto.", (0, 5), _paras("Corto.")) == "anchor too short"


def test_locate_accepts_a_light_edit_only_when_the_answer_survives_it():
    edited = ANCHOR.replace("en el siglo XX", "durante el siglo XX")
    j, a, b, how = bb.locate(ANCHOR, ANSWER, _paras("Otra cosa.", edited))
    assert (j, _paras("Otra cosa.", edited)[j][1][a:b], how) == (1, "Fraas", "fuzzy")
    gone = ANCHOR.replace("Fraas", "otros paleontólogos alemanes")
    assert bb.locate(ANCHOR, ANSWER, _paras(gone)) in (
        "answer not in the edited anchor",
        "anchor not in the article",
    )
    assert bb.locate(ANCHOR, ANSWER, _paras("Un texto distinto del todo.")) == (
        "anchor not in the article"
    )


def test_doc_side_marks_only_the_sentence_holding_the_answer():
    item = {"question": "¿Quién?", "answer": "Fraas", "context": ANCHOR,
            "answer_span": list(ANSWER), "anchor_span": [0, len(ANCHOR)]}  # fmt: skip
    article = wiki.Article("es", "T", 7, tuple(_paras("Intro. Algo.", "Antes. " + ANCHOR)))
    side = bb.doc_side(item, article)
    assert side["gold_paragraph"] == 1 and side["gold_s"] == [[False, False], [False, True]]
    assert side["revid"] == 7 and side["match"] == "exact"


# ---- the consumer's preselection --------------------------------------------------------------


def test_preselect_keeps_everything_up_to_the_limit_and_the_best_in_page_order_past_it():
    pages = [("S", f"texto de relleno número {k}") for k in range(120)]
    pages[100] = ("S", "la cantera de Trossingen")
    assert bb.preselect("Trossingen", pages[:90], 90) == list(range(90))
    kept = bb.preselect("Trossingen", pages, 90)
    assert len(kept) == 90 and kept == sorted(kept) and 100 in kept


# ---- the pages bench -------------------------------------------------------------------------


def _item(title: str, context: str, question: str, answer: str) -> dict:
    a = context.index(answer)
    return {"title": title, "context": context, "question": question, "answer": answer,
            "answer_span": [a, a + len(answer)], "anchor_span": [0, len(context)]}  # fmt: skip


def _pool_items(n: int = 14) -> dict:
    items = {}
    for k in range(n):
        items[f"q{k:02d}"] = {
            "es": _item(f"T{k}", f"Párrafo {k} sobre el río Ebro y la ciudad {k}.",
                        f"¿Qué ciudad {k}?", f"ciudad {k}"),
            "en": _item(f"T{k}", f"Paragraph {k} about the Ebro river and town {k}.",
                        f"Which town {k}?", f"town {k}"),
        }  # fmt: skip
    items["q00"]["es"]["context"] += " También ciudad 3."  # holds q03's Spanish answer
    return items


def test_distractors_skip_the_question_own_paragraph_and_any_holding_its_answer():
    pool = bb.Pool(_pool_items())
    got = pool.distractors("q03", 9)
    assert "q03" not in got and "q00" not in got and len(got) == 9


def test_a_page_row_is_the_same_units_in_the_same_order_in_both_languages():
    pool = bb.Pool(_pool_items())
    row = bb.page_row("q05", pool)
    assert len(row["units"]) == 10 and row["units"][row["gold"]] == "q05"
    for lang in bb.LANGS:
        assert row[lang]["pages"][row["gold"]][1] == pool.items["q05"][lang]["context"]


# ---- scores ----------------------------------------------------------------------------------


def _page_row(answer_end: int = 20) -> dict:
    long_gold = "x" * 1200
    pages = [["T", "corto"]] * 10
    side = {"question": "q", "answer": "a", "answer_span": [answer_end - 5, answer_end],
            "pages": [list(p) for p in pages]}  # fmt: skip
    side["pages"][3] = ["T", long_gold]
    english = {**side, "question": "q in English", "answer_span": [0, 5]}
    return {"id": "p1", "gold": 3, "es": side, "en": english}


def test_page_score_delivers_the_answer_under_the_cut_only_inside_900_characters():
    keep_gold = [[k == 3, 0.9] for k in range(10)]
    near = sc.page_score(_page_row(answer_end=500), "P-es900", keep_gold)
    far = sc.page_score(_page_row(answer_end=1000), "P-es900", keep_gold)
    assert near["hit"] and near["delivered"] and far["hit"] and not far["delivered"]
    assert round(near["kept_share"], 4) == round(900 / (900 + 9 * 5), 4)
    assert sc.page_score(_page_row(), "P-es", [[False, 0.1]] * 10)["hit"] is False


def _doc_row(paragraphs: int = 4, gold_at: int = 2) -> dict:
    pages = [["S", f"Frase uno del párrafo {k}. Frase dos del párrafo {k}."]
             for k in range(paragraphs)]  # fmt: skip
    gold = [[False, False] for _ in pages]
    gold[gold_at] = [False, True]
    side = {"question": "párrafo", "answer": "dos", "pages": pages, "gold_paragraph": gold_at,
            "gold_s": gold}  # fmt: skip
    return {"id": "d1", "es": side, "en": side}


def test_doc_score_reads_select_passages_entries_against_the_gold_sentence():
    row = _doc_row()
    entries = [None, None, [[False, 0.1], [True, 0.9]], [[True, 0.8], [False, 0.2]]]
    mask = sc.doc_mask(row, "D-es", entries)
    score = sc.doc_score(row, "D-es", mask)
    assert score["all_gold"] and score["any_gold"] and score["gold_paragraph_sent"]
    assert 0 < score["kept_share"] < 0.5
    missed = sc.doc_score(row, "D-es", sc.doc_mask(row, "D-es", [None] * 4))
    assert not missed["all_gold"] and missed["kept_share"] == 0


def test_doc_mask_maps_a_preselected_article_back_to_its_paragraphs():
    row = _doc_row(paragraphs=95, gold_at=94)
    row["es"]["pages"][94] = ["S", "Nada. La palabra clave rara."]
    row["es"]["question"] = "palabra clave rara"
    _, sent, index = sc.doc_inputs(row, "D-es90")
    assert len(sent) == 90 and 94 in index
    entries = [[[True, 0.9]] * 2 if full == 94 else None for full in index]
    assert sc.doc_score(row, "D-es90", sc.doc_mask(row, "D-es90", entries))["all_gold"]


# ---- verdicts and power ----------------------------------------------------------------------


def test_paired_verdicts_at_the_five_point_margin():
    same = [True] * 190 + [False] * 10
    assert sc.paired(same, same)["verdict"] == "no worse"
    worse = [True] * 150 + [False] * 50
    assert sc.paired(worse, same)["verdict"] == "worse by more than 5 points"
    few = [True] * 18 + [False] * 2
    assert sc.paired(few, [True] * 20)["verdict"] == "inconclusive"


def test_power_formulas():
    assert sc.n_noninferiority(0.10) == 314
    assert sc.n_noninferiority(0.10, true_diff=-0.06) == 10**9
    assert 300 <= sc.n_detect(0.10) <= 320
    assert round(sc.half_width(0.10, 240), 3) == 0.04
    assert round(sc.power_no_worse(0.10, 314), 2) == 0.80


# ---- the runner ------------------------------------------------------------------------------


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "FIXTURE", tmp_path / "fixture.jsonl")
    monkeypatch.setattr(run, "SEAL", tmp_path / "prereg.sha256")
    monkeypatch.setattr(run, "LEDGER_PATH", tmp_path / "ledger.json")
    return tmp_path


def test_dry_counts_one_call_per_page_set_and_the_consumer_arms_only_where_they_differ(
    isolated, monkeypatch
):
    pages = [_page_row(), {**_page_row(), "id": "p2"}]
    pages[1]["es"] = {**pages[1]["es"], "pages": [["T", "corto"]] * 10}  # nothing over 900
    pages[1]["en"] = {**pages[1]["en"], "question": "another question"}  # identical calls merge
    docs = [_doc_row(paragraphs=4), {**_doc_row(paragraphs=95), "id": "d2"}]
    monkeypatch.setattr(run, "load_rows",
                        lambda data, name, n=None: pages if name == "pages" else docs)  # fmt: skip
    report = run.dry(isolated, 2, 2)
    assert report["by_arm"]["P-es"]["calls"] == 2 and report["by_arm"]["P-en"]["calls"] == 2
    assert report["by_arm"]["P-es900"]["calls"] == 1
    assert report["docs_over_90_paragraphs_es"] == 1
    assert report["by_arm"]["D-es90"]["calls_triage_pages"] >= 4  # 90 paragraphs: three groups+
    assert report["claude_usd"] == 0.0 and report["jev_total"]["calls"] > 0
    assert report["jev_total"]["calls"] <= report["jev_upper_bound_calls"]


def test_replay_without_recordings_is_incomplete_and_scores_nothing(isolated, monkeypatch):
    monkeypatch.setattr(run, "load_rows", lambda data, name, n=None:
                        [_page_row()] if "pages" in name else [_doc_row()])  # fmt: skip
    monkeypatch.setattr(run, "OUT", isolated / "out")
    assert run.run(isolated, live=False, smoke=False) == 1
    assert not (isolated / "out" / "analysis.json").exists()


def test_live_refuses_without_a_matching_seal(isolated, monkeypatch):
    monkeypatch.setattr(run, "load_rows", lambda data, name, n=None: [])
    with pytest.raises(SystemExit, match="nothing spent"):
        run.run(isolated, live=True, smoke=False)


class _Refusing:
    name = "jev"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point, state, qs):
        self.calls += 1
        raise SpendCapReached("spend cap: does not fit")


def test_a_cap_refusal_stops_every_later_call(isolated):
    inner = _Refusing()
    asker = run.Asker(inner, live=True)

    async def twice():
        await asker.decide("P-es", "triage_pages", {"pages": "a"}, {})
        await asker.decide("P-es", "triage_pages", {"pages": "b"}, {})

    asyncio.run(twice())
    assert inner.calls == 1 and asker.failures == 2 and asker.halted


class _WrongModel:
    name = "jev"

    async def decide(self, point, state, qs):
        return Decision(point, {"P01": run.truth(0.9)}, "jev", "jev-1.14.0")


def test_an_answer_from_another_model_stops_the_run(isolated):
    asker = run.Asker(_WrongModel(), live=True)
    with pytest.raises(SystemExit, match="served jev-1.14.0"):
        asyncio.run(asker.decide("P-es", "triage_pages", {"pages": "a"}, {}))
