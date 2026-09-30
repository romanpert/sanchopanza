# Amendment 1 to prereg-find-e2e, before any session is scored

Written 2026-09-30 after six sessions started under the registered command and before any of
them was scored. Sealed with the code in `amend-find-e2e-1.sha256`.

## What happened

The pilot was meant to be one instance on arm F. A wrapper script dropped its arguments and
the full run started with three workers; it was stopped by hand after three sessions had ended
(astropy-12907 N and F, astropy-13236 N) and three were cut mid-way (astropy-13236 F,
astropy-8707 N and F).

## What the pilot showed

- **The MCP server mounts.** In the F session `sanchopanza` is `connected` and
  `mcp__sanchopanza__find_in_repo` is offered. The agent did not call it.
- **The tool set was not the registered one.** `--allowedTools Read Grep Glob` with
  `--permission-mode dontAsk` still offers all 36 built-in tools, and read-only Bash
  (`find . -name ... | grep | head`) ran without asking. The design says the agent has `Read`,
  `Grep` and `Glob` only.
- **Cost.** With 36 tool definitions in every request's prefix the three finished sessions cost
  0.18-0.20 USD each; 58 sessions at that rate do not fit the 7 USD ceiling.

## The change

- `--tools Read,Grep,Glob` limits the built-in set in both arms. Arm F keeps the MCP tool
  through `--mcp-config` and `--allowedTools`, as registered.
- The six sessions above are voided (moved to `find-e2e/void/`) and rerun under the fixed
  command. Their cost stays counted against the 7 USD ceiling: the finished ones at their
  reported cost, the cut ones at `cut_estimate` (their messages' usage at Haiku list price,
  times 1.5: on the finished sessions that usage is 70-77 % of the reported cost).
- A second launch was stopped seconds in, because the tool running it would have killed it at
  ten minutes. Its three cut sessions (astropy-12907 N and F, astropy-13236 N) are voided the
  same way (`void/*-cut2`). The run is now launched as a detached process.
- The first session under the fixed command (django-14559 F) is the pilot and stays in the run:
  4 tools offered, `sanchopanza` connected, a `FILES:` line, 0.131 USD. It did not call the
  tool.

Nothing else changes: instances, arms, prompt, hypotheses, caps, scoring.
