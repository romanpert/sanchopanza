---
name: sanchopanza-code
description: How to work in a Claude Code session that has sanchopanza installed. Use when a request describes behaviour rather than naming a symbol or file and you need to find where it lives in a large or unfamiliar repository; when the conversation was just compacted and a "sanchopanza guard" block follows the summary; when a sanchopanza hook denies a command or adds a note to a result; or when a task will be long and you want to keep the context small.
---

# Working with sanchopanza installed

sanchopanza sits beside you as hooks and one MCP tool. It never edits files and never answers
for you. What it changes for you:

## 1. Finding code: `mcp__sanchopanza__find_in_repo`

- **Use it** when the request describes behaviour ("the export drops the last row", "scope
  handling is wrong after refresh") and has no identifier you could grep, or when a grep for the
  obvious word returns dozens of files. Ask it in the request's own words:
  `find_in_repo(query="<the symptom, as the user put it>", k=8)`. It returns `path:lines` with an
  excerpt; then `Read` the lines it points to.
- **Do not use it** when the request already names a function, class, error message or file:
  `Grep` for that name is faster and exact.
- `kind="symbol"` finds definitions by name; `kind="file"` finds files by path words.

## 2. After a compaction

When the context fills up, Claude Code summarises the conversation. With sanchopanza, a block
headed `sanchopanza guard` follows the summary. It holds, verbatim:

- the output of commands that cannot be run again (their latest run),
- the files changed so far,
- the person's requests, word for word.

Trust that block over the summary for exact values (identifiers, numbers, tokens, paths). Do not
re-run a command whose output is in the block. Re-read a file before editing it, since the
summary does not hold its current text. Check the requests block for anything the summary
reduced or dropped before you call the work done.

## 3. Keep the context small

Every call re-reads the whole conversation, so a long session pays for every large output again
and again. sanchopanza sets the session to compact at a fixed budget; you help by not filling it:

- `Read` large files with `offset`/`limit` once you know where to look;
- pipe long command output through `tail`, `head` or `grep`, and run tests narrowly first
  (one file or `-k`), the full suite once at the end;
- do not paste back long outputs in your own messages.

## 4. When a hook speaks

- A denied shell command comes with its reason (deletes outside the work, sends files or secrets
  to the network, changes permissions, runs something downloaded). Do not retry it reworded; do
  the same thing another way or tell the person why you cannot.
- A note on a delegated task's result (unsourced claims, a search that repeats) is advice to
  check before you rely on that result.
