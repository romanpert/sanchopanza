# Amendment 6: memory v6.2 (the shell touch on writes only), on data that does not exist yet

Written 2026-10-01, before any of the data it names exists. Sealed with the code it names
(`amendment-6.sha256`); each part is built once and scored once.

## Why

Amendment 5 did not confirm v6.1: on the maintainer's own sessions agents in auto mode read
through `sed -n` and `grep -n` about 38 times per request, and 196 of the 258 records the shell
touch gave were unrelated, all of them from reads made before any edit.

## What v6.2 changes (designed on data already seen, declared)

- `memory_hook.SHELL_READS = False`: a Bash or PowerShell call gives a record only for a file it
  writes (`shell.written`), by the edit rule; what it shows still orders the records of that
  file (the lines an interpreter's `s.replace` replaces). Reads through the shell give nothing.
- v6.1's gate (no shell touch once a session edits with a file tool) is removed: with reads off
  it only removed records of files the request wrote.
- `shell.written`, after an adversarial review that probed it: statements come from the
  quote- and comment-aware splitter; a heredoc body counts only when an interpreter runs it, or
  when a later statement runs the script it writes (`cat > /tmp/fix.py <<P ... P; python
  /tmp/fix.py`); `-c`/`-e` code only in an interpreter's statement; `perl -M...` is not `-i`;
  `cp -t DIR` names a folder; `->` is not a redirection; PowerShell's `-Path` or first
  positional argument, never a parameter's value or a `$variable`.

Development, all on seen data. **Two labels**, because the sealed one (`lineage or file`, from
file tools) cannot see an edit made through the shell, and the other (`+shell`, which also
counts a record related when the request writes one of its files through the shell) is
**circular for the shell touch**: both it and the touch decide what a command writes with
`shell.written`, so every record the shell touch gives is related under it by construction, and
a request it reaches cannot count as noise. Neither label alone measures usefulness.

| local, 632 requests | sealed label: recall / precision / noise | `+shell` (circular for the shell touch) | shell gives (related: sealed / `+shell`) |
|---|---|---|---|
| v5 | 0.923 / 0.858 / 0.019 | 0.667 / 0.892 / 0.019 | 0 |
| shell reads on, no gate | 0.968 / 0.329 / 0.221 | 0.985 / 0.594 / 0.149 | 416 (97 / 230) |
| **v6.2** | **0.949 / 0.536 / 0.126** | **0.977 / 0.931 / 0.019** | 152 (16 / 152) |

SWE-chat (each session's folder), sealed label, recall / precision / noise: v6.2 equals v5 on held out 2; held out 3 0.977 / 0.760 / 0.031 against 0.977 / 0.761 / 0.031 (two shell gives); held out 1 0.972 / 0.718 / 0.034 against 0.972 / 0.727 / 0.032 (four shell gives, one related by the sealed label, all four by `+shell`).

B2's 67 fresh requests, post hoc, truth from the run's own patches (**independent of the
parser**): v6.0 0.941 / 0.889 / 0.121, v6.1 0.941 / 0.927 / 0.091, **v6.2 0.941 / 0.973 /
0.030** (37 given); records that changed nothing 0.03 (v5 0.947).

**When** a shell give arrives (`v61_diag_local.py`, local): 125 of 152 at the request's first
write of that file, that is after the edit was made; 27 at a later write. For an agent that
edits through the shell, memory mostly arrives right after its first change of the file, not
before it. File-tool agents get theirs at the Read, before the edit, as in v5.

A hand audit of the 48 shell-write records of an earlier variant (the review): 43 clear writes
of the named file, 5 doubtful, 0 false.

## Fresh data and success

### Part A: an agent that edits through the shell (the purpose of v6), truth independent of the parser

The first adoption chain run with Sonnet 5.5 (`claude-sonnet-5-5`) in `benchmarks/adopt` whose
first session starts after this seal, every arm it ran, replayed by `v6_chain_real.py --tag
amendment-6` (its requests from the second on; truth and labels from the run's patches). All
requests together:

1. recall >= 0.60;
2. precision >= 0.80;
3. noise <= 0.10;
4. records that changed nothing <= 0.20.

Judged only with 20 or more requests that have a related record; otherwise reported, and part
A waits for the next such chain. If none has run by 2026-10-15, the owner decides.

### Part B: the maintainer's sessions (agents that mostly edit with file tools)

`local_v62.py`: sessions whose first stamp is in [2026-10-01 12:00, 2026-10-04 00:00) +02:00,
of folders as `local.py` takes them, not the first of their folder, each with up to five
sessions before it as its pool; built once after 2026-10-04 06:00, scored once.

5. Sealed label: v6.2 recall >= v5 recall - 0.005 (the shell touch must not cost the file
   tools' touch anything).
6. The write detector, judged independently of both labels: in the seeded sample (up to 60,
   seed 20261004) of records the shell touch gave, an auditor who sees only the command and the
   header of the record given (its file), with no label, judges at least 90 % as commands that
   clearly write that file and at most 5 % as clearly not writing it. The auditor is a fresh
   subagent, told nothing of the expected rate.

Reported, not criteria: both labels' precision and noise (the sealed one counts every shell
write as noise; `+shell` counts none), characters per request, records given through the
shell, how many at the request's first write of the file.

## What follows

v6.2 goes to main (with the owner's approval) only if parts A and B both pass.
