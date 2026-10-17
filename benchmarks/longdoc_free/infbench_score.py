"""∞Bench's official scorer for En.QA (`longbook_qa_eng`), vendored unchanged.

Copied from OpenBMB/InfiniteBench, `src/compute_scores.py` at commit
51d9b37b0f1790ead936df2243abbf7f0420e439 (file sha256
ef4b3d6144b41271866071b0d7da2073166b71ac74fac4deafcb6c26515f5d6b): `normalize_answer`,
`f1_score` and `qa_f1_score`, the three functions `get_score_one_longbook_qa_eng` calls, which
scores a prediction as `qa_f1_score(pred, label)` with no post-processing of the reply. Only the
module imports differ (the upstream file loads `evaluate`, `tqdm` and its argument parser for
other tasks). Token F1 after lower-casing and removing punctuation, articles and extra spaces,
the maximum over the references. tests/test_longdoc_free_score.py pins its behaviour.

MIT License

Copyright (c) 2023 OpenBMB

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# ruff: noqa
import re
import string
from collections import Counter


def normalize_answer(s: str) -> str:
    """Lower text and remove punctuation, articles and extra whitespace."""

    def remove_articles(text):
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def white_space_fix(text):
        return " ".join(text.split())

    def remove_punc(text):
        exclude = set(string.punctuation)
        return "".join(ch for ch in text if ch not in exclude)

    def lower(text):
        return text.lower()

    return white_space_fix(remove_articles(remove_punc(lower(s))))


def f1_score(prediction, ground_truth) -> tuple[float, float, float]:
    common = Counter(prediction) & Counter(ground_truth)
    num_same = sum(common.values())
    if num_same == 0:
        return 0, 0, 0
    precision = 1.0 * num_same / len(prediction)
    recall = 1.0 * num_same / len(ground_truth)
    f1 = (2 * precision * recall) / (precision + recall)
    return f1, precision, recall


def qa_f1_score(pred: str, ground_truths) -> float:
    """Computes the F1, recall, and precision."""
    f1 = 0
    prec = 0
    recall = 0
    for ground_truth in ground_truths:
        normalized_prediction = normalize_answer(pred)
        normalized_ground_truth = normalize_answer(ground_truth)

        prediction_tokens = normalized_prediction.split()
        ground_truth_tokens = normalized_ground_truth.split()
        scores = f1_score(prediction_tokens, ground_truth_tokens)
        this_f1, this_prec, this_recall = scores
        f1 = max(f1, this_f1)
        prec = max(prec, this_prec)
        recall = max(recall, this_recall)
    return f1
