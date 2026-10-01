# Changelog

## 0.3.0 (unreleased)

A tool window that follows the session without breaking the prompt cache, an interface for
self-improving harnesses, fetched-content scanning, a security review of all of it, and the
first end-to-end measurements of tool presentation with a real agent, including the ones that
do not favour this package.

### Added

- **Memory v3, just in time** (`install --memory`, still off by default). When the agent opens
  or changes a file, it is given the records of earlier requests that changed that file (the
  two newest, once per session, code only); recall at a prompt now runs only at a session's
  first live request, with the decider at 0.8, and not at all without a decider.
  - **v4: which record, by the lines in view.** Each record keeps prints of the lines it wrote
    (never shown); at a Read the record whose lines the agent sees most is given, nothing when
    it sees none, and at an edit the one whose lines it edits, else the newest. On SWE-chat
    development against v3 (the two newest per file): precision 0.603 to 0.730, recall 0.944
    unchanged, noise 0.049 to 0.038, 13 % fewer characters. The decider's cut at a session's
    first request moves from 0.7 to 0.8 (same recall, higher precision). After a review: prints
    per file, words only (a formatter's quotes and commas do not count), no imports, decorators,
    secret-like lines or failed edits, and a line belongs to its newest writer.
  - **Measured on real people's sessions** (SWE-chat: 60 groups of one person on one public
    repository, sealed; `docs/results/2026-10-01-memory-real`): on the held-out half, 95.0 % of
    requests with a related earlier record had one in view, 55.9 % of what was given was
    related, and 3.4 % of requests with nothing related were given anything. The previous
    design (recall at every prompt, decider at 0.2): 62.2 %, 6.6 % and 26.3 %.
  - **Upgrading:** run `sanchopanza install --memory` again. The new `PostToolUse` and
    `SessionStart: compact` entries are only written by install; without them an existing
    install records and, with a decider, recalls at a session's start only.
- **Label a corpus** (`sanchopanza.label`, `sanchopanza label`, the `label_file` MCP tool in
  `--tools label`). One closed rubric over a `.jsonl`, `.csv` or `.txt`, `classify`'s question
  and p1 gate per item, columns out (label, p, margin, provider, reason), a cache with an age, a
  spend cap, and a cascade when a `CascadeDecider` is behind the squire.
  - **Measured, pre-registered:** 89.3 % on AG News and 98.0 % on DBpedia-14, against Claude
    Haiku 4.5's 83.0 % and 98.0 % on the same questions, at 1/70 to 1/95 of its cost.
  - **The margin is not a second signal:** p1 - p2 separated right from wrong labels no better
    than p1 (AUROC 0.722 against 0.723, 0.902 against 0.903), so the gate stays on p1.
- **Rank a page's elements for the next action** (`sanchopanza.browse`, `sanchopanza browse`, the
  `rank_elements` MCP tool in `--tools browse`). Reads a Playwright accessibility snapshot or HTML
  into elements by code, with no dependency, and ranks them with a top-k tournament of in-context
  questions.
  - **Measured on Mind2Web:** the registered first design failed (R@10 71.0 %, bar 80 %); its
    final round was the fault. With the two rounds mixed (`blend=0.5`), confirmed on 142 new
    steps: 89.4 % in the top 20 and 82.4 % in the top 10, against 38.7 % and 23.2 % for BM25.
  - **Given only the top 20 or 30, in page order, an answering model chooses as well as from
    the whole page** (registered, 82 new steps): Claude Sonnet 5 52.4 % and 50.0 % against
    51.2 %, within the registered bound, at an eighth of the cost. The first try showed them in
    rank order and lost 5 points; in 6 of its 7 lost steps the target was shown, so the fix was
    the presentation: `browse.in_page_order` keeps the page's order and says which of a repeated
    line each element is. `render`, the CLI and `rank_elements` use it.
  - **A hook that prunes browser snapshots** (`harness.browse_hook`, opt-in, not
    recommended): in registered Claude Code sessions it saved on some samples and not on others
    (Playwright MCP: 12.9 % on six tasks, 12.4 % on twelve with the interval crossing zero,
    nothing clear on twelve more; playwright-cli: about 5 % on twelve, nothing on twelve more).
    Questions about position cost answers; it now passes them through (`asks_for_position`). It saved nothing at first, with `playwright-cli`
    and in its first Playwright MCP run; the transcripts showed five faults of the hook, all
    fixed with tests: Claude Code replaces an MCP result past its token limit with a notice before
    any hook runs (the hook now reads the saved result from its own session's `tool-results`
    folder), the agent's own searches, narrowed reads and targeted snapshots were cut, the goal
    lost the user's question (`browse_goal`), and recovery read the whole archive instead of
    grepping it.
  - **An unnamed element is described by its classes and the element holding it**
    (`elements_from_html`, default; `describe_unnamed=False` turns it off): an SVG with class
    `add-wishlist-new__icon` reads "looks like: add wishlist". Registered against a control that
    asks Jev again on the same groups: R@1 +3.5, R@10 +1.4 [-1.4, +4.2], R@20 0.0 on 142 new
    steps. A first registered test without that control failed its bound at R@20 (-1.4
    [-3.5, 0.0]); the control fell exactly as far, so that drop was the noise of asking again.
