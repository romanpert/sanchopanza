# Jev 1.14 against 1.13 with the long window (lot L6: B3, A6, A7): pre-registration

Written 2026-10-15, before any jev-1.14.0 answer on these inputs (the smoke below touched dev
items only). Reviewed against the code by an independent `revisor-prereg` agent before the first
seal; its blocking point (a failure counter shared by concurrent items) and the others it
raised are fixed in the code and folded into this text. `prereg.sha256` holds the hash of this file together with the code it names
(`prereg.manifest.json`, written by `python benchmarks/jev114/l6.py --seal`). Branch
`jev114-l6`; the sealing commit's message carries the hash.

## The question

Jev answers up to 262k tokens a request with the `TypeSafe-Danger-Zone-Long-Context` header,
on 1.13 and on 1.14. Three measurements that sanchopanza's own cuts limited:

- **B3, LongBench v2 alone.** The e2e closing found that Jev only pays where it **replaces** an
  expensive call. Can Jev, reading the whole document, answer a LongBench v2 question alone
  when it is sure, and leave the rest to Sonnet, with quality close enough to Sonnet's?
  Sonnet 5.5 in clean Claude Code (arm N of `docs/results/2026-10-06-h2h-longdoc`): 31/50,
  6.13 USD; chance is 25 %.
- **A6, QASPER with the whole paper in one call.** The published tournament
  (`docs/results/2026-09-27-longdocs`) kept every evidence paragraph in 94.7 % of 300 papers
  but with 48.9 % of the text: P28 (>= 85 % with <= 25 %) fails on compression. Does one call
  with every paragraph whole and one Truth per paragraph pass P28?
- **A7, the memory gate on LongMemEval S with whole sessions.** The gate's recall was 0.725
  against BM25 top 3's 0.851 (`docs/results/2026-09-28-memory-gate`), and the registered
  reading was that the 900-character excerpt caps it (75 % of the evidence turns visible).
  With every session whole in one call, does it reach BM25?

In every experiment two effects are kept apart: **model** (j14 - j13r in the same window) and
**window** (L - S with the same model).

## Arms (`benchmarks/jev114/l6.py`)

Cells `<model>-<window>`:

- `j13r`: jev-1.13.0 asked today; `j14`: jev-1.14.0 asked today. Model pinned per arm
  (`JevDecider(model=..., images=False)`); the preflight runs for both before the first live
  call; an answer served by another model stops the run (lot L4's `Arm`).
- `S`: today's production window: no header, the shipped `Limits` (900 characters a page,
  30 pages a call, a tournament past that). `L`: the header on, and the point shows every page
  whole in one call (`Limits(page_chars=400_000, pages_per_call=1_000)`), or the document up to
  900,000 characters (B3).
- `rec13-S`: the 1.13 answers recorded on 2026-09-27 (A6) and 2026-09-28 (A7), replayed free.
  One draw of a non-deterministic model on another day: a historical reference, and in A6 the
  only S cell (below). A free replay before sealing reproduced the published figures exactly:
  A6 94.67 % all evidence at 48.92 % of the text over 300 papers with 0 missing; A7 gate recall
  0.7252, bm25@3 0.8514 over 120 questions with 0 missing.

Both models are asked on every item, the first alternating with the item's rank in a seeded
launch order (seed 20261015); in A7 the window order also alternates (S first on ranks 0-1 mod
4, L first on 2-3). At most 4 calls in flight. Every live call goes through `CappedDecider` on
the shared ledger `C:/sp-runs/jev114/ledger.json` (4.50 USD) and this lot's cap (**1.50 USD**,
batch `jev114-l6`). Answers are recorded per cell in this folder (hashed keys and answers, no
text), so a relaunch pays nothing twice for an answered call. Claude is not called: 0 USD of
Claude.

**Stops.** A call the cap refuses, or an HTTP 402, stops the run: the set in progress writes no
rows and the runner exits with 2; a relaunch replays what was paid. A set whose scored file
exists is frozen: a live run does not ask it again. A6 does not start unless 0.54 USD of the
lot's cap is left. The live runner checks this seal (`prereg.sha256` over `prereg.manifest.json`:
this file, the code, `fixtures/longdocs.jsonl`, the dev ids, and the hashes of the external
inputs: LongBench `tasks.jsonl`, Sonnet's `sessions.jsonl`, the recorded A7 decisions, QASPER and
LongMemEval) and spends nothing if any of them changed. A timed-out call is settled at 0 in the
ledger although Jev may have billed it; the README reports how many there were.

## The smoke (done before this file was sealed; dev items only)

One LongBench dev task (`66eefe85...`, 118,549 characters), two QASPER papers outside the 300
(the eligible papers after them in the published draw order), one LongMemEval dev question;
every cell; 0.0207 USD, 0 failures. Seen: tokens, cost, latency, and the answers on those
items (all four B3 cells answered the gold letter at 0.92-0.93; A6 and A7 kept the gold in
every cell). Measured and used to fix the constants:

