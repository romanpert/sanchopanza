# C6: the paragraph tournament's excerpt by a window around the best match, on fresh MLQA questions (pre-registration, DRAFT)

Status: **draft, not sealed.** Before the seal: an independent `revisor-prereg` review against
the code, then `python -I benchmarks/b6_es/c6_window.py seal` writes `prereg.sha256` (the sha256
of this file and of `c6-window-run.cmd`, its two local values read as placeholders).
Instrument commit: `364c04dd5ef1350b0d45f86729ecb384b8ad1a84`.

## Question

`Squire.select_passages` shows its paragraph tournament each paragraph's first 900 characters
(`chunks.PAGE_LIMIT`). In B6 (docs/results/2026-10-16-b6-es/) Spanish kept the answer sentence in
85.8 % of 614 articles against English's 91.7 %, and the gap was smallest where the answer
sentence started inside those 900 characters (−4.5 points). Does showing a long paragraph by a
window around its best word match to the question, instead of its head, keep the answer sentence
more often in Spanish, without costing English recall or keeping more text?

## The option under test (opt-in, default unchanged)

`select_passages(..., excerpt="window")` (`src/sanchopanza/squire.py`, `points/chunks.py`,
`text.match_window`): for a paragraph longer than 900 characters, the sentence sharing the most
distinct words with the question (accent-folded, stopwords out, words of two letters or more,
earliest on a tie) is found; if it ends inside the first 900 characters, or no sentence shares a
word, the paragraph is shown exactly as today. Otherwise whole sentences around it (one after,
one before, in turn) up to 900 characters of whitespace-collapsed text are shown, with `[...]`
where text is left out. The sentence stage reads whole paragraphs in both arms. `excerpt="head"`
(the default) is every published run; B6's recordings replay unchanged with it (`analysis-docs.json`
reproduced but for its `head` field).

## Already known before this run: the free ceiling (labels only, no model answer)

| | B6's 614 (looked at) | fresh 836 (this run) |
|---|---|---|
| Spanish: questions the window changes (some paragraph shown differently) | 283 | **400** |
| Spanish: answer sentence enters the tournament's view / leaves it | 34 / 4 | **37 / 3** |
| English: questions changed | 300 | **457** |
| English: enters / leaves | 23 / 0 | **30 / 2** |

On B6's recordings, the 34 Spanish questions whose answer sentence the window brings into view
were kept in 12 (35 %), against 89.2 % where it was in view under both; the 23 English ones in 11
(48 %) against 93.7 %. On the published QASPER inputs (480 questions, English papers) the window
brings 4 answer paragraphs' sentences into view and takes 7 out, but the tournament kept 29 of
30 answer paragraphs outside the view anyway: no change expected there.

**This selection is exploratory.** Three excerpts were compared on B6's inputs by this ceiling
alone (the head; `text.excerpt`, head third plus a character window: fewer answer sentences in
view than the head; a sentence window always, and the head unless the best match lies past it).
The last one changes the fewest paragraphs (672 of 5,588 long Spanish ones, against 3,365) for
the same net gain, and was chosen. No Jev answer to a window request has been seen.

## Data

- MLQA v1.0 test (CC BY-SA 3.0): every question B6 did not use (its pages, docs and smoke ids)
  whose Spanish article is one of B6's 614 docs articles, with its English twin (same id): **836
  questions in 289 articles**, built offline from B6's article cache at B6's pinned revisions
  (CC BY-SA 4.0) by `c6_window.py build`, the gold sentence located by B6's own code
  (`b6_build.doc_row`; 340 exclusions, counted in `bench-manifest.json`). The built file's
  sha256 (raw bytes) is `c040e91417bc2daf78e4d2d428595dc06e0ae19479ec62bbbbaddb533b7841cb`
  (`INPUT_SHA256`); `paid`, `dry` and `report` refuse another.
