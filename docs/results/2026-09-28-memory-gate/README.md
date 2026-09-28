# A recall gate for Claude Code's auto memory (2026-09-28)

**Status: part A measured live and NEGATIVE.** The gate, the hybrid and the passage cascade
all fail their pre-registered recall criteria against BM25 top 3 (0.725, 0.689 and 0.729
against 0.851-0.859), while injecting far fewer characters (a half; 4 % for the cascade) at
0.93-0.97 precision. Exploratory, at equal text: the cascade beats truncated sessions and BM25
paragraphs, and is not distinguishable from BM25 over sentences on whether the answer's own
turn is injected. Spent 0.171 (gate, hybrid) + 0.221 (cascade, after a runner bug was found,
fixed and the run completed) USD. Part B not run.

- **Part A, primary, public**: LongMemEval S with gold labels, `prereg-longmemeval.md`
  (hash pinned in `tests/test_memory_gate_bench.py`; amendments 1-2 before any decision, 3
  after the gate was judged and before the cascade was measured, 4 exploratory).
- **Part B, not run: needs the owner's consent** to send his redacted memories and prompts to
  Jev. `prereg.md`, amended twice before any arm was scored (the lexical label was mostly
  noise). `run.py --live` refuses without `--owner-consent`. Its free, descriptive result
  stands: **on this machine the model read a memory file 6 times in the windows of 551
  prompts.**

## What the gate is

`src/sanchopanza/harness/memory_gate.py`, a `UserPromptSubmit` hook body. Claude Code loads
the head of `memory/MEMORY.md` at session start and leaves every memory file to the model to
open; on this machine it read a memory file 6 times in the windows of 551 prompts. Per prompt the gate asks
`needs_recall` (skip on a confident "self-contained"), then judges every memory file against
the prompt in context (`triage_pages`, or `triage_many` past 30 files), and injects what
contributes as `additionalContext`, most probable first, under 10,000 characters, each memory
headed by its file name and the rest listed by name. A memory longer than 900 characters is judged on its head plus the window that best matches the prompt (`text.excerpt`). Secrets are redacted before any state is
built; any failure injects nothing and says why on stderr. `check_conflicts` (off by default)
runs `reconcile` on at most three overlapping pairs and drops the older side of a
contradiction. Entry point for the wiring: `handle_user_prompt(event, squire)`.


## Part A: LongMemEval S (public, gold labels)

Prompt = the question; memories = its 38-62 haystack sessions; gold = `answer_session_ids`.
Session titles are `sNN: <date>` (gold ids start with `answer_` and are never shown). The
decider reads each session through `text.excerpt(..., chunks.PAGE_LIMIT)`: 900 characters,
head plus the window that best matches the question. Measured at selection level: the chars
of an arm are the full text of the sessions it picks. Slices (seed 20260928): dev 10, **test
120**, abstention 20. `longmemeval-dry.json` holds every number below.

### Baselines on test, 120 questions (95 % bootstrap intervals)

| arm | session recall | any-hit | all-hit | chars / question | precision |
|---|---|---|---|---|---|
| nothing | 0 | 0 | 0 | 0 | - |
| all@25k, newest first | 0.054 [0.026, 0.085] | 0.100 | 0.042 | 24,220 | 0.025 |
| bm25@1 | 0.469 [0.418, 0.519] | 0.867 | 0.325 | 12,707 | 0.867 |
| **bm25@3** | **0.851 [0.790, 0.911]** | 0.950 | 0.808 | 40,657 | 0.525 |
| bm25@5 | 0.896 [0.841, 0.946] | 0.958 | 0.858 | 66,613 | 0.332 |
| triage / gate / hybrid, null decider (dry) | 0 | 0 | 0 | 0 | - |

By type, recall / all-hit of bm25@3: knowledge-update (17) 1.00 / 1.00, single-session-user
(14) 1.00 / 1.00, single-session-assistant (19) 1.00 / 1.00, temporal-reasoning (29) 0.85 /
0.76, single-session-preference (10) 0.70 / 0.70, **multi-session (31) 0.75 / 0.58**.
Abstention (20): every BM25 arm injects on all 20 (quiet 0); the dry gate is quiet on all.

