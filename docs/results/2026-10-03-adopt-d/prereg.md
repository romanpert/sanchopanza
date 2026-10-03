# Adoption study, phase D: pre-registration (DRAFT, not sealed)

Drafted 2026-10-03, before any session of phase D. **Not binding yet.** It becomes binding once
`prereg.sha256` exists and still matches the files its manifest names: this document,
`benchmarks/adopt_d/*.py` and `benchmarks/adopt_d/*.json` (the draw, the exclusion list, the
validation summary, the runner and the verdicts), the files of `benchmarks/adopt/` that the runner
imports (unchanged; their hashes must still equal those in
`../2026-09-30-adopt/prereg-confirm.manifest.json`) and `benchmarks/candor/seal.py`. Seal with:

    python benchmarks/candor/seal.py prereg --out docs/results/2026-10-03-adopt-d \
        --code "benchmarks/adopt_d/*.py" "benchmarks/adopt_d/*.json" \
        "benchmarks/adopt/*.py" "benchmarks/candor/seal.py"

Before sealing, four things must be done and written here: the development probe's result
(below), the validation of the drawn images, the disjointness check run again, and the frozen
commit and absolute ceiling filled in. After sealing, a change is an amendment written here,
dated, before any verdict is read.

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

> Result: _(placeholder: sessions, find visible in N of N, calls to find in N of N sessions,
> ToolSearch calls, commit and Claude Code version it ran on, cost)_

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

**Disjointness, again, right before sealing:** `draw.py check` scans again and fails if any drawn
or spare id is now named anywhere else (for example by the development probe, which is still
being written). A clash replaces that instance by its stratum's next spare, said here.

## Arms, model, sessions

| arm | what |
|---|---|
| N | Claude Code alone |
| S | `sanchopanza install --scope project --write`, the default install, of a frozen copy |

- **S's code:** frozen with `freeze.py` (`[jev,mcp]`) at commit _(to fill in at sealing: the one
  the development probe ran; 1ea9302 or a descendant)_. From eebdfa6 (phase A) to 1ea9302 the
  source changes in 7 files; what `install` writes changes only by `alwaysLoad` on find's server.
  The browse and loop hooks changed are not wired by `install`, and the memory changes act only
  with `--memory`, which S does not use. Any commit chosen later is listed here with its diff to
  1ea9302 under `src/`.
- **Model:** Haiku 4.5 (`claude-haiku-4-5-20251001`), both arms. Claude Code 2.1.285 (the private
  copy of phase A, first on PATH, `DISABLE_AUTOUPDATER=1`), `claude -p` on the subscription, the
  coordinating session's environment stripped (`run.child_env`). Jev `jev-1.13.0` for the decider.
- **Prompt, tools, test command:** phase A's singles, unchanged (`singles_run.PROMPT`,
  `singles_run.test_command`, default tools minus WebFetch and WebSearch, `runtests` shim).
- **Repetitions: 3 per instance and arm, 156 sessions.** Each session in a fresh working copy
  exported from the image, at its own path (`<instance>-r<k>-<arm>`), so no session can see
  another's Claude Code project folder. N and S of the same repetition start together; an
  instance's three pairs run before the next instance; its image is pulled once and dropped after
  its six sessions are graded. Instances run in table order.

## Measures

- **Ran:** a session ran when it was not NOT RUN, was not cut by the timeout and reported a
  result. A **pair** (instance, repetition) is complete when both sessions ran, were graded by
  the harness, and (S) the session is the treatment (below).
- **Resolved:** the official SWE-bench harness on the session's final diff, as phase A. A grade
  with no report from the harness is missing, not a loss.
- **Cost:** list-price cost of the Claude Code call (`run.facts`; a call cut by the timeout is
  charged its cap) plus Jev's journal cost.
- **Turns:** `num_turns` of the result event.
- **Adoption (S):** calls to `mcp__sanchopanza__find_in_repo`, to `ToolSearch` and to `Skill`,
  per session, from the stream's tool uses (main thread and subagents).
- Per instance: `res_N`, `res_S` = mean resolved over its complete pairs; `cost_N`, `cost_S`,
  `turns_N`, `turns_S` = means over the same pairs.

## When an S session counts as the treatment

Amendment 5's positive evidence, all of (a) to (f), unchanged; plus (g):

- (a) the frozen copy stamped with `jev` and `mcp`;
- (b) every decider probe in the row is `JevDecider`;
- (c) find_in_repo's server `connected` in the init line;
- (d) every line its hooks logged had the key, and there is at least one;
- (e) every journalled decision comes from `jev`, `budget` or `code`;
- (f) at most 10 % of the decisions asked of Jev came back with an error;
- **(g) find_in_repo not deferred:** `mcp__sanchopanza__find_in_repo` is in the init line's
  `tools`, the session's transcript was copied, no `deferred_tools_delta` attachment in it names
  the tool, and the `.mcp.json` the session ran with has `"alwaysLoad": true` on the server.

An S session that fails any of these is not the treatment: its pair is incomplete.

## Hypotheses and verdicts

Bootstrap: 10,000 paired resamples over the 26 instances (an instance carries its three pairs),
seed 20261004, percentile intervals.

