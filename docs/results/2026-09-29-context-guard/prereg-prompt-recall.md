# Pre-registration (part 2, offline): recall at the prompt, the new prompt as the question

Written 2026-09-29, while part 1's paid run was in progress and before any decider call of this
part. Sha256 in `prereg-prompt-recall.sha256`.

## The question

When the person sends a new prompt after the conversation was compacted, a `UserPromptSubmit`
hook can add context (it cannot remove any: rewriting history each turn breaks the cached
prefix, measured at up to 4.15x the cost in docs/where-it-pays.md). Which lines of the
earlier, one-shot command output should it add, under a fixed character budget, with the new
prompt as the question? Is a Jev tournament (`Squire.triage_many`, the prompt as `purpose`)
better at it than free alternatives?

What is already known and sets the bar: on LongMemEval sessions the Jev gate did not beat BM25
top 3 on recall (0.725 against 0.851), and at equal text a cascade was not distinguishable
from BM25 over sentences (`2026-09-28-memory-gate`). Nobody has measured it on one-shot tool
output inside a coding session.

## Units

Every recorded phase A followed by a phase-B prompt: the 12 tasks of `2026-09-28-context-e2e`
(Haiku), the 7 Haiku tasks of `2026-09-28-context-lean`, and the phase A of this run's tasks
(part 1) as they exist when this part runs. Split: **test = this run's tasks** (new outputs,
never used to write any rule); dev = the other 19 (the guard's rules were tuned on them).

Candidates: every non-empty line of every at-risk result of phase A (`guard.at_risk`: shell
output that is not a test run, not the harness's own messages), with its command. Needed
lines: those holding a value phase B needs and phase A printed once: the release token
(all), the probe's code and tolerance (e2e and this run). The rule of this run is in a prompt,
not in output: out of scope here (the guard carries it verbatim).

## Arms, each at budgets B = 400 and 1,000 characters (lines joined)

- `recent`: the last lines of the latest outputs, newest first, while they fit.
- `bm25`: lines ranked by BM25 (`text.bm25_scores`) against the new prompt, best first.
- `rule`: the guard's line priority (`guard.ranked_lines`, focus = the new prompt), all lines
  of every output ranked together by (error, overlap, rarity), best first.
- `jev`: `Squire.triage_many(purpose=<new prompt>, pages=[(command, line), ...])`, lines kept by
  the decider first by probability, then the rest by BM25, while they fit. `jev-1.13.0`.

## Measures and decision rules

- Primary: share of units with **every** needed value inside the chosen text (test split).
- **P1**: `jev` >= `bm25` + 10 points at B = 400 on test. **P2**: `jev` >= `rule` + 10 points
  at B = 400 on test. Both at B = 1,000 reported, and dev, descriptively.
- Prediction, written now: the phase-B prompts name what they need ("release token",
  "tolerance", "error code"), so the lexical arms should be strong; P1 more likely fails than
  holds. If it fails, prompt recall ships free (BM25 or the rule), or not at all, and is not
  sold as a Jev capability.

## Budget

Jev: under 0.05 USD (a few hundred lines per unit, grouped 30 per call), inside the 0.10 USD
the owner approved for this iteration; decisions recorded and replayable. No model session.

## Amendment 1 (after the free arms, before any decider call): oblique prompts

The free arms hit the ceiling: with the phase-B prompts as written, `bm25` and `rule` hold every
needed value at 400 characters in 22 of 22 units (`recent`: 1 of 19 dev, 0 of 3 test). Those
prompts name what they need in the output's own words, so P1 and P2 cannot hold. A second,
harder condition is added, with the same arms, budgets and measure, and **replaces the primary
for P1 and P2** (the literal condition stays reported):

- `oblique_en`: "Finish the release: put the identifier the one-off issuing script gave us into
  the release module, and make the calibration check use the limit and the reference that the
  diagnostic run complained about."
- `oblique_es`: "Termina la publicacion: pon en el modulo de release el identificador que nos dio
  el script de un solo uso, y haz que la comprobacion de calibracion use el limite y la
  referencia de la que se quejo la ejecucion de diagnostico."

The same two prompts for every unit (the lean units need only the identifier). Written without
looking at any decider output. Prediction: BM25 falls on both (few shared words, none in
Spanish); the rule keeps what its error and rarity priorities find; P1 is the real test of a
semantic tournament here.

## Amendment 2 (before any decider call): shifted outputs, where a content rule should break

The owner's objection (2026-09-29): a piece built on fixed patterns (English error words, codes
with digits, line shapes) is not universal; the decider is there so that no such rule is
needed. The guard now has a `judge` chooser (`guard.pieces_of` + `guard.choose_by_judge`): every
line of every output that cannot be read again goes to one `triage_many` tournament with the
person's requests as the question; no pattern selects a line. It is added here as the arm
`judge` (the same function the hook runs), and one more condition tests universality:

- `shifted`: in every candidate line, the needed values and their wording are rewritten before
  any arm sees them. The token becomes a word code with no digit (`palabra-palabra-palabra`,
  fixed per unit from a seeded list), the probe code too (`ref-palabra-palabra`); the token
  line reads `identificador de publicacion: <code>`; the probe's failure line reads
  `La sonda se desvio <drift>, por encima del margen <tolerance> (referencia <code>)`, and
  `FAIL` becomes `MAL`. The prompt is `oblique_es`. Needed values follow the rewrite.

Criteria on `shifted`, test and dev pooled (the rule was tuned on neither form): **P3**:
`judge` >= `rule` + 20 points at B = 400; **P4**: `judge` >= `bm25` + 20 points at B = 400.
Prediction: the rule loses the token (no digit, no code shape) and keeps the probe line only by
rarity; BM25 finds little from the Spanish prompt. If P3 fails, the claim "the decider makes
the guard universal" is not made.

## Amendment 3 (after the free arms of amendment 2, before any decider call)

Seen in the free arms: the `shifted` wording shares words with `oblique_es` ("identificador",
"referencia"), so BM25 found every value (27 of 27 at 400): the condition tested lexical overlap,
not universality. Declared as a design error of amendment 2. Added, with everything else as
registered: **`shifted_en`**, the same shifted outputs with the `oblique_en` prompt (no shared
content word between prompt and value lines). P3 and P4 are judged on `shifted_en`; `shifted`
stays reported as run. Also seen and declared: the product's rule (`guard.choose`, with its
per-command headers inside the budget) holds every value at 400 characters in 7 of 27 units
on the literal prompts; the line-level variant measured before amendment 1 was not the
product's.

