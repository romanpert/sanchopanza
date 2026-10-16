"""Scores, comparisons and power for the B6 bench (`b6_run.py`). Pure: no model, no network.

Every metric is a label by construction: a page is the question's own MLQA paragraph or not, a
sentence holds the MLQA answer span or not. Nothing here reads a decider's answer as a label.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from statistics import NormalDist
from typing import Any

import b6_build as bb

from sanchopanza.eval.stats import bootstrap_difference, mcnemar, wilson
from sanchopanza.text import BM25Index

MARGIN = 0.05  # Spanish no worse than English by more than 5 points
TEXT_MARGIN = 0.05  # Spanish keeps at most 5 points more of the text (the Pareto side)
PUBLISHED = {
    "pages": {"recall": 0.983, "kept_share": 0.336, "source": "HotpotQA, 300 questions"},
    "docs": {"recall": 0.872, "kept_share": 0.210, "source": "QASPER, 219 questions"},
}
# `triage_pages` and every tournament call show the decider each page's first 900 characters
# (`chunks.PAGE_LIMIT`, `Limits.page_chars`): the consumer's own cut to 900 sends the decider
# the same text, without the " [...]" marker. What the cut changes is what is delivered.
VIEW = 900
CONSUMER_PRESELECT = 90


def lang_of(arm: str) -> str:
    return "en" if arm.endswith("-en") else "es"


def letters(text: str) -> str:
    return bb.key_of(text)[0]


# ---- pages --------------------------------------------------------------------------------


def page_texts(row: Mapping[str, Any], lang: str) -> list[tuple[str, str]]:
    return [(str(t), str(x)) for t, x in row[lang]["pages"]]


def answer_in_view(row: Mapping[str, Any], lang: str) -> bool:
    """The gold page's answer ends within the 900 characters the decider sees."""
    return row[lang]["answer_span"][1] <= VIEW


def page_score(row: Mapping[str, Any], lang: str, verdicts: Sequence[Sequence[Any]]) -> dict:
    """`hit`: the gold page kept. `delivered`: kept and its answer within the first 900
    characters, what a consumer that cuts each page to 900 passes on (C1, free). `answer_kept`:
    the answer's letters appear in some kept page. Shares are of characters."""
    pages = page_texts(row, lang)
    keep = [bool(v[0]) for v in verdicts]
    hit = keep[row["gold"]]
    kept_text = " ".join(x for (_, x), k in zip(pages, keep, strict=True) if k)
    kept = sum(len(x) for (_, x), k in zip(pages, keep, strict=True) if k)
    return {
        "hit": hit,
        "delivered": hit and answer_in_view(row, lang),
        "answer_kept": letters(row[lang]["answer"]) in letters(kept_text),
        "kept_share": kept / max(1, sum(len(x) for _, x in pages)),
        "kept_chars": kept,
        "kept_pages": sum(keep),
    }


# ---- docs ---------------------------------------------------------------------------------


def doc_inputs(row: Mapping[str, Any], arm: str) -> tuple[str, list[tuple[str, str]], list[int]]:
    """`(question, paragraphs sent, their indexes in the article)`. D-es90 preselects by BM25
    past 90 paragraphs (`b6_build.preselect`); the other arms send the article whole."""
    side = row[lang_of(arm)]
    pages = [(str(s), str(t)) for s, t in side["pages"]]
    keep = list(range(len(pages)))
    if arm == "D-es90":
        keep = bb.preselect(side["question"], pages, CONSUMER_PRESELECT)
    return side["question"], [pages[k] for k in keep], keep


def doc_mask(row: Mapping[str, Any], arm: str, entries: Sequence[Any]) -> list[list[bool]]:
    """Per paragraph of the whole article, per sentence: kept by `select_passages`."""
    _, _, sent = doc_inputs(row, arm)
    gold = row[lang_of(arm)]["gold_s"]
    mask = [[False] * len(g) for g in gold]
    for sub, full in enumerate(sent):
        entry = entries[sub]
        if entry is None:
            continue
        flags = [bool(e[0]) for e in entry]
        if len(flags) != len(gold[full]):
            raise ValueError(f"{row['id']} {arm}: sentence count differs in paragraph {full}")
        mask[full] = flags
    return mask


def sentences(row: Mapping[str, Any], lang: str) -> list[list[str]]:
    return [[t[a:b] for a, b in bb.sentence_ranges(t)] for _, t in row[lang]["pages"]]


