# Pre-registration: prune a coding agent's context by decision, against the cheap masks

Written 2026-09-28 before any decider call of this run. `benchmarks/context/run.py --live`
refuses to spend unless the sha256 of this file (line endings normalized to `\n`) matches
`prereg.sha256`, and `tests/test_context_bench.py` pins the same hash.

## Why

At compaction, `Squire.prune_context` keeps every message and stubs the old tool results
nothing needs (rules first, then one in-context decision; stubs archived and readable). The
arm to beat is not only an LLM summary: on SWE-bench Verified, masking old observations
(M = 10) matched LLM summarization at about half the cost (Lindenbauer et al., "The
Complexity Trap", arXiv:2508.21433). A widely installed plugin, fast-jev-compaction, asks two
questions per call at a 0.5 cut and has never been measured.

## Data

Real Claude Code sessions on the owner's machine, read from `~/.claude/projects/*/*.jsonl`
by `benchmarks/context/build.py` and stored only under `~/.cache/sanchopanza/context/`,
redacted with `sanchopanza.redact.redact_secrets`. Nothing from a session is published; only
aggregates are.

- **Admission**: a project directory whose name contains `sanchopanza` or `sancho` and none
  of `indagis`, `farmacia`, `empresa`, `labzero`, `personal`, `vida`, `innovate`,
  `redes-sociales`, `investigacion`, `memory`. Main thread only (no subagent sidechains).
- **Unit**: one context of a session (the stretch between two compactions). The cut is the
  first message at which the cumulative characters (text, tool inputs, tool results) reach
  60 % of the context, moved forward by one message if it would separate a tool_use from its
  result. History = before the cut, future = after.
- **Size floor**: the history holds >= 40 tool results and >= 150,000 characters of them.
- **Secrets**: a session where a redactor pattern matches a string that looks live (a
  private-key block, or 24+ characters, entropy >= 3.5 bits, no placeholder marker) is
  dropped whole.
- **Sample and split**: at most 40 units, drawn with seed 20260928. Sessions are ordered by
  sha256(`20260928:<session hash>`) and whole sessions go to **dev** until dev holds
  round(15/40 of the units); the rest are **test**. Units are recorded by hash, not by path.
- **Minimum to run**: the live run happens only with >= 8 dev units and >= 12 test units.
  Below that it is not run, and this folder reports "not measurable on this dataset".
  Widening admission is the owner's decision and is made by amending this file (new hash)
  before any call, never after.

On the day of writing, the admission rule admits 72 sessions of this package's own
`claude -p` benches and no unit passes the size floor: the run is blocked on data.

## Labels (a lexical proxy, declared as one)

A history tool result is **NEEDED** when the future's assistant text and tool inputs (never
tool results) contain at least one distinctive token that appears in that result and nowhere
in the history outside tool results. Distinctive: code-shaped identifiers of 6+ characters
(with `_`, a digit, an inner capital, or all capitals), file paths and their last two
components, numbers of 4+ digits, hex strings of 7-40 characters, and quoted strings of 8-120
characters on a line naming an error. A token found in more than max(3, 5 %) of the history's
tool results is a stop token. Secondary labels, reported beside and never mixed in:
`needed_before_refetch` (the use precedes any future tool result showing the token again),
`needed_sole` (the token is in this result only), `reread` (the future repeats the same tool
and input). The proxy misses results that informed a decision without leaving a token, and
credits results for tokens the model would have written anyway.

## Arms

1. `keep_all`: nothing pruned.
2. `last_3`: the API's `clear_tool_uses_20250919` at its default keep of 3.
3. `mask_10`: observation masking, the last 10 tool-calling turns keep their results
   (arXiv:2508.21433).
4. `rules`: `context.rules.triage_rules` alone; undecided results kept; stubs archived.
5. `fastjev`: the fast-jev-compaction replica (`points.context.fastjev_*`), its own cut 0.5.
6. `sanchopanza`: rules, then `points.context.prune_questions` in context (tournament past 30
   candidates), at the cut derived below; unanswered kept; stubs archived.

Arms 5 and 6 run on `jev-1.13.0` (pinned), each through `RecordingDecider` into
`~/.cache/sanchopanza/context/recordings/`, so every later analysis is a free replay. The
recordings hold session content and are not published.