## Amendment 4 (after the first decider run, before any call of the second): the judge in two stages

First decider run, reported as run: line-level `triage_many` (every line a page, no context).
Its cap (0.08 USD) ran out after 6 of 27 units (planning figure 10x low: each call carries 30
lines); on those 6 dev units, at B = 400: `judge` 5/6 literal, 1/6 oblique_en, 4/6 oblique_es,
4/6 shifted, **0/6 shifted_en**; `cascade` 6, 5, 6, 4, 0. Rows after the cap are invalid for
`judge` and `cascade` and are not scored. Diagnosis: a line judged alone does not say which
command printed it or what it is for.

The owner stopped part 1 and asked to measure this properly, approving up to 0.40 USD of Jev.
`judge` becomes the shape the package already confirmed for long documents
(`select_passages`): stage 1, one `triage_many` over **blocks** of consecutive lines of each
output (at most 900 characters, titled by the command); stage 2, `select_sentences` over the
lines of every block stage 1 keeps, each line read inside its block (window 0), probabilities
as answered. A line's verdict is its stage-2 answer; lines of blocks not kept are not kept.
`cascade` = `guard.cascade_order` over these verdicts. Every unit and condition is re-run from
scratch (new recordings file); cap 0.40 USD. P1-P4 are judged on this run, test and dev
reported separately and pooled.

## Amendment 5 (after the two-stage run, before any call of this one): the cascade as a package

The owner's correction (2026-09-29): sanchopanza is a package, cheap deterministic layers first
and the decider as the final judge given well-designed questions; neither "only Jev" nor "only
rules". Reading the two-stage run against its code, before designing this amendment, found
three faults of the questions themselves, declared here because the redesign answers them
**after seeing where the decider failed** (it is not blind to amendments 1-4):

1. **The request never reached the decider.** `chunks.*_questions` cut `purpose` to 400
   characters, and `guard.JUDGE_PURPOSE` spent 301 of them on its preamble: about 95 characters
   of each prompt were read. In `oblique_en` the half asking for the probe's limit and reference
   was never sent, and the probe was found in 0 of 20 units by `judge` (the token in 28 of 28).
