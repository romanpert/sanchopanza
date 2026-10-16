# Results: which folder backs what

One directory per run, each with the report behind its figures. Nothing here is deleted when
it is superseded; this index says which folders carry the claims in the top-level README and
which are the record of how they were reached.

## Head to head: Claude Code alone against Claude Code + sanchopanza

The final scoreboard, per axis and model, and the runs behind each cell. One measured cell is a
win for sanchopanza: memory on Sonnet 5.5 across parallel sessions, with memory on (the install's
default since 2026-10-14). Web, code, long code's Jev part and early compaction on long code are
not.

| Folder | What it backs |
|---|---|
| [2026-10-13-final](2026-10-13-final/) | The scoreboard: web "no gana" on Sonnet 5.5 in three suites, code on Haiku 4.5 non-inferior with no saving, long code's Jev part "no gana", memory "gana" on Sonnet 5.5 across parallel sessions and "sin margen" on Opus 5.5 and in two of three Sonnet families; what was not run, and why |
| [2026-10-05-h2h-gaia](2026-10-05-h2h-gaia/README-conf.md) | GAIA validation, Sonnet 5.5: +3.8 points [-1.5, +9.9], cost 1.074 [0.908, 1.255], wall 1.39: no gana |
| [2026-10-06-h2h-bcp](2026-10-06-h2h-bcp/README-conf.md) | BrowseComp-Plus, Sonnet 5.5: +7.8 points (p 0.092), cost 1.17 [1.007, 1.356]: no gana |
| [2026-10-06-h2h-longdoc](2026-10-06-h2h-longdoc/README-conf.md) | LongBench v2, Sonnet 5.5: -6 points [-18, +6], cost 0.785 [0.634, 1.008]: no gana |
| [2026-10-06-h2h-conf](2026-10-06-h2h-conf/) | The sealed prereg and verdict rule of those three |
| [2026-10-07-h2h-ne](2026-10-07-h2h-ne/) | The compaction window alone (a Claude Code setting) matches the whole line on BrowseComp-Plus: 7 right against 6, cost 0.954 [0.80, 1.15] |
| [2026-10-07-h2h-s2](2026-10-07-h2h-s2/) | S2, the line without the parts that did not act (dev): cheaper than S0, not than N |
| [2026-10-06-h2h-s1](2026-10-06-h2h-s1/), [2026-10-07-h2h-d](2026-10-07-h2h-d/), [2026-10-07-h2h-e](2026-10-07-h2h-e/) | The knowledge line's dev, and two levers closed without a gain (checking the returned document, a stricter check-done) |
| [2026-10-03-adopt-d](2026-10-03-adopt-d/results.md) | SWE-bench Verified, Haiku 4.5, 78 pairs: success non-inferior (46 against 45), cost 1.007 [0.933, 1.143], the 10 % cost bound not shown; both arms loaded the owner's setup |
| [2026-10-07-pilot-a](2026-10-07-pilot-a/) | Passages on arrival on two 60-bug chains, Sonnet 5.5; its edge did not hold on a repeat (`docs/PLAN-GANAR-H2H.md`, `docs/history/STATUS-launch.md`) |
| [2026-10-05-memory-frontier](2026-10-05-memory-frontier/gate-result.md) | The memory headroom gate: no room on Opus 5.5 (1 break in 24), one Sonnet 5.5 cell opens (parallel session) |
| [2026-10-13-memory-cell](2026-10-13-memory-cell/README.md) | The open memory cell, Sonnet 5.5, a fact said in a parallel session or sibling worktree, 24 pairs, pre-registered: S broke 0 facts against N's 11 (McNemar p 0.00049; by scene 4 wins, 0 losses), task 23 vs 24, cost 1.117 [1.05, 1.15], wall 1.12: **gana**. S is the default install plus `--memory`; 8.47 USD |
| [2026-10-13-long-compact](2026-10-13-long-compact/README.md) | Early compaction near 67k (what `install --context-budget 67000` writes) against N-early near 160k, Sonnet 5.5, 5 long60 chains, k = 1, pre-registered: cost 0.900 [0.741, 1.093], quality −1.4 points (non-inferior at −10), wall 1.09: **no gana**, no saving shown (0.858 [0.748, 0.984] if a call cut by a PC reboot is metered rather than charged at its cap, a sensitivity the sealed rule does not use) (under the post-data amendment: conan-2 repeated at 0.952, still no gana: R1 0.875 [0.754, 1.015], R2 0.887 [0.750, 1.050]). 173.11 + 33.69 USD |

