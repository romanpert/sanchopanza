# Adoption study, phase D: pre-registration (DRAFT, not sealed)

Drafted 2026-10-03, before any session of phase D; brought in line with the runner on 2026-10-05,
after an adversarial review of the code (0df3bdf). **Not binding yet.** It becomes binding once
`prereg.sha256` exists and still matches the files its manifest names: this document,
`benchmarks/adopt_d/*.py` (the draw, the runner `run_d.py` with `plan_d.py` and `guard_d.py`, the
verdicts `confirm_d.py`, the validation `validate_d.py`, the grading self-test `selftest_d.py`,
the power scripts `sim_h1.py` and `power.py`, and the tests), `benchmarks/adopt_d/*.json` (the
draw, the exclusion list, the validation summary), every file of `benchmarks/adopt/*.py`
(unchanged; their hashes must still equal those in
`../2026-09-30-adopt/prereg-confirm.manifest.json`) and `benchmarks/candor/seal.py`. Seal with:

    python benchmarks/candor/seal.py prereg --out docs/results/2026-10-03-adopt-d \
        --code "benchmarks/adopt_d/*.py" "benchmarks/adopt_d/*.json" \
        "benchmarks/adopt/*.py" "benchmarks/candor/seal.py"

The runner and the verdicts check the seal themselves (`run_d.seal_refusal`): the manifest must
name this document, `run_d.py`, `confirm_d.py`, `validate_d.py`, `singles-validated.json`, phase
A's five modules (`run`, `singles_run`, `docker_env`, `hook_env`, `confirm`), `seal.py`, and every
file the three globs reach at the time of the check, so a module added to `benchmarks/adopt_d/`
after sealing breaks the seal. Not sealed, on purpose:

- `run-d.cmd` and `run-validate.cmd`, the launchers. That is safe because `run_d.py` does at import
  what `run-d.cmd` sets: it puts the private Claude Code 2.1.285 first on PATH, sets
  `DISABLE_AUTOUPDATER=1`, refuses an `ADOPT_SANCHO` other than D's frozen copy and sets it; and it
  refuses to run unless `claude --version` gives 2.1.285 and the frozen copy's stamp is D's commit
  with `jev` and `mcp`. A changed launcher can change where the log goes, not what runs.
  `validate_d.py` refuses to run once the seal exists, so its launcher has nothing left to do.
- The frozen copy itself (outside the repository): identified by its stamp, as above.
- What both arms load from outside the repository: see "Threats". Hashed at the batch's start and
  checked before every pair instead.

Before sealing, these must be done and written here: the owner's call on the development probe
(below) and, if approved, the need probe's result; the validation of the drawn images; the
disjointness check run again; the absolute ceiling's base and its added amount filled in, here and
in `run_d.py` (`CEILING_BASE_USD`, `CEILING_ADDED_USD`). The frozen commit is filled in (7a39a1f,
`run_d.D_COMMIT`). After sealing, a change is an amendment written here, dated, before any verdict
is read; an amendment written after the first session was graded says so, even though no grade is
seen before the verdicts (see "Measures").

## Why a phase D