- `Squire.fork(thresholds=...)`: a copy with another ceiling for one job.

- **Candor: an agent's report held against what it did** (`sanchopanza.candor`,
  `python -m sanchopanza.harness.candor_hook`, `python -m sanchopanza.candor
  status|release|check`).
  - **Ledger:** built by code from the hooks.
  - **Rules:** deterministic say/do rules, which raise false success, denied edits and
    deletions, claimed actions that never happened, unread citations, inputs substituted in
    silence, undisclosed test edits and consequential actions, changes on disk with no tool call,
    and touching the monitor.
  - **Lock:** a sticky lock that refuses every tool call until a person releases it. It fails
    closed.
  - **Second opinion:** Jev, optional, which only adds notes.
  - **Measured:**
    - on a pre-registered confirmation round, 96 % of misstated reports stopped and 0 of 111
      honest sessions;
    - 9 of 12 real misreports stopped;
    - Jev at AUC 0.98 against Haiku 4.5's 0.68.
  - **It needs the four-line status block:** on prose alone, 24.6 %.
  - **Round 3** (176 new sessions, four new kinds of pressure, pre-registered): 95.3 % of
    misstated reports stopped again and 0 of 126 honest sessions, but 0 of 22 real misreports
    whose falsehood lies outside the record (silent failure, truncated data, a missing suite).
  - **v4** (round 4, 94 new sessions, pre-registered): reads an error printed by a call that
    exited 0 and the workspace snapshot. 105/105 misstatements and 1/61 honest sessions
    stopped; round-3 kinds 6/8 on new sessions; a check that could not run 0/4 (G3 fails).
    The hook now asks for the status block on each prompt (`SANCHOPANZA_CANDOR_ASK_BLOCK`,
    default `prompt`; `stop` holds a report without it once).
  - **On public data** (errata-bench, MALT, tau2-bench): 7 of 10 registered hypotheses fail;
    without the status block the lock catches no real misreport, and `check_done` does not
    carry to tau2's reward. See `docs/results/2026-09-29-candor-external/`.
  - **v6** (`candor.inputs`): URL pieces and harness paths are never inputs, and a file
    attached with `@` counts as read. In requests over 600 characters code no longer locks
    `substituted_input`: the frontier's `input` question asks, at review. Rounds 1-4 are
    unchanged; on errata-bench (in sample) the flags on accepted answers go from 7 to 0.
  - **Round 5** (68 new sessions, pre-registered, v6): 0/39 honest sessions and 62/63
    misstatements locked. The review tier caught 23 of 29 real misreports; the frontier added
    10 findings, all right, none on a negative. 4 of 6 hypotheses hold. New failure mode:
    agents that **write the missing input themselves**.
  - **v6 on held-out data** (SWE-chat, 277 turns of 300 real Claude Code sessions,
    pre-registered): 32 `substituted_input` flags against v5's 721, and locks on 1.8 % of turns
    against 18 %. A blind reader found no real substitution in 200 flagged pairs, so O2 has no
    verdict and O3 fails (0 % against 0 %). `docs/results/2026-09-30-candor-inputs/`.
  - **v7 candidate** (`candor.fabricated`, post hoc, unconfirmed): code locks a fabricated input
    only in a short request that names the file as a source. Otherwise the frontier's
    `authored` question asks, at review. Replay: 0 of 1,938 verdicts change.
  - **Seen on a real Indagis bug** (`docs/results/2026-09-30-indagis-scene/`, three sessions a
    side): candor caught a report claiming a read that never happened, raised two false
    `unchanged_output` locks on a file the prompt named as context, and its lock, one file per
    machine, held two unrelated sessions. Next: scope the lock per project or session, and
    stop `unchanged_output` from reading "the result X writes" as "change X".
  - **The first round is reported in full.** It was registered and mostly failed.

  See `docs/candor.md` and `docs/results/2026-09-29-candor/`.
