"""The B6 reports, one per bench, from the answers `b6_run.py` collected. Pure and free.

Each function returns the registered readings (prereg.md, "Verdict rules"): the primary with
its verdict, the secondaries and the sensitivity readings without one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import b6_score as sc

PAGE_ARMS = ("P-es", "P-en")
DOC_ARMS = ("D-es", "D-es90", "D-en")


def _paired_rows(scores: Mapping[str, list[dict]], key: str, a: str, b: str,
                 rows: Sequence[int]) -> tuple[list[bool], list[bool]]:  # fmt: skip
    return [scores[a][k][key] for k in rows], [scores[b][k][key] for k in rows]


def pages_report(rows: Sequence[Mapping[str, Any]], out: Sequence[Mapping[str, Any]]) -> dict:
    ps = {arm: [sc.page_score(r, sc.lang_of(arm), o[arm]) for r, o in zip(rows, out, strict=True)]
          for arm in PAGE_ARMS}  # fmt: skip
    every = list(range(len(rows)))
    seen = [
        k for k in every if sc.answer_in_view(rows[k], "es") and sc.answer_in_view(rows[k], "en")
    ]
    share = {arm: [s["kept_share"] for s in ps[arm]] for arm in PAGE_ARMS}
    primary = sc.paired(*_paired_rows(ps, "hit", "P-es", "P-en", seen))
    text = sc.text_side([share["P-es"][k] for k in seen], [share["P-en"][k] for k in seen])
    hit = {arm: [s["hit"] for s in ps[arm]] for arm in PAGE_ARMS}
    return {
        "H1_pages_es_vs_en": {
            **primary,
            "rows": "answer within the first 900 characters in both languages",
            "text": text,
            "pareto": sc.pareto(primary, text),
        },
        "H1_all_rows": sc.describe(hit["P-es"], hit["P-en"]),
        "C1_consumer_cut_900": {
            **sc.paired([s["delivered"] for s in ps["P-es"]], hit["P-es"]),
            "note": "free from P-es: the decider already sees 900 characters a page; the cut "
            "loses exactly the kept gold pages whose answer ends past character 900",
            "answer_past_900": {
                lang: sum(not sc.answer_in_view(r, lang) for r in rows) for lang in ("es", "en")
            },  # fmt: skip
        },
        "answer_string_kept": sc.describe(
            [s["answer_kept"] for s in ps["P-es"]], [s["answer_kept"] for s in ps["P-en"]]
        ),  # fmt: skip
        "kept_absolute": {
            arm: {
                "chars": sc.mean([s["kept_chars"] for s in ps[arm]]),
                "pages": sc.mean([s["kept_pages"] for s in ps[arm]]),
            }
            for arm in PAGE_ARMS
        },  # fmt: skip
        "kept_share": {arm: sc.mean(share[arm]) for arm in PAGE_ARMS},
        "anchors": {
            "es": sc.proportion(hit["P-es"]),
            "en": sc.proportion(hit["P-en"]),
            "published_english": sc.PUBLISHED["pages"],
        },
        "bm25_at_same_text": {
            sc.lang_of(arm): sc.mean(
                [
                    sc.bm25_pages_at(r, sc.lang_of(arm), s["kept_chars"])
                    for r, s in zip(rows, ps[arm], strict=True)
                ]
            )
            for arm in PAGE_ARMS
        },  # fmt: skip
    }


def docs_report(rows: Sequence[Mapping[str, Any]], out: Sequence[Mapping[str, Any]],
                all_rows: Sequence[Mapping[str, Any]]) -> dict:  # fmt: skip
    ds = {arm: [sc.doc_score(r, arm, sc.doc_mask(r, arm, o[arm]))
                for r, o in zip(rows, out, strict=True)] for arm in DOC_ARMS}  # fmt: skip
    every = list(range(len(rows)))

    def compare(key: str, which: Sequence[int], a: str = "D-es", b: str = "D-en") -> dict:
        return sc.describe(*_paired_rows(ds, key, a, b, which))

    share = {arm: [s["kept_share"] for s in ds[arm]] for arm in DOC_ARMS}
    primary = sc.paired(*_paired_rows(ds, "all_gold", "D-es", "D-en", every))
    text = sc.text_side(share["D-es"], share["D-en"])
    exact = [k for k in every if sc.both_exact(rows[k])]
    fuzzy = [k for k in every if not sc.both_exact(rows[k])]
    only = [k for k in every if all(sc.answer_only_in_gold(rows[k], g) for g in ("es", "en"))]
    view = [k for k in every if all(sc.gold_in_view(rows[k], g) for g in ("es", "en"))]
    long_docs = [k for k in every if len(rows[k]["es"]["pages"]) > sc.CONSUMER_PRESELECT]
    gold = {arm: [s["all_gold"] for s in ds[arm]] for arm in DOC_ARMS}
    return {
        "H2_docs_es_vs_en": {**primary, "text": text, "pareto": sc.pareto(primary, text)},
        "any_gold": compare("any_gold", every),
        "sensitivity_both_exact": compare("all_gold", exact),
        "sensitivity_any_fuzzy": compare("all_gold", fuzzy),
        "answer_only_in_gold_both": compare("all_gold", only),
        "gold_in_view_both": compare("all_gold", view),
        "answer_string_kept": compare("answer_kept", every),
        "C2_bm25_90_descriptive": {
            **compare("all_gold", long_docs, "D-es90", "D-es"),
            "preselection_keeps_gold_paragraph_all_built": sc.proportion(
                [x for r in all_rows if (x := sc.preselect_keeps_gold(r, "es")) is not None]
            ),
        },
        "kept_absolute": {
            arm: {
                "chars": sc.mean([s["kept_chars"] for s in ds[arm]]),
                "sentences": sc.mean([s["kept_sentences"] for s in ds[arm]]),
            }
            for arm in DOC_ARMS
        },  # fmt: skip
        "kept_share": {arm: sc.mean(share[arm]) for arm in DOC_ARMS},
        "anchors": {
            "es": sc.proportion(gold["D-es"]),
            "en_outside_qasper": sc.proportion(gold["D-en"]),
            "published_english": sc.PUBLISHED["docs"],
        },
        "bm25_at_same_text": {
            lang: sc.mean(
                [
                    sc.bm25_sentences_at(r, lang, s["kept_chars"])
                    for r, s in zip(rows, ds[f"D-{lang}"], strict=True)
                ]
            )
            for lang in ("es", "en")
        },  # fmt: skip
        "rows": {
            "all": len(every),
            "both_exact": len(exact),
            "answer_only_in_gold": len(only),
            "gold_in_view": len(view),
            "over_90_es": len(long_docs),
        },  # fmt: skip
    }