From phase A (`../2026-09-30-adopt/dev-log.md`, "Phase A, second reading" and "Exploration after
the second reading"):

- **find_in_repo was never reachable.** With Claude Code's default tools it was deferred behind
  ToolSearch (`deferred_tools_delta` names it in the transcript) and the model saw only its name.
  0 calls to ToolSearch, find or the skill in 108 S arms. So A's "find 0" measured a tool the
  agent could not see. Fixed in 1ea9302: `install` writes `"alwaysLoad": true` on the server.
- **The singles' extra cost was turns, not overhead.** S cost 1.225 of N [1.014, 1.309] in the
  second reading (1,449 turns against 1,288; cost per turn the same). The first reading's S cost
  1.084 of N. The same arm's cost moves between runs with a ln sd of 0.48.
- **Chains lack power, singles do not.** One PASS_TO_PASS regression sinks a chain: the same Sm
  arm, run twice, moves by a per-run sd of 1.74 bugs of 5. The singles are stable: S in the
  first and second reading disagree on 1 of 26.

So phase D tests the default install with find visible, on singles only, with repetitions.

## The question

With find_in_repo loaded up front, does Claude Code with sanchopanza's default install resolve
as many SWE-bench Verified issues as Claude Code alone, at no more than 10 % more cost, and does
the agent use find?

## Development probe result (to fill in before sealing)

A development probe (`benchmarks/adopt_dev/`, prepared separately, development instances only,
none of the 26 below) must first show that, on Haiku 4.5 with Claude Code 2.1.285 and the frozen
copy phase D will run:

1. `mcp__sanchopanza__find_in_repo` is in the init line's tools of every S session and in no
   `deferred_tools_delta` of its transcript; and
2. Haiku calls find_in_repo in at least one session.

If (1) fails, phase D is not sealed: the install is broken again. If (2) fails (the tool is
visible and never called), phase D is not sealed as written: H4 would be known in advance, and H2
would measure the hooks again. What to do then is the owner's call.

> **Result** (filled 2026-10-05; details in `../2026-09-30-adopt/dev-log.md`, "Development probe"
> and "Development probe 2"). Two probes, Haiku 4.5, Claude Code 2.1.285, 34 sessions, 15.97 USD
> list price:
>
> - **Probe 1**, frozen copy of 1ea9302 (alwaysLoad, old description), 14 sessions, 5.68 USD.
> - **Probe 2**, frozen copy of 4ee2901 (new description, parameter descriptions, `kind` enum,
>   server instructions, plus the PostToolUse nudge), behaviour set of 7 + 3 controls, 20
>   sessions, 10.29 USD.
> - **(1) holds:** `mcp__sanchopanza__find_in_repo` is in the init line's tools of 20 of 20 S
>   sessions, with its schema in turn 1, never deferred; 0 ToolSearch calls (counted again from
>   the streams on 2026-10-05).
> - **(2) holds, barely:** find was called in 1 of 20 S sessions (django-13343, probe 2, tool
>   call 16, after three empty greps; its top two results were the two gold hunks, but the gold
>   file had been Read at call 4). The call came 14 calls after the nudge, in the late-fallback
>   pattern seen in find-e2e, so it is not credited to the nudge.
> - **What D runs is neither probe's copy.** The nudge is opt-in since 16cd46c and D runs the
>   default install, without it. D's copy (7a39a1f, below) writes the same `.mcp.json` and
>   `.claude/settings.json` as 1ea9302 and serves find with probe 2's description and
>   instructions; that it does so is checked for free by capturing Claude Code's first request
>   (`~/.cache/sanchopanza/adopt/d-capture/7a39a1f/`), not by a paid probe.
>
> **The owner's call that (2) asks for** (find visible and almost never used: H4 is nearly known in
> advance, and H2 mostly measures the hooks again): _(to fill in: Roman's answer to question 1)_

**A third probe, prepared, not run** (`benchmarks/adopt_dev/probe_need.py`, e51f7ca). Arm S
only, on D's exact frozen copy of 7a39a1f (the default install: find always loaded, no nudge, the
delegation fix), one session on each of the 10 need-ranked development instances
(`benchmarks/find_need/need-table.json`: Verified singles where a recorded control session took 5
or more searches to the gold file, or never reached it; none of them is drawn or a spare below,
checked by `draw.py check`), Haiku 4.5, Claude Code 2.1.285, 1.50 per call, **cap 12.00 USD**
for the probe. Its rows count in D's ledger (`dev-need/`, see "Caps"). It runs only if the owner
approves it; if approved, gate (2) is read from it, since it is the only probe on the copy D
runs, and it runs where find is needed.

> **Need probe result:** _(to fill in, or "not run" with the owner's call above: sessions, find
> visible in N of N, sessions calling find, ToolSearch calls, cost)_

Nothing is sealed while either placeholder above is unfilled.

## Tasks: 26 new held-out singles (drawn 2026-10-03, before this draft was finished)

`benchmarks/adopt_d/draw.py`, written before the draw; its output is `benchmarks/adopt_d/singles-d.json`.

- **Data.** SWE-bench Verified, `princeton-nlp/SWE-bench_Verified` at revision
  `c104f840cc67f8b6eec6f759ebc8b2693d585d4a` (the find line's `verified.parquet`, sha256
  `a45b1fe4...6dcd`), the file phase A's `singles.py` drew from. Images and problem statements
  come from `singles_run.rows()`, as in phase A; every drawn id is checked to be there.
