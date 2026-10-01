# Amendment 5: memory v6.1 (the shell touch without history, message bodies or file-tool editors), on sessions no pass has scored

Written 2026-10-01, before any of the requests it names was built or scored. Sealed with the
code it names (`amendment-5.sha256`); the items are built once and scored once.

## Why

Amendment 4 did not confirm v6. What was found afterwards, all on data already seen:

- **The bench paired B2's records wrongly** (6073ae6): in arms S and Sm the replay counted the
  compaction summary of `claude -p` as a request. Rerun on the same 67 fresh B2 requests with
  that fix, **post hoc and so not a confirmation** (`chain-v6-real.json`, tag `corrected`): v6
  as sealed in amendment 4 has recall 0.941, precision 0.889, noise 0.121, records that changed
  nothing 0.03, which would have met criteria 1-4 of amendment 4 (v5: recall 0; 0.947 of its
  records changed nothing). By arm: N 1.000 / 0.818, S 1.000 / 0.947, Sm 0.846 / 0.867.
- **The bench gave SWE-chat items no working folder**: `build_v6.py` wrote none, so in the
  replay a shell command naming a file by its absolute path (without a `cd` first) never
  matched, while the hook keeps the folder the session started in. With it
  (`variants_v61.with_cwd`) even v5's figures move (held out 1: 0.950 / 0.748 / 0.030 becomes
  0.972 / 0.727 / 0.032) and the shell touch gives more. Amendment 4's SWE-chat figures were
  measured without it. Every number below has it.
- **The shell touch's noise on SWE-chat** (criterion 5, real). `v6_diag_sources.py`: most of
  it came from `git diff`/`git show` output, the rest from message bodies (`gh api ... --field
  body="$(cat <<EOF ...)"`) and from reads of files the request then did not edit, by agents
  that edit with Edit and Write and whose Read gives the same records anyway (the shell touch
  added no recall on any SWE-chat set).

## What v6.1 changes (designed on data already seen, declared)

1. In `context.shell.view`, through a new one-pass, quote- and comment-aware statement splitter
   (`context.statements`, Bash and PowerShell):
   - the output of a history command (`git diff/show/log/whatchanged/format-patch/range-diff`,
     `git stash show`, `gh pr diff`) is not in view when nothing else in the command prints
     code (`cd`, `echo`, `git status`, counting greps, filters in its pipe print none); when
     something else does (`sed -n 176,200p f; git diff g`), only the unified-diff blocks leave
     the output. `git show <rev>:<path>` and `git diff --no-index` are code, not history;
   - a heredoc (or PowerShell here-string) body is in view only when an interpreter runs it
     (source) or a shell does (more commands); a commit or PR body, or `cat > f <<E`, is not;
   - the quoted strings of a messaging statement (`git commit/tag/notes/merge/stash`, `gh`,
     `glab`, `curl`, `wget`, `hub`) are neither paths nor lines in view.
