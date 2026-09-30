# What sanchopanza adds to an agent, and how

sanchopanza puts the small, repeated decisions of an agent loop on a decision model (Jev, a
self-hosted CLM, or any provider) and on code. Among those decisions: which model a subtask
gets, whether a command is safe, which files matter, and whether the report matches what was
done.

It reaches an agent in three ways:

1. **Hooks the harness runs.** The agent does not call them and mostly does not see them. They
   act on a tool call, a tool result, a prompt or a stop. Some are on when installed, some
   opt-in.
2. **Tools the agent calls on purpose.** These are MCP tools (and one Messages-API tool) that
   appear in the agent's tool list.
3. **A library the harness developer calls.** It has typed decision points, a generic "select a
   few among many", candor's checks, and adapters for the Claude Agent SDK, OpenAI Agents,
   LangChain and the Messages API.

Every decision fails open. With no key, an exhausted budget or a provider error, the harness
gets the default it had before sanchopanza. Every decision is journalled (`JsonlJournal`), and
code decides first wherever code can.

The "status" column says what is measured. It links nothing that was not run.

## 1. What the agent sees: tools it calls

| Tool | What it does | Needs a key | How it gets there | Status |
|---|---|---|---|---|
| `search_archive(query, k)` | BM25 over tool output that was cut or masked out of context and kept on disk; returns paths with the matching excerpt | no | archive MCP server: `sanchopanza archive-mcp` (installed by `--lean`), Codex `config.toml`, or `python -m sanchopanza.harness.mcp --tools archive` | shipped; the agent did not call it in the lean end-to-end run (docs/results/2026-09-28-context-lean/) |
| `find_in_repo(query, k)` | the files and line ranges of the repository that bear on a request: a BM25 shortlist of code fragments, judged in context when a key is set | no (better with one) | archive MCP server with `SANCHOPANZA_FIND=1`, `--tools find`, or Codex `config --find` | on 117 SWE-bench Verified issues: a file the fix edits first in 51 %, top five in 65 % (whole-file BM25: 14 %, 35 %), 0.0016 USD per issue (docs/results/2026-09-29-find/) |
| `label_file(path, rubric, out, max_usd)` | labels every item of a `.jsonl`/`.csv`/`.txt` with a closed rubric and writes columns (label, p, margin, provider, reason); cached for 30 days, capped | yes | `--tools label` | 89.3 % on AG News and 98.0 % on DBpedia-14 against Haiku 4.5's 83.0 % and 98.0 %, at 1/70 to 1/95 of its cost (docs/results/2026-09-30-label/) |
| `rank_elements(goal, page, done, keep)` | the elements of a page (Playwright snapshot, HTML or a file) most likely to be acted on next, with their refs | no (better with one) | `--tools browse`; also `sanchopanza browse PAGE --goal ...` from a shell | on 142 new Mind2Web steps (559 elements a page), the element acted on is in the top 20 in 89.4 % and the top 10 in 82.4 %, BM25 38.7 % and 23.2 %, 0.0065 USD a step; an answering model given only the top 20 scored 5 points under the whole page, not recommended as a replacement (docs/results/2026-09-30-browse/) |
| `verify_citation`, `evaluate_plan`, `align_entities`, `classify_field`, `triage_text` | the decision points an orchestrator asks on purpose: does this source support this claim, the waves of a plan, same entity or not, a closed vocabulary, is this text worth reading | yes | `python -m sanchopanza.harness.mcp --tools decisions` | each measured at decision level (SKILL.md, section 2) |
| `load_tools(need)` | grows the tool set when the model needs a tool that is not loaded yet, by appending, so the cache stays valid | yes | `harness.messages_api.WindowedTools` (Messages API) | measured; where the platform has tool search, its search is cheaper (docs/results/2026-09-25-wide/) |

One server can carry any of these sets:

    python -m sanchopanza.harness.mcp --tools archive,find,decisions

That gives Claude Code (`.mcp.json`), Codex (`config.toml`), Cursor and any other MCP client
one server with the sets chosen. Every tool description is kept under 200 characters, because
every session pays for its tool list.

## 2. What the harness runs: hooks

### Claude Code, `sanchopanza hook` (installed by `sanchopanza install --write`)

