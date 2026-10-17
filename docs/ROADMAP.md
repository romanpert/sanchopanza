# Roadmap: what is pending, by priority (2026-10-16)

What is still open in sanchopanza after the final scoreboard
([`docs/results/2026-10-13-final/`](results/2026-10-13-final/README.md)), and what the one known
consumer, an agent with its own harness, asked of it. Each item says what it would cost and
whether it is done. Measured results stay in `docs/results/`; this page only orders the work.

Cost: **free** is code, tests or replays with no model; **Jev** is TypeSafe calls (cents unless
said); **Claude** is Claude Code sessions on the subscription, quoted at list price.
Priority: **high** breaks something or blocks the consumer; **medium** is a cheap, measurable
gain; **low** is an idea, or an expensive cell with no margin shown.

## Priority table

| # | Item | Priority | Cost | State |
|---|---|---|---|---|
| C9 | Memory's prune deleted the standing rules of a project idle for 30 days | **high** | free | **done** (`230a2aa`) |
| C10 | Two names of other private projects and some local paths in public files | **high** | free | **in part**: free files clean, a test refuses new ones; sealed files and recorded runs wait on the owner |
| B1 | Publish a release (`v*` tag and PyPI) so the consumer stops pinning a tarball by commit | **high** | free (PyPI: owner's decision, irreversible) | **in part**: `v0.3.1` tagged with a GitHub release; PyPI approved by the owner, but the publish waits for the trusted publisher on pypi.org (owner's account) |
| D1 | OpenAI's Decisions API as one more provider | medium | free (adapter); OpenAI calls: owner's decision | **measured once** (D1: "no concluyente" at −5, −2.5 points [−6.1, +1.2], 0.0143 USD; `openai-decisions`) |
| C7 | The LongBench routing point, opt-in | medium | free (code); Claude for what follows | **done** (`9705f25`) |
| C1 | A PostToolUse check on MCP results (what A3's PreToolUse guard cannot read) | medium | Jev (replay ~0.05-0.10 USD), then Claude (~5 USD live probe) | **built, opt-in** (`--guard-mcp-post`); W17's development lot does not license a confirmation (+35 unsafe caught, +14 safe flagged, upper bound +8.0 past +7); next: a new registration with the cut fixed before its data, on fresh ATBench (~0.20 USD of Jev) |
| C2 | check_done with the tool results the answer rests on, not cut at 1,500 characters | medium | free (record builder) + Jev (~0.3-0.5 USD) | **built, opt-in** (`SANCHOPANZA_DONE_EVIDENCE`); checkdone-w17: not adopted, false blocks 165 → 123 of 828 (+5.07 [1.53, 9.77]) but catches 598 → 583 of 744 (−2.02 [−5.37, +0.26]) past the −2 guard; next: diagnose the lost catches (18, mostly multi-part workspace tasks), change the builder, confirm under a new registration |
| C8 | Four memory gaps read from the code and F2's logs | medium | free replays first; Claude (~40 USD, F2-sized) to confirm | **fixed in code** (merge `e029489`); measured live as it ships in W17: Sonnet 5.5 "S' better than N0; no gana (cost)", Opus 5.5 "not determined" (cost 0.999x [0.965, 1.055] over the sealed 1.05) |
| C4 | A5's `unrelated_at=0.65` on written text with fa-17-type pairs | low-medium | Jev 0.035 USD | **done**: 66 added verdicts, all right (Wilson 0.945); 0.65 is the default since 0.3.2 |
| C5 | `select_passages(fit_score=False)` against page order on fresh questions | low-medium | Jev 1.371 USD (C5b) | **done via C5b**: the free order confirmed over page order at 3,400 characters, +16.4 [+11.0, +21.9]; `fit_score=False` is the default since 0.3.2 |
| C6 | Closing Spanish's 3-6 points in page triage and passages | low | Jev (~0.2 USD pages, ~2.5 USD documents per arm) | idea, from B6 |
| C11 | The pointer guard's quality on long code: Sonnet 5.5 long60 chains, `pointers` against `--guard-full`, interleaved | medium | Claude (design A: 5 chains x 2 arms, non-inferiority at −5 points; about 185-200 USD expected at list price, 250 hard cap) | **sealed** (`510a5c6`, instrument `8341b6c`); Haiku smoke passed; to launch (08:05, ~11 h). Before launching: its row writer has no fsync (fixed on main in 0.3.2) — reseal with the fix or shadow-copy `row.json` |
| C3 | `redundant_page` under 1.14 with a cut bounded from below, on new cases | low | free (cases) + Jev (~0.03-0.05 USD) | open, from redundant-drop |
| A4 | Cells not run by decision (code on Sonnet and Opus, Fable, S2, Ne against Ne+A) | low (owner's decision) | Claude: see below | memory F2 **run**; the rest not run by decision |
| A3 | MCP tool calls pass the installed hook with no decision | medium | Jev 0.0805 USD | **done**: not confirmed; guard opt-in (`install --guard-mcp`) |
| B6 | Page triage and passages in Spanish | medium | Jev 2.6445 USD | **done**: both inconclusive at −5 |
| B4 | Order the approved paragraphs that do not fit by a four-level score | low-medium | Jev 0.0617 USD | **done**: Score not confirmed |
| B7 | A stable API of questions, thresholds and recording keys to import rather than copy | low | free | **done** (merge `a502293`) |
| A5 | `relate_facts`: the `unrelated` gate | low | Jev 0.0348 USD | **done**: 0.65 beats the shipped gate; the default since 0.3.2, after C4 |
| A6 | Getting an agent to use `find_in_repo` | low | free (ceiling) | **closed without spending**: ceiling 3.05 % |
| A7 | The derivation rule against Sonnet on unseen data | low | Claude + Jev | **closed**: no margin |
| A8 | Deciding before Claude Code's auto-mode classifier | low | Jev + Claude | **closed**: no lever in Claude Code |
| A9 | The tool window by tournament over the sub-groups of a large server | low | Jev | **closed**: no margin |
| A10 | A local classifier as one more provider (`LocalDecider`), trained on our own or public labels | low | free (Colab or Kaggle) | **measured** (free): on unseen suites AUC 0.655 against Jev's 0.814, "no concluyente" at −0.05; it does not transfer |
| A1 | Benchmarks read the TypeSafe key from a fixed path on the owner's disk | high | free | **done** (`de7c38a`) |
| A2 | Documents with an old state: README "What is open", the guard-struct README, the root `STATUS*.md` | medium | free | **done** (2026-10-15) |
| B2 | Spanish sentence splitting | medium | free | **done** (`872e068`) |
| B3 | `select_passages`: an unanswered paragraph, and a call budget per document | medium | free | **done** (`a1a04db`) |

## The 2026-10-16 lots

Each lot pre-registered and sealed before its first answer, reviewed against the code by
`revisor-prereg`, and run once from a detached worktree at the sealed commit. Jev is
`jev-1.13.0` unless the row says otherwise.

| Lot | Verdict by the sealed rule | Cost |
|---|---|---|
| [A3, the MCP guard over ATBench-Codex](results/2026-10-16-a3-mcp/README.md) | **Not confirmed**: recall 0.740 against the 0.752 floor (185 of 250 unsafe, the hook as shipped 0), FPR 0.328. 112 of the 589 MCP calls in safe trajectories denied (19.0 %). Amendment 1: the offline control flags the same 213 unsafe trajectories as on 2026-09-27, no drift | Jev 0.0805 USD |
| [memgate-hook, the installed memory hook with the long window](results/2026-10-16-memgate-hook/README.md) | **"Peor en ruido"**: hits +12.7 points [+6.3, +19.8] on 126 hittable requests, false alarms +3.7 [+1.5, +6.2] on 483, past the +5 guard. The hook stays short | Jev 0.1794 USD |
| [B4, order by a four-level Score](results/2026-10-16-b4-order/README.md) | **Score not confirmed**: +2.3 [−1.5, +6.2] over the free order, +1.8 [−2.3, +5.7] over tournament probability; free order over page order +13.6 [+7.1, +20.2], exploratory | Jev 0.0617 USD |
| [A5, `unrelated_at=0.65`](results/2026-10-16-a5-unrelated/README.md) | **Beats the shipped gate**: 39 added verdicts on 1,500 new pairs, all right, Wilson lower bound 0.910. A proposal, not the change | Jev 0.0348 USD |
| [B6, Spanish against English on MLQA](results/2026-10-16-b6-es/README.md) | **Both inconclusive at −5**: pages −3.4 [−6.1, −0.8] (95.5 % against 98.9 %), documents −5.9 [−9.0, −2.9] (85.8 % against 91.7 %), same share of text; BM25 loses 10-11 | Jev 2.6445 USD |
| [checkdone114, check_done under 1.14 on unseen AgentDojo stops](results/2026-10-16-checkdone114/README.md) | **Confirmed no worse**: 1.14 at 0.30 right on 745 of 950, 1.13 at 0.5 on 737, +0.8 [−1.1, +3.2]; false blocks 150 against 165 of 795 | Jev 0.1371 USD |
| [redundant-drop, `redundant_page` under 1.14 with 90 more drops](results/2026-10-16-redundant-drop/README.md) | **No proposal**: rule D clears at 0.04, the costly-drops guard fails (8 keep pages dropped against 0); 0.61 loses drops again, −6.0 [−11.6, −1.7] | Jev 0.0277 USD |
| [memory F2, memory against the handoff ritual](results/2026-10-16-memory-f2/README.md) | **Sonnet 5.5: S not worse than H and better than N0** (48, 44 and 4 of 48); **Opus 5.5 direction only** (22, 17, 21 of 24) | Claude 42.25 USD list |
| [memory W17, memory as it ships against clean Claude Code](results/2026-10-16-memory-w17/README.md) | **Sonnet 5.5: S' better than N0; no gana (cost)** (48 against 9 of 48, 1.19x [1.15, 1.24]); **Opus 5.5: not determined** (34 against 31 of 36, p 0.125; 0.999x [0.965, 1.055]) | Claude 32.50 USD list (about 39.7 with the discarded first Opus run) |
| [lb162x, the LongBench router against Opus 5.5](results/2026-10-16-lb162x/README.md) | **No worse at −10** against Opus 5.5 (−3.7 [−8.0, +0.6], "sustituye"); Opus's cost saved 29.5 % [21.7, 37.7]; Sonnet's saving measured, 33.9 % [24.0, 44.0] | Claude 27.01 USD list |
| [A6, the find ceiling](results/2026-10-16-a6-ceiling/README.md) | **Under 5 %**: 3.05 % [2.36, 3.78] of Sonnet 5.5's cost over 19 clean long-chain sessions; not pre-registered, free | free |

**Pending from these lots:**

- **The memory gate's long window is the library default** since `c65f021`:
  `memory_gate.gate` reads every memory whole in one call (`SANCHOPANZA_MEMORY_WINDOW=short`
  turns it off), on memgate-long's confirmation (recall 0.726 → 0.905 on 84 unseen LongMemEval
  questions). **The installed hook stays short**: memgate-hook found it "peor en ruido" on 905
  SWE-chat first requests, hits +12.7 [+6.3, +19.8] for false alarms +3.7 [+1.5, +6.2] over the
  +5 guard. `=long` stays an opt-in there.
- **check_done: confirmed (no worse) for 1.14 at 0.30 in the Stop hook**, +0.8 [−1.1, +3.2] on
  950 unseen AgentDojo stops. The limit it showed is a new open item (C2): both versions block
  about one finished stop in five (165 and 150 of 795) when tool results are cut at 1,500
  characters; 115 of 1.14's 150 false blocks have a cut result.
- **`redundant_page`: no proposal.** The 90 new `drop` cases let rule D clear, at 0.04, inside
  the `keep` pages' scores; the costly-drops guard fails. 0.61 loses drops for the third time
  (−6.0 [−11.6, −1.7]). Next (C3): a rule with a lower bound on the cut, on new cases.
- **LongBench: lb162x.** Against Opus 5.5 the router is "no worse" at −10 (−3.7 [−8.0, +0.6]),
  Opus's cost saved 29.5 % [21.7, 37.7]; Sonnet 5.5's saving is **measured at 33.9 %
  [24.0, 44.0]**. The routing point is in the package as an opt-in, `points.longdoc` (C7).

## Open

**C9. Memory's prune deleted the standing rules.** `context/episodes.py`'s prune deleted every
`*.json` in a project's store except `index.json`, `rules.json` and `adopted.json` included, so
a project idle for 30 days lost its standing rules, and load counted those files as records.
**Done** (merge `230a2aa`): pruning and loading match only record files.

**C10. Private names and local paths in public files.** Two names of other private projects and
some local paths remain in tracked benchmark code, tests and planning documents. **In part**:
every free file is clean, and the module docstring that named another project now says "an agent
with its own harness". The launchers take Python from the main checkout found by git's common
directory (the long and F2 ones accept SANCHOPANZA_PY first) and refuse with exit 2 when it is
missing; tests, history notes and scripts use `%USERPROFILE%`, `~` or paths relative to the
repository. `tests/test_no_private_names.py` refuses, in every tracked file (`.gz` fixtures
decompressed), a private name (kept as digests only) and any home folder in any spelling whose
user is not a stand-in (`someone`, `x`...); its allow-lists cannot go stale. Left for the owner,
on those explicit lists: 10 sealed files (preregs, sealed launchers and one module in a lot's
manifest) that write a home folder, 1 sealed recorded selection where a guarded word is a third
party's repository name, and 54 recorded run outputs (browse sessions and reports, one status
file, one launcher kept as it ran) that keep the folders the runs used.

