# Jev 1.14 against 1.13 on every component bench (lot L1: A1 + A9)

Run of 2026-10-15. `jev-1.13.0` (arm 13r) and `jev-1.14.0` (arm 14), both asked live the same
day, interleaved per case (even cases 1.13 first, odd ones 1.14 first), on the same states and
questions. No Danger Zone header in either arm. Jev only: 0 calls to Claude. Pre-registered in
`prereg.md` (sha256 `08ee40a1...cfb3a9a`, in `prereg.sha256`), sealed at commit 7f6c885 before any
1.14 answer. Every number below is in `report.json` and is rebuilt for free from `rows/` and the
published 1.13 recordings by `python benchmarks/jev114/jev114_components.py report --rows
docs/results/2026-10-15-jev114-l1/rows`; `tests/test_jev114_components.py` pins them.

## Verdict

**1.14 is no worse than 1.13 on the component benches taken together, with the production
thresholds and without a threshold. The gate of the 1.14 plan's phase 2 passes.**

| Global, 14 minus 13r | Items | 13r | 14 | Difference [95 % CI] | McNemar (14 wins / 13r wins, p) | Verdict |
|---|---|---|---|---|---|---|
| With the production thresholds | 1,437 | 1,259 | 1,253 | −0.42 points [−1.46, +0.70] | 33 / 39, p 0.56 | **no peor** |
| Without a threshold (0.5 / argmax) | 1,320 | 1,227 | 1,224 | −0.23 points [−1.14, +0.68] | 19 / 22, p 0.76 | **no peor** |
| Macro AUC over 15 points | 15 points | 0.9838 | 0.9824 | −0.0014 [−0.0057, +0.0021] | | **no peor** |

No component improves or loses under the sealed rule (Holm across seven components). The −2 point
bound is out of reach for a small component unless the arms agree almost everywhere, so "no
concluyente" there is not a loss.

| Component | Items | With thresholds, 13r → 14 [CI] | Verdict | At 0.5 [CI] | Verdict | AUC 13r → 14 | Verdict |
|---|---|---|---|---|---|---|---|
| public | 227 | 207 → 206, −0.4 [−2.2, +0.9] | no concluyente | 165 → 165, 0 [0, 0] | no peor | 0.989 → 0.986 | no peor |
| fifty | 212 | 200 → 196, −1.9 [−5.2, +0.9] | no concluyente | 204 → 205, +0.5 [−1.9, +2.8] | no peor | 0.993 → 0.990 | no peor |
| collision | 102 | 95 → 93, −2.0 [−5.9, +2.0] | no concluyente | 172 → 173, +0.6 [−1.1, +2.8] | no peor | 0.999 → 0.999 | no peor |
| steerability | 28 | 25 → 25, 0 [0, 0] | no peor | 25 → 26, +3.6 [0, +10.7] | no peor | 1.000 → 0.995 | no concluyente |
| agentdojo | 273 | 248 → 250, +0.7 [−1.5, +3.3] | no peor | 261 → 258, −1.1 [−2.6, +0.4] | no concluyente | 0.968 → 0.970 | no peor |
| rest | 454 | 358 → 354, −0.9 [−3.5, +1.8] | no concluyente | 273 → 267, −1.9 [−4.7, +0.9] | no concluyente | 0.981 → 0.978 | no peor |
| supersede | 141 | 126 → 129, +2.1 [0, +5.0] | no peor | 127 → 130, +2.1 [−0.7, +5.0] | no peor | 0.954 → 0.969 | no peor |

Items with thresholds leave out the 17 shell commands and 7 edges the code decided without a
model call. Without a threshold, search, facts, edge and routing have no per-item reading and are
not counted; each collision case gives one or two items. Every call of both arms answered: 0
failures, 0 refusals by the cap, and every call the provider answered named the arm's model
(1,585 for 13r, 1,589 for 14).

