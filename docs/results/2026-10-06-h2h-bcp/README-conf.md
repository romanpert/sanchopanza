# BrowseComp-Plus confirmation: S against clean N, Sonnet 5.5 (2026-10-06)

Preregistered in `docs/results/2026-10-06-h2h-conf/prereg.md` (sealed at h2h 671cfd7, S from
main aad9903; amendment 2 raised the ceiling to 250 USD, not reached). Phase `bcp-conf`, 90 queries
(100 drawn minus the 10 dev) over the fixed local corpus, one session per query and arm, arms
alternating within each query. Judge: the official template on Claude Haiku 4.5 through the
pinned Claude Code (1.97 USD, 0 rows left unjudged). Blind hand read: 35 doubtful rows (judge yes
without exact match), all accepted. Report: `report-bcp-conf.json`. Counts, costs and ids only;
no query, document or answer text.

## Verdict (computed by `gaia_stats.verdict`): **no gana**

| | N (clean Claude Code) | S (S0) |
|---|---|---|
| Right (final grade) | 49/90 | 56/90 |
| Exact match / judge yes without exact match | 35 / 14 | 35 / 21 |
| Total list USD (Jev included) | 61.02 | 71.41 |
| Mean / median USD per query | 0.678 / 0.494 | 0.793 / 0.467 |
| USD per correct answer | 1.245 | 1.275 |
| Mean turns | 15.1 | 17.6 |
| Jev | none | 0.034 USD, 0 errors |

- Success S - N: **+7.8 points**, paired 95 % interval **[0.0, +15.6]**; discordant 10 (S only)
  vs 3 (N only), McNemar exact p = 0.092.
- Cost ratio S/N: **1.17 [1.007, 1.356]**: S is dearer.
- Wall time ratio: **1.26 [1.10, 1.45]**.
- Why "no gana": McNemar is above 0.05, and the cost interval lies entirely above 1.

## Hand read of the favourable number (prereg section 8)

A read-only subagent compared transcripts and S's side logs of the 13 discordant queries and
broke down cost and time over all 90 pairs (lengths and counts only).

- **The S part that acted is the context budget.** `--context-budget 160000` sets
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`: 26 S sessions compacted (38 compactions near 162k
  tokens), no N session did, and after 34 of them the guard put the request back verbatim.
  N gave up 20 times ("not found" at low confidence), S 11; 12 of N's give-ups came at 150k
  tokens or more (median 184k), 2 of S's (median 106k).
- **S only (10):** 2 traced to compaction and the guard (the right document came after a
  compaction, where N had given up), 2 partly, 6 variance with no S output.
- **N only (3):** none traced to S (2 variance, 1 where S stopped earlier with no S cause).
- On the 26 compacted queries S won 4 and lost 1 discordant pairs. A net 2 to 3 pairs can be
  credited to compaction; the rest of the +7.8 points reads as variance in query paths.
- **Formatting:** S's answers are not formatted differently; the 21 vs 14 judge-only gap comes
  from which queries each arm won (its wins are longer, qualified answers).
- **Cost (+0.115 USD per query):** all of it on the compacted queries (+16.05 USD, about 0.62 per
  query, +10.7 searches each); the other 64 queries came out 5.7 USD cheaper. By class: cache
  writes +8.9 USD (re-caching after each compaction), output +1.8, uncached input +1.0, compaction
  summaries about 3.1 USD in all, cache reads -1.6.
- **Wall (+24.8 s per query):** +15.3 s model time (more turns and searches), +7.8 s compaction,
  +3.1 s Stop hooks; no hook latency on the search calls.
- **Nothing else acted:** 0 Stop send-backs (check-done never fired under gate A; candor posted
  its status request after a subagent call in 5 sessions, none discordant), memory made 984 Jev
  decisions and put nothing in front of the model, crawl spoke at the prompt in 10 sessions,
  fetch was called 4 times, find and find-auto produced nothing.
- Data gap: queries 1237 and 1239 (both arms) and 896 (S) have no search log and 0 searches.

## What this says

On deep search S0 is not shown to win: more right answers at p 0.09, at a significantly higher
cost. The one mechanism with a visible effect is early compaction with the request re-injected,
which keeps the agent searching where clean Claude Code gives up with a large context. Its clean
test is an N arm with only `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000` (the "N-early" arm of the
long-session bench), measured against N and S on the same queries.
