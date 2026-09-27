# Changelog

## 0.3.0 (unreleased)

A tool window that follows the session without breaking the prompt cache, an interface for
self-improving harnesses, fetched-content scanning, a security review of all of it, and the
first end-to-end measurements of tool presentation with a real agent, including the ones that
do not favour this package.

### Added

- **`Squire.triage_pages` and `Squire.select_sentences`**: every candidate page asked in one
  call with the others in view, one probability per page; then, inside the kept pages, one per
  sentence. Confirmed on 300 HotpotQA questions nothing was chosen on: 98.3 % of supporting pages
  kept at 34 % of the text in one call, against 94.3 % at 53 % asking page by page in ten; with
  the sentence step, every supporting sentence in 90.3 % at 22 % of the text
  (`docs/results/2026-09-27-chunks/`).
- **`Squire.triage_many` and `points/hierarchy.py`**: `triage_pages` for any number of pages.
  Up to 30 it is one call; past that, balanced groups judged at a lenient first-round cut
  (`Thresholds.pages_first_round`, 0.18, derived) and the survivors judged together at 0.40, a
  tournament after LATTICE (arXiv:2510.13217). Pre-registered on HotpotQA with 100 pages per
  question: on 200 held-out questions both supporting pages kept in 96.5 % at 3.1 % of the text
  in 5 Jev calls; the groups alone 94.0 % at 4.3 %; BM25 at the same page count 50.5 %. The 90
  added pages are off-topic, and a third round is in the code and unmeasured; 0.53 USD
  (`docs/results/2026-09-27-hierarchy/`).
- **Provider `claude-cli`** (`providers/claude_cli.py`): `create("claude-cli", model=...,
  ceiling_usd=..., cache_path=...)` is an `LLMDecider` through `claude -p`, billed to the
  logged-in account and never to an API key (every `ANTHROPIC_*`, `CLAUDE_CODE_USE_*` and
  `AWS_BEARER_TOKEN_BEDROCK` variable is removed from the session). An isolated, tool-less session with a
  prefix of about 730 tokens (about 0.002-0.004 USD at list price per Haiku session), a hard
  ceiling checked before each spawn, a disk cache (`SessionCache`) that survives torn lines,
  and short prompts passed in argv, because under concurrency the CLI waits only 3 s for stdin.
  Numbers from this path are not interchangeable with API numbers without a check.
- **`Squire.check_done` and an opt-in Claude Code Stop hook** (`SANCHO_CHECK_DONE=1`,
  `sanchopanza install --check-done` wires it): before the agent may stop, one calibrated
  question over the last request and what followed it. On 655 AgentDojo trajectories labelled
  by the benchmark's own environment check, the agent's word is right 52 % of the time and the
  question 94 % (AUC 0.98); blocking below the derived cut was right 138 times in 147 held out.
  Never blocks twice in a row; any failure lets the stop through. Measured on AgentDojo tasks,
  not on coding sessions (`docs/results/2026-09-25-completion/`).
- **`Squire.triage_part`**: page triage for purposes with several parts. On multi-part HotpotQA
  questions it kept both supporting paragraphs in 93.3 % of 300 questions nothing was chosen
  on, at 52 % of the text, where BM25 with more text kept 80.3 % and `triage_page` at its
  shipped cut 19.7 %. Answering from what it kept, Haiku 4.5 through the Batch API scored
  69.0 % against 67.7 % from all ten, with 54 % of the tokens (`docs/results/2026-09-25-triage/`).
- **`providers.CascadeDecider`**: a cheap decider first, an expensive one only for the
  questions the cheap one was unsure of, with a threshold per question kind and no default.
  The shape of Claude Code's two-stage permission classifier with a calibrated first stage
  (`docs/results/2026-09-25-cascade/`).
- **`points.actions`**: would a careful operator have stopped this agent action? The first
  stage of a permission gate, measured on R-Judge and ATBench-Codex.
- **`Squire(redact=...)` and `sanchopanza.redact.redact_secrets`**: every state passes through
  the redactor before any provider sees it; a redactor that fails sends nothing.
