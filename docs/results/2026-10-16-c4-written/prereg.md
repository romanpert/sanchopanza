# C4: A5's `unrelated` gate on fa-17's kinds of pair (pre-registration, DRAFT)

Status: **draft, not sealed.** Before the seal: an independent `revisor-prereg` review against
the code, then `python benchmarks/facts_gate/written_run.py seal` writes `prereg.sha256` (the
sha256 of this file and of `c4-written-run.cmd`, its two local values read as placeholders).
Instrument commit: `40097b5f13a995c4dfa67a7c026b1d461b3955ff`.

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
`44351330b80dd172cd7aa75a4c33252e0eeb638cedf216cbdd7e1fcf81e601d8` (LF text); `paid` and
`report` refuse another file.

| kind | what the two facts say | agree (150) | conflict (150) |
|---|---|---|---|
| `dated` | two dated events of one entity that must come in order: enacted then in force, works begun then opened, signed then ratified, born then died, launched then withdrawn, founded then dissolved | the second date after the first | the second before the first |
| `role` | first appointed to a role in one year; in another year, holding it, did something | the act in or after the appointment year | the act before it |
| `subset` | a total, and how many of that total have a property (damaged homes and badly damaged ones, students and foreign students, ...) | the part smaller than the total | the part larger |

and **600 `unrelated` controls**: two facts about the same entity that no values could make
contradict (a law's date and its number of articles, a person's birth and the languages she
speaks, an earthquake's damaged homes and its length in seconds, ...), the shape where A5 found
the gate's added verdicts. Mix 40 / 30 / 30, A5's and the fifth batch's. Half the `dated` pairs
name the entity two ways, as fa-17 does, with the identity stated in the first fact ("La Ley 315,
el nuevo código de aguas, se promulgó el ..." / "El nuevo código de aguas entró en vigor el
...").

**The label rule, checkable by hand.** Two facts that constrain each other are `agree` when
their values respect the constraint and `conflict` when they break it (then they cannot both be
true as stated: the question's own definition). Each case stores the values it was built from,
and `tests/test_facts_written.py` checks every label against them. No label comes from a model.
The rule reads fa-17's label (`agree`) as the owner wrote it; a reviewer who reads a consistent
dated pair as `unrelated` should say so before the seal, since the verdict counts the gate's
`unrelated` on such a pair as wrong.

## Calls and the gate

One call per case: the shipped question (`entities.fact_questions`, point `facts`, jev-1.13.0),
recorded in `fixtures/c4-written/recording.jsonl` (keys and probabilities, no text). The gate is
not derived: it is A5's, **0.65**, applied in code to the same answers (`run.answered`), with the
shipped policy and every gate of A5's family beside it.

## Verdict rule (A5's, applied by `written_run.py report` through `run.verdict`, as written)

Added verdicts are the cases the shipped policy leaves undecided and the gate decides.

1. Fewer than 16 added verdicts: **"undecided: too few cases in the band to reach the target"**.
2. No added verdict on a `conflict` pair (no missed conflict) and the Wilson 95 % lower bound of
   their precision (right = labelled `unrelated`), unrounded, >= 0.80: **"the gate beats the
   shipped policy"**.
3. Otherwise **"the gate does not beat the shipped policy"**.

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
- The `unrelated` controls are not A5's shapes; their band may differ from A5's 7 %.
- Only jev-1.13.0.

## Power (`written_run.py power`, A5's formula)

With every related pair kept out of the band, the 600 controls add about 48-75 verdicts at A5's
band of 8-12.5 %, and "beats" comes out with probability 0.70-0.90 at a true precision of 0.93,
0.87-0.98 at 0.95. Each wrong verdict on a related pair lowers the precision; a single one on a
`conflict` pair decides rule 3.

## Cost and caps

1,500 calls of two short sentences. `CappedDecider`'s estimate: 0.019 USD; at the 71 micro-USD
median request: 0.107 USD; at A5's settled 23 micro-USD a call: **about 0.035 USD expected**. Hard
cap **0.15 USD** in the ledger at `~/.cache/sanchopanza/c4-written/ledger.jsonl`; `paid` refuses
unless the larger estimate plus what the ledger holds fits under it. Claude: 0.

`paid` refuses, before the key is read, unless: the seal matches this file and the launcher; HEAD
descends from the instrument commit and `src/`, `benchmarks/paid_once.py`,
`benchmarks/facts_gate/`, `benchmarks/thresholds.py` and `c4-written-run.cmd` are identical to
it, nothing uncommitted under them; the cases have their hash; the launch rule allows a launch
(one launch and at most one relaunch, none after an HTTP 402, a 429 or the cap); on a first
launch no recording exists; no other `paid` of the lot holds its lock. Then, in one event loop,
`jev-preflight`, the live client and every missing call once, in order; the first refusal,
failure, empty answer or answer from another model stops it. While a relaunch is allowed,
`report` refuses with cases unanswered; after it, an unanswered case is undecided under every
policy and counted (`unanswered`).

**Launch.** From a `git worktree add --detach` at the seal commit, by WMI in its own process group
(`CreateFlags=512`), outside any Claude Code session, never between 02:00 and 08:00. Stopped only
by PID.