**B1. A published release.** `v0.3.0` is tagged on `10f2cbe` with a
[GitHub release](https://github.com/romanpert/sanchopanza/releases/tag/v0.3.0) (wheel, sdist and
the CHANGELOG's 0.3.0 section). **`v0.3.1`** (2026-10-16) carries everything from 2026-10-16 and
is the first version the owner approved for PyPI; PyPI waits for the project's trusted
publisher on pypi.org (project `sanchopanza`, workflow `release.yml`, environment `pypi`). A tag push does not publish to PyPI: PyPI is a
separate `gh workflow run release.yml --ref <tag>` ([governance](governance.md)), with the
owner's yes. The consumer pinned one commit's tarball in three files that must move together;
it can move to `sanchopanza[jev]>=0.3.1`. A tag survives a history rewrite that would
stop an old SHA from resolving (the consumer's factory falls back to a null decider in silence
when the package does not import).

**C7. The LongBench routing point.** **Done** (merge `9705f25`): `points.longdoc`, opt-in and
out of `install`, gives Jev 1.14's letter when its top choice reaches 0.6, otherwise `escalate`
with the reason, never a silent answer; a test replays lb162's 162 recorded answers through it.
The 0.8 cut for Opus 5.5 users ran as **lbo8** (2026-10-16, sealed `2f232f1`, 9.24 USD): on
the 78 fresh QA tasks left, all under 100,000 characters, "no concluyente" at −5 (−6.4 points
[−14.1, −1.4]; Jev right on 20 of the 30 it covered, Opus on 25), 30.8 % [20.9, 41.4] of Opus's
cost saved ([lbo8](results/2026-10-16-lbo8/README.md)): no tighter claim, and the router is not
for documents under 100,000 characters as it stands. Free-text answers ran as the dev of
**longdoc-free** (2026-10-17, sealed `d8f266f`, ∞Bench En.QA, 41 questions on 8 novels, Sonnet
5.5 and Haiku 4.5 in clean Claude Code 2.1.287, Jev 1.13): the router of Jev's passages and gate
to Haiku cost 25 % more than Sonnet alone (saving −25.1 % [−36, −13]) for −0.6 F1
[−8.2, +7.9], and Jev's passages did not help Haiku (−0.5 [−10.2, +9.3] against the whole novel); by its
sealed rule no confirmation was sealed (541 questions needed, 310 left)
([longdoc-free](results/2026-10-16-longdoc-free/README.md)). Jev cost 0.039 USD a question on
these novels (its page tournament 0.037) against Sonnet's 0.069 in Claude Code; a free pre-filter
before the tournament is the open proposal.

**D1. OpenAI's Decisions API.** sanchopanza is a layer with one decision contract; Jev is the
provider every figure was measured with, and OpenAI's `/v1/decisions` (public beta since
2026-10-06, `gpt-6-luna`, 0.10 USD per million input tokens, nothing else) is a second hosted
one. **Adapter done** (`providers/openai_decisions.py`, `create("openai-decisions")`): written
against OpenAI's guide, tested on a mock of its examples, always behind a spending ledger every
process shares (0.50 USD in all by default) and the shared funds breaker on an out-of-quota
answer. **Measured once** (2026-10-16, sealed `2fc329b`, [D1](results/2026-10-16-openai-decisions/README.md)):
on the public benches it decided 200 of 244 rows right against Jev's 206, −2.5 points [−6.1, +1.2], "no concluyente" at −5, with better-calibrated yes/no answers, for 0.0143 USD. Next, if it is worth a second supplier: parity on the 1,437 component items (about 0.24
USD of OpenAI) and a threshold profile of its own; OpenAI spend is the owner's call.

