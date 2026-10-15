# Adoption study, phase D: results (2026-10-05)

Sealed pre-registration `prereg.md` (seal f422cea0, 648837c). Run 2026-10-05 13:47-21:57 on the
frozen copy of 7a39a1f, Haiku 4.5, Claude Code 2.1.285, 26 new SWE-bench Verified singles x N/S x
3 repetitions (78 pairs, three repetitions at once). `confirm_d.py` on the seal; full output in
`verdicts.json`. No amendment was made after sealing. Spend: the ledger went from 206.42 to 294.91
USD; of that, 6.24 is the need probe that ran alongside, so D cost about 82 USD list price
(estimate 78, ceiling 316.42).

Every session ran and was graded; all 78 S sessions met the treatment criteria (commit, (a)-(g)):
no exclusion, no missing pair, no usage limit, no stop.

| Hypothesis | Statistic | Verdict |
|---|---|---|
| H1, non-inferior success (margin -2/26) | mean D = +0.0128 (S 46/78, N 45/78); one-sided 1 % bound -0.0513 >= -0.0769 | **holds** |
| H2, non-inferior cost (upper < 1.10) | median per-instance S/N 1.007, 95 % [0.933, 1.143] | **does not hold** |
| H2, cheaper (upper < 1) | same | **does not hold** |
| H4, adoption (reported) | find called in 2 of 78 S sessions (2.6 %, [0, 7.7 %]); ToolSearch 0; skill 0 | no verdict |

- **Delegations:** N 0 calls; S 2 calls, 0 failed. The fix of 7a39a1f held (13/13 failed before).
- **Exploratory:** turns S/N 1.004 [0.931, 1.153]; cost per turn 1.012 [0.993, 1.047]. Totals:
  N 40.11 USD, 3,993 turns; S 42.52 USD, 4,115 turns (+6 % cost, +3 % turns). The two S
  sessions that called find both resolved (0.86 USD mean, against 0.54 for the 76 that did not;
  selected by the agent, not causal).
- **By stratum (resolved S/N):** easy 29/28, medium 12/11, hard 5/6.

What this says: with the default install as it ships (hooks, coding skill, find always loaded),
Claude Code on Haiku 4.5 resolves as many Verified issues as alone, at about the same cost (the
median ratio is 1.007), but the interval does not rule out up to 14 % more, so the pre-registered
"no more than 10 % dearer" is not shown. The agent almost never uses find. Nothing here shows a
gain; it shows no loss in success.

2026-10-15: text redacted to remove the name of another project; the sealed original (`prereg.sha256`, hash f422cea03d2369f9ed5cd24bd9f26d460235952fee95fc62c094666c1a4122f1) is kept in the git history.