- **H1, non-inferior success.** D = mean over instances of (`res_S` - `res_N`), a share. Holds
  when the one-sided 95 % lower bound (the 5th percentile of the bootstrap) is at least
  **-2/26 = -0.077** (the margin of phase A's singles, 2 of 26, as a share). Undecided when any
  instance has no complete pair; which, is said.
- **H2, cost.** Per instance r = `cost_S` / `cost_N`; the statistic is the median of r, with its
  two-sided 95 % interval. **Non-inferior cost** holds when the upper bound is below 1.10.
  **Cheaper** holds, separately, when the upper bound is below 1. Over the instances with at least
  one complete pair; the others are listed.
- **H4, adoption, reported, no verdict:** share of S sessions with at least one call to
  find_in_repo (with a bootstrap interval over instances), calls per session; the same for
  ToolSearch and the skill. Per stratum as well.
- **Exploratory, no verdict:** median per-instance turns ratio `turns_S` / `turns_N` with its
  interval; cost per turn; within S, resolved and cost of sessions that called find against those
  that did not (selected by the agent, so not causal).
- Reported beside, deciding nothing: totals per arm and stratum, the per-instance table, how many
  instances flip between repetitions in each arm, Jev's spend, every guard block with its command.

Whatever does not hold is reported as not holding.

## Power, said before

`benchmarks/adopt_d/power.py` (copied from the session's scratchpad, unchanged, run again on
2026-10-03 with the same output). It resamples phase A's own runs: per single, N and the two
readings of S treated as three draws of one distribution (the null that a non-inferiority design
must survive); "S 15 % worse" multiplies each instance's chance of resolving by 0.85.

| singles x repetitions | P(H1 holds), arms equal | P(H1 holds), S 15 % worse |
|---|---|---|
| 26 x 1 | 0.66 | 0.06 |
| **26 x 3** | **0.92** | **0.03** |
| 52 x 2 | 0.98 | 0.02 |

Cost: paired ln(S/N) sd on singles 0.381; at 26 x 3 the ~95 % half-width on the mean log ratio
is about x1.088.

Caveats on these numbers, said now:

- The simulation's interval rule is the normal approximation (sum - 1.645 se), not the
  percentile bootstrap used for the verdict; at n = 26 they should be close, the bootstrap
  slightly narrower.
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
| total, absolute | _(to fill in at sealing: everything spent under `adopt/runs/`, `adopt/singles/`, `adopt/singles-d/` and the development probe's root, + 90.00)_ |

**Estimate: ~78 USD** (156 sessions at phase A's per-session costs: N 0.46, S 0.53). Jev is capped
by the hooks at 0.10 per session (7.80 at most), cents expected. The runner refuses another model,
a call cap above 1.50, another frozen commit, a Claude Code other than 2.1.285, an unsealed
document, an S arm whose probe does not find `JevDecider`, and a session over an earlier one's
project folder. An error result (429, the weekly limit) is NOT RUN and stops the batch: that
instance's pairs are set aside under `singles-d/<instance>-limit<k>/` (counted in the ledger, read
by no verdict) and run again whole, as amendment 2 did. A session that started and left no row is
not run again; its pair is missing. Run outside the session (`Win32_Process.Create`), watched
live, not alongside another session's run on the subscription. No retries.

## The runner, to be written before sealing (`benchmarks/adopt_d/`)

Nothing under `benchmarks/adopt/` is edited and no file is added there (`confirm.seal_holds`
requires every `benchmarks/adopt/*.py` to be in phase A's manifest). The runner imports
`run`, `singles_run`, `docker_env`, `hook_env` and `confirm` as a library.

1. `run_d.py`: sets `ADOPT_SANCHO` to D's frozen copy before importing `run` (it reads it at
   import). Its own refusal (`d_refusal`): D's seal holds, the frozen stamp's commit is D's with
   `jev` and `mcp`, Haiku, call cap 1.50, Claude Code 2.1.285, `run.decider_probe` gives
   `JevDecider`. `run.held_refusal` is not used (it checks phase A's seal and eebdfa6).
2. `one(row, arm, rep)`, a copy of `singles_run.one` with the repetition in the paths:
   evidence `singles-d/<id>/r<k>/<arm>`, work `run.WORK/<id>-r<k>-<arm>`, key
   `run.arm_keyfile(key, f"{id}-r{k}", "S")`. It reuses `run.command`, `run.facts`,
   `run.install_sancho`, `run.child_env`, `run.stdin_for`, `docker_env.export`/`agent_diff`,
   `singles_run.PROMPT`/`test_command`/`rows`, and keeps phase A's refusals (an evidence folder
   with no row; a project folder that already holds a session).
3. `grade(id, rep)`: `singles_run.grade`'s harness call with the evidence path as a parameter
   (it is hard-wired to `RUNS/<id>/<arm>` and `run.ARMS` there).
4. Ledger: `run.spent_so_far()` + `singles_run.spent_singles()` + D's rows + the probe's rows;
   the absolute ceiling of the table above; `run.reserve`/`release` with the 9.00 hold per
   instance.
5. Evidence (g): `find_visible(evidence)`: the init line's tools, the transcript's
   `deferred_tools_delta`, the copied `mcp.json`. The row records the transcript's path and
   whether it was copied (a missing transcript fails (g)).
6. `confirm_d.py`: the verdicts above; reuses `confirm.with_decider` for (a)-(f) and
   `confirm.events`; its own bootstrap (H1 needs the one-sided 5th percentile, which
   `confirm.paired_interval` does not give) with seed 20261004; checks D's seal before reading.
7. `validate_d.py`: the validation above (gold and empty patch through `run_swe.py`), writing
   `singles-validated.json`; refuses once the seal holds.
8. Tests (no session, no spend): the paths per repetition, the hold, (g) on a recorded
   transcript from phase A (deferred: must fail) and on the development probe's (must pass), and
   the bootstrap on fixed numbers.

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
