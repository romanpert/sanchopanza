# N-early on BrowseComp-Plus: early compaction alone (2026-10-07)

Dev, not a confirmation. Owner's OK for a 45 USD ceiling; spent **37.97 USD** of list price on
the subscription (Sonnet 5.5), plus a few cents of judge. Branch h2h-ne (NE arm d9c9d89, queries
0def08b). Comparison: `compare-bcp-ne.json` (`compare_lines.py bcp-conf --lines N S0 NE`). Counts,
costs and ids only.

## Question

In the BCP confirmation (2026-10-06) the one S part with an effect was early compaction
(`--context-budget 160000` sets `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`) with the guard putting
the request back after each compaction. Is the effect the window alone, which clean Claude Code
gets from one setting?

- **NE**: clean N whose user settings hold only `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, the value S's
  install writes (`window_for(160000)` = 193000), in the same place. Nothing else of S.
- **Queries**: the 26 conf queries where clean N's main context reached 150,000 tokens or more,
  where a window of 193k can act (`bcp-ne-ids.txt`). One NE session each, against the conf's own N
  and S0 rows of the same queries.

## Results

| | Right | Gold doc seen | Gave up | Sessions compacted | USD | Turns | Wall s |
|---|---|---|---|---|---|---|---|
| N (conf) | 4 | 7 | 19 | 0 | 39.91 | 27.9 | 191 |
| S0 (conf) | 6 | 10 | 17 | 17 (28 compactions) | 39.80 | 31.5 | 224 |
| **NE** | **7** | 10 | **13** | 19 (26 compactions) | **37.97** | 32.5 | 185 |

- NE against S0: discordant 3 / 2 (p 1.0), cost **0.954 [0.80, 1.15]**. The window alone does
  what S0 did here, a little cheaper and faster.
- NE against N: discordant 6 / 3 (p 0.51), cost 0.951 [0.80, 1.11]. **Biased in NE's favour**: the
  queries were chosen because N's sessions ran long, and a rerun of a long session tends to come
  out shorter. Only the comparison with S0, which was not selected on, is fair.
- Gave up: the final answer says it was not found, or gives a confidence under 25 %. N gave up in
  19 of 26, all past 150k; NE in 13, S0 in 17. Less context, fewer give-ups, the same direction as
  the long bench's pilot A (indagis-6c, 2026-10-07).
- Grades: exact match, else the official judge on Claude Haiku 4.5 (0 unjudged). N and S0 also
  had the blind hand read, which accepted every judge-yes in the confirmation; NE had none.

## What it says

On deep search, S's one measured gain is a Claude Code setting. The guard's re-injection of the
request after compaction adds nothing measurable on top of the window here. An S that sets the
window earns it, but so does a clean Claude Code with one line of settings: it is not an argument
for S over N, and it is the clean test the long bench's N-early arm runs on coding sessions.
