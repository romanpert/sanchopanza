# Amendment to the 2026-09-25 cascade registration: the Sonnet 5 arm through the Claude Code CLI

Written 2026-09-27 at 23:05 +02:00, before any Sonnet call of this run and after a three-session
cost pilot whose labels were never compared with the gold. `../2026-09-25-cascade/prereg.md`
and `prereg-codex.md` are unchanged and their hashes still hold; this file changes **one thing,
the path to Sonnet**. Its hash is in `prereg-cli.sha256`; `benchmarks/cascade/sonnet_cli.py
--live` refuses to spend unless all three hashes match.

## Why

The registered primary verdicts, P1 (R-Judge) and P2 (register), and the Codex extension P9
compare the cascade with `claude-sonnet-5`. Its Message Batches sat unprocessed for over an
hour on 2026-09-25 and were cancelled, so none of the three was ever run. The owner asked for
them through Claude Code, billed to the subscription, as the Opus confirmation of 2026-09-27
was (`../2026-09-27-cascade-frontier/prereg-confirm-cli.md`).

## What changes

- **Sonnet arm**: `claude-sonnet-5` through `sanchopanza.providers.claude_cli` (`claude -p`),
  not the Message Batches API. Same system prompt (`providers.llm.SYSTEM`), same user message
  (`state:` plus the JSON state), same answer schema (`llm.build_schema`), forced with
  `--json-schema` instead of a forced tool. No tools, no settings, no MCP, thinking off.
- **Cost**: each session's `total_cost_usd` at list price, as Claude Code reports it, CLI
  overhead included. It is the same in every Sonnet call, so "cascade over Sonnet alone" compares
  like with like; absolute costs are not comparable with the Batch API numbers of the other arms.
- A session that fails (no structured answer) is retried once, then counts as a cancelled
  request, excluded and reported, as the registration does.

## What does not change

Everything else: the data (R-Judge at the registered commit, 571 records; the register, 298;
ATBench-Codex, 500), Jev's recorded answers, the hash split, the derivation rule (smallest tau on
the derivation half whose cascade accuracy reaches Sonnet alone's there), the criteria (on the
held-out half: accuracy difference >= -2 points, paired bootstrap lower bound >= -6 points with
2,000 resamples and seed 7, cascade cost <= 50 % of Sonnet alone), the verdict rule (P1 and P2:
solid; one: partial; neither: negative), P9 reported beside it, and the secondary reports.

## What the recorded answers already say (stated before running)

Jev alone on the held-out halves: R-Judge 86.3 %, register about 85 %, Codex about 79 %. Opus 5,
through two paths, scored 93.2 % held out on R-Judge and 79.9 % on Codex; Haiku 4.5 scored less
than Jev on all three. If Sonnet sits between them, P2 likely holds (the register favours Jev),
P9 likely holds (Codex does not separate the frontier from Jev), and P1 is the open one: on
R-Judge the Opus cascade needed tau 0.80 and failed on cost.

## Cost

Pilot: 0.011 USD per R-Judge case at list price. Codex cases are longer (Opus cost 0.030 there).
Estimated about 18 USD for all 1,369 cases; hard ceiling 25 USD at list price, billed to the
subscription, 0 USD to any key.