## Metrics

- **Freed**: history tool-result characters an arm takes out / all of them (pooled over units).
- **Recall (primary)**: NEEDED results kept literally / NEEDED results, pooled. A stub counts
  as lost; **recoverable** (needed results stubbed by an archiving arm) is reported apart.
- **Needed characters lost.**
- 95 % intervals: percentile bootstrap over units, 2,000 resamples, seed 20260928. Paired
  comparisons resample the same units for both arms. McNemar on pooled needed results is
  reported for the record only (results within a session are not independent).

## Derivation of `context_keep` (dev only)

The sanchopanza arm is planned once at `context_keep = 0.0`; the final cut is then applied
offline. Over 0.00..1.00 in steps of 0.01, the chosen cut is the **highest cut whose pooled
dev recall of NEEDED is >= 0.95**; if none reaches it, 0.00, and the miss is reported. The
cut is fixed before the test split is scored.

## Criteria, on the test split

- **P1 (primary)**: sanchopanza, at the derived cut, frees at least as much as `fastjev`
  (pooled point estimate) and keeps more NEEDED results: pooled recall difference > 0 with
  the lower bound of its paired 95 % interval > 0.
- **P2**: the same against `mask_10`.
- **P3**: sanchopanza's pooled test recall is >= 0.90 (the dev target less 5 points).
- **P4 (secondary)**: `rules` alone frees >= 20 % of the history's result characters at
  pooled recall >= 0.95.

If sanchopanza frees less than a baseline, the criterion against that baseline fails: keeping
more by freeing less is not a win. Any criterion that fails is a negative result and is
reported with the same weight as a positive one, in this folder and in `../README.md`. Every
number is published whether it favours the package or not.

## Cost

`run.py --estimate` prints the expected and worst-case Jev calls, input tokens and USD from
the states the points would send, before any call. The run refuses if the worst case exceeds
`--max-usd`, and `--max-usd` may not exceed **1 USD**, split between the two decider arms;
each arm's `Squire` meter is a hard stop at its share. A run stopped by the ceiling is
reported as incomplete, not re-run.

## Amendment 1 (before any measurement), 2026-09-28

Written before any decider call. The free arms had been run on nothing (0 units); no Jev
arm has been run on any data.

**Why.** The admission rule above admitted 0 units: no project directory on the machine is
named after this package, and the only admitted sessions (this package's own one-command
`claude -p` benches) are far below the size floor. Private sessions are excluded on purpose
and stay excluded. A public source also makes the run reproducible by anyone.

**Data source, replacing the one above.** `nebius/SWE-rebench-openhands-trajectories` on
Hugging Face, license **CC-BY-4.0**, 67,074 trajectories, revision
`35455389ab51bf5e2306bfd436ef72d0f98bf882` (Qwen3-Coder-480B-A35B-Instruct in OpenHands
v0.54.0 on real GitHub issues). A seeded sample of 300 rows (15 pages of 20 at random page
starts, seed 20260928) through the public datasets-server rows API into
`~/.cache/sanchopanza/context/public/` (`benchmarks/context/public.py`). The trajectories carry
structured tool calls and full outputs; OpenHands tools are mapped to the Claude Code names
the rules read (`execute_bash` -> `Bash`; `str_replace_editor` view -> `Read` with
`offset`/`limit` from `view_range`, create -> `Write`, edits -> `Edit`; other tools keep their
names), and the mapping is written in `public.py`. The system message is dropped. A unit is one
trajectory; its session is its `trajectory_id`. The Claude Code source stays in the code, off
by default, and is not used in this run.

**Size floor changed** from 40 results / 150,000 characters to **30 results / 100,000
characters** in the history: the registered floor admitted 19 of the 300 rows, the new one 124
(before the live-key drop, 5 rows). Everything else is unchanged: the 60 % cut, the labels,
the live-key drop, the 40-unit seeded sample, the dev/test rule (15 dev, 25 test), the arms,
the metrics, the derivation of the cut and P1-P4.

**Secondary metric added** (reported, never used in P1-P4): **token recall**, the share of the
distinctive tokens the future used from any history result that are still in at least one kept
result. It exists because the primary label is per result: a stubbed read whose lines survive
in a later, kept read of the same file counts as lost in recall but loses nothing here.