- **`trust="untrusted"` on `remember` and `verify_edge`**: a fact or an edge taken from text
  the agent read is scanned for instructions first, and is not stored or committed when
  flagged or not fully scanned.
- **`Squire.fork()`**: a fresh squire with the whole configuration; the LangChain adapter uses
  it instead of copying private fields, which had dropped the redactor.
- **Recordings carry the option order** (`order_of`): two Choices that differ only in option
  order no longer share a replay key. On the `facts` point the order moves 3 to 4 labels in
  50, all inside the abstention band (`docs/results/2026-09-25-order/`).
- **`python -m sanchopanza`**, and a command line that survives a console that cannot encode
  what it prints (Windows cp1252 crashed `install` on a settings file with an emoji).

- **`sanchopanza.window.ToolWindow`**: a per-session tool window that opens narrow and only
  grows, on a new user turn and after a tool result once that result has passed the injection
  scan. On 97 AgentDojo trajectories and 40 three-task sessions it missed no needed group,
  where selecting once missed 6 and 124 (in-sample; `docs/results/2026-09-25-window/`).
- **`harness.messages_api.WindowedTools`**: the window rendered into the Messages API in the
  shapes `count_tokens` accepts. The whole catalog is deferred and `tools` never changes;
  groups surface through `tool_addition` system messages on Opus 5 (measured end to end) and on
  Opus 4.8 and Fable 5 and 5.1 (shape accepted by `count_tokens`, not run end to end), and
  through a `load_tools` tool answered with references-only results on Sonnet 5 and Haiku 4.5.
- **LangChain per-conversation windows**: `ToolSelectMiddleware(squire, key_of=thread_id)`
  keeps one append-only window per conversation, with its own meter.
- **Catalog prerequisites**: a group entry may declare `requires: [...]`; selections are
  closed over it in code and it is never sent to the model.
- **A `deferred` question in tool selection**: a request that defers its instructions to
  something unread ("do what the email says") keeps the whole catalog. `select_tools` is now
  measured: 91/97 AgentDojo tasks keep every needed group on the recorded run (a live run kept
  92/97 at 77 % less catalog), and a live run on a 248-group catalog kept 94/97 at 88 % less,
  against 38/97 for BM25 at the same budget
  (`docs/results/2026-09-24-tools/`).
- **`sanchopanza.evolve`**: the interface an adaptive, self-improving harness (RRSI-style)
  needs to tune this package without fooling itself: `Knobs` / `Edit` diffs, a hash `Split`
  with a counted holdout and a single-read fresh set, an `Evaluator` that replays recordings
  for free and refuses edits that invalidate them, a noise floor from Wilson width plus
  measured provider drift, `admit` with an edit budget and a cost rule, a refuted-hypothesis
  `Ledger`, a leak critic and a dormant-gate report (`docs/evolve.md`). Its offline demo finds
  nothing admissible above the floor, so the shipped thresholds stand.
- **Fetched-content scanning**: `Squire.scan_content` reads the whole text in overlapping
  windows (`max_windows` bounds the cost), with a free keyword layer in front of the question;
  either layer can flag and neither can clear the other. Off unless enabled with
  `SANCHO_SCAN_CONTENT`, `SANCHO_CONTENT_TOOLS` and `SANCHO_PURPOSE`. Flagged content is
  marked as untrusted in front of the model, never removed.
- **`sanchopanza install`**: builds the hook configuration from the same `HarnessConfig` the
  Guardian uses at runtime; prints by default and writes only under `--write`.
- **An injection bench harvested from AgentDojo v1.2.2** (`benches/agentdojo-injection.jsonl`,
  273 cases, labels by construction) and a `THIRD_PARTY_NOTICES` file carrying AgentDojo's MIT
  licence.
- **`memory_write` can ask the pre-registered fourth question, `common`** (opt-in:
  `write_questions(ask_common=True)`, `Squire.remember(ask_common=True)`,
  `memory.decide_write_common`). The default does not ask it.