- **Excluded: every instance used anywhere before** (`draw.py scan`, `used-ids.json`, sha256
  `b2aca620...41a6`): 300 of the 500. (After the draw, `used-ids.json` was rewritten with paths
  relative to the repository or `~` and at most five places per id, so that no local path is
  committed; its 300 ids are the same, and the draw run again from it gives the same 26 and the
  same spares, checked in code. The first file's sha256 was `eb7514ee...6b6`.)
  - From the earlier selections' own code: phase A's 32 singles (development and held out),
    the find line's retrieval sample, its development sample and find-e2e's sample
    (`singles.used_by_find()`, imported unchanged): 226.
  - By a scan for any Verified id in a file or folder name, or in a file's text, under
    `~/.cache/sanchopanza` (every benchmark's runs, logs, work copies and harness reports) and
    this repository's `benchmarks/` and `docs/`: 74 more. Most are named in recorded Claude Code
    transcripts (`memory-real/transcripts`) or in SWE-chat sessions (`candor-external/swe-chat`);
    also the harness's gold feasibility check (django-11099), find's prereg (django-10097) and the
    development probe's four (`benchmarks/adopt_dev/common.py`: django-12143, django-15104,
    django-15563, sympy-18763). A mention counts as a use: from a mention we cannot tell whether
    it was used, and excluding costs only pool.
  - One file names all 500 (`swe-eval/verified-rows.json`, the dataset's copy): listed, not
    counted.
- **Strata, as phase A's held out:** 10 easy (`<15 min fix`), 10 medium (`15 min - 1 hour`), 6
  hard (`1-4 hours`, `>4 hours`). Pools after exclusion: 80, 107 and 13.
- **Draw.** Seed 20261003. Per stratum, in that order, the unused rows sorted by id and shuffled
  whole with one `random.Random(seed)`; the first 10 / 10 / 6 are drawn, the rest follow in the
  same order as that stratum's spares (12 written per stratum; the hard stratum has 7).

| stratum | instance | repository |
|---|---|---|
| easy | django__django-11133 | django |
| easy | sympy__sympy-24539 | sympy |
| easy | django__django-10914 | django |
| easy | django__django-15863 | django |
| easy | django__django-13023 | django |
| easy | sphinx-doc__sphinx-8269 | sphinx |
| easy | django__django-14787 | django |
| easy | sphinx-doc__sphinx-9367 | sphinx |
| easy | django__django-12125 | django |
| easy | django__django-16429 | django |
| medium | django__django-16819 | django |
| medium | sympy__sympy-14976 | sympy |
| medium | sympy__sympy-13091 | sympy |
| medium | sympy__sympy-22914 | sympy |
| medium | django__django-11848 | django |
| medium | sphinx-doc__sphinx-7748 | sphinx |
| medium | django__django-16454 | django |
| medium | sympy__sympy-20438 | sympy |
| medium | django__django-11551 | django |
| medium | sympy__sympy-19040 | sympy |
| hard | sympy__sympy-12489 | sympy |
| hard | django__django-12325 | django |
| hard | django__django-15629 | django |
| hard | django__django-15268 | django |
| hard | django__django-13344 | django |
| hard | django__django-10554 | django |

16 django, 7 sympy, 3 sphinx (phase A's held out: 15 django, 4 sympy, 4 sphinx, 2 matplotlib, 1
scikit-learn). The earlier samples took up to 12 per repository, so the smaller repositories are
used up: after exclusion only django (138), sympy (34), sphinx (14), matplotlib (9) and
scikit-learn (5) have rows left. The mix is the draw's, not chosen.

**Validation before sealing (free, Docker, no session).** For each drawn instance, in table
order, one at a time (the disk is nearly full): pull its image, export a working copy as the
runner does, and run the official harness twice, with the gold patch (must resolve) and with an
empty patch (must not resolve). An instance fails when the image does not pull or build, the
export fails, the gold patch does not resolve or the empty patch does; it is replaced by its
stratum's next spare that passes, in spare order. Results go to
`benchmarks/adopt_d/singles-validated.json` and here, with each replacement and its reason. If the
hard stratum runs out of spares (7), it is run with fewer and that is said.

How it was done (`validate_d.py`, written 2026-10-05 before the run): swebench 5.0.2 never runs an
empty patch (it lists it under `empty_patch_ids` and writes no report), so "the empty patch must
not resolve" is checked twice, both must hold: the literal empty patch, read from the harness's
run report, and a no-op patch that only adds `adopt_d_noop_patch.txt` at the repository root,
which the harness runs (FAIL_TO_PASS must fail; its PASS_TO_PASS counts are recorded). Images are
only pulled: an image counts as failed only when the registry says it does not exist; a network
error stops the run with nothing recorded. A harness that gives no report twice fails the
instance. Whether the gold patch applies to the exported copy is recorded, not a criterion.
Result (2026-10-05, 10:44-13:15, `singles-validated.json`): **26 of 26 drawn instances pass**,
no replacement, no spare tried, no shortfall. Every image pulled; the gold patch resolved, the
literal empty patch was listed unrun and the no-op patch did not resolve in all 26; the gold patch
applied to the exported copy in all 26. 166 to 664 s per instance. The selected list is the table
above, unchanged.

**Disjointness, again, right before sealing:** `draw.py check` scans again and fails if any drawn
or spare id is now named anywhere else (for example by a development probe written after the
draw). A clash replaces that instance by its stratum's next spare, said here. It does not
read inside phase D's own folders, which name drawn and spare ids by design after the draw
(`draw.CHECK_SKIP`): `~/.cache/sanchopanza/adopt/validate-d/`, `adopt/d-capture/`,
`adopt/d-selftest/` and this results folder (their file and folder names are still read).

- Run 2026-10-05, after the selftest, with 16 of the 26 instances validated:
  `{"drawn_or_spare_now_used_elsewhere": {}}`, exit 0. The need probe's ten instances
  (`benchmarks/find_need/`) were in the scan and none is drawn or a spare.
- Right before sealing: _(to fill in: run again after the validation, and the need probe if run)_

## Arms, model, sessions

| arm | what |
|---|---|
| N | Claude Code alone |
| S | `sanchopanza install --scope project --write`, the default install, of a frozen copy |

- **S's code:** frozen with `freeze.py` (`[jev,mcp]`) at commit **7a39a1f**. From eebdfa6
  (phase A) to 1ea9302 the source changes in 7 files; what `install` writes changes only by
  `alwaysLoad` on find's server. The browse and loop hooks changed are not wired by `install`,
  and the memory changes act only with `--memory`, which S does not use. **1ea9302 to 7a39a1f
  under `src/`:**
  - `mcp.py`: find's description, its parameters' descriptions, `kind` as an enum and the MCP
    server instructions (Claude Code 2.1.285 puts them in the first user message). Fixed at
    session start; they do not move the cached prefix within a session.
  - `find_nudge.py` and the `find-hook` subcommand: added, wired only by `install --find-nudge`,
    which S does not use.
  - `guard_hook.py`, `hookio.py`: helpers moved, no change in behaviour.
  - `harness/generic.py` (7a39a1f): **the delegation fix, below.** `harness/__init__.py`: a
    RecursionError on `from sanchopanza.harness import Guardian` in a fresh interpreter (the
    hooks import `generic` directly and never hit it).
  - `skill_code.md`: unchanged from 1ea9302 in the end (two lines on the nudge were added and
    taken out again).
  - So what `install` writes (`.mcp.json`, `.claude/settings.json`, the skill) is byte-identical
    to 1ea9302's, checked in `d-capture/7a39a1f/`.
- **Found before sealing: S's delegations always failed (fixed in 7a39a1f).** With no
  `SANCHOPANZA_TIERS`, which the default install never sets, the PreToolUse hook rewrote every
  delegation that named a subagent to `subagent_type: "default"`, an agent Claude Code does not
  have. Over every recorded stream of the study, **13 of 13 S delegations failed** with "Agent
  type 'default' not found" (phase A chains: dvc-rel-1 Sf 2, its rerun 2, pydantic-rel-1 Sf 5;
  probe 2: sympy-12419 S 4) and **1 of 1 N delegation succeeded**. This was in every copy since
  0.1.0, phase A's included. It hit S only and cost turns, so it biased S's cost and turns; it
  was rare (0 delegations in the 90 single streams). 7a39a1f allows a delegation untouched and
  asks nothing when no tier is configured, and leaves a tier with no configured name alone.
  Reproduced and checked fixed for free in `d-capture/agent-repro/` and
  `d-capture/agent-repro-7a39a1f/`. Phase D therefore runs a copy that phase A did not: phase A's
  verdicts stand for the copy they ran.
- **Model:** Haiku 4.5 (`claude-haiku-4-5-20251001`), both arms. Claude Code 2.1.285 (the private
  copy of phase A, first on PATH, `DISABLE_AUTOUPDATER=1`), `claude -p` on the subscription, the
  coordinating session's environment stripped (`run.child_env`). Jev `jev-1.13.0` for the decider.
- **Prompt, tools, test command:** phase A's singles, unchanged (`singles_run.PROMPT`,
  `singles_run.test_command`, default tools minus WebFetch and WebSearch, `runtests` shim).
