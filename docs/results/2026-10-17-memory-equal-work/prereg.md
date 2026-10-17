# Equal work: the default install at user scope against clean Claude Code that a person tells to go on, Sonnet 5.5. Written before its data

One lot on F2's runner and scenes (`docs/results/2026-10-16-memory-f2`) as W17 ran them
(`docs/results/2026-10-16-memory-w17`), parameterised, not forked: `benchmarks/memory_carry/
handoff*.py` with the run `ew-sonnet` and the lot `ew` (`handoff.RUNS`, `handoff.LOTS`), plus one
new rule, the nudge (`benchmarks/memory_carry/handoff_nudge.py`), and its reading
(`benchmarks/memory_carry/handoff_ew.py`). The owner approved the lot on 2026-10-17 at about
13:20: rule R3 ("N0 with a nudge"), 12 scenes x 4 repetitions (2 named, 2 bare) = 48 pairs,
Sonnet 5.5 only, about 12.5 to 13.7 USD expected. **The run's hard cap is 22 USD in code**
(`handoff.EW_CAP`): the owner's decision on 2026-10-17 at about 14:25, asked in session, before
any of this lot's data (the first draft had 18 USD). Sealed by `prereg.sha256` (see "Seal");
until that file matches, every live path refuses. No session of this lot has run.

## Question

W17's Sonnet lot found that S' (the default install at user scope) continued a two-step feature
in 48 of 48 pairs against clean Claude Code's (N0) 9 of 48, at 1.187x N0's cost per pair
[1.148, 1.244]: "S' better than N0; no gana (cost)". Most of that extra cost is work N0 did not
do: an N0 session 2 that did not build step 2 mostly stopped to ask what to continue or whether
to go on, and ended there, because nobody answered. W17's README says so as its limit ("in real
use the person answers"), and W17's prereg, sealed before its data, already put F2's cost gap on
"N0 asking a question in session 2 instead of working".

**This lot answers W17's question at equal work:** when a person answers a session that stopped
with a plain "Yes, go ahead.", does S' reach the finished step 2 without costing more than N0
(cost per pair below 1.00 with success not worse), or with more success at no more than 1.10x?

**Why this rule and not another** (reasons, not the post hoc figures below). Four other rules were
weighed (`propuesta`, 2026-10-17, not tracked): the same work in session 1 only (R0: measures the
install's overhead, not the product, and leaves out session 2, where the value is); the pairs
where both arms finished (R1: conditions on N0's outcome, a stratum chosen after the fact, 9
pairs in W17); cost per success (R2: counts success twice, undefined when N0 succeeds nowhere,
and folds two axes into one where rule 2.4 and Pareto ask for two); up to K nudges (R4: K is a
degree of freedom, and a blind "go on" to a session that asked "what should I continue?" is
noise). R3 gives **both arms the same chance to finish**, decided by code and the same in both
arms; it keeps success and cost as separate axes (rule 2.4 of the final scoreboard); and
everything arbitrary in it **favours N0**: the person is perfect (they nudge exactly when step 2
is missing, which they know from the checks), costs nothing (their time is not counted), and S'
controls neither the trigger nor the text. A "gana (coste)" here is therefore conservative.

## Arms

Both arms as in W17: clean Claude Code, a fresh `CLAUDE_CONFIG_DIR` per arm run, kept across its
calls, signed in with the subscription's OAuth token only; **Claude Code 2.1.287** pinned (a
private copy first on the launcher's PATH, `DISABLE_AUTOUPDATER=1`; the launcher refuses another
version, exit 9); `claude -p` with `--output-format stream-json --verbose`, `--settings "{}"`,
`--allowedTools Bash Read Edit Write Glob Grep`, default permission mode; model
`claude-sonnet-5-5`; a 900 s timeout per call. Session 1 is the scene's `first` prompt in both
arms; its work is committed; session 2 is a new session with the pair's line.