- `Thresholds.deferred`, `Thresholds.window_add`: knobs that were borrowed from other points,
  split out at the same values. `Thresholds.derivable` is split out too and is set by the
  derived `memory_write` cut (below). `Thresholds.common_durable` / `common_derivable` hold the
  opt-in `common` path at the values it was measured at (0.70 / 0.75).

### Security fixes, from two adversarial reviews (security and code), each with a test

- A tainted window stays shut: after a blocked tool result nothing widens it until the next
  user turn. `load_tools` hands over nothing while the window is tainted or a scan is in
  flight, and a request that raced an unfinished scan is refused
  (`tests/test_security_fixes.py`).
- An exhausted budget does not open the catalog. Exhaustion is told apart from an outage
  (`Squire.exhausted`) and widens nothing, so an attacker cannot exhaust the budget with long
  documents to open every tool.
- The decision cap holds under concurrency: the meter reserves before the await
  (`Meter.reserve` / `Meter.charge`).
- One `load_tools` judgment per user turn, judged on the user's purpose with the model's
  `need` only as a clue, so a borderline group cannot be won by retrying.
- The Guardian passes the whole fetched text to `scan_content`; `content_limit` no longer
  truncates what the scan reads.
- A NaN, infinite or out-of-range answer is an empty answer at the contract boundary
  (`Answer.valid`, `tests/test_nonfinite_answers.py`), so it can never read as permission.
- An absent answer no longer reads as permission anywhere a policy acts: a downgrade needs the
  person check answered, an edge needs its direction, a memory needs `derivable`, a correction
  is not discarded as a duplicate, and a failed scan window is not counted as clean
  (`docs/results/2026-09-25-window/audit.md`). Replaying all 1,153 recorded cases changed no
  prediction.
- `Squire(decider)` tests the decider with `is not None`, so a falsy decider (a
  `RecordedDecider` holding only defaults) is not swapped for the null one.
- `accepts_tool_addition` matches exact model ids only; `WindowedTools` refuses a window that
  was never opened and declares a tool listed in two groups once.
- LangChain isolation: without `key_of` nothing is kept between requests, and each
  conversation gets its own meter.
- `sanchopanza install` is idempotent, never overwrites the first backup, writes atomically,
  escapes tool names in matchers, refuses non-object settings, and can turn content scanning
  off again.
- Release workflow: actions pinned to commit SHAs, a read-only default token, no persisted
  credentials. The sdist ships no session handoffs or raw run transcripts (302 entries).

### Fixed

- **`triage_many`: a round that prunes nothing no longer asks the same groups again.** It
  reused Jev's non-determinism as a second opinion and broke replay; the round's answers are
  reused, and each page reports the last probability it got. The hierarchy result stands:
  every one of the 200 held-out questions replays identically through `Squire.triage_many`
  (`tests/test_hierarchy_bench.py`).
- **`claude-cli`, hardened after code review**: the prompt always follows `--`, so a prompt
  starting with `-` is not read as an option; a `.cmd` / `.bat` shim is refused; ceilings must
  be finite and positive (a NaN disabled them); every `ANTHROPIC_*`, `CLAUDE_CODE_USE_*` and
  `AWS_BEARER_TOKEN_BEDROCK` variable is stripped from the session; sessions in flight reserve
  their budget and the last ones get what is left of the ceiling, passed as
  `--max-budget-usd`; a cancelled session's process is killed; an unknown cost is charged at
  the session budget; `count_cached=True` counts what the cache already cost; `effort` is part
  of the cache key; a torn cache line no longer swallows the next row.
- Benches refuse to overwrite a different registered pre-registration hash.
- `tools.decide` applies the deferral guard.
- The LangChain adapter selects once per conversation and only widens. It no longer
  re-selects on every model call, the pattern `benchmarks/cache/` measures at 4.15x the cost
  of selecting once. A turn the decider could not answer adds every group nobody answered
  for, so an outage never freezes the window.
- `decide_edge` reads the direction first and commits only on a confident direction. On 50
  cases with eleven reversed triples: 31/38 when deciding, `reversed` caught 4 of 11, 17 edges
  committed and 1 of them backwards (`docs/results/2026-09-24-fourth-batch/`).
