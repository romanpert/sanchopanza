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

## v4.1: the record whose lines the agent is looking at (confirmed on a fresh set)

v3 gave the two newest records that changed a file. v4 keeps, per record and per file, prints
of the lines the request wrote, and gives at a Read the record whose lines the content shows
(nothing when none), at an edit the one whose lines it replaces, else the newest; the
decider's cut at a session's first request moves to 0.8. v4.1 adds an adversarial review's
fixes that held on development data (per file, words only, no imports, decorators, secrets or
failed edits, newest writer owns a line). Designed on development groups; confirmed on 74
groups nobody had looked at (`selection-2.json`, amendment 2, sealed before building).

| fresh set (3,117 requests, 624 with a related record) | recall | precision | noise | records per request |
|---|---|---|---|---|
| v3 shipped | 0.987 | 0.631 | 0.057 | 0.39 |
| **v4.1 shipped** | **0.978** | **0.753** | **0.045** | **0.32** |
| v3 touch alone | 0.986 | 0.659 | 0.050 | |
| v4.1 touch alone | 0.978 | 0.778 | 0.039 | |

All five criteria met: precision above v3, recall within 0.01 of v3, noise not above v3,
recall >= 0.80 with precision >= 0.50, noise <= 0.10. With `lineage` only there is a small cost
beside the gain: recall 0.876 against 0.890 and noise 0.104 against 0.100, precision 0.103
against 0.078. Decider spend 0.025 USD.

Not adopted, measured on development (`variants-v4b-dev.json`): a floor of two lines in view,
the newest record at a Read that shows none of its lines, at a partial Read, and the edit
fallback once per file each lowered precision or recall. Latency is the same as v3's on the
same machine state (a 2,000-line Read hashes in a few milliseconds; the process start dominates).

## v5: the name gate at a first prompt (confirmed on a third fresh set)

At a session's first prompt, with a decider, a record that changed files enters only if the
prompt names one of them (base name, or a stem of four or more characters); a record that
changed nothing is judged as in v4.1, since the labels cannot credit it. The decider is not
asked when no candidate could enter. Designed on the three sets already seen, reviewed
adversarially first (the first version removed change-less records by construction, missed
names before a full stop and in CJK or Korean text, and was measured on prompts cut to 1,000
characters; all fixed), confirmed on `selection-3.json` (amendment 3, sealed before building):
101 groups nobody had scored, 82 of them runs of sessions outside the windows of used groups
(the same people and repositories as seen data) and 19 groups of two sessions.

| third set (3,127 requests, 531 with a related record) | recall | precision | noise | first-request noise | decider calls |
|---|---|---|---|---|---|
| v4.1 | 0.979 | 0.749 | 0.034 | 0.142 | 265 |
| **v5** | **0.979** | **0.758** | **0.031** | **0.118** | **223** |
| touch alone (no recall at a prompt) | 0.979 | 0.763 | 0.031 | 0.114 | 0 |

All four criteria met. `lineage` only: recall 0.862 in both, precision 0.148 -> 0.149. Decider
spend 0.012 USD.

**What the numbers also say:** the decider at a first prompt recovered no request here, none on
either earlier held-out set and one on development (about 8,700 requests in all): the touch
finds the same records. The metric does not credit a record that arrives before the agent
opens the file, which is the only place recall at a prompt could pay. Whether to turn it off by
default is left open: it is already off without a decider, which is how most people run it.

Measured along the way, not acted on: a record's text is a median 1,450 characters (35 % of it
recorded command output) and the touch injects 448 characters per request, so compacting it
cannot pay in cost; 12.8 % of SWE-chat sessions compact at least once (195 compactions in 719),
and no pass so far simulates a compaction.

## Across a compaction (v5, the touch only, as most people run it)

12.8 % of SWE-chat sessions compact at least once, and no earlier pass simulated it. Every
cached session with a `compact_boundary` was replayed event by event through the hook's own
code (`v5_compact.py`): each prompt, each compaction's SessionStart (before the boundary is in
the transcript, as Claude Code writes it), each file tool's PostToolUse with its real input and
result. Only the session's own records are in the store. Items are the requests after the
session's first compaction; labels as above. Sessions split by id hash before scoring.

| split | sessions | requests after a compaction | recall | precision | noise | records / chars per request |
|---|---|---|---|---|---|---|
| development | 69 | 1,103 (283 with a related record compacted out) | 0.929 | 0.816 | 0.041 | 0.38 / 870 |
| held out | 73 | 1,251 (266) | 0.906 | 0.807 | 0.039 | 0.28 / 656 |

