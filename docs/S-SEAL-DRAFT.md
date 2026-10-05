# Arm S for the final comparison: draft of the seal

Draft of 2026-10-05 (indagis s-seal worktree, branch `s-seal`, from main `ee81d0d`, which holds
browse and memory v8.3). It is due sealed 2026-10-06 12:00. What the owner asked for (2026-10-05):
"use sanchopanza in full: hooks, tools, everything, integrated in the agent even if the agent
doesn't use it; context management inside the session, memory, EVERYTHING we have". Nothing here
spent money: no `claude -p`, no API, no Jev. Every install ran into `C:\sp-runs\s-seal-dry\`.

Commits on `s-seal` that S depends on (all local, nothing pushed):

| Commit | What |
|---|---|
| `91d2728` | test re-pinned: `plan`'s output after memory v8.3 (only memory's own matchers changed) |
| `ca8bdfe` | candor's lock: no-id fallback kept per `CLAUDE_CONFIG_DIR`; parallel sessions tested apart |
| `cef2310` | `install --crawl` wires every event crawl answers; `--fetch` registers its server |
| `1f3499e` | prune never touches `browser_evaluate` (matcher and handler), which crawl owns |

**Seal S at `1f3499e` or later** (`s-seal`, merged into main after this draft), not at main
`ee81d0d`: there the browse env below does nothing or removes the crawl line, `--fetch` sends the
agent to a tool that is not there, and prune can rewrite an evaluate crawl has rewritten
(section 3).

## 1. The recommended line

**Agreed with indagis-a1 (browse owner) on 2026-10-05**: a1's candidate line, plus
`SANCHOPANZA_GUARD_CHOOSER=keep` and a store and state folder per session. One command per suite,
run from the task's working folder, into a settings file the session loads. The only difference
between the suites is `--guard-profile`.

```
sanchopanza install --path <settings.json> \
  --guard --guard-profile <coding|sandbox> --context-budget 160000 \
  --memory --candor --find --find-auto --skill \
  --scan-content --check-done \
  --content-tools WebFetch,WebSearch,mcp__sanchopanza-fetch__fetch_passages \
  --crawl --prune --fetch \
  --provider jev --write
