# F1 headroom gate, amendment 1 (2026-10-05, before any data)

An independent check of the seal (c4b853c) against the code passed on all nine items: HEAD,
launcher sha256, commands and caps, scenes, clean user, pinned Claude Code, dry run, empty run
folders, tests. It also found places where the prereg's wording differs from what the sealed
code does. This amendment changes no code and no number. The launcher's sha256 stays
`674634bd1b6a73af26e3fb60921b9ea7b9586d341f09884644c7436d005413dd`. Where the two disagree,
the code is what runs, and it is what this amendment describes.

1. **Without the token** the launcher itself does not refuse. `carry.py` exits 1, and the
   status file shows `sonnet-exit 1` and `opus-skipped`. Nothing is spent.
2. **Tests:** the four F1 test files hold 127 tests, not 126. 8e9dc68 added the `.env` token
   test. All of `tests/test_memory_carry*.py` (189) pass.
3. **Launch checks:** the dry run reads the real token from the `.env` of an agent with its own harness; there is no
   dummy token any more. No token prefix was found in any dry-run file.
4. **Family (ii):** a break counts only when the fact is not kept and the task did not fail
   (decision 4). This applies to every family; the sentence in family (ii) that says "any fact
   not kept" is superseded. Both counts are reported, as decision 4 says.
5. **Table labels:** a pair cut by a timeout shows as "(missing)" in the gate table, not
   "timeout". The status file and the log name the timeout. If Opus is skipped, the table has
   no Opus rows, and Opus reads NOT RUN.
6. **Reported item "subagents and their model"** is not computed by the code. It is read by
   hand from the session streams, and reported that way.
7. **Launch:** only by WMI (`Win32_Process Create`), never from a shell inside a Claude Code
   session. Started from inside one, the session env kept `CLAUDE_EFFORT`,
   `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING`, `CLAUDECODE` and `CLAUDE_CODE_MESSAGING_TOKEN`,
   because the scrub drops only `ANTHROPIC_*`, `CLAUDE_CODE_USE_*`, `TYPESAFE_*`,
   `SANCHOPANZA_*` and `CLAUDE_CONFIG_DIR`. A WMI process gets only the user's and the system's
   stored environment, which hold no `ANTHROPIC*` or `CLAUDE*` variables (checked
   2026-10-05). Each session's `init` is checked anyway.