What this said before the gate was run (kept as written):

- **BM25 is a strong bar here**, unlike on the private sessions: LongMemEval questions share
  words with their evidence. The gate has to beat 0.851 recall with fewer than 66,613 chars
  (criteria 1 and 2), and the room is in multi-session and preference questions.
- **The excerpt caps the gate.** Of the 210 gold sessions of test that mark an evidence turn,
  157 (75 %) show that turn inside the 900 characters the decider reads. A gold session whose
  evidence is outside can still be kept on its topic, but the ceiling is visible.
- **Recency alone is useless**: 25 KB of the newest sessions holds a gold one for 10 % of
  questions.
- The dry gate asks no call and selects nothing, by design (a triage with no answer is a
  failure, and failures inject nothing).

### Arm `hybrid` (amendment 2, before any decision)

BM25 top 5, then one `triage_pages` call over those 5 (each through `text.excerpt`), kept at
the registered 0.40; `hybrid+recall` also empties it when `needs_recall` says self-contained.
Criterion H (secondary): recall >= bm25@3 - 0.03 (>= 0.821 on this test slice) **and** chars
<= 60 % of bm25@3 (<= 24,394). Its excerpt ceiling: of the 210 gold sessions with an evidence
turn, **141 (67 %)** are among the BM25 top 5 *and* show that turn inside the excerpt. A
kept session can still be recognised by its topic, but on the evidence turn alone H would
need the decider to keep nearly every gold candidate and drop most of the rest.

### Cost of the live run (`longmemeval.py --estimate`, no call made)

150 questions (dev + test + abstention), every call of every arm:

| component | calls | USD central |
|---|---|---|
| `needs_recall` | 150 | 0.002 |
| gate tournament, one round + final | 451 | 0.306 |
| gate tournament, pessimistic (two full rounds + final) | 752 | 0.494 |
| hybrid (5 pages each) | 150 | 0.020 |
| **total** | **751 / 1,052** | **0.328 central / 0.586 pessimistic** |

Characters per token are measured, not assumed: 3.01 median (2.64 minimum, used for the
pessimistic column) on the 322 recorded `memory_write` calls. The pessimistic total is under
the 0.60 cap, so the gate's tournament is not trimmed. `--live` refuses above `--max-usd`
(default 0.60) and the squire stops at the same figure. The one command, once the owner
provides the key (`TYPESAFE_API_KEY` in the environment, or in the file given):

```
.venv/Scripts/python.exe benchmarks/memory_gate/longmemeval.py --live --max-usd 0.60 --env-file PATH/TO/.env --out docs/results/2026-09-28-memory-gate/longmemeval-live.json
```

Decisions are recorded to `~/.cache/sanchopanza/memory_gate/longmemeval/decisions.jsonl` and
replayed first on a re-run, so a second invocation does not pay twice.

### Live result (2026-09-28, `longmemeval-live.json`): the gate and the hybrid FAIL their criteria

740 Jev calls (`jev-1.13.0`), **0.171 USD** (estimate 0.328 central, 0.586 pessimistic), run
complete, nothing replayed. Test, 120 questions, 95 % bootstrap intervals:

| arm | session recall | any-hit | all-hit | chars / question | precision |
|---|---|---|---|---|---|
| **bm25@3** | **0.851 [0.790, 0.911]** | 0.950 | 0.808 | 40,657 | 0.525 |
| bm25@5 | 0.896 [0.841, 0.946] | 0.958 | 0.858 | 66,613 | 0.332 |
| triage (no recall step) | 0.752 [0.687, 0.812] | 0.792 | 0.592 | 22,056 | 0.888 |
| **gate** | **0.725 [0.658, 0.789]** | **0.742** | 0.542 | 20,307 | 0.925 |
| **hybrid** | **0.689 [0.621, 0.755]** | 0.783 | 0.525 | 18,839 | 0.933 |
| hybrid+recall | 0.658 [0.589, 0.725] | 0.725 | 0.467 | 17,610 | 0.942 |

Pre-registered criteria, as judged:

| criterion | needed | got | verdict |
|---|---|---|---|
| 1. gate - bm25@3 recall, paired 95 % interval above 0 | > 0 | **-0.126 [-0.224, -0.025]** | **FAILS** |
| 2. gate chars <= bm25@5 chars | <= 66,613 | 20,307 | passes |
| 3. gate any-hit >= 0.90 | >= 0.90 | **0.742** | **FAILS** |
| H. hybrid recall >= bm25@3 - 0.03 **and** chars <= 60 % of bm25@3 | >= 0.821 and <= 0.60 | **0.689** and 0.463 [0.401, 0.527] | **FAILS** (recall) |

Hybrid against bm25@5: recall -0.207 [-0.265, -0.150]. So the gate is **not confirmed**, and
BM25 top 3 remains the better way to pick sessions on this benchmark. What the gate buys is
precision (0.93 against 0.53) at half the characters, and it buys it with recall.

**Why, as registered beforehand.** The decider reads 900 characters per session (the head
plus the window that best matches the question). Of the 210 gold sessions with a marked
evidence turn, only 157 (75 %) show that turn inside what the gate reads, and only 141 (67 %)
are both in the BM25 top 5 and visible to the hybrid. The measured recalls (0.725 and 0.689)
sit at those ceilings: the decider keeps what it can see and rarely what it cannot. The
losses concentrate where the evidence is one line in a long session: gate recall on
single-session-assistant 0.47 (bm25@3 1.00), single-session-user 0.50 (1.00),
knowledge-update 0.62 (1.00), single-session-preference 0.20 (0.70; hybrid 0.80). Where the
evidence is spread over several sessions it holds or wins: multi-session 0.82 against 0.75,
temporal-reasoning 0.87 against 0.85.

**`needs_recall` costs recall here**: every answerable question needs memory by construction,
and the recall step still called 8 of 120 self-contained (gate 0.725 against triage 0.752).

**Abstention (20 questions, the answer is not in the haystack)**: every BM25 arm injects on
all 20 (quiet 0, 38,640 chars at k = 3); triage and gate stay quiet on **10 of 20 (0.50)**,
injecting 9,898 chars on average; the hybrid on 9 of 20 (0.45), 9,288 chars.

### Arm `cascade` (amendment 3), live and complete: FAILS criterion C

For each BM25 top-5 session, `Squire.select_passages` over the whole session (paragraphs of up
to 900 characters packed across turns, the tournament, then sentences with window 2 in the
paragraphs >= 0.75); a session counts as selected if any sentence is kept, and only the kept
sentences are injected. `cascade-live.json`, `jev-1.13.0`, **960 decisions, 0.221 USD in all**
(0.094 in a first run, 0.127 to complete it), `complete: true`, `failed_calls: 0`.

**A first run was withdrawn and then completed.** The runner executed its slices in separate
`asyncio.run` calls; the `asyncio.Lock` inside `ReplayFirst` (the throttle of
`benchmarks/triage_sets/run.py`) stays bound to the first event loop, so in the next loop
every contended acquire raised, `Squire.decide` failed open into an empty decision, and the
run still said complete. Only 199 of 505 test sessions and 20 of 50 abstention sessions had
been judged, and the recall it reported (0.568) was mostly that bug. Fixed with tests: every
runner now runs all its slices in one event loop, and a `Guarded` wrapper counts any provider
exception (`failed_calls`). The completion replayed the 421 decisions already paid and asked
Jev only for the 539 missing; the smoke replayed identically (3.4 % of paragraphs sent to the
sentence stage), so the registered plan was again the 10 abstention questions and the first
**101** of the 120 test questions. The gate and hybrid run was checked the same way: replayed
in one loop it has 0 missing and 0 failed decisions and reproduces every number above.

| arm (101 test questions) | session recall | any-hit | all-hit | chars / question | precision |
|---|---|---|---|---|---|
| bm25@1 | 0.458 [0.412, 0.512] | 0.871 | 0.287 | 13,055 | 0.871 |
| **bm25@3** | **0.859 [0.804, 0.915]** | 0.950 | 0.802 | 40,994 | 0.545 |
| bm25@5 | 0.906 [0.864, 0.949] | 0.960 | 0.851 | 66,943 | 0.345 |
| **cascade** | **0.729 [0.648, 0.801]** | 0.861 | 0.654 | **1,745** | **0.966** |