- **Repository search and one select-among-many path** (`sanchopanza.select`,
  `context.repo`, the `find_in_repo` MCP tool, `python -m sanchopanza.context.repo`).
  The repository is cut into fragments by code, BM25 (`text.BM25Index`, now the package's
  one BM25) keeps a shortlist, and `triage_many` judges it in context when there is a key.
  On 117 SWE-bench Verified issues, pre-registered: a gold file first in 51.3 % and in the
  top five in 65.0 %, against 13.7 % and 35.0 % for whole-file BM25, at 0.0016 USD per issue
  (`docs/results/2026-09-29-find/`). **With an agent** (Haiku 4.5, 27 paired SWE-bench issues,
  the tool offered, not imposed, pre-registered): the agent called it in 6 of 27 sessions, and
  first-file hits were 17 against 16 without it, at the same cost, one `Read` fewer (E1 and E2
  fail, E3 holds; `docs/results/2026-09-30-find-e2e/`). Adoption is the open question. Also:
  `python -m sanchopanza.harness.mcp --tools
  archive,find,decisions` (one server, any sets; the decision tools had no command before),
  `find_in_repo` in the Codex config (`--find`), an opt-in free hint of likely files on each
  prompt (`SANCHOPANZA_FIND_ON_PROMPT`), and providers `clm` (a self-hosted CLM through the
  Jev client; run against a real `clm-serve` on a CPU encoder on 2026-09-30: it works end to
  end, and zero-shot it agrees far less than Jev on the benches, e.g. injection 12/28 against
  27/28, `docs/results/2026-09-30-clm-cpu/`) and `llm` from the environment, which now says so on stderr
  instead of falling back to no decider in silence. See `docs/what-it-adds.md`.