- **N0**: clean Claude Code 2.1.287, nothing installed.
- **S'** (arm `S` in the rows): N0 plus the default install at user scope, exactly W17's arm:
  `sanchopanza install --scope user --memory --write --path <arm's CLAUDE_CONFIG_DIR>/settings.json`
  (`carry_s.U_INSTALL`, `carry_s.install_user`), run from that configuration folder, from `src/`
  at the sealing commit, which is **`src/` and `pyproject.toml` as on main 4c143e1 (`src/` last
  changed at 88f5400)**. Every `sanchopanza ...` hook command is put behind `carry_hook.py ...
  sub` (the arm's own state; the TypeSafe key never in the agent's environment); Jev decides with
  the shipped `jev-1.13.0`; the store starts with F2's 7 decoy rules of other scenes; no MCP
  server (at user scope `install` only prints the `claude mcp add-json` line, not run).
  - **Against W17's S'** (`src/` cbfd932, plus 88f5400 in its Opus redo): the installed
    `settings.json` and skill are **byte for byte the same** (checked free on 2026-10-17: the
    user-scope install written from cbfd932's `src/` and from 4c143e1's, diffed: no difference),
    and the preflight checks again that the runner's install equals a bare `sanchopanza install
    --write` into `~/.claude` (`handoff_preflight.user_check`). On the path S' runs, main has
    since added: memory's bridge into Claude Code's own memory (`memory_native`), imported by the
    memory hook but run only when `SANCHOPANZA_MEMORY_NATIVE` is on, **off by default and not
    set**; and in `CappedDecider` a distinct `LedgerBusy` when the Jev ledger's lock is not had in
    time (319ee79): the call is not made, as before, and the hook falls open as before. The rest
    (check_done's evidence windows, OpenAI's Decisions provider, `select_passages`' free order,
    `relate_facts`' `unrelated_at` default, the page window) is not on the installed hooks' path.
  - The installed `env` (`SANCHOPANZA_CONTEXT_BUDGET=160000`,
    `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`, `SANCHOPANZA_GUARD_PROFILE=coding`) reaches S's tools,
    a tell of the arm, as declared in W17.
  - **Jev's cap in code:** every hook's decider goes through `CappedDecider` on the run's own
    `jev-ledger.jsonl` (`capped_sub.py`), **0.50 USD for the run** (`RUNS["ew-sonnet"]["jev_cap"]`).

**Session 2's line, two strata, as W17:** **named** (the scene's F2 line, "Let's continue with the
shipping labels."), repetitions 1-2; **bare** (`BARE_LINE` = "Let's continue."), repetitions 3-4.

## The nudge (rule R3)

- **When:** after session 2 ran (not cut, no usage limit), the scene's checks run with the agent's
  environment (no key, no PYTHONPATH) **on a copy of the repository**, so that the agent's tree is
  not touched (next point). **If and only if the
  `task` check fails** (step 2 is not in the repository), the arm gets one nudge. A step 2 that
  is there but breaks C or D gets none (`handoff_nudge.wanted`): a person who sees the step done
  would not tell it to go on. The same rule in both arms; at most one nudge per arm.
- **The tree the nudge resumes on is exactly the one session 2 left.** Nothing is committed
  between session 2 and the nudge (session 2's work stays as it left it, committed or not, as a
  person who answers at once would leave it). Session 2's checks run on a copy
  (`handoff.checks_apart`): the repository copied without `.git` into the lot's own folder
  (`<arm record>/checks-s2/repo`, which the agent never sees), the checks run there with
  `PYTHONDONTWRITEBYTECODE=1` and pytest's `-p no:cacheprovider`, and the copy is removed; so no
  `__pycache__`, `.pytest_cache` or other file reaches the agent's tree, and `git status` is
  unchanged. Why it matters: Claude Code's system prompt carries the repository's state; a
  different tree could rebuild it on resume, break the prompt cache and make the nudge dearer
  (about 0.09 USD more a nudge, written again instead of read), which would favour S'. As a check
  in code, the tree's state (`git status --porcelain` and the sha256 of every file's path and
  bytes, `.git` aside, `handoff.tree_state`) is taken before session 2's checks and again just
  before the nudge; if they differ, the arm is cut ("nudge: the repository changed between
  session 2 and the nudge") and `tree_kept` is false in the row. Nothing later used the commit
  the first draft made there (no diff and no check reads the commit history): the final checks run
  in the agent's tree, as in W17.
- **What:** session 2 is resumed once, `claude -p --resume <session 2 id> "Yes, go ahead."`, in the
  same repository and configuration folder, with the same flags and the run's call cap
  (`handoff.nudge_step`, which reuses `handoff.handoff_step`, F2's resumed turn).
- **The text, exactly:** `Yes, go ahead.` (`handoff_nudge.NUDGE`). Chosen now and **not tried on
  any arm before the seal** (tuning it on N0 in a pilot would tune the comparator). It names
  nothing of the scene (tested against every scene's tells) and is **not** memory's continuation
  cue (`memory_recall.continuation` is false for it, tested), so S' gets no record by code for
  it; whatever S's hooks give at that prompt is the product as it ships.
- **The person:** answers blind, whatever session 2's last message said (a question, a plan, a
  claim that it was done), with the same words; knows only that step 2 is missing; costs nothing.
- **Then:** the checks run again, in the agent's tree as in W17, and **they decide** (`kept_all`
  and every `*_pass` of the row; in an arm not nudged they run there too, and an arm whose two
  readings differ is reported, `checks_disagree`, expected 0; it sees a copy that passes
  where the tree fails, not the reverse, which would add a nudge: no check or scene test
  reads git or an absolute path, so neither is expected).
  The row keeps the checks after session 2 (`checks_s2`, `kept_all_s2`), whether the arm was
  nudged (`nudged`) and the nudge's facts (`nudge`: its own cost, the reported running total, how
  the own cost was read, whether it resumed session 2's session and carried its context, tokens,
  wall time, its init, `tree_kept`, the tokens of its **first request** (input, cache read, cache
  write) beside those of session 2's last request, which show whether the resume read session
  2's context from the cache or wrote it again, and, in S', the SessionStart sources S's memory
  hook answered).
- **Its cost:** Claude Code 2.1.287 reports, for a resumed turn, the session's running
  `total_cost_usd` (session 2 plus the turn). The row counts the turn's **own** cost:
  `handoff_cost.turn_own` (F2's H turn), the total less session 2's cost when that equals the
  turn's tokens at Claude Code's rates, else the turn's own report or its tokens priced. A nudge
  that reported no cost is charged its cap and one worst turn (below).
- **NOT RUN (the arm is cut, never retried):** a nudge that timed out, ended without a result,
  ran another model or Claude Code, is not session 2's session (`same_session`), or whose first
  request does not hold at least half of session 2's last one (`context_carried`, F2's rule). A
  nudge stopped by its own `--max-budget-usd` counts as run, as a session does
  (`handoff_nudge.cut_of`).
- **S' must run as S' in the nudge too** (`carry_s.session_breaks(..., start=False)`): the memory
  hook answered the nudge's prompt without an error, did not fail at every Stop, and the
  `sanchopanza-code` skill is in the turn's init; else a harness cut that stops the run (exit 4).
  **The resumed session's SessionStart is recorded, not required:** the installed SessionStart
  entry matches every source (matcher `""`), and the memory hook answers source `resume` as any
  start, without an error (tested); Claude Code documents `resume` as a SessionStart source, but
  whether 2.1.287 under `-p --resume` sends it is not known, and sessions 1 and 2 already proved
  that the user settings load. The sources seen are reported.

## What the agent sees is neutral

As W17, with this lot's own folders:
- each arm works in `C:\sp-runs\w20\r1\t<NN>-<x>` (its repository in `repo\`, its configuration in
  `claude-config\`), NN the pair's number, x a letter per arm from a seeded shuffle; the lot's own
  files (rows, ledger, streams, install output, logs) in `C:\sp-runs\mem-ew\ew-sonnet\`, which no
  session is pointed at. Neither root is, or lies under, F2's or W17's roots (tested);
- tested (`tests/test_memory_carry_ew.py`): no path or file under the work root of any scene, both
  arms and both strata names the scene, the arm, the model, the stratum, the lot, the nudge, or
  gives away the scene's C, D or step 2 (S's installed settings and skill exempt from that last
  check only);
- the checkout's path may not name the lot: the launcher (exit 10) and `handoff_night.py` (exit 11,
  `handoff_seal.path_refusal`) refuse a path with `f2`, `memory`, `handoff`, `memlot`, `w17`,
  `sonnet`, `opus`, `ew`, `equal` or `nudge` in it (create it as, e.g., `..\sp-w20`);
- what remains, inherent and declared, is W17's (S's hooks name the sealed worktree's path and
  `benchmarks\memory_carry\carry_hook.py`; the skill as shipped; the installed `env`; what lies
  beside the arm's folder; a session can open its own configuration folder). Session 2's checks
  before the nudge leave nothing in the agent's tree (they run on a copy, above);
- **shared prompt cache.** Both arms run on the same account one after the other: Anthropic's
  server-side prompt cache can serve one arm a prefix the other just wrote. **Another paid
  Sonnet lot (the guard lot) may run on this machine and account at the same time**: its
  sessions can share Claude Code's system-prompt prefix with this lot's and warm or evict it.
  That touches both arms of a pair alike, since they run back to back and their order alternates;
  cache reads and writes are reported per arm. Its load can slow wall time, which decides
  nothing.

## Scenes and checks

F2's 12 scenes (`scenes_handoff.py`), unchanged, with F2's checks: `task`, `fact` (C), `decision`
(D), `intact`, and the repository's tests. **Primary success, "kept all": `task` and `fact` and
`decision` after the nudge** (after session 2 when there was no nudge). F2's note on checks a
natural implementation can pass without knowing C or D (`h_loud`, `h_nomutate`, `h_batch`,
`h_merge`) holds here too.

## The run

| run | model | scenes x reps | pairs | named / bare | calls | expected USD | run cap |
|---|---|---|---|---|---|---|---|
| `ew-sonnet` | Sonnet 5.5 | 12 x 4 (reps 1-4) | 48 | 24 / 24 | 192 + nudges | 12.5-13.7 | **22.00** |

A pair is one scene at one repetition in N0 and S', one arm after the other. **Which arm goes first
in a pair is W17's** (`build_plan`: arm N0 or S' first by the scene's index and the repetition;
each arm first in 24 of the 48 pairs, 12 in each stratum). **The order of the pairs is new and
interleaved** (`handoff.pair_order`, `RUNS["ew-sonnet"]["order"]`): a named pair, then a bare
one, scene by scene, repetitions 1 and 3 first, then 2 and 4 (h_batch r1, h_batch r3, the next
scene r1, r3, ..., then r2, r4, ...). So any first k pairs hold the two strata alike (at most one
apart), and if the cap stops the run, it removes named and bare pairs alike and does not change
what the estimand mixes. Fixed now, before any data (W17 ran repetition by repetition, the bare
ones last).

- **Expected cost.** W17's Sonnet lot cost 11.18 USD for these 48 pairs (Jev's preflight
  included). The nudges come on top: in W17 N0 left step 2 undone in 39 of 48 pairs, and a nudge
  that does step 2 in a resumed session costs about 0.03 to 0.065 USD (half to all of a session 2
  that does step 2; W17's S' session 2 median 0.062): 1.2 to 2.5 USD. **Expected 12.5 to 13.7
  USD; hard cap 22.00 USD.** **[assumption]** The lower call cap (below) does not bind: W17's
  dearest Sonnet session was 0.118 USD.
- **A cold cache.** If the resume does not read session 2's context from the prompt cache (the
  first request writes it again), a nudge costs about 0.09 USD more: 0.12 to 0.155 a nudge, **15.9
  to 17.2 USD** for the lot. The fix above (an untouched tree, the nudge right after session 2,
  well inside the cache's lifetime) removes the cause this lot can control; whether Claude Code
  2.1.287 rebuilds its system prompt on `--resume` for another reason is not known, and the
  first request's cache read and write per nudge are reported.
- **Where the cap stops the run**, recomputed on the interleaved plan with W17's Sonnet costs per
  pair (11.18 USD over the 48 pairs) and W17's 39 pairs where N0's `task` failed (S' none), for a
  mean nudge cost m (free, `sizing.py`, kept with the proposal, not tracked): **all 48 pairs start
  while m <= 0.1777 USD; 40 or more (the verdict's minimum) while m <= 0.270 USD**; past that the
  verdict is "sin veredicto". A warm nudge (0.03-0.065) and a cold one (0.12-0.155) both fit 48
  pairs. (With the first draft's 18 USD these were 0.072 and 0.145.) A cut by the cap keeps
  the strata even in any prefix of the plan, but drops repetitions 2 and 4 of the scenes last
  in the order (h_pages, h_judge, ...), not pairs spread over every scene. An arm whose tree
  changed between session 2 and the nudge is cut before the nudge is asked, so nothing is
  paid for it.
- **Expected wall time:** W17's Sonnet lot took 118 minutes for 96 arms (about 74 s an arm with
  building and checks); about 40 nudges of 40 to 60 s and a second round of checks add about 30
  to 40 minutes: **about 2.5 hours**.

## Sequence (`handoff_night.py --lot ew`, `ew-night-run.cmd`)

`ew-sonnet` alone, no pilot and no gate. S' not running as S' stops the run at its first such arm.
Any stop other than the end of the run ends the night. A relaunch resumes: recorded arms are kept.

## Criteria (fixed now, over pairs with both arms run; `handoff_ew.analyse`)

A pair counts when both its arms ran (no `cut`, no usage limit, `kept_all` recorded) and both
recorded their checks after session 2 (`kept_all_s2`).

- **The cost ratio (the estimand)** of a pair is S's whole cost (its sessions' own costs, its
  nudge's own cost if it had one, and its Jev decisions) over N0's whole cost (its sessions and
  its nudge if it had one). Its statistic is the **median over pairs**; its interval the
  percentile bootstrap 95 % of that median (linear interpolation), pairs taken in (scene,
  repetition) order and resampled with replacement, **10,000 draws, seed 20261021**
  (`handoff_ew.SEED`, this lot's own, fixed now; `handoff_pairs.ratio_interval`). The rules read
  the interval unrounded (`ci95_raw`).
- **Success:** kept all after the nudge, S' against N0: one-sided exact McNemar (`p_a_better`)
  and the lower bound of the one-sided 95 % Tango score interval for the paired difference
  S' - N0 (F2's `tango_bound`), unrounded.
- **No harm** (W17's S3, `handoff_pairs.harm`, on the checks after the nudge): S's repository
  tests pass in no more than floor(0.125 x pairs) fewer pairs than N0's (6 of 48); S's sessions
  2 (the nudge included) sent back by a rule other than the scene's C in at most 5 % of the pairs.

**Verdict, in this order** (the final scoreboard's rule 2.4, `docs/results/2026-10-13-final`, made
exact as W17 made it, `handoff_pairs.scoreboard`):
1. "**sin veredicto**" with fewer than 40 pairs run;
2. "**sin margen**" when N0 failed kept all **after session 2, before its nudge**, in fewer than
   5 % of the pairs (at most 2 of 48);
3. "**gana (coste)**" when the cost ratio's upper bound is **below 1.00**, Tango's lower bound is
   **above -12.5 points** and there is no harm;
4. "**gana (éxito)**" when McNemar's **p < 0.05**, the cost ratio's upper bound is **at most 1.10**
   and there is no harm;
5. "**no gana**" otherwise.

A "gana" is per model (Sonnet 5.5) and reads: "with these scenes, S' reaches step 2 done without
costing more than (or, for éxito, at no more than 1.10x and with more success than) clean Claude
Code that a person tells to go on once". It is not "S' is cheaper than Claude Code".

**Sealed secondaries (they do not change the verdict):**
- **W17's reading without the nudge**, replicating W17 on new data: `handoff_pairs.analyse` (W17's
  analysis, its seed 20261017) on the rows as they stood after session 2 (`handoff_ew.at_s2`: kept
  all after session 2, the cost of sessions 1 and 2 plus the arm's Jev), with W17's Sonnet verdict
  (S1 McNemar, S2 upper bound <= 1.10, S3 no harm) and its scoreboard.
- **The strata**, named and bare, each with its own cost ratio (this lot's seed), McNemar on kept
  all after the nudge, kept all before and after, and its nudges.
- **The nudge per arm** (and per stratum): how many arms were nudged, how many of those kept all
  after it, the rate.
- **The cost interval with scenes resampled** (`handoff_ew.by_scene`): the pairs of one scene are
  not independent, so the 12 scenes are drawn with replacement, each bringing all its pairs, and
  the median of their ratios is taken (10,000 draws, this lot's seed). Reported beside the
  primary interval; it does not decide.
- **Pairs lost to a nudge NOT RUN** (`handoff_ew.lost_to_nudge`): how many pairs, by arm, left the
  primary reading because a nudge was cut (not S' failing to run as S', which stops the run), and
  a sensitivity reading that keeps them, the cut arm counted as failed (kept all false) at its
  recorded cost (the charge included), with its verdict by the same rule. It does not decide.
- **W17's reading counts the arm's whole Jev and the nudge's send-backs**: its cost is sessions 1
  and 2 plus the arm's Jev (the nudge's decisions included; cents), and its no-harm send-backs
  count those of the nudge, which continues session 2.
- A pair whose N0 cost is zero would be left out of every ratio; it is counted (`n0_zero_cost`). A
  run N0 arm always has a reported or charged cost, so it should be 0.

## Power

Simulated, not a result (`power_normal.py` and `sizing.py`, kept with the proposal, not tracked):
the paired log ratio drawn iid Normal(log of the true median, sd), the interval the rule's
percentile bootstrap of the median, 300 simulated lots of 1,000 draws each (the rule itself uses
10,000). **The sd under R3 is not known.** 0.175 is W17's Sonnet spread of the paired log cost
ratio without the nudge (F2's: 0.171); with a nudge in some N0 arms and not in others the spread
is likely larger, so 0.22 and 0.25 are given too.

| true median | P(upper < 1.00), sd 0.175 | sd 0.22 | sd 0.25 | P(upper <= 1.10), sd 0.175 | sd 0.22 | sd 0.25 |
|---|---|---|---|---|---|---|
| 0.85 | 1.00 | 0.98 | 0.95 | 1.00 | 1.00 | 1.00 |
| 0.90 | 0.91 | 0.79 | 0.69 | 1.00 | 1.00 | 0.99 |
| 0.95 | 0.41 | 0.28 | 0.25 | 1.00 | 0.96 | 0.90 |
| 1.00 | 0.05 | 0.05 | 0.05 | 0.88 | 0.71 | 0.60 |
| 1.05 | 0.00 | 0.00 | 0.00 | 0.33 | 0.25 | 0.20 |

(48 pairs. With 40, the verdict's minimum, at sd 0.175: 0.86 at 0.90, 0.37 at 0.95.)

- The proposal's other column, residuals of R3's ratios imputed on W17's data (sd 0.107), **is
  not a power calculation**: the nudge's cost was invented there (always finishing, at a fixed
  share of a session 2), which takes out the very spread the nudge adds. It is not used.
- **"gana (coste)"** needs the upper bound below 1.00: likely (0.69 to 0.91 by the sd) if the true
  median is 0.90, a coin toss or less at 0.95, and about 0.05 at 1.00 (the rule's own error).
- **"gana (éxito)"** needs the upper bound at 1.10 or below (0.60 to 0.88 at a true 1.00), and
  McNemar needs N0 still failing after its nudge in at least 5 pairs where S' kept all (5 to 0
  gives p = 0.031).
- **The owner chose 48 pairs.**

**Sizing, post hoc, on data already seen (W17's Sonnet rows; NOT a result).** With no session 3
in W17, a nudge was imputed as if it always finished: at the cost of S's own session 2 in the
same pair, R3's ratio is 0.771 [0.760, 0.799]; at N0's median session 2 when it finished, 0.796
[0.738, 0.832]; at half of S's session 2 (a resume with a warm cache), 0.936 [0.898, 0.957]. These
numbers sized the lot; the rule was chosen for the reasons under "Question", and the verdict reads
only this lot's data. What they cannot see: whether "Yes, go ahead." finishes step 2. On the bare
line N0 often asks "what should I continue?", and a blind nudge may not help there: then N0⁺
fails more and costs less, and S' would win on success rather than on cost.

## Reported, not deciding

Per arm `task`, `fact`, `decision`, `intact`, tests, before and after the nudge; the nudges' own
cost (median), how it was read (`cost_source`), and the SessionStart sources S's memory hook
answered in S's nudges; calls (sessions and nudges) stopped by their own cap, per arm; S's session
1 over N0's session 1 (the install's own overhead); cost medians and tokens per arm; session 2's
wall time; what S' gave (`hook-log.jsonl`); S's memory hook answering the SessionStarts; Claude
Code's own auto memory after session 1 per arm; Jev decisions, failures and dollars; subagent
calls; arms that crossed midnight; the harness files and folders the agent's tool calls named
(`handoff_call.TOUCH`, the nudge's calls included); sessions charged for reporting no cost; NOT
RUN rows and their reasons. No pooling with W17 or across models. The metric is not changed after
the data.

## NOT RUN (a row with `cut`, never retried) and stops

As W17 ("NOT RUN" and stops), plus the nudge's own cuts above:
- a session that timed out, ended without a result, or whose `init` shows another model or Claude
  Code; a session stopped by its own `--max-budget-usd` counts as run, with its checks as found;
- **S' did not run as S'** (`carry_s.session_breaks` with no server, `pair_breaks`) in a session or
  in its nudge (above): the arm is cut and the run stops (exit 4);
- an exception in the runner: the arm is NOT RUN, its spend counted, the night goes on;
- **usage limit (429, weekly limit), in any call, the nudge included: a pause, never a result.** No
  row, the arm's folders kept aside, `LIMIT.flag` in the root, the night stops (exit 3); after the
  flag is removed, a relaunch runs that arm again whole. The first 429 is told to the other
  sessions (the weekly limit is shared by the account);
- crash or reboot: the arm's spend counted (`handoff.lost_cost`: its streams', the nudge's
  included, at its reported running total, so session 2 counts twice there: on the safe side;
  a stream with no reported cost at 0.69 USD), its folders kept aside, it runs again whole, at
  most twice;
- three arms in a row with a call that ended without a result stop the run (exit 7);
- a `STOP` file in the root or the run's folder stops before the next arm (exit 6);
- **midnight:** a pair does not start when its expected time (2 arms x 300 s x 1.5 + 120 s: 17
  minutes) would reach midnight, nor an arm; the driver waits and goes on after midnight;
- **quiet hours:** no arm starts whose expected time would reach 02:00-08:00 (Windows Update
  restarts this machine then; exit 8, a relaunch after 08:00 resumes), unless Windows Update is
  paused at least 24 h past the check and no restart is pending (W17 Amendment 1's lift, the same
  code: `winupdate.quiet_lifted`, `handoff.restart_pending`; each lift written to the log).

## Caps, in code

- **Per call** (session 1, session 2 and the nudge): `--max-budget-usd` **0.25 USD**
  (`RUNS["ew-sonnet"]["call_caps"]`). W17 used 0.50; lowered in the first draft so that a pair's
  reserve for three calls let 48 pairs fit 18 USD, and kept at 0.25 under the owner's 22 USD:
  with it the run fits all 48 pairs even with cold-cache nudges (above), which 0.50 (a pair's
  reserve 5.79 USD, no pair past 16.21) would not guarantee. W17's dearest Sonnet session cost 0.118
  (2.1x below the cap); its median session 2 0.04 to 0.06. Whether Claude Code checks a resumed
  call's cap against the session's running total (session 2 plus the nudge) is not known; if it
  does, a nudge has 0.25 less session 2's cost (about 0.21 after an N0 session 2 that asked).
  Calls stopped by their cap are reported per arm.
- **One worst turn per call**, since Claude Code checks the cap between turns (and a resumed call
  reloads its context): F2's `worst_turn`, **0.44 USD** on Sonnet 5.5 (200,000 cached tokens read,
  50,000 written, 20,000 out, at Claude Code's rates). A call costs at most **0.69 USD**.
- **A call that reported no cost** (a session or a nudge with no `result` event: a timeout, a
  crash, a killed process) is charged its cap plus one worst turn, **0.69 USD**, in its row and in
  the ledger; so is each such stream of an interrupted arm.
- **Per arm: three calls** (`handoff.calls_of`: two sessions and a possible nudge), reserved
  whether or not the nudge comes: 3 x 0.69 = **2.07 USD** for N0, plus 3 x 0.05 USD of Jev for S'
  (**2.22 USD**).
- **Per pair, before it starts** (no orphan arm): what the run spent (calls' own costs or their
  charge, Jev, Jev's preflight, interrupted arms) plus **4.29 USD** must stay within **22.00 USD**,
  or the run stops (exit 2). **ew-sonnet starts no pair once it has spent 17.71 USD**, above the
  expected 12.5-13.7 and the cold-cache 15.9-17.2. A run stopped by its cap is analysed over the
  pairs it ran; the interleaved order makes those named and bare alike.
- **Per lot:** the lot is this one run; its cap is the run's, 22.00 USD (`handoff.EW_CAP`, which
  sets both `RUNS["ew-sonnet"]["cap"]` and `LOTS["ew"]["night_cap"]`; tested).
- **Jev:** 0.50 USD for the run through `CappedDecider`; the runner reserves 0.05 USD of Jev per S'
  call, so in the worst case Jev could pass the run's cap by at most 0.35 USD: **22.35 USD at most
  in all**.
- Every cap is counted in Claude Code's own `total_cost_usd` (its price table, plus Jev's own
  costs); at the owner's rates (`benchmarks/meter.py`) the same tokens can come to about 1.5 to 2
  times as much. The subscription pays: the lot counts against the account's weekly limit.

## Running it

- **Keys.** The lead writes `C:\sp-runs\mem-ew\keys-env.cmd` (untracked, outside the repository,
  only `set SANCHOPANZA_KEYS_ENV=<path>`); the launcher refuses (exit 1) without it and never reads
  the file it names. The token reaches only the `claude` processes, the key only S's hooks
  (`C:\sp-runs\w20\r1\typesafe.key`, deleted at the start and end of the run); both are scrubbed
  from each arm's files and redacted from every row.
- **Python.** `C:\sp-runs\mem-ew\python-env.cmd` (untracked, only
  `set PY=<main checkout>\.venv\Scripts\python.exe`); without it the launcher refuses (exit 1).
- **Jev.** `python -m sanchopanza jev-preflight` (exit 0) before launching; the runner makes one
  real Jev decision with the run's key before the run and refuses without an answer.
- **The checkout.** A detached worktree at the sealing commit, at a path that names nothing of the
  lot (e.g. `..\sp-w20`). `handoff_night.py` refuses (exit 11) unless the files match the seal,
  HEAD is the commit that last wrote `prereg.sha256`, `git status --porcelain` is empty, and (this
  lot, `handoff_seal.SEAL_ALONE`) the sealing commit changes only `prereg.manifest.json` and
  `prereg.sha256` (`git diff --name-only HEAD~1 HEAD`).
- **The root.** `handoff.py --run ew-sonnet` refuses (exit 11) a live `--out` other than
  `C:\sp-runs\mem-ew\ew-sonnet`, where the run's ledger and cap live (a dry run may build anywhere).
- **Launch** by WMI with CreateFlags 512 (header of `ew-night-run.cmd`), **by day, between 08:00
  and 20:30** (about 2.5 hours; neither midnight nor 02:00 is reached from the start). Tell the
  other sessions (PID, time, cap). Watch the log's lines and the process with two monitors; kill
  only by verified PID.
- **Reboot.** Nothing relaunches the night; start the same launcher again the same way.

## Commands

    rem free: checks, dry run, seal (from the worktree, PYTHONPATH=<worktree>\src)
    "%PY%" benchmarks\memory_carry\handoff.py --preflight --lot ew --out C:\sp-runs\mem-ew
    ew-night-run.cmd dry
    "%PY%" benchmarks\memory_carry\handoff.py --seal --lot ew
    rem paid: ew-night-run.cmd run, by WMI from a detached worktree at the sealing commit
    rem analysis (free; the night also writes C:\sp-runs\mem-ew\ew-sonnet-table.json)
    "%PY%" benchmarks\memory_carry\handoff_ew.py C:\sp-runs\mem-ew\ew-sonnet

## Seal

`handoff.py --seal --lot ew` writes `prereg.manifest.json` (sha256, LF bytes, of this file and of
`handoff_seal.SEALED_FIXED_EW`: the launcher `ew-night-run.cmd`, `pyproject.toml`,
`benchmarks/meter.py`, the runner and its modules (`handoff_nudge.py` and `handoff_ew.py`
included), `winupdate.py`, their tests (`tests/test_memory_carry_ew.py`, W17's, F2's,
`test_winupdate.py`, `test_durable.py`, `test_launchers.py`), plus every
`benchmarks/memory_carry/*.py` and **every file** under `src/sanchopanza/`) and `prereg.sha256`
(the sha256 of the manifest's lines). A different seal is refused. The instrument is the commit
that adds this file; the seal is its only child, committed alone (the code refuses a sealing commit that changes
anything else); an independent review of this
prereg against the code (`revisor-prereg`) goes before the seal.

## Deviations from W17

- **The nudge (R3)**: a third call, once, when `task` fails after session 2, in both arms; the
  primary success is kept all after it, and the cost ratio counts it.
- **The headroom is measured before the nudge** ("sin margen" reads N0's kept all after session 2),
  not on the primary success: the saving this lot can show is exactly the nudge, so N0's room is
  what it left undone before being told to go on.
- **Call caps 0.25 USD** instead of 0.50 (all three calls), a reserve of three calls per arm, and a
  run cap of 22 USD (the owner's).
- **The pairs' order is interleaved** (named, bare, scene by scene), not repetition by
  repetition; which arm goes first in each pair is W17's.
- **Session 2's checks run on a copy** of the repository before the nudge; the final checks run in
  the agent's tree, as W17's.
- **This lot's own bootstrap seed** (20261021) for the primary; W17's (20261017) for the W17
  reading.
- **No Opus lot.** On Opus N0 already kept all in 31 of 36 W17 pairs: little to nudge, and the
  imputed ratio sat near 0.97, where 36 pairs show a "gana (coste)" with low probability; Opus
  keeps W17's "not determined".
- **`src/` at main 4c143e1** (installed files identical to W17's; see "Arms").
- In the runner: `carry_s.session_breaks` takes `start=False` for the nudge (the resumed session's
  start is recorded, not required); `handoff_step` takes the prompt, the stream's tag and the run's
  call cap (F2's H turn is unchanged); `calls_of` and `reserve_of` count the nudge.

## What this lot does not say

- The person's time and the round trip's latency (wall time is reported, not deciding); a person
  who answers with information (the nudge is blind); more than one nudge.
- Anything about Opus 5.5, other tasks, or a Claude Code other than 2.1.287. If a later Claude Code
  stops less often to ask, or its own auto memory always keeps the plan (as on Opus), the saving
  goes away.
- **The scenes repeat F2's and W17's**: the data are new, but the scenes were chosen knowing that
  N0 stops in them. Generalising needs new scenes.
- Whether "Yes, go ahead." makes N0 finish: that is what the lot measures, not an assumption.
