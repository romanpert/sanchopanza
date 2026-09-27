# Pre-registration: the errors of `verify_edge` and `relate_facts`, and what may change

Written 2026-09-27, before `benchmarks/edge_facts_errors.py` computes anything and before any
threshold or wording is derived. `prereg.sha256` holds the sha256 of this file with CRLF
normalised to LF; `tests/test_edge_facts.py` fails if it changes. Free: recordings only.

## What has already been looked at, and therefore is not evidence

Before this file, the recorded answers of the 50 `edge` and 50 `facts` cases
(`benches/graph.jsonl`, `graph-c.jsonl`, replayed from `fixtures/fourth-batch.jsonl`) were
printed and read case by case. Two candidate changes came out of that reading:

- `facts`: accept `unrelated` when it is the top option at p >= 0.5, keeping the shipped gate
  (`confidence >= relax`) for `agree` and `conflict`. It was scored informally on every
  recording of the same 50 cases (fourth batch, the first recording, the direction-first
  re-recording, the three option-order arms).
- `edge`: a `direction` cut of about 0.88-0.90 for committing, from `ed-26`.

It was also observed that a Choice answer's `confidence` equals `(p_top - 1/k) / (1 - 1/k)`
within the rounding of the reported probabilities, the Choice analogue of the Truth identity
`confidence = |2p - 1|`.

## Data available, and the consequence

Every recording of these two points covers the same 50 + 50 cases. No recorded case of either
point is unseen. A split by case (ed-01..20 against ed-21..50, fa-01..20 against fa-21..50) is
still a split by batch, but both halves were read above, so it cannot serve as the held-out
check the repository requires.

**Therefore no threshold, policy or question wording changes in code in this analysis.** This
is decided here, before the numbers below are computed, whatever they turn out to be.

## What the script computes (descriptive only)

1. `edge`: committed edges and the wrong ones; for each wrong commit, `stated` and `direction`;
   the smallest `direction` among right commits; `reversed` caught of 11; cases with no literal
   mention of subject or object (decided in code, never asked). The Wilson 95 % lower bound of
   commit precision now, and on ed-21..50 under a `direction` cut of 0.88: whether the 80 %
   target of `benchmarks/thresholds.py` would even be reachable there.
2. `facts`, on each recording: decided, right and costly (an `agree` / `conflict` confusion),
   under the shipped policy and under the `unrelated`-at-0.5 rule.
3. The Choice identity over every recorded Choice answer, maximum deviation by option count.

## What would license a change later (the fifth batch)

A batch written before it is measured: 30 `facts` cases (12 `unrelated`, 9 `agree`, 9
`conflict`) and 30 `edge` cases (12 `reversed`, of which at least 6 in passive voice, 12
`supported`, 6 `unsupported`), labels fixed before any answer exists. Asked twice each: the
shipped questions, and a variant with examples on `unrelated` (facts) or a `direction`
question phrased for actions as well as possession (edge). About 120 calls, ~0.003 USD of Jev.

- `facts` policy: ship the `unrelated`-at-0.5 rule iff, on the new batch with the shipped
  question, it agrees with more labels than the shipped policy and makes no more costly errors.
- `facts` wording: ship the examples iff the same holds for the new question against the old,
  both under the shipped policy.
- `edge` wording: ship the new `direction` question iff it catches more `reversed` and commits
  no more wrong edges.
- `edge` threshold: a `direction` cut moves only by `benchmarks/thresholds.py` (derive on one
  batch to a precision target on the Wilson lower bound, report on another), never on one case.
