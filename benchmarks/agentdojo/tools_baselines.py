"""The selector against the baselines the platform gives away for free.

    python benchmarks/agentdojo/tools_baselines.py   # free, nothing is called

Before claiming that a calibrated decision is worth 29 millionths per group, check what you
get for nothing. The Anthropic API ships a **tool search tool** in two flavours,
`tool_search_tool_bm25_20251119` and `tool_search_tool_regex_20251119`: tools are declared
with `defer_loading: true` and the model retrieves the ones it needs, with the discovered
schemas **appended rather than swapped**, so the prompt cache survives. That is the same
cache-safety property this package's fourth invariant claims for itself.

So the honest question is not "does `select_tools` work" - `../../docs/results/2026-09-24-tools/`
already answered that - but "does it beat BM25 over the same catalog". This file answers it
on the same 97 tasks with the same derived ground truth, with no model call on either side:
the selector's choices are replayed from its results file and BM25 is computed here.

BM25 is implemented in thirty lines rather than pulled in, so the comparison has no hidden
tuning: k1=1.5, b=0.75, the standard defaults, over the group name plus its description -
exactly the text the selector is shown.

**What this comparison is and is not.** BM25 at a fixed k is not the tool search tool: the
real thing is called by the model mid-conversation, with the request and its own reasoning as
the query, and it can search more than once. This measures the retrieval quality of a lexical
match over the same catalog given the same request text, which is the part that can be
compared offline. Where the platform's version is likely better is that the model can search
again after learning something; where it is structurally worse is that each search is a round
trip the selector does not need, and it happens after the first request rather than before it.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tools_bench import GROUPS  # noqa: E402

RESULTS = pathlib.Path("docs/results/2026-09-24-tools/results.json")
WORD = re.compile(r"[a-z0-9]+")


SUFFIXES = ("ing", "ies", "es", "ed", "s")


def stem(word: str) -> str:
    """Crude suffix stripping, because a baseline that loses on plurals is not a baseline.

    The first run of this file had no stemming and BM25 scored 30/97 at top-3, with failures
    like "who else is invited to the Networking **event**" against a group described as
    "calendar **events**". That is the same mistake made earlier the same day against a
    keyword injection baseline, where two patterns lost on the benchmark's own typo. A
    baseline is only evidence if it was given its best shot.
    """
    for suffix in SUFFIXES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in WORD.findall(text.lower())]


class BM25:
    """Standard BM25 over the catalog's group descriptions. k1=1.5, b=0.75, no tuning."""

    def __init__(self, documents: dict[str, str], k1: float = 1.5, b: float = 0.75) -> None:
        self.names = list(documents)
        self.docs = {n: tokens(t) for n, t in documents.items()}
        self.k1, self.b = k1, b
        self.avg = sum(len(d) for d in self.docs.values()) / max(len(self.docs), 1)
        n = len(self.docs)
        appears = Counter(term for d in self.docs.values() for term in set(d))
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in appears.items()}

    def score(self, query: str) -> dict[str, float]:
        q = tokens(query)
        out: dict[str, float] = {}
        for name, doc in self.docs.items():
            counts = Counter(doc)
            length = len(doc)
            total = 0.0
            for term in q:
                if term not in counts:
                    continue
                f = counts[term]
                total += self.idf.get(term, 0.0) * (
                    f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
                )
            out[name] = total
        return out

    def top(self, query: str, k: int) -> set[str]:
        ranked = sorted(self.score(query).items(), key=lambda kv: -kv[1])
        return {n for n, s in ranked[:k] if s > 0} or {ranked[0][0]}


def main() -> int:
    rows = [r for r in json.loads(RESULTS.read_text(encoding="utf-8")) if "_cost_usd" not in r]
    bm25 = BM25({n: f"{n} {about}" for n, (about, _m) in GROUPS.items()})

    print("Survival = every group the task actually needs is still there.")
    print("The selector keeps a variable number of groups; BM25 needs a fixed k, so k sweeps.\n")
    print(f"{'selector / baseline':<26}{'survives':>12}{'rate':>8}{'mean groups kept':>20}")
    ok = sum(1 for r in rows if r["survived"])
    kept_mean = sum(len(r["kept"]) for r in rows) / len(rows)
    rate = ok / len(rows)
    print(f"{'sanchopanza select_tools':<26}{ok}/{len(rows):<7}{rate:>8.0%}{kept_mean:>20.1f}")
    for k in range(1, 7):
        survived = 0
        for r in rows:
            chosen = bm25.top(r["purpose"], k)
            if set(r["needed"]) <= chosen:
                survived += 1
        r = survived / len(rows)
        print(f"{'BM25, top-' + str(k):<26}{survived}/{len(rows):<7}{r:>8.0%}{k:>20}")

    # The interesting cut: where each one fails.
    print("\nTasks the selector keeps but BM25 top-3 loses, and the reverse:\n")
    only_bm25 = only_sel = both = neither = 0
    examples = []
    for r in rows:
        chosen = bm25.top(r["purpose"], 3)
        b = set(r["needed"]) <= chosen
        s = r["survived"]
        if s and not b:
            only_sel += 1
            examples.append(("selector only", r))
        elif b and not s:
            only_bm25 += 1
            examples.append(("BM25 only", r))
        elif b and s:
            both += 1
        else:
            neither += 1
    print(
        f"  both survive: {both}   selector only: {only_sel}   "
        f"BM25 only: {only_bm25}   neither: {neither}"
    )
    for label, r in examples[:8]:
        print(f"  [{label:13}] needs {r['needed']} - {r['purpose'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --- A 250-group catalog, which is the case the point was written for ------------------
#
# `points/tools.py` cites a production agent binding 250 schemas at 25-38k tokens per step.
# The AgentDojo catalog is 16 groups, so the selector has never been tried at the scale it
# exists for. `--wide` pads the catalog with realistic distractor groups drawn from domains
# an enterprise harness actually carries, keeps the ground truth unchanged (a padded group is
# never needed), and re-runs the selection. Chunking kicks in above GROUPS_PER_CALL = 48, so
# this also exercises the merge path, which no bench has touched either.
