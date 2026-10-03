"""The behaviour-set rule, without git or the dataset.

Run: .venv/Scripts/python.exe -m pytest benchmarks/adopt_dev -q
"""

from __future__ import annotations

from .behaviour_set import ALWAYSLOAD, WANT, classify, names_gold, tokens, walk


def test_tokens_take_identifiers_in_order_of_appearance() -> None:
    text = ("The `QuerySet.update()` call drops rows when select_related is used with "
            "`only` on a ModelAdmin; see django.db.models.query and e.g. the docs.")  # fmt: skip
    got = tokens(text)
    assert got[:2] == ["QuerySet.update", "QuerySet"]
    assert "update" in got and "select_related" in got and "only" in got
    assert "ModelAdmin" in got and "django.db.models.query" in got and "query" in got
    assert "e.g" not in got and "drops" not in got and "the" not in got


def test_a_statement_in_plain_words_has_no_tokens() -> None:
    assert tokens("The export drops the last row when the page is refreshed.") == []


def test_tokens_are_capped() -> None:
    text = " ".join(f"name_{i}" for i in range(100))
    assert len(tokens(text)) == 40


def test_a_named_file_points_at_the_gold() -> None:
    gold = ["django/contrib/admin/options.py"]
    assert names_gold("admin/options.py", gold) and names_gold("options.py", gold)
    assert not names_gold("options", gold) and not names_gold("forms.py", gold)


def test_a_token_with_few_hits_including_a_gold_file_is_a_control() -> None:
    hits = {"select_related": ["a.py", "b.py"], "Wide": [f"f{i}.py" for i in range(9)]}
    label, why = classify(["Wide", "select_related"], ["b.py"], lambda t: hits.get(t, []))
    assert label == "control" and why["token"] == "select_related"


def test_many_hits_or_no_gold_hit_is_behaviour_only() -> None:
    hits = {"Wide": [f"f{i}.py" for i in range(9)] + ["gold.py"], "Few": ["other.py"]}
    label, why = classify(["Wide", "Few"], ["gold.py"], lambda t: hits.get(t, []))
    assert label == "behaviour" and why == {}


def test_the_walk_stops_when_both_quotas_are_met() -> None:
    rows = [{"instance_id": f"r-{i}"} for i in range(30)]
    labels = {f"r-{i}": ("control" if i % 2 else "behaviour") for i in range(30)}
    picked, seen = walk(rows, lambda r: (labels[r["instance_id"]], {}))
    assert len(picked["behaviour"]) == WANT["behaviour"]
    assert len(picked["control"]) == WANT["control"]
    assert len(seen) == 13  # 7 behaviour-only need 13 rows; the controls were full at row 6


def test_the_alwaysload_probe_ids_are_excluded_by_name() -> None:
    assert len(ALWAYSLOAD) == 10 and "django__django-12143" in ALWAYSLOAD