- LongBench text: 3.77-3.80 characters per token (100,000 characters = 26,550 tokens). So
  `S` = 100,000 characters (under 32k tokens a question) and `L` = 900,000 (about 237k
  tokens, under 262k).
- QASPER, one call with every paragraph: 20-23k tokens a paper (the 900-character criteria of
  every Truth weigh more than the paper): about 0.0009 USD a paper and model.
- LongMemEval, one call with every session whole: 119,606 tokens (0.0050 USD) per model;
  the S gate 3 calls, about 0.001; `needs_recall` 496 tokens.

## B3: LongBench v2, Jev alone

**Inputs.** The 50 tasks of the 2026-10-06 confirmation (`longdoc_data.load()`, the 10 dev ids
of `benchmarks/h2h/longdoc-dev-ids.txt` out), contexts of 104k to 2M characters. Sonnet's
answer, correctness (`ok_oficial`) and list cost per task are read from the run's sessions file
(arm `SONNET-CC`, clean Claude Code, N).

**The question**, one call per task and cell, point `longbench_choice`: state
`{"question": <question>, "document": <the context, middle-cut>}`, one Choice `answer` with
instructions "Which option is the correct answer to `question`? The answer is in `document`:
read it to decide." and options `A`-`D` whose criteria are the four choice texts, in the
dataset's order. The middle cut keeps the first and the last half of the window's characters
(LongBench's own truncation): S shows 100,000 characters of every document, L up to 900,000
(44 of the 50 fit whole). A call that fails (HTTP 400, timeout) is asked again at 0.8 and then
0.64 of the window, **for both models**, so a pair always sees the same text; a cell still
unanswered after the third length is a failure.

**Reading.** The answer is the chosen letter; its confidence is that letter's probability
(`probabilities[choice]`, Choice probabilities being the calibrated output: Choice ECE 0.026
on the public benches). An answer with no probability for its pick is unanswered.

**Metrics per cell:** accuracy (unanswered counts as wrong in `accuracy_all`, and is reported
apart), AUC of the confidence for right against wrong answers (threshold-free), the letters
chosen against the gold letters (position bias), cost and tokens; and the **substitution
sweep**: at each cut in {0.5, 0.6, 0.7, 0.8, 0.9, 0.95}, Jev answers alone where its
confidence is >= the cut and Sonnet's recorded answer stands elsewhere (an unanswered task goes
to Sonnet). Reported: coverage, precision on the covered tasks (Wilson 95 %), Sonnet's accuracy
on the same tasks, the hybrid's accuracy against Sonnet alone (paired), Sonnet's list cost
saved on the covered tasks and the net saving (that minus every Jev call of the cell,
including the attempts discarded by a shorter retry) as a share of Sonnet's cost.

**Substitution verdict (the product question), at the registered cut tau = 0.9**, per cell:
**"sustituye"** only if (1) coverage >= 20 %, (2) precision on the covered tasks >= 90 %
(point estimate), and (3) the hybrid's accuracy minus Sonnet's has a paired 95 % CI lower bound
above -2 points; otherwise **"no sustituye"**. **The product answer is `j14-L`'s verdict**
(the primary cell, chosen before the data); the other three cells are reported with their own
reading and no correction for multiplicity: `j13r-L` against `j14-L` says whether a
substitution is the model's or the window's. The other cuts are descriptive; a cut picked
after seeing the data would be reported as such and gives no verdict.

**Comparisons (family B3, Holm over these six):** accuracy j14-S vs j13r-S and j14-L vs
j13r-L (model); j13r-L vs j13r-S and j14-L vs j14-S (window); AUC j14 vs j13r in S and in L
(model). Each on the tasks both cells answered; the failure-gap rule below applies.

## A6: QASPER, the whole paper in one call