- **Repetitions: 3 per instance and arm, 156 sessions.** Each session in a fresh working copy
  exported from the image, at its own path (`<instance>-r<k>-<arm>`), so no session can see
  another's Claude Code project folder. N and S of the same repetition start together; an
  instance's three pairs run before the next instance; its image is pulled once and dropped after
  its six sessions are graded.
- **Instance order: seeded and interleaved, not table order** (`plan_d.order`, seed 20261005), so
  that no stratum is left to the end of the batch or of the subscription's week. The strata are
  taken in the order they first appear in `singles-validated.json` (easy, medium, hard); each is
  shuffled with one `random.Random(20261005)`, used for all three in turn; the j-th instance of a
  stratum of n is placed at (j + 0.5) / n, ties in stratum order. With 10 / 10 / 6 a hard instance
  comes about every fourth place. The order is computed from the validated list (after any
  replacement), and logged at the batch's start (`D START ... order [...]` in `D.log`).

## Measures

- **Ran:** a session ran when it was not NOT RUN, was not cut by the timeout and reported a
  result (`confirm.ran`). An error result that is not a usage limit ran (see "Stops and re-runs").
  A **pair** (instance, repetition) is complete when both sessions ran on Haiku 4.5 and Claude Code
  2.1.285, were graded by the harness, and (S) the session is the treatment (below). A row whose
  `claude_version` is not 2.1.285 is excluded (code `claude version`), whatever else it holds.
