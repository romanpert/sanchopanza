# Pre-registration fetch1: Claude Code with fetch v2 against Claude Code alone, on free FRAMES tasks

Written 2026-10-05, before any session of this run. Sealed by `prereg-fetch1.sha256`
(`free_fetch_confirm.py --record-hash`, sha256 of this file with CRLF read as LF) and committed
with the code it names before the first session; `free_fetch_confirm.py --live` refuses to spend
while the two disagree. The criteria were fixed by the owner's session before this file was
written and do not move once the first session has run.

## What is being tested

fetch v2 as `sanchopanza install --fetch` sets it up, on a model that reads web pages by itself:
the `sanchopanza-fetch` MCP server (`sanchopanza fetch-mcp`, one tool, `fetch_passages`) at
version 2 (`SANCHOPANZA_FETCH_VERSION=2`, `sanchopanza.webpage_v2`: chrome stripped, passages by
sections, a short line on a 404 or a disambiguation page), registered with `alwaysLoad`, and
`fetch_hook` on `PreToolUse` WebFetch (the first WebFetch of a URL is sent to the tool, a second
one runs). No page budget: `SANCHOPANZA_FETCH_MAX_PAGES` is unset (the fetch v2 pilot found its
line did nothing). Code as of the commit that carries this file (worktree `browse-dev`).

The bar is the owner's: **with sanchopanza, Claude Code has to beat Claude Code without it on
price and on answers at once**, model by model.

## Arms (`free_fetch_confirm.ARMS`, `CAPS`)

The fetch pilots' runner (`free_fetch2_pilot.session_for` on `free_e2e.one_session`): the FRAMES
question and the ANSWER instruction, Claude Code 2.1.287 pinned first on the PATH of the run and
checked by `--preflight`, its normal tools, `Bash` and the scheduling tools denied, WebFetch
denied to the hosts that serve the set (Hugging Face, GitHub, Kaggle, Papers with Code:
`free_frames.DENY`), `--setting-sources ""`. Hooks and MCP servers only through the session's own
`--settings` and `--mcp-config`, never `~/.claude/settings.json` (`--preflight` refuses to run
with a sanchopanza hook there).

| arm | model | cap per session | added |
|---|---|---|---|
| HAIKU | claude-haiku-4-5 | 0.60 USD | nothing |
| HAIKU-FETCH2 | claude-haiku-4-5 | 0.60 USD | the server at version 2 (`alwaysLoad`) and the WebFetch hook |
| SONNET | claude-sonnet-5 | 1.50 USD | nothing |
| SONNET-FETCH2 | claude-sonnet-5 | 1.50 USD | the server at version 2 (`alwaysLoad`) and the WebFetch hook |

Same cap within a model: the question is the same answers for less, not a tighter budget.
`--check-load` (free) checks before any session that the first request of each -FETCH2 arm offers
`fetch_passages` with its schema, not behind ToolSearch. `--preflight` refuses any
`SANCHOPANZA_FETCH_*` variable in the run's own environment.

## Tasks (`fetch-confirm-ids.txt`), one run per task and arm, 240 sessions

Sixty FRAMES test rows (Krishna et al., 2024; cached locally only), chosen by metadata alone
with the fetch pilots' filters (`free_fetch_pilot.eligible`: an answer of at most four words,
three or more Wikipedia links), seeded (`random.Random(20261012).sample` over the eligible pool in
file order, `free_fetch_pilot.sample`), none of any earlier run: pilot 1 (`frames-ids.txt`),
pilot 2 (`frames2-ids.txt`), the fetch pilot (`fetch-pilot-ids.txt`), the fetch v2 pilot
(`fetch2-pilot-ids.txt`), and every smoke (each of their private session files is checked to hold
no other task). Only ids reach the repository. The four arms run interleaved by task
(`free_fetch_confirm.plan`: each task in HAIKU, HAIKU-FETCH2, SONNET, SONNET-FETCH2 before the
next task), so a stop cuts them alike.

Scope: the tasks are Wikipedia tasks (FRAMES). A result here does not by itself generalise to
other sites.

## Grading (`free_fetch_confirm_hand.py`)

- **Blind, by hand.** After the run, `--blind-sheet` writes outside the repository one entry per
  session: a random id, the task, its question and gold, and the session's last ANSWER, shuffled
  (task order and the four answers within a task), with no arm, no cost and no tool count; the key
  (id -> task, arm) goes to a separate file the grader does not open. The grader sets each entry
  right or wrong against the gold; `--apply` refuses a sheet with any entry ungraded and maps the
  grades back. The verdicts read these grades only, never the runner's automatic grade (which is
  reported beside them).
- **The answer is the last ANSWER line of the main transcript.** A session that ended at its cap
  counts with its last ANSWER. A session with no ANSWER line is wrong.
- **Leaks.** A session is marked leak when the runner flags it (a tool result names the set) or the
  wider scan (`free_frames_hand.session_leak`: the set's hosts or names in any tool input or
  result, main agent and subagents) finds it. A leak makes both arms of that model wrong on that
  task. Every leak is reported by task and arm.
- **Cost** is each session's list-price `total_cost_usd`; a session the runner killed (30 min)
  reports none and is charged its arm's cap.

## Hypotheses (`free_fetch_confirm_hand.verdicts`), for each model m in {Haiku, Sonnet}, `m-FETCH2` against `m`

- **Price.** Total cost of `m-FETCH2` / total cost of `m` **at most 0.80**, and `m-FETCH2`
  cheaper (strictly) on **at least 55 %** of the tasks (33 of 60).
- **Answers.** `m-FETCH2` right on **at least as many** tasks as `m` (of 60). No margin: one answer
  fewer fails it.

**fetch v2 beats the harness on model m** (`beats_the_harness`) if and only if both hold for m.
Reported for each model; a result on one model is not claimed for the other. The run is
`complete` when all 240 cells exist; an incomplete run is reported as such.

## Described, not tested

Per arm: right by the runner's grade, mean and median cost, the readers' cost, WebSearch,
WebFetch and `fetch_passages` calls, passage tokens, sessions at the cap, sessions with no ANSWER
line, sessions killed by the runner, sessions that called `fetch_passages` (zero expected in the
base arms), Claude Code versions; exact McNemar paired by task within each model; every miss of a
-FETCH2 arm and every number that favours it read by hand before it is described.

## Spend and stopping

Expected, from the sessions already measured (list prices): HAIKU 0.189 USD a session (80 base
Haiku sessions of the four pilots) and SONNET 0.227 (60 base Sonnet sessions), so 11.3 and 13.6
USD; HAIKU-FETCH2 0.114 (the fetch v2 pilot, 20 sessions), 6.8 USD; SONNET-FETCH2 0.105
(SONNET-FETCH at version 1, the fetch pilot; version 2 has not run on Sonnet), 6.3 USD.
**About 38 USD**; 45 if SONNET-FETCH2 costs what its base does. **Hard ceiling 55 USD in code**
(`free_fetch_confirm.CEILING_USD`, `phase.Limits`, which counts the whole sessions file and keeps
1.50 USD free before each session). Resumable: a resume runs only what is missing. A 429 or
"weekly limit" from Anthropic in a session stops the run at once (STOP-LIMIT); that session is
recorded as not run and runs again on resume. Nothing else stops it before the ceiling. Launched
outside the agent's session (WMI, its own process group, SIGINT ignored).

## Whatever the outcome

The verdicts are published as computed, with the blind grades, the leaks and every miss read by
hand, in `README.md` of this folder. No FRAMES question, answer or page text goes to the
repository: ids, booleans, counts and dollars only.
