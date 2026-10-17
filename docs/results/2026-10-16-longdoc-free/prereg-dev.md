# longdoc-free, dev phase: pre-registration

Instrument commit: `5ada5af09379a9d9bc67d40210c55e00733cd304`

Written 2026-10-17 before any call of this lot. The owner approved the lot on 2026-10-17
(design `design.md`, about 63 USD of Claude and 7 of Jev, hard caps 105 and 11.50, H0
included) and, the same day after the independent review of this file's draft, raised the
Jev cap to **14.00 USD** (dev 1.50, confirmation 12.50: the confirmation's dry run came to 12.32
pessimistic) and set the Claude rule: **what has really been spent plus the caps of what is left
never exceeds 105 USD**. This file registers the **dev phase** only: what it runs, what it may
spend and the rules by which it sets the confirmation. The dev is not a verdict.

## 1. Question

`points.longdoc` substitutes the frontier model on four-option questions. On free-text answers
Jev writes nothing, so it can only choose what is read and who answers. Design (b): Jev keeps
the passages of a long novel that a question needs and judges whether they suffice; where it
says so with p ≥ the cut, Haiku 4.5 answers from those passages, elsewhere Sonnet 5.5 answers
from the whole novel. The dev fixes the cut and whether, and with what money, a confirmation is
sealed; the confirmation (its own pre-registration, sealed after the dev, on all 310 remaining
questions) tests R − N > −5 F1 points, then H − N > −5, at one-sided 2.5 % each, resampling
novels (`stats.verdict`).

## 2. Data

- ∞Bench En.QA (`longbook_qa_eng`), Hugging Face `xinrongzhang2022/InfiniteBench` at commit
  `90f0394333616266d9fe85824ceaf505093cbaa5`, sha256
  `7f53a3aabd5445fa29f168914f13569c348406cfc88a3e495f3f2c13a0966ca4` (`pool.py`, checked
  before any call): 351 questions over 69 novels of 298,903 to 3,171,853 characters, answers a
  list of short references (median 2 words). Licence: MIT repository, Apache-2.0 card.
- Frozen once, from metadata only (ids and novel keys, never a question or answer):
  `ids.json`, the novels in a seeded order (`random.Random(20261017)`), whole, until 40
  questions. **Dev: 41 questions on 8 novels (the longest 1,186,368 characters); confirmation:
  the other 310 on 61.** No dev novel is in the confirmation. `ids.json` is part of both
  instruments (any change after the instrument commit refuses every paid run), and every
  stage novel is checked against its key before a session.
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
  excerpts of one novel. They state everything needed to answer `question`." Its p is the gate.
- Jev `jev-1.13.0` (the model the 0.3.2 default ships; C5b measured `select_passages` on it),
  no long context. B6's asker (`b6_run.Asker`): the recording first, one live call on a miss,
  at most 4 in flight, one call per identical request, stopped by the cap, an outage, another
  model or three failures in a row. A 429 is not retried; a 529 is, up to 3 times inside one call
  (`JevDecider`).
- Lot `longdoc-free-dev` (`paid_once.Lot`): recording `fixtures/longdoc-free/jev-dev.jsonl`,
  ledger `~/.cache/sanchopanza/longdoc-free-dev/ledger.jsonl`, **hard cap 1.50 USD** in
  `CappedDecider` (each call reserved at its pessimistic estimate, settled at its cost). Dry
  run (stub, free): **2,779 calls (1,967 of them page tournaments of about 27,000 characters),
  1.44 USD pessimistic, about 1.13 expected** at B6's measured factors.
- **Balance**: a 402 is a `funds` stop with no relaunch, which would end the dev. Before phase
  J the owner tops up TypeSafe to at least 2.50 USD for this phase and the 0.50 USD cap of the
  W17 Opus repetition (sanchopanza-e1) if it still runs; `python -m sanchopanza jev-preflight`
  must pass.
- One launch and at most one relaunch, none after a 402, a 429, the cap or another model
  (`paid_once.may_launch`). **If any call is still unanswered after that, phase J is
  incomplete: no passages are written (`jev_phase.py rows` refuses), no Claude session runs, and
  the dev is reported as not run.**
- Launcher `longdoc-free-jev-run.cmd dev`, sealed by this file's seal, run from a worktree
  detached at the seal commit itself (checked: HEAD detached and clean, the seal file committed
  and HEAD the last commit that touched it); its `PY` and `SANCHOPANZA_KEYS_ENV` are filled in
  place in that worktree's tracked copy, the one change the clean check allows (its digest, the
  two values masked, must equal the sealed one); refused between 00:00 and 08:00 and with its
  local values unset; the key is read after every other check. **Nothing is committed in the run
  worktree until the dev ends** (a commit there would refuse the next stage).