def doc_score(row: Mapping[str, Any], arm: str, mask: Sequence[Sequence[bool]]) -> dict:
    lang = lang_of(arm)
    gold = row[lang]["gold_s"]
    texts = sentences(row, lang)
    hits = [m for ms, gs in zip(mask, gold, strict=True) for m, g in zip(ms, gs, strict=True) if g]
    kept = [s for ms, ss in zip(mask, texts, strict=True) for m, s in zip(ms, ss, strict=True) if m]
    total = sum(len(s) for ss in texts for s in ss)
    _, _, sent = doc_inputs(row, arm)
    return {
        "all_gold": all(hits),
        "any_gold": any(hits),
        "answer_kept": letters(row[lang]["answer"]) in letters(" ".join(kept)),
        "kept_share": sum(len(s) for s in kept) / max(1, total),
        "kept_chars": sum(len(s) for s in kept),
        "kept_sentences": len(kept),
        "gold_paragraph_sent": row[lang]["gold_paragraph"] in set(sent),
    }


def answer_only_in_gold(row: Mapping[str, Any], lang: str) -> bool:
    """The answer's letters occur in the gold sentence and in no other sentence of the article:
    a question where keeping any other sentence cannot stand in for the gold one."""
    needle = letters(row[lang]["answer"])
    gold = row[lang]["gold_s"]
    for ss, gs in zip(sentences(row, lang), gold, strict=True):
        for s, g in zip(ss, gs, strict=True):
            if not g and needle in letters(s):
                return False
    return True


def gold_in_view(row: Mapping[str, Any], lang: str) -> bool:
    """The gold sentence starts within the 900 characters of its paragraph the tournament sees."""
    side = row[lang]
    j = side["gold_paragraph"]
    ranges = bb.sentence_ranges(side["pages"][j][1])
    first = next(i for i, g in enumerate(side["gold_s"][j]) if g)
    return ranges[first][0] < VIEW


def both_exact(row: Mapping[str, Any]) -> bool:
    return all(row[lang].get("match") == "exact" for lang in bb.LANGS)


# ---- free baselines (BM25, no model) ------------------------------------------------------


def bm25_pages_at(row: Mapping[str, Any], lang: str, budget: int) -> bool:
    """The gold page is among the BM25 best pages that fit `budget` characters (at least one)."""
    pages = page_texts(row, lang)
    scores = BM25Index([f"{t}\n{x}" for t, x in pages]).scores(row[lang]["question"])
    used = 0
    for k in sorted(range(len(pages)), key=lambda k: (-scores[k], k)):
        if used and used + len(pages[k][1]) > budget:
            break
        if k == row["gold"]:
            return True
        used += len(pages[k][1])
    return False


def bm25_sentences_at(row: Mapping[str, Any], lang: str, budget: int) -> bool:
    """Every gold sentence is among the BM25 best sentences of the article within `budget`."""
    side = row[lang]
    flat = [(j, i, s) for j, ss in enumerate(sentences(row, lang)) for i, s in enumerate(ss)]
    scores = BM25Index([s for _, _, s in flat]).scores(side["question"])
    chosen, used = set(), 0
    for k in sorted(range(len(flat)), key=lambda k: (-scores[k], k)):
        if used >= budget:
            break
        chosen.add((flat[k][0], flat[k][1]))
        used += len(flat[k][2])
    gold = {(j, i) for j, g in enumerate(side["gold_s"]) for i, x in enumerate(g) if x}
    return gold <= chosen


def preselect_keeps_gold(row: Mapping[str, Any], lang: str) -> bool | None:
    """Whether BM25 past 90 paragraphs keeps the gold paragraph; None when nothing is cut."""
    side = row[lang]
    if len(side["pages"]) <= CONSUMER_PRESELECT:
        return None
    keep = bb.preselect(side["question"], side["pages"], CONSUMER_PRESELECT)
    return side["gold_paragraph"] in set(keep)


# ---- comparisons -------------------------------------------------------------------------


def mean_difference(a: Sequence[float], b: Sequence[float], *, replicas: int = 2000,
                    seed: int = 7) -> tuple[float, float, float]:  # fmt: skip
    """Mean of a - b with a 95 % CI by paired resampling (the scheme of `eval.stats`)."""
    if len(a) != len(b) or not a:
        raise ValueError("both series must have the same non-zero length")
    n = len(a)
    rng = random.Random(seed)
    diffs = []
    for _ in range(replicas):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(a[i] - b[i] for i in idx) / n)
    diffs.sort()
    observed = sum(x - y for x, y in zip(a, b, strict=True)) / n
    return observed, diffs[int(0.025 * replicas)], diffs[int(0.975 * replicas) - 1]


