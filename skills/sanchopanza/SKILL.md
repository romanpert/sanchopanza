---
name: sanchopanza
description: Add a calibrated, non-generative decision layer to an agent harness with the sanchopanza package. Use when routing between model tiers, triaging fetched pages before they enter context, choosing which pages and sentences of a large set an answer needs, detecting prompt injection, verifying citations, guarding shell commands, aligning entities, classifying into a closed vocabulary, ordering a plan as a DAG, selecting tools from a large catalog, or letting the tool set follow a session without breaking the prompt cache. Also use when deciding whether a small decision model is worth adding at all, or when choosing thresholds.
---

# Wiring a squire into an agent

`sanchopanza` puts the procedural decisions of an agent loop on a model that returns a
typed choice, a scale position or a probability, never text. The knight thinks; the squire
reads. Install with `pip install sanchopanza[jev]`, import as `sanchopanza`.

Everything below has a measurement behind it or says that it does not.

## 1. Decide whether it is worth it at all

It is worth it when the loop makes the same small judgment many times per job, and each one
is currently paid at the large model's price inside its context, with no trace of why.

It is **not** worth it when:

- The judgment needs arithmetic, date comparison or counting. The model class reads numbers
  as text. Code does this for free and correctly.
- Something deterministic already decides it. A literal quote match, token overlap between
  queries, a deny-list regex, the transitive reduction of a graph. Those run first, cost
  nothing and never drift.
- The decision is the only barrier before a dangerous action. The decision model is itself
  vulnerable to instructions injected into its state. It may add a denial; it must never
  grant permission.
- The answer has to be explained in prose. The audit trail here is probabilities.
- **The platform already has tool search, and the catalog is large.** A platform tool search
  appends schemas rather than swapping them, so it keeps the prompt cache too, and it loads by
  tool rather than by group. Measured end to end on Sonnet 5 with a 74-tool AgentDojo catalog,
  success shows no detectable difference between loading everything (70/80 over two runs),
  `ToolWindow` (100/120 over three) and the platform's search (31/40); cost, estimated from
  recorded usage with the `tools` + `system` prefix shared between tasks, is 0.77-0.88x of
  loading everything for the window and 1.48x for the search. On a real MCP catalog of 398
  tools the platform's search is the cheaper, an estimated **0.34x against the window's 0.54x**
  of loading everything, at the same success, because the window loads a group whole and the groups were
  whole MCP servers: it opened the 121-tool Google Workspace server in 11 of 17 tasks
  (`docs/results/2026-09-25-e2e/`, `docs/results/2026-09-25-wide/`,
  `docs/results/2026-09-25-cache/`). Inside Claude Code a sanchopanza hook added nothing
  measurable over its own deferred tool search, and Codex CLI already defers MCP tools behind
  a local BM25 search. See section 3 for where the window does belong.
- **The thing you would be filtering is mostly noise.** Below roughly 17 % precision in
  whatever proposes the candidates, a filter adds nothing measurable. Measure the generator
  before you build the filter.

**Ask where it will act before you ask how accurate it is.** A decision is worth what its
attachment point lets it be worth. Measured in this repository: narrowing a tool catalog once
per session is 43 % cheaper, and the same narrowing done afresh every turn costs 4.15x,
because rewriting `tools` invalidates the whole prompt cache. Outside it: Meta moved the same
static analysis, with the same false-positive rate, from batch to diff time and its fix rate
went from near zero to over 70 %.

Cost check before you build: one decision is about 29 millionths of a dollar, and there are
three different ways that can be worth something. It **substitutes** for a call some model
was going to make anyway (verify this citation, match this pair, check this triple): the
saving is a price ratio, 24x to 119x by list price, and it is the only one of the three whose
arithmetic is safe. It **avoids** tokens entering a context: worth less than it looks,
because inside a warm loop those tokens are priced at the cache-read rate of 0.1x, so the
multiple is 4.8x on a Sonnet-class model, not 48x. Or it makes a check **affordable** that
was previously skipped, which is a quality result and should never be reported as a saving.

Break-evens, measured: a fetched page pays for its own triage above roughly 60 tokens on a
Sonnet-class orchestrator; a delegated subtask pays for its own routing above roughly 75.
See `docs/savings.md` and `docs/where-it-pays.md` in the repository.

## 2. Pick the decision point

