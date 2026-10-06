# LongBench v2 confirmation: S against clean N, Sonnet 5.5 (2026-10-06)

Preregistered in `docs/results/2026-10-06-h2h-conf/prereg.md` (sealed at h2h 671cfd7, S from
main aad9903; amendment 1 raised the ceiling to 25 USD, not reached). Phase `longdoc-conf`, 50
tasks (60 drawn minus the 10 dev), one session per task and arm, arms alternating within each
task. Report: `report-longdoc-conf.json`. Counts, costs and task ids only.

## Verdict (computed by `gaia_stats.verdict`): **no gana**

| | N (clean Claude Code) | S (S0) |
|---|---|---|
| Right (letter) | 31/50 | 28/50 |
| Total list USD (Jev included) | 6.13 | 4.81 |
| Mean / median USD per session | 0.123 / 0.063 | 0.096 / 0.061 |
| USD per correct answer | 0.198 | 0.172 |
| Mean turns | 5.9 | 4.7 |
| Jev | none | 0.0135 USD, 0 errors |

- Success S - N: **-6 points**, paired 95 % interval **[-18, +6]**; discordant 4 (S only) vs 7
  (N only), McNemar exact p = 0.55.
- Cost ratio S/N: **0.785**, 95 % interval **[0.634, 1.008]**: cheaper, but the interval touches 1.
- Wall time ratio 0.994 [0.772, 1.255].
- Why "no gana": the cost interval does not lie below 1, and the success interval reaches far
  below the -2 point margin; S is not right more often either.

## Hand read of the discordant tasks (prereg section 8)

A read-only subagent compared the S and N transcripts and S's side logs of the 11 discordant
tasks (no task text in its report):

- **N right, S wrong (7):** in 6 nothing from sanchopanza reached the model (every hook returned
  nothing, no tool was blocked, check-done, candor and memory never sent the agent back, memory
  injected no rule). Causes: 4 model variance with the same strategy and similar coverage, 2 where
  S read less of the document and answered earlier with no visible S cause. In 1 the crawl hook
  spoke at the prompt with web advice that does not apply to a local file (weak interference).
- **S right, N wrong (4):** variance; no S component produced output.
- Across the 50 tasks the crawl note fired 3 times on this offline suite (S right in 2 of them).
  S sessions were shorter than N's in 21 tasks and longer in 11 (p about 0.11).

No evidence that an S component costs accuracy on long-document reading. Findings to act on
outside this sealed run: the crawl hook should not speak without a browser tool or a URL; candor
saw an answer that admitted it had not read the deciding part and, rightly under gate A, stayed
silent, which is a case for a check-done send-back worth measuring.