- Jev's decisions are recorded only to replay this lot (TypeSafe MCA 2.3(b): never to train a
  model or to distil Jev). Recordings hold hashed keys and the answers, no text.

## 4. The Claude Code phases (paid, the subscription)

Every arm is one headless Claude Code 2.1.287 session (the private pinned copy first on PATH,
`DISABLE_AUTOUPDATER=1`), a clean user and an empty `CLAUDE_CONFIG_DIR` per session, the web
taken away (WebSearch and WebFetch denied, the local hook on every tool), the same tools as
h2h_longdoc, Task and Agent included (`benchmarks/h2h/h2h_lfree.py`). One prompt for N, H and
H0, ∞Bench's En.QA instruction with the book as a file:

> Read the book in the file document.txt (in your working directory) and answer the question.
> Be very concise in your answer. / Question: {question} / End your reply with one line:
> ANSWER: <your answer, in a few words>

| Arm | Model | `document.txt` |
|---|---|---|
| N | Sonnet 5.5 (`claude-sonnet-5-5`) | the whole novel |
| H | Haiku 4.5 (`claude-haiku-4-5-20251001`) | phase J's kept passages for the question |
| H0 | Haiku 4.5 | the whole novel |
| HC | Haiku 4.5 | none; a closed-book prompt ("there is no file ... give your best guess") |

- **Answer**: the text after the reply's last `ANSWER:` (or `Final answer:`) line; without one,
  the reply's last non-empty line only when the session ended without an error; otherwise no
  answer. No answer scores F1 0 and is what lb162x_guard counts as infrastructure (an error
  message or a half-done turn is never scored as an answer; a session at its cap without an
  answer line is a measurement with F1 0). The same rule for every arm. F1 of the answer cut to
  its first 12 tokens is recorded as a secondary.
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
  does not reserve). Expected about 7.7 (N 0.10 a session; H 0.03, H0 0.05, HC 0.005; the
  smoke). Each ceiling leaves room for its sessions at 1.5 times the estimate (a test). This is
  above the design's 15 for the dev, by the owner's rule above.
- **Refusals before any session** (`refusal`): the seal; the instrument (`src`, `benchmarks`,
  `ids.json`) unchanged since its commit; the pinned input; the seal commit itself, detached and
  clean (as phase J); the pinned `claude` first on PATH; the stage's novels present and equal to
  their keys; every dev question's passages present and as long as `jev-dev.jsonl` says;
  `launch.ps1` taking the runner; no `LIMIT.flag`; not before 08:00 and no session crossing
  midnight.
- **Stops**: STOP in `C:/sp-runs/longdoc-free`; a usage limit (429, "weekly limit") stops the
  stage and writes `LIMIT.flag` (a pause, never a result); an outage or three infrastructure
  failures in a row stop the phase (lb162x_guard). The smoke must pass (a Sonnet session above
  0 USD that ended with an answer or at its cap) before phase N starts; its `usd_by_model` is
  read by hand for a subagent on another model.
- **Launch** (by WMI, outside the session): `powershell -File benchmarks/h2h/launch.ps1 -Runner
  h2h_lfree.py -RunnerArgs "--stage dev" -Pin %USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
  -KeysEnv <path> -Log C:\sp-runs\longdoc-free\driver.log -PidFile
  C:\sp-runs\longdoc-free\driver.pids`, after phase J has finished and its rows are written
  (`jev_phase.py rows --phase dev`), and **only when no other lot draws on the subscription**
  (the guard-pointers lot of sanchopanza-e1 runs first; the weekly limit is shared).

## 5. What the dev sets for the confirmation (rules fixed now; `dev_read.py`, `stats.py`)

Applied to the dev's per-question rows (a question with N, H and H0), before any confirmation
call:

1. **Read at all**: at least 35 of the 41 questions complete; else the dev is reported and no
   confirmation is sealed.
2. **Memory**: HC's mean F1 within 10 points of N's means the set measures what Haiku
   remembers (the entity substitution not holding): no confirmation is sealed on it.
