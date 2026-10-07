# GAIA head to head, dev: Claude Code alone (N) against Claude Code with sanchopanza (S)

A development run of 20 GAIA validation tasks on Sonnet 5.5, to check the comparison end to end
before the confirmation (`docs/PLAN-COMPARACION-FINAL.md`, sections 1-3, local). **It is not the
confirmation and no threshold was set from it.** Its 20 tasks (`benchmarks/h2h/gaia-dev-ids.txt`)
are left out of the confirmation, which runs the remaining 135 non-video tasks. Only task ids and
numbers are written here; no question, answer or quote.

## Set-up

`benchmarks/h2h/h2h_gaia.py` at da32e9b and 323cdd4 (sanchopanza `src` frozen at main 76a75d0,
merged into h2h). Claude Code 2.1.287, pinned. GAIA (Mialon et al., 2023), validation split: the
20 ids are `random.Random(20261005).sample` of the 155 non-video tasks (levels 1/2/3: 4/14/2;
attachments: 17 none, 2 xlsx, 1 audio). One headless `claude -p` session per task and arm, arms
interleaved within each task, one run, `--max-budget-usd 1.5`, phase ceiling 25 USD in code,
STOP-LIMIT on a 429 or usage limit. GAIA's own final-answer instruction and its official scorer
(`gaia_scorer.py`); misses the scorer might have got wrong go to a hand review.

| arm | what each session loads |
|---|---|
| N | a clean user: its own empty `CLAUDE_CONFIG_DIR`, the subscription's OAuth token, `--setting-sources user`, its folder under `C:/sp-runs/h2h` (outside the home folder); no plugins, skills, MCP servers, hooks or CLAUDE.md |
| S | the same, plus what `sanchopanza install` writes by default into that user folder (run for real per session, then checked against `gaia_arms.SP_USER_SETTINGS`), plus `TYPESAFE_API_KEY` |

Both arms share the flag settings: the tool allow list, WebFetch denied to the hosts that serve
the set, and a PreToolUse hook (`deny_hook.py`) that denies any call naming them and adds them to
every web search's `blocked_domains`.

**What S carries (the default install, user scope):**

- `PreToolUse` `Agent|Bash|PowerShell|Task|WebSearch|bash|execute|run_command|shell`: `sanchopanza hook` (routing of delegations, search routing, shell guard; Jev when the key is set).
- `PostToolUse` `Agent|Task`: `sanchopanza hook` (review of a subagent's report).
- Compaction guard: `PreCompact` `manual|auto`, `SessionStart` `compact`, `PostToolUse` `Bash`: `sanchopanza guard-hook`.
- `env`: `SANCHOPANZA_CONTEXT_BUDGET=160000`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`, `SANCHOPANZA_GUARD_PROFILE=coding`.
- Skill `sanchopanza-code` in the user's `skills/`.
- No MCP server: a user-scope install prints the `claude mcp add` line for `find_in_repo` instead of writing it. The browse hooks (crawl, prune, sources, fetch), candor, memory, find-auto and the autopilot are opt-in and not installed.

**N is clean, checked for free** with Claude Code's local `/context` (Haiku, no model call):
a fresh `CLAUDE_CONFIG_DIR` with the folder **under** the home folder and the default setting
sources loads the owner's `~/.claude/CLAUDE.md` and the eight `~/.claude/rules/*.md` as project
memory (upward search); outside it, nothing. `--setting-sources ""` loads no memory file even under
the home folder, but it also drops user settings and user skills, so S's install would not load;
hence `user` in both arms. In the sessions' own transcripts, N's skill listing holds only Claude
Code's built-in skills and S's adds `sanchopanza-code`; N's user folder holds no settings or
skills. A Haiku probe through the same runner (made-up task, Bash, WebSearch and Agent) showed S's
hooks running through the frozen copy (5 calls in the shim's log) and Jev answering (1 decision).

## Results

40 sessions, **4.02 USD** at list price (subscription), no 429, no session at its cap, every
session gave a FINAL ANSWER. Jev: 0.0008 USD.

| | N | S |
|---|---|---|
| right, official grade | 14/20 | 15/20 |
| right, with hand review | 14/20 | 15/20 |
| by level (1 / 2 / 3) | 2/4, 10/14, 2/2 | 2/4, 11/14, 2/2 |
| cost, mean / median USD | 0.110 / 0.049 | 0.091 / 0.055 |
| turns, mean / median | 4.9 / 3.5 | 4.9 / 3.0 |
| wall, mean / median s | 35.6 / 23.0 | 31.5 / 22.0 |
| tokens: input / cache read / cache write / output | 578k / 1,803k / 187k / 35k | 322k / 1,815k / 172k / 32k |
| web searches | 21 | 17 |
| tool calls | WebFetch 31, WebSearch 21, Bash 14, ToolSearch 10, PowerShell 2 | WebFetch 31, WebSearch 17, Bash 17, ToolSearch 10, PowerShell 2, Read 1 |
| sessions answered with no tool | 6 (5 right) | 7 (5 right) |
| sanchopanza hook calls (sessions) | - | 52: `hook` 36, `guard-hook` 16 (12 of 20) |
| Jev decisions | - | 20: search 16 (all `full`), guard 4 (all allowed) |

Paired on the 20 tasks: one discordant task, S right and N wrong; exact McNemar p = 1.0. Cost
S - N: mean -0.019 USD, 95 % bootstrap interval [-0.073, 0.021]; ratio of means 0.83
[0.52, 1.23]. Wall: ratio 0.89 [0.60, 1.27].

**Read by hand.** No sanchopanza hook changed anything in any session: all 16 search decisions
routed to the model's own search, the 4 guard decisions allowed the command, no hook output reached
a transcript, no subagent was used and nothing compacted. Every difference between the arms is
therefore run-to-run variation of the same model, and the numbers that favour S are that:

- The discordant task (`624cbf11`): S's session fetched the source with Bash and found the answer
  in it; N's, with the same tools on offer, gave an answer sharing no word with the gold. S's hooks
  made 6 decisions there, all to let the call through.
- S's lower mean cost comes from two tasks: `de9887f5` (N 0.54 USD in 22 turns, S 0.12 in 6) and
  `2a649bb1` (N 0.23 with tools, S 0.03 answering at once). Two others go the other way
  (`e4e91f1c` S 0.35 vs N 0.24, `624cbf11` S 0.36 vs N 0.26). The smoke run of the first task gave
  the reverse of the dev run on the same task (N with tools, S at once).
- The 11 wrong answers (5 tasks both arms, 1 N only) share no word with the gold but one list
  item in one task, in both arms alike; the scorer's review flagged none.
- Four sessions were flagged as possible leaks. In three the match was the task id, which was part
  of the session's folder path (the confirmation names folders by a hash); in one, the benchmark's
  name in a search result. No flagged result held the gold, except where the agent's own fetch of
  the source did (`624cbf11`, S); in `de9887f5` the gold is too short to test that way and the
  flagged results are the session's own paths.

## What this says for the confirmation

- The pipeline works end to end, both arms are what they claim to be, and a session costs about a
  tenth of the planned 0.35 USD (mean 0.10): the 135-task confirmation on Sonnet would be about
  27 USD at list, not 95.
- On GAIA the default S is passive: its hooks see Bash, WebSearch and Agent, decide, and let every
  call through. A confirmation of the default would compare N with N plus latency and a skill
  listing; 6 or 7 of 20 sessions answer without a tool, where no hook can act at all.
