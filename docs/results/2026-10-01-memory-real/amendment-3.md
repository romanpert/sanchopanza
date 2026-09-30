# Amendment 3: memory v5 (the name gate at a first prompt) against v4.1 on a third fresh set

Written 2026-10-01, before any item of the third set was built or scored. Sealed with the code
it names (`amendment-3.sha256`); the items are built and scored once, by `confirm_v5.py`.

## Why

v4.1 confirmed that the touch is where memory pays. What is left of the noise is at a session's
first request: with a decider, BM25 proposes five records and those at 0.8 or above enter. On
the fresh set of amendment 2 that step added no recall at first requests and raised their
noise.

## What v5 changes (designed on data already seen, declared)

At a session's first prompt (`MEMORY_PROMPT=first`, the default with a decider), a candidate
that changed files enters only if the prompt names one of them: its base name, or its stem when
at least four characters, not touched by an ASCII name character (so a sentence's full stop or
text in a script without spaces may follow), any case, NFC (`memory_hook.named_in`). A record
that changed nothing (a question, an investigation, a plan) is judged as in v4.1: the labels
cannot call such a record related, so the gate does not touch it. The decider still judges the
five together; it is not asked when no candidate could enter. `MEMORY_PROMPT_NAMED=off` restores
v4.1. Nothing changes without a decider, with `MEMORY_PROMPT=every`, or in the touch.

An adversarial review of the first version found that it removed change-less records the
metric could never credit (H1), missed names before a full stop and in CJK or Korean text
(H2, H3), and was measured on prompts cut to 1,000 characters while the hook reads them whole
(M1), with one record counted that was never shown (M2). All fixed before these numbers.

Replayed through the hook's code (`replay_v5.py`), each session's first prompt whole from its
transcript, all requests, `lineage or file`, recall / precision / noise:

| set | v4.1 | v5 | first-request noise | decider calls |
|---|---|---|---|---|
| development (953) | 0.938 / 0.736 / 0.037 | 0.938 / 0.744 / 0.034 | 0.170 -> 0.149 | 114 -> 102 |
| held out 1 (1,490; used for v3, never for this question) | 0.950 / 0.737 / 0.030 | 0.950 / 0.740 / 0.030 | 0.108 -> 0.108 | 103 -> 91 |
| held out 2 (3,117; used to confirm v4.1) | 0.978 / 0.761 / 0.043 | 0.978 / 0.768 / 0.042 | 0.154 -> 0.138 | 277 -> 247 |

The effect is small and never negative. With `lineage` only, held out 2: recall 0.876 -> 0.871
(one request of 209). What the decider adds at a first prompt at all is small: against the
touch alone it recovered one request on development and none on the two held-out sets.
Measured with the whole prompt, v4.1's own figures differ from those published with it
(held out 2: precision 0.761, not 0.753; first-request noise 0.154, not 0.170).

Other conditions measured on development and held out 1 and not taken (`v5_first.py`, first
version of the gate, prompts as items keep them): a cut of 0.9 or 0.95, prompts of at least 80
or 200 characters, the name alone without the decider, recall at a prompt off.

## The third set (`selection-3.json`, `select_v5.py`, seed 20261003)

SWE-chat has no eligible group left outside selections 1 and 2. This set takes, per used group,
one run of at least two consecutive sessions none of which was in a window (a window of up to
six from a seeded start), and every group of exactly two sessions: 101 groups (82 outside a
window, 19 of two sessions), 430 sessions. **The 82 are the same people and repositories as
data already seen**, on sessions nobody has built, read or scored; nothing in v5 was tuned per
person or repository. Transcripts fetched under a 1.5 GB cap in code.

## Arms

Both through the hook's code, the same touch, the same prompts (whole), the same cached decider
answers (asked once per first request with candidates, capped at 0.50 USD in code):

- **v5**: `SANCHOPANZA_MEMORY_PROMPT_NAMED=on` (the default).
- **v4.1**: `SANCHOPANZA_MEMORY_PROMPT_NAMED=off`.

## Success (all four; all requests, `lineage or file`, unless named)

v5 is a change that should be no worse anywhere and better somewhere:

1. Not worse at first requests, better in one: v5 first-request noise <= v4.1's and v5
   first-request precision >= v4.1's, with at least one of the two strictly better.
2. v5 recall >= v4.1 recall - 0.005.
3. v5 precision >= v4.1 precision and v5 noise <= v4.1 noise.
4. v5 recall >= 0.80, precision >= 0.50, noise <= 0.10.

Reported, not criteria: `lineage` only, touch alone, decider calls per arm, the two kinds of
group apart.