## Jev 1.14

`jev-1.14.0` against `jev-1.13.0`, both asked on 2026-10-15 on the published inputs; the default
stays `jev-1.13.0`.

| Folder | What it backs |
|---|---|
| [2026-10-15-jev114-l1](2026-10-15-jev114-l1/README.md) | Every component bench (public, fifty, collision, steerability, AgentDojo, supersession, the rest of `benches/`), pre-registered: 1.14 **no peor** on 1,437 items with the production thresholds (−0.42 points [−1.46, +0.70]), at 0.5 (−0.23 [−1.14, +0.68]) and on macro AUC (−0.0014): the phase-2 gate passes. Score ECE 0.152 → 0.109, supersession 12 → 14 of 16; `redundant_page` loses 8 of 125 at the 0.59 cut set on 1.13 with its ordering unchanged (recalibrate before switching). Injection over the whole text: same 21/23 as the window scan, no model effect. 0.1005 USD |
| [2026-10-15-jev114-l2](2026-10-15-jev114-l2/) | check_done and the permission cascade, Claude answers replayed: check_done worse at the 0.5 cut (91.9 % against 94.0 %, AUC 0.970 against 0.982), recalibrate before moving; R-Judge better (89.7 % against 87.4 %), Codex inconclusive, cascade stays on 1.13; R-Judge against Opus 5 at 43.9 % of its cost with 1.14 (65.7 % with 1.13 today), split noise at a 31 % median for both; the Codex confirmation at tau 0.45 holds with 1.14 (37.7 %). 0.173 USD of Jev |
| [2026-10-15-jev114-l3](2026-10-15-jev114-l3/) | The label rubric of 2026-09-30, `jev-1.14.0` against `jev-1.13.0`, 1,000 items each of AG News and DBpedia-14 plus SIB-200 in five languages besides English (`prereg.md`). Argmax accuracy: 88.7 % against 88.8 %, 98.6 % against 98.5 %, and 88.9 % against 89.1 % outside English. Every difference is within ±1.3 points: **no peor** on all three. No measurable extra gain outside English (+1.8 points [-0.3, +4.1]). Coverage at the `classify` gate does not move, so no recalibration. 0.151 USD of Jev |
| [2026-10-15-jev114-l4](2026-10-15-jev114-l4/README.md) | find_in_repo on 117 SWE-bench Verified issues and candor/`check_done` on tau2 (320) and errata (110), pre-registered, nine paired comparisons: find any@1 identical (50.4 % both, 3 won 3 lost) and any@5 −0.9 points [−4.3, +1.7], "no concluyente" under the −2 rule at this n; tau2 AUC **mejora** +0.032 (0.549 → 0.581, Holm p 0.002) but accuracy at 0.5 −1.6 [−4.7, +1.3]; errata AUC −0.043 [−0.098, +0.010], and the 0.83 cut flags 22/55 accepted answers on 1.14 against 8 (recalibrate before switching). Every 2026-09-29 verdict stands. MALT and the counterfactuals not run (budget). 0.5479 USD |
| [2026-10-15-jev114-l5](2026-10-15-jev114-l5/README.md) | Vision on Multimodal-Mind2Web's browse steps, pre-registered: Box over the screenshot (1.14 only) picks the next element in 35.9 % of 142 steps against 42.3 % for 1.13's text ranking (−6.3 points [−16.2, +2.8], no concluyente); a zoomed second Box 43.0 %, Box among the text's top 10 42.3 %. The ranking with the page's band in the state, 48 steps: R@10 93.8 % with and without the image (image effect 0 [−6.3, +6.3]), R@1 62.5 % against 54.2 % (n.s.), 27 % dearer; 1.14 against 1.13 with the image **no peor** (+4.2 [0, +10.4]). Vision mode not recommended by the sealed rule. Jev refuses an image side under about 280 px (documented 256). 1.199 USD |
| [2026-10-15-jev114-l6](2026-10-15-jev114-l6/README.md) | The long-context window, 1.14 against 1.13 crossed with the shipped cut (S) against the whole document with the Danger Zone header (L), pre-registered. **B3** LongBench v2, Jev alone against Sonnet 5.5's recorded 31/50: Jev answers 21-22/50 with the whole document (18-20 at 100k characters); at the registered 0.9 cut it covers 7/50 (14 %) at 6/7 right, the same 6 Sonnet got, saving 1.5 % of Sonnet's cost: **no sustituye** in every cell (post hoc, at 0.6 the hybrid tied Sonnet at 43 % of its cost; to confirm). **A6** QASPER, every paragraph in one call: all evidence 97.0 % (1.13) and 95.3 % (1.14) but 51-53 % of the text, P28 fails in every cell; 1.14 keeps 1.6 points less text (mejora). **A7** memory gate on 36 LongMemEval questions: whole sessions lift recall 0.72 → 0.91 on both models (**mejora**, +18.5 [+5.7, +32.8]), 3.1 points under BM25 top 3 (0.94) with fewer characters; no model effect. Every gain is the window's, available on 1.13. 1.4822 USD |
| [2026-10-15-jev114-recal](2026-10-15-jev114-recal/README.md) | A threshold profile for 1.14, recalibrated free on the L1, L2 and L4 recordings, pre-registered: each cut re-derived by its own rule (90 %/80 % precision derivations, or 1.13's action rate transferred) on a calibration part, judged on a held-out one. With it, 1.14 is **no peor** than 1.13 at 1.13's cuts: 556 against 556 of 646 (0.0 [−1.5, +1.5]), five points no peor, three no concluyente, none peor. check_done 0.5 → 0.30 closes its gap (312 against 313 of 329, false blocks 8 against 7); `redundant_page` is not fixed (0.61, 45 against 47 of 50: one disputed page blocks the 90 % derivation). Profile in `policy.MODEL_PROFILES`, used only when the model is `jev-1.14.0`; `DEFAULT_MODEL` stays 1.13 until a confirmation on unseen cases (about 0.4 USD of Jev). 0 USD |
| [2026-10-15-jev114-b3conf](2026-10-15-jev114-b3conf/README.md) | The confirmation L6 proposed for its post hoc B3 cut (Jev 1.14 L alone where sure at 0.6, Sonnet elsewhere: 31/50, tie with Sonnet at 43 % of its cost), costed before paying and **not run**: resampled from L6's answers, 50 fresh LongBench v2 tasks with Jev alone reach a verdict under the −2-point rule 4 % of the time (CI ±12; Sonnet's per-task answers are unknown on fresh tasks, so the hybrid is read against its mean 31/50), with Sonnet paired 8 %, and all 162 fresh eligible tasks 10 %; the rule needs about 3,200 paired tasks at a true tie, more than LongBench v2 holds. The tie rests on 8 covered tasks split 4-4, and 0.6 fails L6's 90 % precision condition by construction. Deciding more often than not needs the 162 tasks, Sonnet on the covered ones and a −10-point margin set beforehand: about 0.8 USD of Jev and 12 of Claude. The hypothesis stays open. 0 USD |
| [2026-10-15-jev114-recalconf](2026-10-15-jev114-recalconf/README.md) | The confirmation the recalibration asked for, pre-registered, both versions live: the 1.14 profile **does not hold**, so the `DEFAULT_MODEL` switch is "no admisible" and 1.13 stays. A second draw of its 1,298 cases: 551 against 555 of the 646 evaluation items (−0.6 points [−2.3, +0.9], no concluyente; the first draw gave 556 against 556), `redundant_page` **peor** at 0.61 (44 against 48 of 50), check_done holds at 0.30 (310 against 311); 1.14 flips 1.8 % of its decisions between draws, 1.13 0.8 %. On the 910 candor counterfactuals of rounds 2-5, which no cut had seen: holistic 1.14 at 0.90 **peor**, 770 against 800 (−3.3 [−5.4, −1.2] by session), catching 77.7 % of misstatements against 82.3 % with more false flags (3.8 % against 2.6 %), AUC 0.958 against 0.972. New labelled cases for the six L1 points not run: none exist with the same definition. 0.1976 USD of Jev |
| [2026-10-15-memgate-long](2026-10-15-memgate-long/README.md) | The confirmation L6's A7 asked for, jev-1.13.0 only, pre-registered: on the 84 LongMemEval test questions L6 did not reach, the memory gate (`memory_gate.gate`) reading every session whole in one call lifts selection recall from 0.726 to 0.905 (+17.8 points [+10.7, +25.7]): **confirmado**. Against BM25 top 3 (0.815 here) the long gate is +8.9 [0.0, +17.3], **alcanza** (not "bate": the lower bound is 0); the shipped short gate does not (−8.9). It selects 32.9k characters against 20.8k at precision 0.71 against 0.91, about 0.005 USD a prompt against 0.001; 0 failures. Pooled with L6's 36 (descriptive): 0.725 → 0.905. 0.5283 USD of Jev |
| [2026-10-15-lb162](2026-10-15-lb162/README.md) | The confirmation b3conf costed, pre-registered and run: Jev 1.14 with the long window answering alone where its top choice is >= 0.6, Sonnet 5.5 (clean Claude Code 2.1.287) elsewhere, on the 162 fresh LongBench v2 tasks at a -10-point margin. Coverage 37 % (60 of 162); on them Jev 31 right, Sonnet 29 (McNemar 8 against 6, p 0.79); hybrid minus Sonnet **+1.2 points [-3.1, +5.6]**: **no peor**, and with coverage >= 20 % the product claim **sustituye** for long-document multiple-choice questions (not a general Sonnet substitute; at a -2 margin it would not decide). Saving of Sonnet's cost about 27 %, an estimate (Sonnet not asked on the 102 uncovered tasks). 0.875 USD of Jev, 5.757 of Claude |
| [2026-10-16-lb162x](2026-10-16-lb162x/README.md) | lb162's router with the expensive model run wherever lb162 had not, pre-registered, Jev's lb162 answers reused (no Jev call); Opus 5.5 and Sonnet 5.5 in clean Claude Code 2.1.287. Against **Opus 5.5** alone on the 162: hybrid minus Opus **-3.7 points [-8.0, +0.6]**, **no peor** at -10, claim **sustituye** (coverage 37 %), but Opus beats Jev on the covered tasks (37 against 31 of 60, McNemar 10 against 4, p 0.18) and only the -10 margin decides; Opus's cost saved **29.5 % [21.7, 37.7]**. The saving of **Sonnet 5.5**'s cost, measured: **33.9 % [24.0, 44.0]** (lb162's 26.7 % estimate inside). Alone on all 162: Opus 105 right, Sonnet 89 (p 0.011), Opus at 1.26 x Sonnet's cost. 27.01 USD of Claude |

## Main evidence

The runs behind the README's headline numbers.

| Folder | What it backs |
|---|---|
| [2026-09-21-public](2026-09-21-public/) | The public benches (core, safety, graph) replayed from their recording; paper Section 5.9 |
| [2026-09-27-memory-write-cut](2026-09-27-memory-write-cut/) | The `memory_write` cut derived to a precision target, and the substitution against Opus 5: 131x cheaper, 10.9x faster, 2 decisions less accurate |
| [2026-09-28-claude-code-broad](2026-09-28-claude-code-broad/) | The guard inside Claude Code: destructive commands stopped 16 of 16, 0 false alarms in 93 events |
| [2026-09-24-agentdojo](2026-09-24-agentdojo/) | Injection detection on AgentDojo's attacks: 0 false alarms on 149 real tool outputs |
| [2026-09-25-window](2026-09-25-window/) | The tool window and the injection scan that keeps it from widening on planted text |
| [2026-09-25-completion](2026-09-25-completion/) | Checking the agent's own "done": 52 % believed, 94 % with one calibrated question |
| [2026-09-25-triage](2026-09-25-triage/) | Page triage on multi-part questions: the contribution question keeps both pages in 93.3 % |
| [2026-09-27-chunks](2026-09-27-chunks/) | Pages judged in each other's context, then sentences: 98.3 % at 34 % of the text |
| [2026-09-27-hierarchy](2026-09-27-hierarchy/) | The tournament over 100 pages: 96.5 % at 3.1 % of the text in 5 calls |
| [2026-09-27-answers](2026-09-27-answers/) | The kept text answers as well as all of it; the first, free-length run was negative |
| [2026-09-28-fixed-pages](2026-09-28-fixed-pages/) | Keeping documents out of one answering call: 9 of 9 answers at 79.5 % fewer input tokens |
| [2026-09-28-lateral-wholedocs](2026-09-28-lateral-wholedocs/) | One long document: every answer sentence in 87.2 % at 21.0 % of the text (`select_passages`) |
| [2026-09-27-cascade-frontier](2026-09-27-cascade-frontier/) | The Jev-then-Opus permission cascade, confirmed on unseen ATBench-Codex data |
| [2026-09-28-cascade-sonnet](2026-09-28-cascade-sonnet/) | The same cascade against Sonnet 5: partial, over the cost bar on R-Judge |
| [2026-09-29-candor](2026-09-29-candor/) | Say/do checking, confirmation round (`prereg-2.md`). The status-block lock stopped 96 % of misstated reports and 0 of 111 honest sessions; real misreports 9/12, below its registered 80 %. Jev as a second opinion reached AUC 0.98 against Haiku 4.5's 0.68 |
| [2026-09-29-candor](2026-09-29-candor/) (round 4) | v4 on 94 new sessions (`prereg-4.md`), 3 of 4 hypotheses hold: 105/105 misstatements, 1/61 honest sessions, round-3 kinds 6/8 on new sessions; the new kinds 3/7 (G3 fails), a check that could not run 0/4 |
| [2026-09-29-find](2026-09-29-find/) | Repository search on 117 SWE-bench Verified issues (`prereg.md`), 3 of 3 hypotheses hold: a gold file first in 51.3 % and in the top five in 65.0 %, against 13.7 % and 35.0 % for whole-file BM25, at 0.0016 USD per issue |
| [2026-09-29-context-guard](2026-09-29-context-guard/) | The compaction guard next to Claude Code's summary (`prereg.md`, A2-A3; Haiku 4.5, 7 tasks whose facts could reach the model): 2/7 finished with the summary alone, 5/7 with the free rule, 6/7 with the decider cascade (McNemar p = 0.375); H3 fails on a re-readable control. Offline, the cascade kept every needed value in 28/28 on four conditions where BM25 fell to 0/28 once values were reworded; the first decider questions had read ~95 characters of the request |
| [2026-09-29-candor](2026-09-29-candor/) (round 3) | v3 on 176 new sessions (`prereg-3.md`), 5 of 7 hypotheses hold: 95.3 % of misstated reports stopped, 0 of 126 honest sessions, Jev AUC 0.973 against Haiku's 0.666 |
| [2026-09-29-candor](2026-09-29-candor/) (round 5) | v6 on four new tasks (`prereg-5.md`), 4 of 6 hypotheses hold: 0/39 honest sessions and 62/63 misstatements locked; the review tier caught 23 of 29 real misreports. K3 (U1 lock 4/6) and K4 (review 6/11) fail |
| [2026-09-30-candor-inputs](2026-09-30-candor-inputs/) | v6 on held-out SWE-chat (`prereg-inputs.md`): 32 `substituted_input` flags against v5's 721, locks on 1.8 % of turns against 18 % (O1 holds); no real substitution among 200 read, so O2 has no verdict and O3 fails |
| [2026-09-30-opus55-substitution](2026-09-30-opus55-substitution/) | The 211 substitution judgments against Claude Opus 5.5: a tie (200 against 199) at about 99x less per judgment |
| [2026-09-30-label](2026-09-30-label/) | A closed rubric over two public sets (`prereg.md`): Jev 89.3 % (AG News) and 98.0 % (DBpedia-14) against Haiku 4.5's 83.0 % and 98.0 % at 1/70 to 1/95 of its cost; the margin p1 - p2 adds nothing over p1 |
| [2026-09-30-browse](2026-09-30-browse/) | The next element on a Mind2Web page: first design failed (R@10 71.0 %, `prereg.md`), the mixed rounds confirmed on 142 new steps (`prereg-confirm.md`): R@20 89.4 %, R@10 82.4 %, BM25 38.7 % and 23.2 % |

## The negatives the README reports with the same weight

| Folder | What did not pay |
|---|---|
| [2026-09-24-agentdojo-e2e](2026-09-24-agentdojo-e2e/) | In front of a model that already refuses, the injection guard buys nothing |
| [2026-09-25-e2e](2026-09-25-e2e/) | The tool window with a real agent: no detectable difference in success where tool search exists |
| [2026-09-25-cache](2026-09-25-cache/) | The cost basis of those end-to-end comparisons: where the cache breakpoint sits decides the ratios |
| [2026-09-25-wide](2026-09-25-wide/) | Against a real 398-tool MCP catalog, the platform's search is cheaper than the window |
| [2026-09-24-fixed-sequence](2026-09-24-fixed-sequence/) | Judging each document alone (`triage_page`) lost 4 answers in 10 |
| [2026-09-27-longdocs](2026-09-27-longdocs/) | The tournament on whole papers missed the registered 25 % of the text |
| [2026-09-25-cascade](2026-09-25-cascade/) | The registered cascade rule on R-Judge reached Opus at 57 % of its cost, over the 50 % bar |
| [2026-09-29-candor](2026-09-29-candor/) (round 1) | The registered say/do round: 5 of 8 hypotheses failed. The critical-only lock missed most misstatements, and the per-sentence Jev judge added nothing (5.2 %). One of 6 lock sessions let a parallel call through before the lock engaged |
| [2026-09-29-candor](2026-09-29-candor/) (round 3) | Real misreports whose falsehood lies outside the record (a silent failure, a truncated archive, a suite that does not exist): the lock stopped 0 of 22. 4 of 126 paraphrases locked (D1 fails at 3.2 %). A ledger defect lost actions under parallel hooks; fixed |
| [2026-09-29-candor-external](2026-09-29-candor-external/) | On public data, 7 of 10 registered hypotheses fail. errata-bench (real Claude Code sessions, no status block): no real misreport locked, holistic Jev AUC 0.56. MALT: candor's question near chance on reward hacking (0.62) and sandbagging (0.56). tau2-bench: `check_done` below trusting the agent (54 % against 67 %) |
| [2026-09-28-lateral-screen-confirm](2026-09-28-lateral-screen-confirm/) | The BM25 screen did not replicate on fresh questions and was retired |
| [2026-09-28-context-lean](2026-09-28-context-lean/) | This iteration's main negative. Inside Claude Code, with auto-compaction firing mid-task (Haiku 4.5, 7 tasks, pre-registered): native summary 5/7, lean masking 3/7, clearing without an archive 0/6; masking used more input tokens (10.46M against 8.73M) at the same dollars; the agent never called `search_archive`. Offline, index stubs held a needed token for 12.0 % of needed masked results (bar 50 %). Sonnet 5 (partial, spend gate): masking thrashed, five compactions and 2.04 USD on one task |
| [2026-09-28-context](2026-09-28-context/) | Asking a decider what the rest of a coding session will need is at chance (AUC 0.53-0.61); the arrival cut saved 3.7 % and did not beat head+tail; recall with the decider matched BM25 top 3 |
| [2026-09-28-memory-gate](2026-09-28-memory-gate/) | A decider gate over memory files missed its recall criteria against BM25 top 3 on LongMemEval; at equal text, not distinguishable from BM25 over sentences |
| [2026-09-30-find-e2e](2026-09-30-find-e2e/) | `find_in_repo` offered to a Haiku agent on 27 SWE-bench issues (`prereg-find-e2e.md`): called in 6 of 27 sessions; first-file hits 17 against 16, same cost (E1 and E2 fail, E3 holds) |
| [2026-09-30-clm-cpu](2026-09-30-clm-cpu/) | CLM-8B zero-shot on a CPU encoder against Jev on the benches: runs end to end, agrees far less (injection 12/28 against 27/28) and does not separate the classes |
| [2026-09-30-own-harness-scene](2026-09-30-own-harness-scene/) | A real fix in an agent with its own harness, three sessions a side (`prereg-scene.md`): same cost, solo 3/3 against 2/3; candor caught one false read claim and raised two locks on a false reason, one of them on a correct fix; its lock is one file per machine |
| [2026-09-30-browse](2026-09-30-browse/) | Reading less while browsing (`prereg-confirm.md` Phase 2c, `prereg-e2e.md`): Sonnet 5 from Jev's top 20 elements 53.3 % against 58.3 % from the whole page, -5 points [-15, +5], under the bar; a snapshot-pruning hook in 36 real Claude Code sessions with playwright-cli, +0.0095 USD a session [-0.006, +0.027], no saving |

## Corrected: headline invalid

| Folder | What happened |
|---|---|
| [2026-09-28-context-e2e](2026-09-28-context-e2e/) | Its headline, the autopilot 12 of 12 against 6 of 12 for `/compact` (p = 0.014), is **retracted**: under `claude -p --resume` the compaction hook returned the engine's `handle`, so the second phase saw the unmasked history. It compared "no compaction, plus recall" against the native summary. Correction at the top of its README; measured again in 2026-09-28-context-lean |

## Supporting runs and history

Earlier batches, intermediate runs and runs superseded by a later folder. Their numbers are
correct for their sitting; where a later folder replaces a figure, the later one is quoted.

| Folder | What it is |
|---|---|
| [2026-09-24-new-points](2026-09-24-new-points/) | First recording of the eight 0.2.0 points, under the policy of that day (superseded by the replay in paper 5.10) |
| [2026-09-24-fifty](2026-09-24-fifty/) | Fifty cases per binary point and a second annotator |
| [2026-09-24-fifty-v2](2026-09-24-fifty-v2/) | The same fifty-case judgments made two ways (substitution, first version) |
| [2026-09-24-third-batch](2026-09-24-third-batch/) | `memory_write` and `redundant_page` to 100 and 125 cases; a widened gate measured and not shipped |
| [2026-09-24-after-fix](2026-09-24-after-fix/) | The widened `specific` gate, measured and not shipped |
| [2026-09-24-fourth-batch](2026-09-24-fourth-batch/) | `facts`, `edge` and `memory_collision` to 50 cases each |
| [2026-09-24-edge-fix](2026-09-24-edge-fix/) | `edge` with the direction gate read first (intermediate) |
| [2026-09-24-collision](2026-09-24-collision/) | `memory_collision` as two binary questions |
| [2026-09-24-steerability](2026-09-24-steerability/) | Changing the criterion at query time: what moved and what did not |
| [2026-09-24-effort](2026-09-24-effort/) | What more thinking buys a generative judge on closed-vocabulary judgments |
| [2026-09-24-genrm](2026-09-24-genrm/) | A generative verifier as a control on compositional judgments |
| [2026-09-24-tools](2026-09-24-tools/) | The first tool selector and its two failure modes (superseded by the window) |
| [2026-09-24-agentdojo-haiku](2026-09-24-agentdojo-haiku/) | Raw AgentDojo runs with Haiku, kept for the record; no report of its own |
| [2026-09-25-order](2026-09-25-order/) | Option-order sensitivity of a Choice |
| [2026-09-25-pending](2026-09-25-pending/) | Two cheap pending items of 2026-09-25 |
| [2026-09-25-policy-shape](2026-09-25-policy-shape/) | How much of the policy-model gap the policy's shape explains |
| [2026-09-25-push](2026-09-25-push/) | Pushing tools to Sonnet 5 without `tool_addition`: the channel works, the timing does not |
| [2026-09-27-edge-facts](2026-09-27-edge-facts/) | The errors of `verify_edge` and `relate_facts`, and the fifth batch that settled the direction question |
| [2026-09-28-claude-code-harness](2026-09-28-claude-code-harness/) | The first Claude Code end-to-end run, installed as a user would (superseded by claude-code-broad) |
| [2026-09-28-hook-startup](2026-09-28-hook-startup/) | The hook's start-up time before and after lazy imports |
| [2026-09-28-lateral-screen](2026-09-28-lateral-screen/) | The BM25 screen's first, unconfirmed match (see the confirmation above) |
| [2026-09-28-lateral-memo](2026-09-28-lateral-memo/) | Remembering tournament groups: same pages, fewer calls |

Bench rows about pseudonymized persons were hardened on 2026-09-28 and their recordings asked
again; the folders whose figures moved say so in their own README or summary.