**Cost at the amended dataset** (`run.py --estimate`, from the states the points would build):
sanchopanza about 52 calls, 1.08 M input tokens, 0.046 USD (worst case 82 calls, 0.073 USD);
fastjev 77 calls, 1.15 M tokens, 0.048 USD. The 1 USD ceiling stands.

## Amendment 2 (before any measurement), 2026-09-28

Written after the run registered above was published (negative on P1-P4) and before any
decider call of the two simulations below. They replay the autopilot
(`sanchopanza.context.arrival`, the `mask` compaction arm, the `memory_gate` recall store)
offline on the same 40 units, labels, split and seed (`benchmarks/context/simulate.py`).
Criteria are judged on the **test** split (25 units); **dev** is reported as a sanity check
only. **No cut is derived**: every threshold is the registered default of the code as written
today (`arrival.Settings()`: gate 6,000 characters, 20,000 for a result that reads as a
failure, minimum saving 20 %, sentence stage on; `Thresholds()`: `pages_first_round` 0.18,
`pages_in_context` 0.40, `document_paragraphs` 0.75; recall `K = 5`, `--query text`, mask of
the last 10 acting turns and the last 6 messages). Model `jev-1.13.0`, every decision recorded
to `~/.cache/sanchopanza/context/recordings-autopilot/` for free replay, hard ceiling
**0.60 USD for both simulations together** (each run refuses when its worst-case estimate
exceeds its `--max-usd`). Each simulation runs in one event loop; every decider call is
counted, and a run with any failed or empty call, or calls in more than one event loop, is
marked incomplete and reported as such, not re-run into a better number.

### Arrival

Population: history tool results the arrival gate sends to the decider (at or above the
threshold). For each: the agent-facing characters (cut text plus the arrival header with an
80-character archive path, or the whole result when the cut passes it through) and, for
NEEDED results, whether every future-used token (`labels.hits`) survives literally.
Everything cut is archived; a NEEDED result that lost a token is reported as **recoverable**,
never as kept.

Free baselines at **matched characters per result** (each gets exactly what the arrival cut
kept of that result, markers included; no marker charged to them): **head+tail** truncation
(half each; issue #99 of fast-jev-compaction found it hard to beat for trimming inside a
result), **BM25 blocks** (the same blocks as the arrival cut, ranked by BM25 against the same
purpose, best first while they fit, in original order), **random blocks** (seeded by unit and
call). `benchmarks/context/baselines.py`, `criteria.py`.

- **A1 (primary)**: arrival keeps literally more of the NEEDED results' future-used tokens than
  head+tail at the same characters: pooled token retention, arrival minus head+tail, paired
  bootstrap over units (2,000, seed 20260928), lower 95 % bound > 0.
- **A2**: saving >= 40 % of those results' characters (pooled, header included).
- **A3**: NEEDED all-token retention (share of NEEDED results with every used token kept) >= 90 %.
- Reported beside, not judged: the same against BM25 blocks and random blocks, all-token
  retention per arm, the saving without the header.

### Recall

The history masked as the autopilot's compaction masks it; every masked result is an archive
entry. Before each future assistant message, a query built **only from what exists before it**
(latest user prompt and the previous assistant message's text), BM25 top 5 over the entries not
yet injected, one in-context `triage_pages`, kept entries injected (their best-matching passage,
`memory_gate.BODY_LIMIT` characters). A NEEDED masked result is a **hit** when injected at or
before the message that first uses one of its tokens. **Leakage audit**: a hit whose query
already held one of its needed tokens; it must be **0**, or the recall run is invalid and its
criteria are not judged.

- **R1 (primary)**: hit rate of the Jev recall beats BM25@1 (BM25 alone injecting its top 1
  every step): hit-rate difference with paired bootstrap lower bound > 0, **and** the Jev recall
  injects no more characters than BM25@1 in total on test.
- **R2**: the same against BM25@3, descriptive only.

### Reporting

Estimated before registration (`simulate.py --estimate`): arrival 331 calls, 0.128 USD
(worst case 780 calls, 0.273 USD); recall at most 1,024 calls, 0.148 USD. Every criterion is
reported pass or fail as registered, on test, with its interval; a negative outcome is
published with the same weight as a positive one, in this folder and in `../README.md`.