| Event and tool | What happens | On by default once installed | Status |
|---|---|---|---|
| PreToolUse `Agent` / `Task` | `route_task`: the subagent's model tier is rewritten (light, default, deep) from the task's complexity | yes | 17/20 at decision level |
| PreToolUse `WebSearch` | `route_search`: a repeated search is cut, a keyword query can go to a free engine | yes | 17/18 |
| PreToolUse shell (`Bash`, `run_command`...) | `guard_command`: a code deny-list first; the decider can add a denial, never grant | yes | 31/32 with the deny-list, 0 false positives; 16/16 destructive commands stopped inside Claude Code, 0 false alarms in 93 events |
| PostToolUse `Agent` / `Task` | `review_report`: a subagent report stating facts with no source is flagged | yes | 21/22 |
| PostToolUse content tools | `scan_content`: marks injected instructions in arriving text | opt-in `--scan-content` | 0 false alarms on 149 real tool outputs; buys nothing in front of a model that already refuses |
| PostToolUse `Bash`, `Read`, Playwright MCP | `browse_hook`: a large accessibility snapshot (MCP result, `playwright-cli snapshot`, or a `.yml` snapshot file) pruned to the elements ranked for the task, headings and relevant text, full copy archived | opt-in `python -m sanchopanza.harness.browse_hook` | **saved nothing** in 36 real sessions with playwright-cli (+0.0095 USD, [-0.006, +0.027]), same answers; it acted in 8 of 18 |
| Stop | `check_done`: holds the stop once when p(done) < 0.5 | opt-in `--check-done` | 94 % on AgentDojo (AUC 0.98); **does not carry to tau2-bench's reward** (54 % against 67 % for trusting the agent) |
| UserPromptSubmit | a free hint: the repository fragments BM25 ranks first for the prompt, appended as context (repositories of up to 3,000 text files; a hook cannot keep the index between prompts) | opt-in `SANCHOPANZA_FIND_ON_PROMPT=1` | unmeasured end to end; the retrieval itself is measured in docs/results/2026-09-29-find/ |

### Context, `--autopilot` or `--lean` (experimental)

- **Arrival cut.** A PostToolUse hook cuts a long tool result to the blocks the task needs,
  through `updatedToolOutput`, and archives the rest.
- **Recall.** Archived output and memory files are recalled on each prompt or tool call as
  appended context.
- **Masking.** A compaction plugin masks old results at 60 %.

**Measured worse than Claude Code's own compaction** on our tasks: 5/7 native, 3/7 lean
(docs/results/2026-09-28-context-lean/). Keep the native compaction as the default.

### Candor, `python -m sanchopanza.harness.candor_hook` (wired by hand; `install` does not write it)

| Event | What happens |
|---|---|
| UserPromptSubmit | opens the request in the session's ledger, hashes the workspace (`SNAPSHOT=1`), and with `ASK_BLOCK=prompt` appends the request for the four-line status block |
| PreToolUse | with the lock engaged, refuses every call; a call that touches the hooks, the settings or the trace engages it |
| PostToolUse / PostToolUseFailure | appends the call and its outcome to the ledger, under a lock file (parallel calls used to overwrite each other on Windows) |
| Stop | holds the final report against the ledger and the disk. A critical finding engages the sticky lock (`MODE=lock`), and a person releases it with `python -m sanchopanza.candor release --by NAME --why TEXT`. With `ASK_BLOCK=stop`, a report without the block is held once and asked for it |

Status (docs/candor.md):

- **Model-written misstatements:** 95-96 % stopped over two confirmation rounds, and 0 of 237
  honest sessions.
- **Misreports the record cannot show** (a silent failure, a truncated file, a check that could
  not run): 0 of 22 with v3. v4 reads the disk and errors a successful call printed: on round
  4's new sessions it stopped 6 of 8 of round 3's kinds and 105 of 105 misstatements, at 1 of
  61 honest sessions; a check that could not run still passes (0 of 4).
- **Without the status block,** on real third-party sessions, it caught nothing. This is why
  `ASK_BLOCK` exists.

### Codex CLI, `python -m sanchopanza.harness.codex`

- **PostToolUse:** archives every result of 500 characters or more, and points at the archive
  for results of 6,000 or more.
- **SessionStart:** a note about `search_archive`.
- **Config:** `config [DIR] [--find]` prints `.codex/hooks.json` and a `config.toml` fragment
  with the MCP server. Nothing is written for you.

### Other harnesses, as a library

