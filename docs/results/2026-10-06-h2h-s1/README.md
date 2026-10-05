# h2h dev of S1 (S0 with `--knowledge`) on GAIA, BrowseComp-Plus and LongBench v2

A development run on Sonnet 5.5 of the line S1 against Claude Code alone (N) and against S0, on
the dev tasks the earlier dev phases used: the 20 GAIA ids of `gaia-dev-ids.txt`, the 10 of
`bcp-dev-ids.txt` and the 10 of `longdoc-dev-ids.txt`. One run, arms interleaved within each
task where they ran in the same phase. **It is not a confirmation and sets no threshold.** Only
task ids, counts and costs are written here; no question, answer or document text.

## The lines

- **S0** is `benchmarks/h2h/s_install.json` (unsealed): guard (coding profile), context budget
  160,000, memory, candor, find with find-auto, the skill, content scanning, check-done, crawl,
  prune, fetch, Jev as provider, and the crawl, fetch and guard variables.
- **S1** is `benchmarks/h2h/s1_install.json`: S0 with `--knowledge` and without `--fetch`. With
  both flags the install (main 5da2635) wires only the knowledge hook and server: a dry run of the
  whole line with and without `--fetch` wrote identical settings, one PreToolUse hook that
  redirects WebFetch (knowledge's) and no fetch server. `--content-tools` goes too: with
  `--knowledge` the install already scans WebFetch, WebSearch and the three knowledge tools.
  `SANCHOPANZA_FETCH_VERSION` goes: only the fetch server read it, and knowledge sets it itself.
- **N** is the clean user of every h2h phase.

In BrowseComp-Plus and LongBench both arms work offline (`local_hook.py`): knowledge's `search`
is denied there (it is a web search by another name), and `read` and `pick` only reach files in
the session's folder.

## Where each arm comes from

| suite | N | S0 | S1 |
|---|---|---|---|
| GAIA | `dev-s1`, CC, interleaved with S1 | `dev-s0` (this run) | `dev-s1`, SP |
| BrowseComp-Plus | `bcp-dev`, CC (reused) | `bcp-dev`, SP | `bcp-dev-s1` |
| LongBench v2 | `longdoc-dev`, CC (reused) | `longdoc-dev`, SP | `longdoc-dev-s1` |

The offline suites reuse N and S0 from their dev phase of 2026-10-05, run with the same N set-up.
GAIA runs N again: the GAIA dev of 2026-10-05 ran before the permission mode was set explicitly
in both arms, and its S was the default install, not S0, so neither of its arms is comparable.

**Valid sessions.** The TypeSafe account ran out of credit at 21:52 UTC: from then on Jev answered
HTTP 402 and S failed open. Four GAIA S sessions had a 402 and are marked `invalid` in the private
rows and left out (S1 `7673d772`; S0 `33d8ea3b`, `7673d772`, `e142056d`); GAIA stopped there, after
12 of its 20 tasks. Every BrowseComp-Plus and LongBench session finished before 21:52 with no Jev
error. The tables below take the tasks every arm has valid: **GAIA 10, BrowseComp-Plus 10,
LongBench 10.** S1 against N alone has 11 valid GAIA tasks (S1 10/11, N 9/11, the same single
discordant task).

## Results

Grades: GAIA's official scorer (no session was flagged for a hand review); BrowseComp-Plus exact
match, else the judge (Haiku 4.5, official template), with hand verdicts first; LongBench the
letter. "Right" is official / final.

### GAIA (10 tasks)

| | N | S0 | S1 |
|---|---|---|---|
| right | 8 / 8 | 8 / 8 | 9 / 9 |
| cost total, mean / median USD | 1.09, 0.109 / 0.069 | 1.33, 0.133 / 0.078 | 1.18, 0.118 / 0.104 |
| turns, mean | 5.3 | 7.0 | 8.8 |
| wall, mean s | 46.6 | 57.6 | 73.6 |
| tokens in / cache read / cache write / out | 239k / 949k / 94k / 18k | 236k / 1,336k / 121k / 22k | 0.1k / 1,725k / 151k / 21k |
| WebSearch + WebFetch calls | 26 | 14 | 0 |
| knowledge search / read / pick (sessions) | - | - | 21 (5) / 37 (6) / 0 |
| Jev decisions, USD | - | 59, 0.0029 | 193, 0.0211 |

Paired: S1 - N one discordant (`2a649bb1`, S1 right), p = 1.0, cost ratio 1.08 [0.78, 1.72];
S1 - S0 one discordant (`e29834fd`, S1 right), cost ratio 0.88 [0.52, 1.40].

### BrowseComp-Plus (10 tasks)

| | N | S0 | S1 |
|---|---|---|---|
| right | 5 / 5 | 7 / 7 | 6 / 7 |
| cost total, mean / median USD | 4.60, 0.460 / 0.222 | 7.78, 0.778 / 0.498 | 7.68, 0.769 / 0.467 |
| turns, mean | 11.9 | 21.2 | 19.4 |
| wall, mean s | 65.9 | 106.3 | 101.3 |
| tokens cache read / cache write / out | 5,874k / 745k / 45k | 9,592k / 1,239k / 83k | 8,721k / 1,281k / 68k |
| knowledge search (denied offline) / read / pick | - | - | 4 (4) / 0 / 0 |
| Jev decisions, USD | - | 10, 0.0022 | 10, 0.0019 |

Paired: S1 - N `1076` and `58` S1 right, p = 0.5, cost ratio 1.67 [0.89, 3.14]; S1 - S0 no
discordant task, cost ratio 0.99 [0.70, 1.40]. S1's `58` is a hand verdict: its answer names the
same program as S0's, which the judge accepted, and the judge turned S1's down; N's answer names a
different, broader programme and stays wrong.

### LongBench v2 (10 tasks)

| | N | S0 | S1 |
|---|---|---|---|
| right | 7 / 7 | 7 / 7 | 7 / 7 |
| cost total, mean / median USD | 0.65, 0.065 / 0.049 | 1.23, 0.123 / 0.122 | 1.00, 0.100 / 0.100 |
| turns, mean | 3.4 | 5.7 | 4.5 |
| wall, mean s | 18.4 | 39.3 | 32.2 |
| knowledge search / read / pick | - | - | 0 / 0 / 0 |
| Jev decisions, USD | - | 12, 0.0022 | 10, 0.0008 |

No discordant task in any pair. S1 - N cost ratio 1.55 [1.26, 1.97]; S1 - S0 0.81 [0.71, 0.98].

## What each component did

`calls` are the shim's `sanchopanza` runs by subcommand; `outputs` are hook outputs that reached
the main transcript, by component (read from the text: candor's status-block request or lock,
check-done's "does not show this request done", crawl's line, guard's block, knowledge's
redirect); `returns` are Stop blocks that sent the agent back, with the main agent's turns and
list USD between each return and the next one or the end (`benchmarks/h2h/components.py`).

| suite, arm | check-done returns (sessions) | turns after | USD after | candor outputs | other outputs |
|---|---|---|---|---|---|
| GAIA S0 | 7 (7 of 10) | 14 | 0.209 | 10 | crawl 4, fetch 1, hook 2 |
| GAIA S1 | 7 (7 of 10) | 13 | 0.194 | 14 | crawl 4 |
| BCP S0 | 10 (10 of 10) | 23 | 0.927 | 10 | guard 3, crawl 1 |
| BCP S1 | 9 (9 of 10) | 20 | 0.721 | 10 | guard 4, crawl 1 |
| LongBench S0 | 7 (7 of 10) | 18 | 0.310 | 14 | crawl 1, find-auto 1 |
| LongBench S1 | 6 (6 of 10) | 11 | 0.161 | 12 | crawl 1 |

Sanchopanza calls per arm (S0 / S1): GAIA candor-hook 130 / 167, hook 82 / 98, memory-hook
56 / 57; BCP candor-hook 404 / 363; LongBench candor-hook 105 / 83. The knowledge hook never ran:
S1's agents went to the knowledge tools first, and offline WebSearch and WebFetch are disallowed.

**Cost, split.** Over N, S1 costs +0.09 USD on GAIA, +3.08 on BrowseComp-Plus and +0.35 on
LongBench (10 tasks each). Check-done's returns account for 0.19, 0.72 and 0.16 of it. On GAIA,
S1 without the turns after check-done costs 0.99 against N's 1.09; the knowledge tools replaced
every web call and Jev's 193 decisions cost 0.021. On BrowseComp-Plus and LongBench knowledge did
nothing (4 denied searches), so the rest of S1's overhead there (2.36 and 0.19 USD) belongs to the
other components, candor's status block on every session and its 363 and 83 hook runs first.

## Read by hand

- **GAIA `2a649bb1`** (S1 and S0 right, N wrong): S1 searched and read 19 times through knowledge;
  `read` came back with 100-600 characters from the publisher pages (403) and from the
  repository's PDF link, and the agent fetched the paper with curl in Bash. The answer came from
  that text and the model's own knowledge, not from a knowledge read. N, with WebFetch, answered
  with a different pair. Run-to-run variation, plus one gap of `read`: a PDF that curl could get.
- **GAIA `e29834fd`** (N and S1 right, S0 wrong): N and S1 answered from memory with the right
  count before any tool; S0's first recall missed a two-time winner and its fetch passages did not
  correct it. Check-done sent both S arms back to verify. The difference is the first recall.
- **BrowseComp-Plus `1076`** (S0 and S1 right, N wrong): the same retrieval server for all; S1 got
  there in 19 turns and 0.86 USD, S0 in 49 and 1.80, N stopped at a wrong year after 23 searches.
  Knowledge played no part (its one search was denied offline).
- **BrowseComp-Plus `58`**: see the hand verdict above.
- **GAIA `72e110e7`** was flagged as a possible leak in N (a search result named the benchmark);
  all three arms answered it right in three turns, so it changes no comparison.

Every number above that favours S1 over S0 comes from tasks where knowledge was not the reason
(the two GAIA discordants) or from suites where it did nothing (the lower cost on LongBench, with
fewer check-done returns). Knowledge's measurable effect is on GAIA's tool mix: no WebSearch or
WebFetch, 58 knowledge calls in 6 sessions, cache writes and turns up, cost within noise.

## Found in S1, fixed on main

Candor counted a page read through knowledge's `read` as unread: its ledger took a call's target
from `url`, `path` and similar keys, not `url_or_path`, so a final answer citing that page locked
the session at Stop (3 GAIA S1 sessions, after the answer; the citations were a web page and the task's attachment, both read through `read`). Fixed on main (d1e99af, `target_of`
reads `url_or_path` and `pick`'s `sources`); these S1 sessions ran before the fix.

## Spend

13.17 USD at list (subscription): GAIA 2.66 (S1 and N) + 1.47 (S0) + 0.25 (a one-session Haiku
smoke of S1), BrowseComp-Plus 7.68 + 0.09 judge, LongBench 1.00, plus two GAIA sessions stopped in
flight when the batches were stopped (no rows). Jev 0.033 USD over 341 decisions (the invalid sessions included): 47-189 micro-USD
per decision as the journal records it (GAIA S1 115, S0 47, BCP 189, LongBench 83).

## Files

`compare-gaia.json`, `compare-bcp.json`, `compare-longdoc.json`: per arm and per pair, from
`python benchmarks/h2h/compare_lines.py <suite>` over the private rows.