- Labels by construction (B6's): the gold sentence holds the MLQA answer span. No label comes
  from a model.
- The questions are fresh; the articles are B6's (other questions on the same articles).

## Arms

jev-1.13.0 (`DEFAULT_MODEL`), shipped thresholds and limits, no answering model, the whole
article sent (no preselection):

| arm | language | excerpt |
|---|---|---|
| Dh-es | Spanish question and article | head |
| Dw-es | Spanish | window |
| Dh-en | English twin | head |
| Dw-en | English | window |

**Only changed questions are asked**, per language: 400 Spanish, 457 English. On the others both
arms send the same requests, get the same answers and keep the same sentences: their difference is
exactly 0, and the effect over all 836 is the changed questions' effect times their share
(reported, not voted). Within a question the head arm runs first and the window arm reuses its
answer to every identical request (the asker's memo and the recording): the arms differ only
where a request differs. Spanish and English alternate first with the question's launch position.

## Metrics

- **Recall** (primary): every gold sentence of the question kept (B6's `all_gold`).
- **Text kept**: kept characters as a share of the article's sentence characters (B6's
  `kept_share`).
- Intervals: paired, by cluster bootstrap over Spanish articles (10,000 resamples, seed
  20261015, `l4_stats.paired_binary`'s `ci95_cluster` and `c6_stats.mean_ci`); exact McNemar
  reported. Item-bootstrap intervals are reported, not voted.

## Verdict rule (applied by `c6_window.py report`, `c6_stats.verdict`, as written)

On each language's changed questions, with lo/hi the 95 % cluster-bootstrap bounds of the
window − head difference:

1. If lo(English recall) ≤ −0.02: **"not adopted: English recall may fall by 2 points or more"**.
2. Else if lo(Spanish recall) ≤ 0: **"not shown: no Spanish recall gain"**.
3. Else if hi(text kept) ≥ +0.01 in either language: **"Spanish recall gain, but more text kept
   than the margin"**.
4. Else **"window confirmed: Spanish recall up, English not worse, text within the margin"**.

What each licenses. Rule 4 makes `excerpt="window"` a measured option for `select_passages` on
encyclopaedic articles, both languages, at jev-1.13.0; whether it becomes the default is a later
decision (QASPER's ceiling says no change on papers; not measured there). Rule 3 says the gain
costs text and names neither side the winner. Rules 1 and 2 leave the option a candidate.
Nothing here measures `triage_pages` (B6's pages bench: the window brings 2-4 Spanish answers of
300 into view, too few to test), an answering model, or the Spanish−English gap as such (the gap
under each excerpt on questions changed in both languages is reported, not voted).

Reported, not voted: recall on the questions whose answer sentence enters the view (the
mechanism); the answer string anywhere in the kept text; recall over all 836 questions per
language; the absolute text kept per arm.

## Power

Assumed from B6's recordings: the questions whose answer sentence enters the view reach the
in-view rate (Spanish 0.353 → 0.892), those where it leaves fall to the out-of-view rate. That is
**+4.7 points on the 400 changed Spanish questions** (+2.2 over all 836) and +2.8 on the 457
English ones. Jev's draw-to-draw noise on a redrawn request is not known; with a share r of
changed questions flipping each way by noise alone (normal approximation, clustering ignored):

| r | Spanish: P(lo > 0) | English: P(lo > −0.02) |
|---|---|---|
| 0 | 0.99 | 1.00 |
| 0.02 | 0.88 | 0.97 |
| 0.04 | 0.74 | 0.87 |
| 0.06 | 0.62 | 0.76 |

## Cost and caps

The free dry run (`c6_window.py dry`, B6's stub, the memo shared as in the run): 14,396 calls
(Dh-es 5,016; Dw-es 1,388; Dh-en 6,195; Dw-en 1,797), **4.31 USD** at `CappedDecider`'s
pessimistic reservation, 3.24 at B6's billed cost a call (2.5277 USD over 11,202 calls). B6's
stub over-counted sentence calls by 1.8 times, so the expected spend is **about 2.5-3.3 USD**.
Hard cap **6.00 USD** in the ledger at a fixed path, `~/.cache/sanchopanza/c6-window/ledger.jsonl`,
launches beside it in `launches.jsonl`. Claude: 0.

`paid` refuses, before the key is read, unless: it was started from `c6-window-run.cmd` or a copy
differing only in its two local values; the input has its sha256; the dry run's pessimistic
estimate fits in what the cap leaves on the ledger; the seal matches this file and the launcher;
HEAD descends from the instrument commit and `src/`, `benchmarks/b6_es/`, `benchmarks/paid_once.py`,
`benchmarks/jev114/l4_stats.py` and `c6-window-run.cmd` are identical to it, nothing uncommitted
under them; the launch rule allows a launch; on a first launch no recording exists; no other
`paid` of the lot holds its lock. Then, in one event loop: `jev-preflight` (outside the ledger),
the live client (`JevDecider`, jev-1.13.0, long context and images off, a 429 not retried) built
inside it, every call through `CappedDecider` and recorded in `fixtures/c6-window/recording.jsonl`
(hashed keys, no text), at most 4 in flight, never retried. The first cap refusal, 401/402/403/429,
5xx or loss of connection stops every later call; three failures in a row of any kind do too.

**Launch rule.** One launch and at most one relaunch (`paid_once.may_launch`), none after an HTTP
402, a 429 or the cap. A relaunch replays what was recorded and asks the rest. While a relaunch
is allowed, `report` refuses to score with calls unanswered; after it, an unanswered tournament
group keeps its paragraphs (the package's rule: in doubt, a page enters) and the number of
unanswered calls is reported.

**Launch.** From a `git worktree add --detach` at the seal commit, by WMI in its own process group
(`CreateFlags=512`), outside any Claude Code session, never between 02:00 and 08:00; the input is
built there first (`c6_window.py build --data <B6's data folder>`, free). Stopped only by PID.
