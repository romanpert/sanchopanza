"""C6's readings and verdict (`c6_window.py`, prereg in docs/results/2026-10-16-c6-window/).

Pure: no model, no I/O. Every label is B6's, by construction (`b6_score.doc_score`): the gold
sentence holds the MLQA answer span. The resampling unit is the Spanish article, since several
fresh questions share one (`l4_stats.clusters_as_units`).
"""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import NormalDist
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jev114"))

import l4_stats as ls  # noqa: E402

GAIN_LOW = 0.0  # Spanish: the cluster CI's lower bound of (window - head) above 0
EN_NOT_WORSE = -0.02  # English: the same bound above -2 points
TEXT_MARGIN = 0.01  # text kept (share of the article): the upper bound below +1 point
ARMS = {"es": ("Dh-es", "Dw-es"), "en": ("Dh-en", "Dw-en")}


def mean_ci(values: Sequence[float], clusters: Sequence[str]) -> dict[str, Any]:
    """Mean of paired differences with its 95 % CI by cluster bootstrap."""
    n = len(values)
    if n == 0:
        return {"n": 0, "diff": None, "ci95_cluster": None}

    def avg(idx: list[int]) -> float:
        return sum(values[i] for i in idx) / len(idx)

    return {
        "n": n,
        "diff": round(avg(list(range(n))), 5),
        "ci95_cluster": ls.ci95(ls.bootstrap(avg, ls.clusters_as_units(clusters))),
    }


def language(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One language's paired readings. Each score: `{"article", "head": doc_score, "window":
    doc_score, "enters_view": bool}` for a question whose article the window changes."""
    clusters = [s["article"] for s in scores]
    head = [bool(s["head"]["all_gold"]) for s in scores]
    window = [bool(s["window"]["all_gold"]) for s in scores]
    share = [s["window"]["kept_share"] - s["head"]["kept_share"] for s in scores]
    enters = [k for k, s in enumerate(scores) if s["enters_view"]]
    return {
        "recall": ls.paired_binary(window, head, clusters),
        "text_kept_share": mean_ci(share, clusters),
        "kept_share": {
            "head": round(sum(s["head"]["kept_share"] for s in scores) / max(1, len(scores)), 4),
            "window": round(
                sum(s["window"]["kept_share"] for s in scores) / max(1, len(scores)), 4
            ),
        },
        "answer_string_kept": ls.paired_binary(
            [bool(s["window"]["answer_kept"]) for s in scores],
            [bool(s["head"]["answer_kept"]) for s in scores],
            clusters,
        ),
        "gold_sentence_enters_view": ls.paired_binary(
            [window[k] for k in enters], [head[k] for k in enters], [clusters[k] for k in enters]
        ),
        "articles": len(set(clusters)),
    }


def low(reading: Mapping[str, Any]) -> float | None:
    ci = reading.get("ci95_cluster")
    return None if ci is None else ci[0]


def high(reading: Mapping[str, Any]) -> float | None:
    ci = reading.get("ci95_cluster")
    return None if ci is None else ci[1]


def verdict(es: Mapping[str, Any], en: Mapping[str, Any]) -> str:
    """The registered rule, on the changed questions of each language (prereg, "Verdict")."""
    bounds = (low(es["recall"]), high(es["text_kept_share"]), low(en["recall"]),
              high(en["text_kept_share"]))  # fmt: skip
    if any(b is None for b in bounds):
        return "no verdict: a language has no changed question"
    es_low, es_text, en_low, en_text = bounds
    if en_low <= EN_NOT_WORSE:
        return "not adopted: English recall may fall by 2 points or more"
    if es_low <= GAIN_LOW:
        return "not shown: no Spanish recall gain"
    if es_text >= TEXT_MARGIN or en_text >= TEXT_MARGIN:
        return "Spanish recall gain, but more text kept than the margin"
    return "window confirmed: Spanish recall up, English not worse, text within the margin"


def report(by_lang: Mapping[str, Sequence[Mapping[str, Any]]], totals: Mapping[str, int]) -> dict:
    """Every reading, and the verdict. `totals`: fresh questions per language, changed or not;
    an unchanged question is identical in both arms by construction (difference 0)."""
    out: dict[str, Any] = {}
    for lang, scores in by_lang.items():
        got = language(scores)
        diff = got["recall"].get("diff")
        share = len(scores) / max(1, totals[lang])
        got["changed_questions"] = {"n": len(scores), "of": totals[lang], "share": round(share, 4)}
        got["recall_over_every_question"] = None if diff is None else round(diff * share, 4)
        out[lang] = got
    out["gap_es_minus_en"] = gap(by_lang.get("es", ()), by_lang.get("en", ()))
    out["verdict"] = verdict(out["es"], out["en"])
    return out


def gap(es: Sequence[Mapping[str, Any]], en: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Spanish against English recall under each excerpt, on the questions changed in both
    (reported, not voted)."""
    english = {s["id"]: s for s in en}
    both = [(s, english[s["id"]]) for s in es if s["id"] in english]
    clusters = [s["article"] for s, _ in both]
    return {
        excerpt: ls.paired_binary(
            [bool(s[excerpt]["all_gold"]) for s, _ in both],
            [bool(e[excerpt]["all_gold"]) for _, e in both],
            clusters,
        )
        for excerpt in ("head", "window")
    }


# ---- power ---------------------------------------------------------------------------------

Z = NormalDist().inv_cdf


def power_gain(n: int, diff: float, discordant: float, *, low_bound: float = 0.0) -> float:
    """The chance the 95 % CI's lower bound of a paired difference clears `low_bound` at `n`
    questions, when it is truly `diff` and a share `discordant` of the pairs disagree."""
    var = discordant - diff**2
    if n <= 0 or var <= 0:
        return 0.0
    return NormalDist().cdf((diff - low_bound) / math.sqrt(var / n) - Z(0.975))
