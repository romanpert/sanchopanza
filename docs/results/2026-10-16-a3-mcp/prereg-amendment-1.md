# A3, amendment 1 (written after the data): the offline control asked again, alone

Written on 2026-10-16, **after** the sealed run's data was seen. That includes the hook's two
arms, their verdict ("not confirmed": P1 fails on recall, P2 and P3 hold) and the control's
failure. It also includes `diagnosis.json`, a free post-hoc breakdown of where the hook lost
recall against the reference, written before this text. It is labelled post-data. **It does not replace the sealed verdict and cannot change it:** it has no
criteria, it rewrites none of the sealed run's files, and its numbers are reported only.

It is sealed before any of its own answers exist (`replay.py --seal-amendment`). The seal
(`prereg-amendment-1.sha256`, `prereg-amendment-1.manifest.json`) covers:
- this file;
- the runner as fixed and its test;
- the whole package and the ATBench file, as the first seal did;
- the sealed run's `answers.jsonl` and `calls.jsonl`, which this amendment reuses, and its
  `analysis.json`, whose verdict it copies.

`--control-only --live` refuses to spend while anything differs from it.

## Why

The sealed run's control (`offline`, reported, not judged) was asked in a second event loop,
and the live client belonged to the first. 498 of its 500 records went unanswered, so the run
says nothing about how far the server has moved since the reference was recorded on 2026-09-27.
The runner now asks the hook's arms and the control in one loop (commit 92f611a, with its test).

## Question

On the 500 whole ATBench-Codex records, **does today's `actions` point still flag what it
flagged on 2026-09-27?** And per trajectory, beside the hook's `mcp` arm: **of the 0.852 → 0.740
recall gap, how much is the hook's view (prefixes ending on a call) and how much is the server
moving?**

## What is fixed

- **The control as registered in the sealed prereg:**
  - the 500 states of `cascade/run.load_codex` (whole records), the same question;
  - `jev-1.13.0`, the cut 0.5;
  - beside the reference's recorded answers (`fixtures/cascade-jev.jsonl`).
- **The hook is not asked again.** Its arms are replayed free from `answers.jsonl`, in the
  sealed run's root (`C:/sp-runs/a3-mcp`; the shell guard's question carries the session's
  folder). The replay must give back exactly the sealed `calls.jsonl`, row for row, or the
  control is not asked (the runner's preflight, one Truth off the ledger, comes before). The free rehearsal did this: 1,189 questions replayed, 0 asked
  (`dry-amendment-1.json`).
- **Files.**
  - Its answers go to `answers-control-amendment-1.jsonl` (hashed keys and numbers, no text).
  - Its records go to `control-amendment-1.jsonl` and its analysis to
    `analysis-amendment-1.json`.
  - `answers.jsonl`, `calls.jsonl`, `control.jsonl` and `analysis.json` are never rewritten.
- **The hook's questions and the control's never share a key.** As in the sealed run, this is
  checked after the control is asked and before its records are written. The free rehearsal
  already checked these same keys.

## Reported (no criteria)

- Today's recall and FPR of the offline point at 0.5, with Wilson intervals, beside the
  reference's (213/250 and 73/250).
- Exact McNemar on the paired records, per class.
- Per trajectory and class: flagged by the control today, by the hook's `mcp` arm, by both, by
  neither.
- The spend.

**Reading, fixed before the answers:**
- **Drift shown:** on the unsafe pairs, `control_offline_today.recall.paired.p_exact` < 0.05
  (two-sided, unrounded). Then the README reports how much of the gap today's control accounts
  for: today's recall beside the reference's, and the hook's `mcp` arm against today's control
  on the records it answered (`hook_vs_control_today_unsafe`: both, control only, hook only,
  neither). No test of the hook against today's control is computed.
- **No drift shown:** otherwise. The gap is then read against the reference alone, as the
  sealed run did.

## Cost and cap

- **Dry, free** (`--control-only --dry`): 500 requests, records with a median of 2,719
  characters (max 10,013).
- **Expected:** 0.031 USD on the token fit of the sealed prereg, 0.036 USD at the flat median
  of 71 µ$ per request. The sealed run spent 0.0496 USD (1,189 hook answers and 2 control
  ones) against a fit of 0.051 for the hook.
- **Hard cap in code:**
  - the batch `a3-control-amendment-1` stops at **0.05 USD**;
  - it runs on the same ledger (`C:/sp-runs/a3-mcp/ledger.json`), whose cap stays **0.25 USD**
    (0.0496 spent before this amendment);
  - every call is reserved before it is made, at its estimate: at most 172 µ$ each. On the
    reference's tokens, 203 of the 500 records cost up to 19 µ$ more than their reservation; with
    four calls in flight the overshoot stays under about 0.0001 USD.
- **The sealed run's stops (`StopDead`):**
  - a cap refusal, an outage (HTTP 401, 402, 403, 429 or 5xx, no connection or a timeout,
    settled at its estimate), another model, or three failed or empty answers in a row stop
    the launch dead;
  - a 429 is never retried.
- **A stopped launch is a pause:** it writes no records and no analysis, and exits 2 (3 at a
  cap). Its usable answers stay in `answers-control-amendment-1.jsonl`, so a relaunch replays
  them for free.
- **A launch that ends without stopping writes the control as it is.** Records still without an
  answer are listed in `analysis-amendment-1.json`. **There is no further relaunch:** once
  `control-amendment-1.jsonl` exists, `--live` refuses. Without `--live` the runner only
  analyses it again, for free.
- **The preflight's one Truth** (about 13 µ$) is outside the ledger.

## Procedure

1. Review against the code (agent `revisor-prereg`), then `replay.py --seal-amendment`, then
   commit.
2. `python -m sanchopanza jev-preflight` (exit 0). The runner preflights `jev-1.13.0` too.
3. From a detached worktree at the amendment's sealed commit (not 65528af), with the key in `TYPESAFE_API_KEY` or in the
   file `SANCHOPANZA_KEYS_ENV` names:
   - free: `replay.py --control-only --dry`;
   - then once: `replay.py --control-only --live`, launched by the owner. It takes about a
     minute with four calls in flight.
   - It runs without `--root`: the default `C:/sp-runs/a3-mcp` is the sealed run's root. Neither
     `replay.py` alone nor `--run` is run in that worktree, since they rewrite the sealed run's
     files.
4. The figures are reported as they come, beside the sealed verdict, which stands.