2. **Criteria from another domain.** The questions reused `triage.CONTRIBUTES` (pages answering
   a question: founders, rulings), not the reason command output is kept.
3. **A yes or no ranked inside a budget.** At 400 characters the order among kept lines decides.

Also found and fixed before this registration, with tests (`tests/test_context_keep.py`):
`guard.latest_only` dropped a one-shot tool's first output when both runs failed (a probe exits
with its error, then "already consumed"); duplicate lines of one output took room twice; and
the guard now says when Claude Code cut a shell output before the model saw it
(`guard.clipped_of`). The first two change the pool every arm draws from; the free arms of
this run are recomputed with them and compared with the recorded run.

### The arm `keep` (`context.keep`, questions in `points.keep`)

1. Plumbing: `guard.pieces_of` (unchanged). If the pool fits the budget, it all goes, no call.
2. The rule: `guard.choose` over `guard.candidates` (unchanged), free; what stands on failure.
3. The decider (`jev-1.13.0`): stage 1, one **Score** of four levels per block of output
   (blocks of at most 900 characters titled by their command, up to 12 per call, all in view);
   stage 2, one Score per line for the best `DEEP_BLOCKS` = 4 blocks at `MAY` = 1.5 or more,
   each line read in its block. The person's requests go **in full** in their own state field
   (up to 2,400 characters), the judgment in the instructions; the four levels describe
   situations (nothing needed / background or re-readable / a value that might be used / an
   exact value the requests point to that exists only here), each with examples from domains
   no measured task uses. An optional `notes` field (the native summary after a compaction) is
   not exercised offline: no unit has a summary at that point.
4. Order: lines scored `MUST` = 2.0 or more, best first; then the rule's lines; then lines at
   `MAY` or more. Nothing else enters. `MUST`, `MAY` and `DEEP_BLOCKS` are fixed here, a priori
   (level 2 = "a value that might be used"), not fitted on any decider output.

### Conditions

- Seen before (reported, never decisive): `literal`, `shifted_en`.
- **New, written with this amendment** (primary): `json_en`: every needed line rewritten as a
  JSON record with new wording and word codes (`{"event": "grant", "handle": "<w-w-w>"}`;
  `{"level": "error", "msg": "sensor spread above allowance", "spread": d, "allowance": T,
  "ticket": "tk-<w-w>"}`), with a new prompt sharing no content word with those lines ("Wrap
  up: put the identifier we were issued earlier into the release module, and make the
  calibration check use the threshold and the reference that the diagnostic run reported.");
  `vague`: the original outputs and the prompt "Carry on with the remaining steps of the task."
  (the request names nothing: only the criteria can find the values).
- **Declared**: a free smoke run of the script (a fake decider, no network) printed the free
  arms on the new conditions before this text was hashed: at 400 characters `json_en` bm25 0/28,
  rule 0/28, recent 0/28; `vague` rule 7/28, bm25 0/28, recent 0/28 (at 1,000: rule 27/28 on
  `vague`). No decider answer on either new condition has been seen.

### Arms and budget

`recent`, `bm25`, `rule` (free), `keep` on the four conditions; the earlier two-stage `judge`
on the two new conditions only (the baseline for "the redesign matters"). Scores computed once
per unit and condition, fitted at 400 and 1,000. Recordings in
`prompt-recall-keep.jsonl`. Planning estimate 0.16 USD (about 0.03 per condition for `keep`,
0.04 for `judge`); **cap 0.19 USD**, inside the 0.217 left of the 0.40 approved. Rows after the
cap are marked and not scored for the arm that ran out.

### Decision rules (new conditions pooled, 56 units, at 400 characters)

- **P5**: `keep` >= `bm25` + 20 points. **P6**: `keep` >= `rule` + 20 points.
- **P7**: `keep` >= `judge` + 10 points (the redesign of the questions matters).
- **P8** (no harm, `literal`, 28 units): `keep` >= `bm25` - 2 units.
- Descriptive: each new condition alone, test and dev, 1,000 characters, `shifted_en`.

**Predictions, written now.** `vague`: the level-3 criteria match an issued value and a
failure's reference, so `keep` should find both where the rule finds the probe but not the
token; P6 likely holds there. `json_en`: uncertain; the values sit in records whose keys name
nothing the prompt says. If P5-P7 fail, the claim stays as after amendment 4: the decider
chooses better than rules when the request is clear and the budget tight, and it does not make
the guard universal.