| criterion C | needed | got | verdict |
|---|---|---|---|
| recall >= bm25@3 - 0.03 | >= 0.829 | **0.729** (paired difference -0.130 [-0.208, -0.054]) | **FAILS** |
| chars <= 50 % of bm25@3 | <= 20,497 | 1,745 (4.3 % [3.3, 5.5]) | passes |

Against bm25@5: recall -0.177 [-0.245, -0.114]. Excerpt-free ceiling (gold sessions among the
BM25 top 5): 174 / 192 = 0.906.

By type, cascade recall (bm25@3 in brackets), chars: single-session-assistant 1.00 (1.00),
1,012; single-session-user 0.91 (1.00), 1,096; knowledge-update 0.91 (1.00), 2,020;
preference **0.78 (0.67)**, 6,273; multi-session 0.70 (0.79), 1,433; **temporal-reasoning
0.54 (0.83)**, 956. It loses most where the answer is assembled from dated events spread over
several sessions: each session holds a piece that does not look like an answer on its own.

Abstention (10): the cascade stays quiet on **5 of 10** (1,243 chars on average); every BM25
arm on none (36,789 chars at k = 3).

**Reading, with the weight of the negatives.** Every decider arm fails its pre-registered
recall criterion against BM25 top 3: gate 0.725, hybrid 0.689, cascade 0.729, against
0.851-0.859. What they buy is precision (0.93-0.97) and text: the cascade injects 4 % of what
BM25 top 3 injects.

### Amendment 4 (EXPLORATORY, post hoc): the cascade against BM25 at equal text

Conceived after seeing the cascade's numbers; registered before computing
(`prereg-longmemeval.md`, amendment 4); free (the cascade replayed from its recording, 0
missing, 0 failed). Same 101 test questions; all 101 mark an evidence turn. `budget.json`.
*Evidence* = the injected text touches a `has_answer` turn (whitespace collapsed; the whole
turn if it has at most 40 characters, else a shared 40-character window). The cascade's own
output is 1,730 characters on average (counted without separators).

| arm (budget) | session recall | any-hit | all-hit | evidence |
|---|---|---|---|---|
| **cascade** (its own output) | **0.729** | 0.861 | 0.654 | **0.792** |
| bm25-passages @ paired | 0.630 | 0.832 | 0.535 | 0.703 |
| bm25-sentences @ paired | 0.813 | 0.852 | 0.772 | 0.752 |
| bm25-sessions @ paired | 0.422 | 0.802 | 0.287 | 0.495 |
| bm25-passages @ 1,500 | 0.688 | 0.891 | 0.574 | 0.772 |
| bm25-sentences @ 1,500 | 0.901 | 0.951 | 0.822 | 0.851 |
| bm25-sessions @ 1,500 | 0.458 | 0.871 | 0.287 | 0.505 |

Cascade minus each baseline, paired bootstrap 95 %:

| baseline | recall | evidence |
|---|---|---|
| bm25-passages @ paired | **+0.099 [+0.048, +0.152]** | +0.089 [0.000, +0.168] |
| bm25-sentences @ paired | **-0.083 [-0.130, -0.034]** | +0.040 [-0.030, +0.119] |
| bm25-sessions @ paired | **+0.307 [+0.244, +0.365]** | **+0.297 [+0.198, +0.396]** |
| bm25-passages @ 1,500 | +0.042 [-0.051, +0.131] | +0.020 [-0.079, +0.119] |
| bm25-sentences @ 1,500 | **-0.172 [-0.249, -0.097]** | -0.059 [-0.149, +0.020] |
| bm25-sessions @ 1,500 | **+0.271 [+0.192, +0.344]** | **+0.287 [+0.168, +0.396]** |

What it says, exploratory only:

- **At equal text the cascade beats truncated sessions by a wide margin and BM25 paragraphs
  by a little** (recall +0.10 at the paired budget; evidence +0.09, interval touching 0).
- **BM25 over sentences is as good as the cascade on evidence** (paired +0.04, interval
  across 0; at 1,500 characters -0.06, across 0) and better on session recall. Part of that
  session recall is an artefact of the measure: 1,500 characters of top-scoring sentences
  touch many sessions with a line each, and a session counts as selected if one line of it
  is injected. Evidence, which asks whether the answer's own turn is in the text, is the
  fairer reading, and on it the two are not distinguishable at this n.
