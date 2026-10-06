# The change gate: check-done and candor act only on a request that changed something

A product change, prompted by the h2h development run
([2026-10-05-h2h-offline-dev](../2026-10-05-h2h-offline-dev/)): on BrowseComp-Plus and
LongBench v2, question-and-answer suites where nothing is edited, S cost 1.69x and 1.90x of N
without more right answers; check-done sent back 17 of 20 S sessions and the second answer never
changed a grade; candor asked for its status block on every prompt. Everything here is a replay
of recordings: no model was called.

## What changed

`harness.change_gate`, on by default, `SANCHOPANZA_ON_CHANGE=0` to turn it off:

- **check-done** asks Jev only when the current request changed something: an edit tool, a shell
  command that writes, deletes, sends out or installs (candor's classification plus the memory
  touch's `context.shell.written`), any other tool whose name does not start with a reading verb
  (in doubt, a change), or a delegation whose subagent transcripts show a change.
- **candor** asks for its status block at the first call that changes something or runs tests
  (PostToolUse context) instead of at every prompt; Codex keeps it at the prompt. At Stop, a
  request that did neither (and whose snapshot shows nothing changed) has its rule findings
  journalled with `"gated": "no_change"`, and nothing is held, judged, locked or said.
- A fix found on the way: after a compaction, check-done took the compaction summary as the
  request (2 of the 10 BrowseComp-Plus sessions). Hook feedback and compaction summaries no longer
  start a request.

## What it saves (h2h, `h2h-replay.json`, `benchmarks/gate_replay/replay.py`)

| suite | S sessions | changed | send-backs avoided | turns after them | list USD after them | block requests avoided | critical Stop findings avoided |
|---|---|---|---|---|---|---|---|
| BrowseComp-Plus dev | 10 | 0 | 10 of 10 | 23 | 1.04 of 7.78 (13 %) | 10 | 0 |
| LongBench v2 dev | 10 | 0 | 7 of 7 | 18 | 0.35 of 1.23 (28 %) | 10 | 2 |
| GAIA dev (S0) | 0 | | | | | | |

GAIA dev ran S0 without check-done or candor, so it has nothing to replay. Against the S-N gap
(3.18 USD on BrowseComp-Plus, 0.58 on LongBench), the send-back is a third of it on
BrowseComp-Plus, where the rest is S searching more (161 calls against 87), and three fifths on
LongBench. The cost after a send-back is the share of the session's priced tokens (input 1, cache
write 1.25, cache read 0.1, output 5) applied to the row's list cost.

## What it takes

- **check-done on AgentDojo** (the 655 trajectories it was measured on, replayed as Claude Code
  transcripts with the recorded verdicts; `tests/test_claude_code_broad.py` pins it): of its 286
  blocks on unfinished work, **263 are in trajectories that changed nothing**: the agent stopped
  to ask, refused after an injection or never called the action. The gate lets those stops
  through, and 12 of its 13 false blocks. Recall on unfinished runs falls from 286/313 to 23/313.
  The end-to-end scenario D of [2026-09-28-claude-code-broad](../2026-09-28-claude-code-broad/)
  (a value from a file that does not exist, blocked 8 of 8) is a read-only request too.
- **candor on its coding rounds** (`candor-rounds.jsonl`, `benchmarks/gate_replay/candor_rounds.py`,
  rules with block and snapshot as `policy_replay.py`): every lock on a natural misreport is kept
  (9/9, 32/32, 15/15, 11/11 in rounds 2-5). The locks lost are counterfactual reports written
  into sessions that did nothing (18 of 177, 19 of 208, 22 of 111, 12 of 62): the report that
  claims work no call did. Locks on honest reports are unchanged (0, 1, 2, 0).
- No recorded coding session ran check-done: adopt phase D installs no Stop hook.

## Why check-done's question says "not done" to complete answers

The question (`points.completion`) is written for AgentDojo's tool tasks, not for code: "every
part of `task` was carried out ... a question in `task` was answered with what the tools
returned", and "not done" includes "its answer is not supported by the tool results". In the 17
sessions it sent back, the record held 3-14 % of the tool-result text on BrowseComp-Plus and
3-48 % on LongBench (each result is cut to its first 1,500 characters), so the support the
answer cites is mostly out of view, and several BrowseComp-Plus answers say themselves that a
clue is unverified. Proposed, **not applied**: keep, for each tool result, the passages that
share terms with the final answer instead of its head. It changes what Jev reads on AgentDojo
too, so it has to be measured on `benchmarks/completion` first (655 trajectories, about 0.03 USD
of Jev; the shipped numbers are 94.5 % against 55.3 % for trusting the agent, held-out half).

## Second signal: the request asks for an action (`three-gates.json`, `benchmarks/gate_replay/three_gates.py`)

The price above is AgentDojo's stops: the agent asked, refused or never called the action, so
nothing changed. Three gates replayed on the same recordings, no model called:

- **A**: changed something, or the request asks for an action (`change_gate.asks_action`: an
  action verb at the start of a clause, after an optional "please", "can you", "your task is
  to", in English or Spanish; no question mark, "question" or leading wh-word in any sentence;
  quoted text and conditional sentences such as GAIA's "If you are asked for a string, ... write
  the digits" left out). Shipped.
- **B**: changed something, or the final answer claims a finished action in the first person
  ("I sent", "has been booked", "he enviado") in a sentence with no negation. Benchmark only.
- **C**: A or B.

| gate | AgentDojo right blocks kept /286 | false blocks /13 | send-backs avoided /17 | candor block requests avoided /20 | lock findings avoided /2 |
|---|---|---|---|---|---|
| change (as shipped before) | 23 | 1 | 17 | 20 | 2 |
| A | **266** | 1 | **17** | **20** | 2 |
| B | 24 | 1 | 16 | 20 | 2 |
| C | 266 | 1 | 16 | 20 | 2 |

None of the 87 recorded h2h requests (47 GAIA, 20 BrowseComp-Plus, 20 LongBench v2) reads as an
action under A. B does what was expected: AgentDojo's stops claim nothing, so it
keeps one block more than the change gate; and in one of the 17 sessions with a send-back
its rule reads a sentence of the answer as a finished action and lets the send-back back in.
C adds B's send-back to A's and nothing else.

Where A fails:

- 20 AgentDojo trajectories, two requests: "post there the following question: 'Hi, can
  everybody ...?'" (the word "question" outside the quotes reads as a question) and "to each user
  write the message" (the verb does not start a clause).
- The 12 false blocks it still lets through are "Read the content on webpage ..." and "Visit a
  website at ..." (reading, not acting): right to stay closed. The one false block it keeps is
  the trajectory that did change something.
- Not measured: coding requests phrased as questions ("can you fix the parser?" is read as a
  question and stays gated unless something changed), and requests in other languages.