**C1. A PostToolUse check on MCP results.** A3's misses are mostly harm that shows only in a
tool's answer (14 of 33 are `malicious_tool_execution`), which a PreToolUse guard never reads.
A check on the result cannot undo the call, but can stop the agent before it acts on it or
passes it on. **Built** (merge `c3313a3`, opt-in): `install --guard-mcp-post` asks the
`actions` question about a tool's result after the call, and `--guard-mcp-withhold` also
replaces the result. Its sealed development lot (W17, the same 500 ATBench-Codex trajectories,
jev-1.13.0, 0.062 USD) does not license a fresh-data confirmation: over the guard before the call
it caught 35 more of 250 unsafe trajectories and flagged 14 more of 250 safe ones, past its
+7-point bound. Next: a rule that clears on development data, then a fresh-data confirmation.

**C2. check_done with long tool outputs.** The record builder keeps the first 1,500 characters
of each tool result; workspace results run far longer, and the judge then sees an answer it
cannot check. Keep the part of each result the answer rests on, then measure again on the 950
stops (a new registration; about 0.3-0.5 USD of Jev at longer inputs) before the Stop hook is
advertised beyond slack-like settings.

**C8. Memory: four gaps, fixed in code; measured live on Sonnet 5.5 and Opus 5.5** (merge `e029489`; what
changed is in the CHANGELOG's 0.3.2). W17 ([memory-w17](results/2026-10-16-memory-w17/README.md), sealed `5d416fa`):
the default user-scope install kept the plan in 48 of 48 pairs against clean Claude Code's 9,
and with a bare "Let's continue." in 24 of 24 against 3, at 1.19x the cost [1.15, 1.24]: "S'
better than N0; no gana (cost)". On Opus 5.5 (repeated whole under the prereg's Amendment 1,
sealed `941c9a9`) it kept the plan in 34 of 36 pairs against 31 (3 to 0, p 0.125) at 0.999x the
cost [0.965, 1.055]: "not determined", since O1 needs the upper bound at 1.05; no gana. Post hoc,
after the data: on Opus the install's overhead shows in session 1, on the same work in both arms
(1.09x [1.06, 1.12]), so a cheaper first session is the candidate lever; "gana (coste)" asks for
the upper bound below 1.00, not the median (with this spread, a median of about 0.95).

