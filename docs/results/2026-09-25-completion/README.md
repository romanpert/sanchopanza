# Is the agent's "done" true? A calibrated check against labels by construction

Pre-registered in `prereg.md`, run on 2026-09-25. Both registered criteria hold.

A harness decides when an agent is finished, and by default it takes the agent's word.
browser-use added a second LLM judge on top of its agent's self-reported `done`; Claude Code
users write Stop hooks for the same reason. We found no published accuracy for either.

## Data

655 AgentDojo v1.2.2 trajectories of the `slack` suite, all recorded in this repository on
2026-09-24: five pipelines (Sonnet 5 undefended, with spotlighting, with two sanchopanza
defenses; Haiku 4.5 undefended), with and without injected attacks. The label is AgentDojo's
`utility`, computed by the benchmark from the environment's final state. No annotator. 342
trajectories succeeded, 313 did not.

Every arm sees the user request and the transcript (agent text, tool calls, tool results cut
to 1,500 characters), never the system prompt or the benchmark's fields.

## Result

| judge | accuracy, all 655 | accuracy, held-out half | precision of "done" | cost | median latency |
|---|---|---|---|---|---|
| trust the agent | 52.2 % | 55.3 % | 52.2 % | 0 | 0 |
| `jev-1.13.0`, one question | 93.7 % | 94.5 % | 92.4 % | 0.031 USD | 250 ms |
| `claude-sonnet-5`, same question, forced tool output | 95.1 % | 96.1 % | 93.1 % | 2.945 USD | 1,437 ms |
| cascade: Jev, Sonnet below confidence 0.70 | | **96.1 %** | | **21 % of Sonnet** | |

- **P13 holds**: Jev beats trusting the agent by 39 points on the held-out half. AUC of its
  probability 0.98.
- **P14 holds**: the cascade matches Sonnet exactly on the held-out half (difference 0.0,
  bootstrap interval [0.0, 0.0]) and sends 63 of 329 trajectories to Sonnet, at 21 % of
  Sonnet's cost. Over 500 random half splits the median difference is -0.3 points and the
  median cost 20 %.
- Jev alone is 1.6 points behind Sonnet alone, at 1/96 of its cost and 1/6 of its latency.

Sonnet's arm ran live through the Messages API, not the Message Batches API the
pre-registration named: its batch sat unprocessed for over an hour and was cancelled first, so
nothing was paid twice. The request body is identical; the cost above is list price.

### Per pipeline

| pipeline | n | trust | Jev | Sonnet |
|---|---|---|---|---|
| Sonnet 5, undefended | 131 | 72.5 % | 99.2 % | 100 % |
| Sonnet 5, spotlighting | 131 | 70.2 % | 96.2 % | 97.0 % |
| Sonnet 5, sanchopanza redacting | 131 | 20.6 % | 96.2 % | 96.2 % |
| Sonnet 5, sanchopanza marking | 131 | 22.1 % | 93.9 % | 97.7 % |
| Haiku 4.5, undefended | 131 | 75.6 % | 83.2 % | 84.7 % |

Haiku's own trajectories are the hard ones for both judges: its failures look finished.

## The Stop hook

`sanchopanza install --check-done` wires it into Claude Code; `SANCHO_CHECK_DONE=1` turns it
on. It blocks a stop, once, when p(done) < 0.5. That cut is derived on the derivation half to a
90 % precision target for a block, since a false block costs a turn: on the held-out half it
blocked 147 stops and 138 of them were unfinished work (93.9 %, Wilson lower bound 88.8 %),
catching 94 % of the unfinished runs. It never blocks twice in a row and lets the stop through
on any failure.

## What this does not settle

- **AgentDojo is not a coding session.** Its tasks are short tool-using requests with a
  checkable end state. Whether the same question works on a Claude Code session that edits a
  repository is unmeasured; the hook is opt-in for that reason.
- **One suite, 21 user tasks.** Trajectories of the same task are correlated across the five
  pipelines. The split is by file, so the same task appears in both halves; tau is a single
  number, so the leak is small, but it is there.
- **Two of the pipelines fail for a visible reason**: the redacting defense removed content
  the task needed, and the transcript shows it. The undefended and spotlighting rows are the
  fair ones, and they hold at 96 to 99 %.

## Reproducing

```bash
python benchmarks/completion/run.py --analyze          # free, from the recordings
python -m pytest tests/test_completion_bench.py        # pins the Jev numbers
```

Jev's answers are in `fixtures/completion-jev.jsonl`, Sonnet's in `llm-answers.jsonl`.
