# longdoc-free, dev phase: pre-registration

Instrument commit: `253f38b6341f8fc30b5e352ac1149042fcceaba1`

Written 2026-10-17 before any call of this lot. The owner approved the lot on 2026-10-17
(design `design.md`, about 63 USD of Claude and 7 of Jev, hard caps 105 and 11.50, H0
included). This file registers the **dev phase** only: what it runs, what it may spend and the
rules by which it sets the confirmation. The dev is not a verdict; nothing here is read as one.

## 1. Question

`points.longdoc` substitutes the frontier model on four-option questions. On free-text answers
Jev writes nothing, so it can only choose what is read and who answers. Design (b): Jev keeps
the passages of a long novel that a question needs and judges whether they suffice; where it
says so with p ≥ the cut, Haiku 4.5 answers from those passages, elsewhere Sonnet 5.5 answers
from the whole novel. The dev fixes the cut and the confirmation's size and money; the
confirmation (its own pre-registration, sealed after the dev) tests R − N > −5 F1 points, then
H − N > −5, at one-sided 2.5 % each, resampling novels (`stats.verdict`).

## 2. Data

- ∞Bench En.QA (`longbook_qa_eng`), Hugging Face `xinrongzhang2022/InfiniteBench` at commit
  `90f0394333616266d9fe85824ceaf505093cbaa5`, sha256
  `7f53a3aabd5445fa29f168914f13569c348406cfc88a3e495f3f2c13a0966ca4` (`pool.py`, checked
  before any call): 351 questions over 69 novels of 298,903 to 3,171,853 characters, answers a
  list of short references (median 2 words). Licence: MIT repository, Apache-2.0 card.
- Frozen once, from metadata only (ids and novel keys, never a question or answer):
  `ids.json`, the novels in a seeded order (`random.Random(20261017)`), whole, until 40
  questions. **Dev: 41 questions on 8 novels; confirmation: the other 310 on 61.** No dev
  novel is in the confirmation.
- Scorer: ∞Bench's own `qa_f1_score` for En.QA (token F1 after lower-casing and removing
  punctuation, articles and extra spaces, the maximum over the references), vendored
  unchanged from InfiniteBench `src/compute_scores.py` at commit
  `51d9b37b0f1790ead936df2243abbf7f0420e439` (MIT; `infbench_score.py`, a test compares the
  three functions with the upstream file). The upstream scores the reply as it comes; here every
  arm's reply is cut to its answer (section 4) before the same function.

## 3. Phase J: Jev (paid, Jev only)

- Per question: `Squire.select_passages` over the novel as pages (`pages.pages_of`: paragraphs
  joined up to 900 characters, the length the page tournament shows of a page; longer ones cut
  at sentence ends), `fit_chars=60000`, `fit_score=False` (the 0.3.2 default, free order),
  `max_calls=None` (as every published run). The kept sentences in the novel's order are H's
  file (`pages.kept_text`; `[...]` between pages that are not adjacent).
- Then one Truth over `{question, passages}`, point `longdoc_free_gate`: "`passages` are
  excerpts of one novel. They state everything needed to answer `question`." Its p is the gate;
  no usable answer is p None, never covered.
- Jev `jev-1.13.0` (the model the 0.3.2 default ships; C5b measured `select_passages` on it),
  no long context. B6's asker (`b6_run.Asker`): the recording first, one live call on a miss,
  never retried (a 429 is not retried), at most 4 in flight, one call per identical request,
  stopped by the cap, an outage, another model or three failures in a row.
- Lot `longdoc-free-dev` (`paid_once.Lot`): recording `fixtures/longdoc-free/jev-dev.jsonl`,
  ledger `~/.cache/sanchopanza/longdoc-free-dev/ledger.jsonl`, **hard cap 1.50 USD** in
  `CappedDecider` (each call reserved at its pessimistic estimate, settled at its cost). Dry
  run (stub, free): **2,779 calls, 1.44 USD pessimistic**; the measured median of a real request
  (71 micro-USD) puts it near 0.20 USD. One launch and at most one relaunch, none after a 402,
  a 429, the cap or another model (`paid_once.may_launch`).
- Launcher `longdoc-free-jev-run.cmd dev`, sealed by this file's seal; refused between 00:00
  and 08:00 and with its local values unset. Before it: `python -m sanchopanza jev-preflight`.
  The owner's other lots that use Jev that day are asked first (the W17 Opus repetition's hooks
  use Jev with a 0.50 USD cap; phase J waits for it to finish, or leaves 1 USD in the balance).

## 4. The Claude Code phases (paid, the subscription)

Every arm is one headless Claude Code 2.1.287 session (the private pinned copy first on PATH,
`DISABLE_AUTOUPDATER=1`), a clean user and an empty `CLAUDE_CONFIG_DIR` per session, the web
taken away (WebSearch and WebFetch denied, the local hook on every tool), the same tools as
h2h_longdoc (`benchmarks/h2h/h2h_lfree.py`). One prompt for N, H and H0, ∞Bench's En.QA
instruction with the book as a file:

> Read the book in the file document.txt (in your working directory) and answer the question.
> Be very concise in your answer. / Question: {question} / End your reply with one line:
> ANSWER: <your answer>