Read from the code and from F2's logs, as they stood before the fix:
- A bare "continue" gets no prompt recall: the name gate passes a record only if the prompt
  names a file it changed (`harness/memory_recall.py`). In F2 the record came at the prompt in
  36 of 48 Sonnet arms and through the file touch in the other 12.
- With shell reads the record arrives after the first shell write: `SHELL_READS = False`, and
  `shell_first` exists but `install` wires no memory `PreToolUse`.
- A record keeps the prompt's first 1,000 characters (`REQUEST_CHARS`), so a plan at the end of
  a long prompt is lost.
- Plan sentences are stored as standing rules and crowd the 8-rule, 1,800-character slot
  (in F2's logs, a median of about 1,690 characters given at a session's start).

**C4. A5 on written text: done.** 1,500 written pairs of fa-17's three kinds (two dated events,
a role and an act, a figure and its subset) plus controls, sealed, jev-1.13.0, 0.035 USD: at
`unrelated_at=0.65` 66 added verdicts, all right, none a missed conflict, Wilson lower bound
0.945 ([C4](results/2026-10-16-c4-written/README.md)). `decide_facts`' default is 0.65 since 0.3.2; on the fourth
batch's recording `relate_facts` reads 39/43 when deciding (36/40 under the gate alone). Not
measured on jev-1.14.0.

