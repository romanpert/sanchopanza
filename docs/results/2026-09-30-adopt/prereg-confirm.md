# Adoption study, confirmation: pre-registration

Drafted 2026-09-30, finished 2026-10-01, written before any held-out session. Binding once
`prereg-confirm.sha256` exists and still matches the files its manifest names
(`confirm.seal_holds`): this document, `benchmarks/adopt/*.py` (the runner, grading, verdicts,
validation, the extra spares), `benchmarks/adopt/*.json` (the sealed selections, the extra
spares and the validation summary that says which chains take part), the two task files and
`benchmarks/candor/seal.py` (the hashing the seal relies on).
The arms' code is pinned by the frozen install of eebdfa6 (`ADOPT_SANCHO`; every row records
its path and commit). After sealing, a change is an amendment written here, dated, before any
verdict is read.

The owner decided on 2026-09-30 that the
memory arms (`Sm`, `Sf`) wait for memory v3 (v2 measured on 319 real Claude Code sessions of
SWE-chat, 2.6 % precision). v4.1 superseded v3 on held-out real sessions (precision 0.753
against 0.631), and **on 2026-10-01 the owner approved running A on v4.1**: the frozen,
non-editable install of eebdfa6 (`freeze.py`, `ADOPT_SANCHO`), the same one phase B2 runs.
Memory v5, merged into main later that day, is not used (owner, 2026-10-01).

## The question

