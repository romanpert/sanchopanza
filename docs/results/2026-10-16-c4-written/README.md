# A5's `unrelated` gate on fa-17's kinds of pair (C4)

**The result:** on 1,500 new pairs built of the one kind the gate had ever got wrong, accepting
`unrelated` below the shipped confidence gate when it is the top option at probability >= 0.65
(`decide_facts(..., unrelated_at=0.65)`) **beats the shipped policy under the sealed rule**. It
added 66 verdicts, all 66 right, none of them a missed conflict; Wilson 95 % lower bound
**0.945**. It added no `unrelated` to any of the 900 related pairs: two dated events, a role
and an act, a figure and its subset.

This completes the proposal A5 licensed (docs/results/2026-10-16-a5-unrelated/): `unrelated_at=0.65`
may become `decide_facts`' default at jev-1.13.0.

Pre-registered in `prereg.md`:
- instrument commit `319ee79`, sealed in `3a201f0`;
- `prereg.sha256` holds the hash of `prereg.md` (`491183ef…`) and of `c4-written-run.cmd`;
- reviewed twice by `revisor-prereg` against the code before the seal.

Run on 2026-10-16 from a detached worktree at the seal commit, started outside the session
(WMI). The launch started at 18:34:04 and its report was written by 18:40:46. Jev (`jev-1.13.0`) answered
**1,500 of 1,500** calls on the first launch, with no relaunch, no unanswered case and no
refusal. The round's shared ledger settled **0.0350 USD** for this batch, under its 0.15 cap
(23 micro-USD a call; median latency 218 ms). Claude: 0.

## The question

A5's batch had easy `agree` and `conflict` pairs: one value restated, or two plainly different
values. The only wrong verdict the gate had made on the recordings was fa-17 (`benches/graph.jsonl`):
"El nuevo Codigo Penal entro en vigor el 3 de agosto de 2026." against "La Ley 74-25 se promulgo
el 3 de agosto de 2025.", labelled `agree` and read as `unrelated` at 0.63 and 0.59. Does the gate
still meet A5's rule on a batch built of that kind?

## What ran

- **Cases** (`benchmarks/facts_gate/written.py`, `written.jsonl`, sha256 `a589a5d2…`): 1,500
  pairs over invented entities, Spanish and English alternating, labels that follow from the
  values stored with each case.

  | kind | the two facts | `agree` (150) | `conflict` (150) |
  |---|---|---|---|
  | dated | two dated events of one entity that must come in order | the second after the first | the second before the first |
  | role | first appointed to a role; later, holding it, did something | the act in or after the appointment year | the act before it |
  | subset | a total, and how many of it have a property | the part smaller | the part larger |

  Plus 600 `unrelated` controls: two facts about one entity that no values could make
  contradict. 83 of the 300 dated pairs name the entity two ways, as fa-17 does.
- **Calls:** one per case, the shipped question, point `facts`. Every gate is applied in code to
  the same answers.

## The verdict, by the sealed rule

| Condition (prereg) | Needed | Measured |
|---|---|---|
| Cases unanswered | at most 2 % | **0** |
| Added verdicts at 0.65 | at least 16 | **66** |
| Missed conflicts among them | 0 | **0** |
| Wilson 95 % lower bound of their precision (unrounded) | >= 0.80 | **0.945** (66 of 66 right) |

**The gate beats the shipped policy.**

The sealed second reading leaves out the 300 consistent `dated` and `role` pairs (`agree`),
whose label the question's wording could read as `unrelated`. It gives the same 66 of 66: none
of those pairs entered the band, so no label disagreement arises (`label_disagreement_only`:
false).

## The related pairs (`related_kinds`)

| kind: label | pairs | gate's `unrelated` added | shipped policy wrong | shipped policy undecided |
|---|---|---|---|---|
| dated: agree | 150 | 0 | 0 | 0 |
| dated: conflict | 150 | 0 | 0 | 53 |
| role: agree | 150 | 0 | 0 | 0 |
| role: conflict | 150 | 0 | 0 | 0 |
| subset: agree | 150 | 0 | 0 | 1 |
| subset: conflict | 150 | 0 | 7 | 21 |

- **The gate added nothing to the 900 related pairs.** That is 0 of 900, Wilson 95 % upper
  bound 0.4 %, and 2.5 % in each cell of 150.
- **The shipped policy left 53 dated conflicts undecided** (35 % of them). The gate did not turn
  any of them into `unrelated`: when undecided, their top option was not `unrelated` at 0.65.
- **The shipped policy's own costly errors:** 7 subset conflicts read as `agree`, where the part
  is larger than the total. No gate on `unrelated` touches them.
- **The 83 pairs that name the entity two ways** (`two_names`): no added verdict whichever fact
  states the identity. In `fact_a`: 22 agree and 33 conflict, 7 of those undecided. In `fact_b`:
  14 and 14, 3 undecided.

## Every gate of the family (descriptive: only 0.65 was under test)

| `unrelated_at` | Added | Right | Missed conflicts | Wilson 95 % low |
|---|---|---|---|---|
| 0.40 | 120 | 119 | **1** | 0.954 |
| 0.45 | 119 | 119 | 0 | 0.969 |
| 0.50 | 119 | 119 | 0 | 0.969 |
| 0.55 | 114 | 114 | 0 | 0.967 |
| 0.60 | 98 | 98 | 0 | 0.962 |
| **0.65** | **66** | **66** | **0** | **0.945** |
| 0.70 | 26 | 26 | 0 | 0.871 |

The first missed conflict appears at 0.40. The lower gates were not the registered test and
license nothing.

## Where the added verdicts come from

The 66 are all `unrelated` controls: 34 from a bridge's start of works and its length, 30 from a
minister's appointment and the years of study, 2 from a university's enrolment and its library
hours. That is 11 % of the 600 controls, against A5's 7.0 %. Two domains hold 64 of the 66: the
verdicts are not independent draws, and the effective sample is smaller than the Wilson bound
assumes.

## The shipped policy on this batch

Decided 1,134 of 1,500, 1,074 of them right. It read 53 `unrelated` controls as confident
`agree`; as in A5, no gate on `unrelated` reaches those.

## What it licenses, and what it does not

- **Licensed:** `unrelated_at=0.65` as `decide_facts`' default (and so `relate_facts`') at
  jev-1.13.0. On pairs of fa-17's kind it added no wrong verdict and missed no conflict, and on
  the controls it added 66 right ones.
- **Not licensed:** any gate below 0.65, other models, or text beyond these templates.
- **Limits:**
  - 3 kinds x 6 domains x 2 languages of templated text.
  - The added verdicts are concentrated in two domains.
  - Only `jev-1.13.0`.

## Cost and clock

- **Cost:** 0.0350 USD on the round's shared ledger (batch `c4-written`, cap 0.15; the
  round's 6.00 over C4, C5 and C6). 1,500 calls, 832,361 input tokens, each priced at 0.042 USD per
  million: that is the ledger's figure, not TypeSafe's bill. The preflight call is outside it.
- **Clock:** about 7 minutes from launch to report.

## Reproducing

    python benchmarks/facts_gate/written_run.py report   # free, from fixtures/c4-written/recording.jsonl

`analysis.json` is the report the sealed run wrote; `tests/test_c4_c5_published.py` replays it
from the recording. The recording holds keys, token counts, costs and the probabilities of
`agree`, `conflict` and `unrelated`, no text. `launches.jsonl` holds the launch's start and end
lines.
