# GAIA validation confirmation: S against clean N, Sonnet 5.5 (2026-10-06)

Preregistered in `docs/results/2026-10-06-h2h-conf/prereg.md` (sealed at h2h 671cfd7, S from
main aad9903). Phase `gaia-conf`, 135 tasks (155 without video minus the 20 dev), one session
per task and arm, arms alternating within each task. Report: `report-gaia-conf.json`. Counts,
costs and task ids only.

## Verdict (computed by `gaia_stats.verdict`): **no gana**

Primary analysis: 132 tasks (3 dropped by the leak rule in both arms: 676e5e31, 872bfbb1,
c61d22de). Grade: GAIA's scorer plus 8 blind hand verdicts (2 accepted, 6 rejected; one task
gained one right answer in each arm).

| | N (clean Claude Code) | S (S0) |
|---|---|---|
| Right, 132 paired tasks (with hand) | 97 | 102 |
| Right, all 135 (with hand) | 100 | 105 |
| By level, official (L1 / L2 / L3) | 40/46, 51/67, 8/22 | 41/46, 52/67, 11/22 |
| Total list USD, 135 tasks (Jev included) | 14.81 | 15.54 |
| USD per correct answer | 0.148 | 0.148 |
| Mean turns | 5.5 | 6.5 |
| Jev | none | 0.065 USD, 1 error (a timeout: normal fail-open) |

- Success S - N: **+3.8 points**, paired 95 % interval **[-1.5, +9.9]**; discordant 10 (S only)
  vs 5 (N only), McNemar exact p = 0.30.
- Cost ratio S/N: **1.074 [0.908, 1.255]**.
- Wall time ratio: **1.39 [1.12, 1.79]**: S is slower (+18.5 s per task on average).
- Sensitivity with all 135 tasks: +3.7 points [-1.5, +9.6], cost 1.05 [0.90, 1.22]; same verdict.
- Why "no gana": the cost interval contains 1 and McNemar is far from 0.05.

## Hand read (prereg section 8)

A read-only subagent compared the S and N transcripts and S's side logs of the 15 discordant
tasks (no task text in its report) and timed all 132 pairs.

- **N right, S wrong (5):** 1 traced to S: `fetch_passages` returned about 1k of a 299k-character
  data page and S answered without computing; 2 variance with a similar strategy, 1 where S
  answered from memory without searching, 1 scale slip that check-done sent back without change.
- **S right, N wrong (10):** 1 traced to S: check-done sent back a wrong answer and S redid its
  work and corrected it; 9 variance (in five of them N had the right information and phrased or
  scaled its answer wrong). Two may be an indirect effect of `fetch_passages` failing.
- **check-done:** sent back 18 S sessions; 2 changed from wrong to right, 0 from right to wrong,
  10 right answers sent back for nothing; 49 extra turns, 0.78 USD in total.
- **candor:** no Stop send-back; its lock fired falsely ("denied_action") in 4 sessions and
  refused 4 calls, none of them cost an answer; its status request appeared in 24 sessions.
- **memory and guard:** 1,036 and 130 Jev decisions, no output ever reached the model.
- **`fetch_passages`:** 31 % of its 223 calls failed (58 HTTP 4xx, 18 no text, 10 PDF or binary,
  2 UnicodeEncodeError on non-ASCII addresses).
- **crawl note:** shown in 46 sessions; it names `browser_evaluate`, which this arm does not have.
- **Wall time:** S slower in 107 of 132 pairs; median +5.6 s; eight long trajectories make 70 % of
  the excess. Per pair, roughly: hook latency on each tool call (WebSearch +2.7 s, Bash +1.6 s
  per call; Jev latency up to 7.6 s per session, memory the largest), failed fetches and the
  WebFetch redirect (+2.5 s), one more turn (+3.7 s), Stop hooks (+2.1 s), start and end hooks
  and MCP servers (+2.6 s).

## What this says about S0 on web questions

S0 is about as accurate as clean Claude Code on GAIA, costs the same per correct answer and is
slower. The only component with a measured effect here is check-done (2 fixes, no harm). Changes
worth testing in a next line, outside this sealed run: `fetch_passages` falling back to WebFetch
on 4xx, no-text and PDF, a browser-like user agent, encoded non-ASCII addresses, whole tables on
large data pages; no crawl note without a browser tool; memory and candor off (or off the
critical path) for one-shot question answering; the injection scan off the critical path.