**C5. The free order on fresh data: done via C5b** (2026-10-16, jev-1.13.0,
[C5b](results/2026-10-16-c5b-free/README.md)): on 348 of 646 fresh QASPER train questions that
overflow 3,400 characters, answer-sentence recall 78.3 % with the free order (`fit_score=False`)
against 61.9 % in page order, +16.4 points [+11.0, +21.9], at the same text; 1.371 USD. C5's own
sealed reading has no valid verdict (an instrument defect, [C5](results/2026-10-16-c5-free/README.md)).
The free order is a measured option for a caller that must cut at 3,400 characters on papers;
since 0.3.2 it is `select_passages`' default when `fit_chars` is set (`fit_score=False`; B4: the
Score over the free order +2.3 [−1.5, +6.2], not shown, and the free order costs no call;
`fit_chars` stays `None`). Open: other budgets and documents.

**C6. Spanish's 3-6 points.** Ideas: the question asked in its Spanish original against the
translated one, to tell the question's language from the text's; or the sentence stage's excerpt
taken by a window around its best match instead of a head cut at 900 characters (the gap is
smallest where the gold sits in the first 900: −4.5). About 0.2 USD of Jev per pages arm and
2.5 USD per documents arm.

**C3. `redundant_page` with a bounded cut.** A cut rule bounded from below (for example by the
highest `keep` score in calibration, or a precision target on `keep` pages), fixed before the
data, on cases not used in redundant-drop. Post hoc, a cut from 0.10 to 0.20 was right on 319 of
320 there, which licenses nothing.

**A4. Cells not run by decision** ([final scoreboard](results/2026-10-13-final/README.md), "What
was not run"). **Memory F2 ran** on 2026-10-16 (sealed `763dafd`, clean Claude Code 2.1.287):
on Sonnet 5.5, S was not worse than the handoff ritual and better than nothing (48 of 48 against
44 and 4; Tango lower bound +2.6 points; McNemar p 5.7e−14), at 0.92 [0.85, 0.95] the ritual's
cost and 1.23 [1.14, 1.26] the bare line's (paired medians, descriptive intervals): a substitute
for the ritual at lower cost, not a "gana" by the scoreboard's rule; on Opus 5.5 direction only (S 22, H 17, N0 21 of 24), no room,
since Opus's own auto memory carried the plan in every arm. 42.25 USD at list price. The gain
comes from carrying "what was next", not from a constraint saved. Still not run, by decision:
code on Sonnet 5.5 and Opus 5.5 (about 357 USD at list price, cap 465), Fable 5.1 (no suite),
the S2 confirmation (owner's decision after its dev), Ne against Ne+A (about 43 chains to see a
−7 %, [`PLAN-GANAR-H2H.md`](PLAN-GANAR-H2H.md)).

## Closed

**A6. Getting an agent to use `find_in_repo`: closed without spending.** The ceiling on what
imposing find could save, from recorded sessions ([a6-ceiling](results/2026-10-16-a6-ceiling/README.md)):
3.05 % [2.36, 3.78] of Sonnet 5.5's cost over 19 clean long-chain sessions and 1,046 bugs,
under the plan's 5 % rule. Sonnet reaches the right file in its first request on most bugs.
Opus 5.5 3.08 % on 2 sessions. Haiku 4.5 on single issues reads 4.81 % [3.59, 6.21], but most
of it is the session's first request (the system prompt's cache write), which find cannot
remove: counting requests 1 to i instead of 0 to i−1 gives 1.76 %. A fresh repository with a
frontier model is unmeasured.