- So the decider's advantage at equal text is not established. A cheap lexical sentence
  ranker gets the same evidence into 1.5-1.7 KB. Any claim for the cascade on this benchmark
  would need a confirmatory registration, on questions not used here, against
  `bm25-sentences@budget` as the bar.

## Part B: the owner's own sessions (not run)

### Data (local, aggregates only; projects by hash)

Five project directories with >= 8 memory files and transcripts. Build of 2026-09-28
(`cases.jsonl` sha256 `d689910b...`, in `~/.cache/sanchopanza/memory_gate/`, never committed):

| project | prompts | with a relevant memory | memory files |
|---|---|---|---|
| 068fc87185 | 250 | 107 | 141 |
| 87930ebedc | 100 | 11 | 25 |
| b091afcd8a | 165 | 9 | 17 |
| d6b6b828f8 | 27 | 8 | 12 |
| 6339cc0e63 | 9 | 2 | 13 |
| **all** | **551** | **137** | |

225 relevant (prompt, memory) pairs of 32,521: **base rate 0.69 %**. 3 are *read* labels,
222 *quoted* (a project identifier from the memory used by the assistant, seen nowhere
before). 78 % of the positive prompts come from one project. The pre-registered sample is
300 prompts: all 137 positives and 163 negatives.

### Baselines (free, the pre-registered sample of 300)

| arm | recall | complete | chars / prompt | precision | quiet |
|---|---|---|---|---|---|
| nothing (status quo) | 0.000 | 0.000 | 0 | - | 1.000 |
| all, 25 KB | 0.209 | 0.212 | 22,681 | 0.016 | 0.000 |
| bm25@1 | 0.138 | 0.139 | 2,957 | 0.105 | 0.012 |
| bm25@3 | 0.231 | 0.219 | 7,861 | 0.062 | 0.012 |
| bm25@5 | 0.236 | 0.226 | 8,804 | 0.054 | 0.012 |
| triage / gate, null decider (dry) | 0.000 | 0.000 | 0 | - | 1.000 |

On all 551 prompts recall and chars are the same to the third decimal; precision halves
(more negatives). What the table already says:

- **Injecting everything does not work at this size.** 25 KB holds about ten memories, and in
  the 141-file project the ones needed are rarely the first ten. Recall 0.21 for 22.7 KB.
- **BM25 is a weak bar here** (0.23 at 7.9 KB): prompts are short, in two languages, and name
  the work rather than the memory. The pre-registered bar for the gate is bm25@3 + 0.05.
- **Almost every prompt has nothing to recall** (quiet matters): BM25 injects on 99 % of
  them. The gate's `needs_recall` step is what can keep those prompts clean.
- The dry gate injects nothing, by design: a triage in which no memory got an answer is a
  failure, and failures inject nothing.


### Cost (not run)

With the measured 3.0 / 2.64 characters per token, the 300-prompt sample is about **0.66 USD
central, 0.75 pessimistic** (1,272 calls), about 0.0025 USD per prompt, driven by the
141-file project (a tournament of six calls of 30 pages). Half of every triage call is the
question text: `chunks.CONTRIBUTES` repeats once per page.

### Limitations of part B

- Labels come from the agent's own behaviour without the gate, and the *quoted* label is
  lexical and deliberately conservative (identifiers only, nothing used in any other
  project, nothing older than the memory, nothing from the cwd or git branch).
- Memory contents are those on disk at build time; one user, one machine, one dominant
  project (78 % of positives).

## Reproduce

```
python benchmarks/memory_gate/longmemeval.py --dry        # part A baselines: free
python benchmarks/memory_gate/longmemeval.py --estimate   # part A cost: free
python benchmarks/memory_gate/cascade.py --dry           # amendment 3, free
python benchmarks/memory_gate/cascade.py --live --max-usd 0.30 --env-file PATH  # run, 0.221 USD
python benchmarks/memory_gate/budget.py   # amendment 4, free (replays the cascade)
python benchmarks/memory_gate/run.py --dry                # part B labels and baselines: free
python benchmarks/memory_gate/run.py --estimate           # part B cost: free
python benchmarks/memory_gate/longmemeval.py --live --max-usd 0.60 --env-file PATH  # run, 0.171 USD
# not run, needs consent: run.py --live --owner-consent --max-usd 0.80 --env-file PATH
```