| Arm | Model | `document.txt` |
|---|---|---|
| N | Sonnet 5.5 (`claude-sonnet-5-5`) | the whole novel |
| H | Haiku 4.5 (`claude-haiku-4-5-20251001`) | phase J's kept passages for the question |
| H0 | Haiku 4.5 | the whole novel |
| HC | Haiku 4.5 | none; a closed-book prompt ("there is no file ... give your best guess") |

- **Answer**: the text after the reply's last `ANSWER:` line, else its last non-empty line;
  no text is no answer (F1 0, and infrastructure for the guard). The same rule for every arm.
- **Order**: the dev questions in a seeded order (`random.Random(20261018)`). Phase N's
  sessions, then phase Haiku's, where H, H0 and HC are interleaved per question, their order
  rotating with the question's position. One phase per model so each reserves one worst turn.
- **Money** (lb162x's rule, `cap_for`: a session gets its cap while cap plus one worst turn fits
  under the phase's ceiling; below the floor the phase stops, kind `ceiling`):

| Phase | Sessions | Session cap | Ceiling | Worst turn | Floor |
|---|---|---|---|---|---|
| Smoke (one N session, the first dev question) | 1 | 0.80 | 0.80 | 4.32 | 0.80 |
| N | 41 | 3.00 | 12.00 | 4.32 | 0.50 |
| Haiku (H, H0, HC) | 123 | 1.50 | 9.00 | 2.16 | 0.30 |

  **At most 26.12 USD of Claude** (the ceilings plus the smoke's worst turn, which its cap
  does not reserve). Expected about 7.4 (N 0.10 a session; H 0.03, H0 0.05, HC 0.005). Each
  ceiling leaves room for its sessions at 1.5 times the estimate (a test).
- **Refusals before any session** (`refusal`): the seal, the instrument unchanged since its
  commit, the pinned input, a worktree detached at the sealed commit and clean, the pinned
  `claude` first on PATH, every novel and every dev question's passages present, `launch.ps1`
  taking the runner, no `LIMIT.flag`, not before 08:00 and no session crossing midnight.
- **Stops**: STOP in `C:/sp-runs/longdoc-free`; a usage limit (429, "weekly limit") stops the
  stage and writes `LIMIT.flag` (a pause, never a result); an outage or three infrastructure
  failures in a row stop the phase (lb162x_guard). The smoke must pass (a Sonnet session above
  0 USD that ended with an answer or at its cap) before phase N starts.
- **Launch** (by WMI, outside the session, `launch.ps1 -Runner h2h_lfree.py -RunnerArgs
  "--stage dev"`), after phase J has finished and its rows are written (`jev_phase.py rows
  --phase dev`), and **only when no other lot draws on the subscription** (the guard-pointers
  lot of sanchopanza-e1 runs first; the weekly limit is shared).

## 5. What the dev sets for the confirmation (rules fixed now; `dev_read.py`)

Applied to the dev's per-question rows (a question with every arm), before any confirmation
call:

1. **The cut**: the lowest of 0.5, 0.6, 0.7, 0.8, 0.9 whose covered questions have H − N ≥
   −2 F1 points (point estimate). None: the router is not confirmed, and no confirmation is
   sealed for design (b).
2. **n**: 80 % power for R − N > −5 at one-sided 2.5 %, with the dev's SD of the per-question
   difference R − N at that cut, the design effect of its novel clusters (at least 1) and the
   dev's R − N as the true difference (at most 0: a dev gain is not banked). Above the 310
   confirmation questions: no confirmation on En.QA alone (the design's rule; the fallback
   population is a separate lot).
3. **Money**: the confirmation's ceilings from each arm's dev cost per session (mean and 95th
   percentile), its Jev cap from phase J's settled cost over its pessimistic estimate. The
   confirmation's money must fit what is left of the owner's 105 + 11.50 after the dev; if it
   does not, the owner decides before the seal.

Reported, not deciding: HC's mean F1 (what is answered from memory despite the entity
substitution), the gate's coverage at each cut, the share of questions whose normalised gold
answer is in the kept passages, median answer words and the share of replies with an ANSWER
line per arm, sessions at their cap.

## 6. Departures from the design, decided before any data

- **H runs in Claude Code with the passages as `document.txt`**, the same harness, prompt and
  answer rule as H0, instead of a one-field schema call: this repository has no CLI caller for
  that (the design's `ClaudeCLI` is not in it), a prompt of 60,000 characters does not fit
  Windows' command line, and H and H0 then differ only in the file, which is what attributes a
  difference to Jev.
- **`fit_chars` 60,000 and the gate's wording are fixed here**, not tuned on the dev: fewer
  choices made on 41 questions.
- **H0's session cap is 1.50 USD** (h2h_longdoc's for long documents, twice GAIA's), not 0.75.
- **Jev 1.13.0**, the shipped default, not 1.14 (`points.longdoc`'s model): the substitution
  under test is `select_passages` plus a gate as shipped.
- **One phase per model**: N's sessions before Haiku's, not N, H and H0 interleaved per
  question; inside the Haiku phase the arms are interleaved.
- **HC added** (the design's closed-book check), dev only.

## 7. What the dev does not say

It reports no verdict: 41 questions on 8 novels. Its cut and n are chosen on it and never
reused as evidence. One session per question and arm. Sonnet 5.5 only; Opus 5.5 is a later
lot. ∞Bench's novels are famous books with names replaced; HC sizes what memory still answers.
