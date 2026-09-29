# Results: which folder backs what

One directory per run, each with the report behind its figures. Nothing here is deleted when
it is superseded; this index says which folders carry the claims in the top-level README and
which are the record of how they were reached.

## Main evidence

The runs behind the README's headline numbers.

| Folder | What it backs |
|---|---|
| [2026-09-21-public](2026-09-21-public/) | The public benches (core, safety, graph) replayed from their recording; paper Section 5.9 |
| [2026-09-27-memory-write-cut](2026-09-27-memory-write-cut/) | The `memory_write` cut derived to a precision target, and the substitution against Opus 5: 131x cheaper, 10.9x faster, 2 decisions less accurate |
| [2026-09-28-claude-code-broad](2026-09-28-claude-code-broad/) | The guard inside Claude Code: destructive commands stopped 16 of 16, 0 false alarms in 93 events |
| [2026-09-24-agentdojo](2026-09-24-agentdojo/) | Injection detection on AgentDojo's attacks: 0 false alarms on 149 real tool outputs |
| [2026-09-25-window](2026-09-25-window/) | The tool window and the injection scan that keeps it from widening on planted text |
| [2026-09-25-completion](2026-09-25-completion/) | Checking the agent's own "done": 52 % believed, 94 % with one calibrated question |
| [2026-09-25-triage](2026-09-25-triage/) | Page triage on multi-part questions: the contribution question keeps both pages in 93.3 % |
| [2026-09-27-chunks](2026-09-27-chunks/) | Pages judged in each other's context, then sentences: 98.3 % at 34 % of the text |
| [2026-09-27-hierarchy](2026-09-27-hierarchy/) | The tournament over 100 pages: 96.5 % at 3.1 % of the text in 5 calls |
| [2026-09-27-answers](2026-09-27-answers/) | The kept text answers as well as all of it; the first, free-length run was negative |
| [2026-09-28-fixed-pages](2026-09-28-fixed-pages/) | Keeping documents out of one answering call: 9 of 9 answers at 79.5 % fewer input tokens |
| [2026-09-28-lateral-wholedocs](2026-09-28-lateral-wholedocs/) | One long document: every answer sentence in 87.2 % at 21.0 % of the text (`select_passages`) |
| [2026-09-27-cascade-frontier](2026-09-27-cascade-frontier/) | The Jev-then-Opus permission cascade, confirmed on unseen ATBench-Codex data |
| [2026-09-28-cascade-sonnet](2026-09-28-cascade-sonnet/) | The same cascade against Sonnet 5: partial, over the cost bar on R-Judge |
| [2026-09-29-candor](2026-09-29-candor/) | Say/do checking, confirmation round (`prereg-2.md`). The status-block lock stopped 96 % of misstated reports and 0 of 111 honest sessions; real misreports 9/12, below its registered 80 %. Jev as a second opinion reached AUC 0.98 against Haiku 4.5's 0.68 |
| [2026-09-29-find](2026-09-29-find/) | Repository search on 117 SWE-bench Verified issues (`prereg.md`), 3 of 3 hypotheses hold: a gold file first in 51.3 % and in the top five in 65.0 %, against 13.7 % and 35.0 % for whole-file BM25, at 0.0016 USD per issue |
| [2026-09-29-candor](2026-09-29-candor/) (round 3) | v3 on 176 new sessions (`prereg-3.md`), 5 of 7 hypotheses hold: 95.3 % of misstated reports stopped, 0 of 126 honest sessions, Jev AUC 0.973 against Haiku's 0.666 |

## The negatives the README reports with the same weight

| Folder | What did not pay |
|---|---|
| [2026-09-24-agentdojo-e2e](2026-09-24-agentdojo-e2e/) | In front of a model that already refuses, the injection guard buys nothing |
| [2026-09-25-e2e](2026-09-25-e2e/) | The tool window with a real agent: no detectable difference in success where tool search exists |
| [2026-09-25-cache](2026-09-25-cache/) | The cost basis of those end-to-end comparisons: where the cache breakpoint sits decides the ratios |
| [2026-09-25-wide](2026-09-25-wide/) | Against a real 398-tool MCP catalog, the platform's search is cheaper than the window |
| [2026-09-24-fixed-sequence](2026-09-24-fixed-sequence/) | Judging each document alone (`triage_page`) lost 4 answers in 10 |
| [2026-09-27-longdocs](2026-09-27-longdocs/) | The tournament on whole papers missed the registered 25 % of the text |
| [2026-09-25-cascade](2026-09-25-cascade/) | The registered cascade rule on R-Judge reached Opus at 57 % of its cost, over the 50 % bar |
| [2026-09-29-candor](2026-09-29-candor/) (round 1) | The registered say/do round: 5 of 8 hypotheses failed. The critical-only lock missed most misstatements, and the per-sentence Jev judge added nothing (5.2 %). One of 6 lock sessions let a parallel call through before the lock engaged |
| [2026-09-29-candor](2026-09-29-candor/) (round 3) | Real misreports whose falsehood lies outside the record (a silent failure, a truncated archive, a suite that does not exist): the lock stopped 0 of 22. 4 of 126 paraphrases locked (D1 fails at 3.2 %). A ledger defect lost actions under parallel hooks; fixed |
| [2026-09-29-candor-external](2026-09-29-candor-external/) | On public data, 7 of 10 registered hypotheses fail. errata-bench (real Claude Code sessions, no status block): no real misreport locked, holistic Jev AUC 0.56. MALT: candor's question near chance on reward hacking (0.62) and sandbagging (0.56). tau2-bench: `check_done` below trusting the agent (54 % against 67 %) |
| [2026-09-28-lateral-screen-confirm](2026-09-28-lateral-screen-confirm/) | The BM25 screen did not replicate on fresh questions and was retired |
| [2026-09-28-context-lean](2026-09-28-context-lean/) | This iteration's main negative. Inside Claude Code, with auto-compaction firing mid-task (Haiku 4.5, 7 tasks, pre-registered): native summary 5/7, lean masking 3/7, clearing without an archive 0/6; masking used more input tokens (10.46M against 8.73M) at the same dollars; the agent never called `search_archive`. Offline, index stubs held a needed token for 12.0 % of needed masked results (bar 50 %). Sonnet 5 (partial, spend gate): masking thrashed, five compactions and 2.04 USD on one task |
| [2026-09-28-context](2026-09-28-context/) | Asking a decider what the rest of a coding session will need is at chance (AUC 0.53-0.61); the arrival cut saved 3.7 % and did not beat head+tail; recall with the decider matched BM25 top 3 |
| [2026-09-28-memory-gate](2026-09-28-memory-gate/) | A decider gate over memory files missed its recall criteria against BM25 top 3 on LongMemEval; at equal text, not distinguishable from BM25 over sentences |