2. In `memory_hook.touch`: once a session edits an existing file through a file tool (Edit,
   MultiEdit, NotebookEdit; `GATE_EDITS`), its shell touch gives nothing
   (`SHELL_UNTIL_FILE_EDIT`; the flag lives in the session's state and survives prompts and
   compactions; a subagent's edit does not set it). An agent that edits only through the shell
   (Sonnet 5.5 in B2 never used a file tool to edit) keeps it, and so does one that creates a
   file with Write and edits on through the shell.

`shell.written` now also ignores a `<<` inside quotes or a comment. Nothing else changes: the
tree (`memory_tree`), the file tools' touch, recall at a prompt.

Three adversarial reviews: of the first version (2 high, 4 medium, 2 low: any history word
anywhere dropped all output, exponential and quadratic regexes, `bash <<E` bodies lost, `git
show rev:path` lost, `(` in a quoted title and `&` mis-split, `.py` taken for an interpreter, a
test passing without the change), of the splitter (2 high, 5 medium, 3 low: the heredoc judged
by the wrong statement, so `pytest && git commit -F - <<E` leaked its body; quadratic prefix
stripping; interpreters after the third word; a drive's colon taken for `rev:path`; comments;
PowerShell escapes and here-strings; `|&`; two tests passing without the change), and of the
gate (no high; a single Write closing the gate for a shell editor, so Write was taken out of
it; regression tests for the flag across a record given, a compaction and a subagent). All
fixed with tests before the numbers below.

Development (`variants_v61.py`, the touch through the hook's code, each session's folder;
development and held out 1 used to design, held out 2 and 3 seen in amendment 4 and used here
as well), all requests, `lineage or file`, recall / precision / noise, and records given through
the shell (related):

| set (requests) | v5 | v6.0 | v6.1 | shell v6.0 | shell v6.1 |
|---|---|---|---|---|---|
| development (953) | 0.932 / 0.770 / 0.032 | 0.932 / 0.766 / 0.032 | 0.932 / 0.770 / 0.032 | 1 (0) | 0 (0) |
| held out 1 (1,490) | 0.972 / 0.727 / 0.032 | 0.972 / 0.695 / 0.037 | 0.972 / 0.727 / 0.032 | 16 (3) | 2 (1) |
| held out 2 (3,117) | 0.978 / 0.769 / 0.040 | 0.978 / 0.755 / 0.043 | 0.978 / 0.764 / 0.041 | 26 (9) | 12 (7) |
| held out 3 (3,127) | 0.977 / 0.761 / 0.031 | 0.977 / 0.741 / 0.035 | 0.977 / 0.757 / 0.032 | 31 (7) | 9 (1) |

Without the gate (rule 1 only) precision was 0.709 / 0.761 / 0.752 on held out 1-3; with the
gate closing at Write too, 0.727 / 0.764 / 0.759.

B2's 67 fresh requests, post hoc (`chain-v6-real.json`): v6.0 0.941 / 0.889 / 0.121 (45 given),
v6.1 0.941 / 0.927 / 0.091 (41 given); by arm v6.1: N 1.000 / 0.818, S 1.000 / 0.941, Sm 0.846
/ 1.000. The mixed-history rule and counting greps were added after seeing two of these
requests (`wc -l a b; grep -c t a; git diff f | head`, `sed -n 176,200p f; git diff g`).

Two recordings of B2 with the same code, one after the other, gave the same recall, precision
and noise but 0.030 and 0.034 of records that changed nothing (about one record): the tree's
snapshot has a deadline (3 s per git call, 4 s per Stop) and under load it can miss. Declared;
not addressed here.

Not taken (measured): a shell read needing two of a record's lines in view (removes related
one-line grep hits as often as unrelated ones); closing the shell touch at the session's first
file-tool call, or while file-tool calls outnumber shell calls (both left SWE-chat precision
within 0.005 of v5 but cut B2 Sm's recall from 0.846 to 0.615).

## Fresh data: the maintainer's own sessions that no pass has scored

`local_v6.py --build`, locally (no text leaves the machine: the touch calls no model; the
repository gets counts only). Project folders under `~/.claude/projects` (benchmark and
temporary folders excluded, as `local.py`). The only earlier local pass (`local.py`, 1a4963c)
scored, per folder, the sessions after the first of one seeded window of six; `--check-v3`
rebuilds those windows from the sessions that existed then. **The rebuild gives 13 groups (as
published) but 202 requests against 197**, with that commit's code too and no session grown or
created since: the windows may not be exactly those scored. Declared; nothing of v6 or v6.1 was
designed on local data (that pass published one aggregate of the v3 touch), so a session scored
then and taken now biases nothing measured here. Targets: every session of a folder started
before 2026-10-01 12:00 +02:00 that is not after the first of a rebuilt window, and not the
first of its folder; each with up to five sessions before it as its pool. Items as
`build_v6.py` builds SWE-chat's, Bash and PowerShell calls kept (PowerShell replayed as
PowerShell), each with its session's folder. Counted before sealing (no label read): 157 target
sessions in 12 folders.

Labels see only file tools (Edit, MultiEdit, Write), as on SWE-chat: a request that changed a
file through the shell is never "related" by label, so a record the shell touch gives for a
file the request then wrote through the shell counts against it. The tree (records of shell
edits) cannot be replayed from transcripts.

## Success (all; v6.1 touch against v5 touch, on the fresh local items)

All requests, `lineage or file`:

1. v6.1 recall >= v5 recall - 0.005.
2. v6.1 precision >= v5 precision - 0.01.
3. v6.1 noise <= v5 noise + 0.005.
4. Of the records the shell touch gives, at least half related, judged only if it gives 20 or
   more (otherwise reported, not a criterion).

Reported, not criteria: the same on the subset of targets started after the v3 pass (2026-09-30
21:03 +02:00), `lineage` precision, characters per request, shell calls by tool.

## What follows

v6 is integrated in main only if this amendment confirms **and** a later one confirms the gain
where it is meant to pay: an agent that reads and edits through the shell (Sonnet 5.5 in B2), on
requests that do not exist yet (a new adoption run after phase A ends, its criteria sealed
before it runs, as amendment 6). This amendment can only show that v6.1 does no harm where
agents edit with file tools.
