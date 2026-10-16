# D1: OpenAI's Decisions API as a provider, on the public benches

**The result:** by the sealed rule, **"no concluyente"**. Asked as sanchopanza ships (its
questions, its policies, thresholds set against Jev), OpenAI's Decisions API (`gpt-6-luna`)
decided 200 of the 244 public-bench rows right and Jev (`jev-1.13.0`, the public recording) 206:
**−2.5 points, paired bootstrap 95 % [−6.1, +1.2]**, against a −5-point margin (exact McNemar on
7 against 13 discordant rows, p 0.26). It answered all 301 queries, with no refusal and no
unusable answer, for **0.0143 USD**. Its yes/no answers are the better calibrated of the two.

It is the first measurement of a second hosted decision provider behind sanchopanza's contract:
it works end to end and is in the same range as Jev on these points, but this sample cannot say
it is no worse.

Pre-registered in [`prereg.md`](prereg.md):
- reviewed twice by `revisor-prereg` against the code, sealed in `2fc329b`
  (`prereg.sha256`: prereg `9131b812…`, launcher `026fac79…`), instrument `9ab0473`;
- run on 2026-10-16 from a detached worktree at the seal commit, launched outside the session
  (WMI), once: 20:12:14 to 20:13:39, exit 0. The owner approved the OpenAI spend.

## What ran

- **Data:** the public benches (`benches/core.jsonl`, `safety.jsonl`, `graph.jsonl`): 245 cases,
  244 scored rows and one plan; 301 distinct queries, the same set whatever the answers.
- **OpenAI's arm:** each query asked once through `create("openai-decisions")`'s client
  (`providers/openai_decisions.py`, written against OpenAI's guide), behind `CappedDecider` on the
  lot's own ledger (cap 0.10 USD). Preflight: one call with a predicate, a choice and a score,
  all answered, model `gpt-6-luna`, billed at 1.94x the adapter's estimate, so the run projected
  0.025 USD before any query.
- **Jev's arm:** the existing recording `fixtures/public-benches.jsonl` (jev-1.13.0), replayed
  free. No Jev call.
- **Both arms** through `sanchopanza.eval.bench` under the shipped `Thresholds()` and policies,
  cases paired by id.

## Primary result

| | Rows right of 244 | Only this arm right | Difference (OpenAI − Jev) | 95 % (paired bootstrap) | Verdict at −5 |
|---|---|---|---|---|---|
| OpenAI `gpt-6-luna` | 200 (82.0 %) | 7 | **−2.5 points** | **[−6.1, +1.2]** | **no concluyente** |
| Jev `jev-1.13.0` | 206 (84.4 %) | 13 | | | |

A row is right when it is decided and correct under the shipped policy. No query went unasked and
no row lacked a usable answer in either arm (0 and 0), so no row was scored by a default.

## Per point (descriptive)

| Point | Rows | OpenAI decided / right | Jev decided / right |
|---|---|---|---|
| routing | 20 | 20 / 14 | 20 / 14 |
| search | 18 | 18 / 18 | 18 / 17 |
| triage | 16 | 16 / 15 | 16 / 14 |
| injection | 28 | 28 / 28 | 28 / 27 |
| command (deny-list rows decide in code) | 32 | 15 / 15 | 15 / 15 |
| citation | 20 | 17 / 16 | 18 / 18 |
| numeric citation | 24 | 21 / 21 | 22 / 22 |
| unsourced report | 22 | 22 / 22 | 22 / 21 |
| entity | 24 | 24 / 24 | 24 / 24 |
| facts | 20 | 15 / 12 | 16 / 15 |
| dependency | 20 | 20 / 15 | 20 / 19 |

OpenAI gains on search, triage, injection and the unsourced report (one row each) and loses on
the citation points (3 rows), facts (3) and the plan's pairwise dependencies (4). On the binary
points with an AUC, both reach 1.00 except dependency (OpenAI 0.95, Jev 1.00).

**Calibration, by primitive** (expected calibration error, lower is better):

| | Truth (143) | Choice | Score (20) |
|---|---|---|---|
| OpenAI | **0.028** | 0.023 (53) | **0.087** |
| Jev | 0.094 | 0.026 (56) | 0.168 |

Jev's Truth confidence is |2p − 1| from a probability that runs under-confident (its mean
confidence 0.86 against 0.96 right); OpenAI's predicate probabilities sit closer to their hit
rate (0.95 against 0.96). Agreement by primitive: Truth 95.8 % both; Choice 92.5 % against
98.2 %; Score 70 % both.

## Cost and time

- **Spent:** 0.0143 USD on the lot's ledger for the 301 queries, plus 0.00004 for the preflight.
  OpenAI counted 123,148 input tokens where Jev counted 154,827 on the same queries; at 0.10
  against 0.042 USD per million, OpenAI's calls cost about 1.9x Jev's.
- **Latency:** a median of about 250 ms a call for both, on this PC.
- **Clock:** 85 seconds for the 301 calls, one at a time.

## What it licenses, and what it does not

- **"no concluyente":** OpenAI's Decisions API is usable behind sanchopanza's contract, as
  shipped, on these points; this sample cannot show it is within 5 points of Jev, nor that it is
  worse. Where it lost (citations, facts, dependencies) Jev's thresholds and question wording were
  derived on Jev; a threshold profile of its own was not tested.
- **Not measured:** parity on the 1,437 component items (about 0.24 USD), images (not wired in
  the adapter), long context, latency under load, a second draw.
- **The default does not move:** Jev stays the measured default; `openai-decisions` is an
  opt-in provider (`SANCHOPANZA_PROVIDER=openai-decisions`).

## Files

- `prereg.md`, `prereg.sha256`: the registration and its seal.
- `analysis.json`: the report `run.py report` wrote (both arms' summaries and the primary).
- `fixtures/openai-decisions/public-benches.jsonl`: OpenAI's 301 answers (keys, probabilities,
  tokens, cost, latency), no text; `python benchmarks/openai_decisions/run.py report` replays it
  free.
