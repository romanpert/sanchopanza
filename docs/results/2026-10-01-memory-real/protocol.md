# Memory between sessions on real people's sessions (SWE-chat): protocol

Written and sealed 2026-10-01, before any item was built or scored.

## Why

The adoption benchmark's chains are SWE-smith issues asked by a script. People do not work like
that: in SWE-chat's 4,567 pairs of consecutive Claude Code sessions by one person on one public
repository, the next session starts a median 47 minutes after the last one (p75 6 hours), and in
37 % of the pairs it touches a file the previous one touched. `install --memory` is for exactly
that; this measures whether it picks the right earlier records there, before any live test.

## Data

`SALT-NLP/SWE-chat` (ODC-BY). `build.py select`, seed 20261001: of the 134 groups (one person,
one repository) with at least three Claude Code sessions that have a transcript, 60 at random,
each with a window of up to 6 consecutive sessions from a random start (319 sessions). Groups
0-29 are **development**, 30-59 **held out**. `selection.json` holds the ids.

## Items and labels (by code, from the transcripts)

Every request of every session after the first in a window is an item; its pool is the records
(`context.episodes`, as `install --memory` writes them) of the window's earlier sessions. A
record's label for a request: `lineage` when the request's edits take out or rewrite a line the
record's request wrote (lines of 16+ characters, context lines excluded), else `file` when the
request changes a file the record changed, else `none`.

## Development and held out

Selectors (the shipped selection: BM25 top 5 then the decider at 0.2; and variants) are
compared and changed freely on development items. The labels may be corrected on development
data too; any change is declared. Before any held-out item is scored, the chosen selector, the
labels' code and the success criteria are written in an amendment and sealed. Held-out items
are scored once.

Metrics per selector, over requests: recall (requests with a related record in the pool that got
at least one shown), precision (shown records that are related), and noise (requests with no
related record in the pool that got anything shown), each for `lineage` and for `lineage or
file`, for first requests and for all requests. Decider spend is capped in code per pass.
