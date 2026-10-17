# Long documents with free-text answers: the router with a free BM25 pre-filter before Jev (dev2)

**Status: a second dev phase of the longdoc-free lot, run 2026-10-17; by its sealed rule no
cut qualifies, so the router is not confirmed and no confirmation is sealed.** The pre-filter
did what it was for on cost: Jev came to 0.0106 USD a question (the dev's 0.039), and at the
dev's cut the router would have cost 24 % less than Sonnet 5.5 alone. It lost on quality, by
the rule: Haiku 4.5 on the shortlisted passages scored 7 F1 points under the dev's Haiku on
the full passages (−7.0 [−15.5, +2.3]: observed, the interval crosses 0), and at the dev's cut
the router fell 9 points behind Sonnet (−9.0 [−20.2, +1.6], also crossing 0); only Haiku
against Sonnet over all 41 questions excludes 0 (−18.7 [−36.1, −5.8]). Sonnet 5.5 and Haiku
4.5 in clean Claude Code 2.1.287, Jev 1.13.0. Pre-registration `prereg-dev2.md`, sealed `09e30e8`
(`prereg-dev2.sha256`), instrument `1dc7691`.

## The question

The first dev (`../2026-10-16-longdoc-free/`) found the router 25 % dearer than Sonnet alone:
Jev's passage selection cost 0.039 USD a question, 0.037 of it a page tournament over the whole
novel. A probe of 3 questions (`../2026-10-17-lfree-bm25-dry/`) put a free BM25 shortlist of 200
pages before the tournament and measured 0.0115 USD a question. On the same 41 dev questions:
with the pre-filter, does the router (Jev's passages and Truth gate; Haiku 4.5 on the passages
where the gate's p reaches the cut, Sonnet 5.5 with the whole novel elsewhere) save money
against Sonnet alone without losing F1 beyond the dev's rule, and is a confirmation worth
sealing?

## Setup

- ∞Bench En.QA (`longbook_qa_eng`, revision `90f0394`), the dev's 41 questions on 8 whole
  novels, graded by ∞Bench's own `qa_f1_score` on the reply's `ANSWER:` line, as in the dev.
- **Jev (phase J2):** per question, the 200 pages of 900 characters that BM25 scores best for
  the question, in the novel's order; `select_passages` over them (`fit_chars=60000`, the free
  order); then the dev's gate, one Truth: "`passages` are excerpts of one novel. They state
  everything needed to answer `question`." Jev 1.13.0, no long context. One launch, every call
  answered (1,433 calls).
- **Claude Code**, every session one headless Claude Code 2.1.287 (pinned), a clean user and
  `CLAUDE_CONFIG_DIR` per session, the web taken away, the dev's prompt, in the dev's phases:
  a Sonnet smoke, then **N** (Sonnet 5.5, the whole novel, run again), then **H** (Haiku 4.5,
  J2's kept passages). **H0** (Haiku 4.5, the whole novel) and **HC** (closed book) are the
  dev's sessions, reused: they enter no R − N. All sessions ran on 2026-10-17, every one served
  by its model, none at its cap, every reply with an ANSWER line.

## Results (dev2, 41 questions; descriptive except the sealed reading below)

| Arm | Mean F1 (points) | Mean cost a question (USD) |
|---|---|---|
| N: Sonnet 5.5, the whole novel (dev2) | **56.3** | 0.066 |
| H: Haiku 4.5, Jev's passages behind the pre-filter | 37.5 | 0.028 + Jev 0.011 |
| H0: Haiku 4.5, the whole novel (the dev's) | 45.1 | 0.079 |
| HC: Haiku 4.5, closed book (the dev's) | 1.0 | 0.018 |

The router by cut. R − N in F1 points and the saving of N's cost (Jev paid on every question),
with percentile bootstraps resampling the 8 novels (10,000 draws): with 8 clusters they are
wide and only descriptive. The intervals are computed from the published rows with the lot's
`stats.bootstrap`; `dev2.json` holds the point estimates.

| Cut | Covered | Covered H − N | R − N | Saving |
|---|---|---|---|---|
| 0.5 | 33 (80.5 %) | −13.2 | −10.7 [−24.7, +1.5] | +25.2 % [+10.7, +39.1] |
| 0.6 | 32 (78.0 %) | −11.6 | −9.0 [−20.2, +1.6] | +24.3 % [+9.7, +38.6] |
| 0.7 | 24 (58.5 %) | −9.2 | −5.4 [−14.5, +3.7] | +7.8 % [−2.7, +22.5] |
| 0.8 | 11 (26.8 %) | −14.7 | −3.9 [−9.4, +0.4] | −4.9 % [−8.1, −0.3] |
| 0.9 | 1 (2.4 %) | 0.0 | 0.0 | −14.3 % [−17.9, −10.5] |

- **Haiku on these passages against Sonnet:** H − N −18.7 [−36.1, −5.8]; against Haiku with the
  whole novel, H − H0 −7.5 [−18.9, +3.4].
- **Memory answers almost nothing** (HC 1.0 F1, the dev's sessions).

## The sealed reading

By `prereg-dev2.md` section 5 (`dev2_read.py`, `dev2.json`): 41 of 41 questions complete; HC
far below N (no memory stop); **no cut**: the dev's rule wants the lowest of 0.5-0.9 covering
at least 29 % and 8 questions with covered H − N at least −2 F1 points, and every cut that
covers enough (0.5 to 0.7) has covered H − N between −9.2 and −13.2. **The router is not
confirmed and no
confirmation is sealed.** The money would have fitted (a confirmation with N and H on the 310
other questions: Claude 73 USD of the lot's 105 by the registered ceilings, Jev 2.8 expected
against 12.2 left), but the rule stops before money.

## What the pre-filter changed

**In cost, what it was meant to.** Jev 0.0106 USD a question on the 41 (90th percentile 0.0151,
dearest 0.0192), against 0.0392 over the whole novel in the dev and 0.0115 on the probe's 3
questions; 0.434 USD in all, 88 % of its pre-run plan. At the dev's cut the router would save a
quarter of N's cost, where the dev's router cost a quarter more.

**In what Haiku reads, more than the dry run said.** Jev's kept text shrank from a mean of
15,449 characters to 10,534 (median 8,370 to 5,090). ∞Bench's normalised reference is in the
kept text for 18 questions, against 21 in the dev: the pre-filter lost it on 3 and gained it on
none (the dry run's masked and oracle estimates at K = 200 lost 2). The gate barely moved (mean
p 0.647 to 0.651; 78.0 % covered at 0.6, against 80.5 %).

**In H's score, 7 points observed:** H(dev2) − H(dev) −7.0 [−15.5, +2.3] on the same
questions (the interval crosses 0), H from 44.6 to 37.5.

## The N rerun (description, not a verdict)

N ran twice on the same 41 questions, hours apart on 2026-10-17, with the same prompt and the
same pinned Claude Code: N(dev2) − N(dev) +1.2 F1 points [−2.9, +5.4], 17 of 41 questions
scored differently, the SD of the per-question difference 18.2 points; 2.72 USD against 2.84.
One pair of draws of one arm, so a description of its run-to-run variance and nothing to plan
on. It is enough to move the dev's own reading: the dev's gate and H against dev2's N put the
dev's cut at 0.7, not 0.6 (covered H − N at 0.6 −3.5 instead of −0.7).

## Diagnosis: why a cheaper Jev did not pay

The saving was there; Haiku's answers on the shortlisted passages scored lower (observed,
−7.0 [−15.5, +2.3], the interval crossing 0), and on the covered questions far enough under
Sonnet that the rule fails. Splitting H's drop (−7.0 points a question, a sum of −288 points
over 41) by whether the reference was in the kept text, in the dev and in dev2:

| Reference in Jev's kept text (dev → dev2) | Questions | H dev | H dev2 | Share of the drop |
|---|---|---|---|---|
| kept → lost | 3 | 73.3 | 8.3 | −195 points (68 %) |
| kept → kept | 18 | 65.0 | 63.9 | −20 (7 %) |
| absent → absent | 20 | 21.8 | 18.2 | −73 (25 %) |

- **Two thirds of the loss is two questions whose reference left the shortlist** (−100 points
  each, −200 of −288). On both the kept text collapsed (22,805 to 2,981 characters, and 23,651
  to 658) and Haiku went from F1 1.0 to 0.0; on one the gate said so (p 0.64 to 0.46, no longer
  covered), on the other it did not (p 0.81, covered: Haiku answered from passages that no
  longer held the answer). The third question that lost its reference kept its length and moved
  +5 points.
- **Where the reference stayed, Haiku stayed** (65.0 to 63.9, within the arm's run-to-run
  movement measured on N above), though the passages were shorter.
- **Where the reference was never there,** the questions are mostly lost either way (about 20
  F1), and the drop is small and noisy.
- **The lost references explain about half of the covered drop at 0.7; the rest of H's drop
  alone would also fail the rule.** On the questions dev2's gate covers at 0.7, covered H − N
  is −1.9 with the dev's H and −9.2 with dev2's; giving the covered question that lost its
  reference its dev score back brings it to −5.1, so the lost references explain −4.2 of the
  −7.3. At 0.6 they explain −3.0 of −5.3 (from −6.3 to −11.6; restored, −8.6).
- **Without the pre-filter the cut would have moved to 0.7, saving 4 %, and needed about 340
  questions against 310: no confirmation either.** With the dev's own gate and H (full
  passages) against dev2's N, the lowest qualifying cut is 0.7 (24 questions, covered H − N
  −0.05, R − N −0.03), the router saves 3.8 % at dev2's Jev cost, and 80 % power for the
  confirmation there needs about 343 questions. So the dev's pass at 0.6 (−0.7) sat inside one
  arm's run-to-run variance.

## Next

**K = 300 is not proposed.** In the dry run it kept every reference string the full tournament
kept (21 of 21) at about 0.014-0.016 USD a question. At best it would give back the dev's gate
and H on full passages. Against dev2's N that composition sets the cut at 0.7, where it saves
3.8 % at dev2's Jev cost and **loses 2.9 %** at K = 300's (Jev 0.015 a question); 80 % power
for the confirmation there needs about 343 questions, against the 310 left (a projection from
these rows, with the dev's gate and H and dev2's N: not a measurement). A dev at K = 300 would
cost about 0.6 USD of Jev and 1-4 of Claude (H alone, or N and H again), and what it can show
is limited: it would be the third look at the same 41 questions, whose cut has already moved
between 0.6 and 0.7 with one arm's rerun, so any cut chosen there would be chosen on noise
already seen twice. It could show the references come back; it could not show the router holds
or pays.

**The proposal is to stop design (b) on ∞Bench En.QA.** On these novels Sonnet 5.5 in Claude
Code answers at about 0.07 USD a question by searching the file, and the margin left between
Sonnet and Haiku (about 0.04 USD a question) does not carry passage selection plus a gate whose
covered questions lose about 0 to 13 F1 points against Sonnet at the cuts that cover enough,
depending on the draw. What remains open for longdoc-free is a different population
(documents Claude Code cannot grep as cheaply, or Opus 5.5 as the frontier model, where the
margin is larger), which is a new lot with its own design.

## What it does not say

- Nothing on the router beyond these 41 questions, which both devs have now used: the cut and
  every figure here are chosen or measured on them.
- One session per question and arm; H0 and HC are the dev's single draws.
- Nothing about Opus 5.5, K other than 200, other `fit_chars`, or other documents.

## Cost

Jev 0.4338 USD (phase J2, cap 1.00). Claude 3.99 USD at list price on the subscription: the
smoke 0.10, N 2.72, H 1.17. The lot so far: Jev 2.08 USD of the owner's 14.30 (dev 1.6072,
probe 0.0346, dev2), Claude 12.18 of 105.

## Files

`prereg-dev2.md` and `prereg-dev2.sha256` (the registration and its seal), `dry.json` (the free
dry runs before the seal), `jev-dev2.jsonl` (per question: the gate's p, kept characters,
whether the reference is in the kept text), `dev2-smoke-rows.jsonl`, `dev2-sonnet-rows.jsonl`,
`dev2-haiku-rows.jsonl` (per session: F1, cost, turns; no answer text) and their `*-stop.json`,
`dev2.json` (the sealed reading), `../../../fixtures/longdoc-free/jev-dev2.jsonl.gz` (Jev's
recorded decisions, for replay only). Code: `benchmarks/longdoc_free/` (`jev_phase.py` phase
dev2, `dev2_read.py`), `benchmarks/h2h/h2h_lfree.py` (stage dev2).
