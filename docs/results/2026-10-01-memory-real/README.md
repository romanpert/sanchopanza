# Memory between sessions on real people's sessions (SWE-chat), 2026-10-01

**Confirmed on held-out groups: memory v3 (a record given just in time, when the agent opens or
changes a file an earlier request changed) meets all four sealed criteria. v2 (recall at every
prompt) does not come close.** Protocol, selection and amendment sealed before the data they
govern: `protocol.md` (877c1ac), `amendment-1.md` (631f0ad).

## Why this benchmark

The adoption chains are SWE-smith issues asked by a script. People write "fix it", "push",
"はい。修正してください" and start a new session a median 47 minutes after the last one on the
same repository (SWE-chat: 4,567 consecutive pairs; 37 % share a touched file). `SALT-NLP/SWE-chat`
(ODC-BY): real Claude Code sessions in public repositories. 60 groups (one person, one
repository), up to 6 consecutive sessions each, 319 sessions; groups 0-29 development, 30-59
held out. Every request of every later session is an item; its pool is the records the earlier
sessions left. Labels by code from the transcripts: `lineage` (the request rewrites a line the
record wrote) or `file` (it changes a file the record changed).

## Results

All requests, label `lineage or file`. Recall: requests with a related record in the pool that
have one in view; precision: records given that are related; noise: requests with nothing
related that were given anything.

| split | selector | recall | precision | noise | records per request |
|---|---|---|---|---|---|
| development (953 requests, 161 with a related record) | v2 (every prompt, decider at 0.2) | 0.248 | 0.026 | 0.393 | 0.89 |
| | BM25 alone (top 2) | 0.745 | 0.058 | 0.856 | 1.67 |
| | **v3, replayed through the hook's code** | **0.944** | **0.603** | **0.049** | 0.26 |
| **held out** (1,490 requests, 180 with a related record) | v2 (every prompt, decider at 0.2) | 0.622 | 0.066 | 0.263 | 0.67 |
| | **v3, replayed through the hook's code** | **0.950** | **0.559** | **0.034** | 0.24 |

Criteria (amendment 1): recall >= 0.80 (0.950), precision >= 0.40 (0.559), noise <= 0.10 (0.034),
and better than v2 on all three: **all met**.

Stricter label, `lineage` only, held out: v3 0.754 / 0.099 / 0.064; v2 0.544 / 0.019 / 0.282.
Most of what v3 gives is a record of the same file, not of the same lines: useful context, not
proof that the agent needed it. Whether it changes outcomes or cost is a live question, not
answered here.

On the maintainer's own sessions (13 project folders, 197 requests, locally: the touch calls no
model, so no text left the machine; `local.py`): recall 0.958, precision 0.938, noise 0.0
(`lineage`: 0.885 / 0.25 / 0.082).

## What was found on the way

- **Recall at a prompt has a low ceiling on real sessions.** Only 2 % of BM25's candidates are
  related, and the decider judges a short prompt below chance (AUC 0.38; long prompts 0.75).
  At a session's first request with the cut at 0.7 it still adds a little (development recall
  0.932 to 0.944) with noise on 1 % of requests.
- **The file the agent opens says what the prompt does not.** 90 % of the related records the
  touch gives arrive before the request's first edit (held out: 111 of 133).
- `[Request interrupted by user]` was recorded as a request (40 of 993 development "requests")
  and scored 0.90 against an unrelated record; fixed in `episodes.is_request`.
- A touch is a new process per file opened: 0.61 s median at first (300 record files read cold
  took 0.75-3.2 s on Windows, and the harness package pulled in asyncio and the decision
  points); with an index per project and lazy imports, 0.17 s.
- An adversarial review found 3 high and 7 medium issues none of the tests caught (subagents
  using up the main agent's record, an unlocked index losing records under concurrent hooks,
  records of an older split offered while in context, a compaction mid-request, paths after
  `cd`, a 300-record cap on rebuild), all fixed with tests before the held-out pass.

## Declared

- **The held-out "v2" pass of `score.py` ran at 0.7, not 0.2**: its `decider` selector takes the
  cut from `memory_hook.KEEP_AT`, which v3 raised. v2 at 0.2 was recomputed from the cached
  decider answers (`v2_at_its_cut.py`, no new call; `v2-at-0.2-held.json`). v3 beats both
  (0.7: 0.256 / 0.150 / 0.046).
- Development items were rebuilt twice (the interruption mark; unmasked paths for the index);
  development v2 numbers are from the first build (993 requests).
- The metric credits a record already given to an earlier request of the same session; no
  compaction is simulated (SWE-chat sessions rarely reach one).
- Decider spend: development 0.04 USD, held out 0.04 USD.