```

- `coding` for code suites (SWE-bench), `sandbox` for web and research suites (GAIA, FRAMES).
- `--context-budget 160000`, `--guard`, `--skill` and (for a project settings file) `--find` are
  defaults; they are spelled out so the seal does not move if a default does.
- `--provider jev` writes `SANCHOPANZA_PROVIDER=jev`; it needs `TYPESAFE_API_KEY` in the session's
  environment (owner decision D1). Without it every decision point falls to the null decider
  and S is the free half of sanchopanza.

Env, written into the same settings file's `env` block (hooks and MCP servers inherit it):

```
SANCHOPANZA_GUARD_CHOOSER=keep          # the measured cascade (6/7); needs the provider
SANCHOPANZA_CRAWL_LINE_VERSION=6
SANCHOPANZA_CRAWL_NOTES=3
SANCHOPANZA_CRAWL_ECHO=short
SANCHOPANZA_CRAWL_LINE_AT=prompt
SANCHOPANZA_CRAWL_NOTES_AT=front
SANCHOPANZA_CRAWL_SHOT=snapshot-first
SANCHOPANZA_FETCH_VERSION=2
```

Per session (or per pair), so that parallel S sessions share nothing on disk: `SANCHOPANZA_MEMORY_STORE`,
`SANCHOPANZA_CANDOR_DIR`, `SANCHOPANZA_JOURNAL`, `SANCHOPANZA_GUARD_DIR`, `SANCHOPANZA_CRAWL_DIR`,
`SANCHOPANZA_FETCH_DIR`, `SANCHOPANZA_ARCHIVE`, each under the session's run folder outside
`C:\Users\roman`. Without them every S session on the machine writes to `~/.sancho` (it exists here,
so it wins over `~/.sanchopanza`).

### With and without `--knowledge`

**Update 2026-10-05 night:** `--knowledge` is on main (merge 5da2635 of knowledge 402021e onto
7752471; indagis-a1's suite 3032 passed, 0 failed). It registers `sanchopanza-knowledge`
(`search`, `read`, `pick`, alwaysLoad). Decision for coherence (indagis-a1, recorded here by
indagis-95): with `--fetch` and `--knowledge` together, knowledge is the **only** page reader. The
fetch hook, the `sanchopanza-fetch` server and its approval are not wired, and install says so
once on stderr; pinned by
`tests/test_install_knowledge.py::test_fetch_and_knowledge_together_leave_one_hook_and_one_reader_server`.
So **S1 drops `--fetch`**, and `--content-tools` carries the three
`mcp__sanchopanza-knowledge__*` tools instead of `fetch_passages`. A dry run of S1 (in `C:\tmp`) left
on WebFetch only the knowledge hook (plus candor's, which only records), on WebSearch the
knowledge hook and the generic guardian (repeat-query check, no redirect), and no fetch server.
Offline evidence (a1): search puts the gold article in 70-73 % vs WebSearch's 44-48 %; read
delivers the gold in 62/66 vs WebFetch's summary 22/66; QASPER 88.7 % at 995 tokens. Live dev
of S1 against N runs before 12:00. Per-session overhead of the three tools: to count, as in
section 4.

The text below predates the merge. Two versions of the line:

- **S0, sealable today:** the line above.
- **S1, if knowledge lands before the seal:** the line above plus `--knowledge`, and only if, at
  the seal, (a) its dry run passes the checks of section 3 against S0's settings with no new
  conflict, (b) its per-session overhead is counted as in section 4, and (c) it has the same kind
  of evidence row as the others in section 2. If any of the three is missing at 12:00, S0 is
  sealed and knowledge goes in as an S+X arm, as the plan allows.

### How S is applied to a clean session

N is a clean `CLAUDE_CONFIG_DIR` per pair. S must be that same clean config plus what install
writes, and nothing else. Two ways; the seal names one (owner decision D5):

- **Project install** (`--path <task>/.claude/settings.json`): find and fetch go into
  `<task>/.mcp.json` and are approved by name; the skill goes to `<task>/.claude/skills/`. Simple,
  but it puts `.claude/` and `.mcp.json` in the task's checkout: the SWE-bench patch must be taken
  with those excluded, and N then needs the same paths absent.
- **Config install** (`--path <CLAUDE_CONFIG_DIR>/settings.json`, run from the task folder): the
  skill lands in the config's `skills/`; `.mcp.json` still goes to the folder install ran from, with
  `--find` explicit. `--fetch` then only prints the `claude mcp add-json --scope user` line, which
  the runner must run with the same `CLAUDE_CONFIG_DIR`.

## 2. Component by component

Overhead is fixed text the model reads on every request (as cache reads after the first): tool
schemas, server instructions, the skill's listed description. Counted from what the code serves
(`tools/list` of each server, the texts in the package), at 4 characters a token: **an estimate**,
±30 %. Per-prompt and per-event text is listed separately: it is appended, not fixed.

| Component (flag) | In S? | What it writes | Why / evidence | Fixed tokens per request |
|---|---|---|---|---|
| Base guardian (`sanchopanza hook`, no flag) | in | PreToolUse on Agent, Task, WebSearch and the shells; PostToolUse on Agent, Task and the content tools; Stop `*` with `--check-done` | Always wired. Shell guard profile `coding`: 0.01 % of 33,119 of the owner's real commands denied, against 12.2 % for `sandbox` (`2026-09-30-guard-coding`). Delegation fix held in phase D (0 failed) | 0 |
| Compaction guard (`--guard`, default) | in | PreCompact `manual\|auto`, SessionStart `compact`, PostToolUse `Bash` | Confirmed in development only: tasks finished native 2/7, rule 5/7, cascade keep 6/7, McNemar p 0.375, Haiku (`2026-09-29-context-guard`). The `keep` chooser needs the provider | 0 (a block after each compaction) |
| Context budget (`--context-budget`, default 160k) | in | `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`, `SANCHOPANZA_CONTEXT_BUDGET=160000` | Simulated on 1,283 real sessions: re-read cost 42-44 % of today's at 140-200k. Live: Haiku compacts at 160.6-161.7k; Sonnet peaked at 80k and never compacted. Not measured live past 200k (`2026-09-30-adopt/dev-log.md`) | 0 |
| Memory (`--memory`, v8.3) | in | UserPromptSubmit, Stop, SessionEnd, SessionStart (all), PostToolUse on the file tools and the shells | Carry v6.2 confirmed on Sonnet 5.5 (23/24 vs 14/24, p 0.002), no margin on Opus 5.5 (16/16 vs 14/16); v8 cross 24/24 vs 19/24 (`2026-10-02-memory-carry`). v8.x supersession merged | 0 fixed; standing rules at start when the store has any (none in a fresh store) |
| Candor (`--candor`) | in | five hooks (`*` on Pre/Post/PostFailure), `SANCHOPANZA_CANDOR_SNAPSHOT=1` | Round 4: 105/105 counterfactuals locked, 1/61 honest sessions; v6 locks 1.8 % of real SWE-chat turns; the Indagis scene gave 2 false alarms in 3. Lock is per session (`4fa334f`, `ca8bdfe`) | 0 fixed; 59 per prompt (the status-block request) |
| find_in_repo (`--find`) | in | `sanchopanza` server in `.mcp.json`, `alwaysLoad` | Retrieval: Acc@1 51.3 % vs BM25 13.7 % on 117 Verified issues. End to end: called in 6/27 (find-e2e), 2/78 (phase D); never a measured gain | 329 (tool) + 73 (server instructions) |
| find_auto (`--find-auto`) | in | `mcp_tool` hook on PostToolUse and PostToolUseFailure of the search and file tools; server started `--auto` | Opt-in, unmeasured end to end; probe: fired 4/4 where due, gold shown 3, followed 3 (`HANDOFF-2026-10-05-adopt-d`). Tool hidden from the model (`_meta.ui.visibility`) | 0 (hidden) |
| Skill `sanchopanza-code` (`--skill`, default) | in | `SKILL.md` beside the settings | Explains each part; never measured on its own | 121 (listed description; the 752-token body only when invoked) |
| Content scan (`--scan-content`) | in | PostToolUse on WebFetch, WebSearch, fetch_passages, shell fetches; `SANCHOPANZA_SCAN_CONTENT=1` | Detection only, never a barrier; needs the provider to decide anything | 0 |
| Check done (`--check-done`) | in | Stop `*`, `SANCHOPANZA_CHECK_DONE=1` | 94 % vs 52 % for the agent's own word on 655 AgentDojo trajectories; not measured on coding; needs the provider | 0 (one send-back at most) |
| Crawl (`--crawl` + v9 env) | in | SessionStart, UserPromptSubmit, PreToolUse on `browser_(evaluate\|take_screenshot)`, PostToolUse on `browser_evaluate` | Confirmations 3, 4, 5 NOT confirmed, all on price; answers and no-harm held (conf 5, Haiku 19 vs 12). v9 in development (Haiku 10/12 vs 6/12) | 0 fixed; line v6 (298) only on prompts that gather (`LINE_AT=prompt`) |
| Prune (`--prune`) | in | PostToolUse on `mcp__.*__browser_(?!evaluate$).*` | Registered 12.4-13.4 % cheaper with Playwright MCP in three rounds (one interval crossing zero), nothing clear in a fourth; about 5 % then nothing with playwright-cli (`browse_hook` docstring, `2026-09-30-browse`) | 0 |
| Fetch (`--fetch` + `FETCH_VERSION=2`) | in | PreToolUse on WebFetch; `sanchopanza-fetch` server, `alwaysLoad` | Dev: Haiku 16/20 vs 15/20 at 0.114 vs 0.177 USD; confirmation fetch1 sealed and running (blind verdict pending) | 176 (tool) |
| Sources (`--sources`) | **out** | Stop hook | indagis-a1: v1 +52 % cost and no more right answers; v2 ceiling +2..+5 per 100 sessions, closed. In only if the owner wants "everything" literally, then with `SANCHOPANZA_SOURCES_VERSION=2` | 0 |
| Autopilot (`--autopilot`) | **out** | compaction plugin (early-access function hooks), PostToolUse `*` arrival cut, masking at 60 % | The 12/12 was retracted (handle bug); redone: native 5/7, lean masking 3/7, delete 0/6. It replaces the summary the guard is built around | - |
| Lean (`--lean`) | **out** | autopilot plus `search_archive` server | Same rerun: 3/7 against native 5/7; the agent never called `search_archive` | - |
| Compact plugin (`--compact`) | **out** | function-hook plugin pruning at `/compact` instead of summarising | Same mechanism as the autopilot's mask; early access; conflicts with the guard | - |
| Find nudge (`--find-nudge`) | **out** | PostToolUse hint | Fired 5/10 on opening listings, converted none; `--find-auto` takes its place (install refuses both) | - |
| Loop guard (`loop_hook`) | **out** | no install flag | Wired once in browse development; never spoke in 12 sessions | - |
| Knowledge (`--knowledge`) | pending | - | Not built yet (section 1) | to count |

**Fixed overhead of S0: about 700 tokens per request** (329 + 73 + 176 + 121), plus 59 per prompt
from candor and, on gathering prompts only, the 298-token crawl line. At list cache-read prices
(Sonnet 5.5 0.20 USD/MTok, Opus 5.5 0.50 USD/MTok) that is 0.00014 USD a request on Sonnet and
0.00035 on Opus, plus one cache write per session (about 0.003 and 0.007 USD at the 1-hour rate):
0.4-0.8 % of the measured cost of a Sonnet 5.5 request (0.018-0.039 USD) and 0.4 % of an Opus
5.5 one (0.082 USD, memory-carry), from the plan's table. Jev's cost is not in this figure (it is per decision).
Time, measured here: each hook process starts in 190-320 ms; Claude Code runs the hooks of one
event in parallel, and a Bash call reaches five of them (base, guard, candor, memory, find_auto).

## 3. Conflicts found, and what was done

1. **Crawl's v9 env did nothing with `install --crawl` (fixed, `cef2310`).** `LINE_AT=prompt`,
   `ECHO=short`, `NOTES_AT=front` and `SHOT=snapshot-first` are read on UserPromptSubmit,
   PostToolUse of `browser_evaluate` and PreToolUse of `browser_take_screenshot`; install wired
   only SessionStart and the evaluate guard (the benches add `V8_HOOKS` and `V81_HOOKS` by hand).
   With the proposed env, `LINE_AT=prompt` removed the line altogether and the other three were
   silent. `--crawl` now wires all four events; without the env the new ones answer nothing
   (tested). `CRAWL_HOOKS` and `_merge_crawl` are unchanged for the sealed benches.
2. **`--fetch` pointed at a server nobody registered (fixed, `cef2310`).** The hook denies a URL's
   first WebFetch and names `mcp__sanchopanza-fetch__fetch_passages`; install only printed how to
   register it. In a clean config the agent was sent to a tool that did not exist, then paid a
   second WebFetch per URL. A project install now writes the server (`alwaysLoad`) and approves it.
3. **The scan did not see what fetch returns (resolved in the line).** Fetch moves page text from
   WebFetch to `fetch_passages`, which `--scan-content` did not watch. The line names it in
   `--content-tools`. The regex escapes the `-` in the server name (`\-`), which Claude Code's
   non-unicode regex reads as `-`; to check in the preflight.
4. **Two rewrites of one result (resolved, `1f3499e`).** On a `browser_evaluate` result, crawl
   (`ECHO=short`, `NOTES_AT=front`) and prune (`mcp__.*__browser_.*`) could both return a replaced
   output, and Claude Code does not document how two replacements merge. indagis-a1 decided: crawl
   owns the evaluate, prune's confirmed result is about snapshots. Prune's matcher is now
   `mcp__.*__browser_(?!evaluate$).*` and its handler returns early on an evaluate even if wired by
   hand. Crawl and prune were never measured together.
5. **Several Stop hooks may send the agent back at once (accepted).** check-done, memory's rule
   audit and (if in) sources can each return a block on the same Stop; Claude Code joins the
   reasons into one more turn. Candor at Stop does not block (`ASK_BLOCK=prompt`); it may lock.
6. **Context flags.** `--autopilot`, `--lean` and `--compact` replace or mask the native summary
   that `--guard` complements, the autopilot's arrival cut is a second PostToolUse rewriter on
   every tool, and their evidence is negative. Out. Guard + budget + memory is the combination with
   no overlap: the budget decides when Claude Code compacts, the guard what survives it, memory
   what a later request gets back.
7. **Prompt cache.** Nothing in S rewrites `tools`, the system prompt or earlier messages
   mid-session: the MCP tool lists are fixed at start, the skill listing is static, and every hook
   adds text after the last message or replaces a result before it enters the context. The one
   deliberate reset is the compaction the budget triggers at 160k, as native compaction does.
   **To check in the free preflight:** that `find-mcp --auto`, which builds its index at start,
   is connected before the first request, so the tool list does not change after it (capture the
   requests on a local port with a dummy key, as `1ea9302` did).
8. **Hook order.** Claude Code runs an event's matching hooks in parallel, so S has no order to get
   wrong; on PreToolUse a deny from any hook wins over the evaluate guard's rewrite.
9. **Env.** No two components write the same variable. `CLAUDE_CODE_AUTO_COMPACT_WINDOW` is kept if
   the config already sets one (N's clean config does not).
10. **Grader collision (resolved by the runner).** Candor asks every prompt for four status lines
    at the end of the final reply, which would follow GAIA's `FINAL ANSWER:`. indagis-a1's GAIA
    extractor takes only the `FINAL ANSWER` line, in both arms, so the block never reaches the
    scorer and candor stays in S as it ships (`ASK_BLOCK=prompt`).
11. **Silent without a provider.** check-done, the content scan, the guard's `keep`, prune's Jev
    ranking, memory's recall judged at a session's first request and the candor judge decide
    nothing on the null decider. Phase A's S arms ran without Jev without anyone noticing
    (`freeze.py` lacked the extra): the preflight must assert the provider resolves to `jev`.

The candor lock, as asked: the machine-wide file was already gone (`4fa334f`, 2026-09-30: one lock
per session id). What was left is fixed in `ca8bdfe`: a session with no id (the hook gets none)
falls back to its project and now also its `CLAUDE_CONFIG_DIR`, so two harnesses in one checkout
are two locks. Tests show two parallel sessions in one repository never hold each other. A session
with an id is unchanged, and so is the fallback when `CLAUDE_CONFIG_DIR` is unset.

## 4. Memory v6.3 on main

`d0758c7` and `43714fd` reached main through the v7/v8 line. What they add:

- `memory_hook.shell_first`: a PreToolUse deny-once that shows the record before the first shell
  write. **Off**: it runs only with `SANCHOPANZA_MEMORY_SHELL_FIRST=deny`, and install does not
  wire memory on PreToolUse at all, so it cannot fire in S.
- The tree snapshot that goes missing now says why (`worktree.probe`): a `tree` row in
  `MEMORY_STORE_LOG` (only when that is set) and a `why` beside the request's tree file. **On**,
  diagnostic only: it changes no record and nothing the agent sees.
- Benchmark modules (`commit_label.py`, `variants_v63.py`, `v63_tree_repeat.py`,
  `shell_first_pilot.py`): not installed.

## 5. Decisions for the owner

- **D1. Jev in S.** With `--provider jev` (and `GUARD_CHOOSER=keep`), Jev's decisions are part of
  S's cost, as the plan says. Without it, six components decide nothing (conflict 11).
- **D2. Candor in lock mode.** The product locks the session on a critical finding, and in an
  unattended run a lock ends the task. The rate on real turns is 1.8 %; the Indagis scene had 2
  false alarms in 3. Lock (the product) or `MODE=observe` (findings only).
- ~~D3. Candor's status block and GAIA's grader~~: resolved by a1's extractor (conflict 10).
- ~~D4. Crawl and prune on one evaluate result~~: decided by a1, applied in `1f3499e` (conflict 4).
- **D5. Project or config install** (section 1), and memory: per-session stores (independent
  tasks, nothing to carry) or one store per suite (memory works across tasks of a repository, but
  order and parallelism then matter).
- **D6. `--sources`**: out, unless "everything" is meant literally (then `SOURCES_VERSION=2`).
- **D7. `--knowledge`**: S0 now, or wait for it under the three conditions of section 1.
- **D8. Seal at `1f3499e` or later**: the fixes came from `s-seal`.

## 6. Notes for the seal itself

- The hooks run `sanchopanza` from PATH: the sealed run must put the sealed commit's package (with
  the `jev` extra) first on PATH, and the preflight must print `sanchopanza.__file__` and the
  provider from inside a hook, as Indagis's `procedencia.py` does.
- Dry runs: `C:\sp-runs\s-seal-dry\{coding,sandbox}-{plain,sources}\` (settings, `.mcp.json`, skill;
  a second run of the same line changes nothing). Overhead probe: `C:\sp-runs\s-seal-dry\overhead.py`.
- Full suite on `s-seal` at `cef2310`: 2,918 passed, 40 skipped (rerun after `1f3499e` before the
  merge).