- **Exclusions** are reported per arm, per stratum and per criterion (`confirm_d.excluded`; one
  session can carry several codes: no row, started with no row, model, Claude Code version, did not
  run, D's commit, (a) to (g), not graded, refused by `confirm.arm_result`).
- **Resolved:** the official SWE-bench harness on the session's final diff, as phase A. A grade
  with no report from the harness is missing, not a loss. **An empty final diff is graded not
  resolved** (reason `empty diff`): swebench 5.0.2 drops an empty prediction before running it
  and writes no report, and the official leaderboard counts it unresolved. Without this rule an
  agent that changed nothing would make its pair missing instead of a loss. (No counted phase A
  or probe session had an empty diff: singles 0/90, probes 0/34; 8 exist in phase A's set-aside
  `runs/*-limit1/` folders, which no verdict reads.) Every `grade.json` records the sha256 of the
  harness's `run_swe.py`.
- **No grade is seen during the batch.** `D.log` gives each session's status, cost and turns, and
  for grading only `graded <id> r<k>` (or that the harness gave no report, or that grading failed);
  never resolved or not. Grades are in each session's `grade.json`, read only by `confirm_d.py`.
  An amendment after the first session was graded is still reported as written after grading
  began.
- **Cost:** list-price cost of the Claude Code call (`run.facts`; a call cut by the timeout is
  charged its cap) plus Jev's journal cost.
- **Turns:** `num_turns` of the result event.
- **Adoption (S):** calls to `mcp__sanchopanza__find_in_repo`, to `ToolSearch` and to the skill
  (`Skill` calls whose `skill` is `sanchopanza-code`; calls to any other skill are counted apart),
  per session, from the stream's tool uses (main thread and subagents). Over every S session that
  ran as the treatment, graded or not, whatever its N.
- **Delegation (both arms):** `Agent` and `Task` calls per session. A delegation **failed** when
  its error result says `Agent type '<X>' not found` for an X other than the `subagent_type` the
  call asked (the hook's rewrite). Every `Agent type ... not found` is counted beside, whatever X.
  Over every session that ran (S: as the treatment), graded or not.
- Per instance: `res_N`, `res_S` = mean resolved over its complete pairs; `cost_N`, `cost_S`,
  `turns_N`, `turns_S` = means over the same pairs.

## When an S session counts as the treatment

Amendment 5's positive evidence, all of (a) to (f), unchanged (`confirm_d.criteria` reads them one
by one and raises if it ever disagrees with `confirm.with_decider`); plus the frozen copy's commit
being D's (7a39a1f), and (g):

- (a) the frozen copy stamped with `jev` and `mcp`;
- (b) every decider probe in the row is `JevDecider`;
- (c) find_in_repo's server `connected` in the init line;
- (d) every line its hooks logged had the key, and there is at least one;
- (e) every journalled decision comes from `jev`, `budget` or `code`;
- (f) at most 10 % of the decisions asked of Jev came back with an error;
- **(g) find_in_repo not deferred:** `mcp__sanchopanza__find_in_repo` is in the init line's
  `tools`, the session's transcript was copied, no `deferred_tools_delta` attachment in it names
  the tool in its `addedNames` or `addedLines` (only those two fields are read: a delta that lists
  find as removed, or names it elsewhere, does not fail (g)), and the `.mcp.json` the session ran
  with has `"alwaysLoad": true` on the server.

An S session that fails any of these is not the treatment: its pair is incomplete. A failure of
D's commit, (a) to (e) or (g) also stops the batch; (f) stops it only when it fails in 2 of the
last 3 S sessions (see "Stops and re-runs").

## Hypotheses and verdicts

Bootstrap: 10,000 paired resamples over the 26 instances (an instance carries its three pairs),
seed 20261004, percentile intervals, read by index from the sorted draws: two-sided 95 % is
draws[250] to draws[9749]; H1's one-sided bound is draws[100].

- **H1, non-inferior success.** D = mean over instances of (`res_S` - `res_N`), a share. Holds
  when the one-sided 99 % lower bound (the 1st percentile of the bootstrap, draws[100] of 10,000)
  is at least **-2/26 = -0.077** (the margin of phase A's singles, 2 of 26, as a share), compared
  exactly (fractions), the margin included. Undecided when any instance has no complete pair;
  which, is said. **Why the 1st percentile and not the 5th:** at n = 26, with differences that
  take a few discrete values, the percentile bootstrap undercovers. The exact rule, simulated on
  phase A's resolve profile (`sim_h1.py`, seed 20261005, 4,000 studies per scenario, below), let a
  design sitting exactly at the margin pass in **0.117** of studies with the 5th percentile and
  **0.044** with the 1st; power at equality was 0.94 and 0.84. Of the two, only the 1st percentile
  keeps the type I error at or under 5 % in that simulation (its limits: "Power, said before").
- **H2, cost.** Per instance r = `cost_S` / `cost_N`; the statistic is the median of r, with its
  two-sided 95 % interval. **Non-inferior cost** holds when the upper bound is below 1.10.
  **Cheaper** holds, separately, when the upper bound is below 1. Over the instances with at least
  one complete pair (and N's mean cost above 0); the others are listed, and a reading over fewer
  than 26 instances says so beside the verdict.
- **H4, adoption, reported, no verdict:** share of S sessions with at least one call to
  find_in_repo (with a bootstrap interval over instances), calls per session; the same for
  ToolSearch, the `sanchopanza-code` skill and other skills, apart. Over the S sessions that ran as
  the treatment (see "Measures"). Per stratum as well. **Delegations, both arms, per stratum as
  well:** Agent/Task calls per session, failed delegations and sessions with one, and every
  `Agent type ... not found` (see "Measures"); a failed S delegation would mean the fix above did
  not hold.
- **Exploratory, no verdict:** median per-instance turns ratio `turns_S` / `turns_N` with its
  interval; cost per turn; within S, resolved and cost of sessions that called find against those
  that did not (selected by the agent, so not causal).
- Reported beside, deciding nothing: totals per arm and stratum, the per-instance table, how many
  instances flip between repetitions in each arm, Jev's spend, every guard block with its command,
  and the exclusions per arm, stratum and criterion.

Whatever does not hold is reported as not holding.

## Power, said before

**H1, the verdict's own rule.** `benchmarks/adopt_d/sim_h1.py` simulates H1 exactly as
`confirm_d.h1` applies it: 26 instances drawn with replacement from phase A's resolve profile (per
phase A single, the share resolved over its three runs: N and the two readings of S), 3
repetitions per arm, D = mean over instances of `res_S` - `res_N`, 10,000 bootstrap resamples of
the instances, H1 held when the bound is at least -2/26 (compared on integer sums, exactly). Two
scenarios: **at the margin**, S's chance is each instance's times (1 - h), h chosen so that the
expected D is -2/26; **at equality**, both arms with the instance's chance. Run 2026-10-05,
`sim_h1.py --sims 4000`, 4 min 17 s:

    profile: 26 phase A singles, mean resolve 0.6538; margin harm h = 0.1176; 4000 studies per scenario, seed 20261005
    draws[100] (1 %): type I at the margin 0.0440 (MC se 0.0032); power at equality 0.8380
    draws[500] (5 %): type I at the margin 0.1172 (MC se 0.0051); power at equality 0.9390

| bound | P(H1 holds) at the margin (type I) | P(H1 holds), arms equal (power) |
|---|---|---|
| draws[500], 5th percentile (the draft of 2026-10-03) | 0.117 | 0.94 |
| **draws[100], 1st percentile (the rule)** | **0.044** | **0.84** |

**The draft's estimate, kept for the record.** `benchmarks/adopt_d/power.py` (copied from the
session's scratchpad, unchanged, run again on 2026-10-03 with the same output) resamples the same
runs but judges H1 by the normal approximation (sum - 1.645 se); "S 15 % worse" multiplies each
instance's chance of resolving by 0.85. It is not the verdict's rule; its premise, that the
normal approximation and the percentile bootstrap are close at n = 26, did not hold (below).

| singles x repetitions | P(H1 holds), arms equal | P(H1 holds), S 15 % worse |
|---|---|---|
| 26 x 1 | 0.66 | 0.06 |
| **26 x 3** | **0.92** | **0.03** |
| 52 x 2 | 0.98 | 0.02 |

Cost (`power.py`): paired ln(S/N) sd on singles 0.381; at 26 x 3 the ~95 % half-width on the
mean log ratio is about x1.088.

Caveats on these numbers, said now:

- **The type I error depends on the shape of the harm.** `sim_h1.py` spreads it over every
  instance (each instance's chance times 1 - h). When the same expected loss comes as S losing two
  whole instances (N 3 of 3, S 0 of 3, the rest equal), the rule passes far less often: about
  0.1 % or less (a scratch run of the same rule, not in the repository, held in 0 of 1,000
  studies at either bound). 0.044 is the rate for the shape simulated, not a bound over all
  shapes.
- The draft said the normal approximation and the percentile bootstrap "should be close, the
  bootstrap slightly narrower" at n = 26. That was wrong in the direction that matters: the
  bootstrap undercovers here, which is why the rule moved to the 1st percentile.
- Both simulations use phase A's resolve profile; the new instances' rates are not known (below).
- The cost half-width treats all of the per-instance spread as run noise that repetitions
  shrink, so it is optimistic; and H2 is decided on a median, whose interval is wider than the
  mean's.
- With phase A's ratios (1.084 and 1.225), **H2's "non-inferior cost" is unlikely to hold unless
  find shortens sessions**. That is what phase D asks; a "does not hold" is a result.
- The new instances lean more on sympy than phase A's; their resolve rates are not known.

## Caps, in code (list price)

| what | cap |
|---|---|
| per call (`--max-budget-usd`) | 1.50 |
| per instance, held before it starts | its six sessions' caps, 9.00 (all or nothing: no instance runs some pairs and not others for want of room) |
| total, absolute | `CEILING_BASE_USD` + `CEILING_ADDED_USD` (`run_d.py`): the base _(to fill in at sealing from `run_d.py ledger`)_, plus 90.00 (or 110.00: _(owner's decision pending)_) |

- **The ledger** (`run_d.py ledger`, free): every row under `adopt/runs/` (`run.spent_so_far`),
  `adopt/singles/` (`singles_run.spent_singles`), `adopt/singles-d/` (set-aside `-limit<k>`
  folders included; a folder with a stream and no row is charged what its stream reports, or its
  cap) and the three development probes' roots `adopt/dev-alwaysload/`, `adopt/dev-need/`,
  `adopt/dev-nudge/` (rows and abandoned attempts). Jev's journal cost is in D's and the probes'
  rows; phase A's two ledgers count Claude Code's calls only, as phase A did. On 2026-10-05,
  before the need probe: 205.30 (runs 145.55, singles 43.78, singles-d 0, dev 15.97). The base is
  what it says at sealing.
- **The hold:** before an instance starts, the ledger is read again and the instance's six
  sessions' caps (9.00) must fit under the ceiling with it; if they do not, the batch stops before
  that instance and nothing of it runs.
- **If the ceiling binds**, the instances it leaves out have no complete pair: H1 is undecided
  (it needs every instance) and they are listed by name; H2 is read over the instances with a
  complete pair, and said as such (n of 26), the others listed.

**Estimate: ~78 USD** (156 sessions at phase A's per-session costs: N 0.46, S 0.53). Jev is capped
by the hooks at 0.10 per session (7.80 at most), cents expected. The runner refuses another model,
a call cap above 1.50, another frozen commit, a Claude Code other than 2.1.285, a seal that does
not hold, unfilled ceiling constants, an S arm whose probe does not find `JevDecider` (checked at
the batch's start and again before every pair), a session over an earlier one's project folder or
over an evidence folder with no row, and a second batch while one runs. Run outside the session
(`Win32_Process.Create`, `run-d.cmd`), watched live, not alongside another session's run on the
subscription. No retries. Ctrl+C (and Ctrl+Break) are ignored: a stray one killed phase A
mid-grade.

### Stops and re-runs

A stop is a pause: `run_d.py run` again resumes, and grades for free, at its instance's turn,
whatever ran and has no grade. What ran is graded even when the batch stops in the middle of an
instance, and the instance's image is dropped.

- **Run again whole, only when no outcome was seen:** an error result that names a usage limit
  (`api_error_status` 429, or "usage limit", "weekly limit", "rate limit", "hit your ... limit" in
  its text), recorded `NOT RUN (error result)`; a session `claude -p` never started (`NOT RUN
  (harness)`: no session id, no result, nothing spent); or an evidence folder with no row and no
  stream. Every session of that instance that started, except in a missing repetition (below),
  is set aside with its working copy's Claude Code folder under `singles-d/<instance>-limit<k>/`
  (counted in the ledger, read by no verdict), the batch stops, and on the next run the instance
  runs again whole, as amendment 2 did.
- **Missing, never run again:** a folder with a stream and no row (a session that started and
  crashed). Its pair is missing, the other arm of that repetition is not started if it had not
  been. A set-aside of the instance leaves that repetition in place and never runs it again (only
  a session in it that is to be run again is moved aside).
- **Any other error result counts as ran:** recorded `error result (not a usage limit)`, graded on
  its diff like any session, and it stops the batch so that it is looked at.
- **A systemic treatment failure stops the batch** at the first S session that fails D's commit,
  (a) to (e) or (g): those say the install or the harness is broken for every session to come.
  (f), Jev's error rate, can be one bad session: it excludes that session, and stops the batch only
  when it fails in 2 of the last 3 S sessions that left a row (set-asides not counted).
- **Before every pair:** D's seal holds, and the unsealed inputs both arms load (see "Threats")
  still have the hashes recorded at the batch's start (logged as `D INPUTS`); either change stops
  the batch before the pair starts.
- **Before every instance:** at least 15 GB free on C:, and its hold fits under the ceiling.
- **One batch at a time:** `singles-d/batch.lock`, created exclusively with the process id; the
  lock of a process that is gone (a crash) is taken over, and the log says so.

## The runner (`benchmarks/adopt_d/`)

Nothing under `benchmarks/adopt/` is edited and no file is added there (`confirm.seal_holds`
requires every `benchmarks/adopt/*.py` to be in phase A's manifest). The runner imports `run`,
`singles_run`, `docker_env`, `hook_env` and `confirm` as a library. Written 2026-10-05 (3dcec1b),
changed after the adversarial review (0df3bdf).

- **`run_d.py`**, the batch: `check` (free: every refusal, the order, the ledger, the inputs'
  hashes), `ledger` (free), `run` (paid, resumable, started by `run-d.cmd`), `grade` (Docker,
  free: grades what ran, starts nothing), `selftest <id>` (below).
  - At import: sets `ADOPT_SANCHO` to D's frozen copy before importing `run` (it reads it at
    import) and refuses another, puts the private Claude Code first on PATH, sets
    `DISABLE_AUTOUPDATER=1`, and checks that `run` and `hook_env` took D's copy.
  - Its refusal (`d_refusal`): `D_COMMIT` and `CEILING_BASE_USD` filled in, D's seal holds
    (`seal_refusal`, see the header), the frozen stamp's commit is D's with `jev` and `mcp`, Haiku,
    call cap 1.50, Claude Code 2.1.285, and last `run.decider_probe` gives `JevDecider` (the only
    check that starts a process of the frozen copy). `run.held_refusal` is not used (it checks
    phase A's seal and eebdfa6).
  - `one(row, arm, rep, key)`, a copy of `singles_run.one` with the repetition in the paths:
    evidence `singles-d/<id>/r<k>/<arm>`, work `run.WORK/<id>-r<k>-<arm>`, key
    `run.arm_keyfile(key, "<id>-r<k>", "S")`. It reuses `run.command`, `run.facts`,
    `run.install_sancho`, `run.child_env`, `run.stdin_for`, `docker_env.export`/`agent_diff`,
    `singles_run.PROMPT`/`test_command`/`rows`, and keeps phase A's refusals (an evidence folder
    with no row; a project folder that already holds a session). The row records the model,
    image, provenance, Claude Code's version, the unsealed inputs' hashes, the transcript's source
    and whether it was copied, and for S the decider probe and `find_hidden` (the reason (g)
    fails, or empty).
  - `session_call`: the `claude -p` call, its status as in "Stops and re-runs" (a call cut by
    the timeout is charged its cap).
  - `grade_arm`: the official harness through `run_swe.py` on the session's final diff, an empty
    diff graded not resolved without it, no report kept as missing.
  - The ledger, the hold and the stops of "Caps".
- **`plan_d.py`**: `instances` (a complete validation's `selected` list from
  `singles-validated.json`, in table order; refuses an incomplete one or a duplicate) and `order`
  (the run order, above). `run_d.plan_rows` also refuses an image other than the one validated.
- **`guard_d.py`**: the unsealed inputs' sha256 (see "Threats") and the batch lock.
- **`confirm_d.py`**, the verdicts above: refuses to read anything until D's seal holds;
  `criteria` (D's commit, (a) to (g), checked against `confirm.with_decider`), the exclusions,
  its own bootstrap (seed 20261004; H1's draws[100], which `confirm.paired_interval` does not
  give), H1, H2, H4, delegation, the exploratory and beside tables.
- **`validate_d.py`**: the validation above, writing `singles-validated.json`; refuses once the
  seal exists. Started by `run-validate.cmd`.
- **`selftest_d.py`** (`run_d.py selftest <id>`, Docker, free, no session): the grading path end to
  end on one validated instance, the gold patch standing in for the agent. (1) The working copy
  exported as the runner does, the gold patch applied, the diff taken as from a session and graded
  by `run_d.grade_arm`: it must resolve. (2) A second export with the dataset's test patch, the
  FAIL_TO_PASS tests run through the `runtests` shim in the environment `run.child_env` gives the
  sessions: they must fail without the gold patch and pass with it. Writes under
  `adopt/d-selftest/<id>/`. **Result, 2026-10-05, django__django-11133: SELFTEST OK.** The gold
  patch resolved through `grade_arm`; FAIL_TO_PASS
  `httpwrappers.tests.HttpResponseTests.test_memoryview_content` exited 1 without the gold patch
  and 0 with it; 566 s, image pulled and dropped by the selftest.
- **`sim_h1.py`** and **`power.py`**: the power above. **`draw.py`**: the scan, the draw and the
  disjointness check.
- **Tests** (`test_run_d.py`, `test_confirm_d.py`, `test_validate_d.py`; no session, no spend,
  74 pass on 2026-10-05): among them the paths per repetition, the hold and its release, the
  ledger (the need probe included), the seal and its breaks, the order, the input check and the
  lock, which statuses are run again and which stop, the systemic and (f) stops, that the log
  never says a grade, (g) on a recorded phase A transcript (deferred: must fail), on a development
  probe's (must pass) and on `addedNames` only, an empty diff graded as a loss, the bootstrap on
  fixed numbers and H1's inclusive margin, and `criteria` agreeing with `confirm.with_decider` on a
  recorded probe.
- **`run-d.cmd`, `run-validate.cmd`**: launchers, not sealed (see the header).

## Threats

- Repetitions of one instance are not independent draws of the task; the bootstrap resamples
  instances, not sessions, for that reason.
- Haiku only, Claude Code pinned at 2.1.285 while the current release is later; a result is for
  that pair.
- The control is run again here (new instances), so N and S share the day, the binary and the
  subscription's state.
- alwaysLoad puts find's schema in every S request: some of any extra cost is that prefix, which
  the exploration splits from turns.
- The exclusion scan reads what is on this machine on 2026-10-03; an instance used on another
  machine and recorded nowhere here would not be seen.
- **Inputs no seal covers.** Both arms load the owner's global Claude Code instructions,
  `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md` (seen in D's captured first request,
  `d-capture/7a39a1f/`): general coding and workflow conventions (style, testing, git, security,
  when to use subagents) and notes for the owner's other projects, nothing about SWE-bench or
  sanchopanza. The prompts' issue texts come from the harness's `swe-eval/verified-rows.json`
  (`singles_run.rows()`), and grading goes through its `run_swe.py`. None of these is in the
  seal. They are hashed at the batch's start (logged as `D INPUTS`), stored in every row
  (`run_swe.py`'s also in every `grade.json`), compared before every pair, and a change stops the
  batch. They reach both arms alike. They can still interact with the treatment: the
  instructions mention subagents and S's hooks act on delegations, one reason delegation is
  counted in both arms.
- **(f) can exclude one way.** The find server asks Jev, so Jev's errors are more likely in S
  sessions that call find: excluding sessions that fail (f) may drop find users more than others.
  The (f) exclusions are reported per arm, stratum and criterion, with the other exclusions, so a
  skew shows.
