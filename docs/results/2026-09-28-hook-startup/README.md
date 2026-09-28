# The Claude Code hook's start-up, before and after lazy imports (2026-09-28)

`sanchopanza hook` is one Python process per hook event, so what it imports is latency that
every hooked tool call pays before any decision. The end-to-end run
([claude-code-harness](../2026-09-28-claude-code-harness/)) measured 1.0-1.9 s for the command
with an empty input on the maintainer's Windows laptop, three runs each.

## What changed

- `sanchopanza` and `sanchopanza.providers` resolve their public names on first use
  (PEP 562). `from sanchopanza import Squire` works as before; importing a submodule no longer
  loads the squire, `asyncio` and every provider.
- The provider entry-point scan (`importlib.metadata`) runs only when a name is not built in.
- `sanchopanza.cli` imports the bench machinery, the DAG and the providers inside the
  subcommands that use them.
- `harness.claude_code.main` decides in code, before loading the squire or `asyncio`, whether
  the event can lead to a decision (`needs_decision`). It mirrors the early returns of the full
  path; `tests/test_hook_startup.py` checks that every event it skips would have answered `{}`
  and that the skipped path loads none of the heavy modules, in a fresh interpreter.

## Measured

Same laptop, same day, `measure.py` below: 31 interleaved runs per arm and input after one
warm-up round, the installed `sanchopanza` command with `PYTHONPATH` pointing at each tree,
null provider, no network. `before` is commit `5810509`.

| input | before | after |
|---|---|---|
| PreToolUse `Bash` (needs a decision) | 0.319 s | 0.251 s |
| PostToolUse `Bash` `ls`, scanning on (needs none) | 0.312 s | 0.170 s |
| Stop, done-check off (needs none) | 0.339 s | 0.170 s |
| bare `python -c pass` | 0.047 s | |

Medians; minimums and the raw lines are in [results.txt](results.txt). `python -X importtime`
of `sanchopanza.cli` plus `sanchopanza.harness.claude_code`: 221 ms before, 89 ms after
(median of seven).

## What this does and does not say

- The 1.0-1.9 s of the end-to-end run and the 0.3 s here were measured with the same command
  on the same laptop on the same day, under different load (the first while Claude Code
  sessions were running). The machine's state moves this number as much as the code does;
  compare arms only within one interleaved run.
- An event that needs a decision still loads the squire and `asyncio` (and `httpx` for Jev,
  about 45 ms), and then waits for the decision itself: Jev's median was 922 ms in the e2e run.
- The next step, not built: Claude Code 2.1 accepts `"type": "http"` hooks (it POSTs the same
  JSON to a URL) and an `if` field in permission-rule syntax that skips spawning the hook for
  non-matching calls. A long-lived local server would pay the start-up once and keep the
  squire's per-job memory; it needs its own lifecycle and security review first.

## Reproduce

```bash
git worktree add ../before 5810509
python docs/results/2026-09-28-hook-startup/measure.py "$(which python)" 31 ../before/src src
```