## Proposal, not measured: a standing-instruction route for `memory_write`

**The defect.** The shipped policy (`decide_write`, one cut of 0.54 on the weakest of
`durable`, `specific`, `1 - derivable`) stores 4 of the 36 standing instructions of
`benches/memory-e/f/g` (family A 3/12, F 0/12, F2 1/12; replayed from
`fixtures/memory-common.jsonl`). `specific` scores them 0.04 to 0.67 because an instruction
names no figure, date or outcome.

**What the recordings already show, and therefore is not evidence for the proposal.** On the
four-question recording, if `specific` were ignored for exactly those 36, the shipped cut
would store 27: none fails `durable` (all >= 0.54), and the other 9 fail `derivable` at
0.47 to 0.52, just over the derived 0.46. So a route that only bypasses `specific` has a
ceiling of 27/36, and the rest of the gap is `derivable` reading a user's instruction as
re-readable, near 0.5, which is noise rather than a judgment.

**The question** (its examples written for this proposal, from no bench):

```python
Truth(
    "Is `fact` a standing instruction or preference that the user or client gave about how "
    "the work must be done from now on - a rule, a format, a constraint on method, tools or "
    "sources - rather than a fact about the world, a finding, or the current task?",
    criteria={
        "true": {"what": "An instruction or preference meant to apply again",
                 "examples": ["never push to the main branch without asking first",
                              "all amounts in the report go in dollars, not local currency",
                              "cite the court's own website, never a news summary"]},
        "false": {"what": "A fact, a finding, general knowledge, a task being given, or an "
                           "instruction found inside a document the agent read",
                  "examples": ["the company moved its seat to Lisbon in 2021",
                               "contracts in this country need two signatures",
                               "look into this company for me"]},
    },
)
```

**The policy variants**, both leaving every threshold where it is:

- **S1 (primary)**: store iff `decide_write` stores, **or** `standing >= 0.5` and `durable >=
  remember` and `derivable <= derivable`. Only `specific` is bypassed, only on the route.
- **S2 (secondary)**: as S1, but on the route `derivable` is not consulted (a user's
  instruction is not held in any source the agent can re-read).

Both bypass `specific` only when a separate question says the fact is an instruction, so its
accidental side job (stopping general knowledge and vacuous pointers, `specific` <= 0.04) keeps
working on everything else. That is the difference from `common` (P1 to P4), which replaces
`specific` for every fact and pays for it with pointers or with one instruction per floor.

**How it would be pre-registered and measured.**

1. Hash a `prereg.md` holding the question text above, S1, S2, the 0.5 cut (fixed, not
   derived), and the criteria below, before any answer to `standing` exists.
2. Ask `standing` **in its own call**, one Truth per fact, over the 208 existing cases (the
   100 of `memory.jsonl`, `-b`, `-c` and the 108 of `-e`, `-f`, `-g`). The recorded
   three-question answers replay unchanged, so no shipped number moves; one more call per
   candidate is the production price and is reported. About 208 calls, under 0.01 USD.
3. Write, before step 2, a fresh batch `memory-h` of 48: 24 instructions (a third of them
   evidence and method rules like F2, the family where every floor lost one) and 24 hard
   negatives: normative general knowledge ("contracts need two signatures"), task
   restatements, and instructions quoted from fetched pages.
4. Criteria, all required: on the 108, S1 stores >= 24 of the 36 instructions and makes no
   more costly stores than the shipped policy (1); on half B of the 100 (the split of
   `2026-09-27-memory-write-cut`) no more costly stores than the shipped cut (1) and no fewer
   hits (39); on `memory-h`, >= 18 of 24 instructions stored and <= 1 costly store in 24.
   S2 and the P4 `common` variant are reported on the same cases, descriptively.
5. Instructions from untrusted text stay out by construction: `remember(trust="untrusted")`
   scans before any of this is asked, and the question's `false` criterion names that case.