**Inputs.** The 300 papers and questions of `docs/results/2026-09-27-longdocs`
(`benchmarks/longdocs/run.py`'s `build`, seed 2030), gold = QASPER's evidence paragraphs.

**Cells.** `j13r-L` and `j14-L`: `Squire.triage_many` with the production thresholds
(`pages_in_context` 0.40) and `Limits(page_chars=400_000, pages_per_call=1_000)`, so one
`triage_pages` call holds every paragraph whole and one Truth per paragraph, the production
question (`chunks.context_questions`). `rec13-S`: the published tournament, replayed.
**No live S cell**: re-asking the tournament costs about 0.45 USD a model (1,515 calls on the
first run), outside this lot's cap once B3 is paid. So the model effect is measured at L only,
and the window effect (j13r-L against rec13-S) compares two days and two draws of 1.13: it is
reported with that caveat and its verdict reads "window, cross-day".

**Metrics per cell** (as `run.py`'s `score`): all evidence kept (primary), any evidence kept,
text kept (characters of kept paragraphs over the paper's, mean over papers), paragraphs kept,
and P28 (all evidence >= 85 % and text <= 25 %), always over the 300 papers: a paper whose
call failed reads as production reads it (`triage_pages` keeps an unanswered page), every
paragraph kept at the cut, and no evidence kept within the budget below; the number of failed
papers is reported. Threshold-free: **all evidence kept within a
25 % text budget** (paragraphs by probability, unanswered last, the longest prefix within 25 %
of the paper's characters) and the mean per-paper AUC of the probability for evidence
paragraphs.

**Comparisons (family A6, Holm over these six):** model (j14-L vs j13r-L) and window (j13r-L
vs rec13-S), each on all evidence at the cut, all evidence within the 25 % budget (both
McNemar), and text saved (old minus new share of the paper, paired bootstrap: positive means
less text), each on the papers both cells answered, with the failure-gap rule. The
lateral-wholedocs rule GW (87.2 % of answer **sentences** at 21.0 %, 219 other
questions) measures sentences, not paragraphs: quoted as context, not compared.

## A7: the memory gate, whole sessions

**Inputs.** The 120 test questions of `docs/results/2026-09-28-memory-gate`
(`longmemeval.slices`, seed 20260928), launched in the seeded order (20261015), two questions
at a time. **n is set by the cap**: A7 runs last, and a new pair of questions is not started
when the lot's ledger spend plus 0.016 USD a question would pass 1.50 USD. Expected, from the
smoke and the B3 and A6 estimates (0.60 and 0.54 USD): about 25 questions. Fewer than **20**
complete questions give every A7 comparison, the BM25 ones included, the verdict "no
concluyente (n bajo)".

**Cells per question.** `needs_recall` once per model (through S, no header: the same answer
serves both windows). `S`: `memory_gate.triage_memories` as shipped (each session as its head
plus the best-matching window, 900 characters; 30 a call, a tournament past that). `L`: every
session whole (`memory_gate.pages_of(..., limit=400_000)`) in one `triage_many` call with the
long `Limits`. Production thresholds. The gate keeps the triage's sessions when
`needs_recall` looks, none when it does not. A cell fails on a question when any of its calls
failed (the triage, or `needs_recall`, which the point itself would read as "look"), or when
its triage answered no page. `rec13-S` (the recorded gate) and `bm25@3` (computed) on the same
questions.

**Metrics per cell** (as `longmemeval.report`): gate session recall (pooled over gold sessions;
primary), any-hit, all-hit, characters injected, precision; the excerpt ceiling of the
questions run. The comparisons use the questions where all four live cells answered
(complete cases), with the failure-gap rule computed over every launched question; the
original runner's reading (a failed triage injects nothing: recall 0 on that question) is
reported beside it for every cell.

**Comparisons (family A7, Holm over these four):** gate recall j14-S vs j13r-S, j14-L vs
j13r-L (model); j13r-L vs j13r-S, j14-L vs j14-S (window). Paired bootstrap over questions.
**Against BM25 top 3**, per cell: the original criterion 1 (paired CI of recall minus bm25@3
above 0: "bate a BM25") and "alcanza" (point estimate >= bm25@3 - 0.03, the margin of the
original's criteria H and C).

## Decision rule (lot L4's, `l4_stats.verdict`)

For every comparison in a family: binary metrics by exact two-sided McNemar on the discordant
pairs and a 95 % CI of the difference by paired item bootstrap (10,000 resamples, seed
20261015, percentile); AUC, recall and text share by the same paired bootstrap, p = twice the
smaller share of resampled differences on either side of 0. Holm within the family.
**"mejora"** if the difference is > 0 with Holm p < 0.05; else **"no peor"** if the CI's lower
bound is above -2 points (-0.02); else **"no concluyente o peor"**. A comparison where the
newer cell failed on more than 2 % more items gets no favourable verdict; one not measured is
"no medido". Two readings always: with the production threshold (and tau = 0.9 in B3) and
without one (accuracy and AUC, the 25 % budget, recall).

**Power, honestly.** B3 has 50 tasks: a ±2-point rule on accuracy will be "no concluyente"
unless the cells barely disagree; the substitution verdict is the result that matters. A6's
300 papers resolve a few points. A7's ~25 questions resolve only large effects (the gap to
BM25 was 12.6 points).

## Order, spend and what is not done

B3, then A6, then A7 (the lot's priority B3 > A6 > A7). Estimates (smoke-measured): B3 0.60
USD (two models, two windows), A6 0.54, A7 what is left (about 0.30). Hard caps in code: the
ledger's 4.50 and this lot's 1.50; the smoke spent 0.0207 of it.

Not done: the A6 tournament asked again (cost), A7's hybrid and cascade arms (the gate is the
registered primary), the LongBench dev tasks beyond the smoke's one, any Claude call.

## Product recommendation (written in the README from the verdicts, not changed after)

If a B3 cell is "sustituye" at tau = 0.9, the README will say where Jev with the long window
can replace a Sonnet call on long-document questions and at what saving; if none is, it will
say that it cannot on this evidence. A6 "P28 passes" for an L cell would make one call per paper
the long-document triage to recommend over the tournament; A7 "alcanza/bate a BM25" for an L
cell would make whole-session triage a candidate for the memory gate (the default stays
1.13, its thresholds and its `Limits`; nothing in `policy.py` or `DEFAULT_MODEL` changes in
this lot).