- Error messages name the right distribution, `pip install sanchopanza[...]`.

### Changed behaviour a user may notice

- **`memory_write` stores on one derived cut.** `decide_write` stores iff the weakest margin
  `min(durable, specific, 1 - derivable)` is at least 0.54 (`Thresholds.remember` 0.54,
  `Thresholds.derivable` 0.46), where it was a conjunction at 0.70 / 0.70 / 0.75. Derived on
  half of 100 cases to an 80 % precision target at the Wilson lower bound, pre-registered: on
  the held-out half 39/49 with 1 costly store against 37/49 with 2 for the conjunction; on 108
  cases never used for any threshold 74 with 1 against 60 with 4. Pinned benches under the
  shipped policy: the fifty-case bench 200/212 (`memory_write` 29/34), the 124-case bench 82/88
  (it loses `mw-08`, a store at margin 0.51), and the substitution table 200/211 against 202 at
  a plain cut and 204 for Opus 5 (`docs/results/2026-09-27-memory-write-cut/`).
- **The console command is `sanchopanza` only.** The `sancho` alias is gone: `sancho` on PyPI
  is an unrelated package. `python -m sanchopanza` works as well.
- **Benches are scored with the thresholds the policy applies** (`tests/test_policy_in_force.py`):
  the loop points at `saturated` (0.70), injection only above `injection` (0.70). Scored this
  way, `check_loop` is 12/14 and 12/12 on the first batch and 46/50 and 50/50 with the second,
  with zero false alarms; injection is 27/28 on the public bench and 101/124 on AgentDojo.
  No threshold moved.
- **The end-to-end harness shares the cache prefix between tasks** the way a production
  harness with a fixed catalog does: a cache breakpoint on `system` for every arm, and one
  pre-warm request before tasks run in parallel (`benchmarks/agentdojo/e2e_window.py`). The
  cost ratios below are estimated from recorded usage on that basis
  (`benchmarks/agentdojo/reprice_shared_prefix.py`, `tests/test_cache_reprice.py`).
- Page redundancy uses its own `adds_nothing` knob at **0.59**, derived to a 90 % precision
  target (100 % held out), instead of the shared 0.80: more redundant pages are dropped, and
  `redundant` / `SANCHO_T_REDUNDANT` no longer affect it.
- `Guardian.after_tool` returns a `Note` (model context and operator text), not a string; the
  Claude Agent SDK PostToolUse output also sets `systemMessage`.
- `evaluate_plan` never returns tier `light`: plan lines do not ask `person_risk`, and a
  downgrade needs it answered.

### Measured

- **The tool window end to end** (`docs/results/2026-09-25-e2e/`, 6.8 USD): Sonnet 5 on 40
  AgentDojo tasks with a 74-tool catalog. Success pooled over runs: loading everything 70/80,
  the window 100/120, the platform's tool search 31/40, with no detectable difference at this
  n. Time: the window 0.91x of loading everything once the scan and the observe question run
  concurrently. Cost with the prefix shared, as an estimate: the window 0.77-0.88x of loading
  everything, the search 1.48x (`docs/results/2026-09-25-cache/`).
- **A real MCP catalog** (`docs/results/2026-09-25-wide/`, 398 tools, 167,937 tokens of
  definitions): success 7/9 loading everything, 8/9 search, 8/9 the window; cost with the
  prefix shared, as an estimate over every row, search 0.34x and the window 0.54x of loading
  everything. The window opened the 121-tool Google Workspace server in 11 of 17 tasks: the
  cost of a window is set by its coarsest group, and server-sized groups are the open problem.
  No distractor tool was called in any arm of run B (n = 5; run A did not record them).
- **Inside Claude Code**, which defers MCP tools behind its own search, a sanchopanza
  `UserPromptSubmit` hook changed nothing measurable (4/4 against 4/4 on built-in tools; 7/8
  against 7/8 with 329 MCP tools).
- **Pushing tools to Sonnet 5 without being asked** (`docs/results/2026-09-25-push/`): the API
  accepts a harness-written `load_tools` call, but after untrusted text the model refuses the
  payment tools it is handed (0/16 against 5/8 with everything loaded); only a load before the
  model's first move works, which equals opening the group blind. On Opus 5, `tool_addition`
  after the read held 7/8 against 8/8. A mechanism probe, not pre-registered. Not shipped.