| You want to | Method | Measured |
|---|---|---|
| Send a subtask to a cheaper or deeper model | `route_task` | 17/20 raw; 11/11 when acting at confidence >= 0.75; a small LLM got 8/20 |
| Stop a repeated search, or send it to a free engine | `route_search` | 17/18 |
| Keep the pages a multi-part question needs, and only those | `triage_part` (one page at a time), `triage_pages` (up to 30 in one call, each with the others in view), `triage_many` (any number, a tournament) | HotpotQA, labels by construction: `triage_part` 93.3 % of 300 questions keep both supporting pages at 52 % of the text, BM25 80.3 %; `triage_pages` 98.3 % at 34 % in one call, against 94.3 % at 53 % page by page; `triage_many` on 100 pages 96.5 % of 200 held-out questions at 3.1 % in 5 calls, BM25 at the same page count 50.5 %. With the reply forced into one short field, an answering model scores as well from the kept text as from all pages (70.0 % all, 71.0 % kept pages, 70.7 % kept sentences; equality, not gain). On whole QASPER papers the recall holds (94.7 %) but it keeps 48.9 % of the text, not confirmed |
| Keep only the sentences of a kept page that the answer needs | `select_sentences` | After `triage_pages`: every supporting sentence in 90.3 % of 300 questions at 22 % of the text. For one long document use `select_passages` instead: 87.2 % of answer sentences kept at 21.0 % of a paper (QASPER, 219 new questions) |
| Keep an irrelevant or injected page out of the context | `triage_page` | 14/16 relevance. With the document sequence held fixed, relevance triage cut input tokens 75.2 % and correct answers from 10/10 to 6/10: a saving paid for in answers. Injection: 27/28 under the policy on the public bench, AUC 1.00, a regex 23/28; on AgentDojo the question 101/124, a keyword layer 115/124, both 120/124, 0/149 false alarms |
| Mark untrusted content that has already arrived | `scan_content` | Same two layers as injection triage. End to end on AgentDojo's Slack suite, undefended Sonnet 5 was compromised 0 times in 105, so the control buys nothing in front of a model that already refuses; where it is used, mark (1 task in 42) and never redact (65 points of utility) |
| Check that a source supports a claim | `verify_citation` | 19/20; with numbers 23/24 |
| Prioritize a round's lines and get parallel waves | `evaluate_plan` | pairwise 20/20; full DAG 100 % precision, 88 % recall after code cleanup |
| Notice a subagent report that states facts without sources | `review_report` | 21/22 |
| Add a denial on a dangerous shell command | `guard_command` | 29/32 alone; 31/32 with the code deny-list, zero false positives |
| Decide whether two mentions are the same entity | `same_entity` | 24/24 |
| Put free text into a closed vocabulary | `classify` | 80-85 % against independent labels, majority baseline 43-62 % |
| Narrow a large tool catalog, **once per session** | `select_tools` | 91/97 AgentDojo tasks keep every needed group on the recorded run (a live run held 3.1 of 16 groups); BM25 at the same budget 38/97; doing it per turn costs 4.15x. Its misses are groups the request does not name, and it fails when the work moves: 124 misses in 40 three-task sessions |
| Let the tool set follow the session without breaking the cache | `ToolWindow` + `WindowedTools` | 0 misses on 97 trajectories and 40 sessions, in-sample. End to end on Sonnet 5, 74 tools: 100/120 pooled against 70/80 loading everything, 0.91x the time, an estimated 0.77-0.88x the cost; the platform's search 1.48x. On 398 tools the platform's search is cheaper (an estimated 0.34x against 0.54x). Only where there is no tool search or the catalog is small; see section 3 |
| Stop a loop that has already finished, or a check that repeats one | `check_loop` | 12/14 and 12/12 under the policy, AUC 1.00; 46/50 and 50/50 with the second batch, zero false alarms |
| Decide whether a fact is worth writing to long-term memory | `remember` | One cut of 0.54 on the weakest margin, derived to an 80 % precision target and pre-registered: 39/49 with 1 costly store on the held-out half (the conjunction it replaced: 37/49 with 2); 74 of 108 with 1 on cases never used for any threshold (conjunction: 60 with 4). Stores 4 of 36 standing client instructions. `ask_common=True` scores 45/48 on a batch written before it was measured, where the shipped cut scores 37/48, opt-in |
| Reconcile a new fact against a stored one | `reconcile` | 46/50, all four errors the safe `keep_both`; recency comes from your timestamps, never from the model |
| Skip a memory lookup a turn does not need | `needs_recall` | 14/14 on the first bench, AUC 1.00; 50/50 with the second batch |
| Skip a generative extraction call on a chunk with nothing in it | `gate_extraction` | 15/16, AUC 1.00 |
| Check a proposed triple before it enters a graph | `verify_edge` | 31/38 when deciding on 50 cases; 17 committed and 1 of them backwards, with the earlier wording. The `direction` question by roles, default since the fifth batch, caught 10 of 12 reversed edges against 5 with no wrong commit on 30 new cases. A filter in front of a person, not an autonomous committer |
| Drop a source that repeats what you already have | `triage_redundant` | 116/125, AUC 1.00, at a threshold derived to a 90 % precision target (0.59) |
| Find the files and lines of a repository a request needs | `select` over `context.repo` fragments; the `find_in_repo` MCP tool | On 117 SWE-bench Verified issues, pre-registered, the gold patch's files as the label: a gold file first in 51.3 % and in the top five in 65.0 %, against 13.7 % and 35.0 % for whole-file BM25, at 0.0016 USD per issue; without a key the fragments alone reach 42.7 % at five (docs/results/2026-09-29-find/). Retrieval only: agent success with it is unmeasured |
| Hold the agent's final report against what it did, and stop it for a person | `candor.check_record`; the candor hook and its sticky lock | With the four-line status block: 95-96 % of model-written misstatements stopped over two confirmation rounds, 0 of 237 honest sessions stopped, no model call. Misreports the record cannot show (a silent failure, a truncated file, a check that could not run): 0 of 22 with v3; v4 reads the disk and swallowed errors and is being confirmed. Without the block, on real third-party sessions, it caught nothing: ask for the block (`SANCHOPANZA_CANDOR_ASK_BLOCK`) |