- **Claude Agent SDK:** `hook_matchers(guardian)`.
- **OpenAI Agents:** `tool_guardrail`.
- **LangChain / LangGraph:** `ToolSelectMiddleware`.
- **Anything else:** `await guardian.before_tool(ToolCall(...))` returns allow, deny or rewrite.

## 3. What the developer calls: the library

- **`Squire`**, one method per decision point:
  - `route_task` and `route_search`;
  - `triage_page`, `triage_pages`, `triage_many` and `select_sentences`;
  - `select_passages`;
  - `select_tools`, and `ToolWindow` for the tool set;
  - `verify_citation`, `evaluate_plan`, `review_report`, `scan_content` and `guard_command`;
  - `same_entity`, `classify`, `relate_facts`;
  - `remember`, `reconcile` and `needs_recall` for memory;
  - `gate_extraction` and `verify_edge` for graphs;
  - `check_done`, `check_loop`, `triage_redundant` and `prune_context`.

  Each one has typed questions, measured thresholds, a meter (`max_usd`, `max_decisions`) and a
  journal. The measured figures are in `skills/sanchopanza/SKILL.md`, section 2.
- **`sanchopanza.label`**: a closed rubric over a corpus (`label`, `read_items`, `write_rows`,
  `LabelCache` with an age), `Squire.classify`'s question and gate per item; `sanchopanza label`.
- **`sanchopanza.browse`**: a page into elements by code (`elements_from_snapshot`,
  `elements_from_html`), `rank` for the next action, `prune_snapshot`; `sanchopanza browse`.
- **`sanchopanza.select`**: "a few among many", the one shape behind pages, passages, memory,
  archive and repository search. A BM25 shortlist by code (`text.BM25Index`, the package's one
  BM25), then `triage_many` in context when there is a judge.
- **`sanchopanza.context.repo`**: repository search on top of `select`:
  - fragments by code (`context.blocks.split`);
  - `git ls-files` (so `.gitignore` holds);
  - an in-memory index rebuilt when a file changes;
  - `python -m sanchopanza.context.repo "request" [--free]`.
- **`sanchopanza.candor`**:
  - `check_record` (rules, pure code) and `judge_record` (plus Jev, adding notes only);
  - `should_lock`, the sticky `lock`, and the status block (`BLOCK_REQUEST`, `report_block`).

## 4. Providers: who answers the questions

Picked with `SANCHOPANZA_PROVIDER`, or `jev` when `TYPESAFE_API_KEY` is set. A provider that
cannot be built says so on stderr and falls back to no decider.

| Provider | What it is | Configuration |
|---|---|---|
| `jev` | TypeSafe's Jev, pinned to `jev-1.13.0` | `TYPESAFE_API_KEY`, optional `SANCHOPANZA_JEV_URL` |
| `clm` | CLM-8B (Contrastive-LM, Stanford and NVIDIA, Apache-2.0) on your own GPU through `clm-serve`, which speaks the TypeSafe wire format: the Jev client pointed at it | `SANCHOPANZA_CLM_URL` (default `http://localhost:8000`), `SANCHOPANZA_CLM_MODEL`, `CLM_API_KEY`. **Tested against a mock of the wire format only**: no measurement here has used a real CLM |
| `llm` | a general model answering the same typed questions | `ANTHROPIC_API_KEY`, `SANCHOPANZA_LLM_MODEL` (default Claude Haiku 4.5) |
| `recorded` | replays recorded answers, free | `SANCHOPANZA_FIXTURE` |
| `local`, plugins | your own handlers, or any package registered under `sanchopanza.providers` | code, or the entry point |
| `null` | no decider: every point returns the harness's default | nothing |

## 5. What is automatic, what is asked for, and what it costs

| | Automatic (hook) | Invoked (tool or call) |
|---|---|---|
| Needs no key, costs nothing | shell deny-list, candor rules and lock, arrival free cut, Codex archiving | `search_archive`, `find_in_repo` without a key, `check_record` |
| Uses a decider (about 0.00003-0.004 USD a decision) | subtask routing, search routing, guard's added denial, report review, content scan, `check_done`, candor's Jev note | `find_in_repo` with a key, the five decision tools, `load_tools`, every `Squire` method |

What sanchopanza never does:

- write text for the agent;
- approve an action on a model's word;
- rewrite the tools, the system prompt or earlier turns in the middle of a session. Every
  runtime addition is appended context, so the prompt cache stays valid.