## Corrected: headline invalid

| Folder | What happened |
|---|---|
| [2026-09-28-context-e2e](2026-09-28-context-e2e/) | Its headline, the autopilot 12 of 12 against 6 of 12 for `/compact` (p = 0.014), is **retracted**: under `claude -p --resume` the compaction hook returned the engine's `handle`, so the second phase saw the unmasked history. It compared "no compaction, plus recall" against the native summary. Correction at the top of its README; measured again in 2026-09-28-context-lean |

## Supporting runs and history

Earlier batches, intermediate runs and runs superseded by a later folder. Their numbers are
correct for their sitting; where a later folder replaces a figure, the later one is quoted.

| Folder | What it is |
|---|---|
| [2026-09-24-new-points](2026-09-24-new-points/) | First recording of the eight 0.2.0 points, under the policy of that day (superseded by the replay in paper 5.10) |
| [2026-09-24-fifty](2026-09-24-fifty/) | Fifty cases per binary point and a second annotator |
| [2026-09-24-fifty-v2](2026-09-24-fifty-v2/) | The same fifty-case judgments made two ways (substitution, first version) |
| [2026-09-24-third-batch](2026-09-24-third-batch/) | `memory_write` and `redundant_page` to 100 and 125 cases; a widened gate measured and not shipped |
| [2026-09-24-after-fix](2026-09-24-after-fix/) | The widened `specific` gate, measured and not shipped |
| [2026-09-24-fourth-batch](2026-09-24-fourth-batch/) | `facts`, `edge` and `memory_collision` to 50 cases each |
| [2026-09-24-edge-fix](2026-09-24-edge-fix/) | `edge` with the direction gate read first (intermediate) |
| [2026-09-24-collision](2026-09-24-collision/) | `memory_collision` as two binary questions |
| [2026-09-24-steerability](2026-09-24-steerability/) | Changing the criterion at query time: what moved and what did not |
| [2026-09-24-effort](2026-09-24-effort/) | What more thinking buys a generative judge on closed-vocabulary judgments |
| [2026-09-24-genrm](2026-09-24-genrm/) | A generative verifier as a control on compositional judgments |
| [2026-09-24-tools](2026-09-24-tools/) | The first tool selector and its two failure modes (superseded by the window) |
| [2026-09-24-agentdojo-haiku](2026-09-24-agentdojo-haiku/) | Raw AgentDojo runs with Haiku, kept for the record; no report of its own |
| [2026-09-25-order](2026-09-25-order/) | Option-order sensitivity of a Choice |
| [2026-09-25-pending](2026-09-25-pending/) | Two cheap pending items of 2026-09-25 |
| [2026-09-25-policy-shape](2026-09-25-policy-shape/) | How much of the policy-model gap the policy's shape explains |
| [2026-09-25-push](2026-09-25-push/) | Pushing tools to Sonnet 5 without `tool_addition`: the channel works, the timing does not |
| [2026-09-27-edge-facts](2026-09-27-edge-facts/) | The errors of `verify_edge` and `relate_facts`, and the fifth batch that settled the direction question |
| [2026-09-28-claude-code-harness](2026-09-28-claude-code-harness/) | The first Claude Code end-to-end run, installed as a user would (superseded by claude-code-broad) |
| [2026-09-28-hook-startup](2026-09-28-hook-startup/) | The hook's start-up time before and after lazy imports |
| [2026-09-28-lateral-screen](2026-09-28-lateral-screen/) | The BM25 screen's first, unconfirmed match (see the confirmation above) |
| [2026-09-28-lateral-memo](2026-09-28-lateral-memo/) | Remembering tournament groups: same pages, fewer calls |

Bench rows about pseudonymized persons were hardened on 2026-09-28 and their recordings asked
again; the folders whose figures moved say so in their own README or summary.
