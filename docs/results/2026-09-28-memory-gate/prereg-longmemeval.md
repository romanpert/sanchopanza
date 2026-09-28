# Pre-registration, part A: the memory gate on LongMemEval (public, gold labels)

Written 2026-09-28, before any number on this data was computed (the file was downloaded and
its fields and sizes inspected; no arm was scored). `prereg-longmemeval.sha256` holds the
sha256 of this file (LF line endings); `tests/test_memory_gate_bench.py` pins it and
`benchmarks/memory_gate/longmemeval.py --live` refuses to spend while it does not match.
This is the **primary** measurement of the gate. The private-data design in `prereg.md` is
**part B, not run**: it would send the owner's redacted memories and prompts to a third party
and needs his explicit consent first.

## Data

LongMemEval (Wu et al., 2024, MIT), split S, cleaned release: `longmemeval_s_cleaned.json`
from the Hugging Face dataset `xiaowu0162/longmemeval-cleaned`, sha256
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`, kept in
`~/.cache/sanchopanza/memory_gate/longmemeval/`, not redistributed. 500 questions, each with
38-62 chat sessions (median 48, median 10,111 characters each) and gold
`answer_session_ids`; 30 are abstention questions (id ending `_abs`), whose answer is not in
the haystack.

## Mapping to the gate

- Prompt = the question text. Memories = the haystack sessions. A session is rendered as
  `role: content` lines. Its title is `sNN: <date>`; **session ids are never shown** (gold ids
  start with `answer_`, which would leak the label).
- What the decider reads per session is `text.excerpt(session, question, chunks.PAGE_LIMIT)`:
  the head plus the 900-character window that best matches the question's words
  (`memory_gate.pages_of`). Most sessions are longer, so this caps what triage can see; the
  share of gold sessions whose evidence turn (`has_answer`) falls inside that excerpt is
  computed for free and reported as the ceiling the excerpt imposes.
- `needs_recall` is asked with no `topics`. Every non-abstention question needs memory by
  construction, so here the recall step can only lose; its skip rate is reported.
- Measured at **selection level**: an arm chooses sessions, and the characters it costs are
  the full text of the sessions chosen. The 10,000-character render cap of the hook is not
  applied (one median session is 10 KB); it is a harness setting, not what is measured.

## Arms

| arm | selection |
|---|---|
| `nothing` | none |
| `all@25k` | newest first by haystack date, each session taken whole if it still fits under 25,000 characters |
| `bm25@k`, k = 1, 3, 5 | the k best BM25 scores of the question over full session texts, score > 0 |
| `triage` | `Squire.triage_many` (via `memory_gate.triage_memories`), kept sessions |
| `gate` | `triage`, but nothing when `needs_recall` says self-contained |

No cut is derived. Shipped thresholds as registered: `act` 0.75, `pages_in_context` 0.40,
`pages_first_round` 0.18. Provider `jev`, model pinned `jev-1.13.0`. Both calls are made for
every question, so `triage` and `gate` come from the same answers.

## Slices

Non-abstention ids sorted, shuffled with `random.Random(20260928)`: the first **30** are
**dev** (pipeline check only, never judged), the next **150** are **test**. The 30
abstention questions are a separate stratum, run with test and reported apart.

## Metrics (per arm, on test; 95 % percentile bootstrap over questions, 2,000 resamples, seed 20260928)

- **recall**: gold sessions selected / gold sessions (micro).
- **any-hit**: share of questions with at least one gold session selected.
- **all-hit**: share of questions with every gold session selected.
- **chars**: mean characters of the sessions selected, per question.
- **precision**: gold selected / selected (micro).
- By `question_type`: recall, any-hit, all-hit, chars.
- Abstention stratum: **quiet**, the share of questions with nothing selected.

## Criterion (all three on test, to call it confirmed)

1. `gate` recall - `bm25@3` recall > 0, with the paired bootstrap 95 % interval of the
   difference above 0.
2. `gate` chars <= `bm25@5` chars (point estimates).
3. `gate` any-hit >= 0.90.

Reported whatever the outcome. `triage` vs `gate`, every `bm25@k`, `all@25k`, the types, the
abstention stratum and the excerpt ceiling are descriptive. Nothing moves in code on this.

## Cost and cap

`longmemeval.py --estimate` prints the expected calls, tokens and USD for dev + test +
abstention from the real states (central 4 characters per token, pessimistic 3, and a
pessimistic tournament of two full rounds before the final). `--live` refuses if the
pessimistic estimate exceeds `--max-usd` (default 0.60), and the squire's budget is set to the
same cap; a run that hits it is reported as incomplete.

## What this does not measure

- Sessions are chat logs, not Claude Code memory files (one fact each, a few hundred
  characters). The gate sees an excerpt of a long session here and usually the whole of a
  memory file in the hook.
- Whether the answer gets better. That needs a reader model; it is a later, separate test.

## Amendment 1 (2026-09-28, after `--estimate` only, before any arm was scored)

The first version was hashed as
`17f6964d8642ed5d0cb7d0fb80244bbb5992e8650116387b297865598216f370`. Its estimate assumed 4
(central) and 3 (pessimistic) characters per token. Measured on the 322 recorded
`memory_write` calls of `fixtures/memory-common.jsonl`, the JSON body is **3.01** characters
per billed token (median; minimum 2.64), so the estimate now uses 3.0 and 2.64. With the
slices above that put 210 questions at 0.43 USD central and 0.79 pessimistic, over the 0.60
budget. The slices shrink, and nothing else changes:

- **dev**: the first **10** shuffled answerable questions (pipeline check, never judged);
- **test**: the next **120**;
- **abstention**: the 30 `_abs` ids sorted, shuffled with the same seed, first **20**.

Criteria, metrics, arms and seeds are unchanged.

## Amendment 2 (2026-09-28, before any decision was asked)

Amendment 1 was hashed as
`000e0a426fdc9f59e10a08c1668b88b7888e4802506a779eb5c91c311f29b2a0`. Since then only free
numbers exist (`--dry`: the BM25, recency and null-decider arms; `--estimate`). No Jev call
has been made. One arm is added, with its own criterion; nothing above changes.

**Arm `hybrid`.** The BM25 top 5 sessions (score > 0, as `bm25@5`), then one
`Squire.triage_pages` call over those 5 with the question as `purpose`, each session read
through `text.excerpt(session, question, chunks.PAGE_LIMIT)` (head plus the window that best
matches the question), kept at the registered `pages_in_context` (0.40). The kept sessions
are injected; none if the decider answered none. **`hybrid+recall`** is the same selection,
emptied when `needs_recall` says self-contained, from the recall answer the gate already
asks (no extra call). Both are reported.

**Criterion H (secondary; judged on test, reported whatever the outcome):**
`hybrid` recall >= `bm25@3` recall - 0.03 **and** `hybrid` chars <= 60 % of `bm25@3` chars
(point estimates). Reported with it, descriptively: the paired bootstrap intervals of
`hybrid - bm25@3` and `hybrid - bm25@5` recall and of the chars ratio, `hybrid` against
`bm25@5`, and the excerpt ceiling among the hybrid's candidates (gold sessions in the BM25
top 5 whose evidence turn is inside the excerpt, over all gold sessions with one).

**Cost.** One more call per question over 5 pages. Estimate for the 150 questions, every
component: 1,052 calls and 0.586 USD pessimistic (a second full tournament round for the
gate, 2.64 characters per token), 0.328 USD central; the hybrid alone is 150 calls and 0.02
USD. It is under the 0.60 cap, so the gate's tournament is **not** trimmed. The squire's
budget stays 0.60 and a run that hits it is reported as incomplete.

## Amendment 3 (2026-09-28, after the gate and hybrid live run, before the cascade is measured)

Amendment 2 was hashed as
`f97f64e9e1c5d14a23ba53a1a577be4a351168dc2e5a4bb0883fd332f7d1ee71` and judged on it: the gate
fails criteria 1 and 3, the hybrid fails H (`README.md`). Everything above stays as judged.
One arm is added. Its criterion is written here before any cascade decision exists; the only
new free numbers are `cascade.py --estimate` and the calibration below.

**Arm `cascade`** (`benchmarks/memory_gate/cascade.py`). The BM25 top 5 sessions (as
`bm25@5`); for each, `Squire.select_passages` over the WHOLE session with the question as
purpose: the confirmed paragraph tournament (`triage_many`), then `select_sentences` with a
window of `document_window` (2) in the paragraphs at or above `document_paragraphs` (0.75).
A paragraph is consecutive text of the session packed up to 900 characters
(`chunks.PAGE_LIMIT`), across turns, each turn's first piece prefixed with its role, a piece
longer than that split by sentences; titled by the turns it spans. A session is **selected**
if any sentence of it is kept; a session in which the decider answered no sentence is not
(failures inject nothing). **Injected text is the kept sentences only**, and its characters
are the arm's chars. No excerpt: the tournament reads every paragraph whole.

Reported on the test questions it runs on, against `bm25@1/3/5` recomputed on the same
questions: session recall, any-hit, all-hit, injected chars, precision (bootstrap 95 %),
paired intervals of `cascade - bm25@3` and `cascade - bm25@5` recall and of the chars ratio,
by type, and the **excerpt-free ceiling**: gold sessions among the BM25 top 5 over all gold
sessions. Abstention: quiet and chars.

**Criterion C (judged on test):** `cascade` recall >= `bm25@3` recall - 0.03 **and**
`cascade` chars <= 50 % of `bm25@3` chars (point estimates, same questions).

**Budget: 0.30 USD, hard, and how the slice is fixed under it.** Tournament cost is known
exactly from the paragraphs; the sentence stage depends on how many paragraphs reach 0.75,
which nothing measured yet. Characters per billed token, measured on the 740 recorded calls
of the previous run: in-context page calls 3.96 median, 3.34 minimum (used for the
tournament, central and pessimistic); sentence calls are unmeasured here and take 3.96 and
the `memory_write` median 3.0. `--estimate` for 3 smoke + 120 test + 10 abstention questions:
0.229 USD central / 0.274 pessimistic with no sentence call, 0.270 / 0.383 if 5 % of
paragraphs reach sentences, 0.310 / 0.491 at 10 %. So the run is staged, in one invocation:

1. **Smoke**: the first 3 dev questions, live. They measure `s`, the share of paragraphs
   sent to the sentence stage. Never judged.
2. **Plan**: pessimistic cost per question with share `min(1, 2s)`. The first **10**
   abstention questions (of the 20, seeded order) are taken first, then the **largest prefix
   of the 120 test questions, in their seeded order**, whose pessimistic total fits
   0.30 minus what the smoke spent. If fewer than **60** test questions fit, the run stops
   and that is reported.
3. **Run** the planned slice. The squire stops at 0.30 USD in total; a run that hits it is
   reported as incomplete. Only the cascade is asked: the gate and hybrid answers are not
   replayed, so their recorded cost does not count against this cap.

## Amendment 4 (2026-09-28): EXPLORATORY, post hoc, free

Amendment 3 was hashed as
`091d5fb12a649e3b8326e55d4953ae24eef7ce371ffe3ecb95df98803b35f772` and judged on it: the
cascade fails criterion C (`README.md`). **This amendment was conceived after seeing the
cascade's numbers**, so nothing in it is a confirmatory test and nothing is judged against a
criterion; it is written down before it is computed only so that its definitions cannot move
with its results. No Jev call is made: the cascade is replayed from its recording
(`decisions-cascade.jsonl`) on the same **101** test questions.

**The question it asks**: does the cascade's selection beat BM25 when both inject the same
amount of text?

**Budgets**, per question: (a) **paired**, the cascade's own injected characters on that
question (zero when the cascade injected nothing); (b) **fixed**, 1,500 characters.

**Baselines at a budget** (every haystack session of the question, not only the top 5):

- `bm25-passages@budget`: every session split into the cascade's paragraphs
  (`cascade.paragraphs_of`), all paragraphs ranked by BM25 against the question, injected in
  that order until the budget; the last one is cut to fit exactly.
- `bm25-sentences@budget`: the same at sentence level (`text.split_sentences` of each
  paragraph, the unit the cascade injects).
- `bm25-sessions@budget`: sessions ranked by BM25 (as `bm25@k`), their text injected in that
  order and cut at the budget.

**Measures**, for these baselines and for the cascade at its own output:

- session recall, any-hit and all-hit as before: a session counts if any injected character
  comes from it;
- **evidence**: over the questions whose gold sessions mark an evidence turn (`has_answer`),
  the share whose injected text touches at least one evidence turn: after collapsing
  whitespace on both sides, an evidence turn of at most 40 characters appears whole, or a
  longer one shares a 40-character window (step 20) with the injected text;
- mean injected characters (the paired budgets make them equal to the cascade's up to cuts).

Paired bootstrap intervals (seed 20260928, 2,000 resamples) of cascade minus each baseline,
for recall and evidence. Reported whichever way it goes, in a section marked exploratory.
