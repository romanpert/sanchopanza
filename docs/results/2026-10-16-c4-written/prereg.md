# C4: A5's `unrelated` gate on fa-17's kinds of pair (pre-registration, DRAFT)

Status: **draft, not sealed.** Before the seal: an independent `revisor-prereg` review against
the code, then `python benchmarks/facts_gate/written_run.py seal` writes `prereg.sha256` (the
sha256 of this file and of `c4-written-run.cmd`, its two local values read as placeholders).
Instrument commit: `ba632bc7ba2fbbdf2a5dc60d7377c8bad5009462`.

## Question

A5 (docs/results/2026-10-16-a5-unrelated/) found that accepting `unrelated` below the shipped
confidence gate when it is the top option at probability >= 0.65 (`decide_facts(...,
unrelated_at=0.65)`) added 39 verdicts, all right, on 1,500 templated pairs. It licensed a
proposal, not the change: that batch's `agree` and `conflict` pairs were easy restatements, and
the only wrong verdict the gate ever made on the recordings, fa-17 (`benches/graph.jsonl`: "El
nuevo Codigo Penal entro en vigor el 3 de agosto de 2026." against "La Ley 74-25 se promulgo el
3 de agosto de 2025.", `agree`, read as `unrelated` at 0.63 and 0.59), had no pair of its kind
there. Does the gate still meet A5's rule on a batch built of that kind?

## The batch (`benchmarks/facts_gate/written.py`, `written.jsonl`)

1,500 pairs over invented entities, Spanish and English alternating, seed 20261017, sha256
`a589a5d25d025390af8071b80129670a2b129ee003a54f3721e445da246207b9` (LF text); `paid` and
`report` refuse another file.

| kind | what the two facts say | agree (150) | conflict (150) |
|---|---|---|---|
| `dated` | two dated events of one entity that must come in order: enacted then in force, works begun then opened, signed then ratified, born then died, launched then withdrawn, founded then dissolved | the second date after the first | the second before the first |
| `role` | first appointed to a role in one year; in another year, holding it, did something | the act in or after the appointment year | the act before it |
| `subset` | a total, and how many of that total have a property (damaged homes and badly damaged ones, students and foreign students, ...) | the part smaller than the total | the part larger |

and **600 `unrelated` controls**: two facts about the same entity that no values could make
contradict (a law's date and its number of articles, a person's birth and the languages she
speaks, an earthquake's damaged homes and its length in seconds, ...), the shape where A5 found
the gate's added verdicts. Mix 40 / 30 / 30, A5's and the fifth batch's. Numbers from 1,000 up
carry the language's thousands separator, all of them.

**Two names for one entity, as fa-17.** In the three `dated` domains that have a second name (a
law, a bridge, a company), half the pairs name the entity two ways, the identity stated in the
fact with the first event ("La Ley 315, el nuevo código de aguas, se promulgó el ..." / "El nuevo
código de aguas entró en vigor el ..."): **83 of the 300 `dated` pairs** (36 `agree`, 47
`conflict`). After the random order of the two facts the identity sits in `fact_a` in 55 of them
and in `fact_b` in 28 (`identity_in` in each case).

**The label rule, checkable by hand.** Two facts that constrain each other are `agree` when
their values respect the constraint and `conflict` when they break it (then they cannot both be
true as stated: the question's own definition). Each case stores the values it was built from,
and `tests/test_facts_written.py` checks every label against them. No label comes from a model.
The rule reads fa-17's label (`agree`) as the owner wrote it, and that is the primary scoring.
The question's own wording ("`unrelated`: different attributes ... and neither supports nor
contradicts the other") admits `unrelated` for a consistent pair of dated events and for a role
and an act done in it, so a **second reading**, sealed here, scores the same answers without the
300 `dated` and `role` `agree` pairs (1,200 cases). A "does not beat" that the second reading
turns into "beats" is a disagreement about those labels, not a wrong verdict of the gate, and is
reported as such (`label_disagreement_only`). Tests read every value back from the text of all
1,500 cases and check that both facts name the same entity.

## Calls and the gate

One call per case: the shipped question (`entities.fact_questions`, point `facts`, jev-1.13.0),
recorded in `fixtures/c4-written/recording.jsonl` (keys and probabilities, no text). The gate is
not derived: it is A5's, **0.65**, applied in code to the same answers (`run.answered`), with the
shipped policy and every gate of A5's family beside it.

## Verdict rule (A5's, applied by `written_run.py report` through `run.verdict`, as written)

Added verdicts are the cases the shipped policy leaves undecided and the gate decides.

0. **Not run or partial.** No case answered: **"no verdict: not run"**. Once no launch is left,
   more than 2 % of the cases unanswered (more than 30): **"partial: N cases unanswered, no
   verdict"**. With 2 % or fewer, the rules below apply to the answered cases only, and the
   number left out is reported.
1. Fewer than 16 added verdicts: **"undecided: too few cases in the band to reach the target"**.
2. No added verdict on a `conflict` pair (no missed conflict) and the Wilson 95 % lower bound of
   their precision (right = labelled `unrelated`), unrounded, >= 0.80: **"the gate beats the
   shipped policy"**.
3. Otherwise **"the gate does not beat the shipped policy"**.

The second reading applies rules 1-3 to the 1,200 cases without `dated` and `role` `agree` pairs.

What each licenses. Rule 2 completes A5's proposal: `unrelated_at=0.65` may become
`decide_facts`' default at jev-1.13.0 (the change itself is a separate commit, with
`relate_facts`' docs and the CHANGELOG). Rule 3 keeps the default at `None` and names, in
`related_kinds`, which kind the gate turned into `unrelated`. Rule 1 says the band was too thin
here. Reported, not voted: per kind and label, the pairs the gate turns into `unrelated` with the
Wilson 95 % upper bound of that rate, and the shipped policy's own wrong and undecided verdicts
(an `agree` read confidently as `unrelated` is the shipped policy's, which no `unrelated` gate
changes); every gate of the family.

## Limits, stated before the run

- Templated text, like A5's: 3 kinds x 6 domains x 2 languages. The added verdicts are not
  independent draws; the Wilson bound treats them as such.
- The `unrelated` controls are not A5's shapes; their band may differ from A5's 7.0 %.
- Only jev-1.13.0.

## Power (`written_run.py power`, A5's formula)

A5's real band was 39 of 560 same-entity pairs, **7.0 %**. With every related pair kept out of
the band, the 600 controls add about 39-42 verdicts at bands of 6.5-7 %, and "beats" comes out
with probability **0.57-0.62 at a true precision of 0.93 and 0.76-0.80 at 0.95**; at 8-12.5 %
(48-75 added) 0.70-0.90 and 0.87-0.98. Each wrong verdict on a related pair lowers the
precision; a single one on a `conflict` pair decides rule 3. This run is a check, not a powered
test of a small effect: at A5's band a "does not beat" from too few right verdicts is likely
even if the gate is fine, and is read with the per-kind table.

## Cost and caps

1,500 calls of two short sentences. `CappedDecider`'s estimate: 0.019 USD; at the 71 micro-USD
median request: 0.107 USD; at A5's settled 23 micro-USD a call: **about 0.035 USD expected**.
Ledger dollars are each call's input tokens x 0.042 USD per million, not TypeSafe's bill; check
the TypeSafe balance by hand before the launch.

**One ledger for the round.** C4, C5 and C6 share the round's Jev budget in one ledger file,
`C:/sp-runs/w17-jev/ledger.json` (`benchmarks/w17_round.py`; no variable moves it): **6.00 USD
over the three lots**, and this lot's batch `c4-written` capped at **0.15 USD** in it
(`SpendLedger` refuses any call past either). `paid` refuses unless the larger estimate fits in
both what this batch has left and what the round has left (`paid_once.room`). The
`jev-preflight` call (about 13 micro-USD) is outside the ledger. Claude: 0.

`paid` refuses, before the key is read, unless: the seal matches this file and the launcher; HEAD
descends from the instrument commit and `src/`, `benchmarks/paid_once.py`,
`benchmarks/facts_gate/`, `benchmarks/thresholds.py` and `benchmarks/w17_round.py` are identical
to it, nothing uncommitted under them (the launcher is not an instrument path: the seal fixes it,
its two local values read as placeholders, so a filled copy passes); the cases have their hash;
the launch rule allows a launch (one launch and at most one relaunch, none after an HTTP 402, a
429, the cap or an answer from another model); on a first launch no recording exists; no other
`paid` of the lot holds its lock. Then, in one event loop, `jev-preflight`, the live client
(`JevDecider`, its own retries of 429 and 529 turned off: no call is asked twice) and every
missing call once, in order; the first refusal, failure, empty answer or answer from another
model stops it, and the stop is written (`launches.jsonl`). While a relaunch is allowed,
`report` refuses with cases unanswered; after it, rule 0 applies.

**Launch.** From a `git worktree add --detach` at the seal commit, by WMI in its own process group
(`CreateFlags=512`), outside any Claude Code session; the launcher refuses to start between
00:00 and 08:00. It takes a few minutes (A5: 5.7). Stopped only by PID.