`lineage` only: recall 0.882 / 0.752, precision 0.210 / 0.204. The misses looked at one by one
are definitional (a related record compacted out by a later compaction was given instead, or
a Read that shows none of a record's lines, where v4 gives nothing on purpose), not a fault. Of
the related records given, 80 % (dev) and 93 % (held) name a file the compaction summary already
names: whether the verbatim record adds to the summary is not measurable offline.

Not adopted (development): after a compaction, the edit fallback only once per file. Repeated
edits of one file each release one older record of it; limiting that cut characters per request
by 25 % (870 to 651) and raised `lineage` precision (0.210 to 0.288), but lowered precision on
the main label (0.816 to 0.751) and `lineage` recall (0.882 to 0.874). The same rule lowered
precision across sessions too (v4.1 review).

Replay artifact found and handled: the store removes records older than 30 days when it saves,
and SWE-chat sessions are months old, so a replay through the hook's recording kept nothing
until retention was lifted in the replay (`ep.save` default). Earlier passes saved pools with
`keep_days=10_000` and never recorded through the hook, so they were not affected.

Latency of a touch, worst case measured (a Read of 2,000 lines over 300 records of that file),
20 runs with the CPU at 56 % from other work: median 0.130 s, max 0.225 s.

## v6: the working tree and the shell (amendment 4: NOT confirmed)

In phase B2 Sonnet 5.5 read and edited through Bash; Sm had 40 memory prompts, 0 injections, 0
touches; 86-95 % of its records said they changed nothing. v6 reads what a request wrote from the
git working tree and sends Bash and PowerShell calls to the touch (amendment 4 has the design and
the development numbers). Confirmation, run once (`v6_chain_real.py --tag confirm`,
`replay_v6.py` on three held-out sets):

| fresh B2 requests (67, 34 with a related record) | recall | precision | noise | records that changed nothing |
|---|---|---|---|---|
| v5 | 0 | - | 0 | 0.948 |
| v6 | **0.412** | **0.395** | 0.121 | 0.097 |
| by arm, v6: N 26-40 / S 15-40 / Sm 15-40 | 1.000 / 0.500 / 0.000 | 0.818 / 0.421 / 0.000 | 0.250 / 0.083 / 0.077 | |

| SWE-chat, v5 -> v6 touch | recall | precision | noise | records given through the shell (related) |
|---|---|---|---|---|
| held out 1 (1,490) | 0.950 -> 0.956 | 0.748 -> **0.724** | 0.030 -> 0.033 | 15 (5) |
| held out 2 (3,117) | 0.978 -> 0.978 | 0.778 -> 0.768 | 0.039 -> 0.041 | 17 (5) |
| held out 3 (3,127) | 0.979 -> 0.979 | 0.763 -> **0.749** | 0.031 -> 0.034 | 21 (5) |

Criteria: 1 (recall >= 0.60) **failed**, 2 (precision >= 0.50) **failed**, 3 and 4 met, 5 failed
on held out 1 and 3 (precision down 0.024 and 0.014, allowed 0.01). v6 is not shipped as
confirmed. What it fixes is real (records now know what a shell edit changed: 95 % to 10 % that
"changed nothing"), but what the shell touch gives is too often unrelated: about 30 % of its
records are related on SWE-chat, and none of Sm's 13. The causes are the next round.

**Declared after the sealed run (6073ae6):** the replay of amendment 4 paired records with the
wrong requests in arms S (from request 13) and Sm (from request 5): `claude -p` stream-json writes
a compaction summary as an `isSynthetic` user message, which the parser counted as a request.
Their figures above are therefore invalid; N (no compaction) is not affected: recall 1.000,
precision 0.818 on its 15 fresh requests. The verdict stays "not confirmed": a corrected rerun on
the same requests would be post hoc, and the SWE-chat precision drop (criterion 5) is real.
Diagnosis of that drop on seen data (dev + held out 1): of the shell touch's 14 unrelated
records, 6 came from `git diff` output and 2 from `gh api ... "$(cat <<EOF ...)"` bodies.

## v6.1: the shell touch without history, message bodies or file-tool editors (amendment 5: NOT confirmed)

v6.1 (`context/statements.py`, `context/shell.py`, `memory_hook.SHELL_UNTIL_FILE_EDIT`; three
adversarial reviews, all fixed with tests) leaves out of a shell call's view the output of
`git diff/show/log` (whole when nothing else prints code, only the diff blocks when something
does), heredoc bodies that no interpreter or shell runs, and the quoted strings of `git commit`,
`gh`, `curl` and the like; and once a session edits an existing file with a file tool, its
shell touch gives nothing. Design and development numbers are in `amendment-5.md`: on SWE-chat
(with each session's folder, which the bench had been leaving out) precision within 0.005 of
v5, recall equal; on B2's fresh requests, post hoc, recall 0.941 and precision 0.927.

Confirmation, run once on the maintainer's own sessions that no pass had scored
(`local_v6.py`, 12 folders, 153 sessions, 632 requests, 156 with a related record; counts only,
`local-v61.json`):

| | recall | precision | noise | records given through the shell (related) |
|---|---|---|---|---|
| v5 | 0.923 | 0.858 | 0.019 | |
| v6.1 | 0.949 | **0.421** | **0.153** | 258 (62) |

Criterion 1 met (recall up 0.026), 2 and 3 failed by far (precision -0.437, noise +0.134),
4 failed (24 % of the shell's records related, 50 % required). On the 40 requests of sessions
started after the v3 pass: precision 0.774 -> 0.694, noise 0.087 -> 0.174. Not shipped.

**Why** (`v61_diag_local.py`, after the sealed run, so now seen data): all 258 records came
while the gate was open, before any file-tool edit in their session, and almost all from
reads: `sed -n` (47 unrelated, 11 related), `grep -n` (29, 6), `echo "==="; ...` blocks (20,
11), `grep -rn`, `cat`. These agents (Claude Code in auto mode, whose prompt suggests reading
with `cat`, `head` or `sed -n`) make about 38 shell calls per request (23,736 Bash and 952
PowerShell in 632 requests) and read far more than they edit; a shell read is rarely followed
by an edit of that file. SWE-chat's agents read with the Read tool, so its shell reads were few
and the development numbers could not show this. The label cannot see shell edits (17 of the
unrelated records came from `python -` or `sed -i` writes), which explains a little of it,
not most.

Declared: 157 target sessions were counted before sealing and 153 were built: four
transcripts disappeared from disk in between (a cleanup freed about 128 GB of C: at that time).
