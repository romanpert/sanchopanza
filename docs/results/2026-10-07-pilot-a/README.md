# Pilot A: passages on arrival, Sonnet 5.5, long chains (2026-10-07)

Arm A = clean Claude Code + only `sanchopanza passages-hook` (lean edd37bb, fraction 0.25, Jev
ranking, Write guard). N = the gate's clean arm on the same chains, model and caps (root
`C:\sp-runs\L`). One run per chain and arm (k = 1): descriptive, no inferential claim.
Spent: A 54.89 USD (list, subscription), Jev cents.

| Chain | Arm | Calls run | Cost USD | Resolved (of 60) | Cost per resolved | Give-ups (at/past 150k) |
|---|---|---|---|---|---|---|
| conan-long60-1 | N | 51 of 62 (cap) | 28.45 real (32.06 charged: call 51 died and was charged its 4.50 cap; real 0.89) | 44 | 0.647 | 1 (0) |
| conan-long60-1 | A | 58 of 62 (cap) | 30.90 | 47 | 0.657 | 1 (1) |
| pydantic-long60-1 | N | 62 of 62 | 23.55 | 44 | 0.535 | 7 (6) |
| pydantic-long60-1 | A | 62 of 62 | 24.00 | 48 | 0.500 | 4 (2) |

- **Same requests, cost**: conan at call 50, N 27.56 and A 24.61 (-10.7 %), context 427k vs 385k;
  pydantic at call 50, -3.6 %, but A's last 12 calls cost 6.70 against N's 5.60 (two heavy calls)
  and the whole chain came out +1.9 %.
- **Same bugs, quality** (bugs both arms were asked): conan 43 vs 42 (4 only A, 3 only N);
  pydantic 48 vs 44 (4 only A, 0 only N). Together 8 only A vs 3 only N (exact McNemar p 0.23).
- **The hook**: 26 cuts (178,627 -> 47,261 characters), 0 whole re-requests, 2 targeted (r_whole
  0.0; the abort rule never came near). It acted far less than the replay of the owner's Opus
  sessions suggested: Sonnet narrows most Reads with offset/limit, and narrowed Reads and diffs
  pass whole by design.
- **Reading**: A did not hurt quality (if anything the other way) and cost the same to 10 % less;
  with k = 1 and two chains this is a direction, not a result. The earlier stop of N on conan is
  its cost: under the same 38 USD cap A reached 7 more requests.