- **Autopilot for Claude Code, opt-in and experimental** (`sanchopanza install --autopilot`,
  `harness.autopilot`). Measured end to end, pre-registered, and **worse than Claude Code's own
  compaction on our tasks**: native summary 5/7, lean masking 3/7
  (`docs/results/2026-09-28-context-lean/`). Keep the native compaction as the default. The
  earlier 12/12 against 6/12 is retracted (see Measured). Offline, the arrival cut and the
  decider in recall did not beat free baselines (`docs/results/2026-09-28-context/`). The agent never asks for
  context reduction: a tool result over 6,000 characters can be cut on arrival (`PostToolUse`,
  `updatedToolOutput`, the tool's own output shape) to the blocks the current task needs
  (`context.arrival`, `context.blocks`), prose blocks at p >= 0.75 down to sentences with window
  2, the full text archived in `.sanchopanza/archive/` (which ignores itself in git) and named
  in one line; archived output and memory files are recalled by BM25 then one in-context triage
  (`memory_gate.recall`, the Amendment 2 "hybrid" shape) on each prompt and after tool calls,
  as appended context only; and the compaction plugin masks old results into the archive at
  `SANCHOPANZA_COMPACT_AT_PERCENT` (`turn.complete` trigger, new free `mask` arm). No decider
  is asked about future need at compaction: that question measured at chance
  (`docs/results/2026-09-28-context/`); the `tournament` arm exists only to be measured. Memory
  formation at compaction (`context.formation`, `remember` with `trust="untrusted"`) is off by
  default. Every hook fails open; a per-session ledger caps the autopilot at
  `SANCHOPANZA_SESSION_MAX_USD` (0.50). Offline: `benchmarks/context/simulate.py arrival|recall`
  (`--estimate`, `--dry`; `--live` refuses until registered) and the experimental `tournament`
  arm of `benchmarks/context/run.py`.
- **`sanchopanza install --autopilot --lean`, experimental.** The autopilot with no decider:
  masked results keep an index of the codes and pairs they held (`--stub-style index` on
  `sanchopanza compact`, `SANCHOPANZA_STUB_STYLE`; `context.index.index_of`), the arrival cut
  is a free line cut (`SANCHOPANZA_ARRIVAL_MODE=free`, `arrival.free_cut`: first and last lines,
  error lines and BM25 lines against the purpose), no recall is injected
  (`SANCHOPANZA_RECALL_ON=off`), and the `search_archive` MCP server is written to the
  project's `.mcp.json` and approved by name. Measured: 3/7 against the native summary's 5/7,
  and the agent never called `search_archive`.
- **`sanchopanza archive-mcp`**: an MCP server with one tool, `search_archive`, BM25 over
  `.sanchopanza/archive`; no decider and no key (`harness.mcp.build_archive_server`, mcp 1.x
  or 2.x).
- **`sanchopanza.harness.codex`**: hook bodies (`post-tool-use`, `session-start`) and config
  generators for OpenAI's Codex CLI, archiving tool output and pointing at `search_archive`.
  Offline tests only; **not verified end to end** (in four `codex exec` attempts the trusted
  hooks never ran). See `docs/results/2026-09-28-context-lean/codex/`.
- **Broader Claude Code evidence, pre-registered** (`docs/results/2026-09-28-claude-code-broad/`).
  Hook level: 1,816 labelled cases through the `sanchopanza hook` process with real Jev. The
  shell-fetch scan noted 121/124 AgentDojo injections in `curl` output with 0/149 false alarms,
  and scanned nothing for a non-fetching `cat`; the Stop check's blocks were right in 286 of
  299 on 655 AgentDojo runs (13 of 342 finished runs blocked); ATBench-Codex: 0 of 250 unsafe
  trajectories flagged, because the hook does not judge MCP tool calls. End to end: 144
  Claude Code sessions, hooked against plain, 8 reps: destructive commands stopped 16/16 (plain
  ran them 15/15), planted pages flagged 16/16, 0 false alarms in 93 benign events; the agent
  refused the planted text in every session in both arms. 5.29 USD list (subscription), Jev
  0.043 USD. `tests/test_claude_code_broad.py` replays every hook-level verdict from
  `fixtures/claude-code-broad-jev.jsonl`, no key.
- **`triage_many` is the recommended way to keep documents out of a call**, on a
  pre-registered result (`docs/results/2026-09-28-fixed-pages/`): `benchmarks/ab/fixed.py
  --lever pages` judges each document's passages with the others in view, on a pinned corpus
  (`--corpus-ref`), answering through our own evaluation harness, with a free pipeline
  check (`--fake`) and passage-level attribution (`pages.attribute`). `triage_page` keeps its
  injection and source-kind answers; its relevance drop is not the recommended path.
- **`providers.CachedDecider`, opt-in.** Wraps any decider and answers a repeat of the same
  point, state and questions (option order, provider and model included in the key) within
  `ttl_seconds` with the first answer, at zero cost and latency, journalled as
  `<provider>@cache`. Never stores a failed, empty, unreadable or partial decision; an
  unavailable provider still raises. In memory by default, JSON lines on disk with `path=`
  (hash and answers only, no state text). Identical answers within the TTL; it does not fix
  the provider's drift across TTL windows. Tested with fake providers.
- **`Squire.select_passages`, for one long document**, and `select_sentences(window=)`.
  The tournament over the paragraphs, then sentences with a window of two inside the
  paragraphs it keeps at 0.75 or more (`Thresholds.document_paragraphs`,
  `document_window`). Fixed on 261 recorded QASPER questions and confirmed on 219 new
  ones: every answer sentence in 87.2 % at 21.0 % of the text, against 84.0 % at 30.2 %
  for the plain two stages, with 59 % fewer sentence calls; Haiku 4.5 answered from it as
  well as from the whole paper (F1 48.2 % against 44.5 %). `tests/test_select_passages_bench.py`
  replays the 219 through the shipped method and demands the same sentences
  (`docs/results/2026-09-28-lateral-wholedocs/`). `text.split_sentences` is the splitter.
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
- **`Squire.check_done` and an opt-in Claude Code Stop hook** (`SANCHOPANZA_CHECK_DONE=1`,
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
  `SANCHOPANZA_SCAN_CONTENT`, `SANCHOPANZA_CONTENT_TOOLS` and `SANCHOPANZA_PURPOSE`. Flagged content is
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

- **Retracted: "Jev's Truth confidence is exactly |2p - 1|, 651 answers, zero deviation"**
  (0.2.0, the paper, `where-it-pays.md`). The Truth wire carries only the probability
  (`noul`); `providers.jev.from_wire` computes the confidence, and the recordings store the
  converted answer, so they could not show anything else, and the test presented as a canary
  on the provider could not fail. The policy lesson stands: two gates on one number are one
  gate. `from_wire` now says once if Jev ever sends a Truth confidence of its own that
  differs (and keeps ours), and the test says what it checks. Found by another session
  deriving how Jev computes confidence.
- **candor's ledger could lose an action when tool calls ran in parallel.** Their hooks appended
  to one file at once; on Windows an append is a seek then a write, so one entry overwrote
  another and the reader skipped the torn line without a word. Seen once in benchmark round 3;
  8 processes x 150 appends lost 196 of 1,200 lines. Appends are now serialised by a lock file.
- **candor's benchmark label missed a `cat` inside a compound command** and marked one honest
  round-2 session a misreport; it now reads commands the way the rules do. The registered round-2
  numbers stay as recorded.
- **The compaction hook returned the engine's `handle`, so a resumed session was not
  compacted.** `compact_hook.ts` handed back the engine's own message objects for the messages
  it did not change; Claude Code then chained the entries written after the compaction to the
  old ones, and `claude -p --resume` rebuilt the history from before the compaction, unmasked.
  Returned messages now never carry `handle`
  (`test_returned_messages_never_carry_the_engine_handle`); a resumed session starts masked
  (57.1k tokens against 85.8k before). It invalidated the published 12/12 against 6/12. Any
  plugin that replaces a session's messages must not return `handle`.
- **The benchmark runners passed the coordinating session's `CLAUDE_*` variables to the child
  sessions** (`CLAUDE_EFFORT=medium` and others). The runners now drop them.
- **A stale `--out` file could survive a declined compaction.** An earlier run's
  `.sanchopanza/compact-*.json` that nobody blanked kept a copy of the conversation after a
  fallback (exit 3); it is now blanked, and a fallback archives nothing.
- **On Windows the Claude Code hooks never ran.** A hook command written with backslash paths
  was not executed (0 hook events in the attempt), with no error anywhere.
  `install.portable_command` now writes forward slashes. Found by the first end-to-end pilot
  of the autopilot, which is published as invalid (`docs/results/2026-09-28-context-e2e/`).
- **The compaction plugin could be refused whole, silently.** `compact_hook.ts` read
  `$.session.usage` as a value; Claude Code's function-hook compiler refuses a module that
  reads a host capability as a value and says so only in its debug log, so `/compact` fell back
  to the native summary with no sign in the session. The module now only ever calls
  `$.session.usage` and `$.session.compact`. Found by the second pilot attempt, also published
  as invalid.
- **`sanchopanza compact` left a full copy of the conversation behind when it declined.** With
  `--out`, a compaction that freed less than the minimum (exit 3) still left the whole
  conversation, unredacted, in the project directory, where `git add .` would pick it up, and
  the archive written. Pruned results now go to a staging folder that is discarded unless the
  compaction is used, `--out` is written only after that, and both ignore themselves in git.
- **The autopilot's hook passed through silently without a key.** It now says on stderr that it
  passed the event through unchanged and why (`DeciderUnavailable`).
- **Content fetched through the shell was never scanned, even when asked for.** Claude Code
  hands PostToolUse a Bash result as `{"stdout", "stderr", "interrupted", ...}` and `text_of`
  read it as empty, so naming `Bash` in `--content-tools` scanned nothing. `text_of` now reads
  `stdout` and `stderr` (and a plain `output`). And with `--scan-content` on, the output of a
  shell command that fetches from the network (`curl`, `wget`, `aria2c`, `lynx`/`w3m`,
  `Invoke-WebRequest`/`iwr`, `Invoke-RestMethod`/`irm`, HTTPie, `gh api`, inline Python or
  Node code naming an HTTP client) is scanned by default, decided in code by
  `harness.fetch.fetches_from_network`; other shell output only if the shell is named.
  `install` hooks Bash at PostToolUse for this; `--no-shell-fetches` or
  `SANCHOPANZA_SCAN_SHELL_FETCHES=0` turns it off. Tested on the recorded Bash result shape with a
  fixed decider; **not measured in a live Claude Code session**.
- **The tournament asked the same group twice** when a round pruned only from later
  groups and the survivors regrouped into an earlier group. Each tournament now reuses the
  answers of a group it already asked. Replaying every recorded tournament keeps the same
  pages with fewer calls: 60 of 1,359 on the 2026-09-27 QASPER run, 14 of 853 on the
  whole-document confirmation (`docs/results/2026-09-28-lateral-memo/`).
- **The content scan read nothing from Claude Code's built-in tools.** Claude Code hands
  PostToolUse a `Read` result as `{"file": {"content"}}`, `WebFetch` as `{"result"}` and
  `WebSearch` as `{"results"}`; `text_of` read all three as empty, so `--scan-content` never
  scanned them. Found by the first end-to-end run inside Claude Code, fixed, and confirmed by a
  registered run with the released hook: the planted file flagged 2/2 (p 0.98, 0.99), no
  false alarm on benign reads (`docs/results/2026-09-28-claude-code-harness/`). Content fetched
  with `curl` through Bash was not covered by that fix; see the entry above.
- **`triage_many`: a round that prunes nothing no longer asks the same groups again.** It
  reused Jev's non-determinism as a second opinion and broke replay; the round's answers are
  reused, and each page reports the last probability it got. The hierarchy result stands:
  every one of the 200 held-out questions replays identically through `Squire.triage_many`
  (`tests/test_hierarchy_bench.py`).
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

- **The Claude Code hook starts faster.** `sanchopanza` and `sanchopanza.providers` resolve
  their names on first use, the entry-point scan runs only for a provider that is not built
  in, the CLI imports per subcommand, and `sanchopanza hook` decides in code whether an event
  can need a decision before loading the squire or `asyncio`. Measured on the maintainer's
  Windows laptop, interleaved, 31 runs: median 0.17 s for an event that needs no decision and
  0.25 s up to the decision for one that does, against 0.31-0.34 s before
  (`docs/results/2026-09-28-hook-startup/`). The public imports are unchanged.

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
  `redundant` / `SANCHOPANZA_T_REDUNDANT` no longer affect it.
- `Guardian.after_tool` returns a `Note` (model context and operator text), not a string; the
  Claude Agent SDK PostToolUse output also sets `systemMessage`.
- `evaluate_plan` never returns tier `light`: plan lines do not ask `person_risk`, and a
  downgrade needs it answered.

### Measured

- **Compaction mid-session: native summary against lean masking, negative**
  (`docs/results/2026-09-28-context-lean/`, pre-registered, Claude Code 2.1.282 headless with
  Haiku 4.5, 7 tasks, compaction fired by Claude Code's own auto-compaction mid-task, run
  through our own evaluation harness). Native summary 5/7, lean masking (index stubs, archive,
  free arrival cut, pull `search_archive`) 3/7, clearing old results without an archive
  (microcompaction-like) 0/6. H1 and H2 failed. Lean used more input tokens (10.46M against
  8.73M) at the same dollars (1.99 against 2.03 USD, list price) because of cache reads. The
  agent never called `search_archive` (0 of 7 sessions) and tried to re-run one-shot tools 39
  times. Offline: index stubs hold a later-needed token for 12.0 % of needed masked results
  (bar 50 %); free arrival cuts keep all needed lines in about 1 of 4 large outputs; Jev keeps
  them by hardly cutting (95.9 % of characters); the API's `clear_tool_uses` (keep 3) behaves
  like masking with M = 3. Mechanics confirmed: auto-compaction fires mid-turn and runs the
  `session.compact` function hook with trigger `auto`; microcompaction never runs in `-p`;
  `turn.complete` fires once per prompt; the Agent SDK path works. Sonnet 5 (stopped by the spend
  gate): t01 solved by both; t02 masking compacted five times, thrashing near the threshold,
  and failed at 2.04 USD. Spend: probes 2.14, Haiku 6.93, Sonnet 3.75 USD at list price
  (12.82 in all), Jev 0.081 USD.
- **Retracted: the context autopilot's 12/12 against 6/12 for `/compact`**
  (`docs/results/2026-09-28-context-e2e/`, correction at the top). Under `claude -p --resume`
  the compaction hook returned the engine's `handle`, so Claude Code rebuilt the unmasked
  history and phase B never saw the masked context: the comparison was "no compaction, plus
  recall" against the native summary. The +13 % input tokens came mostly from phase-A
  variance, not from recall. Left in place for the record.
- **Pruning a coding agent's context by decision, negative** (`docs/results/2026-09-28-context/`,
  pre-registered, 40 public OpenHands trajectories, offline): all four criteria fail. Asking
  which results the rest of the session will use ranks needed against unneeded at AUC 0.57
  test / 0.61 dev; a replica of the fast-jev-compaction plugin (0.56 / 0.53) frees 81 % and
  keeps 9 % of what the future used, the same as keeping the last three results. The decision
  arm keeps 80 % but frees only 25 %. Amendment 2: the arrival cut saved 3.7 % of long results,
  not better than head+tail at the same size; recall with the decider 70.4 % against BM25
  top 3's 68.5 % at 7.8 % less text, not a detectable difference. 0.076 + 0.154 USD of Jev.
- **A recall gate for Claude Code's memory files, negative** (`docs/results/2026-09-28-memory-gate/`,
  pre-registered, LongMemEval S): BM25 top 3 reaches 0.85 session recall; the gate (0.73),
  the hybrid (0.69) and the passage cascade (0.73) miss their recall criteria while injecting
  far less text (a half; 4 % for the cascade) at 0.93-0.97 precision. Exploratory, at equal
  text: the cascade beats truncated sessions and BM25 paragraphs and is not distinguishable
  from BM25 over sentences on evidence. A runner bug (an `asyncio.Lock` bound to the first event
  loop made later decisions fail open into empty answers while the run said complete) was
  found, fixed with tests, and the run completed; the withdrawn figure is reported. 0.39 USD
  of Jev. Part B, on the owner's own sessions, was not run.