def describe(a: Sequence[bool], b: Sequence[bool]) -> dict[str, Any]:
    """a against b on the same questions: difference, bootstrap CI, McNemar; no verdict."""
    if not a:
        return {"n": 0}
    diff, lo, hi = bootstrap_difference(list(a), list(b))
    only_a, only_b, p = mcnemar(list(a), list(b))
    return {
        "n": len(a),
        "a": round(sum(a) / len(a), 4),
        "b": round(sum(b) / len(b), 4),
        "difference": round(diff, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "only_a": only_a,
        "only_b": only_b,
        "mcnemar_p": round(p, 4),
    }


def verdict(lo: float, hi: float, *, margin: float = MARGIN) -> str:
    if lo > -margin:
        return "no worse" + (" (but lower)" if hi < 0 else "")
    if hi < -margin:
        return f"worse by more than {round(100 * margin)} points"
    return "inconclusive"


def paired(a: Sequence[bool], b: Sequence[bool], *, margin: float = MARGIN) -> dict[str, Any]:
    """`describe`, and the verdict at `margin` from the CI (prereg, rules 1-3)."""
    out = describe(a, b)
    if out["n"]:
        out["verdict"] = verdict(*out["ci95"], margin=margin)
    return out


def proportion(hits: Sequence[bool]) -> dict[str, Any]:
    p, lo, hi = wilson(sum(hits), len(hits))
    return {"n": len(hits), "rate": round(p, 4), "ci95": [round(lo, 4), round(hi, 4)]}


def text_side(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    diff, lo, hi = mean_difference(a, b)
    return {
        "a": round(sum(a) / len(a), 4),
        "b": round(sum(b) / len(b), 4),
        "difference": round(diff, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "within_margin": hi < TEXT_MARGIN,
    }


def pareto(recall: Mapping[str, Any], text: Mapping[str, Any]) -> str:
    """ "no worse on both" when the recall verdict is "no worse" and Spanish keeps at most 5
    points more text (the CI's upper bound); else which side fails."""
    good_recall = str(recall.get("verdict", "")).startswith("no worse")
    if good_recall and text["within_margin"]:
        return "no worse on both"
    if good_recall:
        return "no worse on recall only (more text)"
    return "not shown on recall"


def mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


# ---- power -------------------------------------------------------------------------------

Z = NormalDist().inv_cdf


def n_noninferiority(discordant: float, *, margin: float = MARGIN, true_diff: float = 0.0,
                     alpha: float = 0.05, power: float = 0.80) -> int:  # fmt: skip
    """Paired questions for the 95 % CI's lower bound of a - b to clear -margin with `power`,
    when a - b is truly `true_diff` and a share `discordant` of pairs disagree (normal
    approximation to the paired difference, as the bootstrap estimates it)."""
    var = discordant - true_diff**2
    gap = true_diff + margin
    if gap <= 0 or var <= 0:
        return 10**9
    return math.ceil((Z(1 - alpha / 2) + Z(power)) ** 2 * var / gap**2)


def n_detect(discordant: float, *, drop: float = MARGIN, alpha: float = 0.05,
             power: float = 0.80) -> int:  # fmt: skip
    """Paired questions for McNemar (normal form) to detect a true drop of `drop` with `power`."""
    var = discordant - drop**2
    if var <= 0:
        return 10**9
    num = Z(1 - alpha / 2) * math.sqrt(discordant) + Z(power) * math.sqrt(var)
    return math.ceil(num**2 / drop**2)


def power_no_worse(discordant: float, n: int, *, margin: float = MARGIN,
                   true_diff: float = 0.0) -> float:  # fmt: skip
    """The chance the 95 % CI's lower bound clears -margin at `n` questions (normal form)."""
    var = discordant - true_diff**2
    if var <= 0 or n <= 0:
        return 0.0
    return NormalDist().cdf((true_diff + margin) / math.sqrt(var / n) - Z(0.975))


def half_width(discordant: float, n: int) -> float:
    """The expected half-width of the 95 % CI of a paired difference at `n` questions."""
    return Z(0.975) * math.sqrt(discordant / n)


def power_table(discordances: Sequence[float], sizes: Sequence[int]) -> dict[str, Any]:
    return {
        f"{d:.2f}": {
            "n_no_worse_at_-5_if_equal": n_noninferiority(d),
            "n_no_worse_at_-5_if_-2": n_noninferiority(d, true_diff=-0.02),
            "n_detect_a_-5_drop": n_detect(d),
            "half_width_points": {str(n): round(100 * half_width(d, n), 1) for n in sizes},
            "power_no_worse_if_equal": {str(n): round(power_no_worse(d, n), 2) for n in sizes},
        }
        for d in discordances
    }
