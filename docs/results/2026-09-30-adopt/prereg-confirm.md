# Adoption study, confirmation: pre-registration (DRAFT, not sealed)

Draft of 2026-09-30, written before any held-out session and before the long-session pilot (B).
It becomes binding only when `prereg-confirm.sha256` exists (sealed with
`benchmarks/candor/seal.py` together with the code it names) and still matches those files
(`confirm.seal_holds`). Until then anything here may change, and each change is said in the dev
log. After sealing, a change is an amendment written here, dated, before any verdict is read.

Points still open in this draft are marked **OPEN**.

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
  **conan, 2026-09-30**: conan-1 INVALID by the sealed procedure (pr_13364, pr_13631 and
  pr_15705: fixing the bug alone does not make its FAIL_TO_PASS pass; pr_13364's are
  functional cmake tests), with no spare that fits; it leaves phase A as an invalid chain.
  **OPEN**: the rest of conan and the other repositories.

Every held-out chain is validated in Docker (`validate.py`, then `combined.py validate held`)
before sealing, one repository at a time. Validation runs no session. Harness fixes it needed,
none of which changes a chain already run: the bake commits with `--no-verify` (pydantic's image
carries a pre-commit hook), pytest runs in `/testbed/.venv` where an image has one (pydantic's
test dependencies live there), and grading passes `-p no:pretty` (pytest-pretty replaces the
lines the grader reads). **OPEN**: validation results.

## Phases, models, arms

| phase | tasks | arms | model | approved (list price) |
|---|---|---|---|---|
| B, development | `encode__starlette-long-1r1`: starlette-1, then starlette-rel-1 with pr_2041 swapped for its spare pr_2443 by the combining rule (pr_2041 overlaps pr_2141 and shares its six FAIL_TO_PASS); validated, 10 of 10 | N, Sm | Sonnet 5.5 (`claude-sonnet-5-5`, 1M window) | 25-30 USD |
| C, confirmation stratum | the two combined held-out chains above | N, Sm | Sonnet 5.5 | 55-60 USD |
| A, confirmation | 13 held-out chains: N, Sm. 5 held-out related chains: also Nf, Sf. 26 singles: N, S | as listed | Haiku 4.5 (`claude-haiku-4-5-20251001`) | ~105 USD |

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

## Measures

- **Ran, complete.** A request ran when it was not NOT RUN, was not cut by the timeout and
  reported a result. An arm is complete when every request of its task ran.
- **Resolved:** a bug is resolved when all of its FAIL_TO_PASS and PASS_TO_PASS* pass with the
  arm's final diff (`run.grade_chain`); a request that did not run leaves its bug unresolved. A
  combined chain is graded the same way and split per chain by `combined.py report`. Singles:
  the official harness.
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
  reported. On the 13 chains, bugs resolved by `Sm` >= bugs resolved by `N` minus 3 (5 % of 65).
  On the 5 related chains, `Sf` >= `Nf` minus 1 (of 25). On the singles, `S` >= `N` minus 2 (of
  26). A task missing an arm leaves that H1 undecided, and says which.
- **H2 (cheaper).** Over the chains where both arms are complete, the median of
  cost(`Sm`)/cost(`N`) is below 1 and its 95 % interval lies below 1: confirmed. Median below 1
  and interval across 1: the direction only, not confirmed. Pairs with an incomplete arm are
  listed apart with their cost over the requests both arms ran. Singles: the same ratio for
  `S`/`N`, reported with no verdict.
- **H-new-session, exploration.** Over requests 2-5 of the related chains where both arms are
  complete (up to 20 request pairs), the median of (exploration(`Sf`) + 1) /
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

Power, said before: 13 chains and 20 request pairs give wide intervals. A true 15 % saving with
the spread seen in development (per-chain ratios S/N 0.77-1.02, n = 3; none yet for `Sm`) may
well come out "direction only". That is how it will be reported.

## Caps, in code (list price)

| phase | per call (`--call-cap`) | per chain and arm (`--chain-cap`) | batch (`--ceiling`) |
|---|---|---|---|
| B | 4.50 | 15.00 | spent under `runs/` at the start + 30 |
| C | 4.50 | 15.00 | spent at the start + 60 |
| A chains | 1.50 | 6.00 | spent at the start + 90 |
| A singles | 1.50 | | spent (chains and singles) at the start + 15 |

`--ceiling` counts everything spent before, development included, hence "spent at the start".
Held-out and combined tasks go **all or nothing**: before a task starts, the chain cap of every
one of its arms (singles: both arms' call caps) is held against the ceiling, or the task is not
run at all; so no pair has one arm run and the other not (in development the shared ledger let
one arm take another's room). Held-out tasks refuse to run before the seal holds. Each batch is
watched live; no retries. A request stopped by its arm's chain cap is NOT RUN, its bug counts as
not resolved, and the pair goes to "listed apart" for cost.

Whatever does not hold is reported as not holding.