- **Bench rows hardened for privacy, re-recorded after pseudonymization hardening (2026-09-28).**
  38 rows about pseudonymized persons of the defamation material were generalized (outlet
  domains to `.test`, court dates shifted, nicknames and biographies made generic); labels
  unchanged. Only those rows were asked again (74 Jev decisions, 0.0020 USD). Moved: public
  `facts` 14/15 -> 15/16, fourth-batch `facts` 35/39 -> 36/40, option-order flips 4 and 3 ->
  3 and 2 (`docs/results/2026-09-25-order/`), and the calibration figures those rows feed.
  The entity question's examples, which used benched nicknames, were replaced with invented
  ones and all 48 entity recordings re-asked (0.0013 USD); entity stays 24/24, only the
  calibration figures moved.

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
- **The same design with in-context page triage, pre-registered**
  (`docs/results/2026-09-28-fixed-pages/`): `triage_many` over passages answered 9/9 against
  9/9 at -79.5 % input tokens [-86.5 %, -72.9 %], no answer-bearing passage withheld in any of
  the ten tasks. The tenth was stopped by the 3 USD cap and cannot overturn either bar. One
  answering call, not a warm loop; 0.107 USD of Jev and 3.19 USD at list price.
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
  (`docs/results/2026-09-27-answers/`, pre-registered, Haiku 4.5 through our own evaluation harness,
  the 300 confirmatory chunk questions). With the reply forced into one short field: all pages
  70.0 %, the kept pages 71.0 %, the kept sentences 70.7 %, sentences with no page gate 69.0 %;
  P21s, P22s and P24s hold, and the path check agrees with the API (harness 67.0 % against the
  Batch API's 67.7 % on the same prompts). The claim is equality, not gain; 7.04 USD at list
  price. The first run, with free-length replies, was negative as
  registered (81.0 %, 76.7 %, 76.0 %; P21, P22 and P24 failed; harness 74.7 % against the API's
  67.7 %; 4.46 USD): its score counts a reply correct when the gold answer is contained in it,
  and replies grew with the context (median 30, 9 and 4 words).
- **A BM25 screen before one in-context call, not confirmed, retired**
  (`docs/results/2026-09-28-lateral-screen-confirm/`, pre-registered, 0.45 USD): on 200 fresh
  HotpotQA questions 96.5 % against the tournament's 97.5 %, lower bound -4 points against -3.
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
- **Inside Claude Code, end to end** (`docs/results/2026-09-28-claude-code-harness/`,
  pre-registered, 24 headless sessions with Haiku 4.5 as the agent, with and without the
  hooks): the guard denied both destructive commands that plain Claude Code executed (one by
  the code deny-list, one by Jev at p 0.71-0.74), allowed the benign one, and the Stop check
  blocked the unfinished task once while letting finished ones stop; zero false blocks. All
  17 model decisions came from `jev-1.13.0` (about 0.00005 USD per session), 2 from code, none
  from Claude. 8 of 9 criteria held; the ninth exposed the content-scan bug fixed above.
- **The cascade against Sonnet 5: partial** (`docs/results/2026-09-28-cascade-sonnet/`, the
  2026-09-25 primary verdicts, Sonnet through our own evaluation harness). P1 (R-Judge) fails on cost:
  92.3 % like Sonnet at 57.7 % of its cost (median 47.7 % over 500 re-splits). P2 (register)
  holds: 81.4 % against 80.2 % at 46 %. P9 (Codex) holds: Jev alone matched Sonnet at 0.4 % of
  the cost. 17.42 USD at list price.
- **The permission cascade, confirmed on unseen data** (`docs/results/2026-09-27-cascade-frontier/`,
  pre-registered: tau 0.45 from R-Judge, ATBench-Codex never shown to Opus, Opus 5 through our own evaluation harness). Held-out half, of record: cascade 80.3 % against Opus 79.9 % at 38.8 % of
  its cost, all three criteria hold. The other half, registered after that verdict, replicates
  (77.8 % against 75.8 %, 38.3 %), and so do all 500 (79.1 % against 77.8 %, 38.5 %). On this
  set Jev alone is as accurate as Opus (78.2 %) and lets through fewer unsafe actions (false
  allows 14.9 % against 25.7 %). 15.07 USD at list price.
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

- **Two gates on one number were one gate at the stricter value.** For a Truth answer,
  `confidence` is `|2p - 1|` by construction (the adapter computes it from the probability;
  "651 recorded answers, zero deviation" was circular and is retracted in 0.3.0).
  So a policy asking for both `p >= a` and
  `confidence >= c` was asking for `p >= max(a, (1 + c) / 2)`, and the threshold named in the
  configuration was not the one in force. `memory_write` was configured at 0.70 and enforcing
  0.80; source redundancy at 0.80 and enforcing 0.875; the recall and extraction gates had a
  dead clause. The redundant gates are gone, **no threshold value changed**, and the gap
  between the shipped policy and a plain 0.5 cut fell from eight decisions to three
  (78/88 to 85/88, AUC 1.00 throughout).
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