- **The window is a capability-escalation path unless scanned**: without the scan, 24 of 56
  injected payloads got it to add the group the attacker needed; with it, 0 of 56, and no
  clean text was blocked (0 of 26).
- **Injection on third-party attacks** (`docs/results/2026-09-24-agentdojo/`): the question
  catches 101/124 AgentDojo payloads, a keyword list 115/124, the two together 120/124, with
  0 false alarms on 149 real tool outputs. End to end on AgentDojo's Slack suite
  (`docs/results/2026-09-24-agentdojo-e2e/`), undefended Sonnet 5 was compromised 0 times in
  105, so the control buys nothing there; marking flagged content cost 1 task in 42 and
  redacting it 65 points of utility under attack.
- **Page triage with the document sequence held fixed** (`docs/results/2026-09-24-fixed-sequence/`):
  input tokens -75.2 % [-86.8 %, -63.9 %] and correct answers 10/10 to 6/10. One result; the
  saving is the cost of not answering.
- **`memory_write`**: the shipped cut is in "Changed behaviour" above. It stores 4 of 36
  standing client instructions. With the opt-in `common` question, on a batch written before
  it was measured: 45/48, where the shipped cut scores 37/48 and the three-question
  conjunction 25/48, keeping 32 to 35 of the 36 instructions. A `specific` floor removes the
  junk `common` lets through at the price of about one instruction in twelve; both floors
  tried failed their "lose none" criterion by exactly one
  (`docs/results/2026-09-25-window/memory.md`). As one Choice question: 195/208 against
  130/208 for the three-question conjunction, but 13 costly errors against 11, a trade-off by
  the pre-registered rule (`docs/results/2026-09-25-pending/`); not adopted.
