# Amendment to `prereg-confirm.md`: the Opus arm through the Claude Code CLI

Written 2026-09-27, before any Opus call on ATBench-Codex. `prereg-confirm.md` is unchanged and
its hash still holds; this file changes **one thing, the path to Opus**, and says why. Its own
hash is in `prereg-confirm-cli.sha256`; `benchmarks/cascade/confirm_cli.py --live` refuses to
spend unless both hashes match.

## What changes

- **Opus arm**: `claude-opus-5` through `sanchopanza.providers.claude_cli` (Claude Code 2.1.x,
  `claude -p`), not the Message Batches API. Same system prompt (`providers.llm.SYSTEM`), same
  user message (`state:` plus the JSON state), same answer schema (`llm.build_schema`), forced
  with `--json-schema` instead of a forced tool. No tools, no settings, no MCP, thinking off.
  Billed to the logged-in subscription, not to an API key.
- **Cost**: each session's `total_cost_usd` at list price, as Claude Code reports it. That
  figure includes the CLI's own overhead (a ~730-token prefix and the structured-output turn),
  which is **the same in every Opus call**, so the ratio "cascade over Opus alone" compares like
  with like. Absolute costs are not comparable with the API numbers of 2026-09-25.

## Why

The owner declined further API spend and asked for evaluations through Claude Code instead.
The batch run was estimated at 3.3 USD of API money; through the CLI it costs subscription
quota at list price (below) and 0 USD against any key.

## What does not change

Data (ATBench-Codex, Jev's recorded answers; the case count is halved below), the rule (symmetric escalation at
tau 0.45), the three criteria (accuracy within 2 points of Opus alone; bootstrap lower bound
>= -6 points, 2,000 resamples, seed 7; cost <= 50 %), the secondary reports (false allows,
escalation share, tau 0.35 and 0.65 as a band) and the verdict rule.

## Cases: the held-out half, fixed after a cost pilot

A pilot of three sessions (the first three cases of the file; their labels were read, never
compared with the gold) measured about 0.033 USD per case at list price, so all 500 would be
about 16.5 USD against the subscription. As `prereg-confirm.md` allows, the run is halved: it
uses the cases `benchmarks/cascade/run.py:half` assigns to `held_out` (a hash of the case id,
fixed before any of this, about 250 cases). Pilot sessions of cases outside that half are
ignored. Expected about 8.3 USD at list price; ceiling 10 USD. The interval widens accordingly.

## Added, stated before running

A session that fails (non-zero exit, no structured answer) is retried once; after that it counts
as a cancelled request, excluded and reported, as the original pre-registration does. The run
stops at a ceiling of 10 USD at list price. Answers are cached on disk, so a crash costs only
the sessions in flight.