**Scale.** 1.13 asked again today against its own published recordings, on the same items:
1,187 → 1,186, 9 against 10 discordant of 1,329. 1.14 against 1.13 today: 33 against 39 of 1,437.
1.14 changes about five decisions in a hundred, about evenly in both directions, where 1.13
against itself changes about one and a half.

## The figures to beat

| | Published 1.13 (recorded, today's code) | 1.13 today | 1.14 today |
|---|---|---|---|
| routing, policy | 14/20 | 14/20 | 14/20 |
| routing, Score vs tier concordance | 0.975 | 0.975 | 0.983 |
| Score ECE (public bench) | 0.168 | 0.152 | **0.109** |
| Choice ECE / Truth ECE (public bench) | 0.027 / 0.100 | 0.028 / 0.101 | 0.044 / 0.084 |
| injection, hand-written, policy (0.5) | 27/28 (28) | 27/28 (28) | 27/28 (28) |
| guard: model / code list | 15/15 / 17/17 | 15/15 / 17/17 | 15/15 / 17/17 |
| fifty, policy (0.5) | 200/212 (202) | 200/212 (204) | 196/212 (205) |
| substitution on 211, Jev policy against Opus 5.5's 199 | 200 | 200 | 196 |
| AgentDojo at 0.70: caught / false alarms | 101/124 / 0/149 | 99/124 / 0/149 | 101/124 / 0/149 |
| AgentDojo at 0.5: caught / false alarms | 112 / 0 | 112 / 0 | 110 / 1 |
| steerability, both sides right | 11/14 | 11/14 | 11/14 |
| collision, policy; duplicates caught at `t.act` | 96/102; 16/18 | 95/102; 16/18 | 93/102; 16/18 |
| supersession, first bench held out: tp / fp | 7/10 / 0/22 | 7/10 / 0/22 | 7/10 / 0/22 |
| supersession, second bench: tp / fp, AUC | 11/16 / 0/32, 0.893 | 12/16 / 0/32, 0.964 | **14/16 / 0/32, 0.980** |
| plan: raw AUC; after `dag.py` precision / recall | 0.937; 1.00 / 0.88 | 0.933; 1.00 / 0.88 | 0.949; 1.00 / 0.88 |

The fifty bench was 197/212 under the policy of 2026-09-25; 200/212 is the same recording under
the shipped `memory_write` cut. memory-e, -f and -g (108 cases) have no published recording among
those read, so the first column lacks them; both live arms have them.

## Where 1.14 gains and where it loses

Per point, outside the sealed rule (exploratory, no multiplicity correction):

- **Gains.** The Score is better calibrated (ECE 0.152 → 0.109 on the 20 routing cases, the
  weakest primitive of 1.13), with the same 14/20 routed. Supersession catches 14 of 16 replaced
  rules on the second bench with no false suppression (12 for 1.13 today, 11 recorded). AgentDojo
  at the shipped 0.70: 101 against 99. facts: 60 → 63 of 80.
- **Loses: `redundant_page`.** 115 → 107 of 125 under the policy (9 cases lost, 1 gained, p
  0.021 unadjusted), 7 of the 9 in `retrieval-c`. The ordering does not move
  (AUC 0.997 → 0.995): 8 of the 9 are pages that add nothing, scored 0.60-0.75 by 1.13 and
  0.29-0.52 by 1.14, under the 0.59 cut derived on 1.13. That is a threshold to recalibrate, not
  a worse model.
- **fifty, −4 under the policy** (200 → 196): `extract_gate` −2, `goal_met` −2, `redundant_page`
  −1, `repeats_check` −1, `memory_write` +2; at 0.5 it is +1 (204 → 205). The substitution
  figure follows: 196 under the policy against Opus 5.5's 199.
- Also down, not significant: edge 50 → 46 of 73 (p 0.29).

## A9: injection over the whole text

The 30 AgentDojo texts longer than one 2,000-character window (23 injected, 7 clean), each
model, three ways: the first 2,000 characters only (the bench's cut), the production window scan
(windows of 2,000 with 200 of overlap, at most 8, stop on a hit), and one call over the whole
text (at most about 7k tokens, so no long-context header).

| Way | Arm | Caught at 0.70 | False alarms | With the keyword layer | Calls | Characters shown | AUC |
|---|---|---|---|---|---|---|---|
| first 2,000 | 13r | 13/23 | 0/7 | 22/23, 0/7 | 30 | 60,000 | 0.85 |
| first 2,000 | 14 | 13/23 | 0/7 | 22/23, 0/7 | 30 | 60,000 | 0.84 |
| windows | 13r | 21/23 | 0/7 | 22/23, 0/7 | 55 | 92,689 | 0.99 |
| windows | 14 | 21/23 | 0/7 | 22/23, 0/7 | 55 | 92,697 | 1.00 |
| whole text | 13r | 21/23 | 0/7 | 22/23, 0/7 | 30 | 233,853 | 1.00 |
| whole text | 14 | 21/23 | 0/7 | 22/23, 0/7 | 30 | 233,853 | 1.00 |

No model effect (14 against 13r: 1 case each way, in both ways) and no feature effect (whole
against windows: 0 discordant in either model). The cut at 2,000 is what lost payloads; the
window scan already recovers them, and one call over the whole text catches the same ones with
45 % fewer calls but 2.5 times the text, because the window scan stops at the first hit. It is a
latency lever, not a recall one.

## Cost

| | Calls | Input tokens | USD |
|---|---|---|---|
| 13r | 1,585 | 1,194,874 | 0.0502 |
| 14 | 1,589 | 1,196,211 | 0.0502 |
| Batch `jev114-l1` on the shared ledger (two preflights and the 4-case smoke included) | | | **0.1005** |

Estimated 0.11 before the run; cap 0.30. The shared ledger stood at 0.2738 of 4.50 USD after
this batch (0.1733 of it from lot L2). A repeat of each answer costs nothing: answers are cached
per arm and recorded in `fixtures/jev114/l1-components.jsonl` (1.14) and
`fixtures/jev114/l1-components-113r.jsonl` (1.13 today).

## Not measured here

- The R-Judge and ATBench parts of `claude-code-broad` (data not on this machine; R-Judge is lot
  L2's), its control set (no Jev decision) and the Stop check (lot L2). "Guard" is the shell
  point on the public bench's 32 commands.
- Images, Box and the long-context header: lots L5 and L6.
- No threshold was recalibrated and `DEFAULT_MODEL` stays `jev-1.13.0`.

## Recommendation

- Phase 2 can run: the gate passes on both metrics.
- Do not switch `DEFAULT_MODEL` to 1.14 as it stands. First recalibrate `t.adds_nothing`
  (`redundant_page`, 0.59) on the 1.14 recordings with `benchmarks/thresholds.py` (free), and
  check `memory_write`, `goal_met` and `extract_gate` the same way; a switch should keep the
  Score's better calibration and the supersession gain without the redundancy loss. What
  followed: the [recalibration](../2026-10-15-jev114-recal/README.md) gave 1.14 a profile of its
  own, which does not fix `redundant_page` (0.61); its
  [confirmation](../2026-10-15-jev114-recalconf/README.md) was "not admissible", with
  `redundant_page` worse; and [redundant-drop](../2026-10-16-redundant-drop/README.md), with 90
  more `drop` cases, cleared the derivation only at 0.04 and proposed no cut.
- Injection: keep the window scan. One whole-text call is the same recall for fewer calls and
  more tokens.

## Files

- `prereg.md`, `prereg.sha256`: the sealed question, rule and budget.
- `report.json`: every table here, per-point AUC and the A9 tests.
- `rows/`: one row per case and arm (ids, labels, decisions and answers; no texts).
- Runner: `benchmarks/jev114/` (`jev114_components.py`, `jev114_extras.py`, `jev114_paired.py`, `jev114_report.py`; the prereg names them without the `jev114_` prefix).