- **Answering from the in-context sets: the kept text answers as well**
  (`docs/results/2026-09-27-answers/`, pre-registered, Haiku 4.5 through the Claude Code CLI,
  the 300 confirmatory chunk questions). With the reply forced into one short field: all pages
  70.0 %, the kept pages 71.0 %, the kept sentences 70.7 %, sentences with no page gate 69.0 %;
  P21s, P22s and P24s hold, and the path check agrees with the API (CLI 67.0 % against the
  Batch API's 67.7 % on the same prompts). The claim is equality, not gain; 7.04 USD at list
  price against the subscription. The first run, with free-length replies, was negative as
  registered (81.0 %, 76.7 %, 76.0 %; P21, P22 and P24 failed; CLI 74.7 % against the API's
  67.7 %; 4.46 USD): its score counts a reply correct when the gold answer is contained in it,
  and replies grew with the context (median 30, 9 and 4 words).
- **Whole documents, not confirmed** (`docs/results/2026-09-27-longdocs/`, pre-registered):
  `triage_many` with the shipped cuts on 300 QASPER papers (49 paragraphs on average) kept all
  evidence in 94.7 %, 16.3 points over BM25 at the same paragraph count, but 48.9 % of the text
  against a criterion of 25 %: the recall transfers, the compression does not. Replayed with the
  fixed tournament (54 new calls once TypeSafe had credit again) the numbers move by rounding
  and now replay from the recording. A second pre-registered stage, `select_sentences` inside
  the kept paragraphs (QASPER's highlighted evidence, 261 questions, 5,308 calls, 0.30 USD),
  is not confirmed either: every gold sentence kept in 83.1 % at 31.5 % of the text (criteria
  85 % and 25 %), 31 points over BM25 with the same text.
- **The permission cascade, re-read post hoc** (`docs/results/2026-09-27-cascade-frontier/`,
  free): the registered verdict stands (Opus 5's accuracy at 57 % of its cost on R-Judge,
  over the 50 % criterion). Labelled as post hoc: tau 0.35 reaches 93.2 % (Opus 93.2 %) at
  25.2 % of the cost; prompt caching moves the ratio by at most 0.7 points; one-sided
  escalation does not help. The comparison with Sonnet 5 (P1, P2, P9) is not run.
- **The permission cascade, confirmed on unseen data** (`docs/results/2026-09-27-cascade-frontier/`,
  pre-registered: tau 0.45 from R-Judge, ATBench-Codex never shown to Opus, Opus 5 through the
  Claude Code CLI). Held-out half, of record: cascade 80.3 % against Opus 79.9 % at 38.8 % of
  its cost, all three criteria hold. The other half, registered after that verdict, replicates
  (77.8 % against 75.8 %, 38.3 %), and so do all 500 (79.1 % against 77.8 %, 38.5 %). On this
  set Jev alone is as accurate as Opus (78.2 %) and lets through fewer unsafe actions (false
  allows 14.9 % against 25.7 %). 15.07 USD at list price against the subscription.
  `CascadeDecider` ships no threshold; 0.45 is the documented value.
- **`verify_edge` and `relate_facts`, diagnosed** (`docs/results/2026-09-27-edge-facts/`,
  free): no code change. For a Choice answer, `confidence = (p_top - 1/k) / (1 - 1/k)` to
  within 0.022 over 7,162 recorded answers, the analogue of `|2p - 1|` for Truth, so one
  `relax` gate serves every option of `relate_facts` alike.
- **`verify_edge` asks `direction` by roles** (who does, holds or is the source of the
  relation), licensed by the pre-registered fifth batch (`fifth-batch.md`, 30 + 30 new cases,
  kappa 1.00, 120 calls, 0.0034 USD): 10 of 12 reversed edges caught against 5, 6 of 8 in the
  passive against 1, and no wrong commit against one. `graph.edge_questions(direction_by_roles=
  False)` keeps the old wording for replays; `eval.bench` uses it for the recorded edge benches.
  The `unrelated` gate at 0.5, examples on `unrelated` and a `direction` cut were not licensed.
- **The provider is not deterministic**: the same state asked twice of the pinned
  `jev-1.13.0` moved by up to 0.09 within a day. Decisions within about 0.1 of a cut are coin
  flips between runs, so every number is quoted from a recording and pinned by a replay test.
- **Tool selection needs no covering constraint**: 300 of 300 needed groups kept on requests
  of one to three parts and groups, when each part names its domain. Its misses are groups the
  request does not name (`docs/results/2026-09-25-window/`, section 8).
- At AgentDojo's context sizes pure tool search is the cheapest arm in modelled dollars, and
  the window becomes the cheapest somewhere between 4k and 20k tokens of base context; end to
  end with the prefix shared, the search was an estimated 1.48x of loading everything.
- `window_add` could not be derived: 13 positives in 4,268 answers. It stays equal to `tools`.

## 0.2.0 (2026-09-24)

Eight new decision points, the first measurement of *where* a decision may be applied, a
defect in this package's own thresholds found by attacking its own thesis, and the smallest
contract change that admits an image.

### Fixed, and the most important line in this release

- **Two gates on one number were one gate at the stricter value.** For a Truth answer from
  this model class, `confidence` is exactly `|2p - 1|`: 651 recorded answers across three
  independent runs, zero deviation. So a policy asking for both `p >= a` and
  `confidence >= c` was asking for `p >= max(a, (1 + c) / 2)`, and the threshold named in the
  configuration was not the one in force. `memory_write` was configured at 0.70 and enforcing
  0.80; source redundancy at 0.80 and enforcing 0.875; the recall and extraction gates had a
  dead clause. The redundant gates are gone, **no threshold value changed**, and the gap
  between the shipped policy and a plain 0.5 cut fell from eight decisions to three
  (78/88 to 85/88, AUC 1.00 throughout). `tests/test_policy.py` pins the identity as a canary.
- **The default model is pinned, not an alias.** `jev-1.13.0` rather than `jev-latest`, which
  is what the vendor's own model page asks for when thresholds have been tuned, and this
  package is nothing but tuned thresholds. The squire also warns once if two model versions
  answer within one session.
- **A provenance criterion written into free-text prose did not work, and the answer was
  already in the decision.** `triage.decide` takes `allowed_kinds` / `denied_kinds` and
  filters on the source kind in code, with no extra call. Found by the steerability bench.


### Added

- **Agent memory** (`points/memory.py`): `Squire.remember` (is this fact worth storing),
  `Squire.reconcile` (does it contradict, duplicate or complement a stored one) and
  `Squire.needs_recall` (does this turn need a lookup at all). Recency is never asked of the
  decider: the harness's timestamps decide it in code, because dates are the model class's
  declared weakness, and a collision with unknown recency is flagged, not resolved.
- **Knowledge-graph construction** (`points/graph.py`): `Squire.gate_extraction` (is this
  chunk worth a generative extraction call) and `Squire.verify_edge` (does the text state
  this triple, in this direction). Both mentions are matched in code before any call.
- **Source redundancy** (`points/triage.py`): `Squire.triage_redundant`, for the fetch-heavy
  workloads the end-to-end A/B could not exercise at 1.8 fetches per task.
- **The loop guard** (`points/loop.py`): `Squire.check_loop`, which advises when the goal
  already looks met or a pending check repeats one already run. It appends a note; it never
  denies. It exists because redundant verification is the largest measured waste in an agent
  loop: 18x the clean-run cost, 2.5x the tool calls, no gain in success (arXiv:2608.01347).
- **124 labelled cases** across `benches/{memory,graph-build,retrieval,loop}.jsonl`, a
  recorded run in `fixtures/new-points.jsonl`, results in
  `docs/results/2026-09-24-new-points/`, and `tests/test_new_point_benches.py`, which replays
  them for free in CI.
- **`benchmarks/cache/`**: four arms measuring what narrowing a tool catalog costs when it is
  done once, on alternate turns, or afresh every turn.
- **`docs/where-it-pays.md`**: which decisions are worth taking at all. Three economies
  (substitution, avoidance, affordability), one anti-economy (the prompt cache), a catalog of
  levers ranked by how sure we are, and four things not to use a decision model for.
- **Steerability bench** (`benches/steerability.jsonl`, 14 flipped pairs): the same
  document and topic with only the criterion changed, scored by pair accuracy, because a
  scorer whose inputs are only (query, document) scores 0 % there by construction. 11 of 14.
  Written to check a marketing claim that turned out to be false: instruction-following
  rerankers exist, are cheaper than this model, and four public benchmarks measure them.
  `docs/results/2026-09-24-steerability/`.
- **Attachments** (`sanchopanza.media`): `state` may carry an `Attachment` at any depth, and
  the questions do not change. No vendor sells a calibrated non-generative multimodal
  decision model today - across seven image-classifier vendors not one publishes an ECE - but
  the shape is proven by an independent paper, and a local vision model behind `LocalDecider`
  works now. A text-only provider **refuses** an attachment rather than dropping it.
- **`Thresholds.audit`**: a pre-registered, reproducible sample of decisions marked in the
  journal for re-labelling, so a threshold can never be tuned on cases picked afterwards.
- A warning when the tool selection changes within a session, which is the 4.15x mistake.
- `Thresholds.remember`.

### Changed

- **A fourth invariant: cache-safe by construction.** A decision acts only where acting
  cannot invalidate a cached prefix. Measured over 8 turns on claude-sonnet-5: narrowing a
  58-tool catalog once is **43 % cheaper**; narrowing it on alternate turns is **14 % dearer**
  than never narrowing; narrowing it afresh every turn reads **zero** tokens from cache and
  costs **4.15x** the arm that decided once. Same decision, different moment, opposite sign.
- `HarnessConfig.cheap_search_available` is documented as a **probe, not a flag**, and the
  README example no longer shows `lambda: True`. A capability that is declared rather than
  probed routes work into a hole while fail-open never fires: in production that produced a
  report beginning "this research could not be carried out", 75 % cheaper than delivering.
- `docs/savings.md` now states the comparison that applies inside a warm loop. A cached read
  costs 0.1x base input, so for tokens already in a prefix the multiple is 4.8x on a
  Sonnet-class model, not 48x. Which column applies depends on whether the decision replaces
  a call or avoids tokens.
- The bench runner scores the new points, and computes AUC for gates whose label is a word
  rather than a boolean.
- `docs/paper.md` is draft 3: Sections 5.10 and 5.11, a rewritten analysis, four new threats
  to validity and twelve items of future work.

### Known limitations, measured

- **Three decisions still separate the policy from a plain 0.5 cut** (85 of 88 against 86 of
  88, AUC 1.00 throughout) after the redundant-gate fix above. Those are not tuned away: the
  rule is 50 cases and a second annotator per point, and this bench has 12 to 20 and one.
- **The steerability bench has no baseline.** An instruction-following reranker over the same
  pairs is the comparison that matters and it has not been run, so that bench says what this
  layer does, not what it does better.
- **The `duplicate` branch of `reconcile` never fired** on 16 cases. In practice the point is
  a contradiction detector with a safe default.
- **One confident error on the edge check**: a true triple rejected at confidence 1.00, where
  the text said "declares unconstitutional" and the triple said "annuls". It is why that
  point is specified as a filter in front of a human, not as an autonomous committer.

### Also in 0.2.0: work landed since 0.1.0 and not previously released

#### Fixed

- **Triage judged a long document on its first 1,500 characters.** On a 10,000-character page
  the part that answers the purpose is usually in the middle, so the decider was reading a
  preamble that genuinely did not mention it and dropping the page. `sanchopanza.text.excerpt`
  now sends the head plus the window that best matches the purpose words, deterministically and
  with no extra tokens. Documents at or under the limit are returned unchanged, so no bench
  number moved and the recorded replay still matches byte for byte.
  Found by the new end-to-end A/B, where it made a run cost twice as much and return nothing.

#### Added

- `benchmarks/ab/`: the end-to-end A/B. Same agent, same tasks, one arm with the squire and
  one without, over a fixed corpus built from files already in this repository. Paired
  bootstrap over (task, repetition) pairs, ground truth pinned to a string unique to one
  document, two retrieval conditions and two document sizes, with a spend cap.
- `docs/savings.md`: what the layer costs and the break-even arithmetic, with exact token
  counts and no invented saving percentage.
- `docs/governance.md`: branch protection, the PyPI environment (including the tag rule the
  release workflow needs) and how to release.
- `skills/sanchopanza/SKILL.md`: a skill for coding agents wiring this into a harness.
- `.github/CODEOWNERS`, a release workflow with trusted publishing, a logo and a README.

#### Changed

- Decision point `tools`: which groups of a tool catalog a request needs (one Truth per group,
  chunked and merged; `Thresholds.tools`, in doubt keep; `always` pinned by code; never empty).
  Motivated by harnesses that bind every schema on every step. Not yet measured on a public bench.
- `Squire.select_tools`.
- Harness adapter `sanchopanza.harness.langchain.ToolSelectMiddleware` for LangChain / LangGraph /
  deepagents `AgentMiddleware` (`wrap_model_call` and async), tested in shape.
- Extra `langchain`.

## 0.1.0 (2026-09-21)

First public release, extracted from the decision layer of a production research agent.
Distributed as `sanchopanza` under Apache 2.0; `import sanchopanza`, command `sanchopanza`
with `sancho` as a short alias.

- Contract: Choice / Score / Truth questions, calibrated Answers, Decider protocol.
- Ten decision points with measured question texts and pure policies: routing, search, triage (with injection), citation, plan lines and dependencies (with DAG cleanup), report review, shell guard, entity alignment, fact relation, closed-vocabulary classification (with other).
- Squire: fail-open, per-job budget, journal event per decision.
- Providers: TypeSafe Jev (HTTP, no SDK), recorded / recording, null, LLM forced to schema (Anthropic and OpenAI completers), local handlers, fallback and per-point routing.
- Harness adapters: Claude Agent SDK hooks, Claude Code command hook, MCP server, OpenAI-Agents-style guardrail, harness-agnostic Guardian.
- Eval: bench runner, statistics in plain Python, calibration by primitive.
- Public benches (pseudonymized) and the working paper.
