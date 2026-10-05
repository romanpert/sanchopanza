"""The offline selection analysis of free sessions: candidate answers taken mechanically from tool
results, matching, and the pushback rule. No model, no transcript, no money."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_free_select", ROOT / "benchmarks/browse/free_select.py"
)
sel = importlib.util.module_from_spec(spec)
sys.modules["browse_free_select"] = sel
spec.loader.exec_module(sel)


def test_answer_head_drops_the_explanation_agents_append():
    assert sel.answer_head("Nosferatu the Vampyre (1979), directed by Herzog") == (
        "Nosferatu the Vampyre"
    )
    assert sel.answer_head("Damages (91% Tomatometer) - it is the lowest") == "Damages"
    assert sel.answer_head("~10.7% (3 out of 28 days)") == "10.7%"
    assert sel.answer_head("Wake Up Dead Man — IMDB 7.4") == "Wake Up Dead Man"
    assert sel.answer_head("") == ""


def test_answer_kind_tells_figures_from_names():
    assert sel.answer_kind("10.7%") == "number"
    assert sel.answer_kind("$55") == "number"
    assert sel.answer_kind("1148 sqft") == "number"
    assert sel.answer_kind("3.08 million") == "number"
    assert sel.answer_kind("VGT") == "name"
    assert sel.answer_kind("Glass Onion: A Knives Out Mystery") == "name"
    assert sel.answer_kind("") == ""


def test_clean_removes_urls_search_keys_and_the_websearch_reminder():
    text = (
        'Links: [{"title":"Adrenalinpark Köln","url":"https://x.de/Köln-Park"}]\n'
        "REMINDER: You MUST cite"
    )
    out = sel.clean(text)
    assert "https" not in out and "REMINDER" not in out and '"title":"' not in out
    assert "Adrenalinpark Köln" in out


def test_name_spans_join_connectors_and_split_at_a_colon():
    spans = [s for s, _ in sel.name_spans("I liked Glass Onion: A Knives Out Mystery a lot.")]
    assert "Glass Onion: A Knives Out Mystery" in spans
    assert "Glass Onion" in spans and "A Knives Out Mystery" in spans
    spans = [s for s, _ in sel.name_spans("the film Nosferatu the Vampyre by Herzog")]
    assert "Nosferatu the Vampyre" in spans
    spans = [s for s, _ in sel.name_spans("Potash Markets - Clark Street sells salads")]
    assert "Potash Markets - Clark Street" in spans and "Clark Street" in spans


def test_name_spans_join_a_one_word_name_across_a_comma_and_stop_at_a_newline():
    spans = [s for s, _ in sel.name_spans("banned with Oko, Thief of Crowns in 2019")]
    assert "Oko, Thief of Crowns" in spans and "Thief of Crowns" in spans
    spans = [s for s, _ in sel.name_spans("Renzo Gracie\nWall Street")]
    assert "Renzo Gracie" in spans and "Renzo Gracie\nWall Street" not in spans
    # A trailing connector is not part of the name.
    assert [s for s, _ in sel.name_spans("Bank of")] == ["Bank"]


def test_name_spans_report_where_each_span_starts():
    text = "see Adrenalinpark Köln today"
    ((span, start),) = sel.name_spans(text)
    assert text[start : start + len(span)] == span


def test_number_spans_read_units_and_skip_bare_years():
    found = {v for _s, v, _p in sel.number_spans("In 2021 it sold for $3.08 million, or 3,080,000")}
    assert 3_080_000 in found and 2021 not in found
    assert [v for _s, v, _p in sel.number_spans("31.67% of days")] == [31.67]
    assert [v for _s, v, _p in sel.number_spans("12k followers")] == [12_000]


def test_candidates_rank_by_nearness_to_the_question_and_drop_its_own_words():
    question = "Which paintball places in Cologne are near a karting track?"
    filler = "x " * 200
    text = (
        "Kartcenter Cologne is a karting track. Adrenalinpark Köln offers paintball near the "
        f"karting track. {filler} Imprint. {filler} Imprint. {filler} Imprint. Cologne."
    )
    pool = sel.candidates(text, question, "name")
    names = [c.text for c in pool]
    assert "Cologne" not in names  # only the question's own word
    # Seen once beside the question's words beats seen three times far from them.
    assert names.index("Adrenalinpark Köln") < names.index("Imprint")
    assert next(c for c in pool if c.text == "Imprint").count == 3


def test_candidates_group_figures_by_value_and_drop_the_questions_numbers():
    question = "Based on 2020-2023, how likely is a day over 95 F in June?"
    text = "Days over 95 F in June: 31.67% of days. Another source: 31.67 %. Peak 101 F."
    pool = sel.candidates(text, question, "number")
    keys = [c.key for c in pool]
    assert "31.67" in keys and "95" not in keys
    assert next(c for c in pool if c.key == "31.67").count == 2


def test_candidates_drop_generic_words_and_respect_k():
    text = "The Search Results. Alpha Beta. Gamma Delta. Epsilon Zeta."
    names = [c.text for c in sel.candidates(text, "anything", "name", k=2)]
    assert len(names) == 2 and "The" not in names and "Search" not in names


def test_occurrences_find_the_agents_answer_as_text_or_value():
    text = "LinkedIn has 2M. linkedin again. The share was 41.7% and 41.70 %."
    assert len(sel.occurrences(text, "LinkedIn", "name")) == 2
    assert len(sel.occurrences(text, "41.7%", "number")) == 2
    assert sel.occurrences(text, "", "name") == ()
    assert sel.occurrences(text, "about", "number") == ()


def test_evidence_takes_non_overlapping_windows_best_first_in_text_order():
    filler = "x " * 400
    text = f"Renzo Gracie {filler} Renzo Gracie martial arts NYSE evening {filler} Renzo Gracie"
    starts = [m for m in range(len(text)) if text.startswith("Renzo Gracie", m)]
    out = sel.evidence(text, starts, "martial arts near the NYSE in the evening", limit=1)
    assert "martial arts NYSE evening" in out and " ... " not in out
    assert sel.evidence(text, starts, "q", limit=3).count(" ... ") == 2


def test_same_matches_names_by_coverage_and_figures_within_one_percent():
    assert sel.same("LinkedIn", "Linkedin", "name")
    assert sel.same(
        "Fidelity Emerging Markets Index Fund",
        "Fidelity® Emerging Markets Index Fund (FPADX)",
        "name",
    )
    assert not sel.same("Knives Out", "Glass Onion: A Knives Out Mystery", "name")
    assert not sel.same(
        "Wake Up Dead Man: A Knives Out Mystery", "Glass Onion: A Knives Out Mystery", "name"
    )
    assert sel.same("31.67%", "31.67", "number") and not sel.same("35%", "31.67", "number")
    assert not sel.same("", "x", "name")


def test_claim_puts_the_candidate_first_so_a_long_question_truncates_instead():
    assert sel.claim("VGT", "Which ETF?").startswith("VGT is the answer")


def test_pick_ignores_unscored_candidates():
    assert sel.pick([("a", None), ("b", 0.4), ("c", 0.9)]) == ("c", 0.9)
    assert sel.pick([("a", None)]) is None


def view(success, pick, own=False, gold=False, answered=True, cost=0.1):
    return {
        "answered": answered,
        "success": success,
        "claim_pick": pick,
        "claim_pick_is_own": own,
        "claim_pick_is_gold": gold,
        "mean_call_usd": cost,
    }


def test_the_rule_fires_only_on_an_answer_another_candidate_beats():
    assert sel.fires(view(False, ("x", 0.95)), 0.9)
    assert not sel.fires(view(False, ("x", 0.95), own=True), 0.9)
    assert not sel.fires(view(False, ("x", 0.85)), 0.9)
    assert not sel.fires(view(False, ("x", 0.95), answered=False), 0.9)
    assert not sel.fires(view(False, None), 0.5)


def test_outcome_counts_fixes_risks_and_the_extra_calls():
    views = [
        view(False, ("gold", 0.95), gold=True),
        view(False, ("junk", 0.92)),
        view(True, ("junk", 0.91)),
        view(True, ("own", 0.99), own=True),
    ]
    out = sel.outcome(views, 0.9)
    assert (out["fires"], out["fires_on_wrong"]) == (3, 2)
    assert (out["would_fix_upper_bound"], out["fires_on_right_risk"]) == (1, 1)
    assert out["extra_usd"] == {"1_calls": 0.3, "5_calls": 1.5}