3. **The cut**: the lowest of 0.5, 0.6, 0.7, 0.8, 0.9 that covers at least 29 % of the
   questions (the design's break-even: below it the router saves nothing) and at least 8 of
   them, and whose covered questions have H − N ≥ −2 F1 points (point estimate). None: the
   router is not confirmed, and no confirmation is sealed for design (b).
4. **Feasibility of the confirmation's 310 questions**: n for 80 % power for R − N > −5 at
   one-sided 2.5 %, with the dev's SD of the per-question difference R − N at that cut, the
   design effect of its novel clusters (at least 1.5: 8 clusters estimate it poorly) and the
   dev's R − N as the true difference (at most 0: a dev gain is not banked). Above 310: no
   confirmation on En.QA alone (the fallback population is a separate lot). The confirmation
   runs all 310 either way; n only decides whether it is sealed.
5. **Money**: per Claude phase of the confirmation, 310 sessions per arm at the larger of 1.5
   times the arm's dev mean and its dev 95th percentile, plus one worst turn and the floor (N's
   phase; H's and H0's in one Haiku phase). Claude fits when the dev's real spend (every session
   and open reservation of its three phases, the smoke included, as the guard counts it) plus
   these ceilings is at most 105. Jev's cap stays 12.50; it fits when the confirmation's dry-run
   pessimistic estimate (12.32 USD) is under it (what `paid` requires) and so is its expected
   cost, that estimate times the dev's settled over pessimistic ratio, times a 1.2 margin (up to
   a ratio of 0.85). If either does not fit, the owner decides before any seal.

Reported, not deciding: the gate's coverage at each cut, the share of questions whose
normalised gold answer is in the kept passages, median answer words, the share of replies with
an ANSWER line and the 12-token F1 per arm, sessions at their cap.

## 6. Departures from the design, decided before any data

- **H runs in Claude Code with the passages as `document.txt`**, the same harness, prompt and
  answer rule as H0, instead of a one-field schema call: this repository has no CLI caller for
  that (the design's `ClaudeCLI` is not in it), a prompt of 60,000 characters does not fit
  Windows' command line, and H and H0 then differ only in the file, which is what attributes a
  difference to Jev.
- **`fit_chars` 60,000, `max_calls` None and the gate's wording are fixed here**, not tuned on
  the dev (the design left `fit_chars` and `max_calls` to it): fewer choices made on 41
  questions.
- **Answer length**: the prompt asks for "a few words" in the ANSWER line but sets no hard word
  limit (the design's "word limit"); the answer rule, the median words per arm and the 12-token
  F1 are the controls. Token F1 penalises a long answer, so a verbose N would flatter the
  router: the 12-token F1 is reported beside every comparison.
- **H0's session cap is 1.50 USD** (h2h_longdoc's for long documents, twice GAIA's), not 0.75.
- **Jev 1.13.0**, the shipped default, not 1.14 (`points.longdoc`'s model): the substitution
  under test is `select_passages` plus a gate as shipped.
- **One phase per model**: N's sessions before Haiku's, not N, H and H0 interleaved per
  question; inside the Haiku phase the arms are interleaved.
- **HC added** (the design's closed-book check), dev only, with the memory rule above.
- **Money**: the dev's Claude worst case is 26.12 (the design's 15), and Jev's lot cap 14.00
  (the design's 11.50), both by the owner's decisions of 2026-10-17.

## 7. What the dev does not say

It reports no verdict: 41 questions on 8 novels. Its cut and feasibility are chosen on it and
never reused as evidence. One session per question and arm. Sonnet 5.5 only; Opus 5.5 is a
later lot. ∞Bench's novels are famous books with names replaced; HC sizes what memory still
answers.

## 8. Independent review (`revisor-prereg`, before the seal)

Three rounds on 2026-10-17, against the code, before any call.

1. On the draft (instrument `253f38b`): **one block**, a session that failed with text (an API
   error, an expired login) or met its cap mid-turn was scored as an answer and never reached
   the guard; fixed (the answer rule of section 4, with a test through the guard). And: a cut
   could be set on 1 covered question (now 29 % and 8); phase J's expected cost was 1.13, not
   0.20 (the balance rule); the confirmation's phase J did not fit 10.00 (the owner raised the
   lot's Jev cap to 14.00); `ids.json` and the seal commit were not bound (both now are); the
   dev's money, an incomplete phase J and the answer length were undeclared (sections 3, 6).
2. On `f15e11a`: **one block**, the launcher filled in place would fail the new clean-checkout
   check (it is now the one change allowed, its masked digest checked); and the Jev money rule
   would almost always say "does not fit" (now the pessimistic estimate and the expected cost
   with a 1.2 margin under 12.50). Also the dev's real Claude spend (every session and open
   reservation) and the reply predicate.
3. On `4c1623b`: **can be sealed**; one optional point (a missing `is_error` read as an error),
   done in the instrument above.