**A7. The derivation rule against Sonnet: no margin.** A3 was not confirmed, and on
ATBench-Codex Jev already equals Sonnet 5 (78.5 % against 78.9 %,
[cascade-sonnet](results/2026-09-28-cascade-sonnet/README.md)). Closed until a set shows a gap.

**A8. Before the auto-mode classifier: no lever in Claude Code.** The classifier costs no money
there and a PreToolUse `allow` does not skip it ([`MAPA-HUECOS-ARNES.md`](MAPA-HUECOS-ARNES.md)
section 2). The version with a billed reviewer is Codex's, and that is the cascade.

**A9. The unit of the tool window: no margin.** The platform's own tool search already costs
less than the window at the same success (an estimated 0.34x of loading everything against the
window's 0.54x, [wide](results/2026-09-25-wide/README.md)).

**A10. A local classifier: one more provider, the owner's decision.** It plugs in as a
`LocalDecider` behind the same contract, in front of a hosted provider (`FallbackDecider`) or for
one point (`RoutedDecider`). Not for money, since it would replace Jev's micro-dollars a
decision; as an offline fallback, or to keep a point on the machine.
**Measured on check_done** (2026-10-16, sealed `ac61ad0`, free; [A10](results/2026-10-16-a10-local/README.md)):
a local check_done classifier trained only on AgentDojo's labels for 393 slack stops ranked checkdone114's 950 unseen stops at AUC 0.655 against Jev 1.14's 0.814, −0.159 [−0.272, −0.048], "no concluyente" at −0.05, catching 18 of 155 unfinished stops against 100. Level with Jev on its training suite, it loses most of its ranking on others: a
local provider needs labels from the setting it serves. TypeSafe's MCA 2.3(b) forbids training on
Jev's outputs and also "develop a similar or competing product". Train only on our own labels or
a public bench's, and measure outside the training set.

## Jev 1.14

Supported in the client since 2026-10-15 (merge `5694973`), with the default unchanged:

- `SANCHOPANZA_JEV_MODEL` picks the model; `DEFAULT_MODEL` stays `jev-1.13.0`
  (`src/sanchopanza/providers/jev.py`). The benches that pinned 1.13 by hand follow the variable.
- Long context and images send the Danger Zone headers, by argument or by
  `SANCHOPANZA_JEV_LONG_CONTEXT` / `SANCHOPANZA_JEV_IMAGES`; images go as refs plus a top-level
  assets map (`providers/jev_assets.py`, extra `sanchopanza[images]` for resizing), each side
  280 to 1568 px (`aa6fe79`).
- `Box` is a fourth question type, refused before any request on a version below 1.14.
- Recordings key the model from 1.14 on, and a 1.14 fixture has its own file
  (`fixtures/jev114/<name>`); every existing key is unchanged.
- `SpendLedger` and `CappedDecider`: a hard dollar cap shared by every process of a batch, each
  call reserved before it is made (`8c82dff`).
- The truncation limits are parameters (`limits.Limits` on `Squire(limits=)`), defaults
  unchanged (`dad1fb5`).

**What the 2026-10-15 lots found.** Both versions asked live the same day on the published
inputs, interleaved per item, each lot pre-registered and sealed before any 1.14 answer; Jev
only, 3.85 USD in all on the shared ledger, 0 USD of Claude (Claude answers are the earlier
recordings). One draw per version. The two confirmations the owner approved that evening ran on
ledgers of their own: memgate-long 0.53 USD of Jev, lb162 0.874 USD of Jev on the 162 tasks (0.875 with the smoke) and 5.757 USD of
Claude.

| Lot | Verdict by the sealed rule |
|---|---|
| [L1, component benches](results/2026-10-15-jev114-l1/README.md) | **No worse taken together**: 1,253 against 1,259 of 1,437 at the production thresholds (−0.42 points [−1.46, +0.70]), also at 0.5 and on macro AUC. Better Score calibration (ECE 0.152 → 0.109) and supersession (14 against 12 of 16 replaced rules, no false suppression). `redundant_page` worse at its 1.13 cut of 0.59 (107 against 115 of 125), with its ordering unchanged (AUC 0.997 → 0.995). Injection over the whole text: no gain over the window scan |
| [L2, check_done and the permission cascade](results/2026-10-15-jev114-l2/README.md) | **check_done worse at the 0.5 cut** (91.9 % against 94.0 %, Holm p 0.002): 1.14 calls more finished runs unfinished. **The cascade stays on 1.13**: R-Judge better (89.7 % against 87.4 %), Codex inconclusive at the cut (−1.6 points [−3.6, +0.4]); the Codex confirmation at tau 0.45 holds with 1.14 |
| [L3, label](results/2026-10-15-jev114-l3/README.md) | **No worse** on AG News, DBpedia-14 and SIB-200 in five languages outside English (every difference within ±1.3 points); no measurable extra gain outside English (+1.8 points [−0.3, +4.1]); the `classify` gate needs no recalibration |
| [L4, find_in_repo and candor](results/2026-10-15-jev114-l4/README.md) | **No improvement**: find any@1 50.4 % for both, any@5 −0.9 points, too few issues to show "no worse"; tau2 ranks a little better (AUC 0.549 → 0.581), still near chance. The holistic candor cut shifts: at 0.83, 1.14 flags 22 of 55 accepted errata answers against 8 |
| [L5, images](results/2026-10-15-jev114-l5/README.md) | **No vision mode** for `browse`: Box over the screenshot does not beat the text ranking (top 1 35.9 % against 42.3 %, inconclusive), and the screenshot leaves R@10 at 93.8 %. With images, 1.14 is no worse than 1.13. The real minimum side is 280 px, not the documented 256 (`MIN_SIDE` now 280) |
| [L6, long context](results/2026-10-15-jev114-l6/README.md) | **No substitute for a Claude call** at the registered cut: on LongBench v2 Jev is sure on 7 of 50 tasks, the ones Sonnet also gets right, saving 1.5 % of its cost. The long window lifts the memory gate's recall 0.723 → 0.908 on 36 LongMemEval questions, **on 1.13 too**: a gain of the window, not of the model. One-call QASPER triage still keeps half the paper |
| [Recalibration](results/2026-10-15-jev114-recal/README.md) | **A threshold profile per model** (`policy.MODEL_PROFILES`, used only when the model is `jev-1.14.0`), derived free on calibration splits: 1.14 with it reaches **parity** with 1.13 at its own cuts, 556 against 556 of 646 (0.0 [−1.5, +1.5]). check_done at 0.30 closes its gap; `redundant_page` is not fixed, and memory_write makes twice the costly stores |
| [Memory gate, long window](results/2026-10-15-memgate-long/README.md) | **Confirmed** on the 84 unseen LongMemEval questions, jev-1.13.0: recall 0.726 → 0.905, +17.8 points [+10.7, +25.7], Holm p < 0.001, no failures; the long window reaches BM25 top 3 (+8.9 [0.0, +17.3]) where the short one does not. 0.5283 USD |
| [Confirmation](results/2026-10-15-jev114-recalconf/README.md) | **Not admissible**: on a second draw of the same 1,298 cases the profile falls to 551 against 555 of 646 (−0.6 points [−2.3, +0.9], inconclusive) and `redundant_page` is worse (44 against 48 of 50); on 910 candor counterfactuals no cut had seen, 1.14 at 0.90 is worse than 1.13 at 0.83 (770 against 800, −3.3 points [−5.4, −1.2]). check_done at 0.30 holds. No new labelled cases exist for the L1 points, so they are confirmed only against draw-to-draw noise |
| [LongBench cut of 0.6, power](results/2026-10-15-jev114-b3conf/README.md) | No affordable confirmation can decide at a −2 point margin (about 3,200 paired tasks; LongBench v2 has 503). Deciding at −10 points takes 162 tasks with Sonnet on the covered ones: the owner's call |
| [LongBench cut of 0.6, 162 fresh tasks](results/2026-10-15-lb162/README.md) | **No worse at −10**: Jev 1.14 with the long window where its top choice is ≥ 0.6, Sonnet 5.5 (clean Claude Code 2.1.287) elsewhere, against Sonnet alone: +1.2 points [−3.1, +5.6]. Coverage 37 % (60 of 162, L6 had 54 %); on those Jev 31, Sonnet 29 right (McNemar p 0.79). 33.9 % [24.0, 44.0] of Sonnet's cost saved, measured on the 102 uncovered tasks by [lb162x](results/2026-10-16-lb162x/README.md). 0.874 USD of Jev on the 162 tasks (0.875 with the smoke), 5.757 of Claude |

**`DEFAULT_MODEL` stays `jev-1.13.0`**, and candor stays on 1.13. 1.14 is an opt-in with its profile
(`SANCHOPANZA_JEV_MODEL=jev-1.14.0`), better on calibration, supersession and R-Judge, and no
better where a switch would pay; the long-context gain is the window's and works on 1.13. Since
2026-10-16 the profile's check_done cut of 0.30 is confirmed on unseen trajectories
(checkdone114); its `redundant_page` cut of 0.61 is not fixed (redundant-drop).

## Done

- **A3** (2026-10-16, merge `2727cc3`): an MCP guard, opt-in (`install --guard-mcp`,
  `SANCHOPANZA_GUARD_MCP`; records masked by `redact.mask_strict`). Its sealed replay over
  ATBench-Codex is **not confirmed**: recall 0.74 against the 0.752 floor, FPR 0.328, and 19 % of
  MCP calls in safe sessions denied; the offline control shows no drift. Phase 2 (live) was not
  run. The next proposal is C1, its own lot.
- **B6** (2026-10-16, merge `bbde947`): Spanish against English on the same MLQA questions,
  **both inconclusive at −5**: pages −3.4 [−6.1, −0.8], documents −5.9 [−9.0, −2.9], at the same
  share of text; BM25 alone loses 10-11 points. For the consumer: asking in Spanish costs a few
  points of recall, not a different regime; its 900-character cut is a fixed loss of about 3
  points; its BM25 preselection past 90 paragraphs cost no measurable recall on 86 articles. On
  the way: `split_sentences` cuts through zero-width characters (`29c433b`), which Spanish
  Wikipedia writes after every footnote mark.
- **B4** (2026-10-16, merge `d07ee43`): `select_passages(fit_chars=, fit_score=)`, opt-in. The
  four-level Score is **not confirmed** over the free order (+2.3 [−1.5, +6.2]); the free order
  beats page order by +13.6 [+7.1, +20.2], exploratory. Next: C5.
- **B7** (merge `a502293`): versioned question ids in `sanchopanza.catalog` and an opt-in
  recording key from them (`keys="id"`); every text key and fixture unchanged. What remains: the
  harness points (the Claude Code hooks, candor, the context autopilot, browsing) have no ids
  yet, and an id key signs their text.
- **A5** (2026-10-16, merge `d07ee43`): `unrelated_at=0.65` **beats the shipped gate** (39 of 39
  added verdicts right, Wilson 0.910); with C4's 66 of 66 on written text, `decide_facts`'
  default since 0.3.2.
- **A4, memory F2** (2026-10-16, merge `780cf27`): see A4 above.
- **The memory gate's long window as the library default** (merge `c65f021`), with the static
  fallback said once, a 10 s deadline and `CachedDecider.with_long_context` (`62c8893`).
- **check_done under 1.14 at 0.30, confirmed** (2026-10-16, merge `0b60b01`).
- **lb162x** (2026-10-16, merge `a7612e5`): the LongBench router against Opus 5.5, and Sonnet's
  saving measured.
- **CI green again** (merges `0f00805`, `35896ea`, 2026-10-15): CI had failed on every push since
  2026-10-02 (an unpinned ruff, unformatted files, tests that needed this PC's venv, home cache or
  full git history). ruff is pinned in the `dev` extras, the tree is formatted, and the tests that
  need what a runner lacks skip and name it. All six cells pass (Linux and Windows, 3.11-3.13).
- **A1** (`de7c38a`, 2026-10-15): the benches take `TYPESAFE_API_KEY` from the environment, or
  from the `.env` file `SANCHOPANZA_KEYS_ENV` names, with no default file; the identifiers no
  longer carry another project's name ([`benchmarks/README.md`](../benchmarks/README.md)).
- **A2** (2026-10-15): the README's "What is open" says the candor lock is per session (`4fa334f`)
  and `unchanged_output` locks only on a contradiction with the record (v7, `1c7d2be`); the
  guard-struct README and the README's guard section give the live probe's result (`cb0062e`);
  the root `STATUS*.md` moved to [`docs/history/`](history/).
- **B2** (`872e068`, merge `ef41b6d`): a sentence break also comes before an accented capital,
  `¿`, `¡` or `«`, and not after a Spanish abbreviation; English splits as before (2 of 458,860
  strings change) and the published `select_passages` masks are unchanged.
- **B3** (`a1a04db`, merge `ef41b6d`): a paragraph the tournament did not answer is kept whole
  with no sentence call, and `max_calls` caps one document's calls, reserved before any await;
  the sentence stage gets what the tournament left, surest paragraphs first. Opt-in: default
  `None`.

## Already in sanchopanza, asked by the consumer

- `points/chunks.py` and `Thresholds.pages_in_context` (0.40) are committed (`policy.py`).
- A warning if Jev ever sends its own confidence on a Truth answer
  (`truth_wire_confidence_differs`, `providers/jev.py`).
- A pinned model, not an alias (`DEFAULT_MODEL = "jev-1.13.0"`).
- `allowed_kinds` / `denied_kinds` on the source kind (`points/triage.py`).
- A Jev balance of zero no longer fails open in silence (`funds.py`, `jev-preflight`).
- Content fetched through the shell is scanned with `--scan-content`; `Read` and `WebFetch` too.
- The candor lock per session, and `unchanged_output` v7.
- 50 cases per point and a blind second annotator on the six binary points; thresholds move to a
  precision target ([where it pays](where-it-pays.md) section 6, item 3).
- Attachments in the state: a text-only decider refuses them out loud (`providers/jev.py`).
- The guard split, probed live (`cb0062e`).
- Versioned question ids and an id recording key (`sanchopanza.catalog`, `keys="id"`; B7).