## 3. Wire it in

Hooks for what happens without the model asking; tools for what it asks on purpose.

```python
from sanchopanza import Squire, Thresholds, JsonlJournal
from sanchopanza.providers import create
from sanchopanza.harness import Guardian, HarnessConfig

squire = Squire(
    create("jev"),                      # or "clm" (self-hosted), "llm", "local", "recorded", "null"
    thresholds=Thresholds(),            # the measured defaults
    journal=JsonlJournal("journal.jsonl"),
    brief="what this job is about",
)
guardian = Guardian(squire, HarnessConfig(tiers={"light": "...", "deep": "..."}))
```

- **Claude Agent SDK**: `from sanchopanza.harness.claude_agent_sdk import hook_matchers` and
  pass `hooks=hook_matchers(guardian)`.
- **Claude Code**: point a `PreToolUse` / `PostToolUse` command hook at `sanchopanza hook`.
- **MCP client** (Claude Code, Cursor, Codex, anything): one stdio server with the tool sets you choose, `python -m sanchopanza.harness.mcp --tools archive,find,decisions` (`decisions` needs a provider; the other two work without one). For Codex, `python -m sanchopanza.harness.codex config --find` prints the hooks and the `config.toml` fragment.
- **Anthropic Messages API, large tool catalog**: `ToolWindow(squire, catalog,
  wait_on_deferred=accepts_tool_addition(model))` and
  `WindowedTools(window, tools_by_group, model=model)` from
  `sanchopanza.harness.messages_api`. Send `wt.tools()` unchanged on every request; call
  `window.observe(text, trust="user")` on a user turn and `trust="tool"` on a tool result.
- **LangChain / LangGraph**: `ToolSelectMiddleware(squire, key_of=thread_id)`, one
  append-only window per conversation.
- **Anything else**: `await guardian.before_tool(ToolCall(name, args))` returns allow, deny
  with a reason, or rewrite with new arguments. Map those three to your harness.

