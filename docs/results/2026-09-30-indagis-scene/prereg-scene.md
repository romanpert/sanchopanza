# Pre-registration: the Indagis scene, Claude Code alone against Claude Code with sanchopanza

Written 2026-09-30, before any session. Sealed with `run.py`, `hook_key.py` and
`acceptance_test.py` in `prereg-scene.sha256`.

## The task

A real bug of Indagis, fixed by commit `3a0e243` on 2026-09-27: the MCP tool `declarar_parada`
answered "Anotado en el informe" and stored nothing, so `avisos_parada` in the job's result held
only the exhausted dials. Each session starts at its parent `6ca4e57` in a fresh git worktree of
Indagis, with the prompt in `run.py` (in Spanish, as the owner writes). The prompt names the two
functions the hidden test needs (`registrar_parada`, `paradas_declaradas`), because the tool
itself cannot be exercised without `claude_agent_sdk`, which is not installed on the host.

**Success** = the hidden acceptance test passes (4 tests: stored once, two lines kept in order,
missing fields do not break, `entrada.py` builds `avisos_parada` with `paradas_declaradas()`)
**and** the whole harness suite passes with it. Checked before any session: at `6ca4e57` the
acceptance test fails 4/4; at `3a0e243` it passes, and the suite is 340 green.

## Arms and repetitions

- `solo`: Claude Code, Sonnet 5.5, subscription; tools Read, Edit, Write, Grep, Glob, Bash;
  `--setting-sources project --strict-mcp-config --permission-mode dontAsk`, 60 turns at most,
  `--max-budget-usd 1.50`; the coordinating session's environment removed.
- `sancho`: the same, plus the settings `sanchopanza install --candor` writes (the default
  permission hook on Bash, Agent, Task and WebSearch, with Jev; candor's five hooks), loaded with
  `--settings`. Each hook runs through `hook_key.py`, which gives Jev's key to the hook process
  only: the agent's shell never sees it. Jev capped at 0.05 USD a session.
- 3 repetitions per arm, interleaved (solo-1, sancho-1, solo-2, ...), two at a time.

## Metrics

Per session: success, list cost (`total_cost_usd`), wall seconds, turns, tool calls, re-reads
(`Read` calls on a file already read in the session), tokens (input, cache read, cache write,
output), Jev's cost. Reported per arm as counts and medians. No hypothesis is tested: three
repetitions a side is a scene for the video, not a measurement, and it is reported as that.
What is registered is that **whatever comes out goes in**: if sanchopanza costs more, fails
more or changes nothing, the scene says so.

## Caps (in code)

| | Cap | Expected |
|---|---|---|
| Sessions (subscription, list price) | 9.00 USD for the scene (owner's hard cap 10), 1.50 a session | 3-7 |
| Jev | 0.05 a session | under 0.05 in all |

A session a cap skips is NOT RUN and reported. Worktrees are removed at the end; nothing is
committed to Indagis. The best passing diff is kept in the evidence folder in case the owner
wants it, and nothing is applied without asking.
