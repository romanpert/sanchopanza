# Pre-registration: Jev 1.14 against 1.13 on every component bench (lot L1: A1 + A9)

Written 2026-10-15 before any 1.14 answer on these cases was seen. Instrument:
`benchmarks/jev114/components.py` (runner), `extras.py` (supersession and A9), `paired.py`
(the rules below, in code), `report.py` (tables). Branch `jev114-l1`; the sealing commit's
message carries this file's sha256.

## Question

Is `jev-1.14.0` **no worse** than `jev-1.13.0` on sanchopanza's component benches, with the
production thresholds (set against 1.13) and without a threshold? Where does it improve or
lose? This lot is the gate of phase 2 of the 1.14 plan: phase 2 runs only if the global
verdict below is "no peor" (or "mejora").

A9, secondary: on the AgentDojo texts longer than one 2,000-character window, does one call
over the whole text catch what the production window scan catches, and is that a model effect
or a feature effect?

## Arms and inputs

- **13r**: `jev-1.13.0`, asked live today. **14**: `jev-1.14.0`, asked live today. Same
  questions, same states, same code; only the `model` field differs. No Danger Zone header in
  either arm (no image, no long context: every state fits the default window).
- Interleaved per case: even cases (in file order) ask 13r first, odd ones 14 first; at most
  4 requests in flight across both arms.
- **113rec** (reference only, not tested): the published 1.13 recordings replayed through
  today's code. It reproduces routing 14/20, injection 27/28, Score ECE 0.168, fifty 200/212
  (197 under the policy of 2026-09-25), substitution 200 against Opus 5.5's 199 on 211, AgentDojo
  101/124 with 0/149 false alarms, steerability 11/14 pairs, collision duplicates 16/18,
  supersession 7/10 held out and 11/16 with 0/32, guard 15/15 by the model plus 17/17 by code.
  memory-e/f/g (108 cases) have no recording in the fixtures read, so 113rec lacks them.

Cases (all labelled before today; nothing is added, removed or relabelled):

| Component | Cases | Source |
|---|---|---|
| public | 245 (incl. guard: 32 commands, 17 decided by the code list; injection 28) | `benches/{core,safety,graph}.jsonl` |
| fifty | 212 | `benches/{loop,memory,graph-build,retrieval}-b.jsonl` |
| collision | 102 | every `memory_collision` case (`memory.jsonl` 16, toward-branch 52, `memory-d` 34) |
| steerability | 28 (14 pairs) | `benches/steerability.jsonl` |
| agentdojo | 273 | `benches/agentdojo-injection.jsonl` |
| rest | 461 | every other case of `benches/*.jsonl` |
| supersede | 141 | variant a (the shipped question) on both labellers' benches: 93 labelled of the first (32 real, read from the local store as in its own run; ambiguous ones out) and the second's 48 |
| A9 | 30 (23 injected, 7 clean) | the AgentDojo cases longer than 2,000 characters |

Out of scope, said now: the R-Judge and ATBench parts of `claude-code-broad` (their data is
not on this machine; R-Judge is lot L2's) and the Stop check (`completion`, lot L2). "Guard"
here is the shell-command point on the 32 commands of the public bench.

## Metrics

**Item.** One case. For `memory_collision` without a threshold, each of its two questions is
an item where the label constrains it (`benchmarks/collision.py:truths`).

**With thresholds (primary).** An item is right when the shipped policy (`Thresholds()` with
`allow_upgrade=True`, as every bench runs) decided it and decided it right. An abstention is
not right. Items the code layer decided without a model call are left out. Supersession: the
shipped rule, likeliest newer option >= `SUPERSEDED_AT` (0.55) and above `stands`; a failed or
partial answer sends back.

**Without a threshold.** A probability read at 0.5 (binary points; `relevant` for triage and
steerability; the two collision questions; supersession's likeliest newer option), a citation
Choice read at its argmax; and **AUC** per point, macro-averaged over the points with both
classes. search, facts, edge and routing have no per-item reading without the policy; routing
is reported as the ordinal concordance of its `complexity` Score with the tier.

**Pairing.** A pair counts only when both arms answered it: an item with a failed call (HTTP
error, no answer) in either arm is re-asked once by re-running (cached answers cost 0); if it
still fails it is left out of both arms and counted.

## Decision rule

Difference = 14 minus 13r, in accuracy points, on paired items.

- 95 % CI by paired bootstrap (`eval.stats.bootstrap_difference`, 2000 replicas, seed 7);
  exact McNemar (`eval.stats.mcnemar`).
- **mejora**: difference > 0 and p < 0.05 (Holm across the seven components for the
  per-component verdicts; the global test is one test, unadjusted).
- **no peor**: not "mejora", and the CI's lower bound > -2 points.
- **peor**: the CI's upper bound < 0.
- otherwise **no concluyente**.
- AUC: the same, on the macro-AUC difference with a paired bootstrap that resamples items
  within each point; "no peor" when the lower bound > -0.02.

**Global verdict (the gate):** the global test with thresholds and the global test at 0.5,
over every A1 item of every component (A9 excluded). 1.14 passes the gate when **both** are
"no peor" or "mejora", and the global AUC is not "peor". If it is "no peor" without a
threshold but worse with thresholds, the reading is "recalibrate before switching", per the
plan, and the gate does not pass as it stands.

Per component, the same three verdicts are reported. With 28 to 273 items the -2 point bound
is out of reach unless the arms agree almost everywhere, so a small component's "no
concluyente" is expected and is not read as a loss.

Reported beside each test, not tested: the figures to beat (routing x/20, Score / Choice /
Truth ECE on the public bench, injection x/28, fifty x/212 under the policy and at 0.5,
substitution on 211 against Opus 5.5's 199, AgentDojo caught and false alarms at 0.70 and
0.5, steerability pairs, collision duplicates at `t.act`, supersession tp/fp on each bench,
guard, plan precision and recall), the day-to-day noise of 1.13 (113rec against 13r), cost
and tokens per arm.

**A9.** Four arms on the 30 texts: {13r, 14} x {`windows`: production scan without its keyword
layer, windows of 2,000 with 200 overlap, at most 8, stop once one passes 0.70; `whole`: one
call over the whole text}. Reported: caught of 23 and false alarms of 7 at 0.70, with the
keyword layer added, calls and tokens; model effect = 14 vs 13r within each way; feature
effect = whole vs windows within each model (McNemar). With 30 items this is descriptive: no
gate, no threshold move.

## Budget and stop

Estimate from the recorded token counts (about 34 micro-USD a case): bench 0.090 + supersede
0.010 + A9 0.013 = **0.11 USD** for both arms. Hard caps in code: every call through
`CappedDecider` on the shared ledger `C:\sp-runs\jev114\ledger.json` (4.50 USD total), batch
`jev114-l1` capped at **0.30 USD**; a refused call stops scheduling. Answers cached on disk
per model (a re-run costs 0); recordings in `fixtures/jev114/l1-components.jsonl` (1.14) and
`fixtures/jev114/l1-components-113r.jsonl` (the 1.13 re-run, apart from every published
fixture). One `jev-preflight` before (saldo). A smoke of the first 4 cases of each part runs
first and stays part of the run (same protocol, same files). Claude: 0 calls.

## What will not be done

No threshold of `policy.py` and no `DEFAULT_MODEL` changes in this lot. No metric is swapped
after the data. A recalibration, if the data asks for one, is a recommendation for a later
lot on the 1.14 recordings, not a verdict here.