**Where the tool window belongs.** Recommend `ToolWindow` only where the platform offers no
tool search, or where the catalog is small enough that search round trips cost more than
the groups (on 74 tools the window was an estimated 0.77-0.88x of loading everything and the
platform's search 1.48x). Where the platform has tool search and the catalog is large, use the
platform's search: on 398 tools it was cheaper at the same success. The window's cost is set
by its coarsest group, because an opened group is loaded whole. Size groups as a task would
use them, not as a server ships them: a 121-tool server as one group costs about as much as
loading it. Splitting large servers into sub-groups is the open design question and has not
been measured.

## 3b. Select a few among many: one shape for pages, passages, memory, archive and code

Every "which of these matter?" in the package is the same two stages (`sanchopanza.select`):
a BM25 shortlist by code (`text.BM25Index`, the one BM25), then, with a judge, `triage_many`
in context (a tournament past 30 candidates). Build `Candidate(key, title, text)` for whatever
you have, keep the index if the candidates serve many queries, and call
`await select(query, candidates, squire=squire, keep=k)`. Without a squire, or when the judge
fails, the BM25 order stands: it never returns nothing because a model was down. Do not write
a second BM25 or a second tournament; extend this one.

Where the candidates are a repository, `context.repo` already builds them (fragments at
top-level definitions, `git ls-files`, an in-memory index per root). A self-hosted CLM, which
its authors say is fastest when the same options come back, fits here as the judge
(`SANCHOPANZA_PROVIDER=clm`); it has not been measured in this repository.

## 4. Respect the four invariants, or do not bother

**Fail open.** No provider, no key, exhausted budget, provider bug: every policy returns the
default the harness had before. `Squire.decide` never raises. If you wrap it in something
that can raise, you have broken the main safety property.

**Asymmetry.** The direction whose error the user sees needs more confidence than the cheap
direction. Downgrade a model at 0.75, upgrade at 0.60. Drop a page only on explicit low
relevance; in doubt it enters. Emit a citation verdict at 0.80, else abstain. The guard can
deny, never approve.

**Trace.** One journal event per decision, with probabilities, confidence, cost, latency and
the outcome. It is the audit trail, and later it is the labelled dataset you tune on.

**Cache-safe.** Act only where acting cannot invalidate a cached prompt prefix. The prefix
renders as `tools -> system -> messages` and a change at any level invalidates that level and
everything after it, so:

| Safe to act | Never |
|---|---|
| Before the first request of a session | Rewriting `tools` mid-session |
| On content about to be appended (a page, a search result, a subagent's prompt) | Editing the system prompt mid-session |
| Inside a tool the model called anyway | Deleting or rewriting earlier turns |
| On a delegation, choosing the subagent's model | Switching the model of a running conversation |
| As an appended note (`additionalContext`) | |

If a harness genuinely needs the tool set to change mid-session, use the channels that append
rather than swap, with the whole catalog declared once with `defer_loading: true`. Measured
with `count_tokens` on 2026-09-25 (`docs/results/2026-09-25-window/README.md`, section 1):

- **`tool_addition`** in a mid-conversation `system` message works on Opus 5, Opus 4.8 and
  Fable, and is a 400 on Sonnet 5 and Haiku 4.5. It is proactive: no round trip.
- **A `tool_result` holding only `tool_reference` blocks** works on all of them, from any
  tool. On Sonnet 5 and Haiku that is the only channel, so the model has to call a tool
  (`load_tools`) for the window to grow. There, open with `wait_on_deferred=False`: the model
  acted on a "tools are now available" note in 2 of 16-18 tasks end to end.
- **Do not write the `load_tools` call yourself on Sonnet 5.** The API accepts it, but after
  the model has read untrusted text it takes the new tools as an injection and refuses: 0/16
  against 5/8 with everything loaded. Opus 5 with `tool_addition` after the read held 7/8
  against 8/8. A mechanism probe on one toy task, not pre-registered
  (`docs/results/2026-09-25-push/`).
- **`tool_removal` reclaims nothing** (+26 tokens, the block itself): the schema stays in the
  history where it was added. Removal is a control, never a saving, so keep the window
  append-only.

Verify it worked by watching `cache_read_input_tokens`: a zero across repeated requests means
something is rewriting the prefix.

**A window that widens on what the agent reads is a capability-escalation path.** Without the
injection scan, 24 of 56 AgentDojo payloads got the window to add the group the attacker
needed; with it, none, and no clean text lost an addition (in-sample: the detector was fitted
on the same bench). Never let untrusted text widen the tool set unscanned.

**And a fifth thing that is not an invariant but will cost you more than all of them.**
The squire chooses among the options you tell it exist. If one of those options is not
actually deployed, it will route work into the hole confidently, nothing will fail, and
fail-open will never fire. `cheap_search_available` must be a probe that answers "does this
engine exist and answer, right now", never a constant and never a quota check. The failure it
prevents looks like a saving: a report that begins "this research could not be carried out",
75 % cheaper than delivering one.

## 5. Write the question properly

This is where most of the accuracy lives.

- **Ask it to read, not to predict.** "Is this query written as keywords or as a question?"
  scored 94 %. The earlier version, "would a common search engine find this?", scored 38 %.
  Same decision, same model.
- **Minimal state, named keys.** Send the fields the decision needs and nothing else.
  Irrelevant context degrades the answer. Trim long fields.
- **One dimension per question**, several questions per call. They are answered in parallel
  and cost one round trip.
- **Criteria with examples**, for the true and the false side both. The examples do about
  half the work.
- **Score levels as situations**, not grades. "Look up a fact in a named source and copy it",
  not "easy".
- **Always offer `other` or `none`** when the list may not be exhaustive. The model cannot
  abstain out of domain if you do not let it.
- **Instructions in English, content in any language.** Measured: Spanish content with
  English instructions matched or beat Spanish instructions.

## 6. Long documents: the trap

Triage sees an excerpt, not the whole page. Cutting from the head is wrong on a long
document, because the part that answers the purpose is usually in the middle, and the
decider then judges on a preamble that genuinely does not mention it.

`sanchopanza.text.excerpt` handles this: head plus the window that best matches the purpose
words. Judged on its head, the one document that held the answer was dropped in the
end-to-end benchmark, and the run cost twice as much for no answer at all. If you write your
own state builder for a long document, do the same thing, or chunk before you triage.

For many pages, do not triage them one at a time: `triage_pages` judges up to 30 in one call,
each with the others in view, and `triage_many` runs a tournament past that. Both judge a page
by an excerpt of 900 characters, and `select_sentences` judges the first 40 sentences of a page and
keeps the rest unjudged; a document longer than that should be split first. Judging a long document as document, then sections, then sentences, the tournament's
shape, is an idea and is unmeasured.

## 7. Thresholds move only with evidence

Most defaults in `Thresholds` were fixed before the runs that measured them and have not been
tuned on those results. Move one when you have 50 cases for that point, a second annotator,
and a confidence-band table that justifies the move, or derive it to a stated target on one
set and judge it on another, pre-registered. That is how `adds_nothing` (0.59), the
`memory_write` cut (0.54) and the page selection cuts were set. Not before.

Calibration is per primitive, so do not use one global confidence: Truth answers are
under-confident (they are better than they say), Choice answers are well calibrated, and
Score answers are the least reliable, which is why the Score-driven point is gated hardest.

**Pin the version, and still quote only from a recording.** The same state asked of the same
pinned `jev-1.13.0` moved by up to 0.09 within a day. A decision within about 0.1 of its cut
is a coin flip between runs. Record every run you intend to cite (`--record`) and pin the
figure with a replay test.

**Score the policy, not the model.** A bench that reads probabilities at 0.5 while the policy
acts at 0.70 measures an ordering nobody ships. Score each point with the thresholds its
policy applies, and report a plain 0.5 cut, if at all, as a separate measurement of the
model's ordering.

**A missing answer is not a "no".** An absent answer reads as probability 0.0, which a policy
can mistake for a confident no. Check `.empty` before reading a probability whenever the
default would push the decision in the costly direction; every policy in this package does.

## 8. Measure before you trust

```
sanchopanza bench benches/core.jsonl benches/safety.jsonl benches/graph.jsonl \
    --provider recorded --fixture fixtures/public-benches.jsonl
sanchopanza bench mycases.jsonl --provider jev --record fixtures/mine.jsonl --out results/today
```

The first line replays the public run from its recording, free; each further bench replays
from its own fixture (the paper's Appendix A lists them). Reports agreement when deciding, coverage, Wilson intervals, AUC, Brier, expected calibration
error, agreement by confidence band and calibration by primitive. Write your own cases in the
same format; real material beats invented material and hard negatives beat easy ones.

For an end-to-end question, "does my agent get cheaper or worse", copy `benchmarks/ab/`:
same tasks, same prompts, one arm with the squire and one without, paired bootstrap over the
pairs. Decision-level accuracy does not answer that question and should not be quoted as if
it did. If an evaluation needs a generative model,
run every arm through the same path and control the answer length: free-length replies
from one path are not interchangeable with API numbers (74.7 % against 67.7 % on the same
prompts; 67.0 % against 67.7 % with a short answer field). For tool catalogs, `benchmarks/agentdojo/e2e_window.py` is the model: a success
criterion written before the first run, and more than one run: the all-tools arm moved from
34 to 36 of 40 between two runs with nothing changed, so the model varies against itself as
much as the arms differ. And share the fixed prefix between tasks the way production would: a
cache breakpoint on `system`, and one pre-warm request before tasks run in parallel. Without
them every task pays the catalog as a cache write, and the arms with a fixed catalog look
dearer than they are: loading all 74 tools for 40 tasks cost 1.955 USD that way, against an
estimated 0.909 with the prefix shared (`docs/results/2026-09-25-cache/`).