Is Claude Code with sanchopanza better and cheaper than Claude Code alone on real work, measured
fairly? Two hypotheses (the owner's, 2026-09-30), and the four criteria of the study:

- **H-session.** In ONE session, `sanchopanza install --memory --context-budget 100000` (arm
  `Sm`) costs less than Claude Code alone (`N`) and resolves as much.
- **H-new-session.** A NEW session per request with memory (`Sf`) resolves as much as one
  without (`Nf`) and explores less. It may cost more than staying in one session; what it buys
  is a better-informed start.
- H1 success non-inferior, H2 paired median cost ratio below 1, H3 false blocks bounded and read
  one by one, H4 adoption measured (below).

`Sm` is not the default install: memory is off by default and the default budget is 160k. A
result for `Sm` is a result for that configuration, and would need the default changed before it
could be said of `sanchopanza install` as it ships. The singles (below) test the default install
(`S`).

## Tasks (sealed before this draft)

- Chains: `tasks.md` (sealed; `tasks.sha256`), held out: pygments-2, starlette-2, pydantic-1,
  pydantic-2, conan-1, conan-2, dvc-1, astroid-1.
- Related chains: `tasks-related.md` (sealed at 8b9f1c8), held out: starlette-rel-2,
  pydantic-rel-1, conan-rel-1, conan-rel-2, dvc-rel-1.
- Singles: `singles-selected.json`, the 26 held-out SWE-bench Verified instances (10 easy, 10
  medium, 6 hard), graded by the official harness.
- Combined chains (phases B and C): two chains of one repository asked in one session, in one
  working copy, graded per chain (`benchmarks/adopt/combined.py`, whose docstring holds the
  combining rule). The held-out pairs follow a rule written before any held-out session: per
  repository in `chains.PLAN` order, the first pair (an independent chain of `tasks.md`, a
  related chain of `tasks-related.md`, each in sealed order) whose two chains validate on their
  own and that fits in one image with no swap (no overlapping hunk, no FAIL_TO_PASS test in
  common) and validates combined. By the free check of 2026-09-30 that is
  `pydantic__pydantic-long-1r1` (pydantic-1 + pydantic-rel-1) and `conan-io__conan-long-1r2`
  (conan-1 + conan-rel-2). Not used, and why: starlette-2 + rel-2 (pr_2351 overlaps pr_2381),
  conan-1 + rel-1 (pr_15368 overlaps pr_14078), dvc-1 + rel-1 (pr_10303 overlaps pr_9250);
  pygments and astroid have no related chain. If a pair does not validate, the rule takes that
  repository's next pair (pydantic-2 + rel-1; conan-2 + rel-1, then conan-2 + rel-2).
  **pydantic, validated 2026-09-30**: pydantic-1, pydantic-2 and pydantic-rel-1 valid on their
  own, no swap; `pydantic__pydantic-long-1r1` INVALID combined (with the ten bugs in, one of pr_5869's
  two FAIL_TO_PASS already passes: a bug of pydantic-1 hides it), so the rule takes
  `pydantic__pydantic-long-2r1` (pydantic-2 + pydantic-rel-1), valid, 10 of 10.
  **conan, 2026-09-30: all four chains INVALID** by the sealed procedure (conan-1: 3 of 5 bugs;
  conan-2: 3 of 5, and 3 of 5 again after its swaps; conan-rel-1: 5 of 5; conan-rel-2: 3 of 5).
  Checked by hand, not a harness fault: with pr_16289 alone undone its test still fails on
  `'LocalAPI' object has no attribute 'editable_packages'`, another bug of the chain breaking a
  path every `TestClient` test goes through. conan's bugs hide each other, so no conan chain
  and no conan pair is used. (Found on the way: a swap that succeeded for one bad bug and not
  the next left the stored bugs out of step with the bake's records; `validate.py` now swaps on
  a copy, and conan-2 and conan-rel-1 were validated again with it, same verdict.)

**Amendment of 2026-10-01: extra spares (approved by the owner, written before any held-out
session and before any validation with them).** After replacing culprits instead of victims
(dev log, "After phase B"), conan-1, conan-2, conan-rel-1, conan-rel-2, dvc-1 and dvc-rel-1
were still invalid for want of spares: theirs hide each other too. `benchmarks/adopt/extra.py`
draws up to 9 more per chain without changing any draw already made: it replays `chains.select`
and `related.select` with their seeds, checks they give exactly the sealed spares, and takes the
next bugs of the same shuffled lists (independent chains: after the last chain's spares, 9 per
chain in chain order; related chains: the next pool bugs `grow` would take, with the chain's
spares counted as part of it), skipping every bug used anywhere. The ids are in
`benchmarks/adopt/extra-spares.json`; conan-rel-2 gets none (no unused bug shares a code file
with it: meson's toolchain), so it stays invalid. `validate.py` tries them after the drawn
spares, by the same rules (culprits, swaps on a copy, at most four rounds). Every chain then
validates again, and only chains that validate take part.

**Validation, final (2026-10-01, before the seal; `benchmarks/adopt/chains-validated-summary.json`,
sealed below, is what `confirm.held` reads).** Held-out chains that take part in A:
pygments-2, starlette-2, pydantic-1, pydantic-2, conan-1, conan-2, astroid-1 (7 of the 8 of
`tasks.md`) and starlette-rel-2, pydantic-rel-1, dvc-rel-1 (3 of the 5 of `tasks-related.md`):
**10 chains, 50 bugs; 3 related chains, 15 bugs.** Not taking part: dvc-1 (after four rounds one
of pr_8690's 13 FAIL_TO_PASS still fails when it alone is fixed), conan-rel-1 (four rounds, four
bugs still hidden), conan-rel-2 (no spare left; see the amendment). Found and fixed on the way,
none changing a chain already run: the culprit search asked only one of the two checks (a bug
whose tests pass with every bug in got bisection's leftmost bug as culprit; pydantic-long40-1),
a fifth swap was saved with no check after it, and a patch that did not apply was read as an
answer (dev log, "Phase B2"). After the seal images are rebuilt with `validate.py --bake`, which
neither checks nor saves; `validate.py <chain>` is not run again (it refuses once
the seal holds), and `--bake` checks after baking that every FAIL_TO_PASS still fails.
**astroid-1 was validated on 2026-09-30, before the culprit search asked both checks**: its one
swap replaced pr_2665, the chain's first bug, which is the symptom of the leftmost blame. The
chain is valid by the check as it stands (every bug fails with all in and passes fixed alone),
so it takes part; the sealed code would not necessarily pick the same replacement. Said here
rather than validated again.

Every held-out chain is validated in Docker (`validate.py`, then `combined.py validate held`)
before sealing, one repository at a time. Validation runs no session. Harness fixes it needed,
none of which changes a chain already run: the bake commits with `--no-verify` (pydantic's image
carries a pre-commit hook), pytest runs in `/testbed/.venv` where an image has one (pydantic's
test dependencies live there), and grading passes `-p no:pretty` (pytest-pretty replaces the
lines the grader reads). Results: above.

## Phases, models, arms

| phase | tasks | arms | model | approved (list price) |
|---|---|---|---|---|
| B, development | `encode__starlette-long-1r1`: starlette-1, then starlette-rel-1 with pr_2041 swapped for its spare pr_2443 by the combining rule (pr_2041 overlaps pr_2141 and shares its six FAIL_TO_PASS); validated, 10 of 10 | N, Sm | Sonnet 5.5 (`claude-sonnet-5-5`, 1M window) | 25-30 USD |
| C, confirmation stratum | the two combined held-out chains above | N, Sm | Sonnet 5.5 | 55-60 USD |
| A, confirmation | the 10 held-out chains that validated (7 of `tasks.md`, 3 related): N, Sm. The 3 related: also Nf, Sf. 26 singles: N, S | as listed | Haiku 4.5 (`claude-haiku-4-5-20251001`) | ~105 USD; estimated ~73 (chains ~36, related Nf/Sf ~12, singles ~25, from development's Haiku costs) |

One repetition per task and arm. Claude Code 2.1.285, `claude -p` on the subscription, the
coordinating session's environment stripped (`run.child_env`); Jev `jev-1.13.0` for the decider.
Arms as in `run.ARM_SPECS`; the arms of one task run at the same time, each in its own working
copy exported from the task's image. Prompts, tools (defaults minus WebFetch and WebSearch),
budgets and the `runtests` command are the same in every arm. A task and arm run with another
model than its phase's counts as missing (`confirm.PHASE_MODEL`).

**Rule to run C, fixed before B runs.** B is development and counts toward no verdict. C runs
only if in B `Sm` costs at most 0.90 of `N` over the requests both arms ran (Claude calls plus
Jev) and resolves at least as many bugs as `N` minus one (of ten). Otherwise C is not run, and
that is reported.

**B ran on 2026-09-30 (dev log, "Phase B"): cost ratio 0.958, resolved 9 and 9 of 10. The rule
is not met: C is not run.** Both arms ended at ~80k tokens of context without a compaction, so
B could not reach the long sessions it was meant to probe. Phase C and its caps stay in this
document as written, and are not run.

**B2 ran on 2026-10-01** (development, owner's approval, dev log "Phase B2"):
`pydantic__pydantic-long40-1`, 40 bugs in one session, Sonnet 5.5, N / S / Sm on eebdfa6. N
27/40 at 8.74 USD (peak context 263k, no compaction); S 30/40 at 0.837 of N (compacted at 160k);
Sm 0/40 strictly at 0.729 of N (one wrong exception class broke a PASS_TO_PASS test that all 40
bugs share; 26 by FAIL_TO_PASS). On Sonnet memory recalled nothing (it edits through Bash; Haiku
edits with Edit/Write in 95-100 % of requests, so A is unaffected). Counts toward no verdict.
**A keeps its design**: B2 is one chain on another model; nothing in it is a reason to change
A's arms, and its one lesson is taken into the measures (the FAIL_TO_PASS count, reported).

## Measures

- **Ran, complete.** A request ran when it was not NOT RUN, was not cut by the timeout and
  reported a result. An arm is complete when every request of its task ran.
- **Resolved:** a bug is resolved when all of its FAIL_TO_PASS and PASS_TO_PASS* pass with the
  arm's final diff (`run.grade_chain`); a request that did not run leaves its bug unresolved. A
  combined chain is graded the same way and split per chain by `combined.py report`. Singles:
  the official harness. Reported beside it, deciding nothing: bugs whose FAIL_TO_PASS all pass
  (`f2p_resolved`, `treat_f2p` / `control_f2p`), since a PASS_TO_PASS test every bug of a chain
  shares turns one regression into the whole chain (phase B2).
- **Cost:** per task and arm, the list-price cost of every Claude Code call (`run.call_cost`:
  the difference for a resumed session; a call cut by the timeout is charged its cap, once) plus
  Jev's journal cost.
- **Exploration** (H-new-session): per request that ran, the tool calls of the main thread (a
  subagent's calls, which carry `parent_tool_use_id`, do not count) before its first `Edit`,
  `Write`, `MultiEdit` or `NotebookEdit` (all of them if it never edits).
- **False block:** a PreToolUse denial by sanchopanza's shell guard in an S arm (subagents'
  commands included), read one by one and judged false when the command was legitimate for the
  task; verdicts go to `false-blocks.jsonl` beside this file. Every block is listed with its
  verdict. (candor is not part of `Sm`, `Sf` or `S`.)
- **Adoption:** calls to `find_in_repo`, to the skill, prompts where memory injected records,
  and records injected.

## Hypotheses and verdicts (`benchmarks/adopt/confirm.py`)

Bootstrap: 10,000 paired resamples over tasks (over requests for exploration), seed 20261002,
percentile 95 % intervals.

- **H1 (non-inferior success).** The point difference decides, its paired interval is
  reported. Only chains that validated take part (`confirm.held`). On the chains, bugs resolved
  by `Sm` >= bugs resolved by `N` minus 5 % of their bugs, rounded, at least one
  (`confirm.margin`: 2 of the 50 bugs of the 10 chains, 1 of the 15 of the 3 related); on the related chains, `Sf` >= `Nf` minus the same share
  of theirs. On the singles, `S` >= `N` minus 2 (of
  26). A task missing an arm leaves that H1 undecided, and says which.
- **H2 (cheaper).** Over the chains where both arms are complete, the median of
  cost(`Sm`)/cost(`N`) is below 1 and its 95 % interval lies below 1: confirmed. Median below 1
  and interval across 1: the direction only, not confirmed. Pairs with an incomplete arm are
  listed apart with their cost over the requests both arms ran. Singles: the same ratio for
  `S`/`N`, reported with no verdict.
- **H-new-session, exploration.** Over requests 2-5 of the related chains where both arms are
  complete (up to 12 request pairs), the median of (exploration(`Sf`) + 1) /
  (exploration(`Nf`) + 1) is below 1 and its interval lies below 1. Cost of `Sf` and `Nf`
  reported, no verdict.
- **H3 (false blocks).** False blocks at most 1 per 100 shell commands of the S arms, and no bug
  resolved by the control arm and not by the S arm with a false block in its request. Undecided
  while any block has no verdict.
- **H4 (adoption).** Reported, no verdict.
- **H-session** holds when H1 and H2 hold on the chains. **H-new-session** holds when H1 holds
  on the related chains and the exploration hypothesis holds.

Phase C (two tasks), per pair: cost ratio `Sm`/`N` over the requests both arms ran, and the
resolved difference (per chain of the pair from `combined.py report`). The lever is shown when
both pairs cost at most 0.90 and neither resolves more than one bug fewer. With two tasks this
is a probe of the lever at 300k-400k context, not a confirmation.

Power, said before: 10 chains and 12 request pairs (requests 2-5 of 3 related chains) give wide intervals. A true 15 % saving with
the spread seen in development (per-chain ratios S/N 0.77-1.02, n = 3; none yet for `Sm`) may
well come out "direction only". That is how it will be reported.

## Caps, in code (list price)

| phase | per call (`--call-cap`) | per chain and arm (`--chain-cap`) | batch (`--ceiling`) |
|---|---|---|---|
| B | 4.50 | 15.00 | spent under `runs/` at the start + 30 |
| C | 4.50 | 15.00 | spent at the start + 60 |
| A chains (N, Sm; Nf, Sf on the related), every run | 1.50 | 6.00 | **133.51** (spent under `runs/` at sealing, 58.51, + 75) |
| A singles, every run | 1.50 | | **169.36** (58.51 under `runs/` + 5.85 under `singles/` at sealing + 105) |

`--ceiling` counts everything spent before, development included. The two numbers for A are
absolute and the same for every run of A, however many runs it takes: the chains' ledger counts
`runs/` only, the singles' counts `runs/` and `singles/`, so whatever A's chains spend leaves the
singles the rest of 105 USD, and A as a whole cannot pass 105 (anything another session spends
under `runs/` meanwhile only makes it stricter). For held-out tasks `run.py` and `singles_run.py`
refuse any other model than Haiku 4.5, a per-call cap above 1.50 or a chain cap above 6.00, a
sanchopanza other than the frozen eebdfa6, a Claude Code other than 2.1.285 (and the child
sessions run with `DISABLE_AUTOUPDATER=1`), and a chain whose cache entry is not the one the
sealed summary hashed (`sha256`); grading a held-out chain needs the seal and records it.
An arm that started and left no row (a crash) is not run again: it is listed as missing. An API
or usage-limit error reported as a result is NOT RUN (error result) and stops that arm; a call
stopped by its own cap (`error_max_budget_usd`) ran. A singles grade with no report from the
harness is missing, not a loss.
Held-out and combined tasks go **all or nothing**: before a task starts, the chain cap of every
one of its arms (singles: both arms' call caps) is held against the ceiling, or the task is not
run at all; so no pair has one arm run and the other not (in development the shared ledger let
one arm take another's room). Held-out tasks refuse to run before the seal holds. Each batch is
watched live; no retries. A request stopped by its arm's chain cap is NOT RUN, its bug counts as
not resolved, and the pair goes to "listed apart" for cost.

Whatever does not hold is reported as not holding.

## Amendment 1, 2026-10-01, during phase A, before any verdict is read

Written after pygments-2, starlette-2, starlette-rel-2 and pydantic-1 ran (their per-task grades
were printed by the runner while watching it; `confirm.py A` has not been run) and before any
other held-out task; sealed again with the code it changes.

1. **A prompt too long for Windows' command line.** `run.py` passed each issue to `claude -p` as
   an argument; pydantic-2's second issue has 34,215 characters, over Windows' 32,767, and
   CreateProcess failed in both arms with an exception that ended `run.py` before either arm
   wrote its row (each had run request 1). Changed: a prompt over 16,000 characters goes through
   stdin, the same text (checked live: one Haiku call, 0.03 USD); a call that cannot be started
   is NOT RUN (harness) with the row written, as designed for a `claude -p` that never opens a
   session. No held-out issue but that one is over 4,100 characters (singles: 3,710).
2. **pydantic-2 is run again, both arms, from request 1.** The rule "an arm that left no row is
   not run again" exists so attempts are not mixed and spend is not lost. Here both arms fell at
   the same point for the harness's reason, no result of either was graded or seen, and the
   whole pair is run again; the first attempt (0.22 USD) is kept, counted in the ledger and the
   ceiling, under `runs/pydantic__pydantic-2-crashed1/`, which no verdict reads.
3. **Baking the held-out images.** `validate.py --bake` checks only the FAIL_TO_PASS nodes, and a
   parametrised test absent with the bugs in (pygments-2: `test_lexer_classes[OrgLexer]`;
   pydantic-1: a docstring example) makes pytest exit with "not found" and no results, so the
   check raised (for pydantic it raised before baking pydantic-2 and pydantic-rel-1, which were
   then baked by hand with the same `docker_env.bake` and the validated bugs). From here on images
   are baked with `docker_env.bake` and checked as validation's `check` does (the FAIL_TO_PASS and
   PASS_TO_PASS* nodes together, an absent test counting as failing); a chain whose check fails is
   not run. Results so far: starlette-2, starlette-rel-2, pydantic-1, pydantic-2, pydantic-rel-1
   OK. pygments-2 ran before this check existed; its image is baked again after A and checked the
   same way, and the result is reported with it.
